# NL → 关系映射 → 图 → SPARQL

执行层只跑 SPARQL。SQL 列是清洗语义的对照，不是第二套引擎。

PREFIX：`ent: <http://semantica.local/entity/>`，`prop: <http://semantica.local/prop/>`。  
边投影为 `prop:<edgeType>`（`ofType` / `ofEquip` / `locatedIn` / `ownedBy`）。

## 粒度（问句怎么选 grain）

| 问句信号 | grain | 清洗表（SQL 形） | 图类型 | 默认 JOIN |
|---|---|---|---|---|
| 机型码 + 月 | `type_month` | `device_day ⋈ device_dim GROUP BY equip_type_code, month` | `TypeMonth` | `ofType → EquipType` |
| 出厂编号 + 月 | `equip_month` | `device_day GROUP BY out_factory_code, month` | `EquipMonth` | `ofEquip → Equip`；`ofType`；`Equip-locatedIn→Area`；`Equip-ownedBy→Customer` |
| 区域名 | `area` | `device_dim` 区域聚合 | `Area` | `locatedIn`（回退扩邻居） |
| 客户名 | `customer` | `device_dim` 客户聚合 | `Customer` | `ownedBy` |
| 仅出厂编号 | `equip` | `device_dim` | `Equip` | `locatedIn` / `ownedBy` |

机型优先于设备月：问 `T-V856S 2026年4月` 落 `type_month`，不扫全部 EquipMonth。

## 度量短语 → 字段 → how

| 自然语言 | 字段 | SPARQL 变量 | how | 不是 |
|---|---|---|---|---|
| 运行时间 / 运行小时 / 运行时长 | `run_hours` | `?hours` | `sum` | 客户近 30 天稼动率 |
| 运行天数 / 运行日 | `run_days` | `?days` | `sum` | 日历天数 |
| 报警强度 | `alarm_count / run_hours` | `?alarms` `?hours` | `ratio` | 单月强度再平均 |
| 设备台数 / 设备数 / 台数 / 设备分布 | `devices` | `?devices` | `each` | 跨月 SUM；机型×月是当月 nunique |

运行时真源：`semantica/explorer/nl_metric_schema.json`。问句命中 `phrases` 即绑定 `field` / `prop` / SPARQL 变量；编译器对目录里每个 stored measure 自动加 `OPTIONAL`。新指标只改该 JSON。

## 多表 SPARQL 骨架

`type_month`：

```sparql
SELECT ?slice ?type ?month ?hours ?days ?alarms
WHERE {
  ?slice a ent:TypeMonth ;
         prop:EquipTypeCode ?type ;
         prop:month ?month .
  OPTIONAL { ?slice prop:run_hours ?hours }
  OPTIONAL { ?slice prop:run_days ?days }
  OPTIONAL { ?slice prop:alarm_count ?alarms }
  OPTIONAL { ?slice prop:ofType ?etype }
  FILTER(LCASE(STR(?type)) = "t-v856s")
  FILTER(?month IN ("2026-04", "2026-05", "2026-09"))
}
```

`equip_month`（设备 × 月 × 客户 × 区域）：

```sparql
SELECT ?em ?code ?month ?hours ?days ?type ?area ?customer
WHERE {
  ?em a ent:EquipMonth ;
      prop:month ?month .
  OPTIONAL { ?em prop:OutFactoryCode ?code }
  OPTIONAL { ?em prop:run_hours ?hours }
  OPTIONAL { ?em prop:run_days ?days }
  OPTIONAL { ?em prop:EquipTypeCode ?type }
  OPTIONAL {
    ?em prop:ofEquip ?eq .
    OPTIONAL { ?eq prop:locatedIn ?ar . ?ar rdfs:label ?area }
    OPTIONAL { ?eq prop:ownedBy ?cu . ?cu rdfs:label ?customer }
  }
}
```

FILTER 只绑定问句里出现的维度。IN 列表 = 抽出的全部月份（含区间展开）。

## 扩展新关联

1. `schemas.md` 加 grain 或 JOIN。
2. 编译器 `GRAINS` 加同一行。
3. 图上要有对应边（`build_demo_graphs` 已盖戳的才查得到）。

不靠把 `max_hops` 调大。
