# AWS Deployment - ClickUp Invoice Webhook

This package is for running the FastAPI webhook bridge on AWS App Runner or ECS/Fargate.

The production entrypoint is:

```bash
uvicorn webhook_bridge.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Build

From the repository root:

```bash
docker build -f deploy/aws/Dockerfile -t mtm-clickup-invoice-webhook .
```

## Local Smoke Test

```bash
docker run --rm -p 8000:8000 --env-file deploy/aws/env.invoice-webhook.example mtm-clickup-invoice-webhook
curl http://localhost:8000/healthz
curl http://localhost:8000/clickup/webhooks/invoice-sync/readiness
curl http://localhost:8000/clickup/webhooks/inspection-invoice-sync/readiness
```

Use a private env file for real credentials. Do not place secrets in git.

## AWS App Runner

1. Push the image to ECR.
2. Create an App Runner service from that ECR image.
3. Set the service port to `8000`.
4. Configure environment variables from `env.invoice-webhook.example`.
5. Keep `CLICKUP_INVOICE_WEBHOOK_APPLY=false` until the service passes readiness and a controlled dry run.
6. Change `CLICKUP_INVOICE_WEBHOOK_APPLY=true` only after BC and ClickUp credentials are confirmed.

## ECS/Fargate

Use the same image in a Fargate service behind an HTTPS Application Load Balancer.

Required health check path:

```text
/healthz
```

Recommended invoice readiness path:

```text
/clickup/webhooks/invoice-sync/readiness
```

Inspection invoices use a dedicated route so their JSON payload is never mixed
with shipment-charge mappings:

```text
/clickup/webhooks/inspection-invoice-sync
```

Keep `INSPECTION_INVOICE_WEBHOOK_APPLY=false` for the first call. The route reads
the Magna task's `Invoice Payload` field, validates the customer/item/FEL state,
and returns the proposed BC header and lines without changing either system.

## Operational Guardrails

- `CLICKUP_WEBHOOK_TOKEN` must be set and used as the ClickUp webhook bearer token.
- `CLICKUP_INVOICE_WEBHOOK_APPLY=false` keeps the webhook in dry-run mode.
- `CLICKUP_INVOICE_WEBHOOK_APPLY=true` allows the standard invoice flow to create, post, and FEL-stamp invoices.
- `CLICKUP_INVOICE_SEND_ENABLED=true` applies one guarded delivery contract to every Guatemala webhook path: standard shipment invoices, inspection invoices when their independent apply mode is enabled, and posted-invoice recovery. Business Central sends the approved branded message from `consuelo@mtmlogix.com`, and the bridge requires native Sent Email evidence before ClickUp is finalized.
- A send failure writes a Spanish ClickUp error and prevents the task from being marked complete. The Business Central audit makes recovery idempotent and prevents duplicate customer emails.
- The bridge downloads and validates the Business Central `pdfDocument`; it does not use the legacy Infile customer-delivery email.
- Configure secrets through AWS App Runner/ECS environment variables or Secrets Manager, not through files committed to git.

## Manual Special Requirements

Customer-specific invoice exceptions are documented under:

```text
config/special_invoice_requirements/
```

The active customer rule `gt_int_two_step_special_request` applies only to ALB
Importaciones (`C00056`). The normal shipment webhook creates the following
documents when eligible billable fields are present:

- `<shipment>-INT`: `Freight (Ocean/Truck/Air)`.
- `<shipment>-INT-2`: `Emergency Surcharge`.
- `<shipment>-NAT`: unchanged, when NAT charges exist.

The rule blocks the webhook before BC creation when either required INT charge
is missing or a third INT charge would be assigned without an approved mapping.
This prevents a partial or incorrectly bundled ALB INT invoice.
