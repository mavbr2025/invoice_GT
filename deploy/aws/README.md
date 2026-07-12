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
- `CLICKUP_INVOICE_WEBHOOK_APPLY=true` allows the full flow: status update, BC invoice creation, BC post, FEL stamp, PDF upload, ClickUp comment, and final `Facturada` status.
- The code does not use the legacy FEL customer-send action. It stamps through BC/FEL and downloads the Business Central `pdfDocument`.
- Configure secrets through AWS App Runner/ECS environment variables or Secrets Manager, not through files committed to git.

## Manual Special Requirements

Customer-specific invoice exceptions are documented under:

```text
config/special_invoice_requirements/
```

The current special request is `gt_int_two_step_special_request`: split the INT portion of an approved GT shipment into two manually issued INT invoices, one for `Freight (Ocean/Truck/Air)` and one for `Emergency Surcharge`.

This is intentionally not wired to the ClickUp webhook. Packaging `scripts/` into the image only preserves the controlled manual tooling for an operator with shell access; it does not expose a route, scheduler, or automatic trigger.

Example manual command:

```bash
python scripts/replace_gt_invoice_split_int_charges_once.py \
  --task-id MTMLXGT-21971 \
  --team-id 8451352 \
  --old-invoice GTFVR0003921 \
  --issue-datetime 'GTFVR0003921=2026-06-12T01:25:19'
```

Do not automate this command until the requirement is promoted out of `manual_special_request_only`.
