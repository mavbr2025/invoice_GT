#!/usr/bin/env python3
"""Export invoice charge mappings from the reviewed CFO connection workbook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_WORKBOOK = Path("output/MTM_CFO_BC_ClickUp_Connection_Matrix_2026.xlsx")
DEFAULT_OUTPUT = Path("config/invoice_charge_mappings/gt.json")


def clean(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def export_mapping(
    workbook: Path,
    output: Path,
    *,
    market: str,
    excluded_field_names: set[str] | None = None,
    excluded_field_ids: set[str] | None = None,
) -> dict[str, Any]:
    matrix = pd.read_excel(workbook, sheet_name="Connection Matrix")
    excluded_field_names = {value.strip().lower() for value in excluded_field_names or set() if value.strip()}
    excluded_field_ids = {value.strip() for value in excluded_field_ids or set() if value.strip()}
    required_columns = [
        "CFO BC Item",
        "BC Description",
        "Tax Group",
        "CFO ClickUp Field ID",
        "CFO ClickUp Field",
    ]
    missing_columns = [column for column in required_columns if column not in matrix.columns]
    if missing_columns:
        raise ValueError(f"Connection Matrix is missing required columns: {', '.join(missing_columns)}")

    mappings: list[dict[str, str]] = []
    errors: list[str] = []
    seen_field_ids: set[str] = set()
    for index, row in matrix.iterrows():
        row_number = index + 2
        bc_item_number = clean(row["CFO BC Item"])
        bc_description = clean(row["BC Description"])
        tax_group = clean(row["Tax Group"])
        field_id = clean(row["CFO ClickUp Field ID"])
        field_name = clean(row["CFO ClickUp Field"])
        resolved_field_id = clean(row.get("Resolved ClickUp Field ID"))
        resolved_field_name = clean(row.get("Resolved ClickUp Field"))
        if resolved_field_id and resolved_field_name and not resolved_field_name.lower().startswith("-cost-"):
            field_id = resolved_field_id
            field_name = resolved_field_name
        if field_name.lower() in excluded_field_names or field_id in excluded_field_ids:
            continue
        if not any([bc_item_number, bc_description, tax_group, field_id, field_name]):
            continue

        row_errors = []
        if not bc_item_number:
            row_errors.append("CFO BC Item")
        if not bc_description:
            row_errors.append("BC Description")
        if not tax_group:
            row_errors.append("Tax Group")
        if not field_id:
            row_errors.append("CFO ClickUp Field ID")
        if not field_name:
            row_errors.append("CFO ClickUp Field")
        if field_id and field_id in seen_field_ids:
            row_errors.append(f"duplicate ClickUp Field ID {field_id}")
        if row_errors:
            errors.append(f"row {row_number}: {', '.join(row_errors)}")
            continue

        seen_field_ids.add(field_id)
        mappings.append(
            {
                "charge_name": field_name,
                "clickup_field_id": field_id,
                "clickup_field_name": field_name,
                "bc_item_number": bc_item_number,
                "bc_description": bc_description,
                "tax_group": tax_group,
            }
        )

    if errors:
        raise ValueError("Invalid invoice charge mapping:\n" + "\n".join(errors))
    if not mappings:
        raise ValueError("Connection Matrix did not contain any mapping rows.")

    payload = {
        "market": market.upper(),
        "source_workbook": str(workbook.resolve()),
        "source_sheet": "Connection Matrix",
        "line_type": "Item",
        "skip_zero_amounts": True,
        "amount_basis": "pre_tax_unit_price",
        "mappings": mappings,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--market", default="GT")
    parser.add_argument(
        "--exclude-field-name",
        action="append",
        default=[],
        help="ClickUp field name to leave out of the exported mapping. Can be repeated.",
    )
    parser.add_argument(
        "--exclude-field-id",
        action="append",
        default=[],
        help="ClickUp field ID to leave out of the exported mapping. Can be repeated.",
    )
    args = parser.parse_args()

    payload = export_mapping(
        args.workbook,
        args.output,
        market=args.market,
        excluded_field_names=set(args.exclude_field_name),
        excluded_field_ids=set(args.exclude_field_id),
    )
    print(
        json.dumps(
            {
                "market": payload["market"],
                "mappings": len(payload["mappings"]),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
