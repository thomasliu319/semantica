/**
 * src/workspaces/ManageWorkspace/MarketingPipelineTab.tsx
 *
 * Marketing data-cleaning business process (v=marketing only).
 * Static documentation of the pipeline defined in
 * openspec/changes/marketing-data-processing/: input queue → dimension/fact/budget
 * cleaning → star model → graph build → Explorer.
 */
import { Database, GitBranch, ShieldCheck, Target, ListChecks, AlertTriangle } from "lucide-react";

type PipelineStep = { id: string; title: string; desc: string; badges: string[] };

const PIPELINE: { stage: string; tone: string; steps: PipelineStep[] }[] = [
  {
    stage: "① 输入与队列",
    tone: "#4aa3ff",
    steps: [
      { id: "in", title: "10 张 CSV（只读）", desc: "SQL Server csj_dw.dbo 导出的 2026 H1 口径原始数据，utf-8-sig 去 BOM、全列按字符串读。", badges: ["只读", "口径 2026-01~06"] },
    ],
  },
  {
    stage: "② 维度表清洗",
    tone: "#4cc38a",
    steps: [
      { id: "emp", title: "emp_dim", desc: "fill_sales_dept + v_sales_emp_info 对照；sales_code 工号唯一化 458→455（在职优先 B9）；fdept_add 对齐（B5）；剔除 PII（D3）。", badges: ["455 工号", "无 PII"] },
      { id: "dept", title: "dept_dim", desc: "fill_dept_budget 去重组合 → 科室维度，补 area / area_fq，组织层级 BusinessGroup ← Area ← Dept。", badges: ["fdept 主键"] },
      { id: "prod", title: "product_dim", desc: "ods_sap_cw_product（527 行）→ ZPROD_NAME → ZPROD_TYPE 函数映射（公理 A6）。", badges: ["527 机型"] },
      { id: "cust", title: "customer_dim", desc: "签单 KunnrCode ∪ 出货 fcust_number 并集键，标注角色 contract_party / ship_to / both。", badges: ["角色标注"] },
    ],
  },
  {
    stage: "③ 事实表清洗",
    tone: "#f2b66d",
    steps: [
      { id: "sign", title: "sign_order_line", desc: "dw_sgning_wide_table 7,558 行；完全重复行去重（D2）；金额元 + 万元两列（B3）；回填 zprod_type / fdept / org_scope；负金额保留计 dq（D7）。", badges: ["7,558 行", "元+万元"] },
      { id: "ship", title: "ship_order_line", desc: "dw_sale_order_saptest 8,036 行；保留 ftag='预算数据' 30 行保底预算（D1）；出货视图剔除同 ftag 占位行；同上回填。", badges: ["8,036 行", "保留保底预算"] },
    ],
  },
  {
    stage: "④ 预算表（独立星）",
    tone: "#c084fc",
    steps: [
      { id: "dbud", title: "dept_budget_month", desc: "fill_dept_budget 234 行 = 39 科室 × 6 月；万元含税保持原值不 ×10000（D5）；18 行空 Fdept 保留进 dq。", badges: ["234 行", "万元"] },
      { id: "pbud", title: "product_budget_month", desc: "fill_product_budget 36 行 = 6 类型 × 6 月；两预算表不建任何连接（B10 互斥）。", badges: ["36 行", "互斥"] },
    ],
  },
  {
    stage: "⑤ 产出",
    tone: "#ff7b72",
    steps: [
      { id: "out", title: "parquet + dq_report + model_star", desc: "datasets/processed/marketing_2026H1/*.parquet + dq_report.json + model_star.json（星型描述）。", badges: ["parquet", "dq_report"] },
      { id: "graph", title: "marketing_cleaned_semantics.json", desc: "build_marketing_graph.py → 知识图谱 + marketing_ontology.ttl，供 Explorer 加载与 GraphRAG 检索。", badges: ["21,236 节点", "93,018 边"] },
    ],
  },
];

const CALIBER: { no: string; name: string; filter: string; cost: string }[] = [
  { no: "1", name: "组织", filter: "org_scope = 'in_scope'（Orgname 属装备一）", cost: "228.6%" },
  { no: "2", name: "机型", filter: "zprod_type ∈ 预算覆盖 6 类", cost: "148.2%" },
  { no: "3", name: "科室", filter: "fdept 非空", cost: "103.3%" },
  { no: "4", name: "单位", filter: "分子 /10000 后与万元预算相除", cost: "差 10⁴ 倍" },
];

