# Business Central Connector

This workspace now includes a small Python connector for the Microsoft Dynamics 365 Business Central API.

It covers:

- Microsoft Entra client-credentials authentication
- environment discovery
- company discovery
- basic `items` and `customers` reads
- multi-market company profiles such as Mexico and Guatemala
- a pricing-oriented lookup flow with support for a custom pricing endpoint
- a Render-ready webhook bridge for ClickUp customer sync
- a Render-ready webhook bridge for GT/USD sales invoice creation from ClickUp

## 1. Configure credentials

Copy `.env.example` to `.env` and fill in:

- `BC_TENANT_ID`
- `BC_CLIENT_ID`
- `BC_CLIENT_SECRET`
- `BC_ENVIRONMENT`
- `BC_DEFAULT_MARKET` plus per-market company/currency settings

The connector supports either a legacy single-company setup with `BC_COMPANY_ID` or market-specific profiles. For your use case, market profiles are the better fit.

If your team exposes pricing through a custom Business Central API, also set:

- `BC_CUSTOM_PRICING_PATH`
- or a market-specific path such as `BC_MARKET_MX_CUSTOM_PRICING_PATH`

Example:

```env
BC_TENANT_ID=11111111-1111-1111-1111-111111111111
BC_CLIENT_ID=22222222-2222-2222-2222-222222222222
BC_CLIENT_SECRET=replace-me
BC_ENVIRONMENT=Production
BC_DEFAULT_MARKET=MX
BC_MARKET_MX_COMPANY_ID=33333333-3333-3333-3333-333333333333
BC_MARKET_MX_LOCAL_CURRENCY_CODE=MXN
BC_MARKET_MX_SUPPORTED_CURRENCY_CODES=MXN,USD
BC_MARKET_GT_COMPANY_ID=44444444-4444-4444-4444-444444444444
BC_MARKET_GT_LOCAL_CURRENCY_CODE=GTQ
BC_MARKET_GT_SUPPORTED_CURRENCY_CODES=GTQ,USD
BC_MARKET_MX_CUSTOM_PRICING_PATH=/api/contoso/pricing/v1.0/companies({company_id})/priceCalculations
```

## 2. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

## 2a. Optional: webhook bridge deployment

This repo now includes a small FastAPI service for ClickUp -> Business Central sync:

- `GET /healthz`
- `POST /clickup/webhooks/customer-sync`
- `POST /clickup/webhooks/invoice-sync`

The service is configured for Render via `render.yaml`.

Additional env vars:

- `CLICKUP_WEBHOOK_TOKEN`
- `CLICKUP_WEBHOOK_TEAM_ID`
- `CLICKUP_WEBHOOK_CUSTOM_TASK_IDS=true`
- invoice automation env vars for GT/USD field mapping and BC line accounts

Local run:

```bash
uvicorn webhook_bridge.main:app --host 0.0.0.0 --port 8000
```

Render start command:

```bash
uvicorn webhook_bridge.main:app --host 0.0.0.0 --port $PORT
```

## WhatsApp intake scaffold

The webhook bridge now also includes a minimal inbound WhatsApp -> ClickUp intake endpoint:

- `POST /whatsapp/webhooks/inbound`

It is designed for Twilio's inbound WhatsApp webhook and currently supports:

- Twilio signature validation
- inbound message normalization into a provider-agnostic event shape
- create-or-update booking intake tasks in ClickUp keyed by customer phone
- task comment append for follow-up messages

Additional env vars:

- `TWILIO_AUTH_TOKEN`
- `TWILIO_VALIDATE_SIGNATURE=true`
- `TWILIO_VALIDATE_URL=` optional exact public URL used for signature validation
- `WHATSAPP_CLICKUP_BOOKING_LIST_ID`
- `WHATSAPP_CLICKUP_OPERATIONS_LIST_ID` optional fallback list if you want all unmatched traffic to land in Operations
- `WHATSAPP_CLICKUP_CUSTOMER_DIRECTORY_LIST_ID` optional ClickUp customer directory list used for phone matching
- `WHATSAPP_CLICKUP_DIRECTORY_*` optional field-name overrides for customer-directory lookup
- `WHATSAPP_CLICKUP_ROUTE_RULES_JSON` optional phone-based routing rules to target customer-specific lists
- optional `WHATSAPP_CLICKUP_*_FIELD_NAME` overrides for your ClickUp custom field names

Recommended ClickUp custom fields for the booking intake list:

- `Customer Phone`
- `Customer Name`
- `Source Channel`
- `Conversation ID`
- `Last WhatsApp Message At`
- `Last WhatsApp Message ID`
- optional routed customer field such as `Routed Customer`

Routing behavior:

