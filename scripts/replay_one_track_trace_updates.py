#!/usr/bin/env python3
"""Replay generated ONE track-and-trace updates into ClickUp tasks.

Default mode is a dry run. Pass --apply to update ClickUp. The script maps
generated events to created sandbox tasks by `Booking number/` using the email
shipment manifest produced by create_one_sandbox_email_shipments.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from clickup_integration.client import ClickUpClient  # noqa: E402
from clickup_integration.config import ClickUpSettings  # noqa: E402


DYNAMIC_FIELD_NAMES = {
    "Last T&T Update",
    "ETD/",
    "ETA/",
    "ETA Schedule/",
    "Gate out empty/",
    "Gate-in full/",
    "Arrival at transshipment",
    "Departure from transshipment",
    "Actual time of arrival",
    "Carrier release",
    "Cambio de ETA",
    "Incidencia",
    "Incidencia Tránsito",
    "Estatus DB/",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay ONE T&T JSONL updates to ClickUp tasks.")
    parser.add_argument(
        "--manifest",
        default="docs/track_trace_fixtures/email_shipments/one_email_shipments_manifest.csv",
        help="CSV manifest from create_one_sandbox_email_shipments.py.",
    )
    parser.add_argument(
        "--updates",
        default="docs/track_trace_fixtures/generated/one_track_trace_clickup_updates.jsonl",
        help="JSONL updates from generate_one_track_trace_stress.py.",
    )
    parser.add_argument(
        "--output",
        default="docs/track_trace_fixtures/replay/one_track_trace_replay_results.jsonl",
        help="Replay result JSONL path.",
    )
    parser.add_argument(
        "--event-delay-seconds",
        type=float,
        default=0,
        help="Delay after each event update group. Use 2-5 seconds for automation stress tests.",
    )
    parser.add_argument(
        "--field-delay-seconds",
        type=float,
        default=0.05,
        help="Small delay between ClickUp field API calls when --apply is used.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update ClickUp. Omit for dry-run only.",
    )
    parser.add_argument(
        "--all-fields",
        action="store_true",
        help="Replay all generated fields instead of only dynamic tracking/status fields.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Optional cap for smoke testing. 0 means all matching events.",
    )
    parser.add_argument(
        "--only-booking",
        default="",
        help="Replay only updates for this booking number.",
    )
    parser.add_argument(
        "--only-status",
        default="",
        help="Replay only updates whose T&T status matches this value.",
    )
    parser.add_argument(
        "--only-event-code",
        default="",
        help="Replay only updates whose event code matches this value.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_by_booking = load_task_lookup(Path(args.manifest))
    updates = load_updates(
        Path(args.updates),
        task_by_booking,
        args.max_events,
        only_booking=args.only_booking,
        only_status=args.only_status,
        only_event_code=args.only_event_code,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")

    client = ClickUpClient(ClickUpSettings.from_env()) if args.apply else None
    results: list[dict[str, Any]] = []
    started = time.monotonic()

    for index, update in enumerate(updates, start=1):
        result = replay_update(
            client,
            update,
            task_by_booking,
            all_fields=args.all_fields,
            field_delay_seconds=args.field_delay_seconds,
        )
        result["event_index"] = index
        result["events_total"] = len(updates)
        results.append(result)
        append_jsonl(output_path, result)

        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry-run",
                    "event": f"{index}/{len(updates)}",
                    "booking_number": result["booking_number"],
                    "status": result["status"],
                    "task_id": result["task_id"],
                    "error": result["error"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if args.apply and args.event_delay_seconds > 0 and index < len(updates):
            time.sleep(args.event_delay_seconds)

    elapsed = round(time.monotonic() - started, 2)
    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "manifest": args.manifest,
        "updates": args.updates,
        "output": args.output,
        "tasks": len(task_by_booking),
        "events": len(updates),
        "successful_events": sum(1 for result in results if not result["error"]),
        "failed_events": sum(1 for result in results if result["error"]),
        "elapsed_seconds": elapsed,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


def load_task_lookup(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Manifest not found: {path}")
    lookup: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as file_obj:
        for row in csv.DictReader(file_obj):
            booking = row.get("booking_number", "").strip()
            task_id = row.get("task_id", "").strip()
            if booking and task_id:
                lookup[booking] = {
                    "task_id": task_id,
                    "task_url": row.get("task_url", "").strip(),
                    "shipment_key": row.get("shipment_key", "").strip(),
                }
    if not lookup:
        raise SystemExit(
            f"No task IDs found in manifest: {path}. Run create_one_sandbox_email_shipments.py --apply first."
        )
    return lookup


def load_updates(
    path: Path,
    task_by_booking: dict[str, dict[str, str]],
    max_events: int,
    *,
    only_booking: str = "",
    only_status: str = "",
    only_event_code: str = "",
) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Updates file not found: {path}")
    selected: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file_obj:
        for line in file_obj:
            if not line.strip():
                continue
            update = json.loads(line)
            booking = update["task_lookup"]["value"]
            if booking not in task_by_booking:
                continue
            if only_booking and booking != only_booking:
                continue
            if only_status and update["event"]["status"] != only_status:
                continue
            if only_event_code and update["event"]["code"] != only_event_code:
                continue
            selected.append(update)
            if max_events and len(selected) >= max_events:
                break
    if not selected:
        raise SystemExit("No matching updates found for task IDs in the manifest.")
    return selected


def replay_update(
    client: ClickUpClient | None,
    update: dict[str, Any],
    task_by_booking: dict[str, dict[str, str]],
    *,
    all_fields: bool,
    field_delay_seconds: float,
) -> dict[str, Any]:
    booking = update["task_lookup"]["value"]
    task = task_by_booking[booking]
    task_id = task["task_id"]
    fields = select_fields(update["set_custom_fields"], all_fields=all_fields)
    fields = sort_status_last(fields)
    error = ""
    applied_fields: list[str] = []
    if client is not None:
        try:
            for field in fields:
                client.set_task_custom_field_value(
                    task_id,
                    field["field_id"],
                    field["value"],
                    value_options=field.get("value_options"),
                )
                applied_fields.append(field["field_name"])
                if field_delay_seconds > 0:
                    time.sleep(field_delay_seconds)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

    return {
        "mode": "apply" if client is not None else "dry-run",
        "batch_id": update["batch_id"],
        "booking_number": booking,
        "shipment_key": update["shipment_key"],
        "task_id": task_id,
        "task_url": task.get("task_url", ""),
        "event_sequence": update["event_sequence"],
        "event_code": update["event"]["code"],
        "status": update["event"]["status"],
        "fields": [field["field_name"] for field in fields],
        "applied_fields": applied_fields,
        "error": error,
    }


def select_fields(fields: list[dict[str, Any]], *, all_fields: bool) -> list[dict[str, Any]]:
    if all_fields:
        return fields
    return [field for field in fields if field.get("field_name") in DYNAMIC_FIELD_NAMES]


def sort_status_last(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(fields, key=lambda field: field.get("field_name") == "Estatus DB/")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
