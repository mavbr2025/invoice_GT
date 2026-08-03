from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings


MARKET = "GT"
TEST_RECIPIENT = "mario@mtmlogix.com"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Send one existing FEL-stamped GT invoice through the internal BC email canary. "
            "This never creates or posts an invoice."
        )
    )
    parser.add_argument(
        "--invoice-number",
        help="Existing posted invoice number. Omit to select one random eligible invoice.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually send the internal canary. Without this flag the command is read-only.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Allow one new canary only when the existing BC evidence is an explicit Failed "
            "outbox record. Queued, unknown, timed-out, and sent states are never retried."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional dotenv file containing the Business Central connection settings.",
    )
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file, override=True)

    bc = BusinessCentralClient(Settings.from_env())
    fel_row = _select_invoice(bc, invoice_number=args.invoice_number)
    invoice_number = str(fel_row.get("number") or "").strip()
    posted_invoice = bc.get_posted_sales_invoice_by_number(invoice_number, market=MARKET)
    if not posted_invoice:
        raise SystemExit(f"Posted Business Central invoice {invoice_number} was not found.")
    if str(posted_invoice.get("status") or "").strip().lower() == "canceled":
        raise SystemExit(f"Posted Business Central invoice {invoice_number} is canceled.")

    result: dict[str, Any] = {
        "status": "ready_to_send" if not args.apply else "sending",
        "creates_invoice": False,
        "test_recipient": TEST_RECIPIENT,
        "invoice": {
            "id": posted_invoice.get("id"),
            "number": invoice_number,
            "customerNumber": posted_invoice.get("customerNumber"),
            "customerName": posted_invoice.get("customerName"),
            "externalDocumentNumber": posted_invoice.get("externalDocumentNumber"),
            "currencyCode": posted_invoice.get("currencyCode"),
            "totalAmountIncludingTax": posted_invoice.get("totalAmountIncludingTax"),
            "felStatus": fel_row.get("electronicDocumentStatus"),
        },
    }
    evidence_before = _get_bc_evidence(bc, invoice_number=invoice_number)
    result["bc_evidence_before"] = evidence_before

    if evidence_before.startswith("Sent|"):
        result["status"] = "already_sent_and_native_bc_evidence_verified"
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return
    if evidence_before.startswith("Outbox|"):
        outbox_status = _evidence_value(evidence_before, "Status").lower()
        if not args.apply:
            result["status"] = (
                "ready_to_retry_explicit_failed_outbox"
                if outbox_status == "failed"
                else "blocked_existing_bc_outbox_message"
            )
        elif outbox_status != "failed":
            result["status"] = "blocked_existing_bc_outbox_message"
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            raise SystemExit(2)
        elif not args.retry_failed:
            result["status"] = "blocked_failed_outbox_requires_explicit_retry_flag"
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            raise SystemExit(2)

    if not args.apply:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return

    try:
        bc.send_posted_invoice_test_email_to_mario(str(fel_row["id"]), market=MARKET)
    except requests.Timeout:
        evidence_after = _wait_for_bc_evidence(bc, invoice_number=invoice_number, timeout_seconds=90)
        result["bc_evidence_after"] = evidence_after
        if evidence_after.startswith("Sent|"):
            result["status"] = "sent_and_native_bc_evidence_verified_after_client_timeout"
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return
        result["status"] = (
            "blocked_bc_outbox_after_client_timeout"
            if evidence_after.startswith("Outbox|")
            else "unresolved_after_client_timeout_no_retry"
        )
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        raise SystemExit(2)

    evidence_after = _wait_for_bc_evidence(bc, invoice_number=invoice_number, timeout_seconds=30)
    result["bc_evidence_after"] = evidence_after
    if not evidence_after.startswith("Sent|"):
        result["status"] = "send_returned_without_native_bc_evidence_no_retry"
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        raise SystemExit(2)
    result["status"] = "sent_and_native_bc_evidence_verified"
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


def _select_invoice(
    bc: BusinessCentralClient,
    *,
    invoice_number: str | None,
) -> dict[str, Any]:
    if invoice_number:
        row = bc.get_posted_invoice_fel_description_by_number(invoice_number, market=MARKET)
        if not row:
            raise SystemExit(f"FEL row for invoice {invoice_number} was not found.")
        rows = [row]
    else:
        rows = bc.get_posted_invoice_fel_descriptions(
            filters="cancelled eq false",
            top=100,
            order_by="systemModifiedAt desc",
            market=MARKET,
        )

    eligible = [
        row
        for row in rows
        if str(row.get("electronicDocumentStatus") or "").strip().upper() == "STAMP RECEIVED"
        and not bool(row.get("cancelled"))
        and str(row.get("number") or "").strip()
    ]
    if not eligible:
        raise SystemExit("No eligible non-canceled GT invoice with FEL status Stamp Received was found.")
    recent_candidates = sorted(eligible, key=_invoice_sequence, reverse=True)[:20]
    return secrets.choice(recent_candidates)


def _invoice_sequence(row: dict[str, Any]) -> int:
    digits = "".join(character for character in str(row.get("number") or "") if character.isdigit())
    return int(digits or 0)


def _wait_for_bc_evidence(
    bc: BusinessCentralClient,
    *,
    invoice_number: str,
    timeout_seconds: int,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    evidence = "NotFound"
    while time.monotonic() < deadline:
        evidence = _get_bc_evidence(bc, invoice_number=invoice_number)
        if evidence:
            if evidence.startswith(("Sent|", "Outbox|", "SentWrongAccount|", "ConfigurationError|")):
                return evidence
        time.sleep(3)
    return evidence


def _get_bc_evidence(bc: BusinessCentralClient, *, invoice_number: str) -> str:
    row = bc.get_invoice_email_canary_evidence_by_number(invoice_number, market=MARKET)
    if not row:
        return "Unavailable"
    return str(row.get("evidence") or "Unavailable")


def _evidence_value(evidence: str, key: str) -> str:
    prefix = f"{key}="
    for component in evidence.split("|"):
        if component.startswith(prefix):
            return component[len(prefix) :].strip()
    return ""


if __name__ == "__main__":
    main()
