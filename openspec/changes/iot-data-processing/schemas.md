# 拟议产物字段（对照 MES 接口文档）

来源：`/Users/thomasliu/deviceData/提供给MES的接口(2026-08-18) .docx`（2026-08-18）。  
实采 JSON 多出来的列标「实采」；文档写了但语义不能当 3–8 月时序的标「禁止误用」。

## 身份键（全文统一，禁止改名）

文档把三套编码分得很清，清洗列必须原样保留：

| 字段 | 文档含义 | 不是 |
|---|---|---|
| `OutFactoryCode` | 出厂编号 | 客户现场编码 |
| `EquipCode` | 数控系统编码 | 出厂编号 |
| `EquipName` | 客户设备编码 | 机型名 |
| `EquipTypeCode` | 设备类型编码 | 设备显示名 |
| `EquipTypeName` | 设备名称（如立式加工中心 / 钻攻机） | 客户现场编码 |
| `CompanyId` | 客户 ID | 创世纪租户 ID |
| `GwCode` | 网关编码 | 出厂编号 |

主键默认：`OutFactoryCode`（Excel 清单键）。串机过滤键：`EquipCode`。

## 状态词（禁止混用）

客户列表 `GetCustomerList` 计的是**台数**；运行状态 `GetEquipRunStatusList` 计的是**单机单日时长**。文档用词不一致处以下表为准。

| 中文 | 客户列表（台） | 运行状态（时长） | 报警 |
|---|---|---|---|
| 故障 | `FaultCount` | `BreakDownTime` | `IsShutdown` 不是故障 |
| 加工 | `ProcessingCount` | `RunTime`（运行） | — |
| 停机 | `IdleCount` | **无对应时长桶** | `IsShutdown`：1 是 / 0 否 |
| 待机 | `StandbyCount` | `StandbyTime` | — |
| 关机 | `BoxDisconnectCount` | `StopTime` | — |

`StopTime` = **关机时间**，不是停机。`IdleCount` = **停机数量（台）**，不能和 `StopTime` 互译。

时长类字段文档给的是中文串（「1小时37分钟40秒」）。清洗一律同时保留原文，并解析 `*_sec` / `*_rate_pct`。

---

## 表一览

| 表 | 粒度 | 主键 | 接口 | 角色 |
|---|---|---|---|---|
| `device_dim` | 设备 | `out_factory_code` | GetEquipInfoPageList | 维度 |
| `device_day` | 设备 × 日 | `out_factory_code, date` | GetEquipRunStatusList | 主事实 |
| `alarm_event` | 报警 | `alarm_id` | GetEquipAbnorPageList | 事件 |
| `program_cycle` | 程序段 | `program_id` | GetEquipProgramPageList | 事件 |
| `progress_day` | 设备 × 日 × 程序 | `progress_id` | GetEquipProductionProgressPageList | 日产量 |
| `spindle_asof` | 设备 × 拉取时刻 | `out_factory_code, as_of` | GetEquipSpindleWithFeedData | 快照，禁止当历史 |
| `customer_asof` | 客户 × 拉取时刻 | `company_id, as_of` | GetCustomerList | 近 30 天快照 |
| `customer_boot_window` | 客户 × 查询窗 | `company_id, start, end` | GetEquipBootOrRunningTimeList | 客户合计，禁止摊设备 |
| `dq_report` | 规则 | `rule_id` | — | 丢弃审计 |

## 信号清单覆盖（对照五类）

| 类别 | 幻灯片信号 | 现采 | 结论 |
|---|---|---|---|
| CNC 运行 | 主轴负载、进给、转速、程序号、模式 | 负载/进给/转速仅 `spindle_asof`；程序号有 `program_cycle` 历史；模式≈运行四态 | 历史缺主轴；无独立「模式」字段 |
| 报警/事件 | 报警号、级别、持续时间 | 有代码、时长、是否停机；**级别 0%** | 无级别 |
| 轴/伺服 | 跟随误差、电流、温度 | 快照：XYZ 负载、电流；刀位 70%；跟随误差无字段；温度全空 | **无 4–8 月轴时序**（E1） |
| 环境/辅机 | 冷却液、液压、振动 | 无接口 | 记 uncovered |
| 维护记录 | 保养、换刀、维修 | 无 CMMS。报警几乎全「已解决」；ProcessDept=报警正文；刀位仅快照 | **无保养/换刀台账**（E2） |

派生指标与切片见 [metrics.md](./metrics.md)。

---

## `device_dim`

源：GetEquipInfoPageList。

