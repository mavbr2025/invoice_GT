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

## Invoice layout audit API paths

Version `0.1.1.0` adds read-only API pages for invoice layout diagnostics. These pages are intended to answer which report/layout Business Central will use for direct print/email paths, without sending any invoice.

Expected paths after publishing:

```text
/api/mtmlogix/layoutAudit/v1.0/companies({company_id})/customerLayoutSetup
/api/mtmlogix/layoutAudit/v1.0/companies({company_id})/documentSendingProfiles
/api/mtmlogix/layoutAudit/v1.0/companies({company_id})/reportSelections
/api/mtmlogix/layoutAudit/v1.0/companies({company_id})/customReportSelections
/api/mtmlogix/layoutAudit/v1.0/companies({company_id})/reportLayoutSelections
/api/mtmlogix/layoutAudit/v1.0/companies({company_id})/reportLayouts
```

For the COTTONTEXTILE invoice issue, the checks are:

1. `customerLayoutSetup`: filter `number eq 'C00081'` and confirm the customer `documentSendingProfile`.
2. `documentSendingProfiles`: inspect the customer profile, or the default profile if the customer field is blank. Confirm email attachment is PDF and that the profile does not force a separate electronic-only output.
3. `customReportSelections`: filter `sourceNo eq 'C00081'`. If invoice rows exist, these override the global sales report selection for this customer.
4. `reportSelections`: inspect rows where `usage` is invoice-related and `useForEmailAttachment` is true. This identifies the report and layout used when BC sends an invoice by email.
5. `reportLayoutSelections`: match the selected `reportId` and company `MTM_GT_PROD`; confirm the default layout description is the corrected invoice layout.
6. `reportLayouts`: match the selected `reportId` and `reportLayoutName` to confirm the actual layout exists, is installed, and is not obsolete.

The layout is not correct if any effective invoice email attachment row points to an older layout that still renders:

- missing customer NIT
- `FACTRURA`
- the bank/payment footer

The layout is also not correct if BC API PDF rendering fails with the payment information error observed during the May 2026 audit.

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

`SendFelInvoice` is intentionally disabled. The legacy provider send routine renders and sends a Jasper/FEL PDF that bypasses the MTM Business Central invoice layout. The supported customer-delivery path is:

1. post the sales invoice in Business Central,
2. call `StampFelInvoice` for FEL/SAT stamping without customer email,
3. download `salesInvoices({id})/pdfDocument`,
4. upload that PDF to ClickUp and send it through the approved MTM workflow.
