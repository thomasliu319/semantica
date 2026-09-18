# Tasks: IoT 时序数据处理

实现 [spec.md](./specs/iot-data-processing/spec.md)，列对照 [schemas.md](./schemas.md)。  
原始 JSON 只读。入口拟议 `datasets/process_iot_timeseries.py`，输出 `datasets/processed/iot_mar_aug_2026/`。

## 1. 输入与队列

- [ ] 1.1 复用 `datasets/fetch_iot_timeseries.py` 的 `device_gaps` / `MASTER_PATH`，列出磁盘完备设备（当前 199）
- [ ] 1.2 未完备设备只进 `dq_report.excluded_incomplete`，不读入清洗（当前 `172609583`）
- [ ] 1.3 忽略 `_complete/catalog.json`

## 2. 维度与快照

- [ ] 2.1 写 `device_dim.parquet`（身份键按文档；Excel 机型核对列；不含 Ip/SIM）
- [ ] 2.2 写 `spindle_asof.parquet`（`as_of`=拉取 Timestamp；不 join 到 device_day）
- [ ] 2.3 写 `customer_asof.parquet`（只留 188 台涉及的 CompanyId；丢掉合计行）
- [ ] 2.4 写 `customer_boot_window.parquet`（客户粒度；禁止 ÷ EquipCount）

## 3. device_day

- [ ] 3.1 从运行状态展开日历日；解析四桶秒与百分比（关机=`stop_time_*`）
- [ ] 3.2 丢掉 2026-03 全部日
- [ ] 3.3 丢掉整月 `sum(run_time_sec)=0` 的设备-月；月内零运行日保留
- [ ] 3.4 聚合当日报警条数、`IsShutdown=1` 条数、程序循环、进度产量/计划产量
- [ ] 3.5 校验四桶秒之和与 `total_time_sec`，差异进 dq
- [ ] 3.6 强制非空 `equip_type_code`；T-600 与 T-V856S 同一文件

## 4. 事件表

- [ ] 4.1 `alarm_event`：`EquipCode` 过滤；`duration_sec` 来自 DurationDetail；冲突置空留行
- [ ] 4.2 `program_cycle`：`EquipCode` 过滤；回填 `out_factory_code`；End&lt;Start 进 dq 仍可留行
- [ ] 4.3 `progress_day`：`EquipCode` 过滤；`stat_date=StatisticalDateStr`；保留班次与 PlanOutput
- [ ] 4.4 事件表同样丢掉 3 月；不因空运行月删除 4–8 月事件
- [ ] 4.5 不匹配身份的行写 `rejected/*.jsonl`

## 5. 报告与产物

- [ ] 5.1 写 `dq_report.json`：完备数、排除 12 台、dropped_march、dropped_idle_device_month、串机、时长冲突、四桶不平衡
- [ ] 5.2 parquet 无 `label`/`y`/`is_fault`/`split` 列；有 `company_id`
- [ ] 5.3 脚本 `--out` 默认为 `datasets/processed/iot_mar_aug_2026/`
- [ ] 5.4 不修改 `datasets/json/iot_timeseries/` 源 JSON（`_semantic/` 目录除外）
- [ ] 5.5 `dq_report.uncovered_signals` 至少包含：跟随误差、轴温、冷却液、液压、振动、保养台账、换刀事件
- [ ] 5.6 写出 `device_day.is_run_day`、`run_hours` 等 metrics.md 派生列；刷新 `_semantic/metric_catalog.json`

## 6. 测试

- [ ] 6.1 `tests/datasets/test_process_iot_timeseries.py`：三月过滤、空月过滤、串机丢弃、DurationDetail、StopTime 列名、无标签列
- [ ] 6.2 用 1–2 台夹具 JSON，不打真实 OpenAPI