| 清洗列 | 源字段 | 文档含义 | 规则 |
|---|---|---|---|
| `out_factory_code` | OutFactoryCode | 出厂编号 | 主键；与 Excel 出厂编码对齐 |
| `equip_code` | EquipCode | 数控系统编码 | 串机过滤键 |
| `equip_name` | EquipName | 客户设备编码 | 可空 |
| `equip_type_id` | EquipTypeId | 设备类型 Id | |
| `equip_type_code` | EquipTypeCode | 设备类型编码 | T-600 / T-V856S |
| `equip_type_name` | EquipTypeName | 设备名称 | 立式加工中心 / 钻攻机 |
| `gate_id` | GateId | 网关 Id | |
| `gw_code` | GwCode | 网关编码 | |
| `company_id` | CompanyId | 客户 ID | |
| `company_name` | CompanyName | 客户名称 | |
| `area_name` | AreaName | 区域 | 华南/华东/东北/华北/华中/西南/西北 |
| `out_factory_date` | OutFactoryDate | 设备出厂日期 | 常空 |
| `info_create_date` | CreateDate | 创建时间 | 台账创建，不是工况 |
| `excel_equip_type_code` | Excel 机型 | — | 核对用，冲突记 dq |
| `info_id` | Id | ID 主键 | |

不进本表：`Ip`、`SIMNo`。

---

## `device_day`

源：GetEquipRunStatusList（入参必填 `currentDate` = 统计日期）。  
文档时长全是中文串；实采已解析 `*Sec` / `*RatePct`。

| 清洗列 | 源字段 | 文档含义 | 规则 |
|---|---|---|---|
| `out_factory_code` | OutFactoryCode | 出厂编号 | 主键之一 |
| `date` | currentDate / 行内 date | 统计日期 | 主键之一；不是 StartTime/EndTime |
| `equip_code` | EquipCode | 数控系统编码 | |
| `equip_name` | EquipName | 客户设备编码 | |
| `equip_type_code` | EquipTypeCode | 设备类型编码 | |
| `equip_type_name` | EquipTypeName | 设备名称 | |
| `total_time_raw` | TotalTime | 总时间 | |
| `run_time_raw` | RunTime | 运行时间 | |
| `standby_time_raw` | StandbyTime | 待机时间 | |
| `stop_time_raw` | StopTime | **关机时间** | 不是停机 |
| `breakdown_time_raw` | BreakDownTime | **故障时间** | |
| `run_time_sec` | 解析 RunTime | 运行秒 | |
| `standby_time_sec` | 解析 StandbyTime | 待机秒 | |
| `stop_time_sec` | 解析 StopTime | 关机秒 | |
| `breakdown_time_sec` | 解析 BreakDownTime | 故障秒 | |
| `total_time_sec` | 解析 TotalTime | 总秒 | 与四桶之和核对，差记 dq |
| `run_time_rate_pct` | RunTimeRate | 运行时间百分比 | |
| `standby_time_rate_pct` | StandbyTimeRate | 待机时间百分比 | |
| `stop_time_rate_pct` | StopTimeRate | 关机时间百分比 | |
| `breakdown_time_rate_pct` | BreakDownTimeRate | 故障时间百分比 | |
| `alarm_count` | 当日报警聚合 | — | 从表 `alarm_event` |
| `alarm_shutdown_count` | IsShutdown=1 | 停机报警条数 | |
| `program_cycle_count` | Output 当日合计 | — | 从表 `program_cycle` |
| `program_seconds` | OutputSumSecond 当日 | — | |
| `progress_output` | Output 当日合计 | 累计循环次数 | 从表 `progress_day` |
| `progress_plan_output` | PlanOutput 当日合计 | 计划产量 | |
| `company_id` | 回填 dim | 客户 ID | 后续按客户切分 |
| `month` | 自 `date` | 自然月 | `YYYY-MM` |
| `is_run_day` | `run_time_sec > 0` | 有运行日 | 不是开机 |
| `run_hours` | `run_time_sec / 3600` | 运行小时 | |

四桶语义锁定：运行 / 待机 / 关机 / 故障。不发明「停机秒」。

---

## `alarm_event`

源：GetEquipAbnorPageList。  
请求文档另有 `IsShutdown`（是否停机：1 是 / 0 否）、`ProcessStatus`（未处理、已处理）。响应示例又写「已解决」——清洗保留原文，另映射标准枚举。

