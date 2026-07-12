#!/usr/bin/env python3
"""Create synthetic ONE shipment tasks that look like inbound emails.

Default mode is a dry run. Pass --apply to create tasks in the ClickUp sandbox
list and populate the key custom fields used by shipment automations.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT))

from generate_one_track_trace_stress import (  # noqa: E402
    DEFAULT_LIST_ID,
    DROPDOWN_OPTION_IDS,
    FIELD_IDS,
    ROUTES,
    build_container_numbers,
    date_field,
    dropdown_field,
    format_dt,
    parse_datetime,
    text_field,
)

from clickup_integration.client import ClickUpClient  # noqa: E402
from clickup_integration.config import ClickUpSettings  # noqa: E402


DEFAULT_START = "2026-04-29T08:00:00-06:00"

EXTRA_FIELD_IDS = {
    "Customer Name": "14296306-ecb3-4edc-8baf-7c3b8c6250ec",
    "Shipper's Name": "16dcb817-4494-4af0-8dc9-f13b8a08df7c",
    "Shipper Email": "eeb01d52-75fe-4d37-80d4-356b7f727421",
    "Origin": "250d25fd-2922-4358-9dbc-1c39ce661fdc",
    "Cargo Description": "4aadfbc5-2c4e-49f5-a7e9-646092635695",
    "Cargo Ready Date": "d76ccfeb-4166-44d7-bae5-59ff515b80ac",
}

SHIPPER_PROFILES = [
    ("Ningbo Harbor Precision Parts Co., Ltd.", "exports@ningbo-harbor-parts.cn"),
    ("Shenzhen Apex Home Products Ltd.", "shipping@apexhome-shenzhen.cn"),
    ("Qingdao Sunrise Machinery Co., Ltd.", "logistics@sunrise-machinery.cn"),
    ("Xiamen Blue Ocean Ceramics Ltd.", "docs@blueocean-ceramics.cn"),
    ("Yantian Global Electronics Co., Ltd.", "export.ops@yantian-electronics.cn"),
    ("Foshan Meridian Furniture Manufacturing", "salesops@meridian-foshan.cn"),
    ("Guangzhou Pearl Lighting Factory", "shipment@pearl-lighting.cn"),
    ("Ningbo Eastline Tools Co., Ltd.", "booking@eastline-tools.cn"),
    ("Shantou Bright Toys Manufacturing", "export@brighttoys-shantou.cn"),
    ("Suzhou Prime Textile Group", "logistics@primetextile-suzhou.cn"),
]

CUSTOMER_NAMES = [
    "Sandbox Customer Guatemala",
    "Sandbox Customer Mexico",
    "Sandbox Customer El Salvador",
    "Sandbox Automotive Imports",
    "Sandbox Retail Distribution",
    "Sandbox Industrial Supplies",
]

CARGO_DESCRIPTIONS = [
    "Auto spare parts, non-hazardous",
    "Household goods and retail fixtures",
    "Ceramic tiles and sanitary ware",
    "LED lighting components",
    "Textile rolls and accessories",
    "Plastic household articles",
    "Furniture parts, KD packed",
    "Machinery spare parts",
]

CSV_COLUMNS = [
    "batch_id",
    "clickup_list_id",
    "shipment_index",
    "shipment_key",
    "task_id",
    "task_url",
    "task_name",
    "received_at",
    "from_email",
    "to_email",
    "subject",
    "shipper_name",
    "shipper_email",
    "customer_name",
    "origin",
    "pol",
    "mother_pol",
    "port_of_discharge",
    "booking_number",
    "number_of_containers",
    "container_type",
    "container_numbers",
    "cargo_description",
    "cargo_ready_date",
    "etd",
    "eta",
    "initial_estatus_db",
    "mode",
    "error",
]


@dataclass(frozen=True)
class EmailShipment:
    index: int
    shipment_key: str
    task_name: str
    received_at: datetime
    from_email: str
    to_email: str
    subject: str
    shipper_name: str
    shipper_email: str
    customer_name: str
    origin: str
    pol: str
    mother_pol: str
    port_of_discharge: str
    booking_number: str
    container_type: str
    container_numbers: list[str]
    cargo_description: str
    cargo_ready_date: datetime
    etd: datetime
    eta: datetime
    initial_status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or create synthetic ONE shipment email tasks in ClickUp."
    )
    parser.add_argument("--shipments", type=int, default=25, help="Number of email shipment tasks.")
    parser.add_argument("--list-id", default=DEFAULT_LIST_ID, help="Target ClickUp list id.")
    parser.add_argument("--seed", type=int, default=20260429, help="Deterministic random seed.")
    parser.add_argument("--start", default=DEFAULT_START, help="First synthetic email timestamp.")
    parser.add_argument(
        "--spacing-seconds",
        type=int,
        default=30,
        help="Seconds between synthetic email timestamps.",
    )
    parser.add_argument(
        "--max-containers",
        type=int,
        default=5,
        help="Maximum containers per shipment. Shipment counts rotate from 1 to this value.",
    )
    parser.add_argument(
        "--initial-status",
        choices=("Booking por Confirmar", "Booking confirmado"),
        default="Booking por Confirmar",
        help="Initial Estatus DB/ value set after task creation.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/track_trace_fixtures/email_shipments",
        help="Directory for dry-run or apply manifests.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create tasks and set custom fields in ClickUp. Omit for dry-run only.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.25,
        help="Delay between ClickUp API calls when --apply is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.shipments < 1:
        raise SystemExit("--shipments must be at least 1")
    if args.max_containers < 1:
        raise SystemExit("--max-containers must be at least 1")
    if args.spacing_seconds < 0:
        raise SystemExit("--spacing-seconds cannot be negative")

    start = parse_datetime(args.start)
    batch_id = f"ONE-EMAIL-SEED-{start.strftime('%Y%m%d%H%M%S')}"
    rng = random.Random(args.seed)
    shipments = build_email_shipments(args, start, rng)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "one_email_shipments_manifest.csv"
    payload_path = output_dir / "one_email_shipments_payloads.jsonl"

    client = ClickUpClient(ClickUpSettings.from_env()) if args.apply else None
    manifest_rows: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []

    for shipment in shipments:
        payload = build_clickup_payload(args.list_id, batch_id, shipment)
        result = apply_payload(client, payload, args.sleep_seconds) if client else dry_run_result()
        manifest_rows.append(to_manifest_row(batch_id, args.list_id, shipment, result))
        payload_rows.append({**payload, "result": result})

    write_manifest(manifest_path, manifest_rows)
    write_jsonl(payload_path, payload_rows)

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "batch_id": batch_id,
        "clickup_list_id": args.list_id,
        "shipments": len(shipments),
        "manifest": str(manifest_path),
        "payloads": str(payload_path),
        "created": sum(1 for row in manifest_rows if row["task_id"]),
        "errors": sum(1 for row in manifest_rows if row["error"]),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def build_email_shipments(
    args: argparse.Namespace,
    start: datetime,
    rng: random.Random,
) -> list[EmailShipment]:
    shipments: list[EmailShipment] = []
    for index in range(1, args.shipments + 1):
        route = ROUTES[(index - 1) % len(ROUTES)]
        shipper_name, shipper_email = SHIPPER_PROFILES[(index - 1) % len(SHIPPER_PROFILES)]
        customer_name = CUSTOMER_NAMES[(index - 1) % len(CUSTOMER_NAMES)]
        cargo_description = CARGO_DESCRIPTIONS[(index - 1) % len(CARGO_DESCRIPTIONS)]
        container_type = rng.choice(["40 HC", "40 DRY", "20GP"])
        container_numbers = build_container_numbers(index, args.max_containers)
        booking_number = f"ONEYTT26{index:06d}"
        shipment_key = f"ONE-TT-{index:04d}"
        received_at = start + timedelta(seconds=(index - 1) * args.spacing_seconds)
        cargo_ready_date = (start + timedelta(days=1 + (index % 7))).replace(hour=9, minute=0, second=0)
        etd = (start + timedelta(days=3 + (index % 9))).replace(hour=18, minute=0, second=0)
        eta = etd + timedelta(days=24 + (index % 6))
        origin = f"{route.pol} factory zone"
        subject = (
            f"New ONE shipment request - {booking_number} - "
            f"{len(container_numbers)}x {container_type} from {route.pol}"
        )
        task_name = f"EMAIL | {shipment_key} | {booking_number} | {route.pol}"
        shipments.append(
            EmailShipment(
                index=index,
                shipment_key=shipment_key,
                task_name=task_name,
                received_at=received_at,
                from_email=shipper_email,
                to_email="sandbox-shipments@mtm-logistics.test",
                subject=subject,
                shipper_name=shipper_name,
                shipper_email=shipper_email,
                customer_name=customer_name,
                origin=origin,
                pol=route.pol,
                mother_pol=route.mother_pol,
                port_of_discharge=route.pod,
                booking_number=booking_number,
                container_type=container_type,
                container_numbers=container_numbers,
                cargo_description=cargo_description,
                cargo_ready_date=cargo_ready_date,
                etd=etd,
                eta=eta,
                initial_status=args.initial_status,
            )
        )
    return shipments


def build_clickup_payload(list_id: str, batch_id: str, shipment: EmailShipment) -> dict[str, Any]:
    description = build_email_description(batch_id, shipment)
    non_trigger_fields = [
        dropdown_field("Carrier/", "ONE"),
        text_field("Booking number/", shipment.booking_number),
        text_field("Container(s) number(s)/", "; ".join(shipment.container_numbers)),
        {
            "field_name": "Number of Containers",
            "field_id": FIELD_IDS["Number of Containers"],
            "type": "number",
            "value": len(shipment.container_numbers),
        },
        dropdown_field("Container type and size/", shipment.container_type),
        dropdown_field("POL", shipment.pol),
        dropdown_field("Mother POL", shipment.mother_pol),
        dropdown_field("Port Of Discharge", shipment.port_of_discharge),
        dropdown_field("MTM booking (Yes/No)", "Yes"),
        dropdown_field("Carrier release", "Pending"),
        short_text_extra("Customer Name", shipment.customer_name),
        short_text_extra("Shipper's Name", shipment.shipper_name),
        email_extra("Shipper Email", shipment.shipper_email),
        short_text_extra("Origin", shipment.origin),
        text_extra("Cargo Description", shipment.cargo_description),
        date_extra("Cargo Ready Date", shipment.cargo_ready_date),
        date_field("ETD/", shipment.etd),
        date_field("ETA Schedule/", shipment.eta),
        date_field("ETA/", shipment.eta),
    ]
    trigger_fields = [dropdown_field("Estatus DB/", shipment.initial_status)]
    return {
        "batch_id": batch_id,
        "clickup_list_id": list_id,
        "create_task": {
            "name": shipment.task_name,
            "description": description,
        },
        "set_custom_fields_before_status": non_trigger_fields,
        "set_custom_fields_last": trigger_fields,
        "shipment": {
            "shipment_key": shipment.shipment_key,
            "booking_number": shipment.booking_number,
            "container_numbers": shipment.container_numbers,
            "shipper_name": shipment.shipper_name,
            "origin": shipment.origin,
            "pol": shipment.pol,
            "port_of_discharge": shipment.port_of_discharge,
            "initial_status": shipment.initial_status,
        },
    }


def build_email_description(batch_id: str, shipment: EmailShipment) -> str:
    containers = "\n".join(f"- {container}" for container in shipment.container_numbers)
    return f"""From: {shipment.shipper_name} <{shipment.from_email}>
