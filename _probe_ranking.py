import pandas as pd
from pathlib import Path
P = Path("datasets/processed/marketing_2026H1")
ship = pd.read_parquet(P/"ship_order_line.parquet")
sign = pd.read_parquet(P/"sign_order_line.parquet")
dept = pd.read_parquet(P/"dept_dim.parquet")
dbud = pd.read_parquet(P/"dept_budget_month.parquet")
prod = pd.read_parquet(P/"product_dim.parquet")
pbud = pd.read_parquet(P/"product_budget_month.parquet")

covered = sorted(pbud["product_type"].dropna().unique().tolist())
print("covered product types:", covered)

m = (ship["org_scope"]=="in_scope") & ship["zprod_type"].isin(covered) & (ship["fdept"].fillna("")!="")
actual = ship[m].groupby("fdept")["total_money_fc_hs_wan"].sum()
print("\nactual total:", round(actual.sum(),2), "rows:", int(m.sum()))

bud = dbud.groupby("fdept")["assessment_ship_budget_hs"].sum()
print("budget total:", round(bud.sum(),2), "depts:", len(bud))

t = pd.DataFrame({"actual": actual, "budget": bud})
t["fdept"] = t.index
t = t.merge(dept[["fdept","sales_dept","area"]], on="fdept", how="left")
t["achieve"] = (t["actual"]/t["budget"]*100).round(2)
t = t[t["budget"]>0]
t = t.sort_values("achieve", ascending=False).reset_index(drop=True)
print("rows budget>0:", len(t))
print("total budget:", round(t["budget"].sum(),2))
print("total actual:", round(t["actual"].sum(),2))
print("overall achieve:", round(t["actual"].sum()/t["budget"].sum()*100,2))
print("\nTop 5:")
print(t.head(5)[["fdept","sales_dept","area","budget","actual","achieve"]].to_string())
print("\nBottom 5:")
print(t.tail(5)[["fdept","sales_dept","area","budget","actual","achieve"]].to_string())

# also print all rows for full comparison
print("\nALL ROWS (sorted):")
for i, r in t.iterrows():
    print(f"{i+1}|{r['sales_dept']}|{r['area']}|{r['fdept']}|{round(r['budget'],2)}|{round(r['actual'],2)}|{r['achieve']}%")