1. If a phone routing rule matches, the task is created in that target list.
2. Otherwise, if `WHATSAPP_CLICKUP_CUSTOMER_DIRECTORY_LIST_ID` is set, the bridge scans that customer directory list for a matching phone number.
3. If the matched customer task contains a target-list field such as `WhatsApp Intake List ID`, the task is created in that list.
4. If the matched customer has no target list, the bridge uses `WHATSAPP_CLICKUP_OPERATIONS_LIST_ID` when present.
5. If that is not set, it falls back to `WHATSAPP_CLICKUP_BOOKING_LIST_ID`.

Example route rules:

```json
[
  {
    "match_type": "exact_phone",
    "pattern": "+5215512345678",
    "list_id": "901600000001",
    "customer_name": "SMARTSPACE"
  },
  {
    "match_type": "phone_prefix",
    "pattern": "+502",
    "list_id": "901600000099",
    "customer_name": "GUATEMALA OPS"
  }
]
```

Customer-directory lookup defaults:

- phone fields: `Contact Phone 1`, `Contact Phone Number`, `Phone`, `Customer Phone`
- customer label fields: `Business Central Legal Name`, `Clientes/`, `Customer Name`
- target list id fields: `WhatsApp Intake List ID`, `Operations List ID`, `Booking Intake List ID`, `Shipment Management EndPoint`
- target list values: raw ClickUp list id or full ClickUp list URL
- allowed statuses: blank means any CRM status

Preview a route from the CLI:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli resolve-whatsapp-route --phone +5215512345678
```

Twilio console setup:

1. Configure your WhatsApp sender or sandbox in Twilio.
2. Point the inbound message webhook at your deployed `/whatsapp/webhooks/inbound` URL.
3. Copy the Twilio account auth token into `TWILIO_AUTH_TOKEN`.
4. If the public webhook URL differs from the URL seen by FastAPI behind your proxy, set `TWILIO_VALIDATE_URL` to the public URL exactly.

## 3. Try the connector

List environments:

```bash
python3 -m business_central_client.cli environments
```

List companies for the configured environment:

```bash
python3 -m business_central_client.cli companies
```

List items:

```bash
python3 -m business_central_client.cli items --market MX --top 10
```

List customers:

```bash
python3 -m business_central_client.cli customers --market GT --top 10
```

Run the pricing-oriented flow:

```bash
python3 -m business_central_client.cli price-preview --market MX --currency-code USD --customer-number C10000 --item-number 1896-S --quantity 5
```

## Invoice automation

### Business Central -> ClickUp Revenue Guatemala invoice mirror

Phase 1 of the posted customer invoice mirror is implemented as a scheduled CLI job.
It uses Business Central as the source of truth and mirrors posted invoices into the
ClickUp Revenue Guatemala list.

Default target:

- ClickUp Workspace: `8451352`
- ClickUp Revenue Guatemala List: `901710831940`
- ClickUp shipment/Invoicing List: `152220606`
- Business Central market profile: `GT`

Required configuration:

```env
BC_TENANT_ID=
BC_CLIENT_ID=
BC_CLIENT_SECRET=
BC_ENVIRONMENT=Production
BC_MARKET_GT_COMPANY_ID=

CLICKUP_ACCESS_TOKEN=
CLICKUP_TOKEN_TYPE=Bearer
CLICKUP_REVENUE_GT_WORKSPACE_ID=8451352
CLICKUP_REVENUE_GT_LIST_ID=901710831940
CLICKUP_REVENUE_GT_INVOICING_LIST_ID=152220606
CLICKUP_REVENUE_GT_EXCEPTION_LIST_ID=
CLICKUP_REVENUE_GT_DEFAULT_STATUS=vigente
```

`CLICKUP_REVENUE_GT_EXCEPTION_LIST_ID` should be set before apply mode. If it is
blank, failures are logged locally and the job continues gracefully, but no ClickUp
exception task can be created.

Dry-run incremental sync:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices
```

Apply incremental sync:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices --apply
```

Dry-run one invoice:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices --invoice-no GTFVR0003573
```

Apply one invoice:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices --invoice-no GTFVR0003573 --apply
```

Weekly/full reconciliation dry-run:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices --full-review
```

Local cron example:

```cron
15 * * * * cd /path/to/Contracting_Tool && PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices --apply >> output/revenue_invoice_sync.log 2>&1
30 6 * * 1 cd /path/to/Contracting_Tool && PYTHONPATH=. python3 -m clickup_integration.cli sync-revenue-invoices --full-review --apply >> output/revenue_invoice_sync_weekly.log 2>&1
```

Field mapping:

- The job discovers custom fields from the Revenue Guatemala list at runtime.
- It resolves ClickUp dropdown values to option IDs.
- Default field names include `Collection Estatus`, `Currency Invoice`, `Customer`, and `Carrier/`.
- Override field-name candidates with `CLICKUP_REVENUE_GT_FIELD_NAMES_JSON` when the list labels change.

Known Phase 1 limitations:

