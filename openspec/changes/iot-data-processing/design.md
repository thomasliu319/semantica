# Design: IoT 时序清洗

入口 `datasets/process_iot_timeseries.py`。原始 JSON 只读（`_semantic/metric_catalog.json` 除外）。产物 `datasets/processed/iot_mar_aug_2026/`。

## 流水线

```
Excel 200 台 master
        │
        ├─ device_gaps(days=184) 空 → 完备队列（199）
        └─ 有缺口 → dq_report.excluded_incomplete（172609583）
                        │
        GetEquipInfoPageList → device_dim（Excel 机型核对列）
                        │
        ┌───────────────┼────────────────┐
        │               │                │
  RunStatus        事件三表           快照
  展开日历日      EquipCode 精确匹配   spindle_asof
  丢 3 月         丢 3 月             customer_asof
  丢空运行月      冲突字段置空留行     customer_boot_window
        │               │                │
        └────── 当日聚合 ─┘                │
                        │                │
                   parquet + rejected/ + dq_report.json
```

## 粒度

| 表 | 何时丢行 | 何时留行 |
|---|---|---|
| `device_dim` | 未完备 | 完备即可，即使 4–8 月全空运行 |
| `device_day` | 3 月；整月 `sum(run_time_sec)=0` | 有运行月里的零运行日 |
| 事件三表 | 3 月；`EquipCode` 不符 | 空运行月里的 4–8 月事件 |
| `spindle_asof` | 无 ResultData | 有快照即写；禁止 join 日表 |
| 客户两表 | 合计行；非 199 台涉及的客户 | 客户粒度，禁止 ÷ EquipCount |

## 时长

- 运行状态：优先 `*Sec` / `*RatePct`，否则解析中文串。四桶之和 ≠ `total_time_sec` 进 dq，行仍留。
- 报警：优先 `DurationDetail`；`Duration=0` 且详情非空用详情；两边都 >0 且不等则 `duration_sec` 置空。
- 列名锁定：`StopTime` → `stop_time_*`（关机）。不发明停机秒。

## 非目标

不写 `label` / `y` / `is_fault` / `split`；不输出保养/换刀台账；不把主轴快照摊到 4–8 月。
