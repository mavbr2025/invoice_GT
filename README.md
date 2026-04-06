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

This repo now includes a small FastAPI service for ClickUp -> Business Central customer sync:

- `GET /healthz`
- `POST /clickup/webhooks/customer-sync`

The service is configured for Render via `render.yaml`.

Additional env vars:

- `CLICKUP_WEBHOOK_TOKEN`
- `CLICKUP_WEBHOOK_TEAM_ID`
- `CLICKUP_WEBHOOK_CUSTOM_TASK_IDS=true`

Local run:

```bash
uvicorn webhook_bridge.main:app --host 0.0.0.0 --port 8000
```

Render start command:

```bash
uvicorn webhook_bridge.main:app --host 0.0.0.0 --port $PORT
```

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
