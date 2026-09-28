import { useState, useEffect, useMemo, useRef } from "react";
import { Scale, Search, ArrowRight, Info, Play, GitBranch, Circle, Rows3 } from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { readVersion } from "../OntologyWorkspace/ontologyUrlState";

const IOT_GRAPHRAG_TEMPLATE_GROUPS = [
  {
    dim: "设备 × 月",
    items: [
      "设备 152600398 2026-08 工作情况",
      "设备 172600735 2026-04 2026-05 2026-06 运行与报警",
      "T-V856S 2026年4月，2026年5月，2026年9月运行时间，运行天数，设备台数",
    ],
  },
  {
    dim: "区域",
    items: [
      "华南区 设备分布",
      "华南区 运行小时",
      "华东区 运行时长",
    ],
  },
  {
    dim: "客户",
    items: [
      "太仓卓立精密机械有限公司 设备情况",
      "深圳市天铸智造有限公司 设备情况",
    ],
  },
  {
    dim: "机型 × 月",
    items: [
      "T-V856S 2026-04 运行时间",
      "T-V856S 2026-04 2026-05 运行时间",
      "T-V856S 2026年04月，2026年05月运行时间",
      "T-V856S 2026年4月，2026年5月运行时间，运行天数",
      "T-V856S 2026-04 报警强度为什么高",
      "T-600 2026-08 运行小时",
    ],
  },
  {
    dim: "治理",
    items: [
      "主轴快照能不能当 4–8 月工况",
      "为什么丢掉 3 月",
      "关机是不是停机",
    ],
  },
];

const MARKETING_GRAPHRAG_TEMPLATE_GROUPS = [
  {
    dim: "达成率 · 科室/大区",
    items: [
      "管理出机达成率",
      "华南大区 考核出机达成率",
      "华东一区销售一科 管理签单达成",
    ],
  },
  {
    dim: "达成率 · 产品类型",
    items: [
      "通用钻攻机 管理出机达成率",
      "立加 考核出机达成率",
    ],
  },
  {
    dim: "结构 / 份额",
    items: [
      "产品类型出货结构",
      "通用钻攻机 出货份额",
    ],
  },
  {
    dim: "客户 × 机型",
    items: [
      "客户 C01000008 机型",
      "客户 C01000005 机型",
    ],
  },
  {
    dim: "业务员行为",
    items: [
      "连续3个月不签单人数",
      "连续2个月未出机人数",
    ],
  },
  {
    dim: "治理 · 拒答探针",
    items: [
      "成本利润率",
      "主管 团队业绩",
      "下半年 出货",
    ],
  },
];

type OutcomeKind = "approved" | "rejected" | "deferred" | "pending" | string;

function outcomeColor(outcome: string) {
  const o = (outcome ?? "").toLowerCase();
  if (o.includes("approv") || o.includes("accept")) return { color: "#6ee7b7", bg: "var(--ws-green-soft)", border: "rgba(76,195,138,0.3)" };
  if (o.includes("reject") || o.includes("denied") || o.includes("fail"))  return { color: "#fca5a5", bg: "var(--ws-red-soft)",   border: "rgba(255,123,114,0.3)" };
  if (o.includes("defer") || o.includes("pending") || o.includes("review")) return { color: "#fbbf24", bg: "var(--ws-amber-soft)", border: "rgba(242,182,109,0.3)" };
  return { color: "var(--ws-text-muted)", bg: "rgba(255,255,255,0.04)", border: "rgba(255,255,255,0.1)" };
}

function OutcomeBadge({ outcome }: { outcome: OutcomeKind }) {
  const c = outcomeColor(outcome);
  return (
    <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", color: c.color, background: c.bg, border: `1px solid ${c.border}` }}>
      {outcome || "unknown"}
    </span>
  );
}

interface ChainStep {
  id: string;
  relationship: string;
  content?: string;
  type?: string;
  hop?: number;
  [key: string]: unknown;
}

interface GraphSource {
  id: string;
  type: string;
  content: string;
  score: number;
  kind: string;
  hop: number;
  facts?: string;
}

interface GraphPathHop {
  source: string;
  relationship: string;
  target: string;
  hop: number;
}

