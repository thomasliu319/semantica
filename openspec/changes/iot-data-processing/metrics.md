# 完备设备语义指标层

窗口：**2026-04-01～08-31**（B5）。对象：磁盘完备 **199** 台（T-V856S 100、T-600 99）。  
`172609583` 无台账，不进本层。B1 仍有效：这里是**派生度量**，不是监督标签，不叫 OEE、不造 `is_fault`。

机读目录：`datasets/json/iot_timeseries/_semantic/metric_catalog.json`。

## 维度（谁 / 在哪 / 何时 / 做什么）

| 维度 | 键 | 业务语义 | 基数（199 台） | 注意 |
|---|---|---|---|---|
| 设备 | `out_factory_code` | 出厂编号，一台物理机 | 199 | Excel 清单键 |
| 数控系统 | `equip_code` | 系统侧编码 | ≈199 | 串机过滤 |
| 现场编码 | `equip_name` | 客户设备编码 | 可空 | 不是机型 |
| 机型 | `equip_type_code` | T-600 / T-V856S | 2 | 合表强制保留 |
| 设备名称 | `equip_type_name` | 钻攻机 / 立式加工中心 | 2 | 文档叫「设备名称」 |
| 客户 | `company_id` / `company_name` | 使用现场 | 108 | 后续切分按客户 |
| 区域 | `area_name` | 华南/华东/… | 6+空 | 空 9 台 |
| 日历日 | `date` | 统计日期 | 153 日 | 运行状态粒度 |
| 自然月 | `month` | 设备-月 | 5 | 空月可从 device_day 去掉 |
| 程序 | `program_code` | 加工程序名 | 见事件表 | |
| 报警代码 | `abno_code` | 报警号 | 主代码 O0005/O0006/M01/EMG | |
| 报警类别 | `abno_type_name` | 类别名称 | 油位过低占多数 | **与正文常不一致** |
| 是否停机报警 | `is_shutdown` | 该条报警是否停机 | 1/0 | 不是故障时长 |
| 班次 | `shift_start` / `shift_end` | 进度实采班次 | 部分行 | 文档未列 |
| 快照时刻 | `as_of` | 主轴拉取时间 | 1 次/台 | 禁止当下维历史 |

「设备库」7 台是客户名，不是仓库维度。

## 度量（按业务域）

### 1. CNC 运行 / 时间结构 — 粒度 `device × date`

文档四桶，禁止改名。占比优先用接口百分比；缺失时用秒/总秒。

| id | 中文名 | 公式 | 单位 | 不是 |
|---|---|---|---|---|
| `run_time_sec` | 运行时间 | `RunTime` 解析 | 秒 | 加工件数 |
| `standby_time_sec` | 待机时间 | `StandbyTime` | 秒 | 停机 |
| `stop_time_sec` | 关机时间 | `StopTime` | 秒 | 停机 |
| `breakdown_time_sec` | 故障时间 | `BreakDownTime` | 秒 | 停机报警条数 |
| `total_time_sec` | 总时间 | `TotalTime` | 秒 | |
| `run_time_rate_pct` | 运行时间占比 | `RunTimeRate` | % | 客户列表「近30天稼动率」 |
| `standby_time_rate_pct` | 待机时间占比 | `StandbyTimeRate` | % | |
| `stop_time_rate_pct` | 关机时间占比 | `StopTimeRate` | % | |
| `breakdown_time_rate_pct` | 故障时间占比 | `BreakDownTimeRate` | % | |
| `is_run_day` | 有运行日 | `run_time_sec > 0` | 0/1 | 开机 |
| `run_hours` | 运行小时 | `run_time_sec / 3600` | h | 可按设备/月/机型加总 |

199 台 4–8 月：运行 **76,800 h**；单台中位 180 h、中位有运行日仅 **21 / 153**。

### 2. 报警 / 事件 — 粒度 `alarm`，可滚到日/设备

| id | 中文名 | 公式 | 单位 | 语义陷阱 |
|---|---|---|---|---|
| `alarm_count` | 报警条数 | count | 条 | 含已解决 |
| `alarm_shutdown_count` | 停机报警条数 | `IsShutdown=1` | 条 | 不是故障秒 |
| `alarm_duration_sec` | 报警持续秒 | 解析 `DurationDetail` | 秒 | `Duration` 常为 0 |
| `alarm_code` | 报警号 | `AbnoCode` | — | |
| `alarm_type` | 报警类别 | `AbnoTypeName` | — | 「油位过低」88,062 条，正文常是 ATC/换刀 |
| `process_status` | 处理状态 | 原文 | — | 几乎全是「已解决」 |

4–8 月：**131,601** 条报警，其中停机报警 **114,805**（87%）。T-V856S 117,949 vs T-600 13,652。

