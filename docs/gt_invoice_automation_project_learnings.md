# GT Invoice Automation Project Learnings

## Purpose

This document captures the practical lessons from the MTM Logix Guatemala invoice automation project and turns them into repeatable standards for future automation work.

The project connected ClickUp shipment tasks, Business Central customer invoices, FEL/SAT stamping, invoice PDF generation, ClickUp PDF writeback, task status updates, AWS deployment, and GitHub synchronization. The main lesson is that this type of work is not just "coding an integration." It is production software sitting directly on top of operations, finance, tax, document design, and customer-facing workflow.

## What Made This Project Difficult

1. The process crossed several systems with different failure modes: ClickUp, Business Central, FEL/SAT, AWS, GitHub, and local development.
2. The business rule was not one invoice per shipment. The correct behavior was two invoice groups per shipment, INT and NAT, with different charge logic, tax notes, customer requirements, and output expectations.
3. Some data lived in ClickUp shipment fields, some in related quotes, some in Business Central customer records, and some only became visible after posting or stamping.
4. PDF layout was not cosmetic. Missing placeholders, hidden fields, container overflow, invoice descriptions, and report selection directly affected whether invoices could be sent to customers.
5. Errors after posting were high risk. Once Business Central and FEL/SAT were involved, the system needed to know how to resume, cancel, reissue, and avoid duplicate or incomplete results.
6. Deployment was part of the product. AWS IAM, Elastic Beanstalk, API Gateway, environment variables, tokens, and logs all had to be operational before the webhook could be trusted.

## Core Learnings

### Treat Automations As Production Workflows

An automation that creates invoices is not a background helper. It is a production workflow with financial and tax consequences. The code must include readiness checks, reconciliation, failure handling, audit trails, and clear operator feedback.

For future projects, every automation should define:

- Trigger source.
- Required input fields.
- External systems touched.
- Idempotency rules.
- Human approval points.
- Rollback or correction path.
- Final acceptance checklist.

### Build From Real Data Before Writing Code

The shipment-to-invoice mapping became clearer only after comparing real ClickUp shipments, Business Central invoices, and the CFO mapping workbook. That should be the default pattern.

Before implementing an integration, collect a representative corpus:

- Successful examples.
- Edge cases.
- Incorrect historical examples.
- Missing-field examples.
- High-value transactions.
- Different customer/account types.

Then build the mapping table from evidence, not assumptions.

### Use A Formal Mapping Matrix

The connection matrix was one of the most valuable tools in the project. Future matrices should include these columns:

- Business concept.
- Source system.
- Source object.
- Source field label.
- Source field ID.
- Data type.
- Destination system.
- Destination object.
- Destination field.
- Transform rule.
- Required for invoice creation.
- Required for posting.
- Required for stamping.
- Default value.
- Validation rule.
- Owner.
- Notes and examples.

Field labels alone are not enough. Use stable IDs wherever possible because labels drift and shared fields may behave differently depending on list, folder, or space access.

### Separate Readiness From Execution

The system should never discover critical blockers only after creating invoices. A readiness/preflight step should run before any Business Central write.

Minimum invoice preflight checks:

- Shipment task exists and is readable.
- Shipment is in the correct ClickUp status, such as `Listo para facturar`.
- Customer can be resolved to a Business Central customer number.
- Business Central customer is not blocked.
- Business Central customer has required posting groups.
- Customer has valid FEL/SAT fields, including country when required.
- ETA/date fields are present where needed.
- Currency is resolved correctly.
- Required ClickUp custom fields are available in the task location.
- Charge lines resolve to Business Central items or accounts.
- Non-billable placeholders such as "No almacenaje" and "No DyD" are treated intentionally.
- INT/NAT split is known.
- Invoice total from extracted fields matches expected total.
- No active duplicate invoice exists for the same shipment/group unless the run is explicitly a replacement.

### Dry Run Must Be A First-Class Product Feature

Dry run should not be a developer-only convenience. It should produce a reviewable invoice preview before any live write.

