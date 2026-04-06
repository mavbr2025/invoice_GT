# Current Customer BC Audit

Source list: `https://app.clickup.com/8451352/v/l/81x8r-183737`

Audit date: `2026-04-04`

Scope:
- ClickUp list `52717033` (`List 3: Qualified Pipeline`)
- `current customer` tasks only
- BC market is derived from ClickUp `Owner Country/`

Summary:
- `43` current-customer tasks reviewed
- `1` already linked cleanly in ClickUp
- `20` look ready for BC write-back now
- `19` need manual review before write-back
- `3` are blocked because `Owner Country/` is missing

## Already Linked

| ClickUp task | Customer | Market | BC customer no. | Notes |
| --- | --- | --- | --- | --- |
| `MTM-2035587` | ESKOLOR, S.A. | `GT` | `C00069` | ClickUp already contains BC number, BC id, BC link, and match status. |

## Ready For Write-Back

These are the strongest current candidates based on task name, selected `Clientes/` value, market, and BC candidate alignment.

| ClickUp task | Customer | Market | BC customer no. | BC customer name |
| --- | --- | --- | --- | --- |
| `MTM-2021335` | RTA | `MX` | `C00013` | RTA PRODUCTS LLC |
| `MTM-2021350` | BIORGANI - GIAI INNOVATION, SOCIEDAD ANONIMA | `GT` | `C00025` | GIAI INNOVATIONS, SOCIEDAD ANONIMA |
| `MTM-2022700` | AFFIMEX Cored Wire, S DE RL DE CV | `MX` | `C00066` | AFFIMEX CORED WIRE |
| `MTM-2025188` | ALCANCE INTEGRAL, S.A. - GRS | `GT` | `C00001` | ALCANCE INTEGRAL, SOCIEDAD ANÓNIMA |
| `MTM-2027518` | Espacios Dinámicos | `MX` | `4` | ESPACIOS DINAMICOS |
| `MTM-2028308` | Instalaciones Modernas, S.A. | `GT` | `C00076` | INSTALACIONES MODERNAS SOCIEDAD ANONIMA |
| `MTM-2029885` | HOUSEHOLD SOLUTIONS - OSTER | `GT` | `C00019` | HOUSEHOLD SOLUTION SA |
| `MTM-2035549` | TAGOMAGO DISTRIBUTION | `MX` | `C00067` | TAGOMAGO DISTRIBUTION |
| `MTM-2035554` | Klasnic Insumos SA de CV | `MX` | `C00068` | KLASNIC INSUMOS |
| `MTM-2035578` | DORAL IMPORTACIONES, S.A. (MOVESA) | `GT` | `C00060` | DORAL IMPORTACIONES SOCIEDAD ANONIMA |
| `MTM-2035602` | BARENTZ GUATEMALA | `GT` | `C00065` | BARENTZ GUATEMALA, SOCIEDAD ANONIMA |
| `MTM-2035606` | BODEGANGAS, SOCIEDAD ANONIMA | `GT` | `C00062` | BODEGANGAS, SOCIEDAD ANONIMA |
| `MTM-2035670` | CARMIEL / Haifa Corporación | `GT` | `C00068` | CARMIEL, SOCIEDAD ANONIMA |
| `MTM-2035672` | TEXTISUR - TEXTILES DEL SUR, S.A. - INDUSTRIAS DISNA / FRAZIMA INTERNACIONAL, S. A | `GT` | `C00071` | INDUSTRIAS DISNA, SOCIEDAD ANONIMA |
| `MTM-2035916` | DISCOGUA - DISTRIBUIDORA COMERCIAL GUATEMALTECA, S.A. | `GT` | `C00079` | DISTRIBUIDORA COMERCIAL GUATEMALTECA SOCIEDAD ANONIMA |
| `MTM-2035933` | ANTIQUE, S.A. | `GT` | `C00070` | ANTIQUE SOCIEDAD ANONIMA |
| `MTM-2036013` | MULTIMATERIALES | `GT` | `C00067` | MULTIMATERIALES, SOCIEDAD ANONIMA |
| `MTM-2036043` | SOLAR GUATE (Energía Solar de Guatemala, S.A.) | `GT` | `C00086` | ENERGIA SOLAR DE GUATEMALA, SOCIEDAD ANONIMA |
| `MTM-2036502` | COTTONTEXTILE, S.A. - TEXTILASA | `GT` | `C00081` | COTTONTEXTILE, SOCIEDAD ANONIMA |
| `MTM-2036618` | MULTISERVICIOS STONE ART | `GT` | `C00087` | MULTISERVICIOS STONE ART, SOCIEDAD ANONIMA |

## Manual Review Before Write-Back

These still need a human check because the top BC candidate is ambiguous, weak, or visibly mismatched.

