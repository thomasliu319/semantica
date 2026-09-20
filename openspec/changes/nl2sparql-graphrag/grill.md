# Grill-Me：自然语言 → 图 schema → SPARQL

OpenSpec 规则：B 组阻塞。每题只许一个主选项；选「其他」必须补一句。  
本 change 解决 GraphRAG「只靠词法召回 + 2 跳」扩不动多表关联。

导图锚点：问句 → 清洗表粒度 → 图节点/边 → SPARQL（关系计划的可执行形）。  
图上的「SQL」是**关系映射**，落地查询是 SPARQL，不是再跑一遍 parquet。

---

## B. 阻塞题

### B1. GraphRAG 扩图的真源？

| 选项 | 含义 | 若选错 |
|---|---|---|
| `hop2` | 词法种子 + 无向 2 跳 | 机型×多月、设备×客户×区域 associ 会被邻居淹没或截断 |
| `llm_freeform` | LLM 直接写 SPARQL | 不可重复，关机/停机/稼动率语义会漂 |
| `vector_milvus` | 向量召回当主路径 | 本仓库还没有 Milvus 运行时；图示是后续 |
| `sparql_schema` | OpenSpec 目录把 NL 编成 SPARQL，结果当证据 | 目录未覆盖的问句仍要回退 |

推荐默认：`sparql_schema`。FalkorDB / Milvus / Embedding / LLM Agent 只记 non-goal。

### B2. 问句落到哪一层粒度？

| 选项 | 对齐 | 不适合 |
|---|---|---|
| `device_day` | 日事实 | 用户说「4 月、5 月」要对齐月切片 |
| `stamped_slice` | 已盖戳的 TypeMonth / EquipMonth / Area / Customer | 日级明细不在 Explorer 图上 |
| `always_join_raw` | 每次从 device_day 现算 | 图里没有日节点；会绕开 Analyze compose |

推荐默认：`stamped_slice`。日表语义仍写在映射里（`device_day GROUP BY`），查询读切片。

### B3. 问到了图上没有的月（如 2026-09）？

| 选项 | 含义 |
|---|---|
| `drop_silent` | SPARQL 没行就当没问 |
| `declare_missing` | 对齐问到的月，缺月写「图上无切片」，不编数 |
| `invent` | 用邻月或窗口外快照补 |

推荐默认：`declare_missing`。窗口仍是 B5：4–8 月。主轴快照禁止当 9 月时序。

### B4. 一句里多个指标？

| 选项 | 含义 |
|---|---|
| `first_only` | 只算第一个短语 |
| `all_mentioned` | 按出现顺序，各按字段语义（可加总 / 重算比 / 分月列出） |
| `llm_pick` | 模型猜用户更关心哪个 |

推荐默认：`all_mentioned`。运行小时、运行天数可加总；报警强度用 Σ报警/Σ小时；设备数不跨月加总。

### B5. 多表关联怎么扩？

| 选项 | 含义 |
|---|---|
| `more_hops` | 把 hop 加到 3–4 | 枢纽 `dataset:cleaned` 会灌水 |
| `join_catalog` | 粒度决定 JOIN：`ofType` / `ofEquip` / `locatedIn` / `ownedBy`，写进同一条 SPARQL |
| `n_queries` | 每张表一条 SPARQL 再在内存拼 |

推荐默认：`join_catalog`。一条计划、一条 SPARQL，边在目录里声明，新表加一行就能扩。

---

## D. 可默认题

### D1. 「schema SQL 映射」指什么？

推荐：`relational_analog`。目录同时写清洗 SQL 形（`device_day ⋈ device_dim GROUP BY`）和 SPARQL 形。执行只跑 SPARQL。

### D2. 本步要不要 LLM？

推荐：`compiler_only`。确定性编译；图示里的 LLM / Agent 下一 change。

### D3. 证据链展示什么？

推荐：`map_plus_sparql`。模式映射表 + 编译出的 SPARQL + 绑定行；2 跳只作未编译问句的回退。

### D4. 状态词？

推荐：沿用 iot-data-processing。关机 ≠ 停机；运行占比 ≠ 客户近 30 天稼动率；计划达成率不得舰队平均。

---

## 答完之后

1. 写入 [decisions.md](./decisions.md)。
2. 映射真源：[schemas.md](./schemas.md)。
3. spec SHALL + 编译器 + GraphRAG 接 SPARQL。