| 清洗列 | 源字段 | 文档含义 | 规则 |
|---|---|---|---|
| `alarm_id` | Id | ID 主键 | 主键 |
| `out_factory_code` | OutFactoryCode | 出厂编号 | 必须能对上 device_dim |
| `equip_code` | EquipCode | 数控系统编码 | 与身份不符 → rejected |
| `equip_name` | EquipName | 客户设备编码 | |
| `equip_type_code` | EquipTypeCode | 设备类型编码 | |
| `equip_type_name` | EquipTypeName | 设备名称 | |
| `abno_code` | AbnoCode | 报警代码 | |
| `abno_type_name` | AbnoTypeName | 报警类别名称 | |
| `abno_content` | AbnoContent | 报警内容 | |
| `create_time` | CreateTime | 报警时间 | 事件时间 |
| `duration_sec_api` | Duration | 持续时长(秒) | 常为 0 |
| `duration_detail` | DurationDetail | 持续时长详情(时分秒) | 优先解析 |
| `duration_sec` | 解析 DurationDetail | 持续秒 | 与 API 秒冲突则本字段空、记 dq |
| `is_shutdown` | IsShutdown | 是否停机 1/0 | 文档请求+响应；实采可能缺 |
| `process_status` | ProcessStatus | 报警状态 | 原文 |
| `is_concerned` | IsConcerned | 是否关注 1/0 | |
| `process_time` | ProcessTime | （实采）处理时间 | 文档响应表未列 |
| `level` | Level | 报警级别 | 常空 |

不进分析表：Reportor / ReportPhone / Repairtor / RepairPhone / Address / CompanyPhone。

---

## `program_cycle`

源：GetEquipProgramPageList。文档入参必填 `EquipName`（客户设备编码）；实采另过滤 `EquipCode`。

| 清洗列 | 源字段 | 文档含义 | 规则 |
|---|---|---|---|
| `program_id` | Id | ID 主键 | 主键 |
| `equip_code` | EquipCode | 数控系统编码 | 必须 = device_dim |
| `equip_name` | EquipName | 客户设备编码 | |
| `equip_type_code` | EquipTypeCode | 设备类型编码 | |
| `equip_type_name` | EquipTypeName | 设备名称 | |
| `out_factory_code` | 回填 dim | 出厂编号 | 接口行常无此字段 |
| `program_code` | ProgramCode | 加工程序名 | |
| `output` | Output | 累计循环次数 | |
| `output_sum_second` | OutputSumSecond | 累计循环时间（秒） | |
| `output_sum_raw` | OutputSum | 累计循环时间 | 中文串 |
| `avg_output_time_second` | AvgOutPutTimeSecond | 单次循环平均时长（秒） | |
| `avg_output_time_raw` | AvgOutPutTime | 单次循环平均时长 | |
| `start_time` | StartTime | 开始时间 | |
| `end_time` | EndTime | 结束时间 | 可早于 start，记 dq |

---

## `progress_day`

源：GetEquipProductionProgressPageList。粒度为统计日 + 程序，不是程序段。  
文档把 `CreateTime` 写成「报警时间」——与实采不符（实采是拉取时刻）。**事件日用 `StatisticalDateStr`。**

| 清洗列 | 源字段 | 文档含义 | 规则 |
|---|---|---|---|
| `progress_id` | EquipProgramOutPutInDayId | （实采）日产量主键 | 文档未列；有则用 |
| `out_factory_code` | OutFactoryCode | （实采）出厂编号 | 文档未列 |
| `equip_code` | EquipCode | 数控系统编码 | 必须匹配 |
| `equip_name` | EquipName | 客户设备编码 | |
| `equip_type_code` | EquipTypeCode | 设备类型编码 | |
| `equip_type_name` | EquipTypeName | 设备名称 | |
| `company_id` | CompanyId | 客户 ID | |
| `workshop_id` | WorkshopId | 车间 ID | 常空 |
| `program_code` | ProgramCode | 加工程序名 | |
| `stat_date` | StatisticalDateStr | 统计日期（字符串） | 粒度键 |
| `output` | Output | 累计循环次数 | |
| `plan_output` | PlanOutput | 计划产量 | |
| `avg_output_time_second` | AvgOutPutTimeSecond | 单次循环平均时长（秒） | |
| `output_sum_second` | OutputSumSecond | 累计循环时间（秒） | |
| `processing_time_sum_raw` | ProcessingTimeSum | 累计加工时间 | 中文串 |
| `processing_time_sum_sec` | 解析 | 累计加工秒 | |
| `avg_processing_time_raw` | AvgProcessingTime | 单次加工平均时长 | |
| `avg_processing_time_sec` | 解析 | 单次加工秒 | |
| `shift_start_time` | ShiftStartTime | （实采）班次开始 | 文档未列 |
| `shift_end_time` | ShiftEndTime | （实采）班次结束 | 文档未列 |
| `row_create_time` | CreateTime | 文档误标「报警时间」 | 只做拉取痕迹，不当事件时间 |

