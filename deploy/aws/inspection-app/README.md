# InspectionApp AWS Lambda

InspectionApp uses a Lambda Function URL only as a short-lived ingress. It validates
the ClickUp Automation token, starts an asynchronous Lambda invocation, and returns
`202 Accepted` before the report worker downloads photos or generates a PDF.

The worker owns the existing delivery sequence:

1. Generate and upload `<VIN>.pdf` to SharePoint.
2. Write the report URL to ClickUp.
3. Write the resolved photo-folder URL to ClickUp.
4. Attach the PDF in `Origin Inspection Report`.
5. Set the task to `PASSED` only after all prior writes succeed.

## Canonical report payload

InspectionApp reads the canonical JSON from the ClickUp `Report Payload` field
(`14cba98e-7dd2-426b-90b6-5c88be5e27e4`) when present. It validates the schema,
VIN filename, task ID, checkpoint set, and SharePoint folder reference before using
the payload as the report source. This avoids reconstructing report data from the
individual ClickUp fields.

Set `request.mode` to `apply` for a normal validated-status run. Use `dry_run` only
for controlled tests; it downloads photos and renders a local PDF but does not upload
the file, update ClickUp fields, attach a PDF, or change task status.

## Runtime configuration

Start with `env.example`. Store the values in AWS Lambda environment variables or
Secrets Manager, never in the container image. `INSPECTION_APP_APPLY=false` is the
safe first deployment mode.

`INSPECTION_APP_WEBHOOK_TOKEN` is used for readiness and controlled manual calls.
The production ClickUp API webhook is authenticated with its own `X-Signature` HMAC
secret, returned only when the subscription is created and stored as
`CLICKUP_API_WEBHOOK_SECRET`.

## Build and deploy

Create a private ECR repository once:

```bash
aws ecr create-repository --repository-name mtm-inspection-app --region us-east-1
```

Build and push a Linux image from the repository root:

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1
IMAGE="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/mtm-inspection-app:initial"

aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker buildx build --platform linux/amd64 --push \
  -f deploy/aws/inspection-app/Dockerfile -t "$IMAGE" .
```

Create the Lambda with 15 minutes, 4 GB memory, and 4 GB ephemeral storage. Its role
needs CloudWatch Logs permissions and `lambda:InvokeFunction` on this same function
so the ingress can start the worker asynchronously. Then create a Function URL with
`AuthType=NONE`; the application-level bearer token remains mandatory.

## ClickUp API webhook

Register a list-scoped `taskStatusUpdated` webhook on Magna Inspections. Store the
returned webhook secret in `CLICKUP_API_WEBHOOK_SECRET`. InspectionApp accepts only
the `validated` status, so the worker's own `PASSED` update is ignored.

The endpoint is:

```text
<function-url>/clickup/webhooks/inspection-reports
```

## Optional ClickUp Automation

An Automation is not required for the API webhook path. Use one only when a more
specific business trigger is needed than the `validated` task status.

1. Trigger when a task status changes to `validated`. This is the Magna report-ready
   state; the worker alone changes a successful task to `PASSED`.
2. Add conditions: VIN is populated, `OneDrive Pictures` is populated, and
   `Inspection Final Report URL` is empty.
3. Add the **Call webhook** action.
4. Enter `<function-url>/clickup/webhooks/inspection-reports/` and select ClickUp's
   Task ID dynamic field as the final URL segment.
5. Add `Authorization` with `Bearer <INSPECTION_APP_WEBHOOK_TOKEN>`.
6. Call `<function-url>/clickup/webhooks/inspection-reports/readiness` with the same
   bearer token. It must return `ready` before enabling the Automation.
7. Test while `INSPECTION_APP_APPLY=false`; the endpoint must return `202` and the
   worker log must show `dry_run`.
8. Set `INSPECTION_APP_APPLY=true` only after the environment readiness and a real
   SharePoint/ClickUp dry run are verified.

Do not trigger on `PASSED`: the worker owns that final transition. The URL-empty
condition prevents report writeback events from starting another report run.
