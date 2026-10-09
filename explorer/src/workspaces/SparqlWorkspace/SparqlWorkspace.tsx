import { useState, useRef } from "react";
import Editor, { useMonaco } from "@monaco-editor/react";
import { Play, Copy, Download, Table2, AlertCircle, FileCode2 } from "lucide-react";
import { readVersion } from "../OntologyWorkspace/ontologyUrlState";

const IOT_TEMPLATES: { label: string; query: string }[] = [
  {
    label: "NL编译：T-V856S 4/5/9月",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?slice ?type ?month ?hours ?days ?alarms
WHERE {
  ?slice a ent:TypeMonth ;
         prop:EquipTypeCode ?type ;
         prop:month ?month .
  OPTIONAL { ?slice prop:run_hours ?hours }
  OPTIONAL { ?slice prop:run_days ?days }
  OPTIONAL { ?slice prop:alarm_count ?alarms }
  OPTIONAL { ?slice prop:ofType ?etype }
  FILTER(LCASE(STR(?type)) IN ("t-v856s"))
  FILTER(?month IN ("2026-04", "2026-05", "2026-09"))
}
ORDER BY ?month`,
  },
  {
    label: "机型×月报警强度",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?type ?month ?hours ?alarms ?intensity ?stopShare ?monthShare
WHERE {
  ?slice a ent:TypeMonth ;
         prop:EquipTypeCode ?type ;
         prop:month ?month ;
         prop:run_hours ?hours ;
         prop:alarm_count ?alarms ;
         prop:alarm_per_run_hour ?intensity ;
         prop:stop_time_share ?stopShare ;
         prop:run_hours_share_of_month ?monthShare .
}
ORDER BY DESC(?intensity)`,
  },
  {
    label: "客户单台运行与报警强度",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?devices ?hoursPerDevice ?alarmPerHour
WHERE {
  ?c a ent:Customer ;
     rdfs:label ?label ;
     prop:devices ?devices ;
     prop:run_hours_per_device ?hoursPerDevice ;
     prop:alarm_per_run_hour ?alarmPerHour .
}
ORDER BY DESC(?alarmPerHour)
LIMIT 20`,
  },
  {
    label: "报警号停机占比",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?code ?alarms ?shutdownRate ?secPerEvent
WHERE {
  ?a a ent:AlarmCode ;
     rdfs:label ?code ;
     prop:alarm_count ?alarms ;
     prop:shutdown_alarm_rate ?shutdownRate ;
     prop:alarm_duration_per_event ?secPerEvent .
}
ORDER BY DESC(?alarms)`,
  },
  {
    label: "O0005 全部属性",
    query: `PREFIX prop: <http://semantica.local/prop/>
SELECT ?p ?o
WHERE {
  <http://semantica.local/entity/alarm:O0005> ?p ?o .
}`,
  },
  {
    label: "机型×月现算循环/报警",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?type ?month ?cyclesPerAlarm
WHERE {
  ?slice a ent:TypeMonth ;
         prop:EquipTypeCode ?type ;
         prop:month ?month ;
         prop:program_cycles ?cycles ;
         prop:alarm_count ?alarms .
  FILTER(?alarms > 0)
  BIND(?cycles / ?alarms AS ?cyclesPerAlarm)
}
ORDER BY DESC(?cyclesPerAlarm)`,
  },
  {
    label: "衍生指标目录",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?formula ?domain ?not
WHERE {
  ?m a ent:DerivedMetric ;
     rdfs:label ?label ;
     prop:formula ?formula ;
     prop:domain ?domain .
  OPTIONAL { ?m prop:not_label ?not }
}
LIMIT 30`,
  },
  {
    label: "机型×月运行小时",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?hours ?alarms
WHERE {
  ?slice a ent:TypeMonth ;
         rdfs:label ?label ;
         prop:run_hours ?hours ;
         prop:alarm_count ?alarms .
}
ORDER BY DESC(?hours)
LIMIT 20`,
  },
  {
    label: "已批准清洗决策",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?d ?label ?category ?outcome
WHERE {
  ?d a ent:decision ;
     rdfs:label ?label ;
     prop:category ?category ;
     prop:outcome ?outcome .
}
LIMIT 20`,
  },
  {
    label: "O0005 打在哪些设备",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?equip
WHERE {
  <http://semantica.local/entity/alarm:O0005> prop:raisedOnEquip ?equip .
}
LIMIT 20`,
  },
  { label: "All triples", query: "SELECT ?s ?p ?o\nWHERE {\n  ?s ?p ?o\n}\nLIMIT 20" },
  { label: "Node types", query: "SELECT ?type (COUNT(?s) AS ?count)\nWHERE {\n  ?s a ?type\n}\nGROUP BY ?type\nORDER BY DESC(?count)" },
];

const MARKETING_TEMPLATES: { label: string; query: string }[] = [
  // ── 达成分析（口径四要素：org_scope=in_scope + 预算覆盖机型 + 科室非空 + 万元）──
  {
    label: "达成率 · 管理出机（科室）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：分子=出货含税万元(in_scope+预算覆盖机型+科室非空)；分母=管理出机预算
SELECT ?deptLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
    }
    GROUP BY ?dept
  }
  {
    SELECT ?dept (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_ship_budget_hs ?b .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)
LIMIT 50`,
  },
  {
    label: "达成率 · 考核出机（科室）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：分子同管理出机（同一字段 TotalMoneyFC_HS），仅预算列不同
SELECT ?deptLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
    }
    GROUP BY ?dept
  }
  {
    SELECT ?dept (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:assessment_ship_budget_hs ?b .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)
LIMIT 50`,
  },
  {
    label: "达成率 · 管理签单（科室）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：分子=签单含税万元(不是不含税 TotalMoneyFc)；分母=管理签单预算
SELECT ?deptLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:SignOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
    }
    GROUP BY ?dept
  }
  {
    SELECT ?dept (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_signed_contract_hs ?b .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)
LIMIT 50`,
  },
  {
    label: "达成率 · 大区汇总（管理出机）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：科室→大区上卷(partOf)，分子/分母同口径分别上卷
SELECT ?areaLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?area (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
      ?dept prop:partOf ?area .
    }
    GROUP BY ?area
  }
  {
    SELECT ?area (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_ship_budget_hs ?b .
      ?dept prop:partOf ?area .
    }
    GROUP BY ?area
  }
  ?area rdfs:label ?areaLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)