A useful dry run should show:

- Shipment number.
- Customer number and name.
- Group to be invoiced: INT, NAT, or both.
- Booking.
- Containers.
- HBL or reference fields.
- Invoice lines.
- Quantity.
- Description.
- Unit price.
- Currency.
- Total per line.
- Total per invoice group.
- Skipped fields with reason.
- Missing mapping or readiness blockers.
- Whether the system would create, reuse, post, stamp, send, or upload.

### Validate Totals Before Issuance

Every run must reconcile extracted fields before invoice creation. The automation should not create an invoice if the expected billable amount and the generated invoice amount do not match within a defined tolerance.

Recommended validation loop:

1. Extract all billable ClickUp fields.
2. Normalize values, currencies, and zero/non-billable markers.
3. Map every billable field to a Business Central item or account.
4. Generate expected invoice lines.
5. Sum by invoice group: INT and NAT.
6. Compare expected totals with any available quote, validation comment, or known target.
7. Stop before Business Central creation if the total is not explainable.

### Design Idempotency From Day One

The webhook should be safe to retry. A repeated call should not create duplicate invoices if the prior run already created or posted records.

Recommended idempotency behavior:

- Use shipment ID plus invoice group as a logical key.
- Store or recover created Business Central draft invoice IDs.
- Store or recover posted invoice numbers.
- If a run fails after posting but before ClickUp writeback, resume writeback instead of creating new invoices.
- If a run fails after one group succeeds, do not recreate the successful group unless explicitly told to replace it.
- If cancellation is required, verify Business Central and FEL/SAT state before reissuing.

### Error Writeback Is Part Of The Workflow

The Spanish ClickUp error comments were essential because they made failures visible to operations, not just developers.

Errors should always include:

- Task ID.
- Stage.
- Process status.
- Business Central invoice numbers or IDs created so far.
- Human-readable detail.
- Required action.
- Clear statement that the automation is incomplete until PDFs, comments, and status are updated.

The error should be posted even if the final status update fails.

### Capture Raw External Error Details

Generic HTTP 400 errors slow the project down. The Business Central and FEL/SAT response body must be captured and surfaced.

For integrations, logs and comments should retain:

- HTTP status.
- Endpoint or operation.
- External error code.
- External error message.
- Business object involved.
- Request correlation ID if available.

Do not hide the actual external error behind a generic exception.

### PDF Layout Is Part Of The Business Logic

Invoice PDFs are not an afterthought. The invoice is the customer-facing artifact and the legal/tax artifact. Layout must be tested like code.

For invoice templates, test these fixtures:

- One container.
- Six containers.
- Twelve containers.
- Long booking.
- Long customer name.
- Multiple invoice lines.
- Long description.
- INT disclaimer.
- NAT disclaimer.
- Draft/pro forma output.
- Posted/stamped output.

Template changes should be verified visually before broad use.

### Business Central Extensions Should Expose Integration Fields Explicitly

When standard Business Central APIs do not expose required fields, add a purpose-built extension/API page instead of relying on manual UI changes or hidden behavior.

Examples of fields that should be explicit in integration APIs:

- Customer country and FEL/SAT fields.
- Custom customer fields used for invoicing.
- Invoice report/layout metadata if needed.
- Posted invoice identifiers.
- Electronic document/FEL status.
- Cancellation status and cancellation error details.

### Keep Deployment Repeatable

AWS setup consumed significant time because deployment depended on IAM, Elastic Beanstalk, API Gateway, environment variables, tokens, and logs.

Future deployments should have a runbook that includes:

- AWS account and region.
- Application name.
- Environment name.
- Runtime version.
- Application version naming convention.
- Required environment variables.
- Required IAM managed policies.
- API Gateway URL.
- Health endpoint.
- Readiness endpoint.
- Log locations.
- Rollback version.
- Manual recovery steps.

No production webhook should be enabled until the deployed version and readiness endpoint are verified.

### Use Managed Policies Instead Of Growing Inline Policies

