# MTM GT Invoice Standard

This extension packages the approved Guatemala invoice layout and routes Business Central invoice output to one standard report/layout.

## What It Adds

- Report extension `71100 "MTM GT Invoice Standard"` for existing report `50105 FacturaGTM`.
- Draft/pro forma report `71104 "MTM GT Draft Invoice"` for unposted sales invoice output.
- RDLC layout `MTMGTInvoiceStandard202606OnePage`.
- Draft RDLC layout file `MTMGTDraftInvoice202605.rdl` mirrors the same one-page visual design against draft invoice data.
- Install/setup codeunit that points posted sales invoice output to `50105 FacturaGTM` and draft/pro forma invoice output to `71104 "MTM GT Draft Invoice"` with the same visual layout.
- Upgrade codeunit that reapplies the routing when the app is updated.
- Setup page `71100 "MTM GT Invoice Std. Setup"` with an action to reapply routing after publishing or after customer-specific report changes.

## Layout Rules Included

- `FACTURAR A` customer block.
- Customer block order: name, `NIT`, then address.
- No `DATOS COMPLEMENTARIOS` block.
- No payment/bank instruction footer.
- Embedded MTM Logix logo from the approved design package, independent of the BC company picture.
- HBL-inspired page margins, border frame, and footer spacing.
- Business Central-safe MTM typography using Aptos as the hosted-renderer fallback for the MTM Logix Noto Sans standard.
- No watermark layer in the Business Central-rendered invoice, preventing any overlay on invoice fields or charge rows.
- Aligned FEL header/table spacing with no blank separator row.
- Bottom fiscal/certification box includes authorization number, certification date, certifier text, FEL badge, and QR generated from the certified FEL UUID stored in `Fiscal Invoice Number PAC`.
- QR encodes the FEEL public document URL and renders directly inside the BC PDF/email layout.
- Boxed invoice line table and lower settlement band with boxed totals.
- Boxed shipment reference grid beside the customer block with placeholders for PO, booking, and up to 12 containers.
- Shipment booking and container metadata is read from hidden `MTM META` invoice comment lines; container values can span multiple 100-character-safe comment lines.
- `TOTAL EN LETRA` prints inline in the lower settlement band.
- `SALDO PENDIENTE` is removed from the invoice output.
- ISR disclaimer is dynamic and all caps: invoice lines with `NAT*` item/account numbers print `SUJETO A PAGOS TRIMESTRALES ISR`; invoice lines with `INT*` item/account numbers print `SUJETO A PAGOS TRIMESTRALES ISR. SERVICIOS NO AFECTOS. NO AFECTO AL IVA (FUERA DEL HECHO GENERADOR ART. 3, 7 Y 8, LEY DEL IVA).`.
- Detail line rows and the shipment grid use fixed compact heights so long descriptions or container lists do not push totals, QR, or certification footer onto a second page.
- Posted and draft invoice detail rows are paged in fixed 8-line groups: page 1 shows visible lines 1-8, page 2 shows lines 9-16, page 3 shows lines 17-24, and so on.
- The invoice heading is in the RDLC page header and repeats on every page when the line count requires pagination.
- The FEL certification band and QR are in the reserved RDLC page footer so they cannot slip onto an orphaned second page; `PAGINA X DE Y` prints below that footer block.
- Posted and draft invoice line descriptions resolve from BC line-level custom description fields first (`Description XL` / `Descripción Factura`), then the standard BC line description, then the `INT*` / `NAT*` item or G/L account master description as a fallback.
- Draft/pro forma invoices use the same visual template and print `BORRADOR - SIN CERTIFICAR` in the fiscal authorization area, without FEL QR.

## Build Output

Compiled app:

```text
bc_extension/mtm_gt_invoice_standard/MTMLogix_MTMGTInvoiceStandard_0.1.0.34.app
```

The local build used the AL compiler from the installed VS Code AL extension and symbols from the existing local AL workspace.

## Publish And Test

1. Publish `MTMLogix_MTMGTInvoiceStandard_0.1.0.34.app` to sandbox first.
2. Confirm dependency app `Mario Veraldo / MTM / 2.1.0.18` is already installed.
3. Open page `MTM GT Invoice Standard Setup`.
4. Run `Apply Invoice Routing`.
5. Generate the same posted sales invoice through:
   - manual print/download PDF for posted invoice,
   - draft invoice print/PDF,
   - pro forma invoice print/PDF,
   - requested email,
   - automatic email attachment.
6. Save the PDFs and validate they all use the same output.

Important: if the certifying/FEL provider renders a PDF outside Business Central report rendering, this extension cannot control that provider-side PDF. That external template must be updated separately to match this same layout.
