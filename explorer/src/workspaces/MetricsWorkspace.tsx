import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Calculator, Play, Sigma } from "lucide-react";

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

type Catalog = {
  grains: Grain[];
  bases_by_source: Record<string, BaseMeasure[]>;
  presets: Preset[];
  ops: string[];
  notes: string[];
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

const OPS: { id: string; label: string }[] = [
  { id: "div", label: "÷" },
  { id: "mul", label: "×" },
  { id: "add", label: "+" },
  { id: "sub", label: "−" },
  { id: "share", label: "份额" },
];

export function MetricsWorkspace() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [grain, setGrain] = useState("type_month");
  const [selectedBases, setSelectedBases] = useState<string[]>([]);
  const [presetOn, setPresetOn] = useState<Record<string, boolean>>({});
  const [customId, setCustomId] = useState("custom_ratio");
  const [customOp, setCustomOp] = useState("div");
  const [customA, setCustomA] = useState("alarm_count");
  const [customB, setCustomB] = useState("run_hours");
  const [includeCustom, setIncludeCustom] = useState(false);
  const [result, setResult] = useState<ComposeResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const grainSpec = catalog?.grains.find((item) => item.id === grain);
  const sourceBases = useMemo(() => {
    if (!catalog || !grainSpec) return [];
    return catalog.bases_by_source[grainSpec.source] || [];
  }, [catalog, grainSpec]);
  const availablePresets = useMemo(() => {
    const ids = new Set(selectedBases);
    return (catalog?.presets || []).filter((preset) => ids.has(preset.a) && (preset.op === "share" || (preset.b && ids.has(preset.b))));
  }, [catalog, selectedBases]);

  useEffect(() => {
    fetch("/api/iot/metrics/catalog")
      .then(async (res) => {
        if (!res.ok) throw new Error(`catalog ${res.status}`);
        return res.json();
      })
      .then((data: Catalog) => {
        setCatalog(data);
        const first = data.grains.find((item) => item.id === "type_month") || data.grains[0];
        setGrain(first.id);
        setSelectedBases(first.bases);
        setPresetOn(Object.fromEntries(data.presets.map((preset) => [preset.id, true])));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "无法加载指标目录"));
  }, []);

  useEffect(() => {
    if (!catalog) return;
    const spec = catalog.grains.find((item) => item.id === grain);
    if (!spec) return;
    setSelectedBases(spec.bases);
    setIncludeCustom(false);
    const nextA = spec.bases.includes("alarm_count") ? "alarm_count" : spec.bases[0];
    const nextB = spec.bases.includes("run_hours") ? "run_hours" : spec.bases[1] || spec.bases[0];
    setCustomA(nextA);
    setCustomB(nextB);
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
      .filter((preset) => presetOn[preset.id] !== false && ids.has(preset.a) && (preset.op === "share" || (preset.b && ids.has(preset.b))))
      .map((preset) => ({ id: preset.id, op: preset.op, a: preset.a, b: preset.b, name_zh: preset.name_zh, not: preset.not }));
    if (includeCustom && customId.trim() && ids.has(customA) && (customOp === "share" || ids.has(customB))) {
      derived.push({ id: customId.trim(), op: customOp, a: customA, b: customOp === "share" ? null : customB, name_zh: customId.trim(), not: null });
    }
    try {
      const res = await fetch("/api/iot/metrics/compose", {
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
                    <span style={{ color: "var(--ws-text-muted)", marginLeft: 6, fontFamily: "monospace" }}>{preset.a} {preset.op === "share" ? "份额" : preset.op} {preset.b || ""}</span>
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
