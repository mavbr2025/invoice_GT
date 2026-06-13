from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from business_central_client.client import BusinessCentralClient
from clickup_integration.client import ClickUpClient
from clickup_integration.invoice_sync import InvoiceAutomationSettings


logger = logging.getLogger(__name__)

DEFAULT_INVOICE_PDF_FIELD_ID = "5d67859a-1ae0-4cda-9f57-2a89bf1ff259"


def resolve_invoice_pdf_field_id() -> str:
    pdf_field_id = os.getenv("CLICKUP_INVOICE_PDF_FIELD_ID", DEFAULT_INVOICE_PDF_FIELD_ID).strip()
    if not pdf_field_id:
        raise ValueError("CLICKUP_INVOICE_PDF_FIELD_ID is required for invoice PDF upload.")
    return pdf_field_id


def validate_invoice_pdf_field_on_task(
    clickup_summary: dict[str, Any],
    *,
    field_id: str | None = None,
) -> dict[str, Any]:
    resolved_field_id = field_id or resolve_invoice_pdf_field_id()
    field = _find_custom_field_by_id(clickup_summary.get("custom_fields") or {}, field_id=resolved_field_id)
    if not field:
        raise ValueError(
            "ClickUp task does not expose the Invoice to Client custom field "
            f"({resolved_field_id}). Confirm the token user has access to the field's parent "
            "space/folder/list before issuing invoices."
        )
    return field


def finalize_clickup_issued_invoices(
    *,
    clickup: ClickUpClient,
    bc_client: BusinessCentralClient,
    clickup_summary: dict[str, Any],
    invoice_result: dict[str, Any],
    settings: InvoiceAutomationSettings,
    workspace_id: str | None,
    mark_status: bool = True,
) -> dict[str, Any]:
    created_invoices = delivery_invoices_from_result(invoice_result)

    market = _resolve_delivery_market(invoice_result, settings=settings)
    resolved_workspace_id = workspace_id or clickup.settings.default_workspace_id
    if not resolved_workspace_id:
        raise ValueError("A ClickUp workspace ID is required to upload invoice PDFs to a custom field.")

    pdf_field_id = resolve_invoice_pdf_field_id()
    validate_invoice_pdf_field_on_task(clickup_summary, field_id=pdf_field_id)

    uploaded_documents, pdf_field_update = _upload_invoice_pdfs_to_clickup_field(
        clickup=clickup,
        bc_client=bc_client,
        task_id=clickup_summary["task_id"],
        workspace_id=resolved_workspace_id,
        field_id=pdf_field_id,
        created_invoices=created_invoices,
        market=market,
        existing_attachment_ids=_existing_file_field_attachment_ids(
            clickup_summary.get("custom_fields") or {},
            field_id=pdf_field_id,
        ),
    )
    comment_text = build_issued_invoice_comment(
        bc_client=bc_client,
        market=market,
        created_invoices=created_invoices,
        uploaded_documents=uploaded_documents,
    )
    comment = clickup.create_task_comment(
        clickup_summary["task_id"],
        comment_text=comment_text,
        notify_all=False,
    )
    final_status_update = None
    if mark_status:
        final_status_update = mark_clickup_invoice_facturada(
            clickup=clickup,
            clickup_summary=clickup_summary,
            settings=settings,
        )

    return {
        "pdf_field_id": pdf_field_id,
        "uploaded_documents": uploaded_documents,
        "pdf_field_update": pdf_field_update,
        "comment": comment,
        "comment_text": comment_text,
        "final_status_update": final_status_update,
    }


