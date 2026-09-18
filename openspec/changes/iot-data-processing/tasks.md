# Tasks: IoT 时序数据处理

实现 [spec.md](./specs/iot-data-processing/spec.md)，列对照 [schemas.md](./schemas.md)，度量对照 [metrics.md](./metrics.md)。  
设计见 [design.md](./design.md)。入口 `datasets/process_iot_timeseries.py`，输出 `datasets/processed/iot_mar_aug_2026/`。

## 1. 输入与队列

- [x] 1.1 复用 `device_gaps` / `MASTER_PATH`，列出磁盘完备设备（199 台）
- [x] 1.2 `172609583` 只进 `dq_report.excluded_incomplete`，不读入清洗
- [x] 1.3 忽略 `_complete/catalog.json`，以磁盘完备为准

## 2. 维度与快照

- [x] 2.1 写 `device_dim.parquet`（身份键按文档；Excel 机型核对列；不含 Ip/SIM）
- [x] 2.2 写 `spindle_asof.parquet`（`as_of`=拉取 Timestamp；不 join 到 device_day）
- [x] 2.3 写 `customer_asof.parquet`（只留 199 台涉及的 CompanyId；丢掉合计行）
- [x] 2.4 写 `customer_boot_window.parquet`（客户粒度；禁止 ÷ EquipCount）

## 3. device_day

- [x] 3.1 从运行状态展开日历日；解析四桶秒与百分比（关机=`stop_time_*`）
- [x] 3.2 丢掉 2026-03 全部日
- [x] 3.3 丢掉整月 `sum(run_time_sec)=0` 的设备-月；月内零运行日保留
- [x] 3.4 聚合当日报警条数、停机报警条数、程序循环、进度产量/计划产量
- [x] 3.5 校验四桶秒之和与 `total_time_sec`，差异进 dq
- [x] 3.6 强制非空 `equip_type_code`；T-600 与 T-V856S 同一文件
- [x] 3.7 写出 `is_run_day`、`run_hours`、`month`、`company_id`

## 4. 事件表

- [x] 4.1 `alarm_event`：`EquipCode` 过滤；`duration_sec` 来自 DurationDetail；冲突置空留行
- [x] 4.2 `program_cycle`：`EquipCode` 过滤；回填 `out_factory_code`；End&lt;Start 进 dq 仍可留行
- [x] 4.3 `progress_day`：`EquipCode` 过滤；`stat_date=StatisticalDateStr`；保留班次与 PlanOutput；有计划才算达成率
- [x] 4.4 事件表丢掉 3 月；不因空运行月删除 4–8 月事件
- [x] 4.5 不匹配身份的行写 `rejected/*.jsonl`

## 5. 报告与产物

- [x] 5.1 写 `dq_report.json`：完备数、排除 1 台、dropped_march、dropped_idle_device_month、串机、时长冲突、四桶不平衡
- [x] 5.2 parquet 无 `label`/`y`/`is_fault`/`split` 列；有 `company_id`
- [x] 5.3 `--out` 默认为 `datasets/processed/iot_mar_aug_2026/`
- [x] 5.4 不修改 `datasets/json/iot_timeseries/` 源 JSON（`_semantic/` 除外）
- [x] 5.5 `uncovered_signals` 含：跟随误差、轴温、冷却液、液压、振动、保养台账、换刀事件
- [x] 5.6 刷新 `_semantic/metric_catalog.json`

## 6. 测试

- [x] 6.1 `tests/datasets/test_process_iot_timeseries.py`：三月过滤、空月过滤、串机丢弃、DurationDetail、StopTime 列名、无标签列
- [x] 6.2 用 1–2 台夹具 JSON，不打真实 OpenAPI
