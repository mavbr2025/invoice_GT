from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings as BusinessCentralSettings
from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings
from clickup_integration.mapping import resolve_dropdown_field


DEFAULT_START_DATE = "2026-01-01"
DEFAULT_WORKSPACE_ID = "8451352"
DEFAULT_INVOICING_LIST_ID = "152220606"
DEFAULT_REVENUE_LIST_ID = "901710831940"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local SQLite review database for shipment/invoice reconciliation."
    )
    parser.add_argument("--db", default="output/reconciliation_2026.sqlite3")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--market", default="GT")
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--invoicing-list-id", default=DEFAULT_INVOICING_LIST_ID)
    parser.add_argument("--revenue-list-id", default=DEFAULT_REVENUE_LIST_ID)
    parser.add_argument("--clickup-page-limit", type=int, default=30)
    parser.add_argument("--bc-page-size", type=int, default=100)
    parser.add_argument(
        "--clickup-detail",
        action="store_true",
        help="Fetch every ClickUp task detail endpoint. Slower, but may capture more attachment detail.",
    )
    parser.add_argument(
        "--skip-bc",
        action="store_true",
        help="Only load ClickUp data.",
    )
    parser.add_argument(
        "--skip-clickup",
        action="store_true",
        help="Only load Business Central data.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    reset_loaded_data(conn)

    loaded_at = datetime.now(UTC).isoformat()
    save_run_metadata(
        conn,
        {
            "loaded_at": loaded_at,
            "start_date": args.start_date,
            "market": args.market.upper(),
            "workspace_id": args.workspace_id,
            "invoicing_list_id": args.invoicing_list_id,
            "revenue_list_id": args.revenue_list_id,
        },
    )

    if not args.skip_clickup:
        clickup = ClickUpClient(ClickUpSettings.from_env())
        load_clickup_list(
            conn,
            clickup,
            list_id=args.invoicing_list_id,
            source_label="shipment_invoicing",
            page_limit=args.clickup_page_limit,
            start_date=args.start_date,
            fetch_detail=args.clickup_detail,
        )
        load_clickup_list(
            conn,
            clickup,
            list_id=args.revenue_list_id,
            source_label="clickup_revenue_invoices",
            page_limit=args.clickup_page_limit,
            start_date=args.start_date,
            fetch_detail=args.clickup_detail,
        )

    if not args.skip_bc:
        bc = BusinessCentralClient(BusinessCentralSettings.from_env())
        load_business_central_invoices(
            conn,
            bc,
            market=args.market.upper(),
            start_date=args.start_date,
            page_size=args.bc_page_size,
        )

    refresh_review_views(conn)
    conn.commit()
    print_summary(conn, db_path)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS run_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_fields (
            source_system TEXT NOT NULL,
            source_label TEXT NOT NULL,
            list_id TEXT,
            field_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            field_type TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (source_system, source_label, field_id)
        );

        CREATE TABLE IF NOT EXISTS clickup_tasks (
            task_id TEXT PRIMARY KEY,
            source_label TEXT NOT NULL,
            source_list_id TEXT NOT NULL,
            custom_id TEXT,
            name TEXT,
            status TEXT,
            url TEXT,
            list_id TEXT,
            list_name TEXT,
            folder_id TEXT,
            folder_name TEXT,
            space_id TEXT,
            date_created TEXT,
            date_updated TEXT,
            date_closed TEXT,
            date_done TEXT,
            due_date TEXT,
            start_date TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clickup_task_fields (
            task_id TEXT NOT NULL,
            field_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            field_type TEXT,
            value_text TEXT,
            resolved_label TEXT,
            value_json TEXT,
            PRIMARY KEY (task_id, field_id),
            FOREIGN KEY (task_id) REFERENCES clickup_tasks(task_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS clickup_task_attachments (
            task_id TEXT NOT NULL,
            attachment_id TEXT NOT NULL,
            attachment_origin TEXT NOT NULL,
            field_id TEXT,
            field_name TEXT,
            title TEXT,
            extension TEXT,
            mimetype TEXT,
            url TEXT,
            date TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (task_id, attachment_id, attachment_origin),
            FOREIGN KEY (task_id) REFERENCES clickup_tasks(task_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bc_invoices (
            invoice_id TEXT PRIMARY KEY,
            number TEXT,
            market TEXT NOT NULL,
            company_id TEXT,
            company_name TEXT,
            posting_date TEXT,
            document_date TEXT,
            due_date TEXT,
            customer_id TEXT,
            customer_number TEXT,
            customer_name TEXT,
            currency_code TEXT,
            external_document_number TEXT,
            subtotal REAL,
            tax_amount REAL,
            total_amount REAL,
            remaining_amount REAL,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bc_invoice_lines (
            invoice_id TEXT NOT NULL,
            line_id TEXT NOT NULL,
            line_number INTEGER,
            sequence INTEGER,
            line_type TEXT,
            object_id TEXT,
            object_number TEXT,
            account_id TEXT,
            item_id TEXT,
            description TEXT,
            quantity REAL,
            unit_price REAL,
            amount_excluding_tax REAL,
            tax_amount REAL,
            amount_including_tax REAL,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (invoice_id, line_id),
            FOREIGN KEY (invoice_id) REFERENCES bc_invoices(invoice_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_clickup_tasks_source ON clickup_tasks(source_label, source_list_id);
        CREATE INDEX IF NOT EXISTS idx_clickup_fields_name ON clickup_task_fields(field_name);
        CREATE INDEX IF NOT EXISTS idx_bc_invoices_number ON bc_invoices(number);
        CREATE INDEX IF NOT EXISTS idx_bc_invoices_external_doc ON bc_invoices(external_document_number);
        CREATE INDEX IF NOT EXISTS idx_bc_invoice_lines_invoice ON bc_invoice_lines(invoice_id);
        """
    )


def reset_loaded_data(conn: sqlite3.Connection) -> None:
    for table in (
        "clickup_task_attachments",
        "clickup_task_fields",
        "clickup_tasks",
        "source_fields",
        "bc_invoice_lines",
        "bc_invoices",
        "run_metadata",
    ):
        conn.execute(f"DELETE FROM {table}")


def save_run_metadata(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO run_metadata(key, value) VALUES (?, ?)",
        sorted(values.items()),
    )


def load_clickup_list(
    conn: sqlite3.Connection,
    clickup: ClickUpClient,
    *,
    list_id: str,
    source_label: str,
    page_limit: int,
    start_date: str,
    fetch_detail: bool,
) -> None:
    field_payload = clickup.get_list_custom_fields(list_id)
    for field in field_payload.get("fields", []) or []:
        conn.execute(
            """
            INSERT OR REPLACE INTO source_fields
            (source_system, source_label, list_id, field_id, field_name, field_type, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "clickup",
                source_label,
                list_id,
                field.get("id"),
                field.get("name") or field.get("id"),
                field.get("type"),
                dump_json(field),
            ),
        )

    for page in range(page_limit):
        print(f"Loading ClickUp {source_label} page {page + 1}/{page_limit}...", flush=True)
        payload = clickup.get_list_tasks(
            list_id,
            include_closed=True,
            page=page,
            subtasks=True,
        )
        tasks = payload.get("tasks", []) or []
        if not tasks:
            break
        for task_summary in tasks:
            task_id = task_summary.get("id")
            if not task_id:
                continue
            task = (
                clickup.get_task(task_id, include_subtasks=False)
                if fetch_detail
                else task_summary
            )
            if not include_clickup_task(task, start_date=start_date):
                continue
            upsert_clickup_task(conn, task, source_label=source_label, source_list_id=list_id)


def include_clickup_task(task: dict[str, Any], *, start_date: str) -> bool:
    threshold = parse_iso_date_start(start_date)
    for key in ("date_created", "date_updated", "date_closed", "date_done", "due_date", "start_date"):
        value = parse_clickup_timestamp(task.get(key))
        if value and value >= threshold:
            return True
    return False


def upsert_clickup_task(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    *,
    source_label: str,
    source_list_id: str,
) -> None:
    list_info = task.get("list") or {}
    folder_info = task.get("folder") or task.get("project") or {}
    space_info = task.get("space") or {}
    status = task.get("status") or {}
    conn.execute(
        """
        INSERT OR REPLACE INTO clickup_tasks
        (task_id, source_label, source_list_id, custom_id, name, status, url, list_id, list_name,
         folder_id, folder_name, space_id, date_created, date_updated, date_closed, date_done,
         due_date, start_date, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.get("id"),
            source_label,
            source_list_id,
            task.get("custom_id"),
            task.get("name"),
            status.get("status") if isinstance(status, dict) else status,
            task.get("url"),
            list_info.get("id"),
            list_info.get("name"),
            folder_info.get("id"),
            folder_info.get("name"),
            space_info.get("id") if isinstance(space_info, dict) else None,
            parse_clickup_timestamp(task.get("date_created")),
            parse_clickup_timestamp(task.get("date_updated")),
            parse_clickup_timestamp(task.get("date_closed")),
            parse_clickup_timestamp(task.get("date_done")),
            parse_clickup_timestamp(task.get("due_date")),
            parse_clickup_timestamp(task.get("start_date")),
            dump_json(task),
        ),
    )

    for field in task.get("custom_fields", []) or []:
        field_id = field.get("id")
        if not field_id:
            continue
        value = field.get("value")
        resolved = resolve_dropdown_field(
            {
                "value": value,
                "type_config": field.get("type_config"),
            }
        )
        value_text = field_value_text(value)
        resolved_label = (resolved or {}).get("name")
        conn.execute(
            """
            INSERT OR REPLACE INTO clickup_task_fields
            (task_id, field_id, field_name, field_type, value_text, resolved_label, value_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.get("id"),
                field_id,
                field.get("name") or field_id,
                field.get("type"),
                value_text,
                resolved_label,
                dump_json(value),
            ),
        )
        if field.get("type") == "attachment" and isinstance(value, list):
            for attachment in value:
                insert_clickup_attachment(
                    conn,
                    task_id=task.get("id"),
                    attachment=attachment,
                    field_id=field_id,
                    field_name=field.get("name") or field_id,
                )

    for attachment in task.get("attachments", []) or []:
        insert_clickup_attachment(conn, task_id=task.get("id"), attachment=attachment)


def insert_clickup_attachment(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    attachment: dict[str, Any],
    field_id: str | None = None,
    field_name: str | None = None,
) -> None:
    attachment_id = attachment.get("id")
    if not attachment_id:
        return
    conn.execute(
        """
        INSERT OR REPLACE INTO clickup_task_attachments
        (task_id, attachment_id, attachment_origin, field_id, field_name, title, extension, mimetype, url, date, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            attachment_id,
            field_id or "task",
            field_id,
            field_name,
            attachment.get("title"),
            attachment.get("extension"),
            attachment.get("mimetype"),
            attachment.get("url") or attachment.get("url_w_query") or attachment.get("url_w_host"),
            parse_clickup_timestamp(attachment.get("date")),
            dump_json(attachment),
        ),
    )


def load_business_central_invoices(
    conn: sqlite3.Connection,
    bc: BusinessCentralClient,
    *,
    market: str,
    start_date: str,
    page_size: int,
) -> None:
    company_id = bc._resolve_company_id(company_id=None, market=market)
    if not company_id:
        raise ValueError(f"No Business Central company is configured for market {market}.")
    company = bc.get_company_metadata(company_id=company_id, market=market) or {}
    company_name = company.get("name") or company.get("displayName")

    for invoice in iter_bc_entities(
        bc,
        company_id=company_id,
        entity_name="salesInvoices",
        filters=f"postingDate ge {start_date}",
        page_size=page_size,
    ):
        loaded_count = conn.execute("SELECT COUNT(*) FROM bc_invoices").fetchone()[0]
        if loaded_count and loaded_count % 25 == 0:
            print(f"Loaded {loaded_count} BC invoices...", flush=True)
        invoice_id = first_value(invoice, "id", "systemId", "SystemId")
        if not invoice_id:
            continue
        insert_bc_invoice(
            conn,
            invoice,
            market=market,
            company_id=company_id,
            company_name=company_name,
        )
        for sequence, line in enumerate(
            bc.get_posted_sales_invoice_lines(invoice_id, market=market),
            start=1,
        ):
            insert_bc_invoice_line(conn, invoice_id=invoice_id, line=line, sequence=sequence)


def iter_bc_entities(
    bc: BusinessCentralClient,
    *,
    company_id: str,
    entity_name: str,
    filters: str,
    page_size: int,
) -> Iterable[dict[str, Any]]:
    skip = 0
    while True:
        url = f"{bc.settings.api_base_url}/companies({company_id})/{entity_name}"
        payload = bc._request(
            "GET",
            url,
            params={
                "$top": page_size,
                "$skip": skip,
                "$filter": filters,
            },
        )
        rows = payload.get("value", []) or []
        if not rows:
            break
        yield from rows
        if len(rows) < page_size:
            break
        skip += page_size


def insert_bc_invoice(
    conn: sqlite3.Connection,
    invoice: dict[str, Any],
    *,
    market: str,
    company_id: str,
    company_name: str | None,
) -> None:
    invoice_id = first_value(invoice, "id", "systemId", "SystemId")
    conn.execute(
        """
        INSERT OR REPLACE INTO bc_invoices
        (invoice_id, number, market, company_id, company_name, posting_date, document_date, due_date,
         customer_id, customer_number, customer_name, currency_code, external_document_number,
         subtotal, tax_amount, total_amount, remaining_amount, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_id,
            first_value(invoice, "number", "No.", "no"),
            market,
            company_id,
            company_name,
            first_value(invoice, "postingDate", "Posting_Date"),
            first_value(invoice, "documentDate", "invoiceDate", "Document_Date"),
            first_value(invoice, "dueDate", "Due_Date"),
            first_value(invoice, "customerId", "billToCustomerId"),
            first_value(invoice, "customerNumber", "billToCustomerNumber", "Bill_to_Customer_No"),
            first_value(invoice, "customerName", "billToName", "Bill_to_Name"),
            first_value(invoice, "currencyCode", "Currency_Code"),
            first_value(invoice, "externalDocumentNumber", "customerPurchaseOrderReference"),
            numeric_value(invoice, "totalAmountExcludingTax", "amount", "subtotal"),
            numeric_value(invoice, "totalTaxAmount", "taxAmount", "Total_VAT"),
            numeric_value(invoice, "totalAmountIncludingTax", "amountIncludingVAT", "totalAmount"),
            numeric_value(invoice, "remainingAmount", "remainingBalance", "balanceDue"),
            dump_json(invoice),
        ),
    )


def insert_bc_invoice_line(
    conn: sqlite3.Connection,
    *,
    invoice_id: str,
    line: dict[str, Any],
    sequence: int,
) -> None:
    line_id = first_value(line, "id", "systemId", "SystemId") or str(sequence)
    conn.execute(
        """
        INSERT OR REPLACE INTO bc_invoice_lines
        (invoice_id, line_id, line_number, sequence, line_type, object_id, object_number,
         account_id, item_id, description, quantity, unit_price, amount_excluding_tax,
         tax_amount, amount_including_tax, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_id,
            line_id,
            int_value(line, "lineNumber", "Line_No"),
            sequence,
            first_value(line, "lineType", "type"),
            first_value(line, "lineObjectId", "accountId", "itemId"),
            first_value(line, "lineObjectNumber", "accountNumber", "itemNumber"),
            first_value(line, "accountId"),
            first_value(line, "itemId"),
            first_value(line, "description", "Description", "displayName"),
            numeric_value(line, "quantity", "Quantity"),
            numeric_value(line, "unitPrice", "Unit_Price"),
            numeric_value(line, "amountExcludingTax", "amount", "Amount"),
            numeric_value(line, "taxAmount", "Tax_Amount"),
            numeric_value(line, "amountIncludingTax", "Amount_Including_VAT"),
            dump_json(line),
        ),
    )


def refresh_review_views(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP VIEW IF EXISTS review_bc_invoice_lines;
        CREATE VIEW review_bc_invoice_lines AS
        SELECT
            i.number AS bc_invoice_no,
            i.posting_date,
            i.customer_number,
            i.customer_name,
            i.currency_code,
            i.external_document_number,
            l.sequence,
            l.line_type,
            l.object_number,
            l.description,
            l.quantity,
            l.unit_price,
            l.amount_excluding_tax,
            l.tax_amount,
            l.amount_including_tax
        FROM bc_invoice_lines l
        JOIN bc_invoices i ON i.invoice_id = l.invoice_id;

        DROP VIEW IF EXISTS review_clickup_charge_fields;
        CREATE VIEW review_clickup_charge_fields AS
        SELECT
            t.source_label,
            t.task_id,
            t.custom_id,
            t.name AS task_name,
            t.status,
            t.url,
            f.field_name,
            f.value_text,
            f.resolved_label
        FROM clickup_task_fields f
        JOIN clickup_tasks t ON t.task_id = f.task_id
        WHERE lower(f.field_name) LIKE '%cost%'
           OR lower(f.field_name) LIKE '%charge%'
           OR lower(f.field_name) LIKE '%freight%'
           OR lower(f.field_name) LIKE '%invoice%'
           OR lower(f.field_name) LIKE '%storage%'
           OR lower(f.field_name) LIKE '%demurrage%'
           OR lower(f.field_name) LIKE '%d&d%'
           OR lower(f.field_name) LIKE '%vgm%';

        DROP VIEW IF EXISTS review_possible_invoice_task_matches;
        CREATE VIEW review_possible_invoice_task_matches AS
        SELECT
            i.number AS bc_invoice_no,
            i.customer_name AS bc_customer_name,
            i.external_document_number AS bc_reference,
            i.total_amount AS bc_total_amount,
            t.source_label,
            t.task_id,
            t.custom_id,
            t.name AS clickup_task_name,
            t.status AS clickup_status,
            t.url AS clickup_url,
            CASE
                WHEN t.name = i.number THEN 100
                WHEN t.name LIKE '%' || i.number || '%' THEN 90
                WHEN i.external_document_number IS NOT NULL
                     AND i.external_document_number != ''
                     AND (
                        t.name LIKE '%' || i.external_document_number || '%'
                        OR EXISTS (
                            SELECT 1 FROM clickup_task_fields f
                            WHERE f.task_id = t.task_id
                              AND (f.value_text LIKE '%' || i.external_document_number || '%'
                                   OR f.resolved_label LIKE '%' || i.external_document_number || '%')
                        )
                     ) THEN 70
                ELSE 0
            END AS match_score
        FROM bc_invoices i
        JOIN clickup_tasks t
          ON t.name LIKE '%' || i.number || '%'
          OR (
              i.external_document_number IS NOT NULL
              AND i.external_document_number != ''
              AND t.name LIKE '%' || i.external_document_number || '%'
          )
        WHERE match_score > 0;
        """
    )


def print_summary(conn: sqlite3.Connection, db_path: Path) -> None:
    counts = {
        "clickup_tasks": conn.execute("SELECT COUNT(*) FROM clickup_tasks").fetchone()[0],
        "clickup_task_fields": conn.execute("SELECT COUNT(*) FROM clickup_task_fields").fetchone()[0],
        "clickup_attachments": conn.execute("SELECT COUNT(*) FROM clickup_task_attachments").fetchone()[0],
        "bc_invoices": conn.execute("SELECT COUNT(*) FROM bc_invoices").fetchone()[0],
        "bc_invoice_lines": conn.execute("SELECT COUNT(*) FROM bc_invoice_lines").fetchone()[0],
        "possible_matches": conn.execute(
            "SELECT COUNT(*) FROM review_possible_invoice_task_matches"
        ).fetchone()[0],
    }
    print(f"Wrote {db_path}")
    for key, value in counts.items():
        print(f"{key}: {value}")


def parse_clickup_timestamp(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    try:
        timestamp = int(str(value))
    except (TypeError, ValueError):
        return str(value)
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=UTC).date().isoformat()


def parse_iso_date_start(value: str) -> str:
    return datetime.fromisoformat(value).date().isoformat()


def first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in {None, ""}:
            return value
    return None


def numeric_value(payload: dict[str, Any], *keys: str) -> float | None:
    value = first_value(payload, *keys)
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def int_value(payload: dict[str, Any], *keys: str) -> int | None:
    value = first_value(payload, *keys)
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def field_value_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return dump_json(value)
    return str(value)


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


if __name__ == "__main__":
    main()
