# Decisions

冻结时间：2026-09-19。来源：Grill-Me `grill.md` 推荐默认。  
本文件是规格真源。改口必须先改这里，再改 spec / 编译器。

| 题 | 选项 | 冻结含义 |
|---|---|---|
| B1 | `sparql_schema` | GraphRAG 主路径：NL → 目录 → SPARQL；未命中目录才回退 2 跳 |
| B2 | `stamped_slice` | 读 TypeMonth / EquipMonth / Area / Customer / Equip，不现扫 device_day |
| B3 | `declare_missing` | 问到的月都对齐；无切片标明，不编数、不用主轴快照补 |
| B4 | `all_mentioned` | 问句里每个指标都算；加总/重算比/分月列出按字段 how |
| B5 | `join_catalog` | 多表用目录 JOIN 写进一条 SPARQL，不靠加 hop |
| D1 | `relational_analog` | SQL 只作映射说明，执行 SPARQL |
| D2 | `compiler_only` | 本 change 无 LLM / Milvus / FalkorDB |
| D3 | `map_plus_sparql` | 答案里必须能看见映射表和 SPARQL |
| D4 | `reuse_iot` | 沿用 iot-data-processing 状态词与禁止项 |

补充：清洗窗口 2026-04～08。`172609583` 不进图。
