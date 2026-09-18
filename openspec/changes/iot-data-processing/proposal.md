# Change: IoT 设备时序数据处理（前期）

状态：`spec-frozen`（B1–D5）+ **E1/E2 因信号清单重开**。已写入 [decisions.md](./decisions.md)，规格见 [specs/iot-data-processing/spec.md](./specs/iot-data-processing/spec.md)。实现任务见 [tasks.md](./tasks.md)。

对应导图：**数据挖掘 → 数据处理**（第二步）。  
范围只覆盖「理解数据 / 理解业务 / 清洗与预处理」。不做特征工程、不做模型。

## Why

结构化拉取已经完成 **188 / 200** 台（T-600 97、T-V856S 91），窗口 2026-03-01～08-31。  
原始 JSON 不能直接进特征或模型：粒度混杂、空字段多、部分接口会串机或串客户，3 月几乎全停。

导图对这一步的约束是：

- 先理解数据和业务，再洗。
- 清洗以纯净为先（「让数据纯 / 宁肯错杀」）：存疑记录宁可丢掉，不为凑样本留脏数据。

在业务 Y 和清洗门槛未拍板前写特征，会把停机、串机、客户合计、拉取时刻快照误当成设备历史。

## What Changes

字段级定义见 [schemas.md](./schemas.md)，对照 `提供给MES的接口(2026-08-18) .docx`。  
身份键按文档原义保留：`OutFactoryCode` 出厂编号、`EquipCode` 数控系统编码、`EquipName` 客户设备编码。  
状态词锁定：`RunTime` 运行、`StandbyTime` 待机、`StopTime` **关机**、`BreakDownTime` **故障**；`IdleCount` / `IsShutdown` 才是 **停机**，不能和关机互译。

| 表 | 粒度 | 主键 | 来源 | 角色 |
|---|---|---|---|---|
| `device_dim` | 设备 | `out_factory_code` | GetEquipInfoPageList | 维度 |
| `device_day` | 设备 × 日 | `out_factory_code, date` | GetEquipRunStatusList + 当日从表聚合 | 主事实 |
| `alarm_event` | 报警 | `alarm_id` | GetEquipAbnorPageList | 事件；`IsShutdown`=是否停机 |
| `program_cycle` | 程序段 | `program_id` | GetEquipProgramPageList | 循环次数/累计循环秒 |
| `progress_day` | 设备 × 日 × 程序 | `progress_id` | GetEquipProductionProgressPageList | 计划产量、班次、加工时长 |
| `spindle_asof` | 设备 × 拉取时刻 | `out_factory_code, as_of` | GetEquipSpindleWithFeedData | 快照，禁止当 3–8 月时序 |
| `customer_asof` | 客户 × 拉取时刻 | `company_id, as_of` | GetCustomerList | 近 30 天开机率/稼动率 |
| `customer_boot_window` | 客户 × 查询窗 | `company_id, start, end` | GetEquipBootOrRunningTimeList | 客户合计，禁止摊设备 |
| `dq_report` | 规则 | `rule_id` | — | 丢弃审计 |

`device_day` 四桶只保留文档时长：运行 / 待机 / 关机 / 故障（均解析 `*_sec` + 原文）。不发明「停机秒」。  
`progress_day` 事件日用 `StatisticalDateStr`；文档把 `CreateTime` 标成「报警时间」与实采不符，不当事件时间。班次 `ShiftStartTime/EndTime`、计划产量 `PlanOutput` 文档响应表不全，实采有则保留。

处理原则：

1. **只收 188 台完备设备**；12 台未完备默认不进清洗集。
2. **设备身份以 `GetEquipInfoPageList` 为准**，Excel 机型只做核对。
3. **程序 / 进度必须 `EquipCode` 精确匹配**；对不上的行丢弃。
4. **开机合计 `GetEquipBootOrRunningTimeList` 是客户级**，禁止下沉为设备特征。
5. **主轴 `GetEquipSpindleWithFeedData` 是拉取时刻快照**（约 2026-09-16），不是 3–8 月历史，禁止当时间序列。
6. **报警时长优先解析 `DurationDetail`**（持续时长详情）；文档 `Duration` 为秒但常为 0。`IsShutdown` 按文档映射停机 1/0。
7. **运行状态四桶按文档中文落地**：运行 / 待机 / 关机 / 故障；客户列表的停机台数不写进 `device_day`。
8. 存疑行写入 `rejected/` 并记原因，不静默填补。
9. PII 不进分析表：`Ip`、`SIMNo`、电话、地址。

## 已理解的数据（Grill 前冻结的事实）

来源：188 台完备目录 `datasets/json/iot_timeseries/<OutFactoryCode>/`，窗口 Mar–Aug 2026。

| 事实 | 数字 |
|---|---|
| 完备 / Excel | 188 / 200 |
| T-600 / T-V856S | 97 / 91 |
| 客户数 | 106（单客户最多 15 台，78 家只有 1 台） |
| 区域 | 华南 122、华东 54、西南 5、华中 3、华北 1、空 3 |
| 运行小时 | min 0、p50 180.6、p90 1143.9、max 2072.5；1 台全程 0 小时 |
| 3 月 `run_seconds=0` | **187 / 188** |
| 程序循环为 0 | 13 台 |
| 报警次数 | 全部 > 0；T-V856S 均值 1142，T-600 均值 138 |
| 日均利用率中位 | ~4% |

接口语义：

- 运行状态：按日 `currentDate` 拉满 184 天，不是区间查询。
- 程序：有 `StartTime/EndTime`，但接口会返回同客户其他设备，必须过滤。
- 进度：按 `StatisticalDate` + `ProgramCode` 的日产量。
- 报警：`CreateTime` 事件流；`AbnoCode` 大量为 `M01` / 类型「其它」；`StartTime` 常为空。
- 开机：`customerIdList` 客户合计（示例 `EquipCount=13`）。
- 主轴：实时快照，无历史。

`_complete/catalog.json` 仍是旧快照（103 台），**不能当清洗输入**；以磁盘完备判定为准。

## Non-goals

- 不等待剩余 12 台（除非 Grill 改口）。
- 不在本 change 做特征、标签、模型、UMAP、树模型。
- 不把 Explorer 图谱当分析表。
- 不编造 Excel 未给出的 `EquipCode`。
- 不把客户级开机时长摊到设备。

## Impact

- 新增：`openspec/changes/iot-data-processing/` 规格与后续清洗脚本、parquet/csv。
- 读取：`datasets/json/iot_timeseries/` 完备设备 JSON。
- 不改 OpenAPI 拉取协议；清洗发现截断再另开 fetch change。

## 退出条件

Grill-Me 已闭环（[decisions.md](./decisions.md)）。实现完成 [tasks.md](./tasks.md) 全部勾选后关闭本 change。
