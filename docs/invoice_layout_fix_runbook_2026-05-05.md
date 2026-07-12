# Invoice Layout Fix Runbook - 2026-05-05

## Goal

Make manual invoice output and BC direct-send invoice output use the same corrected GT layout:

- MTM Logix NIT visible and labeled.
- Customer NIT visible and labeled.
- Customer block wording corrected to `FACTURAR A`.
- No bank/payment footer.
- Manual PDF and automatic/direct-send PDF resolve to the same effective layout.

The expected layout behavior is defined in:

`config/invoice_layouts/gt.toml`

## Current State

The current observed layouts are not correct:

- Direct-send screenshot: missing customer NIT and shows `FACTRURA A`.
- Manual Jasper PDFs: customer NIT value exists, but is not labeled; bank/payment footer still prints.
- BC API `pdfDocument`: fails with `No payment information is provided in Company Information. Review the report.`

BC API credentials work, but the custom API pages from this repo are not currently published in production:

- `/api/mtmlogix/customerSync/v1.0/...` returns `404`.
- `/api/mtmlogix/layoutAudit/v1.0/...` returns `404`.

## What Can Be Uploaded to BC

`config/invoice_layouts/gt.toml` is not directly uploadable to Business Central. It is the local source-of-truth and validation file for what the invoice must look like.

Business Central needs two separate things:

1. A corrected report layout file:
   - Word layout: `.docx`
   - RDLC layout: `.rdlc`
   - Jasper/FEL provider layout, if the Guatemala localization renders invoices outside native BC layouts
2. Setup/routing changes in BC so manual print and direct-send/email use that same corrected layout.

In other words:

- Upload the corrected `.docx`, `.rdlc`, or Jasper layout in the BC/report layout tool.
- Select that same layout in `Report Selections - Sales`, customer-specific document layouts, and document sending profile setup.
- Use the TOML/PDF checker after export/render to confirm the uploaded layout is correct.

The TOML can become an automated upload payload only if a custom API accepts these settings and applies them to BC/report-layout tables. The current production tenant does not expose that custom API yet.

## Fix Sequence

### 1. Export the Effective Layouts

In Business Central, identify and export the layouts used by:

1. Manual invoice PDF generation.
2. Direct email/send invoice attachment.
3. Any customer-specific layout for `C00081`.

BC places to inspect:

- `Report Selections - Sales`
- `Report Layout Selection`
- `Customer Document Layouts` / customer-specific report selections
- `Document Sending Profiles`
- Customer card for `C00081`, field `Document Sending Profile`

If the direct-send layout differs from the manual layout, direct send is using the wrong layout and must be repointed after the template is corrected.

### 2. Correct the Template Content

Apply these changes to the invoice report/Jasper/RDLC/Word layout that should become the shared standard.

Customer block:

- Replace any `FACTRURA A` text with `FACTURAR A`.
- Add a customer NIT line formatted exactly as:

```text
NIT: {customer_nit}
```

For `C00081`, this must render:

```text
NIT: 108207552
```

Issuer/company block:

- Keep or add MTM Logix NIT line:

```text
NIT: 109582985
```

Payment/footer block:

- Remove the full bank/payment block from invoice output.
- The corrected output must not contain:

```text
Realizar pagos a la siguiente Cuenta
Banco:
Cuenta No.:
A nombre de:
```

For Jasper layouts, this usually means deleting the footer frame/static text fields or setting the payment footer `printWhenExpression` to `false`.

For RDLC/Word layouts, remove the payment footer controls and any expression that requires company payment information. This is also expected to eliminate the BC API PDF error about missing payment information.

Save/import the corrected template with a clear versioned name, for example:

`gt_invoice_standard_2026_05`

### 3. Route Manual and Direct Send to the Same Layout

In BC, set the effective invoice email attachment and manual print layout to the same corrected layout.

Global setup:

- In `Report Selections - Sales`, update invoice-related usage rows.
- The row used for email attachment must point to the corrected report/layout.
- `Use for Email Attachment` must be enabled only on the corrected invoice PDF layout.

Customer-specific setup:

- Check `C00081` customer-specific document layouts.
- If a customer-specific invoice layout exists, update it to the corrected layout or remove it so the global corrected layout applies.

Report layout selection:

- In `Report Layout Selection`, for company `MTM_GT_PROD`, set the selected layout for the invoice report ID to the corrected layout.

Document sending profile:

- Confirm the selected/default profile attaches a PDF.
- Confirm it does not select a separate report/layout that bypasses the corrected invoice layout.

### 4. Validate Before Sending to Customers

Generate both outputs for the same non-canceled invoice:

1. Manual PDF.
2. Direct-send/email attachment PDF.

Save both PDFs locally and run:

```bash
PYTHONPATH=. python3 scripts/check_invoice_pdf_layout.py \
  "PATH_TO_PDF.pdf" \
  --config config/invoice_layouts/gt.toml \
  --customer-number C00081
```

Both PDFs must pass.

Expected passing conditions:

- Contains `NIT: 109582985`.
- Contains `NIT: 108207552`.
- Contains `FACTURAR A`.
- Does not contain `FACTRURA`.
- Does not contain the bank/payment footer.

### 5. Optional API-Based Audit

After publishing extension version `0.1.1.0`, run:

```bash
PYTHONPATH=. python3 scripts/audit_bc_invoice_layouts.py \
  --config config/invoice_layouts/gt.toml \
  --customer-number C00081
```

This confirms which BC report selections, customer-specific report selections, report layout selections, report layouts, and document sending profile are effective.
