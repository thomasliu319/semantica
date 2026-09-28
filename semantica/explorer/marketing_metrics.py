"""Compose additive marketing measures into derived ratios without inventing margin labels.

Reads cleaned parquet under datasets/processed/marketing_2026H1/.

This mirrors the IoT `semantica/explorer/iot_metrics.py` contract (``catalog`` /
``compose`` / ``stamp_metrics``) but for the marketing/operations star+plan model:

- Achieve rates always enforce the four-element caliber (B6/B7/B8/B3):
  ``org_scope == in_scope`` AND ``zprod_type`` in budget-covered AND ``fdept``
  non-empty AND amount in 万元含税.
- The two budget projections (dept / product) are the same money seen from two
  angles; they are never added together (B10).
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
PROCESSED = REPO / "datasets" / "processed" / "marketing_2026H1"
WINDOW = {"StartTime": "2026-01-01", "EndTime": "2026-06-30"}
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_FORBIDDEN_ID = re.compile(r"(毛利|成本|净利|利润|margin|oee|稼动)", re.IGNORECASE)

OPS = ("div", "mul", "add", "sub", "share", "achieve")

SHIP_BASES: dict[str, tuple[str, str, str]] = {
    "ship_amount_fc_hs_wan": ("total_money_fc_hs_wan", "sum", "出货含税万元"),
    "ship_amount_fc_hs": ("total_money_fc_hs", "sum", "出货含税元"),
    "ship_amount_fc": ("total_money_fc", "sum", "出货不含税元"),
    "ship_qty": ("fqty", "sum", "出货数量"),
    "ship_docs": ("docno", "nunique", "出货单数"),
    "ship_emps": ("sales_code", "nunique", "出机业务员数"),
    "ship_customers": ("cust_code", "nunique", "出货客户数"),
}

SIGN_BASES: dict[str, tuple[str, str, str]] = {
    "sign_amount_fc_hs_wan": ("total_money_fc_hs_wan", "sum", "签单含税万元"),
    "sign_amount_fc_hs": ("total_money_fc_hs", "sum", "签单含税元"),
    "sign_amount_fc": ("total_money_fc", "sum", "签单不含税元"),
    "sign_qty": ("fqty", "sum", "签单数量"),
    "sign_docs": ("docno", "nunique", "签单单数"),
    "sign_emps": ("sales_code", "nunique", "签单业务员数"),
}

DEPT_BUDGET_BASES: dict[str, tuple[str, str, str]] = {
    "assessment_ship_budget_hs": ("assessment_ship_budget_hs", "sum", "考核出机预算万元"),
    "management_ship_budget_hs": ("management_ship_budget_hs", "sum", "管理出机预算万元"),
    "management_signed_contract_hs": ("management_signed_contract_hs", "sum", "管理签单预算万元"),
}

PRODUCT_BUDGET_BASES: dict[str, tuple[str, str, str]] = {
    "assessment_ship_budget_hs": ("assessment_ship_budget_hs", "sum", "考核出机预算万元"),
    "management_ship_budget_hs": ("management_ship_budget_hs", "sum", "管理出机预算万元"),
    "gl_management_signed_contract_hs": ("gl_management_signed_contract_hs", "sum", "管理签单预算万元"),
}

# B10 projection note: the dept projection names the signed-contract budget
# ``management_signed_contract_hs``; the product projection names the same
# money ``gl_management_signed_contract_hs``. Never add them.
_BUDGET_FALLBACK: dict[str, dict[str, str]] = {
    "management_signed_contract_hs": {"product_budget": "gl_management_signed_contract_hs"},
}

_NAME_COLS = {"sales_code": "sales_name", "cust_code": "cust_name"}


def _bd(source: str, fact_keys: list[str], budget_keys: list[str], join: list[tuple[str, str]]) -> dict:
    return {"source": source, "fact_keys": fact_keys, "budget_keys": budget_keys, "join": join}


_DEPT_BUDGET = lambda fk, bk, join: _bd("dept_budget", fk, bk, join)
_PRODUCT_BUDGET = lambda fk, bk, join: _bd("product_budget", fk, bk, join)


GRAINS: dict[str, dict[str, Any]] = {
    "month": {
        "id": "month", "label_zh": "自然月", "source": "ship", "keys": ["month"],
        "features": "窗口内月度出货趋势与达成；1 月冷启动",
        "budget": _DEPT_BUDGET(["month"], ["month"], [("month", "month")]),
    },
    "dept_month": {
        "id": "dept_month", "label_zh": "科室 × 月", "source": "ship", "keys": ["fdept", "month"],
        "features": "科室在自然月的出机/签单与达成；空科室不入达成（B8）",
        "budget": _DEPT_BUDGET(["fdept", "month"], ["fdept", "month"], [("fdept", "fdept"), ("month", "month")]),
    },
    "dept": {
        "id": "dept", "label_zh": "科室", "source": "ship", "keys": ["fdept"],
        "features": "科室汇总达成；键 Fdept_add，不是出货表的 fdept_sap（ontology §5.6）",
        "budget": _DEPT_BUDGET(["fdept"], ["fdept"], [("fdept", "fdept")]),
    },
    "area": {
        "id": "area", "label_zh": "大区", "source": "ship", "keys": ["area"],
        "features": "区域汇总达成/份额；空区域单独成组",
        "budget": _DEPT_BUDGET(["area"], ["area"], [("area", "area")]),
    },
    "area_month": {
        "id": "area_month", "label_zh": "大区 × 月", "source": "ship", "keys": ["area", "month"],
        "features": "区域月度趋势与达成",
        "budget": _DEPT_BUDGET(["area", "month"], ["area", "month"], [("area", "area"), ("month", "month")]),
    },
    "product_type": {
        "id": "product_type", "label_zh": "产品类型", "source": "ship", "keys": ["zprod_type"],
        "features": "产品类型结构份额/达成；3C钻攻机等未覆盖类型预算挂销售部（B7）",
        "budget": _PRODUCT_BUDGET(["zprod_type"], ["product_type"], [("zprod_type", "product_type")]),
    },
    "product_type_month": {
        "id": "product_type_month", "label_zh": "产品类型 × 月", "source": "ship", "keys": ["zprod_type", "month"],
        "features": "产品类型月度达成（对照 fill_product_budget 覆盖的 6 类）",
        "budget": _PRODUCT_BUDGET(["zprod_type", "month"], ["product_type", "month"], [("zprod_type", "product_type"), ("month", "month")]),
    },
    "model": {
        "id": "model", "label_zh": "机型", "source": "ship", "keys": ["zprod_name", "zprod_type"],
        "features": "机型出货结构；键 ZPROD_NAME，不是物料编码 FmateNumber",
    },
    "emp": {
        "id": "emp", "label_zh": "业务员", "source": "ship", "keys": ["sales_code"],
        "features": "业务员人均出机；同工号多名取在职行（B9）",
    },
    "customer": {
        "id": "customer", "label_zh": "客户", "source": "ship", "keys": ["cust_code"],
        "features": "客户 × 机型出货明细；签单侧是 KunnrCode，出货侧是 fcust_number",
    },
    "sign_month": {
        "id": "sign_month", "label_zh": "签单 × 月", "source": "sign", "keys": ["month"],
        "features": "月度签单与管理签单达成（签单 TotalMoneyFc_HS，不是不含税）",
        "budget": _DEPT_BUDGET(["month"], ["month"], [("month", "month")]),
    },
    "sign_dept_month": {
        "id": "sign_dept_month", "label_zh": "签单 × 科室 × 月", "source": "sign", "keys": ["fdept", "month"],
        "features": "科室月度签单与管理签单达成",
        "budget": _DEPT_BUDGET(["fdept", "month"], ["fdept", "month"], [("fdept", "fdept"), ("month", "month")]),
    },
    "sign_product_type": {
        "id": "sign_product_type", "label_zh": "签单 × 产品类型", "source": "sign", "keys": ["zprod_type"],
        "features": "产品类型签单结构（预算对照同产品投影）",
        "budget": _PRODUCT_BUDGET(["zprod_type"], ["product_type"], [("zprod_type", "product_type")]),
    },
    "budget_dept_month": {
        "id": "budget_dept_month", "label_zh": "科室预算 × 月", "source": "dept_budget", "keys": ["fdept", "month"],
        "features": "科室月度预算（万元含税，Plan 星，不与事实相加 A5）",
    },
    "budget_product_month": {
        "id": "budget_product_month", "label_zh": "产品预算 × 月", "source": "product_budget", "keys": ["product_type", "month"],
        "features": "产品类型月度预算（与科室预算是同一笔钱的两个投影，禁止相加 B10）",
    },
}


PRESETS: list[dict[str, Any]] = [
    {
        "id": "ship_per_emp",
        "op": "div",
        "a": "ship_amount_fc_hs_wan",
        "b": "ship_emps",
        "name_zh": "人均出机万元",
        "domain": "ship",
    },
    {
        "id": "sign_per_emp",
        "op": "div",
        "a": "sign_amount_fc_hs_wan",
        "b": "sign_emps",
        "name_zh": "人均签单万元",
        "domain": "sign",
    },
    {
        "id": "product_type_share",
        "op": "share",
        "a": "ship_amount_fc_hs_wan",
        "b": None,
        "name_zh": "产品类型出货份额",
        "domain": "structure",
    },
    {
        "id": "area_share",
        "op": "share",
        "a": "ship_amount_fc_hs_wan",
        "b": None,
        "name_zh": "区域出货份额",
        "domain": "structure",
    },
    {
        "id": "ship_qty_share",
        "op": "share",
        "a": "ship_qty",
        "b": None,
        "name_zh": "出货数量份额",
        "domain": "structure",
    },
    # Achieve presets — numerator is caliber-filtered, denominator is budget.
    {
        "id": "assessment_ship_achieve_pct",
        "op": "achieve",
        "a": "ship_amount_fc_hs_wan",
        "b": "assessment_ship_budget_hs",
        "name_zh": "考核出机达成率",
        "domain": "achieve",
        "not": "全表出货直接除预算（漏四要素会得 228.6%）",
    },
    {
        "id": "management_ship_achieve_pct",
        "op": "achieve",
        "a": "ship_amount_fc_hs_wan",
        "b": "management_ship_budget_hs",
        "name_zh": "管理出机达成率",
        "domain": "achieve",
        "not": "全表出货直接除预算（漏四要素会得 228.6%）",
    },
    {
        "id": "management_sign_achieve_pct",
        "op": "achieve",
        "a": "sign_amount_fc_hs_wan",
        "b": "management_signed_contract_hs",
        "name_zh": "管理签单达成率",
        "domain": "achieve",
        "not": "签单不含税 TotalMoneyFc 当分子",
    },
]

INT_KEYS = {
    "ship_qty",
    "sign_qty",
    "ship_docs",
    "sign_docs",
    "ship_emps",
    "sign_emps",
    "ship_customers",
}

NOTES = [
    "B1 clean_only：派生度量/达成探针，不是分析报告；不造毛利/成本/利润率",
    "达成四要素（缺一即错）：org_scope=in_scope ∧ zprod_type∈预算覆盖 ∧ fdept非空 ∧ 万元含税",
    "两张预算表是同一笔钱的两个投影（B10），禁止相加；一次查询只走一条预算投影",
    "宽表金额为元、预算为万元，对照前须 /10000（B3）；本目录一律万元含税",
    "出货表 fdept_sap 是 SAP 出货组织，不是预算科室（ontology §5.6），不进对照",
    "参考基准（H1 默认口径）：考核出机 130.6% / 管理出机 91.1% / 管理签单 103.2%",
]


def catalog() -> dict[str, Any]:
    bases_by_source = {
        "ship": [_base_entry(k, v) for k, v in SHIP_BASES.items()],
        "sign": [_base_entry(k, v) for k, v in SIGN_BASES.items()],
        "dept_budget": [_base_entry(k, v) for k, v in DEPT_BUDGET_BASES.items()],
        "product_budget": [_base_entry(k, v) for k, v in PRODUCT_BUDGET_BASES.items()],
    }
    grains = []
    for gid, spec in GRAINS.items():
        grains.append(
            {
                "id": gid,
                "label_zh": spec["label_zh"],
                "source": spec["source"],
                "keys": list(spec["keys"]),
                "features": spec["features"],
                "bases": [row["id"] for row in bases_by_source[spec["source"]]],
                "budget": spec.get("budget"),
            }
        )
    return {
        "window": WINDOW,
        "grains": grains,
        "bases_by_source": bases_by_source,
        "presets": PRESETS,
        "ops": list(OPS),
        "notes": NOTES,
    }


def stamp_metrics(bases: Mapping[str, Any], *, extra: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Round additive totals and attach ratio presets. Skip share (needs a cohort)
    and achieve (needs a budget join)."""
    payload = {key: _finite(value) for key, value in bases.items()}
    frame = pd.DataFrame([payload])
    recipes = [item for item in PRESETS if item["op"] not in ("share", "achieve")] + list(extra or [])
    apply_derived(frame, recipes)
    row = frame.iloc[0].to_dict()
    return {key: _json_num(key, value) for key, value in row.items() if _finite(value) is not None}


