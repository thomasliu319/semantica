# nl2sparql-graphrag

## 编译

- SHALL 把可识别的度量/维度问句编译成只读 SPARQL SELECT。
- SHALL 在答案中同时给出关系映射（清洗表粒度）和 SPARQL 文本。
- SHALL NOT 对问句调用 LLM 生成 SPARQL（本 change）。
- SHALL NOT 把 GraphRAG 主路径建立在 hop>2 上。

## 对齐

- SHALL 对问句中每一个月份对齐一行；无节点则标明图上无切片，且不把该月计入合计。
- SHALL 对问句中每一个度量短语出一块答案，how 为 sum / ratio / each。

## 回退

- 目录无法选择 grain 时，SHALL 回退现有词法召回 + 2 跳，且不得假装已编译。

## 禁止

- SHALL NOT 用主轴快照或客户近 30 天稼动率填充缺失月。
- SHALL NOT 把关机与停机、运行占比与稼动率写成同一字段。