const RULES: { no: string; text: string }[] = [
  { no: "R1", text: "日期标准化 YYYY-MM-DD；空值统一（NULL / \"NULL\" / 空串 → 空）。" },
  { no: "R2", text: "金额列保留 2 位小数；数量列保留 3 位小数。" },
  { no: "R3", text: "科室键以 fdept_add 对齐；fdept 仅作对照，值域冲突（92 行）记 dq。" },
  { no: "R4", text: "同工号多名取规范行（在职优先），聚合层 GROUP BY SalesCode + MAX(姓名)。" },
  { no: "R5", text: "期间取 Fyear/Fmonth（签单）与 fyear/fperiod（出货）；禁止用日期反推。" },
  { no: "R6", text: "机型以 ZPROD_NAME 为准；FmateNumber 物料编码降为属性。" },
  { no: "R7", text: "空键不参与任何对照；未归属行进 dq 保留。" },
  { no: "R8", text: "负金额（退货/退补）保留，dq 计数而非剔除。" },
];

const DQ: { label: string; value: string; desc: string }[] = [
  { label: "无科室行", value: "出货 1131 / 签单 800", desc: "B8 空键伪命中" },
  { label: "机型未登记", value: "签单 20 / 出货 38", desc: "未命中置空 + model_unregistered" },
  { label: "工号双行", value: "3 工号", desc: "C13437/C13480/C15083 各 2 行（B9）" },
  { label: "负金额行", value: "签单 264 / 出货 299", desc: "退货/退补保留（D7）" },
  { label: "空 Fdept 预算", value: "18 行", desc: "其他部门代卖，保留进 dq" },
  { label: "科室键冲突", value: "92 行", desc: "fdept vs fdept_add 值域冲突" },
];

const RESULTS: { label: string; value: string; tone: string }[] = [
  { label: "考核出机达成率", value: "130.6%", tone: "var(--ws-accent)" },
  { label: "管理出机达成率", value: "91.1%", tone: "var(--ws-green)" },
  { label: "管理签单达成率", value: "103.2%", tone: "var(--ws-purple)" },
];

const BLOCKERS: { id: string; name: string; found: string; cost: string }[] = [
  { id: "B6", name: "组织口径", found: "预算 234/234 是装备一，宽表混 8 个组织", cost: "228.6%" },
  { id: "B7", name: "机型覆盖", found: "预算只覆盖 6/22 产品类型，漏 3C钻攻机 12.1 亿", cost: "148.2%" },
  { id: "B8", name: "空键伪命中", found: "出货 1163/8036 行无科室", cost: "103.3%" },
  { id: "B9", name: "工号不唯一", found: "458 行 / 455 工号，3 工号在职+离职各一行", cost: "业绩翻倍" },
  { id: "B10", name: "预算同源", found: "两张预算表三指标合计差 ≤1.26 万元", cost: "预算翻倍" },
];

