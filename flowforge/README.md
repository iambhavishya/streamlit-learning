# FlowForge

A local, browser based data preparation workflow app inspired by Alteryx. Upload CSV, Excel, or Parquet files; define reusable steps and branches; run the workflow; inspect every intermediate result; and export CSV or a workflow JSON file. Data stays in the local Streamlit process. This is an initial product, not full Alteryx parity.

## Run

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Upload a file, add an `input` step, and then add processing steps. Give each step a unique ID. Select its upstream input step(s) and paste its configuration JSON. The order of selected inputs matters for joins. Run the workflow, choose an output, and export its full CSV. Workflow JSON saves the graph and configurations; uploaded data files must be uploaded again when loading it.

## Configuration reference

| Operation | Inputs | Configuration JSON example |
|---|---:|---|
| input | 0 | `{"source":"orders.csv"}` (set from source selector) |
| select | 1 | `{"columns":["customer","amount"]}` |
| filter | 1 | `{"column":"amount","operator":">=","value":"100"}` |
| formula | 1 | `{"column":"amount","action":"multiply","target":"taxed","value":"1.18"}` |
| sort | 1 | `{"columns":["amount"],"ascending":false}` |
| sample | 1 | `{"rows":100}` |
| aggregate | 1 | `{"group_by":["customer"],"column":"amount","function":"sum"}` |
| join | 2 | `{"left_key":"customer_id","right_key":"id","how":"left"}` |
| union | 2 | `{}` |
| deduplicate | 1 | `{"columns":["customer_id"]}` |
| rename | 1 | `{"mapping":{"old_name":"new_name"}}` |

Filter operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`, `not contains`, `is null`, `is not null`. Formula actions: `uppercase`, `lowercase`, `trim`, `length`, `to number`, `fill null`, `multiply`, `add`. Aggregation functions follow pandas (`sum`, `mean`, `count`, `min`, `max`, etc.). Only use trusted workflow JSON; large uploads and joins can consume substantial local memory.

## Example workflow

Upload `orders.csv` with `customer,amount` columns. Save this as `workflow.json` and import it:

```json
[
  {"id":"orders","op":"input","inputs":[],"config":{"source":"orders.csv"}},
  {"id":"large","op":"filter","inputs":["orders"],"config":{"column":"amount","operator":">=","value":"100"}},
  {"id":"totals","op":"aggregate","inputs":["large"],"config":{"group_by":["customer"],"column":"amount","function":"sum"}}
]
```

## Current scope and next milestones

This app supports local tabular processing, branching, joins, intermediate previews, workflow JSON, and CSV export. A production equivalent would need a graphical canvas, database/cloud connectors, SQL pushdown, profiling, schedules, authentication, collaboration, audit logs, scalable execution, and more transformation tools. The engine is isolated in `engine.py` to support those additions.