- Business Central invoice PDF/XML/SAT attachment support depends on those documents being exposed by the BC API payload or a future custom endpoint.
- Shipment task linking is prepared but conservative; missing shipment matches are non-blocking.
- Customer dropdown options are not created automatically. Missing dropdown options route to the exception path.
- Webhooks are intentionally out of scope for Phase 1; the CLI is designed so a future webhook can call the same mapper/sync functions.

The invoice webhook is designed for this workflow:

- ClickUp remains the source of truth
- scope is Guatemala (`GT`) and `USD` only
- when task status is `OK Finops` and ETA exists within 10 days, the bridge updates the task to `Listo para facturar`
- when task status is `Listo para facturar`, the bridge creates split BC sales invoices for `INT...` and `NAT...` item groups

Expected header inputs:

- BC customer id or BC customer number, or a resolvable `Invoice to (Consignee's name)` dropdown value
- invoice currency
- reference
- dates, with `ETA/` used as the due-date fallback

Expected line inputs:

- the billable ClickUp fields listed in `config/invoice_charge_mappings/gt.json`
- each non-zero field becomes one BC `Item` sales invoice line
- mapped `INT...` items are grouped into one invoice and mapped `NAT...` items into a second invoice
- zero or blank fields are skipped

## Truck inspection PDF reports

This repo now includes a first-slice inspection report automation under
`inspection_reports/`. It generates PDFs from ClickUp truck tasks and SharePoint
inspection photos, uploads the PDF back to SharePoint, and writes the report link
to a ClickUp custom field.

See [docs/inspection_reports.md](docs/inspection_reports.md) for setup, matching
rules, and dry-run commands.

Safety rules:

- blocks duplicates by checking existing BC `salesInvoices` with the same external reference
- fails when required fields are missing
- logs every transition and invoice attempt through the webhook service logs
- after successful BC creation, downloads the INT/NAT PDFs, uploads both files into the configured ClickUp invoice file field, comments the BC invoice numbers/ids/links, then marks the invoice status as `Facturada`
- if BC invoice creation succeeds but PDF upload/comment/status update fails, returns `failed_post_creation` and does not mark the task `Facturada`

The bridge defaults to dry-run mode so the end-to-end webhook can be tested without
mutating ClickUp or Business Central:

```env
CLICKUP_INVOICE_WEBHOOK_APPLY=false
```

Set `CLICKUP_INVOICE_WEBHOOK_APPLY=true` only when the bridge should update ClickUp
statuses, create BC invoices, and write BC invoice number/id back into ClickUp.

The active GT charge mapping is generated from the reviewed CFO workbook:

```bash
PYTHONPATH=. python3 scripts/export_invoice_charge_mapping.py \
  --workbook output/MTM_CFO_BC_ClickUp_Connection_Matrix_2026.xlsx \
  --output config/invoice_charge_mappings/gt.json \
  --market GT
```

For a local sandbox pass before wiring the webhook end to end:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli smoke-test-invoice --task-id YOUR_TASK_ID --custom-task-ids --team-id YOUR_TEAM_ID
```

To actually create the invoice in BC sandbox and write the invoice id/number back into ClickUp:

```bash
PYTHONPATH=. python3 -m clickup_integration.cli smoke-test-invoice --task-id YOUR_TASK_ID --custom-task-ids --team-id YOUR_TEAM_ID --set-ready-status --apply --writeback
```

## Pricing note

The public Business Central API is great for standard entities, but it does not expose a simple built-in "calculate effective customer price" endpoint in the same way many teams expect.

The `price-preview` command therefore supports two modes:

- `custom_endpoint`: calls your custom Business Central pricing API when `BC_CUSTOM_PRICING_PATH` or a market-specific custom path is configured
- `base_item_price`: falls back to the item's standard unit price and clearly labels that it is not a full customer-specific price calculation

For currency handling:

- Mexico supports `MXN` and `USD`
- Guatemala supports `GTQ` and `USD`
- If `--currency-code` is omitted, the connector uses the customer's BC `currencyCode` when present
- If the customer has no currency configured, the connector falls back to the market's local currency

If we want real pricing outcomes for your pricing exercise, the next step is usually one of these:

1. Create a custom Business Central API that returns the effective sales price for a given customer, item, quantity, date, and currency.
2. Use a quote/order workflow in BC and read the line price calculated by the application logic.

## File layout

- `business_central_client/config.py`: environment-driven settings
- `business_central_client/auth.py`: token acquisition and caching
- `business_central_client/client.py`: Business Central REST client
- `business_central_client/pricing.py`: pricing-oriented helper logic
- `business_central_client/cli.py`: command-line interface
- `clickup_integration/cli.py`: ClickUp/customer bridge commands
- `webhook_bridge/main.py`: FastAPI webhook entrypoint for Render
- `render.yaml`: Render web service definition
- `tests/test_client.py`: a few smoke tests for URL construction
