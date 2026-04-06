# Business Central Customer Structure

This document captures the live Business Central `customers` API shape currently accessible through the connector. It is intended to be the source structure for CRM and ClickUp matching work.

## Markets

- `MX` -> company `MTM_MX_PROD`
- `GT` -> company `MTM_GT_PROD`

## Customer fields observed in both MX and GT

- `id`
- `number`
- `displayName`
- `type`
- `email`
- `phoneNumber`
- `website`
- `addressLine1`
- `addressLine2`
- `city`
- `state`
- `postalCode`
- `country`
- `currencyCode`
- `currencyId`
- `taxRegistrationNumber`
- `taxLiable`
- `taxAreaDisplayName`
- `taxAreaId`
- `paymentMethodId`
- `paymentTermsId`
- `shipmentMethodId`
- `salespersonCode`
- `creditLimit`
- `balanceDue`
- `blocked`
- `lastModifiedDateTime`
- `@odata.etag`

## Meaning of the most important BC fields

- `id`: BC internal GUID for the customer record
- `number`: BC customer number; strong candidate for a stable external key if BC is the system of record
- `displayName`: customer/account name
- `currencyCode`: default customer currency in BC
- `taxRegistrationNumber`: tax ID / registration number
- `paymentTermsId`: payment terms reference
- `paymentMethodId`: payment method reference
- `salespersonCode`: owner or salesperson reference
- `blocked`: whether the customer is blocked for normal use
- `lastModifiedDateTime`: good anchor for incremental syncs

## Live sample: MX

```json
{
  "number": "1038",
  "displayName": "CARLOS GASCON",
  "email": "cgascon@alienpro.com.mx",
  "phoneNumber": "525526213117",
  "currencyCode": "MXN",
  "type": "Company"
}
```

## Live sample: GT

```json
{
  "number": "C00001",
  "displayName": "ALCANCE INTEGRAL, SOCIEDAD ANÓNIMA",
  "email": "gaguilar@grs-electronics.com",
  "phoneNumber": "50376077032",
  "currencyCode": "USD",
  "country": "GT",
  "taxRegistrationNumber": "63226545",
  "type": "Company"
}
```

## Recommended canonical customer model

Use this as the neutral integration model before mapping into ClickUp:

```json
{
  "market": "MX | GT",
  "bc_company_id": "string",
  "bc_customer_id": "string",
  "bc_customer_number": "string",
  "name": "string",
  "email": "string | null",
  "phone": "string | null",
  "website": "string | null",
  "address_1": "string | null",
  "address_2": "string | null",
  "city": "string | null",
  "state": "string | null",
  "postal_code": "string | null",
  "country": "string | null",
  "currency_code": "MXN | GTQ | USD | other",
  "tax_id": "string | null",
  "payment_terms_id": "string | null",
  "payment_method_id": "string | null",
  "salesperson_code": "string | null",
  "blocked": "boolean | normalized-status",
  "last_modified_at": "ISO datetime"
}
```

## Initial ClickUp matching template

This is the field-by-field template to review once we inspect the ClickUp structure:

| Canonical field | BC field | ClickUp field | Notes |
|---|---|---|---|
| `market` | derived from company profile | TBD | MX or GT |
| `bc_company_id` | integration config | TBD | Not usually shown to end users |
| `bc_customer_id` | `id` | TBD | Internal BC GUID |
| `bc_customer_number` | `number` | TBD | Strong external key candidate |
| `name` | `displayName` | TBD | Account/customer name |
| `email` | `email` | TBD | Contact or account email |
| `phone` | `phoneNumber` | TBD | Normalize formatting |
| `website` | `website` | TBD | Optional |
| `address_1` | `addressLine1` | TBD | Optional |
| `address_2` | `addressLine2` | TBD | Optional |
| `city` | `city` | TBD | Optional |
| `state` | `state` | TBD | Optional |
| `postal_code` | `postalCode` | TBD | Optional |
| `country` | `country` | TBD | Important for MX/GT split |
| `currency_code` | `currencyCode` | TBD | Must support local currency and USD |
| `tax_id` | `taxRegistrationNumber` | TBD | Strong dedupe candidate |
| `payment_terms_id` | `paymentTermsId` | TBD | Usually integration/internal only |
| `payment_method_id` | `paymentMethodId` | TBD | Usually integration/internal only |
| `salesperson_code` | `salespersonCode` | TBD | Optional owner mapping |
| `blocked` | `blocked` | TBD | Normalize to active/inactive if needed |
| `last_modified_at` | `lastModifiedDateTime` | TBD | Useful for sync |

## Matching recommendations

- Prefer `bc_customer_number` as the first stable external key if BC is the source of truth.
- Use `tax_id` as a secondary match key where reliable.
- Treat `email` as helpful but not unique enough by itself.
- Keep `currency_code` explicit because both MX and GT can invoice in local currency and USD.
- Keep `market` explicit so the same ClickUp workspace can still route to the correct BC company.

## Next step

Inspect the ClickUp account/customer structure and populate the `ClickUp field` column in the template above. Once we have that, we can define:

1. a canonical mapping
2. the sync direction
3. the match/upsert key
4. the transform rules
