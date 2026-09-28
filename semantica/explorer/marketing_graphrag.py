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
    (["全年", "下半年", "Q3", "Q4", "7月", "8月", "9月", "10月", "11月", "12月"], "数据窗口仅 2026-01~06（H1），窗口外无法回答"),
]


class MarketingGraphRAG:
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
                "其预算挂在 SalesDept 且 Fdept 为空，不走产品类型维度，故对照为 0"
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
        kind = "ship" if ("出机" in q or "出货" in q) else "sign"
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
            "参考基准：考核出机 130.6% / 管理出机 91.1% / 管理签单 103.2%（H1 默认口径）",
        ]
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
        label = ENTITY_LABEL.get(key, key)
        if key == "metric":
            value = METRIC_LABEL.get(value, value)
        rows.append(f"| {label} | `{value}` |")
    return rows


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
        if scope.get("month"):
            month = scope["month"]
            sources.append(src(f"month:2026-{int(month):02d}", "月"))
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
    lines: list[str] = []
    intent = result.get("intent")

    if intent == "refuse":
        lines.append(f"**{result.get('refusal_reason', '无法回答')}**")
    elif intent in ("achieve_dept", "achieve_product"):
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
        if scope.get("dept"):
            scope_parts.append(f"科室 `{scope['dept']}`")
        if scope.get("area"):
            scope_parts.append(f"大区 `{scope['area']}`")
        if scope.get("product_type"):
            scope_parts.append(f"产品类型 `{scope['product_type']}`")
        if scope.get("month"):
            scope_parts.append(f"月 `{scope['month']}`")
        if scope_parts:
            lines.append("范围：" + "、".join(scope_parts))
        ev = result.get("evidence") or {}
        lines.append(f"证据：{ev.get('rows', 0)} 行事实、{ev.get('budget_rows', 0)} 行预算")
        top = result.get("top_contributors") or []
        if top:
            lines.append("")
            lines.append("**贡献 Top 科室**：")
            for item in top[:10]:
                lines.append(f"- {item.get('fdept')}：{_num(item.get('amount_wan'))} 万元")
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
    lines = [f"## {query}", "", _render_answer(result)]
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
