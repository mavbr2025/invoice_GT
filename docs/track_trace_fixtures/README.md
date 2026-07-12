# ONE Track-and-Trace Stress Fixtures

This folder supports sandbox testing for autonomous shipment management in ClickUp list `901712832326`.

The generator creates deterministic synthetic ONE events with replay timestamps seconds apart. It is designed to test status changes by updating `Estatus DB/` through the shipment lifecycle, plus the key date and tracking fields that ClickUp automations usually watch.

## Generate a 100-shipment stress file

```bash
python3 scripts/generate_one_track_trace_stress.py \
  --shipments 100 \
  --spacing-seconds 5 \
  --max-containers 5 \
  --start "2026-04-29T09:00:00-06:00" \
  --output-dir docs/track_trace_fixtures/generated
```

Outputs:

- `one_track_trace_events.csv`: human-readable event stream for review or import mapping.
- `one_track_trace_clickup_updates.jsonl`: replay-ready updates with ClickUp custom field IDs and dropdown option IDs.
- `one_track_trace_summary.json`: counts, field IDs, status option IDs, and batch metadata.

The script does not write to ClickUp. It only generates fixture files.

## Create Sandbox Shipments as Email Tasks

Use this when you want the ClickUp list to contain synthetic shipment tasks before replaying track-and-trace status updates.

Dry-run first:

```bash
python3 scripts/create_one_sandbox_email_shipments.py \
  --shipments 100 \
  --max-containers 5 \
  --start "2026-04-29T08:00:00-06:00" \
  --output-dir docs/track_trace_fixtures/email_shipments
```

Create the tasks in ClickUp:

```bash
python3 scripts/create_one_sandbox_email_shipments.py \
  --shipments 100 \
  --max-containers 5 \
  --start "2026-04-29T08:00:00-06:00" \
  --output-dir docs/track_trace_fixtures/email_shipments \
  --apply
```

The direct-creation script writes task descriptions that look like inbound emails and then sets structured ClickUp fields, including:

- `Carrier/`
- `Booking number/`
- `Container(s) number(s)/`
- `Number of Containers`
- `Container type and size/`
- `POL`
- `Mother POL`
- `Port Of Discharge`
- `Customer Name`
- `Shipper's Name`
- `Origin`
- `Cargo Description`
- `Cargo Ready Date`
- `ETD/`
- `ETA/`
- `Estatus DB/`

The `Estatus DB/` field is set last so automations that listen to the initial status change see a populated shipment.

## Replay Track-and-Trace Updates

After creating the email tasks with `--apply`, generate a matching T&T stream and replay it:

```bash
python3 scripts/generate_one_track_trace_stress.py \
  --shipments 10 \
  --spacing-seconds 2 \
  --max-containers 5 \
  --start "2026-04-29T10:30:00-06:00" \
  --output-dir docs/track_trace_fixtures/run_10/generated

python3 scripts/replay_one_track_trace_updates.py \
  --manifest docs/track_trace_fixtures/run_10/email_shipments/one_email_shipments_manifest.csv \
  --updates docs/track_trace_fixtures/run_10/generated/one_track_trace_clickup_updates.jsonl \
  --output docs/track_trace_fixtures/run_10/replay/apply_results.jsonl \
  --event-delay-seconds 2 \
  --field-delay-seconds 0.05 \
  --apply
```

The replay helper updates only dynamic tracking/status fields by default and sets `Estatus DB/` last in each event group. Use `--all-fields` only if you intentionally want every event to rewrite static shipment fields too.

## Statuses Covered

The normal status sequence is:

```text
Booking por Confirmar
Booking confirmado
En recolección de origen
En puerto de origen
Tránsito Marítimo
Por arribar
Arribado en destino
En ruta a almacén
En almacén
Embarque cerrado
```

The fixture also includes branch scenarios:

- `delayed_eta`: ETA changes and `Cambio de ETA` is set.
- `transshipment`: transshipment milestones and labels are populated.
- `customs_hold`: `Incidencia` and `Incidencia Tránsito` are set before delivery continues.
- `rolled`: origin sailing is rolled, then the shipment proceeds with a later ETD/ETA.
- `cancelled`: booking moves to `Cancelado`.

## Replay Guidance

Use `one_track_trace_clickup_updates.jsonl` for automation testing. Each line contains:

- `task_lookup`: default lookup by `Booking number/`.
- `suggested_task_name`: useful if your runner creates test tasks first.
- `replay_at`: when the update should be sent.
- `set_custom_fields`: ClickUp field IDs and values to apply.
- `comment_text`: optional audit/comment text for the synthetic carrier event.

For status automation validation, the replay runner should process the JSONL lines in file order and wait until each line's `replay_at`, or use the generated `replay_offset_seconds` from the CSV.

If the automation listens to the native ClickUp task status column, update that column in the replay runner as well. This fixture always updates the custom field `Estatus DB/`.
