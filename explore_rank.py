import json, collections
g = json.load(open("datasets/json/marketing_cleaned_semantics.json"))
nodes = g["nodes"]; edges = g["edges"]
by_id = {n["id"]: n for n in nodes}

covered_types = {"卧加", "型材机", "小五轴", "立加", "通用钻攻机", "龙门机"}

dept_info = {}
for n in nodes:
    if n.get("type") == "Dept":
        p = n.get("properties", {})
        dept_info[n["id"]] = {"name": p.get("content") or n["id"], "sales_dept": p.get("sales_dept"), "area": p.get("area")}

ofmodel = collections.defaultdict(list); ofdept = collections.defaultdict(list); budgetsfor = collections.defaultdict(list); oftype = collections.defaultdict(list)
for e in edges:
    r = e.get("relation")
    if r == "ofModel": ofmodel[e["source"]].append(e["target"])
    elif r == "ofType": oftype[e["source"]].append(e["target"])
    elif r == "ofDept": ofdept[e["source"]].append(e["target"])
    elif r == "budgetsFor": budgetsfor[e["source"]].append(e["target"])

# budget per dept
dept_budget = collections.defaultdict(float)
for b in [n for n in nodes if n.get("type") == "DeptBudgetMonth"]:
    for d in budgetsfor.get(b["id"], []):
        dept_budget[d] += float(b.get("properties", {}).get("assessment_ship_budget_hs") or 0)

# covered model ids (Product budget_covered true)
covered_models = {n["id"] for n in nodes if n.get("type") == "Product" and str(n.get("properties", {}).get("budget_covered")).lower() == "true"}

def compute(use_oftype):
    dept_actual = collections.defaultdict(float)
    for s in nodes:
        if s.get("type") != "ShipOrderLine": continue
        p = s.get("properties", {})
        if p.get("org_scope") != "in_scope": continue
        if not ofdept.get(s["id"]): continue
        if use_oftype:
            if not any(t.replace("ptype:", "") in covered_types for t in oftype.get(s["id"], [])): continue
        else:
            if not any(m in covered_models for m in ofmodel.get(s["id"], [])): continue
        dept_actual[ofdept[s["id"]][0]] += float(p.get("amount_wan") or 0)
    return dept_actual

for use_oftype in (False, True):
    da = compute(use_oftype)
    tot_b = sum(dept_budget.values()); tot_a = sum(da.values())
    print(f"use_oftype={use_oftype}: 目标={tot_b:,.2f} 实际={tot_a:,.2f} 达成={tot_a/tot_b*100:.2f}%")
    # top 1
    top = max(dept_budget, key=lambda d: da.get(d,0)/dept_budget[d] if dept_budget[d] else 0)
    print(f"   top: {dept_info[top]['name']!r} 目标={dept_budget[top]:,.2f} 实际={da.get(top,0):,.2f}")