export function MarketingPipelineTab() {
  return (
    <div className="ws-page">
      <div className="ws-scroll" style={{ flex: 1, padding: "18px 22px", display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", display: "grid", placeItems: "center", color: "var(--ws-accent)" }}>
            <Database size={18} />
          </div>
          <div>
            <div style={{ color: "var(--ws-text)", fontSize: 16, fontWeight: 750, lineHeight: 1.1 }}>营销数据清洗流程</div>
            <div className="ws-body" style={{ fontSize: 11, marginTop: 3 }}>10 张 CSV → 维度/事实/预算清洗 → 星型建模 → 知识图谱</div>
          </div>
          <span className="ws-pill ws-pill--accent" style={{ marginLeft: "auto" }}>v=marketing</span>
        </div>

        {/* 达成率结果 */}
        <div className="ws-stat-grid ws-stat-grid--3">
          {RESULTS.map((r) => (
            <div key={r.label} className="ws-stat-card">
              <div className="ws-eyebrow" style={{ marginBottom: 6 }}>{r.label}</div>
              <div className="ws-stat-value" style={{ color: r.tone }}>{r.value}</div>
              <div className="ws-stat-label">H1 默认口径实算</div>
            </div>
          ))}
        </div>

        {/* 流水线 */}
        <div className="ws-card" style={{ padding: "18px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <GitBranch size={15} color="var(--ws-accent)" />
            <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>清洗流水线</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {PIPELINE.map((group, gi) => (
              <div key={group.stage} style={{ display: "flex", gap: 14 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 22, flexShrink: 0 }}>
                  <div style={{ width: 12, height: 12, borderRadius: 999, background: group.tone, boxShadow: `0 0 10px ${group.tone}66`, marginTop: 6 }} />
                  {gi < PIPELINE.length - 1 && <div style={{ width: 2, flex: 1, background: "rgba(255,255,255,0.08)", marginTop: 4 }} />}
                </div>
                <div style={{ flex: 1, paddingBottom: 18 }}>
                  <div style={{ color: group.tone, fontSize: 12, fontWeight: 800, letterSpacing: "0.03em", marginBottom: 10 }}>{group.stage}</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {group.steps.map((step) => (
                      <div key={step.id} style={{ padding: "11px 14px", borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid var(--ws-border)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span style={{ color: "var(--ws-text)", fontSize: 13, fontWeight: 700 }}>{step.title}</span>
                          {step.badges.map((b) => (
                            <span key={b} className="ws-pill ws-pill--mono" style={{ fontSize: 10 }}>{b}</span>
                          ))}
                        </div>
                        <div className="ws-body" style={{ fontSize: 12, marginTop: 5, lineHeight: 1.6 }}>{step.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 达成率四要素 */}
        <div className="ws-card" style={{ padding: "18px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Target size={15} color="var(--ws-accent)" />
            <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>达成率四要素（漏掉任一即失真）</div>
          </div>
          <div style={{ width: "100%", overflowX: "auto", borderRadius: 10, border: "1px solid var(--ws-border)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead style={{ background: "rgba(255,255,255,0.03)" }}>
                <tr>
                  {["#", "要素", "过滤条件", "漏掉后果"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--ws-text-muted)", fontWeight: 700, borderBottom: "1px solid var(--ws-border)", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {CALIBER.map((c) => (
                  <tr key={c.no}>
                    <td style={{ padding: "8px 10px", color: "var(--ws-text-dim)", borderBottom: "1px solid var(--ws-border)" }}>{c.no}</td>
                    <td style={{ padding: "8px 10px", color: "var(--ws-text)", fontWeight: 700, borderBottom: "1px solid var(--ws-border)", whiteSpace: "nowrap" }}>{c.name}</td>
                    <td style={{ padding: "8px 10px", color: "var(--ws-text)", fontFamily: "JetBrains Mono, monospace", fontSize: 11, borderBottom: "1px solid var(--ws-border)" }}>{c.filter}</td>
                    <td style={{ padding: "8px 10px", color: "#ff7b72", fontWeight: 700, borderBottom: "1px solid var(--ws-border)", whiteSpace: "nowrap" }}>{c.cost}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="ws-body" style={{ fontSize: 11, marginTop: 8 }}>
            达成率 = Σ ShipOrderLine.total_money_fc_hs_wan（满足四要素） / Σ DeptBudgetMonth.*_budget_hs（万元含税原值），分母为 0 → null。
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          {/* 清洗规则 */}
          <div className="ws-card" style={{ padding: "16px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <ListChecks size={15} color="var(--ws-green)" />
              <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>清洗规则</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {RULES.map((r) => (
                <div key={r.no} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span className="ws-pill ws-pill--mono" style={{ fontSize: 10, flexShrink: 0 }}>{r.no}</span>
                  <span className="ws-body" style={{ fontSize: 12, lineHeight: 1.55 }}>{r.text}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* 数据质量 */}
            <div className="ws-card" style={{ padding: "16px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <ShieldCheck size={15} color="var(--ws-amber)" />
                <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>数据质量报告（dq_report.json）</div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {DQ.map((d) => (
                  <div key={d.label} style={{ padding: "9px 11px", borderRadius: 9, background: "rgba(0,0,0,0.18)", border: "1px solid var(--ws-border)" }}>
                    <div className="ws-eyebrow" style={{ fontSize: 9 }}>{d.label}</div>
                    <div style={{ color: "var(--ws-text)", fontSize: 13, fontWeight: 700, marginTop: 2 }}>{d.value}</div>
                    <div className="ws-body" style={{ fontSize: 10, marginTop: 2 }}>{d.desc}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* 阻塞项 */}
            <div className="ws-card" style={{ padding: "16px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <AlertTriangle size={15} color="#ff7b72" />
                <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>实采后追加的阻塞项（B6–B10）</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {BLOCKERS.map((b) => (
                  <div key={b.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "6px 0" }}>
                    <span className="ws-pill ws-pill--mono" style={{ fontSize: 10, flexShrink: 0 }}>{b.id}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ color: "var(--ws-text)", fontSize: 12, fontWeight: 700 }}>{b.name}</span>
                      <span className="ws-body" style={{ fontSize: 11 }}>　{b.found}</span>
                    </div>
                    <span style={{ color: "#ff7b72", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{b.cost}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
