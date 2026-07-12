#!/usr/bin/env python3
"""Match the CFO BC/ClickUp product base to current reconciliation data."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_WORKBOOK = Path("/Users/mario/Downloads/Products BC - ClickUp.xlsx")
DEFAULT_DB = Path("output/reconciliation_2026.sqlite3")
DEFAULT_OUTPUT = Path("output/cfo_connection_matches_2026")


FIELD_ALIASES = {
    "freight (ocean/truck/air)": ["-Cost- Freight", "Freight", "Freight (Ocean/Truck/Air)"],
    "origin charges": ["-Cost- Origin Charges", "Origin Charges"],
    "inland origin": ["-Cost- Inland Origin", "Inland origin"],
    "customs broker origin": ["-Cost- Customs broker origin", "Customs Broker Origin"],
    "emergency surcharge": ["-Cost- Emergency Surcharge", "Emergency Surcharge"],
    "doc fee origin": ["-Cost- Doc fee origin", "Doc Fee Origin"],
    "inspection at origin": ["-Cost- Inspection at origin", "Inspection at Origin"],
    "cargo maritime insurance": ["- Cost - Insurance", "Cargo Maritime Insurance"],
    "destination charges": ["-Cost- Destination charges", "Destination Charges"],
    "doc fee destination": ["-Cost- Doc Fee Dest", "Doc Fee Destination"],
    "ct / handling fee": ["-Cost- CT / Handling fee", "CT / Handling Fee"],
    "customs broker": ["-Cost- Customs agent", "Customs Broker", "Customs agent"],
    "inland destination": ["-Cost- Inland destination", "Inland Destination"],
    "almacenaje alc cliente (usd)": [
        "-Cost- Storage (USD)",
        "Almacenaje alc cliente (USD)",
        "Almacenaje al cliente (USD)",
    ],
    "d&d al cliente (usd)": ["-Cost- D&D (USD)", "D&D al cliente (USD)"],
    "custody": ["-Cost- Custody", "Custody"],
    "trading company": ["-Cost- Trading Company", "Trading Company"],
}


BC_PROPOSALS = {
    "inspection at origin": [],
    "inland destination": ["NAT00000031"],
    "custody": ["NAT00000004", "INT000000020", "NAT00000014"],
    "trading company": [],
}


@dataclass
class ConnectionMatch:
    sort_order: int
    cfo_bc_number: str
    cfo_bc_description: str
    cfo_tax_group: str
    cfo_clickup_field_id: str
    cfo_clickup_field_name: str
    current_clickup_field_id: str
    current_clickup_field_name: str
    current_clickup_field_type: str
    clickup_tasks_with_value: int
    clickup_sample_values: str
    related_cost_field_id: str
    related_cost_field_name: str
    related_cost_tasks_with_value: int
    field_match_method: str
    bc_product_exists: str
    bc_observed_lines: int
    bc_observed_total: float
    proposed_bc_number: str
    proposed_bc_description: str
    proposed_tax_group: str
    proposed_observed_lines: int
    status: str
    action: str
    notes: str


def normalize(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def cell(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def read_cfo_mapping(path: Path) -> list[dict[str, str]]:
    raw = pd.read_excel(path, sheet_name="Click Up-BC", header=None)
    rows: list[dict[str, str]] = []
    for idx, row in raw.iloc[2:].iterrows():
        if row.isna().all():
            continue
        rows.append(
            {
                "sort_order": str(len(rows) + 1),
                "bc_number": cell(row.iloc[0]),
                "bc_description": cell(row.iloc[1]),
                "tax_group": cell(row.iloc[2]),
                "field_id": cell(row.iloc[3]),
                "field_name": cell(row.iloc[4]),
            }
        )
    return rows


def read_products(path: Path) -> dict[str, dict[str, str]]:
    products = pd.read_excel(path, sheet_name="Productos")
    result: dict[str, dict[str, str]] = {}
    for _, row in products.iterrows():
        number = cell(row.get("Nº"))
        if not number:
            continue
        result[number] = {
            "number": number,
            "description": cell(row.get("Descripción")),
            "tax_group": cell(row.get("Grupo contable IVA prod.")),
        }
    return result


def load_current_fields(conn: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    rows = conn.execute(
        """
        select
          field_id,
          field_name,
          max(coalesce(field_type, '')) as field_type,
          count(distinct task_id) as task_count,
          count(distinct case
            when coalesce(value_text, resolved_label, '') <> ''
              or coalesce(value_json, '') not in ('', 'null', '[]', '{}')
            then task_id end) as tasks_with_value
        from clickup_task_fields
        group by field_id, field_name
        """
    ).fetchall()
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = {
            "field_id": row[0],
            "field_name": row[1],
            "field_type": row[2],
            "task_count": row[3],
            "tasks_with_value": row[4],
            "sample_values": sample_values(conn, row[0]),
        }
        by_id[row[0]] = item
        by_name.setdefault(normalize(row[1]), []).append(item)
    return by_id, by_name


def sample_values(conn: sqlite3.Connection, field_id: str) -> str:
    values: list[str] = []
    for (value,) in conn.execute(
        """
        select coalesce(nullif(value_text, ''), nullif(resolved_label, ''), nullif(value_json, ''))
        from clickup_task_fields
        where field_id = ?
          and coalesce(value_text, resolved_label, value_json, '') <> ''
          and coalesce(value_json, '') not in ('null', '[]', '{}')
        limit 5
        """,
        (field_id,),
    ):
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in values:
            values.append(text[:60])
    return " | ".join(values)


def load_bc_usage(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        select
          object_number,
          max(coalesce(description, '')) as description,
          count(*) as lines,
          round(sum(coalesce(amount_including_tax, amount_excluding_tax, 0)), 2) as total
        from bc_invoice_lines
        where coalesce(object_number, '') <> ''
        group by object_number
        """
    ).fetchall()
    return {
        row[0]: {
            "object_number": row[0],
            "description": row[1],
            "lines": int(row[2] or 0),
            "total": float(row[3] or 0),
        }
        for row in rows
    }


