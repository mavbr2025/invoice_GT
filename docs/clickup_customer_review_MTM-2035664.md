# ClickUp Customer Review: `MTM-2035664`

This note captures the customer-related structure observed from ClickUp task `MTM-2035664` and compares it against the Business Central customer model.

## Task identity

- ClickUp custom task ID: `MTM-2035664`
- ClickUp API task ID: `86dxp6nmg`
- Task name: `FPK`
- Status: `current customer`
- List: `List 3: Qualified Pipeline` (`52717033`)
- URL: `https://app.clickup.com/t/86dxp6nmg`

## High-signal customer fields found in ClickUp

- `name`
  - value: `FPK`
- `Clientes/`
  - type: dropdown
  - selected value index: `73`
  - appears to represent the customer/account selector
- `Webpage`
  - value: `https://fpk.com.gt`
- `Tax ID`
  - value: `null`
- `Sales Contact`
  - value: `null`
- `Sales email`
  - value: `null`
- `The customer Needs credit?`
  - value: `null`
- `Total customer value`
  - value: `null`
  - configured currency type: `USD`
- `Trade`
  - selected labels: `Asia`, `North America`

## Important gaps vs Business Central

Compared with the BC customer structure in [bc_customer_structure.md](/Users/mario/Documents/Contracting_Tool/docs/bc_customer_structure.md), this ClickUp task does not currently expose several fields we would normally want for deterministic customer sync:

- BC customer number
- market/company (`MX` vs `GT`)
- invoice currency (`GTQ`, `MXN`, or `USD`)
- address lines
- city/state/postal code
- country
- phone
- payment terms
- payment method
- tax ID is present as a field, but empty on this record

## Matching implications

This task is not yet strong enough to sync deterministically into BC by itself unless we define a match strategy.

Current likely candidates:

- `Clientes/` selected customer name
- task `name`
- website domain
- tax ID when populated

Recommended order of trust:

1. BC customer number if added to ClickUp
2. Tax ID if populated and reliable
3. explicit ClickUp field for BC customer ID or BC customer number
4. normalized company name plus market

I would not use website alone or task name alone as a hard upsert key.

## Recommendation for ClickUp schema

Add or confirm these fields on customer records in ClickUp:

- `Market`
  - values: `MX`, `GT`
- `BC Customer Number`
  - strongest sync key if BC is source of truth
- `Invoice Currency`
  - values: `MXN`, `GTQ`, `USD`
- `Tax ID`
  - keep as text
- `Customer Legal Name`
  - if different from short display name
- `Customer Email`
- `Customer Phone`
- `Country`
- `Address`
- `Needs Credit`

Optional but helpful:

- `BC Company`
- `BC Customer ID`
- `Payment Terms`
- `Payment Method`

## Provisional mapping for this task

| Canonical field | ClickUp source | Observed value | Comment |
|---|---|---|---|
| `name` | task `name` | `FPK` | Likely short account name |
| `website` | `Webpage` | `https://fpk.com.gt` | Good supporting identifier |
| `tax_id` | `Tax ID` | empty | Present but not populated |
| `customer_value` | `Total customer value` | empty | Commercial field, not identity |
| `needs_credit` | `The customer Needs credit?` | empty | Good BC credit workflow input later |
| `trade_regions` | `Trade` | `Asia`, `North America` | Useful commercial metadata, not sync key |
| `crm_customer_selector` | `Clientes/` | selected option present | Important, but we need the resolved option name/id in a cleaner way |

## Next step

For a robust BC sync, we should inspect:

1. the resolved selected value of `Clientes/`
2. the list custom fields for the customer list
3. whether another ClickUp list or task type stores more complete customer master data

Then we can decide whether ClickUp is the source of truth for customer master data, or whether it should reference BC customers instead of duplicating them.
