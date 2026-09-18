# Decisions

冻结时间：2026-09-17。来源：Grill-Me canvas `grill-answers`。  
本文件是规格真源。改口必须先改这里，再改 spec。

| 题 | 选项 | 冻结含义 |
|---|---|---|
| B1 | `clean_only` | 本 change 不定监督 Y，不构造故障/OEE 标签 |
| B2 | `hybrid` | `device_day` 主表 + `alarm_event` / `program_cycle` / `progress_day` 从表 |
| B3 | `drop_idle_device_month` | `device_day` 丢掉整月 `run_time_sec` 合计为 0 的设备-月；台仍留在 `device_dim` |
| B4 | `pooled_flag` | 两机型一张表，必须保留 `equip_type_code` |
| B5 | `drop_mar` | 事实表/事件表日历从 **2026-04-01** 起，3 月进 `dq_report` 不当行 |
| D1 | `exclude` | 未完备不进清洗集（当前 `172609583`） |
| D2 | `lock` | 禁止客户开机合计摊设备；禁止主轴快照当 3–8 月时序；禁止未过滤 `EquipCode` 的程序/进度/报警 |
| D3 | `by_company` | 不产出 train/test 文件；`company_id` 必须保留，后续切分 SHALL 按客户 |
| D4 | `parquet` | `datasets/processed/iot_mar_aug_2026/*.parquet` + `dq_report.json` |
| D5 | `detail` | 报警持续秒解析 `DurationDetail`；与 `Duration` 冲突则清空该字段、保留行 |
| E1 | `snapshot_keep` | 轴/伺服只留 `spindle_asof`，禁止摊到 `device_day` |
| E2 | `uncover` | 无 CMMS；不把报警当保养/换刀台账 |

补充约束：canvas `grill-notes` 为空。周末、班次是否故障不在本 change 定义。

E1/E2 已按推荐默认冻结：轴/伺服只作快照，维护记缺口。环境/辅机同样 `uncover`。