def choose_field(
    row: dict[str, str],
    by_id: dict[str, dict[str, Any]],
    by_name: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str, str]:
    cfo_id = row["field_id"]
    cfo_name = row["field_name"]
    if cfo_id and cfo_id in by_id:
        match = by_id[cfo_id]
        return match, "field_id", "CFO field ID exists in current ClickUp extraction."
    exact = by_name.get(normalize(cfo_name), [])
    if exact:
        return exact[0], "field_name", "CFO field name exists in current ClickUp extraction."
    alias = choose_alias_match(cfo_name, by_name)
    if alias:
        return alias, "semantic_alias", "Matched by charge-name alias to current operational field."
    return None, "missing", "No current ClickUp field found for this CFO row."


def choose_alias_match(cfo_name: str, by_name: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    aliases = FIELD_ALIASES.get(normalize(cfo_name), [])
    candidates: list[dict[str, Any]] = []
    for alias in aliases:
        candidates.extend(by_name.get(normalize(alias), []))
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            not normalize(item["field_name"]).startswith("-cost"),
            -int(item.get("tasks_with_value") or 0),
            item["field_name"],
        ),
    )[0]


def best_bc_proposal(
    field_name: str,
    products: dict[str, dict[str, str]],
    usage: dict[str, dict[str, Any]],
) -> tuple[str, str, str, int]:
    proposals = BC_PROPOSALS.get(normalize(field_name), [])
    ranked: list[tuple[int, str, dict[str, str]]] = []
    for number in proposals:
        product = products.get(number, {"description": "", "tax_group": ""})
        observed = int(usage.get(number, {}).get("lines") or 0)
        ranked.append((observed, number, product))
    if not ranked:
        return "", "", "", 0
    observed, number, product = sorted(ranked, key=lambda item: (-item[0], item[1]))[0]
    return number, product.get("description", ""), product.get("tax_group", ""), observed


def status_and_action(
    row: dict[str, str],
    product_exists: bool,
    field: dict[str, Any] | None,
    match_method: str,
    proposed_number: str,
    proposed_lines: int,
    observed_lines: int,
) -> tuple[str, str, str]:
    cfo_name = row["field_name"]
    if field is None:
        return (
            "blocked_clickup_field_missing",
            "Create or expose a ClickUp charge field before automation.",
            "No usable ClickUp source field found.",
        )
    if not row["bc_number"]:
        if not proposed_number:
            return (
                "blocked_bc_item_missing",
                "Assign the BC item/product number and tax group.",
                "CFO mapping row does not specify a BC item, and no observed BC invoice-line pattern resolved it.",
            )
        qualifier = "observed in 2026 invoice lines" if proposed_lines else "from product catalog only"
        return (
            "needs_bc_item_confirmation",
            f"Confirm proposed BC item {proposed_number} for {cfo_name}.",
            f"BC item is blank in CFO base; proposal is {qualifier}.",
        )
    if not product_exists:
        return (
            "blocked_bc_product_not_in_cfo_catalog",
            "Validate the BC product exists in Business Central and add it to the CFO base.",
            "CFO row references a BC item not present in the Productos sheet.",
        )
    if observed_lines == 0:
        return (
            "ready_no_2026_usage_observed",
            "Keep mapping, but validate with future or historic invoices before full automation.",
            "The product exists but was not observed in the January 1, 2026+ BC invoice lines.",
        )
    if match_method == "semantic_alias":
        return (
            "ready_use_current_clickup_field",
            "Use the matched current ClickUp field ID in automation and update the CFO workbook reference.",
            "CFO business mapping is valid; ClickUp field ID was resolved by semantic alias rather than direct ID.",
        )
    return (
        "ready",
        "Use this row as a direct translation-table entry.",
        "BC product and ClickUp field both resolve directly.",
    )