---

## `spindle_asof`（禁止当 3–8 月时序）

源：GetEquipSpindleWithFeedData。文档备注：OutFactoryCode / GwCode / EquipCode / EquipName 至少一个有值。无日期入参。

| 清洗列 | 源字段 | 文档含义 |
|---|---|---|
| `out_factory_code` | 查询键 | 出厂编号 |
| `equip_code` | EquipCode | 数控系统编码 |
| `as_of` | Timestamp | 响应时间（拉取时刻） |
| `x_ac` / `x_load` | XAC / XLoad | X 轴实际坐标 / 负载 |
| `y_ac` / `y_load` | YAC / YLoad | Y |
| `z_ac` / `z_load` | ZAC / ZLoad | Z |
| `a_ac` / `a_load` | AAC / ALoad | A |
| `c_ac` / `c_load` | CAC / CLoad | C |
| `main_arbor` | MainArbor | 主轴 |
| `speed` | Speed | 转速 |
| `speed_rate` | SpeedRate | 转速倍率 |
| `spindle_load` | Load | 主轴负载 |
| `feed` | Feed | 进给 |
| `feed_rate` | FeedRate | 进给倍率 |
| `program_name` | ProgramName | 加工程序名称 |
| `program_code` | ProgramCode | 程序号 |
| `knife_position` | KnifePosition | 当前刀位号 |
| `electricity` | Electricity | 电流 |
| `line_no` | LineNo | 当前行 |
| `program_ac` | ProgramAC | 程序坐标 |
| `program_order` | ProgramOrder | 顺序号 |
| `son_program_code` | SonProgramCode | 子程序号 |
| `gcode_content` | GcodeCoent | G 代码模块（文档拼写） |

`as_of` 约在 2026-09-16 拉取窗，不能 join 到 3–8 月 `device_day` 当工况。

---

## `customer_asof`

源：GetCustomerList。`BootRate` / `UtilRate` 文档为 **近 30 天开机率 / 稼动率**，不是 Mar–Aug 日序列。

| 清洗列 | 源字段 | 文档含义 |
|---|---|---|
| `company_id` | CustomerId | 客户 ID |
| `company_name` | CustomerName | 客户名称 |
| `en_code` | EnCode | 客户代码 |
| `area_name` | AreaName | 区域 |
| `fault_count` | FaultCount | 故障数量（台） |
| `processing_count` | ProcessingCount | 加工数量（台） |
| `idle_count` | IdleCount | **停机数量（台）** |
| `standby_count` | StandbyCount | 待机数量（台） |
| `box_disconnect_count` | BoxDisconnectCount | **关机数量（台）** |
| `total_equip_count` | TotalEquipCount | 设备总数量 |
| `boot_rate_30d` | BootRate | 近 30 天开机率 |
| `util_rate_30d` | UtilRate | 近 30 天稼动率 |
| `as_of` | Timestamp / fetched_at | 快照时刻 |
| `is_summary` | IsSummary | 汇总行；`true` 或名称=合计 → 丢弃 |

只保留完备设备涉及的 `CompanyId`。

---

## `customer_boot_window`

源：GetEquipBootOrRunningTimeList。粒度为客户，`EquipCount` 是该客户设备数。

| 清洗列 | 源字段 | 文档含义 | 规则 |
|---|---|---|---|
| `company_id` | CustomerId | 客户 ID | 主键之一 |
| `company_name` | CustomerName | 客户名称 | |
| `equip_count` | EquipCount | 设备数量 | ≥1；禁止 ÷ 到单台 |
| `total_running_time_sec` | TotalRunningTime | 运行总时间(秒) | 窗口合计 |
| `total_boot_time_sec` | TotalBootTime | 开机总时间(秒) | 窗口合计 |
| `start_time` / `end_time` | 查询窗 | 开始/结束时间 | |
| `as_of` | fetched_at | 拉取时刻 | |

`summary` 合计行丢弃。

---

## `dq_report`

每条规则：`rule_id, table, count, example_keys, note`。  
至少覆盖：身份冲突、EquipCode 串机、时长四桶之和 ≠ TotalTime、Duration vs DurationDetail 冲突、程序 End&lt;Start、进度 CreateTime 误当事件日、主轴/开机被误当下沉。
