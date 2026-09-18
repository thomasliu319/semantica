# Spec: IoT 时序数据处理

状态：`frozen`（B1–D5）+ **E1/E2 重开**。见 [decisions.md](../../decisions.md)。列定义见 [schemas.md](../../schemas.md)。

## ADDED Requirements

### Requirement: 清洗输入集

系统 SHALL 只读取 Excel 200 台清单中通过 `device_gaps(days=184)` 的完备设备。完备定义：8 个接口 JSON + `meta.json` + `trend_summary.json`、身份行非空、运行状态 184 个 `ok` 日。  
系统 SHALL NOT 把未完备的 12 台写入任何事实表或维度表（D1）。  
系统 SHALL NOT 以 `_complete/catalog.json` 为输入；以磁盘完备判定为准。

#### Scenario: 完备设备进入清洗

- **WHEN** 设备目录 `device_gaps(days=184)` 为空
- **THEN** 该设备写入 `device_dim`

#### Scenario: 未完备设备排除

- **WHEN** 设备缺少程序/报警 JSON，或 `GetEquipInfoPageList.rows` 为空
- **THEN** 该设备不出现在 `device_dim` 或任何事实表，并在 `dq_report` 记 `excluded_incomplete`

### Requirement: 日历窗口

系统 SHALL 将事实表与事件表的业务日期限制为 **2026-04-01 至 2026-08-31**（B5）。  
系统 SHALL 把 2026-03 的运行日、报警、程序、进度计入 `dq_report`（`dropped_march`），SHALL NOT 写入对应 parquet。

#### Scenario: 三月运行日不进 device_day

- **WHEN** 运行状态行的 `date` 为 2026-03-01 至 2026-03-31
- **THEN** 该行不写入 `device_day`

### Requirement: 空运行设备-月

系统 SHALL 在 `device_day` 中丢弃整月 `sum(run_time_sec)=0` 的设备-月（B3）。  
该设备仍留在 `device_dim`。  
4–8 月事件表（报警/程序/进度）SHALL 仍按日历窗口保留，不因该月无运行而删除。

#### Scenario: 整月未运行

- **WHEN** 某设备在 2026-04 的所有 `device_day` 候选行 `run_time_sec` 均为 0
- **THEN** 该设备 4 月没有任何 `device_day` 行，并在 `dq_report` 记 `dropped_idle_device_month`

#### Scenario: 月内部分日未运行

- **WHEN** 某设备-月合计运行秒 > 0，且其中若干日 `run_time_sec=0`
- **THEN** 这些零运行日仍写入 `device_day`

### Requirement: 混合粒度产物

系统 SHALL 输出（B2、D4）：

- `device_dim`
- `device_day`
- `alarm_event`
- `program_cycle`
- `progress_day`
- `spindle_asof`
- `customer_asof`
- `customer_boot_window`
- `dq_report.json`

路径：`datasets/processed/iot_mar_aug_2026/`。表为 parquet（`dq_report` 为 JSON）。原始 JSON SHALL NOT 被修改。

#### Scenario: 运行状态对齐到日

- **WHEN** 完备设备有 4–8 月运行状态且该月非空运行
- **THEN** `device_day` 对该设备-月覆盖该月每一个日历日

### Requirement: 机型合表

系统 SHALL 将 T-600 与 T-V856S 写入同一套表（B4）。  
`device_dim` 与 `device_day` SHALL 包含 `equip_type_code`。  
系统 SHALL NOT 按机型拆成两套目录。

#### Scenario: 两机型同行

- **WHEN** 清洗输入同时含 T-600 与 T-V856S
- **THEN** `device_day` 中两机型行共存，且 `equip_type_code` 非空

### Requirement: 本步不造标签

系统 SHALL NOT 在本 change 构造监督标签、OEE 综合分、故障二分类或 train/test 划分文件（B1）。  
`device_dim` SHALL 保留 `company_id`。后续切分 SHALL 按客户，SHALL NOT 按设备随机（D3）。

#### Scenario: 无标签列

