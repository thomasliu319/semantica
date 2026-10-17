"""Marketing GraphRAG bridge for the Explorer Decisions workspace.

Ports the rule-based ``MarketingGraphRAG`` from ``datasets/marketing_graphrag.py``
into the installed package (paths anchored to the repo root, mirroring
``semantica/explorer/marketing_metrics.py``) and exposes ``run_marketing_graphrag``,
which turns a natural-language question into a ``GraphRAGResponse``-compatible
payload so the Decisions workspace can run the same metrics as the marketing
model's GraphRAG (achieve rates, structure/share, customer × model, salesperson
behavior) under ``v=marketing``.

Caliber is structural: every "achieve" answer is forced through
org_scope=in_scope AND zprod_type in budget-covered AND dept not-null AND 万元.
Questions on the "do-not-ask" list are refused explicitly.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
PROCESSED = REPO / "datasets" / "processed" / "marketing_2026H1"
GRAPH_JSON = REPO / "datasets" / "json" / "marketing_cleaned_semantics.json"

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

METRIC_LABEL = {
    "management_ship": "管理出机",
    "assessment_ship": "考核出机",
    "management_sign": "管理签单",
}

ENTITY_LABEL = {
    "area": "大区",
    "dept": "科室",
    "product_type": "产品类型",
    "model": "机型",
    "month": "月",
    "emp": "业务员",
    "customer": "客户",
    "metric": "指标",
}

REFUSALS: list[tuple[list[str], str]] = [
    (["毛利", "成本", "利润", "净利"], "成本/毛利字段在禁止直查的底层表（FinalCost），本图未建模，不能回答"),
    (["主管", "手下", "团队业绩"], "主管只有姓名无工号键，存在重名歧义；本图不建 Supervisor 节点，不能回答"),
    (["身份证", "手机号", "电话", "联系方式", "出生日期"], "PII 不进分析层（D3），不提供"),
    (["全年", "下半年", "Q3", "Q4", "明年", "上半年"], "数据窗口仅 2026-01~06（H1），窗口外无法回答"),
]


class MarketingGraphRAG:
    MAX_MONTH = 6  # 数据窗口 2026-01~06（H1）

    def __init__(self) -> None:
        self.ship = pd.read_parquet(PROCESSED / "ship_order_line.parquet")
        self.sign = pd.read_parquet(PROCESSED / "sign_order_line.parquet")
        self.emp = pd.read_parquet(PROCESSED / "emp_dim.parquet")
        self.dept = pd.read_parquet(PROCESSED / "dept_dim.parquet")
        self.prod = pd.read_parquet(PROCESSED / "product_dim.parquet")
        self.cust = pd.read_parquet(PROCESSED / "customer_dim.parquet")
        self.dbud = pd.read_parquet(PROCESSED / "dept_budget_month.parquet")
        self.pbud = pd.read_parquet(PROCESSED / "product_budget_month.parquet")
        self.covered = sorted(self.pbud["product_type"].dropna().unique().tolist())

    # ---------------- v1.3 时间跨度累加语义 ---------------- #

    @staticmethod
    def _parse_time(q: str) -> dict | None:
        """v1.3 时间口径解析（对应 biz:timeKind 五值）。

        归一为 ``{year, start, end, kind}``，start/end 为闭区间月：
        - ``asof``   截止目前/最新 → 1..MAX_MONTH（取最新完整月）
        - ``ytd``    截止N月 → 1..N 累计（含当月，RULE-1/CT13，禁止降级为单月）
        - ``range``  1-N月 → 1..N 累计
        - ``month``  裸单月 N月 → N..N（仅当问句未用「截止/1-N」措辞）
        """
        year = None
        ym = re.search(r"(20\d{2})\s*年", q)
        ymh = re.search(r"(20\d{2})\s*[-/]\s*(\d{1,2})\s*月?", q)
        if ym:
            year = int(ym.group(1))
        elif ymh:
            year = int(ymh.group(1))

        if re.search(r"截止\s*(目前|最新|当前|今天|当下)", q):
            return {"year": year, "start": 1, "end": MarketingGraphRAG.MAX_MONTH, "kind": "asof"}

        rng = re.search(r"(\d{1,2})\s*[-~至到]\s*(\d{1,2})\s*月", q)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            return {"year": year, "start": min(a, b), "end": max(a, b), "kind": "range"}

        m_ytd = re.search(r"截止\s*(?:20\d{2}\s*年)?\s*(\d{1,2})\s*月", q)
        if m_ytd:
            return {"year": year, "start": 1, "end": int(m_ytd.group(1)), "kind": "ytd"}

        m_single = re.search(r"(\d{1,2})\s*月", q)
        if m_single:
            mm = int(m_single.group(1))
            return {"year": year, "start": mm, "end": mm, "kind": "month"}

        if ymh:
            return {"year": year, "start": int(ymh.group(2)), "end": int(ymh.group(2)), "kind": "month"}

        return None

    def _time_mask(self, df: pd.DataFrame, time: dict | None) -> pd.Series:
        """月份累加掩码：fyear=:Y AND fperiod BETWEEN start AND end（闭区间，含当月）。"""
        if not time:
            return pd.Series(True, index=df.index)
        m = pd.Series(True, index=df.index)
        if time.get("year") is not None:
            m &= df["year"].astype(str) == str(time["year"])
        m &= (df["month"] >= time["start"]) & (df["month"] <= time["end"])
        return m

    def _time_caveat(self, time: dict | None) -> list[str]:
        """把解析出的时间口径写成口径提示（含超出窗口的说明）。"""
        if not time:
            return []
        kind = time["kind"]
        s, e = time["start"], time["end"]
        out = []
        if kind in ("ytd", "range"):
            label = f"1-{e}月累计（闭区间、含当月，RULE-1/CT13）"
            if e > self.MAX_MONTH:
                label += f"；数据窗口仅 2026-01~{self.MAX_MONTH:02d}，{self.MAX_MONTH + 1}-{e}月未取数"
            out.append(f"时间口径={label}")
        elif kind == "asof":
            out.append(f"时间口径=截止目前（取最新完整月 2026-{self.MAX_MONTH:02d}）")
        elif kind == "month":
            out.append(f"时间口径=单月 2026-{e:02d}月")
            if e > self.MAX_MONTH:
                out.append(f"数据窗口仅 2026-01~{self.MAX_MONTH:02d}，{e}月超出窗口")
        return out

    # ---------------- stage 1: entity linking ---------------- #

    def link(self, q: str) -> dict:
        ents: dict[str, Any] = {}

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

        time = self._parse_time(q)
        if time:
            ents["time"] = time
            # 保留 month 别名，兼容 behavior 等仅需截止月的意图
            ents["month"] = time["end"]

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
        # 区间感知拒答：整段窗口都落在数据窗口外才拒（如「8月」），
        # 部分越界（如「截止7月」）放行并在口径提示中说明（RULE-1/CT13）。
        time = ents.get("time")
        if time and time.get("start", 1) > self.MAX_MONTH:
            return "refuse", f"请求月份 {time['start']} 月超出数据窗口 2026-01~{self.MAX_MONTH:02d}（H1），无法回答"
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

    def _dept_detail_rows(self, metric: str, area: str | None, dept_filter: str | None, time: dict | None) -> tuple[list[dict], dict]:
        """按 销售部×大区×科室 汇总目标/达成/达成率，返回 (明细行, 总计)。"""
        fact = self.ship if FACT_OF_METRIC[metric] == "ship" else self.sign
        m = self._by_dept(fact, area)
        if dept_filter:
            m &= fact["fdept"] == dept_filter
        m &= self._time_mask(fact, time)
        fact_g = fact[m].groupby(["sales_dept", "area", "fdept"], dropna=False)["total_money_fc_hs_wan"].sum()

        b = self.dbud
        bm = pd.Series(True, index=b.index)
        if dept_filter:
            bm &= b["fdept"] == dept_filter
        elif area:
            bm &= b["area"] == area
        bm &= self._time_mask(b, time)
        bud_g = b[bm].groupby(["sales_dept", "area", "fdept"], dropna=False)[BUDGET_COL[metric]].sum()

        combined = pd.DataFrame({"target_wan": bud_g, "achieve_wan": fact_g}).fillna(0.0)
        if combined.empty:
            return [], {"target_wan": 0.0, "achieve_wan": 0.0, "achieve_pct": None}

        combined["achieve_pct"] = combined.apply(
            lambda r: round(float(r["achieve_wan"]) / float(r["target_wan"]) * 100, 2)
            if r["target_wan"] else None,
            axis=1,
        )
        # 达成率降序，无目标（den=0）沉底
        combined = combined.sort_values("achieve_pct", ascending=False, na_position="last")

        rows: list[dict] = []
        for (sd, ar, fd), r in combined.iterrows():
            rows.append({
                "sales_dept": "" if pd.isna(sd) else str(sd),
                "area": "" if pd.isna(ar) else str(ar),
                "fdept": "" if pd.isna(fd) else str(fd),
                "target_wan": round(float(r["target_wan"]), 2),
                "achieve_wan": round(float(r["achieve_wan"]), 2),
                "achieve_pct": round(float(r["achieve_pct"]), 2) if r["achieve_pct"] is not None else None,
            })

        tgt = float(combined["target_wan"].sum())
        ach = float(combined["achieve_wan"].sum())
        totals = {
            "target_wan": round(tgt, 2),
            "achieve_wan": round(ach, 2),
            "achieve_pct": round(ach / tgt * 100, 2) if tgt else None,
        }
        return rows, totals

    def achieve_dept(self, ents: dict) -> dict:
        metric = ents.get("metric", "assessment_ship")
        fact = self.ship if FACT_OF_METRIC[metric] == "ship" else self.sign
        dept_filter = ents.get("dept")
        area = ents.get("area")
        time = ents.get("time")

        m = self._by_dept(fact, area)
        if dept_filter:
            m &= fact["fdept"] == dept_filter
        m &= self._time_mask(fact, time)
        num = float(fact.loc[m, "total_money_fc_hs_wan"].sum())

        b = self.dbud
        bm = pd.Series(True, index=b.index)
        if dept_filter:
            bm &= b["fdept"] == dept_filter
        elif area:
            bm &= b["area"] == area
        bm &= self._time_mask(b, time)
        den = float(b.loc[bm, BUDGET_COL[metric]].sum())

        top = (
            fact[m].groupby("fdept")["total_money_fc_hs_wan"].sum().sort_values(ascending=False).head(10)
        )
        details, totals = self._dept_detail_rows(metric, area, dept_filter, time)
        return {
            "intent": "achieve_dept",
            "metric": metric,
            "caliber": {"org_scope": "in_scope", "model_covered_only": True,
                        "dept_notnull": True, "unit": "万元含税"},
            "scope": {"dept": dept_filter, "area": area, "time": time},
            "numerator_wan": round(num, 2),
            "denominator_wan": round(den, 2),
            "achieve_pct": round(num / den * 100, 1) if den else None,
            "evidence": {"rows": int(m.sum()), "budget_rows": int(bm.sum())},
            "top_contributors": [{"fdept": k, "amount_wan": round(float(v), 2)} for k, v in top.items()],
            "details": details,
            "totals": totals,
            "caveats": self._time_caveat(time),
        }

    def achieve_product(self, ents: dict) -> dict:
        metric = ents.get("metric", "assessment_ship")
        fact = self.ship if FACT_OF_METRIC[metric] == "ship" else self.sign
        ptype = ents.get("product_type")
        time = ents.get("time")

        m = self._caliber(fact)
        if ptype:
            m &= fact["zprod_type"] == ptype
        m &= self._time_mask(fact, time)
        num = float(fact.loc[m, "total_money_fc_hs_wan"].sum())

        b = self.pbud
        bm = pd.Series(True, index=b.index)
        col = BUDGET_COL[metric]
        if col not in b.columns:
            col = "gl_management_signed_contract_hs"
        if ptype:
            bm &= b["product_type"] == ptype
        bm &= self._time_mask(b, time)
        den = float(b.loc[bm, col].sum())
        caveats = self._time_caveat(time)
        if ptype and ptype not in self.covered:
            caveats.append(
                f"{ptype} 不在产品预算覆盖的 {len(self.covered)} 类内（B7）；"
                "其预算挂在 SalesDept 且 Fdept 为空，不走产品类型维度，故对照为 0"
            )
        return {
            "intent": "achieve_product",
            "caveats": caveats,
            "metric": metric,
            "caliber": {"org_scope": "in_scope", "model_covered_only": True,
                        "dept_notnull": True, "unit": "万元含税"},
            "scope": {"product_type": ptype, "time": time, "covered_types": self.covered},
            "numerator_wan": round(num, 2),
            "denominator_wan": round(den, 2),
            "achieve_pct": round(num / den * 100, 1) if den else None,
            "evidence": {"rows": int(m.sum()), "budget_rows": int(bm.sum())},
        }

    def behavior_emp(self, ents: dict) -> dict:
        q = ents.get("_q") or ""
        kind = "ship" if ("出机" in q or "出货" in q) else "sign"
        fact = self.sign if kind == "sign" else self.ship

        m = re.search(r"连续\s*(\d+)\s*个?月", q)
        need = int(m.group(1)) if m else None
        time = ents.get("time")
        cutoff = int((time or {}).get("end") or self.MAX_MONTH)

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
            "caveats": ["计数为口径探针，不是名单报告（B1）；离职人员空窗属状态非业绩，已单列 employment_status"] + self._time_caveat(time),
        }

    def customer_model(self, ents: dict) -> dict:
        code = ents.get("customer")
        dfs = []
        for f, rel in ((self.sign, "contract_party"), (self.ship, "ship_to")):
            sub = f[f["cust_code"] == code] if code else f
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
        time = ents.get("time")
        m = fact["org_scope"] == "in_scope"
        if ents.get("product_type"):
            m &= fact["zprod_type"] == ents["product_type"]
        m &= self._time_mask(fact, time)
        g = fact[m].groupby("zprod_type")["total_money_fc_hs_wan"].sum().sort_values(ascending=False)
        total = float(g.sum())
        return {
            "intent": "structure_share",
            "caliber": {"org_scope": "in_scope", "unit": "万元含税", "basis": "自身总额（不是预算）"},
            "scope": {"time": time},
            "total_wan": round(total, 2),
            "shares": [{"zprod_type": k, "amount_wan": round(float(v), 2),
                        "pct": round(float(v) / total * 100, 1) if total else None,
                        "budget_covered": k in self.covered} for k, v in g.items()],
            "caveats": self._time_caveat(time),
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
        extra = ["参考基准：考核出机 130.6% / 管理出机 91.1% / 管理签单 103.2%（H1 默认口径）"]
        if intent != "achieve_dept":
            # 科室达成报告已含完整口径+分析，不再标「口径探针」
            extra.insert(0, "达成率为口径探针，不是分析报告（B1/G6）")
        body["caveats"] = body.get("caveats", []) + extra
        return body


@lru_cache(maxsize=1)
def _rag() -> MarketingGraphRAG:
    return MarketingGraphRAG()


def _num(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _linked_entities_table(result: dict) -> list[str]:
    ents = result.get("linked_entities") or {}
    if not ents:
        return []
    rows = ["| 实体 | 值 |", "| --- | --- |"]
    for key, value in ents.items():
        if key == "month":
            continue  # 冗余于 time 口径
        if key == "time" and isinstance(value, dict):
            kind = value.get("kind")
            if kind in ("ytd", "range"):
                text = f"1-{value['end']}月累计（含当月）"
            elif kind == "asof":
                text = "截止目前（最新完整月）"
            elif kind == "month":
                text = f"{value['end']}月（单月）"
            else:
                text = str(value)
            rows.append(f"| 时间口径 | `{text}` |")
            continue
        label = ENTITY_LABEL.get(key, key)
        if key == "metric":
            value = METRIC_LABEL.get(value, value)
        rows.append(f"| {label} | `{value}` |")
    return rows


def _time_label(time: dict | None) -> str:
    """把解析出的时间口径渲染成中文标题片段（如「2026年6月」「2026年1-6月累计」）。"""
    if not time:
        return ""
    year = time.get("year") or 2026
    kind = time.get("kind")
    if kind == "ytd":
        return f"{year}年1-{time['end']}月累计"
    if kind == "range":
        return f"{year}年{time['start']}-{time['end']}月"
    if kind == "asof":
        return f"{year}年截止{time['end']}月"
    return f"{year}年{time['end']}月"


def _report_title(result: dict) -> str:
    """生成报告标题前缀，如「2026年6月华南大区各科室管理出机」。"""
    scope = result.get("scope") or {}
    metric = METRIC_LABEL.get(result.get("metric"), "")
    tlabel = _time_label(scope.get("time"))
    dept = scope.get("dept")
    area = scope.get("area")
    if dept:
        org = dept
    elif area:
        org = f"{area}各科室"
    else:
        org = "各科室"
    return f"{tlabel}{org}{metric}"


@lru_cache(maxsize=1)
def _deepseek_client():
    """懒加载 DeepSeek 客户端；不可用（无 key / 缺依赖 / 网络错）返回 None。"""
    try:
        from semantica.llms import DeepSeek

        llm = DeepSeek(model="deepseek-chat")
        if llm.is_available():
            return llm
    except Exception:
        pass
    return None


def _deepseek_report(result: dict, title: str, detail_md: str) -> dict | None:
    """单次调用 DeepSeek 生成「总览 + 细分分析建议 + 根因分析」；返回 {overview, analysis} 或 None。"""
    llm = _deepseek_client()
    if llm is None:
        return None
    metric = METRIC_LABEL.get(result.get("metric"), "")
    totals = result.get("totals") or {}
    ov_hdr = f"## {title}整体数据分析总览"
    an_hdr = f"## {title}维度细分分析与建议"
    rc_hdr = f"## {title}根因分析"
    prompt = (
        f"你是营销数据分析专家。请基于下面这份《{title}》明细数据撰写分析报告，"
        f"输出为 Markdown，严格包含以下三个部分（每部分用 `## ` 二级标题，标题后直接写正文）：\n\n"
        f"{ov_hdr}\n"
        f"（用一段话概述整体达成情况：总目标、总达成、整体达成率；哪些科室表现突出、哪些未达标；"
        f"语气客观，突出关键数字，金额保留两位小数）\n\n"
        f"{an_hdr}\n"
        f"（分三点：1. 异常高绩效分析（达成率显著高于100%）；2. 低绩效预警（达成率低于80%）；"
        f"3. 稳健提升空间（80%~100%）。每点列出具体科室与数据依据，并给出可执行建议）\n\n"
        f"{rc_hdr}\n"
        f"（对未达标与异常科室做根因分析：从人员、客户储备、市场竞争、产品结构、渠道政策等业务视角"
        f"推断可能原因，并给出改进方向；明确说明这是基于数据的推断）\n\n"
        f"整体汇总（这是系统计算好的权威口径，请直接引用、不要自行重新求和）："
        f"总目标 {_num(totals.get('target_wan'))} 万元，总达成 {_num(totals.get('achieve_wan'))} 万元，"
        f"整体达成率 {f'{totals['achieve_pct']:.2f}%' if totals.get('achieve_pct') is not None else '—'}。\n"
        f"数据明细（单位：万元；达成率 = 达成/目标；指标口径：{metric}）：\n{detail_md}\n\n"
        f"注意：不要编造数据，所有数字必须来自上表明细与整体汇总；不要重复输出明细表；"
        f"不要自行重新加总金额或重算达成率。"
    )
    try:
        text = llm.generate(prompt, temperature=0.3, max_tokens=2000)
    except Exception:
        return None
    if not text:
        return None

    def _cut(start_hdr: str, end_hdr: str | None) -> str:
        si = text.find(start_hdr)
        if si < 0:
            return ""
        if end_hdr:
            ei = text.find(end_hdr, si + len(start_hdr))
            return text[si:ei].strip() if ei >= 0 else text[si:].strip()
        return text[si:].strip()

    overview = _cut(ov_hdr, an_hdr)
    analysis = _cut(an_hdr, None)
    if not overview and not analysis:
        return None
    return {"overview": overview, "analysis": analysis}


def _detail_markdown(details: list[dict], totals: dict) -> list[str]:
    """生成数据明细表 Markdown 行（含表头与总计行）。"""
    lines = [
        "| 销售部 | 大区 | 科室 | 目标(万元) | 达成(万元) | 达成率 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in details:
        pct = f"{row['achieve_pct']:.2f}%" if row["achieve_pct"] is not None else "—"
        lines.append(
            f"| {row['sales_dept']} | {row['area']} | {row['fdept']} | "
            f"{_num(row['target_wan'])} | {_num(row['achieve_wan'])} | {pct} |"
        )
    total_pct = f"{totals['achieve_pct']:.2f}%" if totals.get("achieve_pct") is not None else "—"
    lines.append(
        f"| 总计 |  |  | {_num(totals.get('target_wan'))} | {_num(totals.get('achieve_wan'))} | {total_pct} |"
    )
    return lines


def _render_achieve_dept_report(result: dict) -> str:
    """按用户指定模版渲染：口径说明 → 总览 → 明细表 → 细分分析建议 → 根因分析。"""
    metric = METRIC_LABEL.get(result.get("metric"), str(result.get("metric", "")))
    title = _report_title(result)
    scope = result.get("scope") or {}
    time = scope.get("time")
    details = result.get("details") or []
    totals = result.get("totals") or {}

    detail_md = "\n".join(
        [f"- {row['fdept']}（{row['sales_dept']}/{row['area']}）：目标 {_num(row['target_wan'])} 万元，"
         f"达成 {_num(row['achieve_wan'])} 万元，达成率 "
         f"{f'{row['achieve_pct']:.2f}%' if row['achieve_pct'] is not None else '—'}"
         for row in details]
    )
    ai = _deepseek_report(result, title, detail_md)

    lines: list[str] = []

    # ① 取数口径说明
    lines.append(f"## {title}取数口径说明")
    lines.append("")
    lines.append(f"- **指标口径**：{metric}目标金额、{metric}达成金额、达成率。")
    lines.append("- **维度口径**：按销售部、大区、科室统计。")
    lines.append(f"- **时间范围**：{_time_label(time) or '未指定'}。")
    lines.append("- **金额口径**：以结果字段为准，默认按含税解读。")
    lines.append("- **口径一致性**：达成率 = 达成_万元 / 目标_万元，同口径计算。")
    lines.append("")

    # ② 整体数据分析总览（DeepSeek / 规则兜底）
    if ai and ai.get("overview"):
        lines.append(ai["overview"])
    else:
        lines.extend(_rule_overview(result, title, details, totals))
    lines.append("")

    # ③ 数据明细表
    lines.append(f"## {title}数据明细表")
    lines.append("")
    lines.extend(_detail_markdown(details, totals))
    lines.append("")

    # ④ 维度细分分析与建议 + 根因分析（DeepSeek / 规则兜底）
    if ai and ai.get("analysis"):
        lines.append(ai["analysis"])
    else:
        lines.extend(_rule_analysis(result, title, details, totals))
    lines.append("")

    # ⑤ 口径提示（保留时间跨度累加语义说明）
    caveats = result.get("caveats") or []
    if caveats:
        lines.append("**口径提示**：")
        for c in caveats:
            lines.append(f"- {c}")
    return "\n".join(lines)


def _rule_overview(result: dict, title: str, details: list[dict], totals: dict) -> list[str]:
    """DeepSeek 不可用时的规则兜底——整体数据分析总览。"""
    n = len(details)
    tpct = totals.get("achieve_pct")
    lines = [f"## {title}整体数据分析总览", ""]
    if n == 0:
        lines.append("无科室明细数据。")
        return lines
    over = sum(1 for r in details if r["achieve_pct"] is not None and r["achieve_pct"] >= 100)
    below = sum(1 for r in details if r["achieve_pct"] is not None and r["achieve_pct"] < 80)
    top = max(details, key=lambda r: r["achieve_pct"] if r["achieve_pct"] is not None else -1)
    lines.append(
        f"{title}共 {n} 个科室，整体目标 {_num(totals.get('target_wan'))} 万元，"
        f"达成 {_num(totals.get('achieve_wan'))} 万元，整体达成率 "
        f"{f'{tpct:.2f}%' if tpct is not None else '—'}。{over} 个科室达成率超 100%，"
        f"{below} 个科室低于 80% 警戒线；表现最突出的是 {top['fdept']}"
        f"（{f'{top['achieve_pct']:.2f}%' if top['achieve_pct'] is not None else '—'}）。"
    )
    return lines


def _rule_analysis(result: dict, title: str, details: list[dict], totals: dict) -> list[str]:
    """DeepSeek 不可用时的规则兜底——维度细分分析与建议 + 根因分析。"""
    lines = [f"## {title}维度细分分析与建议", ""]
    high = [r for r in details if r["achieve_pct"] is not None and r["achieve_pct"] >= 100][:3]
    low = [r for r in details if r["achieve_pct"] is not None and r["achieve_pct"] < 80][:3]
    mid = [r for r in details if r["achieve_pct"] is not None and 80 <= r["achieve_pct"] < 100][:3]
    lines.append("1. **异常高绩效分析**：")
    if high:
        for r in high:
            lines.append(f"   - {r['fdept']} 达成率 {r['achieve_pct']:.2f}%，建议复盘成功案例并经验共享。")
    else:
        lines.append("   - 无达成率超 100% 的科室。")
    lines.append("2. **低绩效预警**（达成率 < 80%）：")
    if low:
        for r in low:
            lines.append(f"   - {r['fdept']} 达成率仅 {r['achieve_pct']:.2f}%，低于警戒线，需介入诊断。")
    else:
        lines.append("   - 无达成率低于 80% 的科室。")
    lines.append("3. **稳健提升空间**（80%~100%）：")
    if mid:
        for r in mid:
            lines.append(f"   - {r['fdept']} 达成率 {r['achieve_pct']:.2f}%，接近达标，建议月末冲刺。")
    else:
        lines.append("   - 无 80%~100% 区间的科室。")
    lines.append("")
    lines.append(f"## {title}根因分析")
    lines.append("")
    lines.append("（DeepSeek 未配置或不可用，以下为规则推断。）")
    if low:
        lines.append(
            f"未达标科室 {('、'.join(r['fdept'] for r in low))} 可能受人员流失、客户储备不足、"
            "市场竞争加剧或产品结构偏弱影响；建议从签单转化漏斗与在手订单入手逐科室排查。"
        )
    else:
        lines.append("当前无显著未达标科室；建议关注高绩效科室的可复制打法。")
    return lines


def _build_sources(session: Any, result: dict) -> list[dict[str, Any]]:
    """Map the rule-based answer back onto graph nodes for the evidence tables."""

    def src(node_id: str, facts: str = "", score: float = 0.9) -> dict[str, Any]:
        node = session.get_node(node_id) or {}
        content = str(node.get("content") or node_id)
        node_type = str(node.get("type") or "entity")
        return {
            "id": node_id,
            "type": node_type,
            "content": content,
            "score": score,
            "kind": "retrieve",
            "hop": 0,
            "facts": facts,
        }

    intent = result.get("intent")
    sources: list[dict[str, Any]] = []
    scope = result.get("scope") or {}
    if intent == "refuse":
        return sources
    if intent in ("achieve_dept", "achieve_product"):
        metric_label = METRIC_LABEL.get(result.get("metric"), "")
        if scope.get("area"):
            sources.append(src(f"area:{scope['area']}", f"口径 达成率 {result.get('achieve_pct')}%"))
        if scope.get("dept"):
            sources.append(src(f"dept:{scope['dept']}", f"{metric_label}达成 {result.get('achieve_pct')}%"))
        if scope.get("product_type"):
            sources.append(src(f"ptype:{scope['product_type']}", f"{metric_label}达成 {result.get('achieve_pct')}%"))
        time = scope.get("time")
        if time:
            if time.get("kind") in ("ytd", "range"):
                sources.append(src(f"month:2026-{int(time['end']):02d}", f"1-{time['end']}月累计（含当月）"))
            elif time.get("kind") == "asof":
                sources.append(src(f"month:2026-{int(time['end']):02d}", "截止目前（最新完整月）"))
            else:
                sources.append(src(f"month:2026-{int(time['end']):02d}", f"单月 {time['end']}月"))
        for item in (result.get("top_contributors") or []):
            sources.append(src(f"dept:{item.get('fdept')}", f"贡献 {_num(item.get('amount_wan'))} 万元", 0.7))
    elif intent == "behavior_emp":
        for item in (result.get("sample") or []):
            sources.append(src(
                f"emp:{item.get('sales_code')}",
                f"连续 {item.get('consecutive_empty_months')} 月无事件 · {item.get('employment_status')}",
                0.7,
            ))
    elif intent == "customer_model":
        cust = result.get("customer") or {}
        if cust.get("cust_code"):
            sources.append(src(f"cust:{cust['cust_code']}", cust.get("cust_name") or ""))
        for item in (result.get("top_models") or []):
            sources.append(src(f"model:{item.get('zprod_name')}", f"{item.get('role')} {_num(item.get('amount_wan'))} 万元", 0.7))
    elif intent == "structure_share":
        for item in (result.get("shares") or []):
            covered = "预算覆盖" if item.get("budget_covered") else "未覆盖"
            sources.append(src(
                f"ptype:{item.get('zprod_type')}",
                f"份额 {item.get('pct')}% · {_num(item.get('amount_wan'))} 万元 · {covered}",
                0.7,
            ))
    return sources


def _render_answer(result: dict) -> str:
    intent = result.get("intent")

    if intent == "refuse":
        return f"**{result.get('refusal_reason', '无法回答')}**"
    if intent == "achieve_dept":
        return _render_achieve_dept_report(result)

    lines: list[str] = []
    if intent == "achieve_product":
        metric = METRIC_LABEL.get(result.get("metric"), str(result.get("metric", "")))
        pct = result.get("achieve_pct")
        num = _num(result.get("numerator_wan"))
        den = _num(result.get("denominator_wan"))
        if pct is not None:
            lines.append(f"{metric}达成率 = {num} 万元 ÷ {den} 万元 = **{pct}%**")
        else:
            lines.append(f"{metric}达成率：分母为 0，无法计算")
        scope = result.get("scope") or {}
        scope_parts = []
        if scope.get("product_type"):
            scope_parts.append(f"产品类型 `{scope['product_type']}`")
        time = scope.get("time")
        if time:
            if time.get("kind") in ("ytd", "range"):
                scope_parts.append(f"时间 `1-{time['end']}月累计（含当月）`")
            elif time.get("kind") == "asof":
                scope_parts.append("时间 `截止目前（最新完整月）`")
            elif time.get("kind") == "month":
                scope_parts.append(f"时间 `{time['end']}月（单月）`")
        if scope_parts:
            lines.append("范围：" + "、".join(scope_parts))
        ev = result.get("evidence") or {}
        lines.append(f"证据：{ev.get('rows', 0)} 行事实、{ev.get('budget_rows', 0)} 行预算")
    elif intent == "behavior_emp":
        event = "出机" if result.get("event") == "ship" else "签单"
        need = (result.get("caliber") or {}).get("consecutive_months")
        lines.append(f"连续 ≥{need} 个月无{event}的**业务**人数 = **{result.get('consecutive_hit_count')}**")
        lines.append(f"业务员总数 {result.get('business_headcount')}，窗口内无{event} {result.get('no_event_in_window')}")
        sample = result.get("sample") or []
        if sample:
            lines.append("")
            lines.append("**样本（按连续空窗月数降序）**：")
            for item in sample:
                lines.append(
                    f"- {item.get('sales_name') or item.get('sales_code')}（{item.get('sales_code')}）"
                    f"：{item.get('consecutive_empty_months')} 月 · {item.get('employment_status')}"
                )
    elif intent == "customer_model":
        cust = result.get("customer") or {}
        name = cust.get("cust_name") or cust.get("cust_code") or "全部客户"
        lines.append(f"客户 **{name}**（`{cust.get('cust_code') or '—'}`）签单/出货机型：")
        models = result.get("top_models") or []
        for item in models:
            role = "签单" if item.get("role") == "contract_party" else "出货"
            lines.append(f"- {item.get('zprod_name')}：{_num(item.get('amount_wan'))} 万元（{role}）")
    elif intent == "structure_share":
        lines.append(f"产品类型出货结构（合计 {_num(result.get('total_wan'))} 万元，口径 basis=自身总额）：")
        for item in (result.get("shares") or []):
            covered = "预算覆盖" if item.get("budget_covered") else "未覆盖"
            lines.append(
                f"- {item.get('zprod_type')}：{item.get('pct')}%（{_num(item.get('amount_wan'))} 万元）· {covered}"
            )

    caveats = result.get("caveats") or []
    if caveats:
        lines.append("")
        lines.append("**口径提示**：")
        for c in caveats:
            lines.append(f"- {c}")
    return "\n".join(lines)


def _format_response(query: str, result: dict, sources: list[dict[str, Any]]) -> str:
    body = _render_answer(result)
    if result.get("intent") == "achieve_dept":
        # 科室达成报告自带标题结构（口径说明/总览/明细表/分析/根因），无需再前置问句标题。
        lines = [body]
    else:
        lines = [f"## {query}", "", body]
    linked = _linked_entities_table(result)
    if linked:
        lines.extend(["", "### 关联实体", "", *linked])
    if sources:
        lines.extend([
            "",
            "### 主要命中",
            "",
            "| 节点 | 类型 | 来源 | 要点 |",
            "| --- | --- | --- | --- |",
        ])
        for row in sources[:6]:
            lines.append(f"| {row['content'] or row['id']} | {row['type']} | 召回 | {row['facts']} |")
    return "\n".join(lines)


def run_marketing_graphrag(session: Any, query: str, max_results: int = 12) -> dict[str, Any]:
    """Run marketing GraphRAG and return a GraphRAGResponse-compatible dict."""
    text = (query or "").strip()
    if not text:
        raise ValueError("query must not be empty")
    if len(text) > 500:
        raise ValueError("query must be 500 characters or less")

    try:
        rag = _rag()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"marketing processed parquet not found: {exc}") from exc

    result = rag.answer(text)
    intent = result.get("intent")
    sources = _build_sources(session, result)
    response = _format_response(text, result, sources)

    if intent == "refuse":
        outcome = "refused"
        confidence = 1.0
    else:
        outcome = "answered"
        confidence = 0.95

    entity_ids = [row["id"] for row in sources][:8]

    decision_id = session.graph.record_decision(
        category=f"marketing_graphrag::{intent}",
        scenario=text,
        reasoning=response,
        outcome=outcome,
        confidence=confidence,
        entities=entity_ids,
        decision_maker="explorer-marketing-graphrag",
    )
    session.handle_graph_mutation(
        "ADD_NODE",
        decision_id,
        session.get_node(decision_id) or {"id": decision_id, "type": "decision"},
    )

    chain = [
        {
            "id": neighbor.get("id"),
            "type": neighbor.get("type"),
            "relationship": neighbor.get("relationship"),
            "hop": neighbor.get("hop"),
            "content": neighbor.get("content", ""),
        }
        for neighbor in session.get_neighbors(decision_id, 5)
        if neighbor.get("id") not in {"dataset:cleaned"}
    ]

    return {
        "decision_id": decision_id,
        "query": text,
        "response": response,
        "reasoning_path": "",
        "confidence": confidence,
        "outcome": outcome,
        "num_sources": len(sources),
        "num_reasoning_paths": 0,
        "sources": sources,
        "path": [],
        "chain": chain,
        "sparql": "",
        "mapping": [],
    }
