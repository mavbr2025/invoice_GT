from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import unquote
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Request

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings as BusinessCentralSettings
from clickup_integration.bc_sync import apply_clickup_to_bc_customer_sync
from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings
from clickup_integration.create_preview import apply_clickup_bc_customer_create
from clickup_integration.invoice_sync import (
    InvoiceAutomationSettings,
    apply_clickup_bc_sales_invoice,
    prepare_clickup_invoice_status_transition,
)
from clickup_integration.mapping import summarize_task_for_customer_mapping
from clickup_integration.matcher import match_clickup_customer_to_bc
from clickup_integration.writeback import prepare_clickup_bc_writeback
from whatsapp_integration.booking_intake import BookingTarget, process_whatsapp_booking_intake
from whatsapp_integration.config import WhatsAppSettings
from whatsapp_integration.provider import (
    normalize_twilio_inbound,
    validate_twilio_request_signature,
)
from whatsapp_integration.router import route_customer_message


app = FastAPI(title="ClickUp to Business Central Customer Bridge")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/whatsapp/webhooks/inbound")
async def whatsapp_inbound(
    request: Request,
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
) -> dict[str, Any]:
    try:
        form_payload = await _safe_form_urlencoded(request)

        settings = WhatsAppSettings.from_env(
            require_booking=True,
            require_twilio_auth=False,
        )
        if settings.twilio_validate_signature:
            if not settings.twilio_auth_token:
                raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured.")
            if not validate_twilio_request_signature(
                url=settings.twilio_validate_url or str(request.url),
                params=form_payload,
                provided_signature=x_twilio_signature,
                auth_token=settings.twilio_auth_token,
            ):
                raise HTTPException(status_code=401, detail="Invalid Twilio signature.")

        event = normalize_twilio_inbound(form_payload)
        clickup = ClickUpClient(ClickUpSettings.from_env())
        route = route_customer_message(event, settings, clickup=clickup)
        logger.info(
            "WhatsApp route decision source=%s reason=%s message_id=%s customer_phone=%s list_id=%s customer_task_id=%s customer_task_custom_id=%s",
            route.source,
            route.reason,
            event.get("message_id"),
            event.get("customer_phone"),
            route.list_id,
            route.customer_task_id,
            route.customer_task_custom_id,
        )
        if route.route != "booking_intake":
            result = {
                "status": "ignored",
                "reason": route.reason or "unsupported_route",
                "route": route.route,
                "route_source": route.source,
                "message_id": event.get("message_id"),
            }
            _log_webhook_result(task_id=None, result=result)
            return result
        if not route.list_id:
            raise HTTPException(
                status_code=500,
                detail="No ClickUp target list resolved for WhatsApp intake.",
            )

        result = process_whatsapp_booking_intake(
            event=event,
            clickup=clickup,
            settings=settings,
            target=BookingTarget(
                list_id=route.list_id,
                customer_name=route.customer_name,
                customer_task_id=route.customer_task_id,
                customer_task_name=route.customer_task_name,
                customer_task_custom_id=route.customer_task_custom_id,
                route_source=route.source,
            ),
        )
        _log_webhook_result(task_id=result.get("task_id"), result=result)
        return result
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - exercised in runtime logs
        logger.exception("WhatsApp inbound webhook failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/clickup/webhooks/customer-sync")