| ClickUp task | Customer | Market | Top BC candidate | Why review first |
| --- | --- | --- | --- | --- |
| `MTM-2021322` | GRUPO TEX MODAS | `GT` | `C00023` CORPORACION EXPERTISE, SOCIEDAD ANONIMA | Score is artificially high but the BC name does not match the ClickUp customer. |
| `MTM-2021956` | ALMACEN LA BODEGA | `GT` | `C00056` ALB IMPORTACIONES, SOCIEDAD ANONIMA | Could be a valid commercial alias, but not deterministic from current fields. |
| `MTM-2026256` | ABDITRANS - GT | `GT` | `C00003` GLORIA CARRERA BARRIOS | Current top candidate is not credible. |
| `MTM-2026471` | FERRECOMER, S.A. - EL ARENAL | `GT` | `C00022` FERRECOMER SOCIEDAD ANONIMA | Looks promising, but score is still below the safe write-back threshold. |
| `MTM-2027416` | AVERY DENNINSON | `MX` | `C00070` AGAVES DE SELECCION | Current top candidate is not credible. |
| `MTM-2028607` | INGRUP (Inyectores de plastico) | `GT` | `C00053` DISTRIBUIDORA DE MOTORES DEL ATLANTICO | Current top candidate is not credible. |
| `MTM-2035339` | Wine.com - Kywee | `MX` | `C00005` WEG MEXICO SA DE CV | Current top candidate is not credible. |
| `MTM-2035584` | EVCOPLASTICS DE MEXICO S DE RL DE CV | `MX` | `794` TRAMONTINA DE MEXICO, S.A. DE C.V. | Top candidate is clearly mismatched. |
| `MTM-2035593` | CORPORACION LB - LEBOLSHA | `GT` | `C00025` GIAI INNOVATIONS, SOCIEDAD ANONIMA | Current top candidate is not credible. |
| `MTM-2035634` | Agencias Way | `GT` | `C00046` AGENCIAS WAY, SOCIEDAD ANONIMA | Name alignment is good, but score is still low enough that a manual confirm is better. |
| `MTM-2035664` | FPK | `GT` | `C00001` ALCANCE INTEGRAL, SOCIEDAD ANÓNIMA | Current top candidate is not credible. |
| `MTM-2035674` | MAGNA MOTORS / Hyundai | `GT` | `C00095` MAGNA MOTORS GUATEMALA SOCIEDAD ANONIMA | Looks plausible, but score is still below the safe write-back threshold. |
| `MTM-2035675` | MOTOCOM, S.A. - MASESA | `GT` | `C00024` TEXMODAS SA | Current top candidate is not credible. |
| `MTM-2035777` | REPUESTOS ACQUARONI | `GT` | `C00054` RESPUESTOS TOTAL SA | Could be related, but the legal name is still too far from the ClickUp customer for blind write-back. |
| `MTM-2035728` | Wine.com | `MX` | `C00005` WEG MEXICO SA DE CV | Current top candidate is not credible. |
| `MTM-2037026` | MASTER AUTO | `GT` | `C00012` INDUSTRIA CENTROAMERICANA DE QUIMICOS FARMACEUTICOS SOCIEDAD ANONIMA | Current top candidate is not credible. |
| `MTM-2037911` | Textilasa | `GT` | `C00024` TEXMODAS SA | Could be related, but not deterministic from current fields. |
| `MTM-2038018` | The Best Music S A | `GT` | `C00005` PRODUCTOS MULTIPLES, S.A. | Current top candidate is not credible. |
| `MTM-2038110` | Grupo Andujar | `MX` | `C00020` GRUPO AMDOSA | Similar shape, but not safe enough for blind write-back. |

## Missing Market

These cannot be matched until `Owner Country/` is populated in ClickUp.

| ClickUp task | Customer | Needed field |
| --- | --- | --- |
| `MTM-2038558` | MTA Agentes corporativos de Carga MTA, S. A. | `Owner Country/` |
| `MTM-2038664` | ALTURISA | `Owner Country/` |
| `MTM-2038665` | PANACAFE DE GUATEMALA | `Owner Country/` |

## Recommended Next Moves

1. Bulk write back the `Ready For Write-Back` group into ClickUp.
2. Add a manual review queue for the `Manual Review Before Write-Back` group.
3. Require `Owner Country/` before a task can move into the BC sync flow.
4. Add a stronger BC key to ClickUp when known:
   - `Tax ID`
   - `Business Central Customer Number`
   - `Business Central Customer ID`
5. Tighten the matcher before full automation:
   - reward exact normalized name matches more heavily
   - penalize obvious mismatches between ClickUp name and BC legal name
   - prefer `Tax ID` and website/domain over fuzzy name-only matches
