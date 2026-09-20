# Change: 自然语言 → 图 schema → SPARQL（GraphRAG 可扩展）

状态：`spec-frozen`（B1–B5、D1–D4）。真源 [decisions.md](./decisions.md)，映射 [schemas.md](./schemas.md)。

## Why

现行 Decisions GraphRAG 是词法召回 + 无向 2 跳。机型×多月、设备×客户×区域这类**多表关联**扩不动：跳数不够，枢纽节点会灌水，缺月被静默丢掉。

Analyze 已有 compose API，SPARQL 工作区已有手写模板，两边没有从问句自动落到同一套 schema。

## What Changes

1. OpenSpec 目录：NL 短语 → 清洗表粒度 → 图类型/边 → SPARQL 模式。
2. 确定性编译器：问句编成一条 SELECT，在 Explorer 的 rdflib 投影上执行。
3. GraphRAG：能编译则 SPARQL 作取数与证据；不能编译才 2 跳。
4. 缺月 `declare_missing`；多指标 `all_mentioned`。

## Non-goals

- 不接图示中的 AI Gateway / FalkorDB / Milvus / Embedding / LLM Agent。
- 不在 GraphRAG 路径重跑 parquet，不发明 OEE / `is_fault`。
- 不把主轴快照或客户近 30 天稼动率当成 4–8 月切片。