@app.post("/clickup/webhooks/customer-sync/{webhook_path:path}")
async def clickup_customer_sync(
    request: Request,
    webhook_path: str = "",
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    if webhook_path and not webhook_path.startswith("customer-sync"):
        raise HTTPException(status_code=404, detail="Not Found")

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
    task_id = extract_task_id(payload) or extract_task_id_from_path(
        request.url.path,
        base_path="/clickup/webhooks/customer-sync",
    )
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
        if match_result.get("status") == "likely_match":
            writeback = prepare_clickup_bc_writeback(
                clickup_summary=summary,
                match_result=match_result,
                bc_client=bc,
            )
            _apply_clickup_customer_writeback(clickup=clickup, writeback=writeback)
            response = {
                "status": "processed",
                "action": "link_existing_customer",
                "result": {
                    "status": "applied",
                    "message": "Linked the existing Business Central customer back into ClickUp.",
                    "match_result": match_result,
                    "writeback": writeback,
                },
            }
            _log_webhook_result(task_id=task_id, result=response)
            return response

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
        _apply_clickup_customer_writeback(clickup=clickup, writeback=writeback)
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


@app.post("/clickup/webhooks/invoice-sync")
@app.post("/clickup/webhooks/invoice-sync/{webhook_path:path}")
async def clickup_invoice_sync(
    request: Request,
    webhook_path: str = "",
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    if webhook_path and not webhook_path.startswith("invoice-sync"):
        raise HTTPException(status_code=404, detail="Not Found")

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
    task_id = extract_task_id(payload) or extract_task_id_from_path(
        request.url.path,
        base_path="/clickup/webhooks/invoice-sync",
    )
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
        settings = InvoiceAutomationSettings.from_env()

        team_id = _resolve_clickup_team_id(clickup)
        use_custom_task_ids = _env_bool("CLICKUP_WEBHOOK_CUSTOM_TASK_IDS", default=True)
        logger.info(
            "Processing ClickUp invoice webhook task_id=%s custom_task_ids=%s team_id=%s",
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
        actions: list[str] = []
        transition_result = prepare_clickup_invoice_status_transition(
            clickup_summary=summary,
            settings=settings,
        )
        if transition_result.get("status") == "ready_to_update":
            clickup.update_task(
                summary["task_id"],
                status=settings.ready_status,
                custom_task_ids=use_custom_task_ids,
                team_id=team_id,
            )
            actions.append("update_status")
            logger.info(
                "Updated ClickUp task_id=%s status from %s to %s",
                summary.get("task_id"),
                summary.get("status"),
                settings.ready_status,
            )
            summary = {**summary, "status": settings.ready_status}

        invoice_result: dict[str, Any] | None = None
        if _status_equals(summary.get("status"), settings.ready_status):
            invoice_result = apply_clickup_bc_sales_invoice(
                clickup_summary=summary,
                bc_client=bc,
                settings=settings,
            )
            actions.append("create_sales_invoice")
            if invoice_result.get("status") == "applied":
                invoice_writeback = invoice_result.get("invoice_writeback") or {}
                if invoice_writeback.get("field_ids"):
                    _apply_clickup_invoice_writeback(clickup=clickup, writeback=invoice_writeback)
                    actions.append("writeback_invoice")
            response = {
                "status": "processed",
                "action": ",".join(actions),
                "transition": transition_result if actions and "update_status" in actions else None,
                "result": invoice_result,
            }
            _log_webhook_result(task_id=task_id, result=response)
            return response

        response = {
            "status": "ignored",
            "reason": transition_result.get("status"),
            "task_id": summary.get("task_id"),
            "task_status": summary.get("status"),
            "market": summary.get("market"),
            "result": transition_result,
        }
        _log_webhook_result(task_id=task_id, result=response)
        return response
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - exercised in runtime logs
        logger.exception("ClickUp invoice webhook failed for task_id=%s", task_id)
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


def extract_task_id_from_path(path: str, *, base_path: str) -> str | None:
    normalized_path = path.rstrip("/")
    normalized_base = base_path.rstrip("/")
    if not normalized_path.startswith(normalized_base):
        return None

    suffix = normalized_path[len(normalized_base) :].lstrip("/")
    if not suffix:
        return None

    first_segment = suffix.split("/", 1)[0].strip()
    if not first_segment:
        return None

    # ClickUp may double-encode path variables; decode conservatively.
    decoded_segment = unquote(unquote(first_segment)).strip()
    return decoded_segment or None


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


async def _safe_form_urlencoded(request: Request) -> dict[str, str]:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" not in content_type:
        return {}

    body = await request.body()
    if not body:
        return {}

    return {
        key: value
        for key, value in parse_qsl(body.decode("utf-8"), keep_blank_values=True)
    }


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


def _apply_clickup_customer_writeback(*, clickup: ClickUpClient, writeback: dict[str, Any]) -> None:
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


def _apply_clickup_invoice_writeback(*, clickup: ClickUpClient, writeback: dict[str, Any]) -> None:
    invoice_number_field_id = writeback.get("field_ids", {}).get("invoice_number")
    if invoice_number_field_id and writeback.get("bc_invoice_number") is not None:
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            invoice_number_field_id,
            writeback["bc_invoice_number"],
        )

    invoice_id_field_id = writeback.get("field_ids", {}).get("invoice_id")
    if invoice_id_field_id and writeback.get("bc_invoice_id") is not None:
        clickup.set_task_custom_field_value(
            writeback["task_id"],
            invoice_id_field_id,
            writeback["bc_invoice_id"],
        )


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


def _status_equals(left: str | None, right: str | None) -> bool:
    return " ".join((left or "").strip().lower().split()) == " ".join((right or "").strip().lower().split())
