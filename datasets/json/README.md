# Demo graph JSON

Explorer-ready `ContextGraph` files collected from cookbooks, tests, and examples.

## Load in Explorer

```bash
conda activate semantica
export SEMANTICA_ALLOW_ANONYMOUS=true
semantica-explorer --graph datasets/json/lab_alpha.json
```

Open http://127.0.0.1:8000 then **Open Semantica Explorer**.

## Files

| File | Demo | Source |
|------|------|--------|
| `alice_bob_acme.json` | Smallest 4-node canvas | Explorer deterministic example |
| `apple_inc.json` | First knowledge graph | Cookbook 08 + `sample_document.txt` |
| `tech_corp.json` | Visualization notebook | Cookbook 16 / 03 |
| `lab_alpha.json` | Timeline + layout | Cookbook 03 temporal section |
| `startup_investment.json` | Temporal investment | Cookbook 02 analytics |
| `company_aliases.json` | Duplicate company names | Cookbook 18 dedup |
| `disease_network.json` | Healthcare network | Disease network cookbook test |
| `python_ecosystem.json` | Language / docs / PyPI | Cookbook 06 multi-source |
| `programming_stack.json` | Decisions + languages | Explorer API tests |
| `manufacturing_shopfloor.json` | Shop-floor ISA-95 | Manufacturing `seed.sql` |
| `device_iot_model.json` | 200 设备主数据 + MES 遥测/报警/程序 | `source/equip_master_200.json` + MES/PdM OpenAPI |
| `corporate_org.json` | Org chart | `corporate_ontology.ttl` |
| `catalog.json` | Index with node/edge counts | Generated |

Regenerate after editing `datasets/build_demo_graphs.py`:

```bash
python datasets/build_demo_graphs.py
```
