from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POSTED_INVOICE_API = (
    ROOT
    / "bc_extension"
    / "customer_invoicing_sync"
    / "src"
    / "PostedInvoiceFelDescriptionApi.Page.al"
)
EMAIL_MGT = (
    ROOT
    / "bc_extension"
    / "customer_invoicing_sync"
    / "src"
    / "MtmInvoiceCustomerEmailMgt.Codeunit.al"
)
EMAIL_AUDIT = (
    ROOT
    / "bc_extension"
    / "customer_invoicing_sync"
    / "src"
    / "MtmInvoiceEmailAudit.Table.al"
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


def test_native_invoice_email_requires_exact_scenario_account_and_sent_evidence() -> None:
    source = EMAIL_MGT.read_text(encoding="utf-8")

    assert "IsThereEmailAccountSetForScenario" in source
    assert "GetEmailAccount" in source
    assert "consuelo@mtmlogix.com" in source
    assert "Email.Send(EmailMessage, SenderAccount)" in source
    assert "GetSentEmailsForRecord" in source
    assert "GetMessageId()" in source
    assert "GetAccountId()" in source
    assert "Document-Mailing" not in source


def test_email_audit_persists_native_message_and_verification_state() -> None:
    source = EMAIL_AUDIT.read_text(encoding="utf-8")

    assert '"BC Email Message Id"' in source
    assert '"Sender Account Id"' in source
    assert '"Native Send Accepted"' in source
    assert '"Native Sent Verified"' in source


def test_failed_email_audit_commits_before_api_error() -> None:
    source = EMAIL_MGT.read_text(encoding="utf-8")
    start = source.index("local procedure FailAudit")
    end = source.index("[TryFunction]", start)
    body = source[start:end]

    assert body.index("Commit();") < body.index("Error(ErrorText);")
