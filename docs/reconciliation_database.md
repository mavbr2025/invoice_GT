# Reconciliation Review Database

This local SQLite database is a read-only extraction artifact for comparing Business Central invoices, Business Central invoice lines, ClickUp Revenue invoice tasks, and ClickUp shipment/Invoicing tasks.

Default database:

```bash
output/reconciliation_2026.sqlite3
```

Build or refresh the initial snapshot:

```bash
PYTHONPATH=. python3 -u scripts/build_reconciliation_database.py \
  --db output/reconciliation_2026.sqlite3 \
  --start-date 2026-01-01 \
  --market GT \
  --clickup-page-limit 5 \
  --bc-page-size 100
```

For a fuller ClickUp sweep, increase `--clickup-page-limit`. Use `--clickup-detail` only when attachment-level detail from every task is needed; it is much slower because it fetches each task one by one.

## Source Lists

- Shipment/Invoicing list: `152220606`
- ClickUp Revenue Guatemala invoice list: `901710831940`
- BC market profile: `GT`

## Tables

- `bc_invoices`: normalized posted sales invoice headers from Business Central.
- `bc_invoice_lines`: normalized posted sales invoice lines from Business Central.
- `clickup_tasks`: normalized ClickUp task headers from both source lists.
- `clickup_task_fields`: one row per ClickUp custom field value.
- `clickup_task_attachments`: task-level and custom-field attachment metadata when present in the source payload.
- `source_fields`: ClickUp custom field definitions for the loaded lists.
- `run_metadata`: extraction parameters.

Each main table keeps the source payload in `raw_json` so future reconciliation logic can recover fields that were not normalized yet.

## Review Views

- `review_bc_invoice_lines`: invoice headers joined to BC invoice lines.
- `review_clickup_charge_fields`: ClickUp fields likely related to charges, costs, invoices, storage, D&D, freight, VGM, or demurrage.
- `review_possible_invoice_task_matches`: first-pass candidate matches between BC invoices and ClickUp tasks using invoice number and external document/reference text.

Example queries:

```bash
sqlite3 -header -column output/reconciliation_2026.sqlite3 \
  "select * from review_bc_invoice_lines limit 20;"

sqlite3 -header -column output/reconciliation_2026.sqlite3 \
  "select * from review_clickup_charge_fields limit 50;"

sqlite3 -header -column output/reconciliation_2026.sqlite3 \
  "select bc_invoice_no, bc_customer_name, bc_reference, source_label, custom_id, clickup_task_name, match_score
   from review_possible_invoice_task_matches
   order by match_score desc
   limit 50;"
```

## Next Use

Use this database as the input for the translation-table analysis. The next step should compare:

- BC line descriptions and item/account numbers.
- ClickUp charge/cost custom fields.
- Customer, shipment reference, PO, BL/HBL/MBL, and invoice number.
- Cases where one ClickUp charge maps to multiple BC lines, or several ClickUp charges are grouped into one BC line.