def build_matches(workbook: Path, db: Path) -> tuple[list[ConnectionMatch], dict[str, Any]]:
    cfo_rows = read_cfo_mapping(workbook)
    products = read_products(workbook)
    with sqlite3.connect(db) as conn:
        by_id, by_name = load_current_fields(conn)
        usage = load_bc_usage(conn)

    matches: list[ConnectionMatch] = []
    statuses: Counter[str] = Counter()
    for raw_row in cfo_rows:
        field, match_method, field_note = choose_field(raw_row, by_id, by_name)
        cost_field = choose_alias_match(raw_row["field_name"], by_name)
        if cost_field and not normalize(cost_field["field_name"]).startswith("-cost"):
            cost_field = None
        cfo_number = raw_row["bc_number"]
        product = products.get(cfo_number, {})
        observed = usage.get(cfo_number, {})
        proposed_number, proposed_desc, proposed_tax, proposed_lines = best_bc_proposal(
            raw_row["field_name"], products, usage
        )
        status, action, status_note = status_and_action(
            raw_row,
            bool(product),
            field,
            match_method,
            proposed_number,
            proposed_lines,
            int(observed.get("lines") or 0),
        )
        statuses[status] += 1
        notes = "; ".join(part for part in [field_note, status_note] if part)
        matches.append(
            ConnectionMatch(
                sort_order=int(raw_row["sort_order"]),
                cfo_bc_number=cfo_number,
                cfo_bc_description=raw_row["bc_description"],
                cfo_tax_group=raw_row["tax_group"],
                cfo_clickup_field_id=raw_row["field_id"],
                cfo_clickup_field_name=raw_row["field_name"],
                current_clickup_field_id=str(field.get("field_id", "")) if field else "",
                current_clickup_field_name=str(field.get("field_name", "")) if field else "",
                current_clickup_field_type=str(field.get("field_type", "")) if field else "",
                clickup_tasks_with_value=int(field.get("tasks_with_value") or 0) if field else 0,
                clickup_sample_values=str(field.get("sample_values", "")) if field else "",
                related_cost_field_id=str(cost_field.get("field_id", "")) if cost_field else "",
                related_cost_field_name=str(cost_field.get("field_name", "")) if cost_field else "",
                related_cost_tasks_with_value=int(cost_field.get("tasks_with_value") or 0) if cost_field else 0,
                field_match_method=match_method,
                bc_product_exists="yes" if product else "no",
                bc_observed_lines=int(observed.get("lines") or 0),
                bc_observed_total=float(observed.get("total") or 0),
                proposed_bc_number=proposed_number,
                proposed_bc_description=proposed_desc,
                proposed_tax_group=proposed_tax,
                proposed_observed_lines=proposed_lines,
                status=status,
                action=action,
                notes=notes,
            )
        )

    summary = {
        "source_workbook": str(workbook),
        "source_database": str(db),
        "mapping_rows": len(matches),
        "status_counts": dict(statuses),
        "ready_rows": sum(
            count for status, count in statuses.items() if status.startswith("ready")
        ),
        "needs_decision_rows": len(matches)
        - sum(count for status, count in statuses.items() if status.startswith("ready")),
    }
    return matches, summary


def write_outputs(matches: list[ConnectionMatch], summary: dict[str, Any], output_base: Path) -> None:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(match) for match in matches]
    csv_path = output_base.with_suffix(".csv")
    json_path = output_base.with_suffix(".json")
    summary_path = output_base.with_name(output_base.name + "_summary.json")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    matches, summary = build_matches(args.workbook, args.db)
    write_outputs(matches, summary, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
