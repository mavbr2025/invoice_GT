from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any
import re
import unicodedata

from business_central_client.client import BusinessCentralClient
from clickup_integration.mapping import is_current_customer_status


def match_clickup_customer_to_bc(
    *,
    clickup_summary: dict[str, Any],
    bc_client: BusinessCentralClient,
    top_n: int = 8,
) -> dict[str, Any]:
    task_status = clickup_summary.get("status")
    if not is_current_customer_status(task_status):
        return {
            "status": "not_current_customer",
            "message": (
                "ClickUp task is not eligible for BC customer sync. "
                "Only tasks with status CURRENT CUSTOMER are processed."
            ),
            "task_status": task_status,
            "market": clickup_summary.get("market"),
            "candidates": [],
        }

    market = clickup_summary.get("market")
    if not market:
        return {
            "status": "no_market",
            "message": "ClickUp task does not resolve to a supported market from Owner Country/.",
            "market": None,
            "candidates": [],
        }

    clickup_name = clickup_summary.get("name") or ""
    clickup_fields = clickup_summary.get("custom_fields") or {}
    clickup_website = (clickup_fields.get("Webpage") or {}).get("value") or ""
    clickup_tax_id = (clickup_fields.get("Tax ID") or {}).get("value") or ""
    normalized_clickup_tax_id = _norm_tax_id(clickup_tax_id)
    selected_customer = clickup_fields.get("Clientes/")
    selected_name = ""
    if selected_customer:
        from clickup_integration.mapping import resolve_dropdown_field

        resolved = resolve_dropdown_field(selected_customer)
        selected_name = (resolved or {}).get("name") or ""

    terms = [clickup_name, selected_name, clickup_website]
    terms = [term for term in terms if term]

    rows = bc_client.get_entities("customers", top=500, market=market).get("value", [])
    candidates = []
    exact_tax_id_matches = []
    for row in rows:
        row_name = row.get("displayName") or ""
        row_email = row.get("email") or ""
        row_website = row.get("website") or ""
        row_tax_id = row.get("taxRegistrationNumber") or ""
        normalized_row_tax_id = _norm_tax_id(row_tax_id)

        score = 0.0
        for term in terms:
            for candidate in [row_name, row_email, row_website, row_tax_id]:
                score = max(score, SequenceMatcher(None, _norm(term), _norm(candidate)).ratio())

        candidate = {
            "score": round(score, 3),
            "market": market,
            "id": row.get("id"),
            "number": row.get("number"),
            "displayName": row_name,
            "email": row_email,
            "website": row_website,
            "country": row.get("country"),
            "currencyCode": row.get("currencyCode"),
            "taxRegistrationNumber": row_tax_id,
        }

        if normalized_clickup_tax_id and normalized_clickup_tax_id == normalized_row_tax_id:
            candidate["score"] = 1.0
            candidate["match_basis"] = "exact_tax_id"
            exact_tax_id_matches.append(candidate)
            continue

        if score >= 0.45:
            candidates.append(candidate)

    if exact_tax_id_matches:
        exact_tax_id_matches.sort(key=lambda item: item["displayName"])
        return {
            "status": "likely_match",
            "task_status": task_status,
            "market": market,
            "clickup_name": clickup_name,
            "selected_customer_name": selected_name or None,
            "website": clickup_website or None,
            "tax_id": clickup_tax_id or None,
            "match_basis": "exact_tax_id",
            "candidates": exact_tax_id_matches[:top_n],
        }

    candidates.sort(key=lambda item: item["score"], reverse=True)
    top_candidates = candidates[:top_n]

    if normalized_clickup_tax_id and (not top_candidates or top_candidates[0]["score"] < 0.85):
        return {
            "status": "no_match",
            "market": market,
            "clickup_name": clickup_name,
            "selected_customer_name": selected_name or None,
            "website": clickup_website or None,
            "tax_id": clickup_tax_id or None,
            "match_basis": "tax_id_guard_no_exact_match",
            "candidates": top_candidates,
        }

    if not top_candidates:
        return {
            "status": "no_match",
            "market": market,
            "candidates": [],
        }

    best = top_candidates[0]
    status = "possible_match"
    if best["score"] >= 0.62:
        status = "likely_match"

    return {
        "status": status,
        "task_status": task_status,
        "market": market,
        "clickup_name": clickup_name,
        "selected_customer_name": selected_name or None,
        "website": clickup_website or None,
        "tax_id": clickup_tax_id or None,
        "candidates": top_candidates,
    }


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _norm_tax_id(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    value = value.upper()
    return re.sub(r"[^A-Z0-9]+", "", value)
