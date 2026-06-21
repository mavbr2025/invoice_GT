# Special Invoice Requirements

This file records invoice behaviors that are approved for manual handling but are not yet part of the standard ClickUp webhook automation.

## GT INT Two-Step Invoice Special Request

Schema: `config/special_invoice_requirements/gt_int_two_step_special_request.json`

Manual tool: `scripts/replace_gt_invoice_split_int_charges_once.py`

Status: `manual_special_request_only`

Automation status: not automated. Do not call this flow from the ClickUp webhook, a scheduled job, or a generic invoice endpoint until the business rule is approved and converted into a normal product requirement.

### Business Rule

For customer-specific exceptions, the INT side of a Guatemala shipment can be split into two Business Central invoices:

1. INT ocean freight management: `Freight (Ocean/Truck/Air)`
2. INT emergency surcharge: `Emergency Surcharge`

The script uses the standard GT invoice mapping preview first, then filters the already-mapped INT lines into the two special invoices. Business Central still owns invoice numbering, posting, FEL stamping, and PDF rendering.

### Current Safety Rules

- The operator must provide the shipment task ID and the old invoice number being replaced.
- The script cancels the old BC/FEL invoice before issuing the split replacements.
- If FEL cancellation rejects the issue datetime, rerun with the exact SAT/FEL issue datetime override.
- If a rerun finds active replacement invoices, it reuses them only when their totals match the expected split totals.
- ClickUp delivery replaces `Invoice to Client` with the active split PDFs and writes the normal BC reference comment.
- The final `Facturada` status is updated only when the task has the invoice status custom field.

### Example

```bash
python scripts/replace_gt_invoice_split_int_charges_once.py \
  --task-id MTMLXGT-21971 \
  --team-id 8451352 \
  --old-invoice GTFVR0003921 \
  --issue-datetime 'GTFVR0003921=2026-06-12T01:25:19'
```

The original validation case was requested through `DISPUTE-441`, but the shipment source of truth is `MTMLXGT-21971`.