interface DecisionItem {
  decision_id: string;
  category?: string;
  outcome?: string;
  scenario?: string;
  reasoning?: string;
  confidence?: number;
}

interface GraphRAGResult {
  decision_id: string;
  query: string;
  response: string;
  reasoning_path: string;
  confidence: number;
  outcome: string;
  num_sources: number;
  sources: GraphSource[];
  path: GraphPathHop[];
  chain: ChainStep[];
  sparql?: string;
  mapping?: { nl?: string; table?: string; node?: string; joins?: string; metrics?: string }[];
}

const MARKDOWN_COMPONENTS: Components = {
  h2: ({ children }) => <h2 style={{ margin: "0 0 12px", fontSize: 18, fontWeight: 750, color: "var(--ws-text)", letterSpacing: "-0.02em" }}>{children}</h2>,
  h3: ({ children }) => <h3 style={{ margin: "18px 0 8px", fontSize: 13, fontWeight: 700, color: "var(--ws-text)", letterSpacing: "0.02em" }}>{children}</h3>,
  p: ({ children }) => <p style={{ margin: "0 0 10px", fontSize: 13, lineHeight: 1.65, color: "var(--ws-text)" }}>{children}</p>,
  strong: ({ children }) => <strong style={{ color: "var(--ws-text)", fontWeight: 700 }}>{children}</strong>,
  em: ({ children }) => <em style={{ color: "var(--ws-text-muted)" }}>{children}</em>,
  ul: ({ children }) => <ul style={{ margin: "0 0 10px", paddingLeft: 18, color: "var(--ws-text)", fontSize: 13, lineHeight: 1.6 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ display: "block", margin: "0 0 10px", paddingLeft: 18, color: "var(--ws-text)", fontSize: 13, lineHeight: 1.7, whiteSpace: "normal" }}>{children}</ol>,
  li: ({ children }) => <li style={{ display: "list-item", marginBottom: 6, whiteSpace: "normal" }}>{children}</li>,
  code: ({ className, children }) => {
    const block = typeof className === "string" && className.includes("language-");
    if (block) {
      return <code className={className} style={{ fontFamily: "JetBrains Mono, Fira Code, monospace", fontSize: 11, color: "var(--ws-text)" }}>{children}</code>;
    }
    return <code style={{ fontFamily: "JetBrains Mono, Fira Code, monospace", fontSize: 11, color: "var(--ws-accent)", background: "var(--ws-accent-soft)", padding: "1px 5px", borderRadius: 4 }}>{children}</code>;
  },
  pre: ({ children }) => (
    <pre style={{ margin: "8px 0 14px", padding: 12, overflowX: "auto", fontSize: 11, lineHeight: 1.5, fontFamily: "JetBrains Mono, Fira Code, monospace", background: "rgba(255,255,255,0.03)", border: "1px solid var(--ws-border)", borderRadius: 8, color: "var(--ws-text)", whiteSpace: "pre" }}>
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div style={{ width: "100%", overflowX: "auto", margin: "8px 0 14px", borderRadius: 10, border: "1px solid var(--ws-border)" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead style={{ background: "rgba(255,255,255,0.03)" }}>{children}</thead>,
  th: ({ children }) => <th style={{ textAlign: "left", padding: "8px 10px", color: "var(--ws-text-muted)", fontWeight: 700, borderBottom: "1px solid var(--ws-border)", whiteSpace: "nowrap" }}>{children}</th>,
  td: ({ children }) => <td style={{ padding: "7px 10px", color: "var(--ws-text)", borderBottom: "1px solid var(--ws-border)", verticalAlign: "top" }}>{children}</td>,
};

const PATH_HOP_RE = /(\d+)\.\s+\*\*(.+?)\*\*\s+—`([^`]+)`→\s+\*\*(.+?)\*\*/g;
const KIND_ZH: Record<string, string> = { retrieve: "召回", expand: "扩图", sparql: "SPARQL" };

function pathToMarkdownTable(text: string): string {
  const rows = [...text.matchAll(PATH_HOP_RE)];
  if (rows.length < 1) return text;
  const table = [
    "| # | 起点 | 关系 | 终点 |",
    "| --- | --- | --- | --- |",
    ...rows.map((row) => `| ${row[1]} | ${row[2]} | \`${row[3]}\` | ${row[4]} |`),
  ].join("\n");
  return text.replace(PATH_HOP_RE, "").replace(/### 证据链\s*/, `### 证据链\n\n${table}\n\n`);
}