### 3. 程序 / 产量 — 粒度程序段或日×程序

| id | 中文名 | 公式 | 单位 | 覆盖 |
|---|---|---|---|---|
| `program_cycles` | 累计循环次数 | `Output` | 次 | 程序+进度都有，含义接近但接口不同 |
| `program_seconds` | 累计循环时间 | `OutputSumSecond` | 秒 | |
| `avg_cycle_sec` | 单次循环平均时长 | `AvgOutPutTimeSecond` | 秒 | |
| `progress_output` | 日产量（循环次数） | 进度 `Output` | 次 | |
| `plan_output` | 计划产量 | `PlanOutput` | 件/次 | **仅 4 台有非空计划** |
| `plan_achievement_pct` | 计划达成率 | `output / plan_output` | % | 只在有计划的行算，禁止舰队平均 |
| `processing_time_sec` | 累计加工时间 | 解析 `ProcessingTimeSum` | 秒 | 进度表 |

4–8 月程序循环 **205,563**。计划达成不要当舰队 KPI。

### 4. 轴 / 伺服与维护 — 只作快照或缺口

| id | 中文名 | 粒度 | 状态 |
|---|---|---|---|
| `spindle_load` / `feed` / `speed` | 主轴负载 / 进给 / 转速 | `as_of` | 快照，E1 未答前不展开到日 |
| `axis_x_load` 等 | 轴负载 | `as_of` | 无跟随误差、温度全空 |
| `knife_position` | 当前刀位号 | `as_of` | 不是换刀事件 |
| （无） | 保养 / 换刀台账 | — | E2：无 CMMS |

## 推荐切片（语义查询）

1. 机型 × 月：运行小时、运行占比、报警条数、停机报警条数、循环次数  
2. 客户 × 设备：同厂多机对比（切分键 `company_id`）  
3. 设备 × 日：四桶结构（运行/待机/关机/故障）  
4. 报警号 × 机型：O0005 是否只打在立加  
5. 程序号 × 设备：换产/重复加工  

不要切片：把 `UtilRate`（客户近 30 天）和日 `run_time_rate_pct` 放在同一张趋势里。

## 衍生指标（基础度量自由组合）

Analyze 的 Metrics Composer 对清洗 parquet 按粒度加总后再做四则 / 份额。**除数为 0 → null**。不是 OEE，不造 `is_fault`。

| id | 公式 | 粒度特征 | 不是 |
|---|---|---|---|
| `alarm_per_run_hour` | `alarm_count / run_hours` | 机型×月：立加密度远高于钻攻 | 故障率 |
| `shutdown_alarm_rate` | `alarm_shutdown_count / alarm_count` | 报警号：停机报警占比 | 故障时长占比 |
| `run_hours_per_run_day` | `run_hours / run_days` | 设备：有运行日的强度 | 开机率 |
| `run_hours_per_device` | `run_hours / devices` | 客户 / 区域：单台水平 | 近30天稼动率 |
| `cycles_per_run_hour` | `program_cycles / run_hours` | 机型×月：加工节奏 | 计划达成率 |
| `seconds_per_cycle` | `program_seconds / program_cycles` | 程序号 | |
| `run_time_share` | `run_time_sec / total_time_sec` | 四桶结构 | 客户近30天稼动率 |
| `stop_time_share` | `stop_time_sec / total_time_sec` | 关机结构 | 停机 |
| `breakdown_time_share` | `breakdown_time_sec / total_time_sec` | 故障秒结构 | 停机报警占比 |
| `run_hours_share` | `run_hours / Σ run_hours` | 当前结果集内份额 | 稼动率 |
| `run_hours_mom` | `(h_t − h_{t−1}) / h_{t−1}` | 仅自然月 | 3 月已丢掉，4 月为 null |
| `run_hours_share_of_month` | 机型小时 / 当月总小时 | 仅机型×月 | |

自定义：任意两个已选基础指标做 `÷ × + −`，或对单个指标做份额。`plan_achievement_pct` 仍禁止舰队平均。

## 4–8 月实算摘要

| 切片 | 运行小时 | 报警 | 停机报警 | 循环次数 |
|---|---|---|---|---|
| T-V856S ×100 | 41,959 | 117,949 | 109,234 | 148,967 |
| T-600 ×99 | 34,841 | 13,652 | 5,571 | 56,596 |
| 华南 125 | 59,963 | 101,100 | — | — |
| 华东 54 | 12,526 | 20,455 | — | — |

月趋势：4 月运行 1,262 h（冷）；5–7 月约 1.1–1.3 万 h；**8 月 38,226 h**。报警 5–6 月最高（约 4.5–4.9 万），7 月掉到 2,074。
