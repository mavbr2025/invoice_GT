from scripts.replace_gt_invoice_split_int_charges_once import (
    _retain_non_replaced_invoice_attachments,
)


def test_retain_non_replaced_invoice_attachments_keeps_nat_pdf() -> None:
    fields = {
        "Invoice to Client": {
            "id": "5d67859a-1ae0-4cda-9f57-2a89bf1ff259",
            "value": [
                {"id": "old-int", "title": "MTMLXGT-25745-INT.pdf"},
                {"id": "nat", "title": "MTMLXGT-25745-NAT.pdf"},
            ],
        }
    }

    result = _retain_non_replaced_invoice_attachments(
        fields,
        replaced_invoice_number="GTFVR0004044",
        replaced_external_reference="MTMLXGT-25745-INT",
    )

    assert result["Invoice to Client"]["value"] == [
        {"id": "nat", "title": "MTMLXGT-25745-NAT.pdf"}
    ]