def delivery_invoices_from_result(invoice_result: dict[str, Any]) -> list[dict[str, Any]]:
    finalized_invoices = invoice_result.get("finalized_invoices") or []
    delivery_invoices: list[dict[str, Any]] = []
    for finalized in finalized_invoices:
        if not isinstance(finalized, dict):
            continue
        invoice = finalized.get("posted_invoice_after_stamp") or {}
        stamp_row = finalized.get("custom_api_row_after_stamp") or {}
        stamp_status = str(stamp_row.get("electronicDocumentStatus") or "").strip().lower()
        if stamp_status != "stamp received":
            raise ValueError(
                "Invoice delivery requires every posted invoice to have FEL status Stamp Received."
            )
        if not invoice.get("id") or not invoice.get("number"):
            raise ValueError("Invoice delivery result is missing a posted invoice id or number.")
        delivery_invoices.append(
            {
                **invoice,
                "invoice_group": finalized.get("invoice_group") or invoice.get("invoice_group"),
                "externalDocumentNumber": finalized.get("externalDocumentNumber")
                or invoice.get("externalDocumentNumber"),
            }
        )

    if delivery_invoices:
        return delivery_invoices

    created_invoices = invoice_result.get("created_invoices") or []
    if invoice_result.get("status") == "applied" and created_invoices:
        return list(created_invoices)

    raise ValueError(
        "Invoice delivery requires either an applied invoice result with created_invoices "
        "or a finalized posted-invoice result with FEL status Stamp Received."
    )


