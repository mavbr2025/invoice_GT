from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DEFAULT_DB = "output/reconciliation_2026.sqlite3"
DEFAULT_CSV = "output/reconciliation_best_matches_2026.csv"
DEFAULT_JSON = "output/reconciliation_best_matches_2026.json"
DEFAULT_MD = "output/reconciliation_best_matches_2026.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score best BC invoice to ClickUp matches.")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--json", default=DEFAULT_JSON)
    parser.add_argument("--md", default=DEFAULT_MD)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    invoices = [dict(row) for row in conn.execute("SELECT * FROM bc_invoices ORDER BY posting_date, number")]
    tasks = load_clickup_tasks(conn)

    revenue_tasks = [task for task in tasks if task["source_label"] == "clickup_revenue_invoices"]
    shipment_tasks = [task for task in tasks if task["source_label"] == "shipment_invoicing"]

    rows: list[dict[str, Any]] = []
    for invoice in invoices:
        revenue_match = best_revenue_match(invoice, revenue_tasks)
        shipment_match = best_shipment_match(invoice, shipment_tasks)
        rows.append(build_result_row(invoice, revenue_match, shipment_match))

    write_csv(Path(args.csv), rows)
    write_json(Path(args.json), rows)
    write_markdown(Path(args.md), rows)
    print_summary(rows, Path(args.csv), Path(args.json), Path(args.md))


def load_clickup_tasks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    tasks = [dict(row) for row in conn.execute("SELECT * FROM clickup_tasks")]
    field_rows = conn.execute(
        """
        SELECT task_id, field_name, value_text, resolved_label
        FROM clickup_task_fields
        """
    )
    fields_by_task: dict[str, dict[str, str]] = {}
    for row in field_rows:
        value = row["resolved_label"] or row["value_text"]
        if value is None:
            continue
        fields_by_task.setdefault(row["task_id"], {})[row["field_name"]] = str(value)

    for task in tasks:
        fields = fields_by_task.get(task["task_id"], {})
        task["fields"] = fields
        task["search_text"] = normalize_text(
            " ".join(
                [
                    task.get("task_id") or "",
                    task.get("custom_id") or "",
                    task.get("name") or "",
                    task.get("status") or "",
                    " ".join(fields.values()),
                ]
            )
        )
    return tasks


