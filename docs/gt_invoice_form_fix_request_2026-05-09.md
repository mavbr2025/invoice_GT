# GT Invoice Form Fix Request - 2026-05-09

## Scope

Fix the Guatemala invoice PDF form used by the automated email/FEL path.

This is separate from the Business Central Word report layout `1306`. The BC Word layout has already been corrected locally, but the PDF attached/sent through the FEL flow is still rendered by another form engine.

## Evidence

Sample invoice:

- Invoice: `GTFVR0003715`
- PDF: `/Users/mario/Downloads/Invoice/Factura_GTFVR0003715.pdf`
- XML: `/Users/mario/Downloads/Invoice/Factura_GTFVR0003715.xml`
- UUID: `08D02BFB-C403-4D2F-922A-A1EC9E6531FA`

The XML source data is correct:

- Issuer NIT: `109582985`
- Issuer name: `MTM LOGIX GUATEMALA, SOCIEDAD ANONIMA`
- Customer NIT: `3312801`
- Customer name: `REINVENTION REVOLUTION, LLC`

The generated PDF is not correct:

- It prints `FACTRURA A`.
- It does not print issuer NIT.
- It does not print customer NIT.
- This sample PDF does not show the Banco Industrial footer, but the standard must explicitly suppress that footer in all invoice variants.

## Required Form Output

Header/company block must include:

```text
MTM LOGIX GUATEMALA, SOCIEDAD ANONIMA
NIT: 109582985
```

Customer block must print:

```text
FACTURAR A
{customer name}
NIT: {customer NIT}
{customer address}
```

For sample `GTFVR0003715`, the customer block must include:

```text
FACTURAR A
REINVENTION REVOLUTION, LLC
NIT: 3312801
```

The PDF must not contain:

```text
FACTRURA
Realizar pagos a la siguiente Cuenta
Banco:
Cuenta No.:
A nombre de:
Banco Industrial
```

## Expected XML Bindings

Use the FEL XML attributes:

| PDF Field | XML Source |
| --- | --- |
| Issuer NIT | `Emisor/@NITEmisor` |
| Issuer legal name | `Emisor/@NombreEmisor` |
| Customer NIT | `Receptor/@IDReceptor` |
| Customer name | `Receptor/@NombreReceptor` |
| Customer email | `Receptor/@CorreoReceptor` |

## Acceptance Test

After the form is updated, export/regenerate the PDF for `GTFVR0003715` or another test invoice and run:

```bash
python3 /Users/mario/Documents/Contracting_Tool/scripts/check_invoice_pdf_layout.py \
  /path/to/generated_invoice.pdf \
  --config /Users/mario/Documents/Contracting_Tool/config/invoice_layouts/gt.toml \
  --customer-number C00103
```

The check must pass.

## Routing Requirement

The same corrected form must be used for:

- Manual invoice PDF download/print.
- Automated invoice email attachment.
- Public FEEL/FEL report link, if that link is controlled by the same provider.

If those are separate templates, update all of them with the same rules above.