- **WHEN** 写出 `device_day.parquet`
- **THEN** 表中不存在 `label`、`y`、`is_fault`、`split` 列

### Requirement: 防串机与防串客户

系统 SHALL 仅保留 `EquipCode == device_dim.equip_code` 的程序、进度、报警行；其余写入 `rejected/` 并记 `equip_code_mismatch`。  
系统 SHALL NOT 把 `GetEquipBootOrRunningTimeList` 的客户合计摊到单台设备。  
系统 SHALL NOT 把 `GetEquipSpindleWithFeedData` join 到 4–8 月 `device_day` 当作工况。  
主轴只进 `spindle_asof`，带 `as_of`。

#### Scenario: 同客户程序串机

- **WHEN** 程序接口返回其他 `EquipCode` 的行
- **THEN** 这些行不进入 `program_cycle`

### Requirement: 状态词与时长

列名与 MES 文档对齐：`StopTime` SHALL 作为关机时间，SHALL NOT 当作停机。  
停机仅来自报警 `IsShutdown` 或客户列表 `IdleCount`。  
`device_day` 四桶 SHALL 为运行 / 待机 / 关机 / 故障，并同时保留中文原文与 `*_sec`。  
系统 SHALL NOT 发明「停机秒」列。

#### Scenario: 关机不是停机

- **WHEN** 运行状态 `StopTime` 非空
- **THEN** 写入 `stop_time_sec` / `stop_time_raw`，列名不含 idle/停机

### Requirement: 报警时长

系统 SHALL 用 `DurationDetail` 解析 `duration_sec`（D5）。  
当 `Duration`（秒）与解析结果冲突，系统 SHALL 将 `duration_sec` 置空、保留该行，并在 `dq_report` 记 `duration_conflict`。

#### Scenario: Duration 为 0 但详情非空

- **WHEN** `Duration=0` 且 `DurationDetail` 解析为 40 秒
- **THEN** `duration_sec=40`，行保留

#### Scenario: 秒与详情冲突

- **WHEN** `Duration=120` 且 `DurationDetail` 解析为 40 秒
- **THEN** `duration_sec` 为空，行仍在 `alarm_event`

### Requirement: 进度事件日

系统 SHALL 用 `StatisticalDateStr` 作为 `progress_day.stat_date`。  
系统 SHALL NOT 用进度 `CreateTime` 作为业务日期。  
实采班次 `ShiftStartTime` / `ShiftEndTime` 与 `PlanOutput` SHALL 保留。

#### Scenario: 拉取时刻不当事件日

- **WHEN** 进度行 `CreateTime` 为拉取日、`StatisticalDateStr` 为 2026-08-15
- **THEN** `stat_date=2026-08-15`

### Requirement: PII

系统 SHALL NOT 把 `Ip`、`SIMNo`、电话、地址写入分析 parquet。

### Requirement: 轴伺服与维护信号缺口

`[NEEDS CLARIFICATION: E1]` 轴/伺服：跟随误差无字段；XYZ 负载与电流仅存在于 `spindle_asof` 快照；温度全空。  
`[NEEDS CLARIFICATION: E2]` 维护：无保养/换刀/维修主数据。报警 `ProcessDept` SHALL NOT 当作部门（与 `AbnoContent` 重复）。  
在 E1/E2 作答前，系统 SHALL NOT 将主轴快照展开为 4–8 月轴时序，SHALL NOT 输出名为保养/换刀台账的表。

环境/辅机（冷却液、液压、振动）当前无接口，SHALL 记入 `dq_report.uncovered_signals`。

### Requirement: 语义度量层

系统 SHALL 按 [metrics.md](../../metrics.md) 为完备设备提供派生度量，且 SHALL NOT 把它们写成监督标签或 OEE 综合分。  
系统 SHALL 使用文档状态词：运行时间占比不是客户「近30天稼动率」；关机不是停机；计划达成率 SHALL 仅在 `plan_output` 非空的行计算。  
系统 SHALL 写出 `datasets/json/iot_timeseries/_semantic/metric_catalog.json`。
