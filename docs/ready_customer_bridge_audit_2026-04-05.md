# Ready Customer Bridge Audit

Audit date: `2026-04-05`

Scope: the 20 customers currently marked as ready for BC write-back.

## Coverage

- Market from ClickUp `Owner Country/`: `20/20`
- ClickUp `Clientes/` selected: `20/20`
- ClickUp `Webpage`: `12/20`
- ClickUp tax ID fields (`Tax ID` or `Customer Tax ID`): `1/20`
- ClickUp primary contact email candidates (`Sales email`/`Finance email`/`Operations Email`/`Contact E-mail 1`): `16/20`
- ClickUp primary phone candidates (`Contact Phone Number` or `Contact Phone 1`): `14/20`
- BC email: `13/20`
- BC phone: `12/20`
- BC website: `0/20`
- BC tax ID: `19/20`
- BC currency: `20/20`
- BC payment terms and payment method: `20/20` and `20/20`

## Agreement

- Exact normalized name matches between ClickUp display alias and BC legal name: `2/20`
- Exact email matches: `7/20`
- Exact phone matches after digit normalization: `1/20`
- Exact tax ID matches: `1/20`
- Exact website matches: `0/20`

## What The Data Says

- ClickUp is strong for commercial aliases, contact names, contact emails, and sometimes website.
- Business Central is much stronger for tax ID, currency, payment terms, payment method, blocked status, and the canonical invoicing customer record.
- Customer names are often aliases in ClickUp and legal names in BC, so name alone is not a safe synchronization key.
- Website is almost never usable as a reconciliation key today because it is usually present in ClickUp but absent in BC.
- Email is useful but not authoritative. Contact emails in ClickUp often differ from the account email stored in BC.
- Phone is not reliable enough to key on; formatting and contact-vs-account differences are common.

## Recommended Bridge Contract

### BC-Owned Fields

- `Business Central Customer Number`
- `Business Central Customer ID`
- `Business Central Customer Link`
- `displayName` / legal invoicing name
- `taxRegistrationNumber`
- `currencyCode`
- `paymentTermsId`
- `paymentMethodId`
- `blocked`
- `creditLimit`
- `salespersonCode` if you want operational ownership to align to BC

### ClickUp-Owned Fields

- `Owner Country/` as the routing field for market
- `Clientes/` as the commercial/customer selector alias
- `Contact Name 1..6`
- `Contact E-mail 1..6`
- `Contact Phone 1..6` and `Contact Phone Number`
- `Sales Contact`, `Operations Contact`, `Finance Contact`
- `Trade`, `Industry`, product and revenue fields
- `The customer Needs credit?` as workflow input, not as financial truth

### Candidate Bidirectional Fields With Rules

- `website`: allow ClickUp to propose updates to BC only when BC website is blank or after manual approval
- primary account email: only sync after choosing one canonical ClickUp email source
- primary account phone: only sync after choosing one canonical ClickUp phone source
- legal name: only sync from ClickUp to BC on explicit create flow or manual approval
- tax ID: sync only with strict validation because BC is currently the stronger source

## Gating Rules For A Water-Tight Bridge

1. Never create or relink without `Owner Country/`.
2. Treat `Business Central Customer Number` as the primary external key once present.
3. Do not let ClickUp overwrite BC finance fields directly.
4. Require manual approval when name is alias-like and tax ID is blank.
5. Normalize legal suffixes and punctuation for matching, but never use name-only matching as the final authority.
6. Pick one canonical ClickUp contact email and one canonical ClickUp phone before enabling write-back to BC.
7. Prefer create flows only when no BC number exists and no credible BC match remains.

## Review Files

- JSON matrix: `ready_customer_bridge_matrix_2026-04-05.json`
- CSV matrix: `ready_customer_bridge_matrix_2026-04-05.csv`

## Sample Mismatch Patterns

- `MTM-2021350` name alias: ClickUp `BIORGANI` vs BC `GIAI INNOVATIONS, SOCIEDAD ANONIMA`
- `MTM-2022700` name alias: ClickUp `AFFIMEX` vs BC `AFFIMEX CORED WIRE`
- `MTM-2025188` name alias: ClickUp `GRS` vs BC `ALCANCE INTEGRAL, SOCIEDAD ANÓNIMA`
- `MTM-2028308` name alias: ClickUp `Instalaciones Modernas` vs BC `INSTALACIONES MODERNAS SOCIEDAD ANONIMA`
- `MTM-2029885` name alias: ClickUp `Oster/Distelsa` vs BC `HOUSEHOLD SOLUTION SA`
- `MTM-2021335` email mismatch: ClickUp `RTAoperations@rtaproducts.com` vs BC `None`
- `MTM-2025188` email mismatch: ClickUp `conta1gt@grs-electronics.com` vs BC `gaguilar@grs-electronics.com`
- `MTM-2027518` email mismatch: ClickUp `violeta@smartspace.mx` vs BC `email@em.comx`
- `MTM-2035554` email mismatch: ClickUp `None` vs BC `ventas1@klasnic.com.mx`
- `MTM-2035670` email mismatch: ClickUp `gerencia@htcorp.com` vs BC `None`
- `MTM-2021335` phone mismatch: ClickUp `+1 954 499 9149` vs BC `954 4999149`
- `MTM-2021350` phone mismatch: ClickUp `+502 5950 9758` vs BC `50401010`
- `MTM-2022700` phone mismatch: ClickUp `+52 314 334 1708` vs BC `314 177 0000`
- `MTM-2025188` phone mismatch: ClickUp `+502 2304 5555` vs BC `50376077032`
- `MTM-2027518` phone mismatch: ClickUp `+52 55 5414 2159` vs BC `123456789`
