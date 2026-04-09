from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings as BusinessCentralSettings
from clickup_integration.bc_sync import apply_clickup_to_bc_customer_sync
from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings
from clickup_integration.create_preview import apply_clickup_bc_customer_create
from clickup_integration.mapping import summarize_task_for_customer_mapping
from clickup_integration.matcher import match_clickup_customer_to_bc


app = FastAPI(title="ClickUp to Business Central Customer Bridge")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/clickup/webhooks/customer-sync")
async def clickup_customer_sync(
    request: Request,
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    expected_token = os.getenv("CLICKUP_WEBHOOK_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=500, detail="CLICKUP_WEBHOOK_TOKEN is not configured.")
    provided_token = _extract_webhook_token(
        x_webhook_token=x_webhook_token,
        authorization=authorization,
    )
    if provided_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token.")

    payload = await _safe_json(request)
    task_id = extract_task_id(payload)
    if not task_id:
        result = {
            "status": "ignored",
            "reason": "missing_task_id",
        }
        _log_webhook_result(task_id=None, result=result)
        return result

    try:
        clickup = ClickUpClient(ClickUpSettings.from_env())
        bc = BusinessCentralClient(BusinessCentralSettings.from_env())

        team_id = _resolve_clickup_team_id(clickup)
        use_custom_task_ids = _env_bool("CLICKUP_WEBHOOK_CUSTOM_TASK_IDS", default=True)
        logger.info(
            "Processing ClickUp webhook task_id=%s custom_task_ids=%s team_id=%s",
            task_id,
            use_custom_task_ids,
            team_id,
        )
        task = _fetch_clickup_task_for_webhook(
            clickup=clickup,
            task_id=task_id,
            custom_task_ids=use_custom_task_ids,
            team_id=team_id,
        )
        if task is None:
            logger.warning(
                "Ignoring webhook task_id=%s because the ClickUp task could not be fetched.",
                task_id,
            )
            result = {
                "status": "ignored",
                "reason": "task_lookup_failed",
                "task_id": task_id,
                "custom_task_ids": use_custom_task_ids,
                "team_id": team_id,
            }
            _log_webhook_result(task_id=task_id, result=result)
            return result
        summary = summarize_task_for_customer_mapping(task)

        if not summary.get("sync_eligible"):
            result = {
                "status": "ignored",
                "reason": "not_current_customer",
                "task_id": summary.get("task_id"),
                "custom_id": summary.get("custom_id"),
                "task_status": summary.get("status"),
            }
            _log_webhook_result(task_id=task_id, result=result)
            return result

        custom_fields = summary.get("custom_fields") or {}
        bc_customer_id = (custom_fields.get("Business Central Customer ID") or {}).get("value")
        bc_match_status = _resolve_clickup_match_status(custom_fields)

        if bc_customer_id and bc_match_status == "Confirmed":
            result = apply_clickup_to_bc_customer_sync(
                clickup_summary=summary,
                bc_client=bc,
            )
            response = {
                "status": "processed",
                "action": "update_existing_customer",
                "result": result,
            }
            _log_webhook_result(task_id=task_id, result=response)
            return response

        match_result = match_clickup_customer_to_bc(clickup_summary=summary, bc_client=bc)
        result = apply_clickup_bc_customer_create(
            clickup_summary=summary,
            current_match_result=match_result,
            bc_client=bc,
        )
        if result.get("status") != "applied":
            response = {
                "status": "processed",
                "action": "create_blocked",
                "result": result,
            }
            _log_webhook_result(task_id=task_id, result=response)
            return response

        writeback = result["writeback"]
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            writeback["field_ids"]["number"],
            writeback["bc_customer_number"],
        )
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            writeback["field_ids"]["id"],
            writeback["bc_customer_id"],
        )
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            writeback["field_ids"]["link"],
            writeback["bc_customer_link"],
        )
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            writeback["field_ids"]["legal_name"],
            writeback["bc_legal_name"],
        )
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            writeback["field_ids"]["status"],
            writeback["bc_match_status"],
        )
        response = {
            "status": "processed",
            "action": "create_customer_and_writeback",
            "result": result,
        }
        _log_webhook_result(task_id=task_id, result=response)
        return response
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - exercised in runtime logs
        logger.exception("ClickUp customer webhook failed for task_id=%s", task_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _fetch_clickup_task_for_webhook(
    *,
    clickup: ClickUpClient,
    task_id: str,
    custom_task_ids: bool,
    team_id: str | None,
) -> dict[str, Any] | None:
    attempts: list[tuple[bool, str | None]] = []
    primary_team_id = team_id or clickup.settings.default_workspace_id
    attempts.append((custom_task_ids, primary_team_id))
    if custom_task_ids and primary_team_id is None:
        inferred_team_id = _infer_clickup_team_id(clickup)
        if inferred_team_id:
            attempts.append((True, inferred_team_id))
    if not custom_task_ids:
        attempts.append((False, None))

    seen: set[tuple[bool, str | None]] = set()
    for attempt_custom_ids, attempt_team_id in attempts:
        key = (attempt_custom_ids, attempt_team_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            return clickup.get_task(
                task_id,
                custom_task_ids=attempt_custom_ids,
                team_id=attempt_team_id,
                include_subtasks=False,
            )
        except Exception:
            logger.exception(
                "ClickUp task lookup failed for task_id=%s custom_task_ids=%s team_id=%s",
                task_id,
                attempt_custom_ids,
                attempt_team_id,
            )
    return None


def _resolve_clickup_team_id(clickup: ClickUpClient) -> str | None:
    explicit_team_id = os.getenv("CLICKUP_WEBHOOK_TEAM_ID", "").strip() or None
    if explicit_team_id:
        return explicit_team_id
    return clickup.settings.default_workspace_id or _infer_clickup_team_id(clickup)


def _infer_clickup_team_id(clickup: ClickUpClient) -> str | None:
    try:
        workspaces = clickup.get_authorized_workspaces()
    except Exception:
        logger.exception("Unable to infer ClickUp team id from authorized workspaces.")
        return None

    teams = workspaces.get("teams") or []
    if len(teams) == 1:
        team_id = teams[0].get("id")
        return str(team_id) if team_id is not None else None

    default_workspace_id = clickup.settings.default_workspace_id
    if default_workspace_id:
        return default_workspace_id

    return None


def extract_task_id(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("Task ID"),
        payload.get("task_id"),
        payload.get("taskId"),
        payload.get("task", {}).get("id") if isinstance(payload.get("task"), dict) else None,
    ]
    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


def _resolve_clickup_match_status(custom_fields: dict[str, Any]) -> str | None:
    field = custom_fields.get("BC Match Status") or {}
    value = field.get("value")
    type_config = field.get("type_config") or {}
    for option in type_config.get("options", []):
        if option.get("id") == value or option.get("orderindex") == value:
            return option.get("name")
        if value is not None and str(option.get("id")) == str(value):
            return option.get("name")
        if value is not None and str(option.get("orderindex")) == str(value):
            return option.get("name")
    return None


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def _safe_json(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}

    if isinstance(payload, dict):
        return payload
    return {}


def _extract_webhook_token(
    *,
    x_webhook_token: str | None,
    authorization: str | None,
) -> str | None:
    if x_webhook_token:
        return x_webhook_token.strip()

    if not authorization:
        return None

    value = authorization.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _log_webhook_result(*, task_id: str | None, result: dict[str, Any]) -> None:
    logger.info(
        "Webhook result task_id=%s status=%s action=%s reason=%s result_status=%s result_message=%s",
        task_id,
        result.get("status"),
        result.get("action"),
        result.get("reason"),
        (result.get("result") or {}).get("status") if isinstance(result.get("result"), dict) else None,
        (result.get("result") or {}).get("message") if isinstance(result.get("result"), dict) else None,
    )