function GraphRAGMarkdown({ content }: { content: string }) {
  const markdown = pathToMarkdownTable(content).trim();
  if (!markdown) return null;
  return (
    <div className="graphrag-md" style={{ whiteSpace: "normal" }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function ReportTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div style={{ width: "100%", overflowX: "auto", margin: "8px 0 16px", borderRadius: 10, border: "1px solid var(--ws-border)" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, whiteSpace: "normal" }}>
        <thead style={{ background: "rgba(255,255,255,0.03)" }}>
          <tr>
            {headers.map((header) => (
              <th key={header} style={{ textAlign: "left", padding: "8px 10px", color: "var(--ws-text-muted)", fontWeight: 700, borderBottom: "1px solid var(--ws-border)", whiteSpace: "nowrap" }}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row[0]}-${index}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${index}-${cellIndex}`} style={{ padding: "8px 10px", color: "var(--ws-text)", borderBottom: "1px solid var(--ws-border)", verticalAlign: "top", lineHeight: 1.55 }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function nodeLabel(id: string, rag: GraphRAGResult, chain: ChainStep[]): string {
  const hit = rag.sources.find((row) => row.id === id);
  if (hit?.content) return hit.content;
  const step = chain.find((row) => row.id === id);
  if (step?.content) return step.content;
  return id.replace(/^(equipmonth|equip|customer|area|slice|type|month|band|domain|alarm|dept|ptype|cust|emp|model):/, "");
}

function GraphRAGStructured({ rag, chain }: { rag: GraphRAGResult; chain: ChainStep[] }) {
  const intro = rag.response.split("### 主要命中")[0]?.trim() || `## ${rag.query}`;
  return (
    <div style={{ whiteSpace: "normal" }}>
      <GraphRAGMarkdown content={intro} />
      <h3 style={{ margin: "18px 0 8px", fontSize: 13, fontWeight: 700, color: "var(--ws-text)" }}>主要命中</h3>
      <ReportTable
        headers={["节点", "类型", "来源", "要点"]}
        rows={rag.sources.slice(0, 6).map((row) => [row.content || row.id, row.type, KIND_ZH[row.kind] || row.kind, row.facts || ""])}
      />
      {rag.path.length > 0 ? (
        <>
          <h3 style={{ margin: "18px 0 8px", fontSize: 13, fontWeight: 700, color: "var(--ws-text)" }}>证据链</h3>
          <ReportTable
            headers={["#", "起点", "关系", "终点"]}
            rows={rag.path.map((hop, index) => [
              String(index + 1),
              nodeLabel(hop.source, rag, chain),
              hop.relationship,
              nodeLabel(hop.target, rag, chain),
            ])}
          />
        </>
      ) : null}
      <h3 style={{ margin: "18px 0 8px", fontSize: 13, fontWeight: 700, color: "var(--ws-text)" }}>全部证据</h3>
      <ReportTable
        headers={["#", "来源", "跳数", "类型", "节点", "要点"]}
        rows={rag.sources.map((row, index) => [
          String(index + 1),
          KIND_ZH[row.kind] || row.kind,
          String(row.hop),
          row.type,
          row.content || row.id,
          row.facts || "",
        ])}
      />
    </div>
  );
}

const NODE_ACCENTS = ["#4aa3ff","#4cc38a","#f2b66d","#c084fc","#ff7b72","#38bdf8","#a78bfa"];

function ChainNode({ step, index }: { step: ChainStep; index: number }) {
  const accent = NODE_ACCENTS[index % NODE_ACCENTS.length];
  return (
    <div style={{ padding: "14px 16px", borderRadius: "var(--ws-radius)", background: "var(--ws-surface)", border: `1px solid ${accent}28`, borderLeft: `3px solid ${accent}`, position: "relative" }}>
      {step.type && (
        <div style={{ fontFamily: "monospace", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: accent, marginBottom: 5 }}>
          {step.type}
        </div>
      )}
      <div style={{ color: "var(--ws-text)", fontSize: 13, fontWeight: 600 }}>{step.content || step.id}</div>
      {step.id && step.id !== step.content && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--ws-text-dim)", marginTop: 3 }}>{step.id}</div>
      )}
    </div>
  );
}

function RelEdge({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0, padding: "2px 0" }}>
      <div style={{ width: 2, height: 10, background: "var(--ws-border)" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: 999, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", maxWidth: 260 }}>
        <ArrowRight size={10} color="var(--ws-accent)" />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--ws-accent)", letterSpacing: "0.06em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      </div>
      <div style={{ width: 2, height: 10, background: "var(--ws-border)" }} />
    </div>
  );
}

type ChainView = "cards" | "orbit";
type ChainPick = { kind: "node" | "edge"; index: number } | null;

function CausalFlow({ chain, loading }: { chain: ChainStep[]; loading: boolean }) {
  if (loading) return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {[1,2,3].map((i) => <div key={i} className="ws-skeleton" style={{ height: 68 }} />)}
    </div>
  );
  if (!chain.length) return (
    <div className="ws-empty">
      <div className="ws-empty-icon"><Info size={28} /></div>
      <div className="ws-empty-title">No chain steps</div>
      <div className="ws-empty-body">No causal chain steps were found for this decision.</div>
    </div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {chain.map((step, i) => (
        <div key={`${step.id}-${i}`}>
          <ChainNode step={step} index={i} />
          {i < chain.length - 1 && <RelEdge label={chain[i + 1]?.relationship || "→"} />}
        </div>
      ))}
    </div>
  );
}

