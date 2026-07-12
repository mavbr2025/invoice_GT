from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import asdict
from typing import Any
from urllib.parse import unquote

from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings
from inspection_reports.canonical import (
    DEFAULT_CANONICAL_PAYLOAD_FIELD_ID,
    CanonicalPayloadError,
    canonical_request_mode,
    load_canonical_payload_from_task,
)
from inspection_reports.config import GraphSettings, InspectionReportSettings
from inspection_reports.sharepoint import SharePointGraphClient
from inspection_reports.workflow import InspectionReportWorkflow


WEBHOOK_PATH = "/clickup/webhooks/inspection-reports"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if event.get("job_type") == "inspection_report":
        return _process_report_job(event)
    return _accept_clickup_webhook(event, context)


def _accept_clickup_webhook(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_path = _request_path(event)
    if request_path == "/healthz":
        return _response(200, {"status": "ok"})

    headers = {
        str(key).lower(): str(value)
        for key, value in (event.get("headers") or {}).items()
        if value is not None
    }
    raw_body = _request_body(event)
    expected_token = _env("INSPECTION_APP_WEBHOOK_TOKEN")
    clickup_signature_secret = _env("CLICKUP_API_WEBHOOK_SECRET")
    if not expected_token and not clickup_signature_secret:
        return _response(500, {"status": "not_ready", "reason": "missing_webhook_auth"})
    if not _has_valid_webhook_auth(
        headers=headers,
        raw_body=raw_body,
        expected_token=expected_token,
        clickup_signature_secret=clickup_signature_secret,
    ):
        return _response(401, {"status": "unauthorized"})

    if request_path == f"{WEBHOOK_PATH}/readiness":
        return _response(200, _readiness())

    payload = _request_payload(raw_body)
    task_id = _extract_task_id(payload) or _extract_task_id_from_path(request_path)
    if not task_id:
        return _response(400, {"status": "invalid_request", "reason": "missing_task_id"})

    request_id = _request_id(task_id=task_id, payload=payload)
    worker_name = _env("INSPECTION_APP_WORKER_FUNCTION_NAME") or getattr(
        context,
        "invoked_function_arn",
        None,
    )
    if not worker_name:
        return _response(500, {"status": "not_ready", "reason": "missing_worker_function"})

    job = {
        "job_type": "inspection_report",
        "request_id": request_id,
        "task_id": task_id,
        "source_event": str(payload.get("event") or "clickup_automation"),
    }
    try:
        _invoke_async(worker_name=worker_name, job=job)
    except Exception as exc:  # noqa: BLE001 - ClickUp should retry an unaccepted event.
        logger.exception("Could not enqueue inspection report task_id=%s", task_id)
        return _response(503, {"status": "enqueue_failed", "task_id": task_id, "message": str(exc)})

    logger.info("Accepted inspection report request_id=%s task_id=%s", request_id, task_id)
    return _response(202, {"status": "accepted", "request_id": request_id, "task_id": task_id})


def _process_report_job(job: dict[str, Any]) -> dict[str, Any]:
    task_id = str(job.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("Inspection report job is missing task_id.")

    apply_mode = _env_bool("INSPECTION_APP_APPLY", default=False)
    clickup = ClickUpClient(ClickUpSettings.from_env())
    settings = InspectionReportSettings.from_env()
    task = _fetch_clickup_task(clickup=clickup, task_id=task_id, settings=settings)
    if task is None:
        raise RuntimeError(f"ClickUp task lookup failed for inspection task_id={task_id}.")

    configured_list_id = settings.clickup_list_id
    task_list_id = _task_list_id(task)
    if configured_list_id and task_list_id and task_list_id != configured_list_id:
        return {
            "status": "ignored",
            "reason": "unexpected_list",
            "task_id": task_id,
            "request_id": job.get("request_id"),
        }

    try:
        canonical_payload = load_canonical_payload_from_task(
            task,
            field_id=_env("INSPECTION_REPORT_CANONICAL_PAYLOAD_FIELD_ID")
            or DEFAULT_CANONICAL_PAYLOAD_FIELD_ID,
        )
    except CanonicalPayloadError as exc:
        return {
            "status": "blocked",
            "reason": "invalid_canonical_payload",
            "message": str(exc),
            "task_id": task_id,
            "request_id": job.get("request_id"),
        }

    trigger_statuses = _csv_env("INSPECTION_APP_TRIGGER_STATUSES")
    current_status = str((task.get("status") or {}).get("status") or "").strip()
    ignore_trigger_status = bool(job.get("ignore_trigger_status"))
    if (
        trigger_statuses
        and not ignore_trigger_status
        and _normalize(current_status) not in {_normalize(value) for value in trigger_statuses}
    ):
        return {
            "status": "ignored",
            "reason": "trigger_status_not_allowed",
            "task_id": task_id,
            "request_id": job.get("request_id"),
            "task_status": current_status or None,
        }

    requested_mode = canonical_request_mode(canonical_payload) if canonical_payload else "apply"
    run_mode = str(job.get("mode_override") or requested_mode).strip().lower()
    if run_mode not in {"apply", "dry_run"}:
        return {
            "status": "blocked",
            "reason": "invalid_run_mode",
            "task_id": task_id,
            "request_id": job.get("request_id"),
        }

    if canonical_payload and (run_mode == "dry_run" or not apply_mode):
        workflow = InspectionReportWorkflow(
            settings=settings,
            clickup_client=clickup,
            sharepoint_client=SharePointGraphClient(GraphSettings.from_env()),
        )
        result = workflow.run_canonical_payload(
            canonical_payload,
            task=task,
            dry_run=True,
        )
        response = asdict(result)
        response.update(
            {
                "request_id": job.get("request_id"),
                "canonical_payload_used": True,
                "run_mode": "dry_run",
            }
        )
        return response

    if not apply_mode:
        return {
            "status": "dry_run",
            "task_id": task_id,
            "request_id": job.get("request_id"),
            "task_status": current_status or None,
        }

    workflow = InspectionReportWorkflow(
        settings=settings,
        clickup_client=clickup,
        sharepoint_client=SharePointGraphClient(GraphSettings.from_env()),
    )
    result = workflow.complete_missing_report_for_task(
        task,
        target_status=_env("INSPECTION_REPORT_SUCCESS_STATUS") or "PASSED",
        canonical_payload=canonical_payload,
    )
    response = asdict(result)
    response["request_id"] = job.get("request_id")
    response["canonical_payload_used"] = bool(canonical_payload)
    logger.info(
        "Completed inspection report request_id=%s task_id=%s result=%s status_updated=%s",
        job.get("request_id"),
        task_id,
        response.get("status"),
        response.get("status_updated"),
    )
    return response


def _fetch_clickup_task(
    *,
    clickup: ClickUpClient,
    task_id: str,
    settings: InspectionReportSettings,
) -> dict[str, Any] | None:
    attempts = [
        (settings.custom_task_ids, settings.clickup_team_id or clickup.settings.default_workspace_id),
        (False, None),
    ]
    seen: set[tuple[bool, str | None]] = set()
    for custom_task_ids, team_id in attempts:
        key = (custom_task_ids, team_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            return clickup.get_task(
                task_id,
                custom_task_ids=custom_task_ids,
                team_id=team_id,
                include_subtasks=False,
            )
        except Exception:  # noqa: BLE001 - use the internal ID fallback below.
            logger.warning(
                "ClickUp lookup failed task_id=%s custom_task_ids=%s team_id=%s",
                task_id,
                custom_task_ids,
                team_id,
            )
    return None


def _invoke_async(*, worker_name: str, job: dict[str, Any]) -> None:
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=worker_name,
        InvocationType="Event",
        Payload=json.dumps(job).encode("utf-8"),
    )


def _request_body(event: dict[str, Any]) -> bytes:
    raw_body = event.get("body") or ""
    if isinstance(raw_body, dict):
        return json.dumps(raw_body, separators=(",", ":")).encode("utf-8")
    if event.get("isBase64Encoded"):
        return base64.b64decode(raw_body)
    return str(raw_body).encode("utf-8")


def _request_payload(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _request_path(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext") or {}
    http = request_context.get("http") or {}
    path = str(event.get("rawPath") or http.get("path") or "")
    return f"/{path.lstrip('/')}" if path else ""


def _extract_task_id(payload: dict[str, Any]) -> str | None:
    candidates = (
        payload.get("Task ID"),
        payload.get("task_id"),
        payload.get("taskId"),
        (payload.get("task") or {}).get("id") if isinstance(payload.get("task"), dict) else None,
    )
    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


def _extract_task_id_from_path(path: str) -> str | None:
    normalized_path = path.rstrip("/")
    normalized_base = WEBHOOK_PATH.rstrip("/")
    if not normalized_path.startswith(normalized_base):
        return None
    suffix = normalized_path[len(normalized_base) :].lstrip("/")
    if not suffix:
        return None
    return unquote(unquote(suffix.split("/", 1)[0])).strip() or None


def _provided_token(headers: dict[str, str]) -> str:
    token = headers.get("x-webhook-token", "").strip()
    if token:
        return token
    authorization = headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization


def _has_valid_webhook_auth(
    *,
    headers: dict[str, str],
    raw_body: bytes,
    expected_token: str | None,
    clickup_signature_secret: str | None,
) -> bool:
    provided_token = _provided_token(headers)
    if expected_token and hmac.compare_digest(provided_token, expected_token):
        return True

    signature = headers.get("x-signature", "").strip().lower()
    if not signature or not clickup_signature_secret:
        return False
    expected_signature = hmac.new(
        clickup_signature_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def _request_id(*, task_id: str, payload: dict[str, Any]) -> str:
    webhook_id = str(payload.get("webhook_id") or "").strip()
    history_items = payload.get("history_items") or []
    history_id = ""
    if history_items and isinstance(history_items[0], dict):
        history_id = str(history_items[0].get("id") or "").strip()
    if webhook_id and history_id:
        return f"{webhook_id}:{history_id}"
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"clickup:{task_id}:{fingerprint}"


def _task_list_id(task: dict[str, Any]) -> str | None:
    list_data = task.get("list") or {}
    candidate = list_data.get("id") if isinstance(list_data, dict) else None
    candidate = candidate or task.get("list_id")
    return str(candidate).strip() if candidate is not None and str(candidate).strip() else None


def _readiness() -> dict[str, Any]:
    missing = [
        name
        for name in ("INSPECTION_APP_WEBHOOK_TOKEN", "CLICKUP_ACCESS_TOKEN")
        if not _env(name)
    ]
    graph_error: str | None = None
    try:
        GraphSettings.from_env()
    except Exception as exc:  # noqa: BLE001 - a readiness response must stay machine-readable.
        graph_error = str(exc)

    settings = InspectionReportSettings.from_env()
    if not settings.clickup_list_id:
        missing.append("INSPECTION_REPORT_CLICKUP_LIST_ID")
    if not settings.report_link_field_ids:
        missing.append("INSPECTION_REPORT_LINK_FIELD_IDS")
    if not settings.picture_folder_field_ids:
        missing.append("INSPECTION_REPORT_PICTURE_FOLDER_FIELD_IDS")
    if not settings.report_attachment_field_ids:
        missing.append("INSPECTION_REPORT_ATTACHMENT_FIELD_IDS")
    if graph_error:
        missing.append("Microsoft Graph configuration")

    return {
        "status": "ready" if not missing else "not_ready",
        "missing_runtime_config": missing,
        "graph_error": graph_error,
        "apply_mode": _env_bool("INSPECTION_APP_APPLY", default=False),
        "success_status": _env("INSPECTION_REPORT_SUCCESS_STATUS") or "PASSED",
        "trigger_statuses": list(_csv_env("INSPECTION_APP_TRIGGER_STATUSES")),
        "clickup_api_signature_enabled": bool(_env("CLICKUP_API_WEBHOOK_SECRET")),
    }


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _env(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


def _env_bool(name: str, *, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> tuple[str, ...]:
    value = _env(name)
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
