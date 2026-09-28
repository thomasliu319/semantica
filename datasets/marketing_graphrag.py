"""Lightweight GraphRAG over the marketing knowledge graph (OpenSpec marketing-graphrag).

Four stages: entity linking -> path binding -> subgraph retrieval -> answer assembly.
Rule-based (G1), in-memory JSON + parquet (G2), no LLM / no graph DB / no network.

Caliber is structural: every "achieve" answer is forced through
org_scope=in_scope AND zprod_type in budget-covered AND dept not-null AND 万元 (B6/B7/B8/B3).
Questions on the "do-not-ask" list are refused explicitly (G5).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

_DS = Path(__file__).resolve().parent
DEFAULT_IN = _DS / "processed" / "marketing_2026H1"
DEFAULT_GRAPH = _DS / "json" / "marketing_cleaned_semantics.json"

METRIC_WORDS = {
    "管理出机": "management_ship",
    "考核出机": "assessment_ship",
    "出机": "assessment_ship",
    "管理签单": "management_sign",
    "签单达成": "management_sign",
}
BUDGET_COL = {
    "management_ship": "management_ship_budget_hs",
    "assessment_ship": "assessment_ship_budget_hs",
    "management_sign": "management_signed_contract_hs",
}
FACT_OF_METRIC = {"management_ship": "ship", "assessment_ship": "ship", "management_sign": "sign"}

REFUSALS: list[tuple[list[str], str]] = [
    (["毛利", "成本", "利润", "净利"], "成本/毛利字段在禁止直查的底层表（FinalCost），本图未建模，不能回答"),
    (["主管", "手下", "团队业绩"], "主管只有姓名无工号键，存在重名歧义；本图不建 Supervisor 节点，不能回答"),
    (["身份证", "手机号", "电话", "联系方式", "出生日期"], "PII 不进分析层（D3），不提供"),
    (["全年", "下半年", "Q3", "Q4", "7月", "8月", "9月", "10月", "11月", "12月"], "数据窗口仅 2026-01~06（H1），窗口外无法回答"),
]


class MarketingGraphRAG:
    def __init__(self, inp: Path = DEFAULT_IN, graph: Path = DEFAULT_GRAPH) -> None:
        self.ship = pd.read_parquet(inp / "ship_order_line.parquet")
        self.sign = pd.read_parquet(inp / "sign_order_line.parquet")
        self.emp = pd.read_parquet(inp / "emp_dim.parquet")
        self.dept = pd.read_parquet(inp / "dept_dim.parquet")
        self.prod = pd.read_parquet(inp / "product_dim.parquet")
        self.cust = pd.read_parquet(inp / "customer_dim.parquet")
        self.dbud = pd.read_parquet(inp / "dept_budget_month.parquet")
        self.pbud = pd.read_parquet(inp / "product_budget_month.parquet")
        self.report = json.loads((inp / "dq_report.json").read_text(encoding="utf-8"))
        self.graph_meta = json.loads(Path(graph).read_text(encoding="utf-8"))["meta"] if Path(graph).exists() else {}
        self.covered = sorted(self.pbud["product_type"].dropna().unique().tolist())

    # ---------------- stage 1: entity linking ---------------- #

    def link(self, q: str) -> dict:
        ents: dict[str, Any] = {}

        # 大区优先于科室：华南大区 这类「区名」同时出现在 dept 值域里（ontology §2.1 的 4 个落单值）
        for name in sorted(self.dept["area"].dropna().astype(str).unique(), key=len, reverse=True):
            if name and name in q:
                ents["area"] = name
                break
        if "area" not in ents:
            for name in sorted(self.dept["fdept"].dropna().astype(str).unique(), key=len, reverse=True):
                if name and name in q:
                    ents["dept"] = name
                    break
        for t in sorted(self.covered, key=len, reverse=True):
            if t in q:
                ents["product_type"] = t
                break
        if "product_type" not in ents:
            for t in sorted(self.prod["zprod_type"].dropna().astype(str).unique(), key=len, reverse=True):
                if t and t in q:
                    ents["product_type"] = t
                    break
        for z in sorted(self.prod["zprod_name"].dropna().astype(str).unique(), key=len, reverse=True):
            if z and z in q:
                ents["model"] = z
                break

        m = re.search(r"(\d{4})-(\d{1,2})", q)
        if m:
            ents["month"] = int(m.group(2))
        else:
            m2 = re.search(r"(\d{1,2})\s*月", q)
            if m2:
                ents["month"] = int(m2.group(1))

        for name in sorted(self.emp["sales_name"].dropna().astype(str).unique(), key=len, reverse=True):
            if name and name in q:
                hits = self.emp[self.emp["sales_name"] == name]["sales_code"].tolist()
                ents["emp"] = hits[0] if len(hits) == 1 else hits
                break
        c = re.search(r"\bC\d{5,}\b", q)
        if c:
            ents["customer"] = c.group(0)

        for word, metric in METRIC_WORDS.items():
            if word in q:
                ents["metric"] = metric
                break
        if "metric" not in ents:
            ents["metric"] = "assessment_ship" if "出机" in q or "出货" in q else "management_sign"
        return ents

    # ---------------- stage 2: intent + refusal ---------------- #

    def classify(self, q: str, ents: dict) -> tuple[str, str | None]:
        for words, reason in REFUSALS:
            if any(w in q for w in words):
                return "refuse", reason
        # 科室 × 产品类型 的预算交叉（分配矩阵未导出）
        if ("dept" in ents or "area" in ents or "科室" in q) and "product_type" in ents and (
            "达成" in q or "预算" in q
        ):
            return "refuse", "预算的科室维度与产品类型维度是同一笔预算的两个投影，分配矩阵未导出，不能交叉（B10）"
        if re.search(r"连续.{0,6}(不签单|没签单|未出机|未出货|无签单)", q) or any(
            w in q for w in ("活跃度", "没出机", "零签单")
        ):
            return "behavior_emp", None
        if "customer" in ents or ("客户" in q and "机型" in q):
            return "customer_model", None
        if "product_type" in ents or "机型" in q or "产品类型" in q or "份额" in q or "结构" in q:
            if "达成" in q or "预算" in q or "对照" in q:
                return "achieve_product", None
            return "structure_share", None
        if "达成" in q or "预算" in q or "完成" in q:
            return "achieve_dept", None
        return "structure_share", None

    # ---------------- stage 3: retrieval ---------------- #

    def _caliber(self, df: pd.DataFrame) -> pd.Series:
        return (
            (df["org_scope"] == "in_scope")
            & df["zprod_type"].isin(self.covered)
            & (df["fdept"].fillna("") != "")
        )

    def _by_dept(self, df: pd.DataFrame, area: str | None) -> pd.Series:
        m = self._caliber(df)
        if area:
            depts = set(self.dept.loc[self.dept["area"] == area, "fdept"])
            m &= df["fdept"].isin(depts)
        return m

    def achieve_dept(self, ents: dict) -> dict:
        metric = ents.get("metric", "assessment_ship")
        fact = self.ship if FACT_OF_METRIC[metric] == "ship" else self.sign
        dept_filter = ents.get("dept")
        area = ents.get("area")
        month = ents.get("month")

        m = self._by_dept(fact, area)
        if dept_filter:
            m &= fact["fdept"] == dept_filter
        if month:
            m &= fact["month"] == month
        num = float(fact.loc[m, "total_money_fc_hs_wan"].sum())

        b = self.dbud
        bm = pd.Series(True, index=b.index)
        if dept_filter:
            bm &= b["fdept"] == dept_filter
        elif area:
            bm &= b["area"] == area
        if month:
            bm &= b["month"] == month
        den = float(b.loc[bm, BUDGET_COL[metric]].sum())

        top = (
            fact[m].groupby("fdept")["total_money_fc_hs_wan"].sum().sort_values(ascending=False).head(10)
        )
        return {
            "intent": "achieve_dept",
            "metric": metric,
            "caliber": {"org_scope": "in_scope", "model_covered_only": True,
                        "dept_notnull": True, "unit": "万元含税"},
            "scope": {"dept": dept_filter, "area": area, "month": month},
            "numerator_wan": round(num, 2),
            "denominator_wan": round(den, 2),
            "achieve_pct": round(num / den * 100, 1) if den else None,
            "evidence": {"rows": int(m.sum()), "budget_rows": int(bm.sum())},
            "top_contributors": [{"fdept": k, "amount_wan": round(float(v), 2)} for k, v in top.items()],
        }

    def achieve_product(self, ents: dict) -> dict:
        metric = ents.get("metric", "assessment_ship")
        fact = self.ship if FACT_OF_METRIC[metric] == "ship" else self.sign
        ptype = ents.get("product_type")
        month = ents.get("month")

        m = self._caliber(fact)
        if ptype:
            m &= fact["zprod_type"] == ptype
        if month:
            m &= fact["month"] == month
        num = float(fact.loc[m, "total_money_fc_hs_wan"].sum())

        b = self.pbud
        bm = pd.Series(True, index=b.index)
        col = BUDGET_COL[metric]
        if col not in b.columns:
            col = "gl_management_signed_contract_hs"
        if ptype:
            bm &= b["product_type"] == ptype
        if month:
            bm &= b["month"] == month
        den = float(b.loc[bm, col].sum())
        caveats = []
        if ptype and ptype not in self.covered:
            caveats.append(
                f"{ptype} 不在产品预算覆盖的 {len(self.covered)} 类内（B7）；"
                "其预算挂在 SalesDept（如 3C销售部）且 Fdept 为空，不走产品类型维度，故对照为 0"
            )
        return {
            "intent": "achieve_product",
            "caveats": caveats,
            "metric": metric,
            "caliber": {"org_scope": "in_scope", "model_covered_only": True,
                        "dept_notnull": True, "unit": "万元含税"},
            "scope": {"product_type": ptype, "month": month, "covered_types": self.covered},
            "numerator_wan": round(num, 2),
            "denominator_wan": round(den, 2),
            "achieve_pct": round(num / den * 100, 1) if den else None,
            "evidence": {"rows": int(m.sum()), "budget_rows": int(bm.sum())},
        }

    def behavior_emp(self, ents: dict) -> dict:
        q = ents.get("_q") or ""
        if "出机" in q or "出货" in q:
            kind = "ship"
        else:
            kind = "sign"
        fact = self.sign if kind == "sign" else self.ship

        m = re.search(r"连续\s*(\d+)\s*个?月", q)
        need = int(m.group(1)) if m else None
        cutoff = int(ents.get("month") or 6)

        biz = self.emp[self.emp["user_role"] == "业务"]["sales_code"]
        act = fact[fact["sales_code"].isin(set(biz))]
        by_emp: dict[str, set[int]] = {
            k: set(v) for k, v in act.groupby("sales_code")["month"].apply(list).items()
        }
        names = dict(zip(self.emp["sales_code"], self.emp["sales_name"]))
        status = dict(zip(self.emp["sales_code"], self.emp["employment_status"]))

        runs: list[tuple[str, int]] = []
        for code in biz:
            months = by_emp.get(code, set())
            run = 0
            for mm in range(cutoff, 0, -1):
                if mm in months:
                    break
                run += 1
            runs.append((code, run))
        runs.sort(key=lambda x: -x[1])

        if need is None:
            # 「连续不签单人数」默认口径：截至 cutoff 月已连续 >=3 个月无事件
            need = 3
        hit = [r for r in runs if r[1] >= need]
        return {
            "intent": "behavior_emp",
            "event": kind,
            "caliber": {"user_role": "业务", "window": "2026-01~06", "cutoff_month": cutoff,
                        "consecutive_months": need},
            "business_headcount": int(len(biz)),
            "no_event_in_window": int(sum(1 for _, r in runs if r == cutoff)),
            "consecutive_hit_count": len(hit),
            "sample": [{"sales_code": c, "sales_name": names.get(c, ""),
                        "employment_status": status.get(c, ""),
                        "consecutive_empty_months": r} for c, r in hit[:10]],
            "caveats": ["计数为口径探针，不是名单报告（B1）；离职人员空窗属状态非业绩，已单列 employment_status"],
        }

    def customer_model(self, ents: dict) -> dict:
        code = ents.get("customer")
        dfs = []
        for f, rel in ((self.sign, "contract_party"), (self.ship, "ship_to")):
            if code:
                sub = f[f["cust_code"] == code]
            else:
                sub = f
            if len(sub):
                g = sub.groupby("zprod_name")["total_money_fc_hs_wan"].sum().sort_values(ascending=False)
                dfs.append((rel, g))
        out = []
        for rel, g in dfs:
            for z, v in g.head(10).items():
                out.append({"role": rel, "zprod_name": z, "amount_wan": round(float(v), 2)})
        name = ""
        if code:
            hit = self.cust[self.cust["cust_code"] == code]
            name = hit["cust_name"].iloc[0] if len(hit) else ""
        return {
            "intent": "customer_model",
            "customer": {"cust_code": code, "cust_name": name},
            "top_models": out,
            "caveats": ["签单侧角色=contract_party，出货侧=ship_to，两者不合并计额"],
        }

    def structure_share(self, ents: dict) -> dict:
        metric = ents.get("metric", "assessment_ship")
        fact = self.ship if FACT_OF_METRIC[metric] == "ship" else self.sign
        m = fact["org_scope"] == "in_scope"
        if ents.get("product_type"):
            m &= fact["zprod_type"] == ents["product_type"]
        if ents.get("month"):
            m &= fact["month"] == ents["month"]
        g = fact[m].groupby("zprod_type")["total_money_fc_hs_wan"].sum().sort_values(ascending=False)
        total = float(g.sum())
        return {
            "intent": "structure_share",
            "caliber": {"org_scope": "in_scope", "unit": "万元含税", "basis": "自身总额（不是预算）"},
            "total_wan": round(total, 2),
            "shares": [{"zprod_type": k, "amount_wan": round(float(v), 2),
                        "pct": round(float(v) / total * 100, 1) if total else None,
                        "budget_covered": k in self.covered} for k, v in g.items()],
        }

    # ---------------- stage 4: answer ---------------- #

    def answer(self, q: str) -> dict:
        ents = self.link(q)
        ents["_q"] = q
        intent, reason = self.classify(q, ents)
        if intent == "refuse":
            return {"question": q, "intent": "refuse", "answer": None,
                    "refusal_reason": reason, "linked_entities": {k: v for k, v in ents.items() if k != "_q"}}
        fn = {
            "achieve_dept": self.achieve_dept,
            "achieve_product": self.achieve_product,
            "behavior_emp": self.behavior_emp,
            "customer_model": self.customer_model,
            "structure_share": self.structure_share,
        }[intent]
        body = fn(ents)
        body["question"] = q
        body["linked_entities"] = {k: v for k, v in ents.items() if k != "_q"}
        body["caveats"] = body.get("caveats", []) + [
            "达成率为口径探针，不是分析报告（B1/G6）",
            f"参考基准：考核出机 130.6% / 管理出机 91.1% / 管理签单 103.2%（H1 默认口径）",
        ]
        return body


def main() -> None:
    ap = argparse.ArgumentParser(description="Marketing GraphRAG (rule-based, in-memory)")
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    ap.add_argument("--q", required=True, help="自然语言问句")
    ap.add_argument("--compact", action="store_true")
    a = ap.parse_args()

    rag = MarketingGraphRAG(a.inp, a.graph)
    out = rag.answer(a.q)
    print(json.dumps(out, ensure_ascii=False, indent=None if a.compact else 2))


if __name__ == "__main__":
    main()
