import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Calculator, Play, Sigma } from "lucide-react";
import { readVersion } from "./OntologyWorkspace/ontologyUrlState";

type Grain = {
  id: string;
  label_zh: string;
  source: string;
  keys: string[];
  features: string;
  bases: string[];
};

type BaseMeasure = { id: string; name_zh: string; agg: string };
type Preset = { id: string; op: string; a: string; b?: string | null; name_zh: string; not?: string | null; domain?: string };

type DimensionMember = { code: string; label_zh: string };
type DimensionDomain = {
  code: string;
  label_zh: string;
  cn_alias?: string;
  description?: string;
  members: DimensionMember[];
};

type MeasureRef = {
  code: string;
  label_zh: string;
  category?: string;
  caliber?: string;
  unit?: string;
  base_id?: string | null;
};

type DerivedRef = {
  code: string;
  label_zh: string;
  cn_alias?: string;
  formula?: string;
  unit?: string;
  caliber?: string;
  supported: boolean;
  preset_ids?: string[];
};

type TimeKind = { kind: string; label_zh: string; sql: string; rule: string };
type TimeItem = { code: string; label_zh: string; text?: string; note?: string };
type TimeSemantics = {
  time_kinds: TimeKind[];
  rulings: TimeItem[];
  constraints: TimeItem[];
  time_key_joins: TimeItem[];
};

type Catalog = {
  window?: { StartTime: string; EndTime: string };
  grains: Grain[];
  bases_by_source: Record<string, BaseMeasure[]>;
  presets: Preset[];
  ops: string[];
  notes: string[];
  dimensions?: DimensionDomain[];
  measures?: MeasureRef[];
  derived?: DerivedRef[];
  time_semantics?: TimeSemantics;
};

type ComposeResult = {
  grain: string;
  label_zh: string;
  features: string;
  columns: string[];
  rows: Record<string, string | number | null>[];
  row_count: number;
  derived: Preset[];
  notes: string[];
};

type Domain = "iot" | "marketing" | "marketingfix";

const DOMAINS: Record<Domain, { label: string; base: string; defaultGrain: string; customA: string; customB: string }> = {
  iot: { label: "IoT 设备", base: "/api/iot/metrics", defaultGrain: "type_month", customA: "alarm_count", customB: "run_hours" },
  marketing: { label: "营销经营", base: "/api/marketing/metrics", defaultGrain: "month", customA: "ship_amount_fc_hs_wan", customB: "ship_emps" },
  marketingfix: { label: "营销经营 fix", base: "/api/marketingfix/metrics", defaultGrain: "month", customA: "ship_amount_fc_hs_wan", customB: "ship_emps" },
};

// The Explorer version (v=) selects the metric domain — never a UI toggle, so
// IoT and marketing reports stay fully separated.
function domainFromVersion(): Domain {
  if (readVersion() === "marketing") return "marketing";
  if (readVersion() === "marketingfix") return "marketingfix";
  return "iot";
}

const OPS: { id: string; label: string }[] = [
  { id: "div", label: "÷" },
  { id: "mul", label: "×" },
  { id: "add", label: "+" },
  { id: "sub", label: "−" },
  { id: "share", label: "份额" },
];

function presetUsable(preset: Preset, ids: Set<string>): boolean {
  // share 与 achieve 的 b 端分别是「全表」与「预算表」，不在当前粒度的 bases 里；
  // 其余算子要求 a、b 都在已选基础指标中。
  if (preset.op === "share") return ids.has(preset.a);
  if (preset.op === "achieve") return ids.has(preset.a);
  return ids.has(preset.a) && !!preset.b && ids.has(preset.b);
}

function opLabel(op: string): string {
  if (op === "share") return "份额";
  if (op === "achieve") return "达成";
  return op;
}