def best_revenue_match(invoice: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [score_revenue_task(invoice, task) for task in tasks]
    scored = [row for row in scored if row["score"] > 0]
    if not scored:
        return None
    return sorted(scored, key=lambda row: (row["score"], row["amount_delta"] == 0), reverse=True)[0]


def score_revenue_task(invoice: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    invoice_no = invoice.get("number") or ""
    score = 0
    reasons: list[str] = []

    if task.get("name") == invoice_no:
        score += 100
        reasons.append("exact_invoice_task_name")
    elif invoice_no and invoice_no in (task.get("name") or ""):
        score += 80
        reasons.append("invoice_number_in_task_name")
    else:
        return {
            "score": 0,
            "task": task,
            "reasons": [],
            "amount_delta": None,
            "customer_similarity": 0,
        }

    po = field(task, "PO")
    if po and invoice.get("external_document_number") and normalize_text(po) == normalize_text(invoice["external_document_number"]):
        score += 20
        reasons.append("po_matches_external_document")

    customer_score = similarity(invoice.get("customer_name"), field(task, "Customer"))
    if customer_score >= 0.92:
        score += 15
        reasons.append("customer_name_matches")
    elif customer_score >= 0.75:
        score += 8
        reasons.append("customer_name_similar")

    amount_delta = amount_difference(invoice, task)
    if amount_delta == 0:
        score += 10
        reasons.append("amount_matches")
    elif amount_delta is not None and amount_delta <= 1:
        score += 5
        reasons.append("amount_within_1")

    return {
        "score": score,
        "task": task,
        "reasons": reasons,
        "amount_delta": amount_delta,
        "customer_similarity": round(customer_score, 4),
    }


def best_shipment_match(invoice: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [score_shipment_task(invoice, task) for task in tasks]
    scored = [row for row in scored if row["score"] > 0]
    if not scored:
        return None
    return sorted(scored, key=lambda row: row["score"], reverse=True)[0]


def score_shipment_task(invoice: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    ref = invoice.get("external_document_number") or ""
    customer = invoice.get("customer_name") or ""
    search_text = task.get("search_text") or ""
    normalized_ref = normalize_text(ref)
    score = 0
    reasons: list[str] = []

    mtm_refs = re.findall(r"\bMTMLXGT-\d+\b", ref, flags=re.IGNORECASE)
    for mtm_ref in mtm_refs:
        if normalize_text(mtm_ref) in search_text:
            score += 100
            reasons.append(f"mtm_reference:{mtm_ref.upper()}")

    if normalized_ref and normalized_ref in search_text:
        score += 70
        reasons.append("external_document_full_text_match")

    for key in ("PO/", "Booking number/", "Master BL Number/", "Carrier/"):
        value = field(task, key)
        if value and normalized_ref and normalize_text(value) == normalized_ref:
            score += 60
            reasons.append(f"{key}_exact_reference_match")

    for token in reference_tokens(ref):
        if token in search_text:
            score += 12
            reasons.append(f"reference_token:{token}")

    task_name_score = similarity(ref, task.get("name"))
    if task_name_score >= 0.9:
        score += 35
        reasons.append("task_name_similar_to_reference")
    elif task_name_score >= 0.75:
        score += 20
        reasons.append("task_name_partially_similar_to_reference")

    consignee = field(task, "Invoice to (Consignee's name)")
    customer_score = similarity(customer, consignee)
    if customer_score >= 0.9:
        score += 20
        reasons.append("customer_matches_consignee")
    elif customer_score >= 0.75:
        score += 10
        reasons.append("customer_similar_to_consignee")

    return {
        "score": score,
        "task": task,
        "reasons": reasons,
        "customer_similarity": round(customer_score, 4),
        "reference_similarity": round(task_name_score, 4),
    }


def build_result_row(
    invoice: dict[str, Any],
    revenue_match: dict[str, Any] | None,
    shipment_match: dict[str, Any] | None,
) -> dict[str, Any]:
    revenue_task = (revenue_match or {}).get("task") or {}
    shipment_task = (shipment_match or {}).get("task") or {}
    return {
        "bc_invoice_no": invoice.get("number"),
        "posting_date": invoice.get("posting_date"),
        "bc_customer_number": invoice.get("customer_number"),
        "bc_customer_name": invoice.get("customer_name"),
        "currency_code": invoice.get("currency_code"),
        "external_document_number": invoice.get("external_document_number"),
        "bc_total_amount": invoice.get("total_amount"),
        "revenue_match_score": (revenue_match or {}).get("score", 0),
        "revenue_match_confidence": confidence((revenue_match or {}).get("score", 0), high=100, medium=80),
        "revenue_task_id": revenue_task.get("task_id"),
        "revenue_task_name": revenue_task.get("name"),
        "revenue_task_url": revenue_task.get("url"),
        "revenue_amount_delta": (revenue_match or {}).get("amount_delta"),
        "revenue_match_reasons": "; ".join((revenue_match or {}).get("reasons", [])),
        "shipment_match_score": (shipment_match or {}).get("score", 0),
        "shipment_match_confidence": confidence((shipment_match or {}).get("score", 0), high=90, medium=50),
        "shipment_task_id": shipment_task.get("task_id"),
        "shipment_custom_id": shipment_task.get("custom_id"),
        "shipment_task_name": shipment_task.get("name"),
        "shipment_task_status": shipment_task.get("status"),
        "shipment_task_url": shipment_task.get("url"),
        "shipment_match_reasons": "; ".join((shipment_match or {}).get("reasons", [])),
    }


def amount_difference(invoice: dict[str, Any], task: dict[str, Any]) -> float | None:
    currency = (invoice.get("currency_code") or "").upper()
    field_name = "Total Invoice (USD)" if currency == "USD" else "Total Invoice (GTQ)"
    raw = field(task, field_name)
    if not raw:
        return None
    try:
        return abs(float(invoice.get("total_amount") or 0) - float(raw))
    except (TypeError, ValueError):
        return None


def confidence(score: int | float, *, high: int, medium: int) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def field(task: dict[str, Any], name: str) -> str | None:
    return (task.get("fields") or {}).get(name)


def normalize_text(value: Any) -> str:
    value = str(value or "").upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return " ".join(value.split())


def reference_tokens(value: str) -> list[str]:
    normalized = normalize_text(value)
    tokens = [token for token in normalized.split() if len(token) >= 5]
    return list(dict.fromkeys(tokens))


def similarity(left: Any, right: Any) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    revenue_high = sum(1 for row in rows if row["revenue_match_confidence"] == "high")
    shipment_high = sum(1 for row in rows if row["shipment_match_confidence"] == "high")
    shipment_medium = sum(1 for row in rows if row["shipment_match_confidence"] == "medium")
    lines = [
        "# Reconciliation Best Matches",
        "",
        f"- BC invoices reviewed: {total}",
        f"- High-confidence ClickUp Revenue invoice matches: {revenue_high}",
        f"- High-confidence shipment matches: {shipment_high}",
        f"- Medium-confidence shipment matches: {shipment_medium}",
        "",
        "## Best Shipment Matches",
        "",
        "| BC Invoice | Customer | Reference | Amount | Shipment Match | Score | Reasons |",
        "| --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in sorted(rows, key=lambda r: r["shipment_match_score"], reverse=True)[:50]:
        lines.append(
            "| {bc_invoice_no} | {bc_customer_name} | {external_document_number} | {bc_total_amount} | {shipment_task_name} | {shipment_match_score} | {shipment_match_reasons} |".format(
                **{key: md_cell(value) for key, value in row.items()}
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def print_summary(rows: list[dict[str, Any]], csv_path: Path, json_path: Path, md_path: Path) -> None:
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"BC invoices reviewed: {len(rows)}")
    for prefix in ("revenue", "shipment"):
        for level in ("high", "medium", "low", "none"):
            count = sum(1 for row in rows if row[f"{prefix}_match_confidence"] == level)
            print(f"{prefix}_{level}: {count}")


if __name__ == "__main__":
    main()