def _resolve_delivery_market(
    invoice_result: dict[str, Any],
    *,
    settings: InvoiceAutomationSettings,
) -> str:
    candidates = [
        invoice_result.get("market"),
        (invoice_result.get("preview") or {}).get("market")
        if isinstance(invoice_result.get("preview"), dict)
        else None,
        (invoice_result.get("live_summary") or {}).get("market")
        if isinstance(invoice_result.get("live_summary"), dict)
        else None,
        settings.supported_market,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip().upper()
        if value:
            return value
    raise ValueError("Invoice delivery could not resolve the Business Central market.")


def mark_clickup_invoice_facturada(
    *,
    clickup: ClickUpClient,
    clickup_summary: dict[str, Any],
    settings: InvoiceAutomationSettings,
) -> dict[str, Any]:
    return _set_invoice_status(
        clickup=clickup,
        clickup_summary=clickup_summary,
        settings=settings,
        target_status=os.getenv("CLICKUP_INVOICE_FINAL_STATUS", "Facturada").strip() or "Facturada",
    )


def build_issued_invoice_comment(
    *,
    bc_client: BusinessCentralClient,
    market: str,
    created_invoices: list[dict[str, Any]],
    uploaded_documents: list[dict[str, Any]],
) -> str:
    company = bc_client.get_company_metadata(market=market)
    company_name = (company or {}).get("name") or (company or {}).get("displayName") or ""
    uploaded_by_invoice_id = {
        document.get("invoice_id"): document for document in uploaded_documents if document.get("invoice_id")
    }

    lines = ["Business Central invoices issued:"]
    for invoice in created_invoices:
        invoice_group = str(invoice.get("invoice_group") or "ALL").upper()
        invoice_number = invoice.get("number") or ""
        invoice_id = invoice.get("id") or ""
        link = (
            bc_client.build_sales_invoice_url(company_name=company_name, invoice_number=str(invoice_number))
            if company_name and invoice_number
            else ""
        )
        uploaded = uploaded_by_invoice_id.get(invoice_id) or {}
        lines.extend(
            [
                "",
                f"{invoice_group} invoice",
                f"- Number: {invoice_number}",
                f"- ID: {invoice_id}",
                f"- Link: {link or 'Unavailable'}",
                f"- PDF: {uploaded.get('file_name') or 'Unavailable'}",
            ]
        )
    return "\n".join(lines)


def _upload_invoice_pdfs_to_clickup_field(
    *,
    clickup: ClickUpClient,
    bc_client: BusinessCentralClient,
    task_id: str,
    workspace_id: str,
    field_id: str,
    created_invoices: list[dict[str, Any]],
    market: str,
    existing_attachment_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    uploaded_documents: list[dict[str, Any]] = []
    new_attachment_ids: list[str] = []
    for invoice in created_invoices:
        invoice_id = str(invoice.get("id") or "").strip()
        if not invoice_id:
            raise ValueError("Created invoice is missing its Business Central id.")

        invoice_number = str(invoice.get("number") or invoice_id).strip()
        invoice_group = str(invoice.get("invoice_group") or "").strip().upper()
        file_stem = invoice.get("externalDocumentNumber") or invoice_number
        file_name = f"{file_stem}.pdf"
        pdf_content = _download_invoice_pdf_with_retry(
            bc_client=bc_client,
            invoice_id=invoice_id,
            market=market,
        )
        temp_path = _write_temp_pdf(pdf_content)
        try:
            upload_result = clickup.upload_custom_field_attachment(
                workspace_id,
                field_id,
                temp_path,
                file_name=file_name,
                mime_type="application/pdf",
            )
        finally:
            temp_path.unlink(missing_ok=True)

        attachment_id = _extract_attachment_id(upload_result)
        if not attachment_id:
            raise ValueError(f"ClickUp did not return an attachment id for {file_name}.")
        new_attachment_ids.append(attachment_id)
        uploaded_documents.append(
            {
                "invoice_group": invoice_group,
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "file_name": file_name,
                "attachment_id": attachment_id,
                "upload_result": upload_result,
            }
        )

    combined_attachment_ids = [*existing_attachment_ids, *new_attachment_ids]
    pdf_field_update = clickup.set_task_file_custom_field_attachments(
        task_id,
        field_id,
        combined_attachment_ids,
    )
    return uploaded_documents, pdf_field_update


def _download_invoice_pdf_with_retry(
    *,
    bc_client: BusinessCentralClient,
    invoice_id: str,
    market: str,
    attempts: int = 3,
    delay_seconds: float = 2.0,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            pdf_content = bc_client.get_sales_invoice_pdf_content(invoice_id, market=market)
            if not pdf_content:
                raise ValueError(f"Business Central returned an empty PDF for invoice {invoice_id}.")
            return pdf_content
        except Exception as exc:  # pragma: no cover - retry behavior is runtime defensive code
            last_error = exc
            if attempt == attempts:
                break
            logger.info(
                "BC invoice PDF not ready invoice_id=%s attempt=%s/%s error=%s",
                invoice_id,
                attempt,
                attempts,
                exc,
            )
            time.sleep(delay_seconds)
    raise RuntimeError(f"Could not download Business Central invoice PDF for {invoice_id}: {last_error}")


def _write_temp_pdf(content: bytes) -> Path:
    with NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(content)
        return Path(handle.name)


def _extract_attachment_id(upload_result: dict[str, Any]) -> str:
    candidates: list[Any] = [
        upload_result.get("id"),
        upload_result.get("attachment_id"),
        (upload_result.get("attachment") or {}).get("id")
        if isinstance(upload_result.get("attachment"), dict)
        else None,
        (upload_result.get("data") or {}).get("id") if isinstance(upload_result.get("data"), dict) else None,
    ]
    attachments = upload_result.get("attachments")
    if isinstance(attachments, list) and attachments:
        first = attachments[0]
        if isinstance(first, dict):
            candidates.append(first.get("id"))

    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return ""


def _existing_file_field_attachment_ids(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_id: str,
) -> list[str]:
    field = _find_custom_field_by_id(custom_fields, field_id=field_id)
    value = (field or {}).get("value")
    if not isinstance(value, list):
        return []

    ids = []
    for item in value:
        if not isinstance(item, dict):
            continue
        attachment_id = item.get("id")
        if attachment_id is not None and str(attachment_id).strip():
            ids.append(str(attachment_id).strip())
    return ids


def _find_custom_field_by_id(
    custom_fields: dict[str, dict[str, Any]],
    *,
    field_id: str,
) -> dict[str, Any] | None:
    for details in custom_fields.values():
        if details.get("id") == field_id:
            return details
    return None


def _set_invoice_status(
    *,
    clickup: ClickUpClient,
    clickup_summary: dict[str, Any],
    settings: InvoiceAutomationSettings,
    target_status: str,
) -> dict[str, Any]:
    custom_fields = clickup_summary.get("custom_fields") or {}
    for field_name in settings.invoice_status_field_names:
        field = custom_fields.get(field_name)
        if not field:
            continue
        option_id = _dropdown_option_id(field, target_status)
        if option_id is None:
            raise ValueError(f"Could not resolve ClickUp invoice status option: {target_status}")
        return clickup.set_task_custom_field_value(clickup_summary["task_id"], field["id"], option_id)
    raise ValueError("Could not find the ClickUp invoice status field to mark the task as Facturada.")


def _dropdown_option_id(field: dict[str, Any], option_name: str) -> str | int | None:
    target = _normalize_status(option_name)
    for option in (field.get("type_config") or {}).get("options", []):
        if _normalize_status(option.get("name")) == target:
            return option.get("id") or option.get("orderindex")
    return None


def _normalize_status(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())