function CausalOrbit({ chain, loading }: { chain: ChainStep[]; loading: boolean }) {
  const [picked, setPicked] = useState<ChainPick>(null);

  useEffect(() => {
    setPicked(null);
  }, [chain]);

  const layout = useMemo(() => {
    const count = chain.length;
    const gap = 78;
    const radius = 15;
    const pad = 36;
    const width = Math.max(520, pad * 2 + Math.max(count - 1, 0) * gap);
    const height = 210;
    const midY = 96;
    const nodes = chain.map((step, index) => ({
      step,
      index,
      x: pad + index * gap,
      y: midY + (index % 2 === 0 ? -10 : 10),
      color: NODE_ACCENTS[index % NODE_ACCENTS.length],
    }));
    const edges = nodes.slice(0, -1).map((from, index) => {
      const to = nodes[index + 1];
      const lift = index % 2 === 0 ? -28 : 28;
      const cx = (from.x + to.x) / 2;
      const cy = (from.y + to.y) / 2 + lift;
      return {
        index,
        from,
        to,
        rel: chain[index + 1]?.relationship || "relatedTo",
        d: `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`,
      };
    });
    return { width, height, radius, nodes, edges };
  }, [chain]);

  if (loading) {
    return <div className="ws-skeleton" style={{ height: 220 }} />;
  }
  if (!chain.length) {
    return (
      <div className="ws-empty">
        <div className="ws-empty-icon"><Info size={28} /></div>
        <div className="ws-empty-title">No chain steps</div>
        <div className="ws-empty-body">No causal chain steps were found for this decision.</div>
      </div>
    );
  }

  const pickedNode = picked?.kind === "node" ? layout.nodes[picked.index] : null;
  const pickedEdge = picked?.kind === "edge" ? layout.edges[picked.index] : null;

  return (
    <div>
      <div style={{ overflowX: "auto", marginBottom: 12 }}>
        <svg
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          role="img"
          aria-label="Causal chain graph"
          onClick={() => setPicked(null)}
          style={{ display: "block", minWidth: "100%" }}
        >
          <defs>
            <marker id="chain-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(127,208,255,0.7)" />
            </marker>
          </defs>
          {layout.edges.map((edge) => {
            const active = picked?.kind === "edge" && picked.index === edge.index;
            return (
              <g key={`edge-${edge.index}`}>
                <path d={edge.d} fill="none" stroke="transparent" strokeWidth={18} style={{ cursor: "pointer" }} onClick={(event) => { event.stopPropagation(); setPicked({ kind: "edge", index: edge.index }); }} />
                <path d={edge.d} fill="none" stroke={active ? "var(--ws-accent)" : "rgba(127,208,255,0.35)"} strokeWidth={active ? 2.6 : 1.6} markerEnd="url(#chain-arrow)" style={{ pointerEvents: "none" }} />
              </g>
            );
          })}
          {layout.nodes.map((node) => {
            const active = picked?.kind === "node" && picked.index === node.index;
            return (
              <g key={`node-${node.index}-${node.step.id}`}>
                {active ? <circle cx={node.x} cy={node.y} r={layout.radius + 7} fill="none" stroke={node.color} strokeWidth={1.5} opacity={0.7} /> : null}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={layout.radius}
                  fill={active ? node.color : `${node.color}33`}
                  stroke={node.color}
                  strokeWidth={2}
                  style={{ cursor: "pointer" }}
                  onClick={(event) => { event.stopPropagation(); setPicked({ kind: "node", index: node.index }); }}
                />
              </g>
            );
          })}
        </svg>
      </div>
      <div style={{ minHeight: 72, padding: "12px 14px", borderRadius: 12, background: "var(--ws-surface)", border: "1px solid var(--ws-border)" }}>
        {pickedNode ? (
          <div>
            <div className="ws-eyebrow" style={{ marginBottom: 6 }}>节点 · {pickedNode.step.type || "entity"}</div>
            <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>{pickedNode.step.content || pickedNode.step.id}</div>
            {pickedNode.step.id && pickedNode.step.id !== pickedNode.step.content ? (
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "var(--ws-text-dim)", marginTop: 4 }}>{pickedNode.step.id}</div>
            ) : null}
          </div>
        ) : pickedEdge ? (
          <div>
            <div className="ws-eyebrow" style={{ marginBottom: 6 }}>条件</div>
            <div style={{ color: "var(--ws-accent)", fontSize: 14, fontWeight: 700 }}>{pickedEdge.rel}</div>
            <div style={{ fontSize: 12, color: "var(--ws-text-muted)", marginTop: 6 }}>
              {pickedEdge.from.step.content || pickedEdge.from.step.id} → {pickedEdge.to.step.content || pickedEdge.to.step.id}
            </div>
          </div>
        ) : (
          <div style={{ color: "var(--ws-text-muted)", fontSize: 12 }}>点击圆形或边，查看节点文本或条件关系。</div>
        )}
      </div>
    </div>
  );
}

