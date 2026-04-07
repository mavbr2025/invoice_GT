# MTM Customer Invoicing Sync

This AL extension scaffolds the Business Central side of the ClickUp customer bridge for the non-standard customer fields that are not exposed by the standard `customers` API.

## What this extension is for

The Python bridge already updates the standard BC customer fields through the public API:

- `displayName`
- `taxRegistrationNumber`
- `email`
- `phoneNumber`
- `website`
- `addressLine1`
- `paymentTermsId`
- `paymentMethodId`
- `creditLimit`

This extension is only for the custom/local fields that still need a BC-side API surface, including:

- `CFDI Customer Name`
- `Correo Factura`
- `Cash Flow Payment Terms Code`
- `Copy Sell-to Addr. to`
- `Tax Identification Type`
- any other custom customer fields you decide to expose here

## Files

- [`app.json`](/Users/mario/Documents/Contracting_Tool/bc_extension/customer_invoicing_sync/app.json)
- [`CustomerInvoicingSyncApi.Page.al`](/Users/mario/Documents/Contracting_Tool/bc_extension/customer_invoicing_sync/src/CustomerInvoicingSyncApi.Page.al)
- [`CustomerInvoicingSyncMgt.Codeunit.al`](/Users/mario/Documents/Contracting_Tool/bc_extension/customer_invoicing_sync/src/CustomerInvoicingSyncMgt.Codeunit.al)
- [`launch.json`](/Users/mario/Documents/Contracting_Tool/bc_extension/customer_invoicing_sync/.vscode/launch.json)

## Expected API path

Once this extension is published, the Python bridge should use:

```text
/api/mtmlogix/customerSync/v1.0/companies({company_id})/customerInvoicing({customer_id})
```

Set that value in:

```text
BC_CUSTOMER_INVOICING_SYNC_PATH=/api/mtmlogix/customerSync/v1.0/companies({company_id})/customerInvoicing({customer_id})
```

`{customer_id}` must be the BC customer `SystemId`.

## Before publishing

1. Open this folder in VS Code with the AL Language extension installed.
2. Update [`launch.json`](/Users/mario/Documents/Contracting_Tool/bc_extension/customer_invoicing_sync/.vscode/launch.json) to point to your BC sandbox environment name if it is not literally `Sandbox`.
3. Download symbols from the sandbox.
4. Confirm the scaffold field numbers still match your tenant using Page Inspection on the BC Customer Card:
   - `CFDI Customer Name = 27007`
   - `Correo Factura = 50110`
   - `Copy Sell-to Addr. to = 7601`
   - `Tax Identification Type = 14020`
   - `Cash Flow Payment Terms Code = 840`
5. If your sandbox shows different numbers, update [`CustomerInvoicingSyncMgt.Codeunit.al`](/Users/mario/Documents/Contracting_Tool/bc_extension/customer_invoicing_sync/src/CustomerInvoicingSyncMgt.Codeunit.al) before publishing.
6. Publish the extension to sandbox first.
7. Test the API page in the browser or Postman before wiring it into Render.

## Suggested test sequence

1. `GET` one record from the API page and confirm the custom fields are visible.
2. `PATCH` one sandbox customer with:
   - uppercase `cfdiCustomerName`
   - normalized `correoFactura`
   - `copySellToAddressTo=Company`
   - `taxIdentificationType=Legal Entity`
   - `cashFlowPaymentTermsCode`
3. Verify the BC card reflects the changes.
4. Only then set `BC_CUSTOMER_INVOICING_SYNC_PATH` in local `.env` and in Render.

## Important note

This scaffold now includes the field numbers captured from your tenant. Keep using Page Inspection as the source of truth if you move to another localization, environment, or app version.