To: MTM Sandbox Shipments <{shipment.to_email}>
Date: {format_dt(shipment.received_at)}
Subject: {shipment.subject}

Hello Operations,

Please create and monitor this ONE shipment in the sandbox.

Carrier: ONE
Booking number: {shipment.booking_number}
Shipper: {shipment.shipper_name}
Shipper email: {shipment.shipper_email}
Customer: {shipment.customer_name}
Origin: {shipment.origin}
POL: {shipment.pol}
Mother POL: {shipment.mother_pol}
Port of discharge: {shipment.port_of_discharge}
Container count: {len(shipment.container_numbers)}
Container type: {shipment.container_type}
Container numbers:
{containers}
Cargo description: {shipment.cargo_description}
Cargo ready date: {format_dt(shipment.cargo_ready_date)}
ETD: {format_dt(shipment.etd)}
ETA: {format_dt(shipment.eta)}

This is a synthetic inbound email for automation testing.
Batch: {batch_id}
Shipment key: {shipment.shipment_key}

Regards,
{shipment.shipper_name}
"""


def apply_payload(
    client: ClickUpClient | None,
    payload: dict[str, Any],
    sleep_seconds: float,
) -> dict[str, Any]:
    assert client is not None
    task_id = ""
    task_url = ""
    try:
        created = client.create_task(
            payload["clickup_list_id"],
            name=payload["create_task"]["name"],
            description=payload["create_task"]["description"],
        )
        task_id = created["id"]
        task_url = created.get("url", "")
        for field in payload["set_custom_fields_before_status"]:
            set_custom_field(client, task_id, field)
            sleep_if_needed(sleep_seconds)
        for field in payload["set_custom_fields_last"]:
            set_custom_field(client, task_id, field)
            sleep_if_needed(sleep_seconds)
        return {"mode": "apply", "task_id": task_id, "task_url": task_url, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"mode": "apply", "task_id": task_id, "task_url": task_url, "error": str(exc)}


def set_custom_field(client: ClickUpClient, task_id: str, field: dict[str, Any]) -> None:
    client.set_task_custom_field_value(
        task_id,
        field["field_id"],
        field["value"],
        value_options=field.get("value_options"),
    )


def dry_run_result() -> dict[str, str]:
    return {"mode": "dry-run", "task_id": "", "task_url": "", "error": ""}


def short_text_extra(field_name: str, value: str) -> dict[str, Any]:
    return {"field_name": field_name, "field_id": EXTRA_FIELD_IDS[field_name], "type": "short_text", "value": value}


def email_extra(field_name: str, value: str) -> dict[str, Any]:
    return {"field_name": field_name, "field_id": EXTRA_FIELD_IDS[field_name], "type": "email", "value": value}


def text_extra(field_name: str, value: str) -> dict[str, Any]:
    return {"field_name": field_name, "field_id": EXTRA_FIELD_IDS[field_name], "type": "text", "value": value}


def date_extra(field_name: str, value: datetime) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": EXTRA_FIELD_IDS[field_name],
        "type": "date",
        "iso": format_dt(value),
        "value": int(value.timestamp() * 1000),
        "value_options": {"time": True},
    }


def to_manifest_row(
    batch_id: str,
    list_id: str,
    shipment: EmailShipment,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "clickup_list_id": list_id,
        "shipment_index": shipment.index,
        "shipment_key": shipment.shipment_key,
        "task_id": result.get("task_id", ""),
        "task_url": result.get("task_url", ""),
        "task_name": shipment.task_name,
        "received_at": format_dt(shipment.received_at),
        "from_email": shipment.from_email,
        "to_email": shipment.to_email,
        "subject": shipment.subject,
        "shipper_name": shipment.shipper_name,
        "shipper_email": shipment.shipper_email,
        "customer_name": shipment.customer_name,
        "origin": shipment.origin,
        "pol": shipment.pol,
        "mother_pol": shipment.mother_pol,
        "port_of_discharge": shipment.port_of_discharge,
        "booking_number": shipment.booking_number,
        "number_of_containers": len(shipment.container_numbers),
        "container_type": shipment.container_type,
        "container_numbers": "; ".join(shipment.container_numbers),
        "cargo_description": shipment.cargo_description,
        "cargo_ready_date": format_dt(shipment.cargo_ready_date),
        "etd": format_dt(shipment.etd),
        "eta": format_dt(shipment.eta),
        "initial_estatus_db": shipment.initial_status,
        "mode": result.get("mode", ""),
        "error": result.get("error", ""),
    }


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sleep_if_needed(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


if __name__ == "__main__":
    main()