def compose(
    *,
    grain: str,
    bases: Sequence[str] | None = None,
    derived: Sequence[Mapping[str, Any]] | None = None,
    apply_presets: bool = True,
    limit: int = 200,
    frames: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    spec = GRAINS.get(grain)
    if spec is None:
        raise ValueError(f"unknown grain: {grain}")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be 1..500")

    source = spec["source"]
    available = _bases_for(source)
    requested = list(bases) if bases is not None else list(available)
    selected = [item for item in requested if item in available]
    if not selected:
        selected = list(available)

    regular_raw: list[Mapping[str, Any]] = []
    achieve_raw: list[Mapping[str, Any]] = []
    for item in derived or []:
        op = str(item.get("op") or "").strip()
        if op == "achieve":
            achieve_raw.append(item)
        else:
            regular_raw.append(item)

    recipes = _validated_derived(regular_raw, selected)
    if apply_presets:
        recipes = _merge_recipes(
            recipes,
            [p for p in PRESETS
             if p["op"] != "achieve" and p["a"] in selected and (p["op"] == "share" or p.get("b") in selected)],
        )

    achieve_recipes = _validated_achieve(achieve_raw, selected, spec)
    if apply_presets:
        achieve_recipes = _merge_recipes(
            achieve_recipes,
            [p for p in PRESETS if p["op"] == "achieve" and p["a"] in selected and spec.get("budget")],
        )

    table = (frames or load_tables())[source]
    keys = list(spec["keys"])
    grouped = _aggregate(table, keys, selected, available)
    apply_derived(grouped, recipes)

    mom_col = None
    if keys == ["month"]:
        amount = "ship_amount_fc_hs_wan" if source == "ship" else "sign_amount_fc_hs_wan"
        if amount in grouped.columns:
            grouped = grouped.sort_values("month")
            prev = grouped[amount].shift(1)
            mom_col = "ship_mom" if source == "ship" else "sign_mom"
            grouped[mom_col] = _ratio(grouped[amount] - prev, prev)

    achieve_cols: list[str] = []
    if achieve_recipes and spec.get("budget"):
        grouped, achieve_cols = _apply_achieve(grouped, table, spec, achieve_recipes, frames)

    if keys == ["month"]:
        pass  # keep ascending month order
    else:
        sort_col = _sort_column(grouped, recipes + achieve_recipes, selected)
        if sort_col:
            grouped = grouped.sort_values(sort_col, ascending=False, na_position="last")
    grouped = grouped.head(limit)

    columns = keys + selected + [item["id"] for item in recipes] + achieve_cols
    for k in keys:
        if k in _NAME_COLS and _NAME_COLS[k] in grouped.columns and _NAME_COLS[k] not in columns:
            columns.append(_NAME_COLS[k])
    if mom_col and mom_col in grouped.columns:
        columns.append(mom_col)
    columns = list(dict.fromkeys(col for col in columns if col in grouped.columns))

    rows = []
    for record in grouped[columns].to_dict(orient="records"):
        rows.append({key: _json_num(key, value) for key, value in record.items()})
    return {
        "grain": grain,
        "label_zh": spec["label_zh"],
        "features": spec["features"],
        "keys": keys,
        "bases": selected,
        "derived": recipes + achieve_recipes,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "notes": NOTES,
    }


@lru_cache(maxsize=1)
def load_tables() -> dict[str, pd.DataFrame]:
    if not (PROCESSED / "ship_order_line.parquet").is_file():
        raise FileNotFoundError(str(PROCESSED))

    def _month_label(df: pd.DataFrame) -> pd.DataFrame:
        y = df["year"].astype(str).str.strip()
        m = pd.to_numeric(df["month"], errors="coerce").fillna(0).astype(int).astype(str).str.zfill(2)
        return df.assign(month=y + "-" + m)

    ship = _month_label(pd.read_parquet(PROCESSED / "ship_order_line.parquet"))
    sign = _month_label(pd.read_parquet(PROCESSED / "sign_order_line.parquet"))
    dbud = _month_label(pd.read_parquet(PROCESSED / "dept_budget_month.parquet"))
    pbud = _month_label(pd.read_parquet(PROCESSED / "product_budget_month.parquet"))

    for df in (ship, sign):
        df["area"] = df["area"].fillna("空").replace("", "空")
        df["zprod_type"] = df["zprod_type"].fillna("未覆盖").replace("", "未覆盖")
        df["zprod_name"] = df["zprod_name"].fillna("未登记机型").replace("", "未登记机型")
        df["cust_code"] = df["cust_code"].fillna("未知客户").replace("", "未知客户")
        df["cust_name"] = df.get("cust_name", pd.Series("", index=df.index)).fillna("未知客户").replace("", "未知客户")
        df["sales_code"] = df["sales_code"].fillna("未归属").replace("", "未归属")
        df["sales_name"] = df["sales_name"].fillna("未归属").replace("", "未归属")
    dbud["fdept"] = dbud["fdept"].fillna("(无科室)").replace("", "(无科室)")
    dbud["area"] = dbud["area"].fillna("空").replace("", "空")
    pbud["product_type"] = pbud["product_type"].fillna("未覆盖").replace("", "未覆盖")

    return {"ship": ship, "sign": sign, "dept_budget": dbud, "product_budget": pbud}


def _caliber_mask(fact: pd.DataFrame, covered: frozenset[str] | None = None) -> pd.Series:
    if covered is None:
        covered = _budget_covered_types()
    return (
        (fact["org_scope"] == "in_scope")
        & fact["zprod_type"].isin(covered)
        & (fact["fdept"].fillna("") != "")
    )


@lru_cache(maxsize=1)
def _budget_covered_types() -> frozenset[str]:
    pbud = pd.read_parquet(PROCESSED / "product_budget_month.parquet")
    return frozenset(str(v) for v in pbud["product_type"].dropna().unique())


def _apply_achieve(
    grouped: pd.DataFrame,
    fact: pd.DataFrame,
    spec: Mapping[str, Any],
    achieve_recipes: Sequence[Mapping[str, Any]],
    frames: dict[str, pd.DataFrame] | None,
) -> tuple[pd.DataFrame, list[str]]:
    bud_spec = spec["budget"]
    bud_src = bud_spec["source"]
    tables = frames or load_tables()
    bud_table = tables[bud_src]
    bud_available = _bases_for(bud_src)

    fact_keys = list(bud_spec["fact_keys"])
    budget_keys = list(bud_spec["budget_keys"])
    join = [(str(l), str(r)) for l, r in bud_spec["join"]]
    left_keys = [j[0] for j in join]
    right_keys = [j[1] for j in join]

    pbud = tables.get("product_budget")
    if pbud is not None and "product_type" in pbud.columns:
        covered = frozenset(str(v) for v in pbud["product_type"].dropna().unique())
    else:
        covered = None
    mask = _caliber_mask(fact, covered)
    fact_avail = _bases_for(spec["source"])

    num_agg: dict[str, tuple[str, str]] = {}
    den_agg: dict[str, tuple[str, str]] = {}
    for r in achieve_recipes:
        fact_col = fact_avail[r["a"]][0]
        budget_base = r["b"]
        if budget_base not in bud_available:
            budget_base = _BUDGET_FALLBACK.get(budget_base, {}).get(bud_src, budget_base)
        budget_col = bud_available[budget_base][0]
        num_agg[f"__num_{r['id']}"] = (fact_col, "sum")
        den_agg[f"__den_{r['id']}"] = (budget_col, "sum")

    num = fact[mask].groupby(fact_keys, dropna=False, as_index=False).agg(**num_agg)
    den = bud_table.groupby(budget_keys, dropna=False, as_index=False).agg(**den_agg)
    den = den.rename(columns=dict(zip(right_keys, left_keys)))

    merged = grouped.merge(num, on=left_keys, how="left").merge(den, on=left_keys, how="left")

    added: list[str] = []
    drop_cols: list[str] = []
    for r in achieve_recipes:
        stem = r["id"][:-4] if r["id"].endswith("_pct") else r["id"]
        merged[r["id"]] = _ratio(merged[f"__num_{r['id']}"], merged[f"__den_{r['id']}"]) * 100
        merged[stem + "_numerator_wan"] = merged[f"__num_{r['id']}"]
        merged[stem + "_denominator_wan"] = merged[f"__den_{r['id']}"]
        added.extend([r["id"], stem + "_numerator_wan", stem + "_denominator_wan"])
        drop_cols.extend([f"__num_{r['id']}", f"__den_{r['id']}"])
    merged = merged.drop(columns=drop_cols)
    return merged, added


def apply_derived(frame: pd.DataFrame, recipes: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    for recipe in recipes:
        op = recipe["op"]
        name = recipe["id"]
        left = recipe["a"]
        right = recipe.get("b")
        if left not in frame.columns:
            continue
        if op == "share":
            frame[name] = _ratio(frame[left], frame[left].sum())
            continue
        if not right or right not in frame.columns:
            continue
        if op == "div":
            frame[name] = _ratio(frame[left], frame[right])
        elif op == "mul":
            frame[name] = frame[left] * frame[right]
        elif op == "add":
            frame[name] = frame[left] + frame[right]
        elif op == "sub":
            frame[name] = frame[left] - frame[right]
    return frame


def _aggregate(
    table: pd.DataFrame,
    keys: list[str],
    selected: Sequence[str],
    available: dict[str, tuple[str, str, str]],
) -> pd.DataFrame:
    named: dict[str, tuple[str, str]] = {m: (available[m][0], available[m][1]) for m in selected}
    grouped = table.groupby(keys, dropna=False, as_index=False).agg(**named)
    for key in keys:
        name_col = _NAME_COLS.get(key)
        if name_col and name_col in table.columns and name_col not in grouped.columns:
            names = table.groupby(key, dropna=False)[name_col].agg(
                lambda values: next((str(v) for v in values if pd.notna(v) and str(v).strip()), "")
            )
            grouped = grouped.merge(names.rename(name_col), on=key, how="left")
    return grouped


def _bases_for(source: str) -> dict[str, tuple[str, str, str]]:
    if source == "ship":
        return SHIP_BASES
    if source == "sign":
        return SIGN_BASES
    if source == "dept_budget":
        return DEPT_BUDGET_BASES
    if source == "product_budget":
        return PRODUCT_BUDGET_BASES
    raise ValueError(f"unknown source: {source}")


def _base_entry(measure_id: str, spec: tuple[str, str, str]) -> dict[str, str]:
    _column, how, name_zh = spec
    return {"id": measure_id, "name_zh": name_zh, "agg": how}


def _validated_derived(raw: Sequence[Mapping[str, Any]], selected: Sequence[str]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    seen = set(selected)
    for item in raw:
        recipe_id = str(item.get("id") or "").strip()
        op = str(item.get("op") or "").strip()
        left = str(item.get("a") or "").strip()
        right = item.get("b")
        right_s = str(right).strip() if right not in (None, "") else None
        if not _ID_RE.match(recipe_id) or _FORBIDDEN_ID.search(recipe_id):
            raise ValueError(f"invalid derived id: {recipe_id}")
        if recipe_id in seen:
            raise ValueError(f"derived id collides: {recipe_id}")
        if op not in OPS:
            raise ValueError(f"invalid op: {op}")
        if left not in selected:
            raise ValueError(f"derived operand not in bases: {left}")
        if op != "share" and (not right_s or right_s not in selected):
            raise ValueError(f"derived operand not in bases: {right_s}")
        seen.add(recipe_id)
        recipes.append(
            {
                "id": recipe_id,
                "op": op,
                "a": left,
                "b": right_s,
                "name_zh": str(item.get("name_zh") or recipe_id),
                "not": item.get("not"),
                "domain": item.get("domain"),
            }
        )
    return recipes


def _validated_achieve(
    raw: Sequence[Mapping[str, Any]], selected: Sequence[str], spec: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if not raw:
        return []
    if not spec.get("budget"):
        raise ValueError(f"grain {spec['id']} has no budget projection for achieve")
    bud_src = spec["budget"]["source"]
    bud_available = _bases_for(bud_src)
    recipes: list[dict[str, Any]] = []
    seen = set(selected)
    for item in raw:
        recipe_id = str(item.get("id") or "").strip()
        left = str(item.get("a") or "").strip()
        right = str(item.get("b") or "").strip()
        if not _ID_RE.match(recipe_id) or _FORBIDDEN_ID.search(recipe_id):
            raise ValueError(f"invalid derived id: {recipe_id}")
        if recipe_id in seen:
            raise ValueError(f"derived id collides: {recipe_id}")
        if left not in selected:
            raise ValueError(f"achieve numerator not in bases: {left}")
        if right not in bud_available and right not in _BUDGET_FALLBACK:
            raise ValueError(f"achieve denominator not a budget base: {right}")
        seen.add(recipe_id)
        recipes.append(
            {
                "id": recipe_id,
                "op": "achieve",
                "a": left,
                "b": right,
                "name_zh": str(item.get("name_zh") or recipe_id),
                "not": item.get("not"),
                "domain": item.get("domain"),
            }
        )
    return recipes


def _merge_recipes(custom: list[dict[str, Any]], presets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {item["id"] for item in custom}
    merged = list(custom)
    for item in presets:
        if item["id"] in seen:
            continue
        merged.append(item)
        seen.add(item["id"])
    return merged


def _sort_column(frame: pd.DataFrame, recipes: Sequence[Mapping[str, Any]], selected: Sequence[str]) -> str | None:
    for recipe in recipes:
        rid = recipe["id"]
        if rid in frame.columns:
            return rid
    for measure in selected:
        if measure in frame.columns:
            return measure
    return None


def _ratio(numerator: pd.Series, denominator: Any) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    if isinstance(denominator, pd.Series):
        den = pd.to_numeric(denominator, errors="coerce")
        return num / den.replace(0, pd.NA)
    try:
        den_v = float(denominator)
    except (TypeError, ValueError):
        return pd.Series([pd.NA] * len(num), index=num.index)
    if den_v == 0 or not math.isfinite(den_v):
        return pd.Series([pd.NA] * len(num), index=num.index)
    return num / den_v


def _finite(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _json_num(key: str, value: Any) -> Any:
    value = _finite(value)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    number = float(value)
    if key in INT_KEYS:
        return int(round(number))
    if abs(number - round(number)) < 1e-9 and abs(number) >= 1:
        return int(round(number))
    if key.endswith("_pct"):
        return round(number, 1)
    return round(number, 4)
