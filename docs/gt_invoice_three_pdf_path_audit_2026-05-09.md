# GT Invoice Three PDF Path Audit - 2026-05-09

## Invoice

- Invoice: `GTFVR0003741`
- Customer: `C00093 GRUPO MASTER DE GUATEMALA SOCIEDAD ANONIMA`
- Customer NIT: `575410`
- Issuer NIT: `109582985`
- UUID: `250F4A40-9E27-414D-A34C-FE5F3EB028AB`

## Files Reviewed

| File | Generator | Likely BC Action/Path | Result |
| --- | --- | --- | --- |
| `1306 Sales - Invoice GTFVR0003741.pdf` | Microsoft Word + Aspose.Words | BC native report `1306 Sales - Invoice` | Passes required layout checks |
| `GTFVR0003741 (2).pdf` | Aspose.PDF for .NET 26.3.0 | BC `Electronic Document > Export E-Document as PDF` | Fails; generic English/CFDI-style layout |
| `NIT_109582985_250F4A40-..._CERTIFICACION_INFILE.pdf` | JasperReports 6.19.1 + iText | INFILE/FEL graphical representation | Fails; closest correct GT form but still has bank footer and unlabeled customer NIT |

## Findings

### 1. Native BC Report 1306

This path is correct.

Passed:

- `FACTURAR A`
- Issuer NIT labeled: `NIT: 109582985`
- Customer NIT labeled: `NIT: 575410`
- No bank footer

This means the BC Word layout `MTM GT Sales Invoice 2026-05` is now behaving correctly.

### 2. BC E-Document PDF Export

This path is not correct.

Fails:

- Uses English `ELECTRONIC INVOICE`
- Uses `Bill-To` / `Ship-To`, not `FACTURAR A`
- Shows empty labels `Company RFC` and `Customer RFC`
- Does not show issuer NIT
- Does not show customer NIT

This looks like a generic E-Document/CFDI print layout, not the Guatemala INFILE representation.

### 3. INFILE Certification PDF

This is the correct layout family, but it is not fully fixed.

Passed:

- Spanish GT invoice structure
- `FACTURAR A`
- Issuer NIT labeled: `NIT: 109582985`
- Customer NIT value present: `575410`

Fails:

- Customer NIT is not labeled as `NIT: 575410`
- Bank footer still appears:
  - `Realizar pagos a la siguiente Cuenta`
  - `Banco: Banco Industrial S.A`
  - `Cuenta No.: 5550017361 DOLARES`
  - `A nombre de: MTM Logix Guatemala, S.A`

## Correct Fix Target

The customer-facing automated invoice should use either:

1. the corrected native BC `1306` layout, or
2. the corrected INFILE/Jasper graphical representation.

It should not use the generic BC E-Document Aspose.PDF/CFDI-style layout.

## What Page Inspection Should Identify

When inspecting the invoice page/action in BC, capture:

- Page name and page ID
- Source table
- Extension name
- Publisher
- Action name for `Export E-Document as PDF`
- Action name for `Export E-Document as XML`
- Action name for INFILE/certification PDF, if separate

The important question is which extension owns the `Export E-Document as PDF` action and whether that action can be rerouted to the INFILE graphical representation PDF.

## Required Routing

Preferred route:

```text
Automated email attachment
  -> INFILE/Jasper graphical representation
  -> corrected template without bank footer and with NIT label
```

Alternative route:

```text
Automated email attachment
  -> BC Report 1306 corrected Word layout
```

Do not use:

```text
Automated email attachment
  -> generic E-Document Aspose.PDF / CFDI layout
```