The IAM quota issue showed that inline policies do not scale well. Prefer named customer-managed policies with clear purpose and small scope.

Recommended pattern:

- One policy for deploy access.
- One policy for read-only diagnosis if needed.
- One policy for log access.
- Avoid accumulating obsolete inline statements on a human IAM user.
- Attach policies to a group when possible.

### Keep GitHub, Local, And AWS In Sync

The system becomes hard to reason about when local code, GitHub code, and AWS deployed code diverge.

Every deployment should record:

- Git branch.
- Commit SHA.
- Application version name.
- AWS environment.
- Deployment time.
- Smoke test result.
- Rollback version.

The deployed application version should be traceable to a Git commit.

## Recommended Engineering Standards For Future Work

### 1. Start With A Discovery Pass

Before code changes:

- Read the existing repo.
- Identify existing modules and helpers.
- Verify current live behavior where possible.
- Confirm the true source of each field.
- Identify write targets and irreversible operations.

Do not build a parallel system when the repo already has usable foundations.

### 2. Create A Short Technical Brief Before Building

Each automation should begin with a one-page brief:

- Goal.
- In scope.
- Out of scope.
- Trigger.
- Source systems.
- Destination systems.
- Required fields.
- Failure modes.
- Acceptance criteria.
- Rollback path.

This avoids confusing "working code" with a completed operational workflow.

### 3. Build The Read-Only Path First

The first implementation should extract data, map it, validate it, and produce a preview without writing to external systems.

Only after the preview is reliable should the code create, post, stamp, upload, or update.

### 4. Gate Live Writes Behind Explicit Preconditions

All live writes should be blocked unless preflight passes.

Examples:

- Do not create Business Central invoice if required customer fields are missing.
- Do not post if totals do not reconcile.
- Do not mark ClickUp as facturada unless PDFs and comments were written.
- Do not retry failed FEL/SAT stamping blindly.
- Do not cancel/reissue without checking current BC and SAT status.

### 5. Make Every Stage Observable

Use structured logs with these fields:

- run_id.
- task_id.
- shipment_number.
- invoice_group.
- stage.
- status.
- bc_invoice_id.
- bc_invoice_number.
- posted_invoice_number.
- fel_status.
- clickup_writeback_status.
- elapsed_ms.

Logs should allow the team to answer: "What happened, where did it stop, and what record do I need to inspect?"

### 6. Add A Post-Run Auditor

Every invoice run should be auditable after the fact.

A single command should check:

- ClickUp task status.
- ClickUp invoice PDF field.
- ClickUp comments.
- Business Central draft invoices.
- Business Central posted invoices.
- FEL/SAT status.
- PDF availability.
- Expected versus actual totals.

This is especially important after partial failures.

### 7. Use Small Deployable Commits

Commit each meaningful checkpoint:

- Mapping changes.
- Validation changes.
- Business Central client changes.
- ClickUp writeback changes.
- AWS deployment changes.
- Template/layout changes.

Avoid mixing unrelated changes in the same commit. This makes rollback and review much faster.

### 8. Treat Secrets As Operational Risk

Do not paste passwords or tokens into chat, logs, code, or screenshots.

Recommended approach:

- Store secrets in AWS environment variables or a secrets manager.
- Use local `.env` files excluded from Git.
- Rotate secrets that were exposed.
- Use short-lived tokens where possible.
- Keep a secret inventory for production dependencies.

### 9. Standardize Human Approval Points

Some actions should remain explicit:

- First live run for a new customer.
- Cancellation of stamped invoices.
- Reissue after FEL/SAT error.
- New charge mapping with tax impact.
- New customer with incomplete BC setup.

The system can prepare and validate, but the approval boundary should be visible.

### 10. Make Documentation Part Of Done

For each production workflow, maintain:

- User runbook.
- Developer runbook.
- Mapping matrix.
- Deployment checklist.
- Error catalog.
- Recovery procedures.
- Known limitations.

