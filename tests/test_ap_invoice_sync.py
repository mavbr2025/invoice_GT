from io import BytesIO

from reportlab.pdfgen import canvas

from clickup_integration.ap_invoice_sync import (
    APPurchaseInvoiceSettings,
    APPurchaseVendorMapping,
    apply_clickup_bc_purchase_invoice,
    build_clickup_ap_transfer_comment,
    prepare_clickup_bc_purchase_invoice_preview,
)


class FakeBC:
    def __init__(self) -> None:
        self.created_invoice = None
        self.created_lines = []

    def find_entities(self, entity_name, *, filters, top=1, company_id=None, market=None):
        if entity_name == "vendors" and filters == "number eq 'P00115'":
            return [
                {
                    "id": "vendor-id",
                    "number": "P00115",
                    "displayName": "OCEAN NETWORK EXPRESS (LOCAL)",
                }
            ]
        if entity_name == "purchaseInvoices" and filters == "number eq 'GTFCR05996'":
            return [
                {
                    "id": "purchase-invoice-id",
                    "number": "GTFCR05996",
                    "invoiceDate": "2026-05-16",
                    "postingDate": "2026-05-16",
                    "dueDate": "2026-05-31",
                    "vendorInvoiceNumber": "NCO-35537",
                    "vendorNumber": "P00115",
                    "vendorName": "OCEAN NETWORK EXPRESS (LOCAL)",
                    "currencyCode": "USD",
                    "totalAmountIncludingTax": 12546,
                    "status": "Open",
                }
            ]
        return []

    def get_purchase_invoice_lines(self, purchase_invoice_id, *, company_id=None, market=None):
        assert purchase_invoice_id == "purchase-invoice-id"
        return [
            {
                "lineObjectNumber": "GTO00000115",
                "description": "CCC,CMD,CRO,CSS,DOF,GAT,OBS,OFT,SCC,THD",
                "unitCost": 12546,
                "taxCode": "NOIVA",
            }
        ]

    def create_purchase_invoice(self, payload, *, company_id=None, market=None):
        self.created_invoice = payload
        return {
            "id": "new-purchase-invoice-id",
            "number": "GTFCRNEW",
            **payload,
        }

    def create_purchase_invoice_line(self, purchase_invoice_id, payload, *, company_id=None, market=None):
        line = {"purchase_invoice_id": purchase_invoice_id, **payload}
        self.created_lines.append(line)
        return line


def make_settings() -> APPurchaseInvoiceSettings:
    return APPurchaseInvoiceSettings(
        supported_market="GT",
        supported_currency="USD",
        approved_finops_labels=("PROCEDE A PAGO",),
        invoice_number_field_names=("Invoice Number",),
        invoice_date_field_names=("🚢 Invoice date",),
        total_amount_field_names=("🚢 Total USD",),
        master_bl_field_names=("Master BL Number/",),
        finops_status_field_names=("Validación FINOPS",),
        vendor_mappings=(
            APPurchaseVendorMapping(
                list_id="901709663424",
                list_name="AP ONE GT USD",
                vendor_number="P00115",
                item_number="GTO00000115",
                tax_code="NOIVA",
                unit_of_measure_code="SER",
            ),
        ),
    )


def clickup_summary(*, finops_value=1):
    return {
        "task_id": "86e1drc8v",
        "name": "NCO-35537",
        "status": "dispute",
        "list": {"id": "901709663424", "name": "AP ONE GT USD"},
        "custom_fields": {
            "Master BL Number/": {
                "id": "8f9d6623-4723-482b-84ba-180dfba29643",
                "type": "short_text",
                "value": "ONEYNB6BF4346400",
            },
            "Validación FINOPS": {
                "id": "66f45c32-3c1e-4cbd-b11d-14a9d45a7d6b",
                "type": "drop_down",
                "value": finops_value,
                "type_config": {
                    "options": [
                        {"id": "ok", "name": "PROCEDE A PAGO", "orderindex": 0},
                        {"id": "dispute", "name": "EN DISPUTA", "orderindex": 1},
                    ]
                },
            },
            "🚢 Invoice date": {
                "id": "1a25eecc-798d-4604-97b9-d0b5eb3ae260",
                "type": "date",
                "value": "1778839200000",
            },
            "🚢 Total USD": {
                "id": "2bd46db8-1155-4994-8cc3-4904cc8906d6",
                "type": "currency",
                "value": "12546",
            },
            "Invoice Number": {
                "id": "2f64d081-fede-48ea-900f-b4944b60d61b",
                "type": "short_text",
                "value": "NCO-35537",
            },
        },
    }


