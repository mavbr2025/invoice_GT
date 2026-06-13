from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POSTED_INVOICE_API = (
    ROOT
    / "bc_extension"
    / "customer_invoicing_sync"
    / "src"
    / "PostedInvoiceFelDescriptionApi.Page.al"
)


def _send_fel_invoice_body() -> str:
    source = POSTED_INVOICE_API.read_text(encoding="utf-8")
    start = source.index("procedure SendFelInvoice")
    end = source.index("[ServiceEnabled]", start + 1)
    return source[start:end]


def test_send_fel_invoice_fails_closed_before_legacy_provider_send() -> None:
    body = _send_fel_invoice_body()

    assert "Error(" in body
    assert "LEGACY FEL CUSTOMER SEND IS DISABLED" in body
    assert "EnvioFactura" not in body