Documentation should be updated in the same PR or commit as the code that changes the workflow.

## Acceleration Playbook For The Next Automation

### Phase 0: Define Done

Define the final state in operational terms. For this project, "done" was not "invoice created." Done meant:

- Invoice created in Business Central.
- Invoice posted.
- FEL/SAT stamped.
- Correct PDF generated.
- PDF uploaded to ClickUp.
- Business Central references commented in ClickUp.
- ClickUp invoice status set to facturada.
- Errors written back in Spanish if anything failed.

Every future automation should define done this concretely.

### Phase 1: Build The Evidence Set

Collect examples before coding:

- 10 normal records.
- 5 edge records.
- 3 historical problem records.
- 1 record for each expected customer or account type.

Create a comparison table and identify patterns.

### Phase 2: Build The Mapping Matrix

Map every source field to every destination field. Include field IDs, labels, transforms, defaults, and validation rules.

Do not leave "we will infer this later" fields unresolved if they are required for posting, stamping, or customer output.

### Phase 3: Build Read-Only Preview

Implement extraction, normalization, mapping, and validation first.

Preview output should be good enough that operations can approve or reject it before live writes.

### Phase 4: Add Controlled Writes

Add writes in this order:

1. Create draft.
2. Add lines.
3. Validate total.
4. Post.
5. Stamp.
6. Generate PDF.
7. Upload PDF.
8. Comment references.
9. Update final status.

Each stage should be resumable or fail with an actionable error.

### Phase 5: Deploy With A Checklist

Before enabling webhook:

- GitHub is current.
- AWS deployed version matches commit.
- Environment variables are present.
- Readiness endpoint passes.
- Health endpoint passes.
- ClickUp webhook test passes.
- Production logs are visible.
- Rollback version is known.

### Phase 6: Monitor And Reconcile

After enabling:

- Audit the first run manually.
- Audit the first run per customer.
- Reconcile invoices daily during the first rollout week.
- Track every failure category.
- Convert repeated failures into preflight checks.

## Suggested Reusable Assets To Build Next

1. `scripts/audit_invoice_run.py`
   - Given a ClickUp task ID or shipment number, report ClickUp, BC, FEL/SAT, PDFs, comments, and status.

2. Persistent run ledger
   - Store every webhook run with `run_id`, task ID, invoice group, BC IDs, posted numbers, FEL status, PDF upload result, and final status.

3. Invoice fixture set
   - Known test shipments for one container, six containers, twelve containers, INT only, NAT only, both groups, missing customer field, missing country, and missing charge mapping.

4. Error catalog
   - Map external errors to Spanish operator messages and recommended actions.

5. Deployment manifest
   - Record commit SHA, AWS app version, environment, and required variables for each release.

6. Mapping validator
   - Fail CI or readiness if a billable ClickUp field has no Business Central mapping.

## What Would Have Saved The Most Time

1. A complete connection matrix before coding.
2. A real sample set of historical invoices and shipments before implementing mappings.
3. A Business Central extension/API page exposing all required customer and FEL fields from the start.
4. A dry-run invoice preview with total reconciliation before the first live invoice.
5. A built-in post-run auditor.
6. Early AWS/IAM deployment runbook and managed policy setup.
7. A fixed PDF fixture suite for one, six, and twelve containers.
8. Consistent Spanish error writeback from the first webhook test.
9. A single source of truth for deployed version, Git commit, and webhook URL.

## Working Agreement For Future Complex Automations

Use this checklist before any production-facing automation:

- We have a source-of-truth mapping matrix.
- We have at least 10 representative examples.
- We have a dry-run preview.
- We have preflight validations.
- We have idempotency rules.
- We have a post-run audit command.
- We have customer-facing artifact checks.
- We have structured logs.
- We have Spanish operational error writeback where needed.
- We have a rollback or correction path.
- We have GitHub, local, and deployed versions aligned.

The goal is not only to move faster. The goal is to move faster without creating uncertainty in finance, operations, tax, or customer-facing documents.
