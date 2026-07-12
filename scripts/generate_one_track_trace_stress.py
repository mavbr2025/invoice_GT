#!/usr/bin/env python3
"""Generate deterministic ONE track-and-trace stress-test fixtures.

The output is intentionally replay-oriented: every row is one carrier event,
and every generated ClickUp update changes `Estatus DB/` plus the relevant
milestone fields. This lets testers validate status-change automations instead
of only validating final shipment snapshots.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_LIST_ID = "901712832326"
DEFAULT_START = "2026-04-29T09:00:00-06:00"

FIELD_IDS = {
    "Carrier/": "49d677fc-e828-41b9-a6f3-2acf65e50ad2",
    "Booking number/": "8b8c3ccd-917b-4321-bd92-5f60af17b1e1",
    "Container(s) number(s)/": "763c6719-b382-46c0-9c0d-6a0118ea9287",
    "Vessel and Voyage/": "7082ebff-8d81-45b5-b88d-461683b6a174",
    "POL": "452a3b68-1052-4942-8231-960e78a83a92",
    "Mother POL": "49434e76-4539-41a0-82d5-fa2b6bfe64f0",
    "Port Of Discharge": "303d68fa-f250-43ac-abe8-17b70e07b46d",
    "Container type and size/": "4f0fb6bf-229a-482c-81c5-07d4e16feb2d",
    "Number of Containers": "a05a2c81-2079-4467-9bfe-3723537bd350",
    "MTM booking (Yes/No)": "9b494c44-041f-46db-87a0-d3e6006e507f",
    "Estatus DB/": "716ee518-bc3e-4545-b288-691df9d544fc",
    "Carrier release": "f0f7289f-ac37-4ce5-bed2-cb950d7715d7",
    "Last T&T Update": "4d28e93b-4c09-45ab-805f-3ca8c8637235",
    "ETD/": "1ffe80c0-f071-4c1c-887c-d6951a6d8582",
    "ETA/": "736ddd1d-33da-4ff8-a128-f7f3f738987d",
    "ETA Schedule/": "62c173cc-2c00-4178-ad63-b0694ecbbfe0",
    "Gate out empty/": "528e9534-c8af-4a2f-8fa9-a0e6f99a59b1",
    "Gate-in full/": "7eecd4c5-4567-4a32-a5cf-bd285887ef7d",
    "Arrival at transshipment": "e7d2bfdd-b84f-47ef-8e19-f8eea1ceee7b",
    "Departure from transshipment": "7d11fab9-5671-466b-9369-5e94e91bc6ef",
    "Actual time of arrival": "973d0f8e-c02f-4b84-8e8c-efe32d093362",
    "Cambio de ETA": "8dd998b4-e9c2-4d8b-a311-c85819cb8655",
    "Incidencia": "11fffe04-9f5c-44fe-a734-568b9393e3e9",
    "Incidencia Tránsito": "1f169213-42dc-4694-8918-4f74f4ac3a68",
}

DROPDOWN_OPTION_IDS = {
    "Carrier/": {
        "ONE": "84c3305f-44f0-403b-b3b0-57350f44dddd",
    },
    "Estatus DB/": {
        "Booking por Confirmar": "21476bea-2b88-48a0-91cd-97951934289c",
        "Booking confirmado": "839df1ac-1667-4958-bb5c-f1c0f70cb9a5",
        "En recolección de origen": "dcadde82-9d53-49e6-ac94-12fa4637219a",
        "En puerto de origen": "8d179bad-c912-4331-a65f-1453be7311fe",
        "Tránsito Marítimo": "b9b45113-61ea-40a4-83db-7a381c822c46",
        "Por arribar": "e6f42fa2-8487-4726-9807-2bf3e0fa5b27",
        "Arribado en destino": "3afb26bb-5207-41e1-a507-944095156e16",
        "En ruta a almacén": "33e05883-7579-460a-9cce-b3e4cc95d23b",
        "En almacén": "d2f4d3d5-b978-4f9d-a961-56f150bee672",
        "Embarque cerrado": "f9dba86d-9bac-4996-b417-9513400103e4",
        "Cancelado": "61ce2eef-e917-43f7-891c-85ddfa953025",
    },
    "Carrier release": {
        "Released": "3bc3e067-1636-41b0-9874-7fc9be59e6a7",
        "Pending": "36368c91-3a3a-4836-b1c9-9d6a9065fe63",
    },
    "MTM booking (Yes/No)": {
        "Yes": "ceba1b41-57b5-4c6e-8786-55535ca69c2b",
        "No": "cefd1217-ce56-42f4-b52f-87dc83806c56",
    },
    "Container type and size/": {
        "20GP": "933afbd4-f9b9-4f1f-8abf-6b9500409231",
        "40 DRY": "83697d87-cc06-42a9-8b42-a448a25d7968",
        "40 HC": "34c23f89-371a-4069-b471-4ba8923071b0",
    },
    "POL": {
        "Ningbo, China": "974abbd6-00dc-46f0-878e-7cc7b91b7c02",
        "Qingdao, China": "0d3c3de1-53ca-42e6-b2f1-dab6c5743a02",
        "Shekou, China": "2f48df78-a449-44a4-882b-0cab87c35020",
        "Yantian, China": "d803c26c-346e-4ca7-8171-b14f9a44e35b",
        "Xiamen, China": "d2b40f9b-035a-4365-954f-1bf776714769",
        "Busan, South Korea": "b63600bd-71ab-44f3-98ef-017896bda65d",
    },
    "Mother POL": {
        "BUSAN": "5f93c214-7f19-4ab5-b22f-1815f8756de1",
        "NINGBO": "29bc2375-ea55-4f2f-8a1e-126933f24162",
        "SHANGHAI": "e722739d-ad97-4669-bdc0-8682aa11573c",
        "QINGDAO": "cfe7390c-4e40-495f-97a8-d3bf8c836b1e",
        "SHEKOU": "1e524da6-5001-4bb2-b4f6-4ca44fb49c36",
        "YANTIAN": "118211ce-923e-4d4e-9a85-90f6d74d9140",
    },
    "Port Of Discharge": {
        "MANZANILLO, MEXICO": "ed63adeb-b862-469e-8b31-352a3ead6053",
        "PUERTO QUETZAL": "d019581d-8cdc-4726-a737-6effe76a4154",
        "PUERTO SANTO TOMÁS DE CASTILLA": "08f0cb43-e4b1-4687-9c23-bbfcd071b596",
        "VERACRUZ, MEXICO": "7942fa0b-d725-4aaf-a4f2-ca376b54046f",
        "Lázaro Cárdenas, México": "2c235019-6db2-4cf8-b7f3-f2562ca07883",
    },
}

LABEL_OPTION_IDS = {
    "Incidencia Tránsito": {
        "Port Omission": "07d4346e-4b01-4620-ad89-bcec23444c2a",
        "Hold by WSL": "1622bde3-0d54-4e54-baa1-6cd873548ced",
        "Blocked by Carrier": "e7638f00-451c-4728-be2d-56f62b640291",
        "Trasbordo Pusan": "db94a276-35a7-455f-91fa-83b57ee01612",
        "Trasbordo Balboa": "151e7daa-cf56-4f96-9972-08ab88d8d329",
        "Trasbordo Cartagena": "7cfa228c-822f-410b-b6b0-b1a0e4b8f50d",
    }
}

DATE_FIELDS = {
    "Last T&T Update",
    "ETD/",
    "ETA/",
    "ETA Schedule/",
    "Gate out empty/",
    "Gate-in full/",
    "Arrival at transshipment",
    "Departure from transshipment",
    "Actual time of arrival",
}

CSV_COLUMNS = [
    "batch_id",
    "clickup_list_id",
    "shipment_index",
    "shipment_key",
    "task_name",
    "scenario",
    "event_sequence",
    "replay_offset_seconds",
    "replay_at",
    "carrier",
    "booking_number",
    "container_number",
    "number_of_containers",
    "vessel_and_voyage",
    "pol",
    "mother_pol",
    "port_of_discharge",
    "event_code",
    "event_description",
    "event_location",
    "event_time",
    "estatus_db",
    "etd",
    "eta",
    "last_tnt_update",
    "gate_out_empty",
    "gate_in_full",
    "arrival_at_transshipment",
    "departure_from_transshipment",
    "actual_time_of_arrival",
    "carrier_release",
    "cambio_de_eta",
    "incidencia",
    "incidencia_transito",
    "notes",
]


@dataclass(frozen=True)
class Route:
    pol: str
    mother_pol: str
    pod: str
    transshipment_location: str
    transshipment_label: str


@dataclass(frozen=True)
class Shipment:
    index: int
    shipment_key: str
    task_name: str
    scenario: str
    booking_number: str
    container_number: str
    number_of_containers: int
    vessel_and_voyage: str
    route: Route
    container_type: str
    etd: datetime
    eta_original: datetime
    eta_current: datetime


ROUTES = [
    Route("Ningbo, China", "NINGBO", "MANZANILLO, MEXICO", "Busan, South Korea", "Trasbordo Pusan"),
    Route("Shekou, China", "SHEKOU", "PUERTO QUETZAL", "Balboa, Panama", "Trasbordo Balboa"),
    Route("Yantian, China", "YANTIAN", "VERACRUZ, MEXICO", "Cartagena, Colombia", "Trasbordo Cartagena"),
    Route("Qingdao, China", "QINGDAO", "PUERTO SANTO TOMÁS DE CASTILLA", "Busan, South Korea", "Trasbordo Pusan"),
    Route("Xiamen, China", "YANTIAN", "Lázaro Cárdenas, México", "Balboa, Panama", "Trasbordo Balboa"),
    Route("Ningbo, China", "NINGBO", "PUERTO QUETZAL", "Cartagena, Colombia", "Trasbordo Cartagena"),
]

VESSELS = [
    "ONE INNOVATION",
    "ONE TRUTH",
    "ONE HAWK",
    "ONE COMMITMENT",
    "ONE MAJESTY",
    "ONE MODERN",
    "ONE MANHATTAN",
    "ONE RECOGNITION",
]

SCENARIO_CYCLE = [
    "normal",
    "normal",
    "normal",
    "delayed_eta",
    "transshipment",
    "normal",
    "customs_hold",
    "rolled",
    "normal",
    "cancelled",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ONE synthetic track-and-trace events for ClickUp sandbox testing."
    )
    parser.add_argument("--shipments", type=int, default=100, help="Number of shipments to generate.")
    parser.add_argument(
        "--spacing-seconds",
        type=int,
        default=5,
        help="Seconds between replay events in the generated stream.",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help="Replay start timestamp, ISO 8601. Default: %(default)s",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Batch identifier. Defaults to ONE-TT-STRESS-YYYYMMDDHHMMSS from --start.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/track_trace_fixtures/generated",
        help="Directory where CSV, JSONL, and summary files are written.",
    )
    parser.add_argument(
        "--list-id",
        default=DEFAULT_LIST_ID,
        help="ClickUp list id to include in output metadata.",
    )
    parser.add_argument("--seed", type=int, default=20260429, help="Deterministic random seed.")
    parser.add_argument(
        "--max-containers",
        type=int,
        default=1,
        help="Maximum containers per shipment. Use 5 to vary shipments from 1-5 containers.",
    )
    parser.add_argument(
        "--order",
        choices=("by-event", "by-shipment"),
        default="by-event",
        help="Replay order. by-event sends the same milestone wave across all shipments.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.shipments < 1:
        raise SystemExit("--shipments must be at least 1")
    if args.spacing_seconds < 1:
        raise SystemExit("--spacing-seconds must be at least 1")

    replay_start = parse_datetime(args.start)
    batch_id = args.batch_id or f"ONE-TT-STRESS-{replay_start.strftime('%Y%m%d%H%M%S')}"
    rng = random.Random(args.seed)

    if args.max_containers < 1:
        raise SystemExit("--max-containers must be at least 1")

    shipments = build_shipments(args.shipments, replay_start, rng, args.max_containers)
    event_rows: list[dict[str, Any]] = []
    update_rows: list[dict[str, Any]] = []

    unordered_events: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for shipment in shipments:
        for event in build_events_for_shipment(shipment):
            sort_key = (event["event_sequence"], shipment.index)
            if args.order == "by-shipment":
                sort_key = (shipment.index, event["event_sequence"])
            unordered_events.append((sort_key[0], sort_key[1], shipment_to_static_row(shipment), event))

    unordered_events.sort(key=lambda item: (item[0], item[1]))
    for replay_index, (_, _, static_row, event) in enumerate(unordered_events):
        replay_at = replay_start + timedelta(seconds=replay_index * args.spacing_seconds)
        replay_offset = replay_index * args.spacing_seconds
        row = {
            "batch_id": batch_id,
            "clickup_list_id": args.list_id,
            "replay_offset_seconds": replay_offset,
            "replay_at": format_dt(replay_at),
            **static_row,
            **event_to_csv(event, replay_at),
        }
        event_rows.append(row)
        update_rows.append(event_to_clickup_update(args.list_id, batch_id, static_row, event, replay_at))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "one_track_trace_events.csv"
    jsonl_path = output_dir / "one_track_trace_clickup_updates.jsonl"
    summary_path = output_dir / "one_track_trace_summary.json"

    write_csv(csv_path, event_rows)
    write_jsonl(jsonl_path, update_rows)
    write_summary(
        summary_path,
        batch_id=batch_id,
        list_id=args.list_id,
        replay_start=replay_start,
        spacing_seconds=args.spacing_seconds,
        shipments=shipments,
        events=event_rows,
        order=args.order,
    )

    print(json.dumps(
        {
            "batch_id": batch_id,
            "shipments": len(shipments),
            "events": len(event_rows),
            "spacing_seconds": args.spacing_seconds,
            "order": args.order,
            "csv": str(csv_path),
            "jsonl": str(jsonl_path),
            "summary": str(summary_path),
        },
        indent=2,
    ))


def build_shipments(
    count: int,
    replay_start: datetime,
    rng: random.Random,
    max_containers: int = 1,
) -> list[Shipment]:
    shipments: list[Shipment] = []
    for index in range(1, count + 1):
        scenario = SCENARIO_CYCLE[(index - 1) % len(SCENARIO_CYCLE)]
        route = ROUTES[(index - 1) % len(ROUTES)]
        vessel = VESSELS[(index - 1) % len(VESSELS)]
        voyage = f"{100 + index % 70:03d}E"
        etd = (replay_start + timedelta(days=3 + (index % 9))).replace(hour=18, minute=0, second=0)
        eta_original = etd + timedelta(days=24 + (index % 6))
        eta_current = eta_original
        if scenario in {"delayed_eta", "customs_hold"}:
            eta_current = eta_original + timedelta(days=3)
        if scenario == "rolled":
            etd = etd + timedelta(days=7)
            eta_original = eta_original + timedelta(days=7)
            eta_current = eta_original + timedelta(days=1)

        booking_number = f"ONEYTT26{index:06d}"
        container_numbers = build_container_numbers(index, max_containers)
        container_number = "; ".join(container_numbers)
        container_type = rng.choice(["40 HC", "40 DRY", "20GP"])
        shipment_key = f"ONE-TT-{index:04d}"
        shipments.append(
            Shipment(
                index=index,
                shipment_key=shipment_key,
                task_name=f"{shipment_key} | {booking_number} | {container_number}",
                scenario=scenario,
                booking_number=booking_number,
                container_number=container_number,
                number_of_containers=len(container_numbers),
                vessel_and_voyage=f"{vessel} {voyage}",
                route=route,
                container_type=container_type,
                etd=etd,
                eta_original=eta_original,
                eta_current=eta_current,
            )
        )
    return shipments


def build_events_for_shipment(shipment: Shipment) -> list[dict[str, Any]]:
    gate_out_empty = shipment.etd - timedelta(days=5, hours=4)
    gate_in_full = shipment.etd - timedelta(days=2, hours=6)
    trans_arrival = shipment.etd + timedelta(days=10, hours=8)
    trans_departure = trans_arrival + timedelta(days=2, hours=3)
    pre_arrival = shipment.eta_current - timedelta(days=2)
    actual_arrival = shipment.eta_current + timedelta(hours=8)
    en_ruta = actual_arrival + timedelta(days=1, hours=2)
    en_almacen = en_ruta + timedelta(hours=10)
    closed = en_almacen + timedelta(days=1, hours=6)

    events = [
        event(0, "BOOKING_REQUESTED", "Booking requested from ONE", shipment.etd - timedelta(days=8), "ONE eCommerce", "Booking por Confirmar"),
        event(1, "BOOKING_CONFIRMED", "Booking confirmed by ONE", shipment.etd - timedelta(days=7), "ONE eCommerce", "Booking confirmado"),
    ]

    if shipment.scenario == "cancelled":
        events.append(
            event(
                2,
                "BOOKING_CANCELLED",
                "Synthetic cancellation before origin pickup",
                shipment.etd - timedelta(days=6),
                "ONE eCommerce",
                "Cancelado",
                notes="Cancellation scenario for automation branch coverage.",
                incidencia=True,
                incidencia_transito=["Blocked by Carrier"],
            )
        )
        return events

    if shipment.scenario == "rolled":
        original_etd = shipment.etd - timedelta(days=7)
        events.append(
            event(
                2,
                "VESSEL_ROLLED",
                "Original sailing rolled by carrier",
                original_etd - timedelta(hours=6),
                shipment.route.pol,
                "En puerto de origen",
                notes="Rolled cargo; ETD and ETA moved forward.",
                cambio_de_eta=True,
                incidencia=True,
                incidencia_transito=["Port Omission"],
            )
        )

    events.extend(
        [
            event(3, "EMPTY_PICKED_UP", "Empty container released to shipper", gate_out_empty, shipment.route.pol, "En recolección de origen", {"Gate out empty/": gate_out_empty}),
            event(4, "GATE_IN_FULL", "Full container gated in at origin terminal", gate_in_full, shipment.route.pol, "En puerto de origen", {"Gate-in full/": gate_in_full}),
            event(5, "VESSEL_DEPARTED", "Vessel departed origin port", shipment.etd, shipment.route.pol, "Tránsito Marítimo", {"ETD/": shipment.etd}),
            event(6, "ARRIVED_TRANSSHIPMENT", "Container arrived at transshipment port", trans_arrival, shipment.route.transshipment_location, "Tránsito Marítimo", {"Arrival at transshipment": trans_arrival}, incidencia_transito=[shipment.route.transshipment_label]),
            event(7, "DEPARTED_TRANSSHIPMENT", "Container departed transshipment port", trans_departure, shipment.route.transshipment_location, "Tránsito Marítimo", {"Departure from transshipment": trans_departure}, incidencia_transito=[shipment.route.transshipment_label]),
            event(8, "PRE_ARRIVAL_NOTICE", "ONE pre-arrival notice received", pre_arrival, shipment.route.pod, "Por arribar", {"ETA/": shipment.eta_current}, cambio_de_eta=shipment.eta_current != shipment.eta_original),
            event(9, "ARRIVED_DESTINATION", "Vessel arrived at destination port", actual_arrival, shipment.route.pod, "Arribado en destino", {"Actual time of arrival": actual_arrival}, carrier_release="Released"),
        ]
    )

    if shipment.scenario == "customs_hold":
        events.append(
            event(
                10,
                "CUSTOMS_HOLD",
                "Synthetic hold before final delivery",
                actual_arrival + timedelta(hours=6),
                shipment.route.pod,
                "Arribado en destino",
                notes="Hold scenario for exception automation coverage.",
                incidencia=True,
                incidencia_transito=["Hold by WSL"],
                carrier_release="Pending",
            )
        )

    events.extend(
        [
            event(11, "OUT_FOR_DELIVERY", "Container released and moving to warehouse", en_ruta, shipment.route.pod, "En ruta a almacén", carrier_release="Released"),
            event(12, "DELIVERED_WAREHOUSE", "Container delivered at warehouse", en_almacen, "Customer warehouse", "En almacén", carrier_release="Released"),
            event(13, "SHIPMENT_CLOSED", "Synthetic shipment closed after delivery", closed, "Customer warehouse", "Embarque cerrado", carrier_release="Released"),
        ]
    )
    return events


def event(
    sequence: int,
    code: str,
    description: str,
    event_time: datetime,
    location: str,
    status: str,
    milestone_updates: dict[str, datetime] | None = None,
    *,
    carrier_release: str = "Pending",
    cambio_de_eta: bool = False,
    incidencia: bool = False,
    incidencia_transito: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "event_sequence": sequence,
        "event_code": code,
        "event_description": description,
        "event_location": location,
        "event_time": event_time,
        "estatus_db": status,
        "milestone_updates": milestone_updates or {},
        "carrier_release": carrier_release,
        "cambio_de_eta": cambio_de_eta,
        "incidencia": incidencia,
        "incidencia_transito": incidencia_transito or [],
        "notes": notes,
    }


def shipment_to_static_row(shipment: Shipment) -> dict[str, Any]:
    return {
        "shipment_index": shipment.index,
        "shipment_key": shipment.shipment_key,
        "task_name": shipment.task_name,
        "scenario": shipment.scenario,
        "carrier": "ONE",
        "booking_number": shipment.booking_number,
        "container_number": shipment.container_number,
        "number_of_containers": shipment.number_of_containers,
        "vessel_and_voyage": shipment.vessel_and_voyage,
        "pol": shipment.route.pol,
        "mother_pol": shipment.route.mother_pol,
        "port_of_discharge": shipment.route.pod,
        "container_type": shipment.container_type,
        "etd": format_dt(shipment.etd),
        "eta": format_dt(shipment.eta_current),
        "eta_schedule": format_dt(shipment.eta_original),
    }


def event_to_csv(event_row: dict[str, Any], replay_at: datetime) -> dict[str, Any]:
    milestones = event_row["milestone_updates"]
    return {
        "event_sequence": event_row["event_sequence"],
        "event_code": event_row["event_code"],
        "event_description": event_row["event_description"],
        "event_location": event_row["event_location"],
        "event_time": format_dt(event_row["event_time"]),
        "estatus_db": event_row["estatus_db"],
        "last_tnt_update": format_dt(replay_at),
        "gate_out_empty": format_optional_dt(milestones.get("Gate out empty/")),
        "gate_in_full": format_optional_dt(milestones.get("Gate-in full/")),
        "arrival_at_transshipment": format_optional_dt(milestones.get("Arrival at transshipment")),
        "departure_from_transshipment": format_optional_dt(milestones.get("Departure from transshipment")),
        "actual_time_of_arrival": format_optional_dt(milestones.get("Actual time of arrival")),
        "carrier_release": event_row["carrier_release"],
        "cambio_de_eta": event_row["cambio_de_eta"],
        "incidencia": event_row["incidencia"],
        "incidencia_transito": "|".join(event_row["incidencia_transito"]),
        "notes": event_row["notes"],
    }


def event_to_clickup_update(
    list_id: str,
    batch_id: str,
    static_row: dict[str, Any],
    event_row: dict[str, Any],
    replay_at: datetime,
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = [
        dropdown_field("Carrier/", "ONE"),
        text_field("Booking number/", static_row["booking_number"]),
        text_field("Container(s) number(s)/", static_row["container_number"]),
        text_field("Vessel and Voyage/", static_row["vessel_and_voyage"]),
        dropdown_field("POL", static_row["pol"]),
        dropdown_field("Mother POL", static_row["mother_pol"]),
        dropdown_field("Port Of Discharge", static_row["port_of_discharge"]),
        dropdown_field("Container type and size/", static_row["container_type"]),
        number_field("Number of Containers", static_row["number_of_containers"]),
        dropdown_field("MTM booking (Yes/No)", "Yes"),
        date_field("ETD/", parse_datetime(static_row["etd"])),
        date_field("ETA Schedule/", parse_datetime(static_row["eta_schedule"])),
        date_field("ETA/", parse_datetime(static_row["eta"])),
        date_field("Last T&T Update", replay_at),
        dropdown_field("Estatus DB/", event_row["estatus_db"]),
        dropdown_field("Carrier release", event_row["carrier_release"]),
        checkbox_field("Cambio de ETA", event_row["cambio_de_eta"]),
        checkbox_field("Incidencia", event_row["incidencia"]),
    ]
    for name, value in event_row["milestone_updates"].items():
        fields.append(date_field(name, value))
    if event_row["incidencia_transito"]:
        fields.append(labels_field("Incidencia Tránsito", event_row["incidencia_transito"]))

    return {
        "batch_id": batch_id,
        "clickup_list_id": list_id,
        "task_lookup": {
            "field_name": "Booking number/",
            "field_id": FIELD_IDS["Booking number/"],
            "value": static_row["booking_number"],
        },
        "suggested_task_name": static_row["task_name"],
        "shipment_key": static_row["shipment_key"],
        "scenario": static_row["scenario"],
        "event_sequence": event_row["event_sequence"],
        "replay_at": format_dt(replay_at),
        "event": {
            "carrier": "ONE",
            "code": event_row["event_code"],
            "description": event_row["event_description"],
            "location": event_row["event_location"],
            "event_time": format_dt(event_row["event_time"]),
            "status": event_row["estatus_db"],
        },
        "set_custom_fields": fields,
        "comment_text": (
            f"[Synthetic ONE T&T] {event_row['event_code']} - "
            f"{event_row['event_description']} at {event_row['event_location']} "
            f"({format_dt(event_row['event_time'])})"
        ),
    }


def dropdown_field(field_name: str, label: str) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": FIELD_IDS[field_name],
        "type": "drop_down",
        "label": label,
        "value": DROPDOWN_OPTION_IDS[field_name][label],
    }


def labels_field(field_name: str, labels: list[str]) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": FIELD_IDS[field_name],
        "type": "labels",
        "labels": labels,
        "value": [LABEL_OPTION_IDS[field_name][label] for label in labels],
    }


def text_field(field_name: str, value: str) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": FIELD_IDS[field_name],
        "type": "short_text",
        "value": value,
    }


def number_field(field_name: str, value: int | float) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": FIELD_IDS[field_name],
        "type": "number",
        "value": value,
    }


def checkbox_field(field_name: str, value: bool) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": FIELD_IDS[field_name],
        "type": "checkbox",
        "value": value,
    }


def date_field(field_name: str, value: datetime) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "field_id": FIELD_IDS[field_name],
        "type": "date",
        "iso": format_dt(value),
        "value": to_epoch_ms(value),
        "value_options": {"time": True},
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_summary(
    path: Path,
    *,
    batch_id: str,
    list_id: str,
    replay_start: datetime,
    spacing_seconds: int,
    shipments: list[Shipment],
    events: list[dict[str, Any]],
    order: str,
) -> None:
    scenario_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for shipment in shipments:
        scenario_counts[shipment.scenario] = scenario_counts.get(shipment.scenario, 0) + 1
    for event_row in events:
        status = event_row["estatus_db"]
        status_counts[status] = status_counts.get(status, 0) + 1
    payload = {
        "batch_id": batch_id,
        "clickup_list_id": list_id,
        "replay_start": format_dt(replay_start),
        "spacing_seconds": spacing_seconds,
        "order": order,
        "shipments": len(shipments),
        "events": len(events),
        "scenario_counts": scenario_counts,
        "status_counts": status_counts,
        "field_ids": FIELD_IDS,
        "status_option_ids": DROPDOWN_OPTION_IDS["Estatus DB/"],
        "notes": [
            "CSV is for review/import mapping.",
            "JSONL is for replay runners; date values are ClickUp epoch milliseconds.",
            "This generator does not write to ClickUp.",
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_dt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def format_optional_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return format_dt(value)


def to_epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def make_container_number(index: int) -> str:
    owner = "ONEU"
    serial = f"{260000 + index:06d}"
    partial = f"{owner}{serial}"
    return f"{partial}{container_check_digit(partial)}"


def build_container_numbers(shipment_index: int, max_containers: int = 1) -> list[str]:
    count = 1 + ((shipment_index - 1) % max_containers)
    return [
        make_container_number(shipment_index if offset == 0 else shipment_index + (offset * 1000))
        for offset in range(count)
    ]


def container_check_digit(container_without_check: str) -> int:
    values = {
        **{str(number): number for number in range(10)},
        "A": 10,
        "B": 12,
        "C": 13,
        "D": 14,
        "E": 15,
        "F": 16,
        "G": 17,
        "H": 18,
        "I": 19,
        "J": 20,
        "K": 21,
        "L": 23,
        "M": 24,
        "N": 25,
        "O": 26,
        "P": 27,
        "Q": 28,
        "R": 29,
        "S": 30,
        "T": 31,
        "U": 32,
        "V": 34,
        "W": 35,
        "X": 36,
        "Y": 37,
        "Z": 38,
    }
    total = 0
    for position, char in enumerate(container_without_check):
        total += values[char] * (2**position)
    check = total % 11
    return 0 if check == 10 else check


if __name__ == "__main__":
    main()