LIMIT 20`,
  },
  {
    label: "达成率排名 · 科室（管理出机）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径同「达成率 · 管理出机」，按达成率降序即为排名（第一行=第1名）
SELECT ?deptLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
    }
    GROUP BY ?dept
  }
  {
    SELECT ?dept (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_ship_budget_hs ?b .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)`,
  },
  // ── 产品达成（产品投影，与科室投影互斥 B10；不要求科室非空）──
  {
    label: "产品达成 · 产品类型（管理出机）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：产品投影，分子=出货含税万元(in_scope+预算覆盖机型)；分母=产品预算(仅覆盖6类)
SELECT ?ptypeLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?ptype (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofType ?ptype .
    }
    GROUP BY ?ptype
  }
  {
    SELECT ?ptype (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:ProductBudgetMonth ;
              prop:budgetsFor ?ptype ;
              prop:management_ship_budget_hs ?b .
    }
    GROUP BY ?ptype
  }
  ?ptype rdfs:label ?ptypeLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)`,
  },
  // ── 人均效能（口径：in_scope，业务员 user_role=业务）──
  {
    label: "人均效能 · 科室人均出机金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 人均出机 = Σ出货含税万元 / nunique(业务员)，口径 in_scope + 业务员
SELECT ?deptLabel ?amountWan ?empCount (ROUND(?amountWan * 100 / ?empCount) / 100 AS ?perEmpWan)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?amountWan) (COUNT(DISTINCT ?emp) AS ?empCount)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:shippedBy ?emp .
      ?emp a ent:SalesPerson ; prop:user_role "业务" .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
}
ORDER BY DESC(?perEmpWan)
LIMIT 50`,
  },
  {
    label: "人均效能 · 科室人均签单金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 人均签单 = Σ签单含税万元 / nunique(业务员)，口径 in_scope + 业务员
SELECT ?deptLabel ?amountWan ?empCount (ROUND(?amountWan * 100 / ?empCount) / 100 AS ?perEmpWan)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?amountWan) (COUNT(DISTINCT ?emp) AS ?empCount)
    WHERE {
      ?s a ent:SignOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:signedBy ?emp .
      ?emp a ent:SalesPerson ; prop:user_role "业务" .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
}
ORDER BY DESC(?perEmpWan)
LIMIT 50`,
  },
  {
    label: "连续未达标 · 无签单业务员",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 业务口径：窗口内(user_role=业务)零签单人员，是「连续不签单」的基集
SELECT ?empLabel ?deptLabel
WHERE {
  ?emp a ent:SalesPerson ; prop:user_role "业务" ; rdfs:label ?empLabel .
  OPTIONAL { ?emp prop:belongsTo ?dept . ?dept rdfs:label ?deptLabel }
  FILTER NOT EXISTS { ?s a ent:SignOrderLine ; prop:signedBy ?emp . }
}
ORDER BY ?deptLabel ?empLabel
LIMIT 100`,
  },
  // ── 机型榜单 / 客户结构 ──
  {
    label: "机型榜单 · 立加签单 TOP10",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?modelLabel (SUM(?amount) AS ?signWan) (SUM(?fqty) AS ?units) (COUNT(?s) AS ?lines)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:fqty ?fqty ;
     prop:ofModel ?model .
  ?model rdfs:label ?modelLabel ; prop:zprod_type "立加" .
}
GROUP BY ?modelLabel
ORDER BY DESC(?signWan)
LIMIT 10`,
  },
  {
    label: "客户签单汇总（合同相对方）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?custLabel (SUM(?amount) AS ?total_wan)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:contractParty ?cust .
  ?cust rdfs:label ?custLabel .
}
GROUP BY ?custLabel
ORDER BY DESC(?total_wan)
LIMIT 30`,
  },
  {
    label: "客户集中度 · 签单 TOP10",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?custLabel ?custWan (ROUND(?custWan * 10000 / ?grandWan) / 100 AS ?sharePct)
WHERE {
  {
    SELECT ?cust ?custLabel (SUM(?amount) AS ?custWan)
    WHERE {
      ?s a ent:SignOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:contractParty ?cust .
      ?cust rdfs:label ?custLabel .
    }
    GROUP BY ?cust ?custLabel
  }
  {
    SELECT (SUM(?a) AS ?grandWan)
    WHERE { ?s a ent:SignOrderLine ; prop:org_scope "in_scope" ; prop:amount_wan ?a . }
  }
}
ORDER BY DESC(?custWan)
LIMIT 10`,
  },
  {
    label: "客户数量 · 签单/出机去重",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?signCustomers ?shipCustomers
WHERE {
  { SELECT (COUNT(DISTINCT ?sc) AS ?signCustomers) WHERE { ?s a ent:SignOrderLine ; prop:contractParty ?sc . } }
  { SELECT (COUNT(DISTINCT ?hc) AS ?shipCustomers) WHERE { ?h a ent:ShipOrderLine ; prop:shipTo ?hc . } }
}`,
  },
  // ── 趋势 / 目标进度 ──
  {
    label: "趋势 · 逐月管理出机金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?monthLabel (SUM(?amount) AS ?shipWan)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:ofDept ?dept ;
     prop:ofModel ?model ;
     prop:inMonth ?month .
  ?model a ent:Product ; prop:budget_covered true .
  ?month rdfs:label ?monthLabel .
}
GROUP BY ?monthLabel
ORDER BY ?monthLabel`,
  },
  {
    label: "目标进度 · 累计达成 vs 时间进度",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 序时进度：H1(1-6月)时间进度 = 6/12 = 50%；达成率高于 50% 即超额完成序时
SELECT ?deptLabel ?budgetWan ?actualWan
       (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
       (50.0 AS ?timeProgressPct)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
    }
    GROUP BY ?dept
  }
  {
    SELECT ?dept (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_ship_budget_hs ?b .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)
LIMIT 50`,
  },
  // ── 结构 / 明细 ──
  {
    label: "产品类型出货结构（预算覆盖口径）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 仅预算覆盖的6类机型（型材机/通用钻攻机/小五轴/龙门机/立加/卧加）
SELECT ?ptypeLabel (SUM(?amount) AS ?shipWan)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:ofModel ?model .
  ?model a ent:Product ; prop:budget_covered true ; prop:zprod_type ?ptypeLabel .
}
GROUP BY ?ptypeLabel
ORDER BY DESC(?shipWan)`,
  },
  {
    label: "机型签单占比结构",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?modelLabel ?ptypeLabel (SUM(?amount) AS ?signWan) (SUM(?fqty) AS ?units)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:fqty ?fqty ;
     prop:ofModel ?model .
  ?model rdfs:label ?modelLabel .
  OPTIONAL { ?model prop:categorizedAs ?ptype . ?ptype rdfs:label ?ptypeLabel }
}
GROUP BY ?modelLabel ?ptypeLabel
ORDER BY DESC(?signWan)
LIMIT 30`,
  },
  {
    label: "出货行明细（金额/口径/台量）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?s ?amount ?orgScope ?fqty
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:amount_wan ?amount ;
     prop:org_scope ?orgScope ;
     prop:fqty ?fqty .
}
ORDER BY DESC(?amount)
LIMIT 30`,
  },
  // ── 排名（大区/销售部/业务员，口径同达成分析）──
  {
    label: "排名 · 销售部管理签单达成率",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：签单含税万元(in_scope+预算覆盖机型+科室非空)，按科室 sales_dept 上卷
SELECT ?salesDept ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?sd (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:SignOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
      ?dept prop:sales_dept ?sd .
    }
    GROUP BY ?sd
  }
  {
    SELECT ?sd (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_signed_contract_hs ?b .
      ?dept prop:sales_dept ?sd .
    }
    GROUP BY ?sd
  }
  BIND(?sd AS ?salesDept)
  FILTER(?budgetWan > 0)
}
ORDER BY DESC(?achievePct)`,
  },
  {
    label: "排名 · 业务员签单金额 TOP20",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径：签单含税万元(in_scope)，按业务员聚合排序
SELECT ?empLabel ?deptLabel (SUM(?amount) AS ?signWan)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:signedBy ?emp .
  ?emp rdfs:label ?empLabel .
  OPTIONAL { ?emp prop:belongsTo ?dept . ?dept rdfs:label ?deptLabel }
}
GROUP BY ?empLabel ?deptLabel
ORDER BY DESC(?signWan)
LIMIT 20`,
  },
  {
    label: "排名 · 业务员出机金额 TOP20",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?empLabel ?deptLabel (SUM(?amount) AS ?shipWan)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:shippedBy ?emp .
  ?emp rdfs:label ?empLabel .
  OPTIONAL { ?emp prop:belongsTo ?dept . ?dept rdfs:label ?deptLabel }
}
GROUP BY ?empLabel ?deptLabel
ORDER BY DESC(?shipWan)
LIMIT 20`,
  },
  // ── 人均效能（台数维度）──
  {
    label: "人均效能 · 科室人均出机台数",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?deptLabel ?shipQty ?empCount (ROUND(?shipQty * 100 / ?empCount) / 100 AS ?perEmpQty)
WHERE {
  {
    SELECT ?dept (SUM(?fqty) AS ?shipQty) (COUNT(DISTINCT ?emp) AS ?empCount)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:fqty ?fqty ;
         prop:ofDept ?dept ;
         prop:shippedBy ?emp .
      ?emp a ent:SalesPerson ; prop:user_role "业务" .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
}
ORDER BY DESC(?perEmpQty)
LIMIT 40`,
  },
  {
    label: "人均效能 · 科室人均立加签单台数",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?deptLabel ?signQty ?empCount (ROUND(?signQty * 100 / ?empCount) / 100 AS ?perEmpQty)
WHERE {
  {
    SELECT ?dept (SUM(?fqty) AS ?signQty) (COUNT(DISTINCT ?emp) AS ?empCount)
    WHERE {
      ?s a ent:SignOrderLine ;
         prop:org_scope "in_scope" ;
         prop:fqty ?fqty ;
         prop:ofDept ?dept ;
         prop:ofModel ?model ;
         prop:signedBy ?emp .
      ?model prop:zprod_type "立加" .
      ?emp a ent:SalesPerson ; prop:user_role "业务" .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
}
ORDER BY DESC(?perEmpQty)
LIMIT 40`,
  },
  // ── 机型榜单 ──
  {
    label: "机型榜单 · 通用钻攻机签单 TOP10",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?modelLabel (SUM(?amount) AS ?signWan) (SUM(?fqty) AS ?units)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:fqty ?fqty ;
     prop:ofModel ?model .
  ?model rdfs:label ?modelLabel ; prop:zprod_type "通用钻攻机" .
}
GROUP BY ?modelLabel
ORDER BY DESC(?signWan)
LIMIT 10`,
  },
  // ── 连续未达标 ──
  {
    label: "连续未达标 · 无出机业务员",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?empLabel ?deptLabel
WHERE {
  ?emp a ent:SalesPerson ; prop:user_role "业务" ; rdfs:label ?empLabel .
  OPTIONAL { ?emp prop:belongsTo ?dept . ?dept rdfs:label ?deptLabel }
  FILTER NOT EXISTS { ?s a ent:ShipOrderLine ; prop:shippedBy ?emp . }
}
ORDER BY ?deptLabel ?empLabel
LIMIT 100`,
  },
  {
    label: "达成率低于80% · 科室清单（管理出机）",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 口径同「达成率 · 管理出机」，仅保留达成率 < 80% 的科室
SELECT ?deptLabel ?budgetWan ?actualWan (ROUND(?actualWan * 10000 / ?budgetWan) / 100 AS ?achievePct)
WHERE {
  {
    SELECT ?dept (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
    }
    GROUP BY ?dept
  }
  {
    SELECT ?dept (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_ship_budget_hs ?b .
    }
    GROUP BY ?dept
  }
  ?dept rdfs:label ?deptLabel .
  FILTER(?budgetWan > 0)
  FILTER(?actualWan * 10000 / ?budgetWan < 8000)
}
ORDER BY ?achievePct`,
  },
  // ── 趋势分析 ──
  {
    label: "趋势 · 逐月管理签单金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?monthLabel (SUM(?amount) AS ?signWan)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:ofDept ?dept ;
     prop:ofModel ?model ;
     prop:inMonth ?month .
  ?model a ent:Product ; prop:budget_covered true .
  ?month rdfs:label ?monthLabel .
}
GROUP BY ?monthLabel
ORDER BY ?monthLabel`,
  },
  // ── 退货分析（ftag=销售退货，负金额取绝对值）──
  {
    label: "退货分析 · 大区退货金额/台数",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?areaLabel (ABS(SUM(?amount)) AS ?returnWan) (ABS(SUM(?fqty)) AS ?returnQty)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:ftag "销售退货" ;
     prop:amount_wan ?amount ;
     prop:fqty ?fqty ;
     prop:ofDept ?dept .
  ?dept prop:partOf ?area .
  ?area rdfs:label ?areaLabel .
}
GROUP BY ?areaLabel
ORDER BY DESC(?returnWan)`,
  },
  {
    label: "退货分析 · 产品类型退货率",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 退货率 = |退货金额| / 出货金额
SELECT ?ptypeLabel ?returnWan ?shipWan (ROUND(?returnWan * 10000 / ?shipWan) / 100 AS ?returnRatePct)
WHERE {
  {
    SELECT ?ptype (ABS(SUM(?amount)) AS ?returnWan)
    WHERE { ?s a ent:ShipOrderLine ; prop:ftag "销售退货" ; prop:amount_wan ?amount ; prop:ofType ?ptype . }
    GROUP BY ?ptype
  }
  {
    SELECT ?ptype (SUM(?amount) AS ?shipWan)
    WHERE { ?s a ent:ShipOrderLine ; prop:org_scope "in_scope" ; prop:amount_wan ?amount ; prop:ofType ?ptype . }
    GROUP BY ?ptype
  }
  ?ptype rdfs:label ?ptypeLabel .
  FILTER(?shipWan > 0)
}
ORDER BY DESC(?returnRatePct)`,
  },
  // ── 订单量与单均 ──
  {
    label: "订单量与单均 · 大区签单订单数/单均",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 订单数=去重 docno（事件 label 即单据号）；单均=金额/订单数
SELECT ?areaLabel (COUNT(DISTINCT ?docno) AS ?orders) (SUM(?amount) AS ?signWan) (ROUND(SUM(?amount) * 100 / COUNT(DISTINCT ?docno)) / 100 AS ?avgWan)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:ofDept ?dept ;
     rdfs:label ?docno .
  ?dept prop:partOf ?area .
  ?area rdfs:label ?areaLabel .
}
GROUP BY ?areaLabel
ORDER BY DESC(?signWan)`,
  },
  // ── 客户分层 ──
  {
    label: "客户分层 · 立加出机台数分层签单结构",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 按客户累计立加出机台数分桶，再汇总签单金额（两侧均先聚合，避免笛卡尔）
SELECT ?bucket (SUM(?custWan) AS ?signAmountWan) (COUNT(DISTINCT ?cust) AS ?custCount)
WHERE {
  {
    SELECT ?cust (SUM(?fqty) AS ?shipQty)
    WHERE {
      ?s a ent:ShipOrderLine ; prop:shipTo ?cust ; prop:ofModel ?model ; prop:fqty ?fqty .
      ?model prop:zprod_type "立加" .
    }
    GROUP BY ?cust
  }
  {
    SELECT ?cust (SUM(?amount) AS ?custWan)
    WHERE { ?s2 a ent:SignOrderLine ; prop:contractParty ?cust ; prop:amount_wan ?amount . }
    GROUP BY ?cust
  }
  BIND(IF(?shipQty < 10, "1_<10台", IF(?shipQty < 20, "2_10-20台", "3_≥20台")) AS ?bucket)
}
GROUP BY ?bucket
ORDER BY ?bucket`,
  },
  // ── 订单结构 ──
  {
    label: "订单结构 · 订单类型签单分布",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?orderType (SUM(?amount) AS ?signWan) (SUM(?fqty) AS ?qty) (COUNT(?s) AS ?lines)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:order_type ?orderType ;
     prop:amount_wan ?amount ;
     prop:fqty ?fqty .
  FILTER(?orderType != "")
}
GROUP BY ?orderType
ORDER BY DESC(?signWan)`,
  },
  // ── 工厂维度 ──
  {
    label: "工厂维度 · 交货工厂出机分布",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?factory (SUM(?amount) AS ?shipWan) (SUM(?fqty) AS ?qty)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:factory ?factory ;
     prop:amount_wan ?amount ;
     prop:fqty ?fqty .
  FILTER(?factory != "")
}
GROUP BY ?factory
ORDER BY DESC(?shipWan)`,
  },
  // ── EHR 效能（职等）──
  {
    label: "EHR · 职等人均出机金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
SELECT ?grade (SUM(?amount) AS ?shipWan) (COUNT(DISTINCT ?emp) AS ?empCount) (ROUND(SUM(?amount) * 100 / COUNT(DISTINCT ?emp)) / 100 AS ?perEmpWan)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:shippedBy ?emp .
  ?emp a ent:SalesPerson ; prop:user_role "业务" ; prop:grade ?grade .
  FILTER(?grade != "")
}
GROUP BY ?grade
ORDER BY DESC(?shipWan)`,
  },
  // ── 人员流动 ──
  {
    label: "人员流动 · 科室在职/离职人数",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?deptLabel ?status (COUNT(?emp) AS ?empCount)
WHERE {
  ?emp a ent:SalesPerson ; prop:belongsTo ?dept ; prop:employment_status ?status .
  ?dept rdfs:label ?deptLabel .
}
GROUP BY ?deptLabel ?status
ORDER BY ?deptLabel ?status`,
  },
  // ── 预算精度 ──
  {
    label: "预算精度 · 大区预算偏差率",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# 偏差率 = (实际-预算)/预算，口径同管理出机
SELECT ?areaLabel ?budgetWan ?actualWan (ROUND((?actualWan - ?budgetWan) * 10000 / ?budgetWan) / 100 AS ?devPct)
WHERE {
  {
    SELECT ?area (SUM(?amount) AS ?actualWan)
    WHERE {
      ?s a ent:ShipOrderLine ;
         prop:org_scope "in_scope" ;
         prop:amount_wan ?amount ;
         prop:ofDept ?dept ;
         prop:ofModel ?model .
      ?model a ent:Product ; prop:budget_covered true .
      ?dept prop:partOf ?area .
    }
    GROUP BY ?area
  }
  {
    SELECT ?area (SUM(?b) AS ?budgetWan)
    WHERE {
      ?budget a ent:DeptBudgetMonth ;
              prop:budgetsFor ?dept ;
              prop:management_ship_budget_hs ?b .
      ?dept prop:partOf ?area .
    }
    GROUP BY ?area
  }
  ?area rdfs:label ?areaLabel .
  FILTER(?budgetWan > 0)
}
ORDER BY ?devPct`,
  },
  // ── 口径对比 ──
  {
    label: "口径对比 · 含3C vs 不含3C 出机金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?caliber (SUM(?amount) AS ?shipWan)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:ofType ?ptype .
  ?ptype rdfs:label ?ptypeLabel .
  BIND(IF(?ptypeLabel = "3C钻攻机", "含3C", "不含3C") AS ?caliber)
}
GROUP BY ?caliber
ORDER BY ?caliber`,
  },
  {
    label: "口径对比 · 含税 vs 不含税 签单金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?deptLabel (SUM(?hs) AS ?inclTaxWan) (SUM(?fc) AS ?exclTaxWan)
WHERE {
  ?s a ent:SignOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?hs ;
     prop:amount_fc_wan ?fc ;
     prop:ofDept ?dept .
  ?dept rdfs:label ?deptLabel .
}
GROUP BY ?deptLabel
ORDER BY DESC(?inclTaxWan)
LIMIT 30`,
  },
  // ── 人效趋势 ──
  {
    label: "人效趋势 · 月度人均出机金额",
    query: `PREFIX ent: <http://semantica.local/entity/>
PREFIX prop: <http://semantica.local/prop/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?monthLabel (SUM(?amount) AS ?shipWan) (COUNT(DISTINCT ?emp) AS ?empCount) (ROUND(SUM(?amount) * 100 / COUNT(DISTINCT ?emp)) / 100 AS ?perEmpWan)
WHERE {
  ?s a ent:ShipOrderLine ;
     prop:org_scope "in_scope" ;
     prop:amount_wan ?amount ;
     prop:shippedBy ?emp ;
     prop:inMonth ?month .
  ?emp a ent:SalesPerson ; prop:user_role "业务" .
  ?month rdfs:label ?monthLabel .
}
GROUP BY ?monthLabel
ORDER BY ?monthLabel`,
  },
  { label: "All triples", query: "SELECT ?s ?p ?o\nWHERE {\n  ?s ?p ?o\n}\nLIMIT 20" },
  { label: "Node types", query: "SELECT ?type (COUNT(?s) AS ?count)\nWHERE {\n  ?s a ?type\n}\nGROUP BY ?type\nORDER BY DESC(?count)" },
];

export function SparqlWorkspace() {
  const monaco = useMonaco();
  const editorRef = useRef<unknown>(null);
  const templates = readVersion() === "marketing" ? MARKETING_TEMPLATES : IOT_TEMPLATES;
  const [query, setQuery] = useState(templates[0].query);
  const [result, setResult] = useState<{ columns?: string[]; rows?: Record<string, string>[]; error?: string; error_line?: number } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copyState, setCopyState] = useState(false);

  function handleEditorWillMount(monacoIns: { languages: { getLanguages(): { id: string }[]; register(opts: { id: string }): void; setMonarchTokensProvider(id: string, p: unknown): void }; editor: { defineTheme(id: string, t: unknown): void } }) {
    if (!monacoIns.languages.getLanguages().some((l) => l.id === "sparql")) {
      monacoIns.languages.register({ id: "sparql" });
      monacoIns.languages.setMonarchTokensProvider("sparql", {
        keywords: ["SELECT", "WHERE", "LIMIT", "FILTER", "OPTIONAL", "PREFIX", "ORDER", "BY", "DESC", "ASC", "GROUP", "DISTINCT", "CONSTRUCT", "ASK", "DESCRIBE"],
        tokenizer: {
          root: [
            [/[a-zA-Z_]\w*/, { cases: { "@keywords": "keyword", "@default": "identifier" } }],
            [/[?$][a-zA-Z_]\w*/, "variable.name"],
            [/<[^>]+>/, "string.uri"],
            [/"[^"]*"/, "string"],
            [/#.*/, "comment"],
            [/[0-9]+(\.[0-9]+)?/, "number"],
          ],
        },
      });
      monacoIns.editor.defineTheme("sparql-dark", {
        base: "vs-dark",
        inherit: true,
        rules: [
          { token: "keyword", foreground: "58a6ff", fontStyle: "bold" },
          { token: "variable.name", foreground: "a5d6ff" },
          { token: "string.uri", foreground: "7ee787" },
          { token: "string", foreground: "a5d6ff" },
          { token: "comment", foreground: "4a6a85", fontStyle: "italic" },
          { token: "number", foreground: "f2b66d" },
        ],
        colors: {
          "editor.background": "#050c18",
          "editor.lineHighlightBackground": "#0a1628",
          "editorLineNumber.foreground": "#2a4060",
          "editorCursor.foreground": "#4aa3ff",
          "editor.selectionBackground": "#1e3a5a",
        },
      });
    }
  }

  function handleEditorDidMount(editor: unknown) {
    editorRef.current = editor;
  }

  async function handleRun() {
    setIsLoading(true);
    setResult(null);
    if (monaco && editorRef.current) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (monaco as any).editor.setModelMarkers((editorRef.current as any).getModel(), "sparql", []);
    }
    try {
      const res = await fetch("/api/sparql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.headers.get("content-type")?.includes("application/json")) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text.substring(0, 100)}`);
      }
      const data = await res.json();
      if (res.status === 207) {
        data.error = data.message || "Warning: Partial success running query.";
      }

      if (data.error && data.error_line && monaco && editorRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (monaco as any).editor.setModelMarkers((editorRef.current as any).getModel(), "sparql", [{
          startLineNumber: data.error_line,
          startColumn: data.error_column || 1,
          endLineNumber: data.error_line,
          endColumn: 100,
          message: data.error,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          severity: (monaco as any).MarkerSeverity.Error,
        }]);
      }
      setResult(data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Network error — could not reach the SPARQL endpoint.";
      setResult({ error: msg });
    } finally {
      setIsLoading(false);
    }
  }

  function handleCopyQuery() {
    navigator.clipboard.writeText(query).then(() => {
      setCopyState(true);
      setTimeout(() => setCopyState(false), 1500);
    }).catch(() => {
      // Clipboard API unavailable (insecure context or denied) — no-op; query is visible in editor
    });
  }

  function handleExportCSV() {
    if (!result?.rows || !result?.columns) return;
    const cols = result.columns;
    const header = cols.join(",");
    const rows = result.rows.map((r) => cols.map((c) => JSON.stringify(r[c] ?? "")).join(",")).join("\n");
    const blob = new Blob([`${header}\n${rows}`], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sparql_results.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="ws-page">
      <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
        {/* ── Toolbar ── */}
        <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--ws-border)", display: "flex", alignItems: "center", gap: 8, flexShrink: 0, background: "rgba(0,0,0,0.18)" }}>
          <div style={{ display: "flex", gap: 6, flex: 1, flexWrap: "wrap", maxHeight: 168, overflowY: "auto", alignContent: "flex-start" }}>
            <span className="ws-eyebrow" style={{ alignSelf: "center", marginRight: 4 }}>Templates:</span>
            {templates.map((t) => (
              <button
                key={t.label}
                className="ws-btn ws-btn--ghost"
                style={{ padding: "4px 10px", fontSize: 11 }}
                onClick={() => { setQuery(t.query); setResult(null); }}
              >
                {t.label}
              </button>
            ))}
          </div>
          <button className="ws-btn ws-btn--ghost" style={{ padding: "6px 10px" }} onClick={handleCopyQuery} title="Copy query">
            <Copy size={13} />{copyState ? "Copied!" : "Copy"}
          </button>
          <button
            className="ws-btn ws-btn--primary"
            onClick={handleRun}
            disabled={isLoading}
            style={{ minWidth: 110, justifyContent: "center" }}
          >
            {isLoading
              ? <><span className="ws-spin" style={{ display: "inline-block" }}><Play size={13} /></span>Running…</>
              : <><Play size={13} />Run Query</>}
          </button>
        </div>

        {/* ── Editor + Results split ── */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Editor */}
          <div style={{ flex: "0 0 55%", minHeight: 0, borderBottom: "1px solid var(--ws-border)", position: "relative" }}>
            <div style={{ position: "absolute", top: 8, right: 12, zIndex: 10, display: "flex", alignItems: "center", gap: 6 }}>
              <span className="ws-pill ws-pill--mono"><FileCode2 size={9} />SPARQL</span>
            </div>
            <Editor
              height="100%"
              defaultLanguage="sparql"
              theme="sparql-dark"
              value={query}
              onChange={(v) => setQuery(v || "")}
              beforeMount={handleEditorWillMount}
              onMount={handleEditorDidMount}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
                lineHeight: 22,
                padding: { top: 16 },
                scrollBeyondLastLine: false,
                renderLineHighlight: "gutter",
                wordWrap: "on",
              }}
            />
          </div>

          {/* Results */}
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden", background: "rgba(0,0,0,0.12)" }}>
            <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--ws-border)", display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--ws-text-muted)", fontSize: 13, fontWeight: 700 }}>
                <Table2 size={14} />
                Results
                {result?.rows && <span className="ws-pill ws-pill--accent">{result.rows.length} rows</span>}
              </div>
              {result?.rows && result.rows.length > 0 && (
                <button className="ws-btn ws-btn--ghost" style={{ marginLeft: "auto", padding: "4px 10px", fontSize: 11 }} onClick={handleExportCSV}>
                  <Download size={12} />Export CSV
                </button>
              )}
            </div>

            <div className="ws-scroll" style={{ flex: 1 }}>
              {isLoading && (
                <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 8 }}>
                  {[1, 2, 3].map((i) => <div key={i} className="ws-skeleton" style={{ height: 36 }} />)}
                </div>
              )}

              {result?.error && !isLoading && (
                <div className="ws-animate-in" style={{ margin: 16, display: "flex", gap: 10, padding: "12px 14px", borderRadius: "var(--ws-radius-sm)", background: "var(--ws-red-soft)", border: "1px solid rgba(255,123,114,0.28)", color: "#fca5a5", fontSize: 13 }}>
                  <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                  {result.error}
                </div>
              )}

              {result?.rows && result?.columns && !isLoading && (
                <div className="ws-animate-in" style={{ overflowX: "auto" }}>
                  {result.rows.length === 0 ? (
                    <div className="ws-empty">
                      <div className="ws-empty-title">No results</div>
                      <div className="ws-empty-body">The query returned 0 rows. Try a broader query or check your data.</div>
                    </div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, color: "var(--ws-text)" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--ws-border)", background: "rgba(0,0,0,0.2)" }}>
                          <th style={{ padding: "8px 14px", textAlign: "left", color: "var(--ws-text-dim)", fontFamily: "monospace", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", width: 40 }}>#</th>
                          {result.columns.map((c) => (
                            <th key={c} style={{ padding: "8px 14px", textAlign: "left", color: "var(--ws-text-muted)", fontFamily: "monospace", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em" }}>?{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.map((r, i) => (
                          <tr key={i} style={{ borderBottom: "1px solid rgba(74,163,255,0.06)" }}>
                            <td style={{ padding: "7px 14px", color: "var(--ws-text-dim)", fontFamily: "monospace", fontSize: 11 }}>{i + 1}</td>
                            {(result.columns ?? []).map((c) => (
                              <td key={c} style={{ padding: "7px 14px", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "monospace" }} title={String(r[c] ?? "")}>
                                {r[c] != null ? (
                                  String(r[c]).startsWith("urn:") || String(r[c]).startsWith("http")
                                    ? <span style={{ color: "#7ee787" }}>{String(r[c])}</span>
                                    : String(r[c])
                                ) : <span style={{ color: "var(--ws-text-dim)", fontStyle: "italic" }}>null</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {!result && !isLoading && (
                <div className="ws-empty">
                  <div className="ws-empty-icon"><Table2 size={28} /></div>
                  <div className="ws-empty-title">Run a query</div>
                  <div className="ws-empty-body">Write SPARQL above or pick a template, then click Run Query to see results here.</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