export function MetricsWorkspace() {
  const [domain] = useState<Domain>(domainFromVersion);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [grain, setGrain] = useState(DOMAINS.iot.defaultGrain);
  const [selectedBases, setSelectedBases] = useState<string[]>([]);
  const [presetOn, setPresetOn] = useState<Record<string, boolean>>({});
  const [customId, setCustomId] = useState("custom_ratio");
  const [customOp, setCustomOp] = useState("div");
  const [customA, setCustomA] = useState(DOMAINS.iot.customA);
  const [customB, setCustomB] = useState(DOMAINS.iot.customB);
  const [includeCustom, setIncludeCustom] = useState(false);
  const [result, setResult] = useState<ComposeResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const domainConfig = DOMAINS[domain];
  const grainSpec = catalog?.grains.find((item) => item.id === grain);
  const sourceBases = useMemo(() => {
    if (!catalog || !grainSpec) return [];
    return catalog.bases_by_source[grainSpec.source] || [];
  }, [catalog, grainSpec]);
  const availablePresets = useMemo(() => {
    const ids = new Set(selectedBases);
    return (catalog?.presets || []).filter((preset) => presetUsable(preset, ids));
  }, [catalog, selectedBases]);

  useEffect(() => {
    let active = true;
    setCatalog(null);
    setResult(null);
    setError("");
    fetch(`${domainConfig.base}/catalog`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`catalog ${res.status}`);
        return res.json();
      })
      .then((data: Catalog) => {
        if (!active) return;
        setCatalog(data);
        const first = data.grains.find((item) => item.id === domainConfig.defaultGrain) || data.grains[0];
        setGrain(first.id);
        setSelectedBases(first.bases);
        setPresetOn(Object.fromEntries(data.presets.map((preset) => [preset.id, true])));
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "无法加载指标目录");
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  useEffect(() => {
    if (!catalog) return;
    const spec = catalog.grains.find((item) => item.id === grain);
    if (!spec) return;
    setSelectedBases(spec.bases);
    setIncludeCustom(false);
    const nextA = spec.bases.includes(domainConfig.customA) ? domainConfig.customA : spec.bases[0];
    const nextB = spec.bases.includes(domainConfig.customB) ? domainConfig.customB : spec.bases[1] || spec.bases[0];
    setCustomA(nextA);
    setCustomB(nextB);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grain, catalog]);

  useEffect(() => {
    if (!catalog || !grainSpec || selectedBases.length === 0) return;
    const allowed = new Set(grainSpec.bases);
    if (selectedBases.some((id) => !allowed.has(id))) return;
    void runCompose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, grain, selectedBases.join("|")]);

  function toggleBase(id: string) {
    setSelectedBases((current) => {
      if (current.includes(id)) {
        return current.length === 1 ? current : current.filter((item) => item !== id);
      }
      return [...current, id];
    });
  }

  async function runCompose() {
    if (!grainSpec) return;
    const allowed = new Set(grainSpec.bases);
    const bases = selectedBases.filter((id) => allowed.has(id));
    if (bases.length === 0) return;
    setLoading(true);
    setError("");
    const ids = new Set(bases);
    const derived = availablePresets
      .filter((preset) => presetOn[preset.id] !== false && presetUsable(preset, ids))
      .map((preset) => ({ id: preset.id, op: preset.op, a: preset.a, b: preset.b, name_zh: preset.name_zh, not: preset.not }));
    if (includeCustom && customId.trim() && ids.has(customA) && (customOp === "share" || ids.has(customB))) {
      derived.push({ id: customId.trim(), op: customOp, a: customA, b: customOp === "share" ? null : customB, name_zh: customId.trim(), not: null });
    }
    try {
      const res = await fetch(`${domainConfig.base}/compose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          grain,
          bases,
          derived,
          apply_presets: false,
          limit: 200,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "组合失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ws-page" style={{ flexDirection: "row" }}>
      <div style={{ width: 380, flexShrink: 0, display: "flex", flexDirection: "column", borderRight: "1px solid var(--ws-border)", overflow: "hidden" }}>
        <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid var(--ws-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 10, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", display: "grid", placeItems: "center", color: "var(--ws-accent)" }}>
              <Sigma size={16} />
            </div>
            <div>
              <div className="ws-eyebrow" style={{ marginBottom: 2 }}>Metric Composer</div>
              <div style={{ color: "var(--ws-text)", fontWeight: 700, fontSize: 15 }}>按维度组合衍生指标</div>
            </div>
            <span className="ws-pill ws-pill--accent" style={{ marginLeft: "auto" }}>{domainConfig.label}</span>
          </div>
        </div>
        <div className="ws-scroll" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
          <label>
            <span className="ws-label">查询粒度</span>
            <select className="ws-input" value={grain} onChange={(event) => setGrain(event.target.value)}>
              {(catalog?.grains || []).map((item) => (
                <option key={item.id} value={item.id}>{item.label_zh}</option>
              ))}
            </select>
          </label>
          {grainSpec && <div className="ws-body" style={{ fontSize: 12 }}>{grainSpec.features}</div>}

          {domain === "marketingfix" && catalog?.time_semantics && (
            <details open style={{ fontSize: 12, color: "var(--ws-text)" }}>
              <summary style={{ cursor: "pointer", fontWeight: 700, color: "var(--ws-accent)", marginBottom: 6 }}>
                时间跨度累加语义（v1.3 重点）
              </summary>

              <div className="ws-label" style={{ marginTop: 4 }}>取数口径（timeKind 五值）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {catalog.time_semantics.time_kinds.map((kind) => (
                  <div key={kind.kind} style={{ padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--ws-border)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                      <strong>{kind.kind} · {kind.label_zh}</strong>
                    </div>
                    <div style={{ marginTop: 3, color: "var(--ws-text-muted)", fontFamily: "monospace", wordBreak: "break-all" }}>{kind.sql}</div>
                    <div style={{ marginTop: 2, color: "var(--ws-text-dim)" }}>{kind.rule}</div>
                  </div>
                ))}
              </div>

              <div className="ws-label" style={{ marginTop: 10 }}>口径定案（RULE）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {catalog.time_semantics.rulings.map((item) => (
                  <div key={item.code} style={{ padding: "6px 10px", borderRadius: 8, background: "rgba(76,195,138,0.05)", border: "1px solid rgba(76,195,138,0.2)" }}>
                    <strong style={{ color: "#6ee7b7" }}>{item.code} · {item.label_zh}</strong>
                    <div style={{ marginTop: 2, color: "var(--ws-text-muted)", lineHeight: 1.5 }}>{item.text}</div>
                  </div>
                ))}
              </div>

              <div className="ws-label" style={{ marginTop: 10 }}>约束（CT）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {catalog.time_semantics.constraints.map((item) => (
                  <div key={item.code} style={{ padding: "6px 10px", borderRadius: 8, background: "rgba(242,182,109,0.05)", border: "1px solid rgba(242,182,109,0.2)" }}>
                    <strong style={{ color: "#fbbf24" }}>{item.code} · {item.label_zh}</strong>
                    <div style={{ marginTop: 2, color: "var(--ws-text-muted)", lineHeight: 1.5 }}>{item.text}</div>
                  </div>
                ))}
              </div>

              <div className="ws-label" style={{ marginTop: 10 }}>时间键逻辑关联（预算 vs 实际）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {catalog.time_semantics.time_key_joins.map((item) => (
                  <div key={item.code} style={{ padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--ws-border)" }}>
                    <strong>{item.code} · {item.label_zh}</strong>
                    <div style={{ marginTop: 2, color: "var(--ws-text-muted)" }}>{item.note}</div>
                  </div>
                ))}
              </div>
            </details>
          )}

          {domain === "marketingfix" && catalog?.dimensions && (
            <details style={{ fontSize: 12, color: "var(--ws-text)" }}>
              <summary style={{ cursor: "pointer", fontWeight: 700, color: "var(--ws-text)", marginBottom: 6 }}>
                维度域（D1–D8）
              </summary>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {catalog.dimensions.map((dim) => (
                  <div key={dim.code} style={{ padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--ws-border)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6 }}>
                      <strong style={{ color: "var(--ws-accent)" }}>{dim.code} {dim.label_zh}</strong>
                      <span className="ws-pill ws-pill--mono">{dim.members.length} 成员</span>
                    </div>
                    <div style={{ marginTop: 4, color: "var(--ws-text-muted)", lineHeight: 1.5 }}>
                      {dim.members.map((member) => member.label_zh).join(" · ")}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}

          {domain === "marketingfix" && catalog?.derived && (
            <details style={{ fontSize: 12, color: "var(--ws-text)" }}>
              <summary style={{ cursor: "pointer", fontWeight: 700, color: "var(--ws-text)", marginBottom: 6 }}>
                衍生指标（X01–X22）
              </summary>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {catalog.derived.map((derived) => (
                  <div key={derived.code} style={{ padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--ws-border)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                      <strong>{derived.code} {derived.label_zh}</strong>
                      <span className="ws-pill" style={{
                        color: derived.supported ? "#6ee7b7" : "#f2b66d",
                        background: derived.supported ? "var(--ws-green-soft)" : "var(--ws-amber-soft)",
                        border: `1px solid ${derived.supported ? "rgba(76,195,138,0.28)" : "rgba(242,182,109,0.28)"}`,
                      }}>
                        {derived.supported ? "可计算" : "口径待确认"}
                      </span>
                    </div>
                    <div style={{ marginTop: 3, color: "var(--ws-text-muted)", fontFamily: "monospace" }}>
                      {derived.formula}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}

          <div>
            <div className="ws-label">基础指标</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {sourceBases.map((item) => {
                const on = selectedBases.includes(item.id);
                return (
                  <button
                    key={item.id}
                    className="ws-pill"
                    data-active={on}
                    onClick={() => toggleBase(item.id)}
                    style={{
                      cursor: "pointer",
                      color: on ? "#7fd0ff" : "var(--ws-text-muted)",
                      background: on ? "var(--ws-accent-soft)" : "rgba(255,255,255,0.04)",
                      border: on ? "1px solid rgba(74,163,255,0.4)" : "1px solid rgba(255,255,255,0.08)",
                    }}
                  >
                    {item.name_zh}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="ws-label">预设衍生</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {availablePresets.length === 0 && <div className="ws-body" style={{ fontSize: 12 }}>当前基础指标凑不出预设公式，可在下方自定义。</div>}
              {availablePresets.map((preset) => (
                <label key={preset.id} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12, color: "var(--ws-text)" }}>
                  <input type="checkbox" checked={presetOn[preset.id] !== false} onChange={(event) => setPresetOn((current) => ({ ...current, [preset.id]: event.target.checked }))} />
                  <span>
                    <strong>{preset.name_zh}</strong>
                    <span style={{ color: "var(--ws-text-muted)", marginLeft: 6, fontFamily: "monospace" }}>{preset.a} {opLabel(preset.op)} {preset.op === "achieve" ? preset.b : preset.b || ""}</span>
                    {preset.not && <div style={{ color: "var(--ws-amber)", marginTop: 2 }}>不是 {preset.not}</div>}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="ws-label">自定义组合</div>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--ws-text)", marginBottom: 8 }}>
              <input type="checkbox" checked={includeCustom} onChange={(event) => setIncludeCustom(event.target.checked)} />
              把下面这一条加入查询
            </label>
            <input className="ws-input" value={customId} onChange={(event) => setCustomId(event.target.value)} placeholder="指标 id" style={{ marginBottom: 8, fontFamily: "monospace" }} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 64px 1fr", gap: 6 }}>
              <select className="ws-input" value={customA} onChange={(event) => setCustomA(event.target.value)}>
                {selectedBases.map((id) => <option key={id} value={id}>{id}</option>)}
              </select>
              <select className="ws-input" value={customOp} onChange={(event) => setCustomOp(event.target.value)}>
                {OPS.map((op) => <option key={op.id} value={op.id}>{op.label}</option>)}
              </select>
              <select className="ws-input" value={customB} onChange={(event) => setCustomB(event.target.value)} disabled={customOp === "share"}>
                {selectedBases.map((id) => <option key={id} value={id}>{id}</option>)}
              </select>
            </div>
          </div>

          <button className="ws-btn ws-btn--primary" onClick={() => void runCompose()} disabled={loading} style={{ justifyContent: "center" }}>
            {loading ? "计算中…" : <><Play size={13} />运行组合</>}
          </button>
          <div className="ws-body" style={{ fontSize: 11, color: "var(--ws-text-dim)" }}>
            {(catalog?.notes || []).map((note) => <div key={note} style={{ marginBottom: 4 }}>{note}</div>)}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--ws-border)", display: "flex", alignItems: "center", gap: 10 }}>
          <Calculator size={14} color="var(--ws-text-muted)" />
          <span style={{ color: "var(--ws-text)", fontWeight: 700, fontSize: 13 }}>{result?.label_zh || grainSpec?.label_zh || "结果"}</span>
          {result && <span className="ws-pill ws-pill--accent">{result.row_count} 行</span>}
        </div>
        <div className="ws-scroll" style={{ flex: 1 }}>
          {error && (
            <div style={{ margin: 16, display: "flex", gap: 10, padding: "12px 14px", borderRadius: "var(--ws-radius-sm)", background: "var(--ws-red-soft)", border: "1px solid rgba(255,123,114,0.28)", color: "#fca5a5", fontSize: 13 }}>
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          {loading && !result && (
            <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 8 }}>
              {[1, 2, 3, 4].map((item) => <div key={item} className="ws-skeleton" style={{ height: 32 }} />)}
            </div>
          )}
          {result && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, color: "var(--ws-text)" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--ws-border)", background: "rgba(0,0,0,0.2)" }}>
                    <th style={{ padding: "8px 14px", textAlign: "left", color: "var(--ws-text-dim)", fontFamily: "monospace", fontSize: 11 }}>#</th>
                    {result.columns.map((column) => (
                      <th key={column} style={{ padding: "8px 14px", textAlign: "left", color: "var(--ws-text-muted)", fontFamily: "monospace", fontSize: 11, fontWeight: 700 }}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr key={index} style={{ borderBottom: "1px solid rgba(74,163,255,0.06)" }}>
                      <td style={{ padding: "7px 14px", color: "var(--ws-text-dim)", fontFamily: "monospace" }}>{index + 1}</td>
                      {result.columns.map((column) => (
                        <td key={column} style={{ padding: "7px 14px", fontFamily: "monospace", whiteSpace: "nowrap" }}>
                          {row[column] == null ? <span style={{ color: "var(--ws-text-dim)", fontStyle: "italic" }}>null</span> : String(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