export function DecisionWorkspace() {
  const templateGroups = readVersion() === "marketing" ? MARKETING_GRAPHRAG_TEMPLATE_GROUPS : IOT_GRAPHRAG_TEMPLATE_GROUPS;
  const templates = templateGroups.flatMap((group) => group.items);
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [selected, setSelected] = useState<DecisionItem | null>(null);
  const [chain, setChain] = useState<ChainStep[]>([]);
  const [chainLoading, setChainLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [query, setQuery] = useState(templates[0]);
  const [ragLoading, setRagLoading] = useState(false);
  const [rag, setRag] = useState<GraphRAGResult | null>(null);
  const [chainView, setChainView] = useState<ChainView>("cards");

  // Tracks the active chain request so stale responses from rapid selections are ignored.
  const chainCtrlRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setListLoading(true);
    setError("");
    fetch("/api/decisions", { signal: ctrl.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        if (r.status === 207) setError(data.message || "Warning: Partial success loading decisions.");
        return data;
      })
      .then((data) => {
        if (ctrl.signal.aborted) return;
        setDecisions(data);
        if (data.length > 0) void loadChain(data[0]);
      })
      .catch((e) => {
        if (e?.name !== "AbortError") {
          setError(e instanceof Error ? e.message : "Failed to load decisions.");
        }
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setListLoading(false);
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cancel any in-flight chain request when the workspace unmounts.
  useEffect(() => () => { chainCtrlRef.current?.abort(); }, []);

  async function loadChain(d: DecisionItem) {
    chainCtrlRef.current?.abort();
    const ctrl = new AbortController();
    chainCtrlRef.current = ctrl;

    setSelected(d);
    setChainLoading(true);
    setChain([]);
    setRag(null);
    setError("");
    try {
      const res = await fetch(`/api/decisions/${encodeURIComponent(d.decision_id)}/chain`, { signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (res.status === 207 && !ctrl.signal.aborted) {
        setError(data.message || "Warning: Partial success loading chain.");
      }
      if (!ctrl.signal.aborted) setChain(data.chain || []);
    } catch (e) {
      if (e instanceof Error && e.name !== "AbortError") {
        setError(e.message);
      }
    } finally {
      if (!ctrl.signal.aborted) setChainLoading(false);
    }
  }

  async function runGraphRAG(nextQuery = query) {
    const text = nextQuery.trim();
    if (!text || ragLoading) return;
    setQuery(text);
    setRagLoading(true);
    setError("");
    try {
      const res = await fetch("/api/decisions/graphrag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text, max_hops: 2, max_results: 12 }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }
      const listed = await fetch("/api/decisions").then((r) => r.json());
      setDecisions(listed);
      const recorded = listed.find((d: DecisionItem) => d.decision_id === data.decision_id);
      setSelected(recorded ?? { decision_id: data.decision_id, category: "graphrag_query", outcome: data.outcome, scenario: data.query, reasoning: data.response });
      setChain(data.chain || []);
      setRag(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "GraphRAG failed.");
    } finally {
      setRagLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const q = filter.toLowerCase().trim();
    if (!q) return decisions;
    return decisions.filter((d) =>
      d.decision_id.toLowerCase().includes(q) ||
      (d.category ?? "").toLowerCase().includes(q) ||
      (d.outcome ?? "").toLowerCase().includes(q)
    );
  }, [decisions, filter]);

  return (
    <div className="ws-page" style={{ flexDirection: "row" }}>
      {/* ── Sidebar list ── */}
      <div className="ws-sidebar" style={{ width: 340 }}>
        <div className="ws-sidebar-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <div style={{ width: 30, height: 30, borderRadius: 9, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", display: "grid", placeItems: "center", color: "var(--ws-accent)", flexShrink: 0 }}>
              <Scale size={15} />
            </div>
            <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>Decisions</div>
            {decisions.length > 0 && !listLoading && (
              <span className="ws-pill ws-pill--mono" style={{ marginLeft: "auto" }}>{decisions.length}</span>
            )}
          </div>
          <div style={{ position: "relative" }}>
            <Search size={12} color="var(--ws-text-dim)" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
            <input
              className="ws-input"
              type="text"
              placeholder="Filter by ID, category, outcome…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              style={{ paddingLeft: 30, fontSize: 12 }}
            />
          </div>
          <div className="ws-eyebrow" style={{ marginTop: 14, marginBottom: 8 }}>GraphRAG</div>
          <textarea
            className="ws-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="问一句，检索图上的证据链…"
            rows={3}
            style={{ fontSize: 12, resize: "vertical", minHeight: 68 }}
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
            {templateGroups.map((group) => (
              <div key={group.dim}>
                <div className="ws-eyebrow" style={{ marginBottom: 4 }}>{group.dim}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {group.items.map((item) => (
                    <button
                      key={item}
                      className="ws-btn ws-btn--ghost"
                      style={{ padding: "3px 8px", fontSize: 10, textAlign: "left" }}
                      onClick={() => setQuery(item)}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <button
            className="ws-btn ws-btn--primary"
            style={{ width: "100%", marginTop: 8, justifyContent: "center" }}
            disabled={ragLoading || !query.trim()}
            onClick={() => void runGraphRAG()}
          >
            {ragLoading ? "Retrieving…" : <><Play size={13} />Run GraphRAG</>}
          </button>
        </div>

        <div className="ws-sidebar-body">
          {listLoading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {[1,2,3,4,5].map((i) => <div key={i} className="ws-skeleton" style={{ height: 58 }} />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="ws-empty" style={{ padding: "28px 12px" }}>
              <div className="ws-empty-title">{decisions.length === 0 ? "No decisions" : "No matches"}</div>
              <div className="ws-empty-body">{decisions.length === 0 ? "No decisions available in the graph." : "Adjust your filter."}</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {filtered.map((d) => {
                const active = selected?.decision_id === d.decision_id;
                return (
                  <button
                    key={d.decision_id}
                    className={`ws-list-item${active ? " ws-list-item--active" : ""}`}
                    onClick={() => void loadChain(d)}
                  >
                    <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 5, color: active ? "#e8f6ff" : "var(--ws-text)" }}>
                      {d.scenario || d.decision_id}
                    </div>
                    {d.scenario ? (
                      <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--ws-text-dim)", marginBottom: 5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {d.decision_id}
                      </div>
                    ) : null}
                    <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                      {d.category && <span style={{ fontSize: 10, color: "var(--ws-text-dim)" }}>{d.category}</span>}
                      {d.outcome && <OutcomeBadge outcome={d.outcome} />}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Detail pane ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 60% 40% at 70% 20%, rgba(74,163,255,0.04), transparent 55%)", pointerEvents: "none" }} />

        {error ? (
          <div style={{ padding: 12, borderRadius: 14, color: "#ffb4c2", background: "rgba(255,157,175,0.1)", border: "1px solid rgba(255,157,175,0.18)", margin: "16px 16px 0 16px", zIndex: 2, position: "relative" }}>
            {error}
          </div>
        ) : null}

        {selected ? (
          <div className="ws-scroll ws-padded ws-animate-in" style={{ position: "relative", zIndex: 1 }}>
            {/* Decision header */}
            <div style={{ marginBottom: 28 }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
                <div>
                  <div className="ws-eyebrow" style={{ marginBottom: 6 }}>Decision Record</div>
                  <h2 className="ws-title">{selected.scenario || selected.decision_id}</h2>
                  {selected.scenario ? (
                    <div style={{ fontFamily: "monospace", fontSize: 11, color: "var(--ws-text-dim)", marginTop: 6 }}>{selected.decision_id}</div>
                  ) : null}
                </div>
                {selected.outcome && <OutcomeBadge outcome={selected.outcome} />}
              </div>
              {selected.category && (
                <span className="ws-pill ws-pill--mono">{selected.category}</span>
              )}
            </div>

            {(rag && rag.decision_id === selected.decision_id ? rag.response : selected.reasoning) ? (
              <div className="ws-card" style={{ padding: 22, marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                  <GitBranch size={14} color="var(--ws-accent)" />
                  <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>Retrieval evidence</div>
                  {rag && rag.decision_id === selected.decision_id ? (
                    <span className="ws-pill ws-pill--accent" style={{ marginLeft: "auto" }}>{rag.num_sources} sources</span>
                  ) : null}
                </div>
                {rag && rag.decision_id === selected.decision_id ? (
                  <GraphRAGStructured rag={rag} chain={chain} />
                ) : (
                  <GraphRAGMarkdown content={selected.reasoning || ""} />
                )}
              </div>
            ) : null}

            {/* Chain section */}
            <div className="ws-card" style={{ padding: 22 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
                <div style={{ width: 8, height: 8, borderRadius: 999, background: "linear-gradient(135deg, var(--ws-accent), var(--ws-amber))", boxShadow: "0 0 10px rgba(74,163,255,0.4)" }} />
                <div style={{ color: "var(--ws-text)", fontSize: 14, fontWeight: 700 }}>Causal Chain</div>
                {chain.length > 0 && !chainLoading && (
                  <span className="ws-pill ws-pill--accent">{chain.length} step{chain.length !== 1 ? "s" : ""}</span>
                )}
                <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                  <button
                    className={`ws-btn ${chainView === "cards" ? "ws-btn--primary" : "ws-btn--ghost"}`}
                    style={{ padding: "4px 10px", fontSize: 11 }}
                    onClick={() => setChainView("cards")}
                    type="button"
                  >
                    <Rows3 size={12} />卡片
                  </button>
                  <button
                    className={`ws-btn ${chainView === "orbit" ? "ws-btn--primary" : "ws-btn--ghost"}`}
                    style={{ padding: "4px 10px", fontSize: 11 }}
                    onClick={() => setChainView("orbit")}
                    type="button"
                  >
                    <Circle size={12} />圆形
                  </button>
                </div>
              </div>
              {chainView === "orbit" ? (
                <CausalOrbit chain={chain} loading={chainLoading} />
              ) : (
                <CausalFlow chain={chain} loading={chainLoading} />
              )}
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", position: "relative", zIndex: 1 }}>
            <div className="ws-empty">
              <div className="ws-empty-icon"><Scale size={32} /></div>
              <div className="ws-empty-title">No decision selected</div>
              <div className="ws-empty-body">Run GraphRAG on the left, or select a recorded decision to inspect its causal chain.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
