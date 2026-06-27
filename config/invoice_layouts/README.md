# Invoice Layout Configs

These files define the expected invoice layout behavior before touching BC report selections or templates.

Current GT standard:

- Customer NIT must print as `NIT: {customer_nit}`.
- Customer block label must be `FACTURAR A`.
- Bank/payment footer must not print on invoice PDFs.
- Manual PDF output and BC direct-send output must resolve to the same effective layout.

Validate a PDF:

```bash
PYTHONPATH=. python3 scripts/check_invoice_pdf_layout.py \
  "tmp/pdfs/GTFVR0003684 COTTONTEXTILE _7680 04052026.pdf" \
  --config config/invoice_layouts/gt.toml \
  --customer-number C00081
```

Audit BC layout selection after the layout audit API is published:

```bash
PYTHONPATH=. python3 scripts/audit_bc_invoice_layouts.py \
  --config config/invoice_layouts/gt.toml \
  --customer-number C00081
```