def one_nco_pdf() -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output)
    y = 780
    for line in (
        "NOTA DE COBRO",
        "No. NCO-35537",
        "CLIENTE: BL:",
        "MTM LOGIX GUATEMALA, SOCIEDAD ANONIMA ONEYNB6BF4346400",
        "FECHA ATRAQUE: 2026-05-16",
        "CARGOS",
        "CCC USD 200.00",
        "CMD USD 1,040.00",
        "CRO USD 160.00",
        "CSS USD 60.00",
        "DOF USD 70.00",
        "GAT USD 160.00",
        "OBS USD 1,280.00",
        "OFT USD 8,812.00",
        "SCC USD 64.00",
        "THD USD 700.00",
        "Total USD 12,546.00",
    ):
        pdf.drawString(36, y, line)
        y -= 14
    pdf.save()
    return output.getvalue()


def test_prepare_purchase_invoice_preview_extracts_pdf_and_compares_to_bc() -> None:
    result = prepare_clickup_bc_purchase_invoice_preview(
        clickup_summary=clickup_summary(),
        bc_client=FakeBC(),
        settings=make_settings(),
        pdf_contents=[one_nco_pdf()],
        compare_invoice_number="GTFCR05996",
    )

    assert result["status"] == "dry_run_ready"
    assert result["payment_gate"]["can_pay"] is False
    assert result["vendor_invoice_number"] == "NCO-35537"
    assert result["source_dates"]["clickup_invoice_date"] == "2026-05-15"
    assert result["source_dates"]["pdf_berthing_date"] == "2026-05-16"
    assert result["proposed_bc_payload"]["invoiceDate"] == "2026-05-16"
    assert result["proposed_bc_payload"]["vendorNumber"] == "P00115"
    assert result["proposed_bc_line_payloads"][0]["lineObjectNumber"] == "GTO00000115"
    assert result["proposed_bc_line_payloads"][0]["description"] == "CCC,CMD,CRO,CSS,DOF,GAT,OBS,OFT,SCC,THD"
    assert result["proposed_bc_comment_line_payloads"][0] == {
        "lineType": "Comment",
        "description": "ClickUp integration transfer: 86e1drc8v / NCO-35537",
    }
    assert result["comparison"]["status"] == "matched"


def test_prepare_purchase_invoice_preview_allows_write_only_for_approved_finops() -> None:
    result = prepare_clickup_bc_purchase_invoice_preview(
        clickup_summary=clickup_summary(finops_value=0),
        bc_client=FakeBC(),
        settings=make_settings(),
        pdf_contents=[one_nco_pdf()],
    )

    assert result["status"] == "dry_run_ready"
    assert result["payment_gate"]["can_pay"] is True


def test_apply_purchase_invoice_creates_invoice_even_when_payment_is_disputed() -> None:
    bc = FakeBC()

    result = apply_clickup_bc_purchase_invoice(
        clickup_summary=clickup_summary(),
        bc_client=bc,
        settings=make_settings(),
        pdf_contents=[one_nco_pdf()],
    )

    assert result["status"] == "applied"
    assert result["payment_gate"]["can_pay"] is False
    assert result["created_invoice"]["number"] == "GTFCRNEW"
    assert bc.created_lines[0]["lineObjectNumber"] == "GTO00000115"
    assert bc.created_lines[1]["lineType"] == "Comment"
    assert "ClickUp integration transfer" in bc.created_lines[1]["description"]
    assert result["bc_comment_warnings"] == []


def test_build_clickup_transfer_comment_includes_bc_invoice_and_payment_status() -> None:
    bc = FakeBC()
    result = apply_clickup_bc_purchase_invoice(
        clickup_summary=clickup_summary(),
        bc_client=bc,
        settings=make_settings(),
        pdf_contents=[one_nco_pdf()],
    )

    comment = build_clickup_ap_transfer_comment(result)

    assert "AP invoice transferred to Business Central via integration." in comment
    assert "BC purchase invoice: GTFCRNEW" in comment
    assert "Vendor invoice: NCO-35537" in comment
    assert "FINOPS status: EN DISPUTA" in comment
