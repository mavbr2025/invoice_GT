from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from typing import Any

import requests

from business_central_client.auth import TokenProvider
from business_central_client.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Business Central invoice report/layout selections for one customer."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/invoice_layouts/gt.toml"),
        help="Invoice layout TOML config.",
    )
    parser.add_argument("--market", help="Configured BC market key, for example GT.")
    parser.add_argument("--customer-number", help="BC customer number, for example C00081.")
    parser.add_argument(
        "--company-name",
        help="BC company name stored in Report Layout Selection.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    market_key = args.market or config.get("company", {}).get("market") or "GT"
    customer_number = args.customer_number or first_customer_number(config)
    company_name = args.company_name or config.get("company", {}).get("bc_company_name") or "MTM_GT_PROD"

    settings = Settings.from_env()
    market = settings.get_market(market_key)
    if not market:
        raise SystemExit(f"Market {market_key} is not configured.")

    client = LayoutAuditClient(settings, market.company_id)
    audit = build_audit(
        client=client,
        customer_number=customer_number,
        company_name=company_name,
        config=config,
    )
    print(json.dumps(audit, indent=2, sort_keys=True, default=str))


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def first_customer_number(config: dict[str, Any]) -> str:
    customers = config.get("customers") or {}
    if not customers:
        raise SystemExit("No customer number was supplied and the config has no customers.")
    return next(iter(customers))


class LayoutAuditClient:
    def __init__(self, settings: Settings, company_id: str) -> None:
        self.settings = settings
        self.company_id = company_id
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {TokenProvider(settings).get_token()}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": settings.user_agent,
            }
        )

    def get(self, entity: str, *, filters: str | None = None, top: int = 500) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"$top": top}
        if filters:
            params["$filter"] = filters
        url = (
            "https://api.businesscentral.dynamics.com/"
            f"v2.0/{self.settings.environment}/api/mtmlogix/layoutAudit/v1.0/"
            f"companies({self.company_id})/{entity}"
        )
        response = self.session.get(url, params=params, timeout=self.settings.timeout_seconds)
        if response.status_code == 404:
            raise SystemExit(
                "The layout audit API is not published in BC yet. "
                "Publish extension version 0.1.1.0 first."
            )
        response.raise_for_status()
        return response.json().get("value", [])


def build_audit(
    *,
    client: LayoutAuditClient,
    customer_number: str,
    company_name: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    customer_rows = client.get(
        "customerLayoutSetup",
        filters=f"number eq '{escape_odata(customer_number)}'",
        top=2,
    )
    customer = customer_rows[0] if customer_rows else None

    profiles = client.get("documentSendingProfiles", top=500)
    selected_profile_code = (customer or {}).get("documentSendingProfile") or None
    selected_profile = choose_document_profile(profiles, selected_profile_code)

    custom_rows = [
        row
        for row in client.get(
            "customReportSelections",
            filters=f"sourceNo eq '{escape_odata(customer_number)}'",
            top=500,
        )
        if is_invoice_usage(row.get("usage"))
    ]
    report_rows = [
        row
        for row in client.get("reportSelections", top=500)
        if is_invoice_usage(row.get("usage"))
    ]
    layout_selection_rows = [
        row
        for row in client.get("reportLayoutSelections", top=1000)
        if (row.get("companyName") or "").upper() == company_name.upper()
    ]
    layout_rows = client.get("reportLayouts", top=2000)

    effective_rows = [
        row for row in custom_rows if row.get("useForEmailAttachment")
    ] or [
        row for row in report_rows if row.get("useForEmailAttachment")
    ]

    effective_layouts = [
        describe_effective_layout(
            row=row,
            layout_selection_rows=layout_selection_rows,
            layout_rows=layout_rows,
        )
        for row in effective_rows
    ]

    findings = classify_findings(
        customer=customer,
        selected_profile=selected_profile,
        custom_rows=custom_rows,
        effective_layouts=effective_layouts,
    )

    return {
        "target_layout": (config or {}).get("layout"),
        "target_overrides": (config or {}).get("overrides"),
        "customer": customer,
        "document_sending_profile": selected_profile,
        "customer_specific_invoice_report_selections": custom_rows,
        "global_invoice_report_selections": report_rows,
        "effective_invoice_email_attachment_layouts": effective_layouts,
        "findings": findings,
    }


def choose_document_profile(
    profiles: list[dict[str, Any]],
    selected_profile_code: str | None,
) -> dict[str, Any] | None:
    if selected_profile_code:
        for profile in profiles:
            if (profile.get("code") or "").upper() == selected_profile_code.upper():
                return profile
    for profile in profiles:
        if profile.get("isDefault"):
            return profile
    return None


def describe_effective_layout(
    *,
    row: dict[str, Any],
    layout_selection_rows: list[dict[str, Any]],
    layout_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    report_id = row.get("reportId")
    explicit_layout_name = (
        row.get("reportLayoutName")
        or row.get("emailAttachmentLayoutName")
        or row.get("customReportLayoutCode")
        or None
    )
    default_selection = next(
        (selection for selection in layout_selection_rows if selection.get("reportId") == report_id),
        None,
    )
    selected_layout_name = explicit_layout_name or (default_selection or {}).get("customReportLayoutCode")
    installed_layouts = [
        layout
        for layout in layout_rows
        if layout.get("reportId") == report_id
        and (
            not selected_layout_name
            or selected_layout_name in {
                layout.get("name"),
                layout.get("caption"),
                layout.get("description"),
            }
        )
    ]
    return {
        "source": "customer" if "sourceNo" in row else "global",
        "report_id": report_id,
        "report_caption": row.get("reportCaption"),
        "explicit_layout_name": explicit_layout_name,
        "default_layout_selection": default_selection,
        "matched_installed_layouts": installed_layouts,
    }


def classify_findings(
    *,
    customer: dict[str, Any] | None,
    selected_profile: dict[str, Any] | None,
    custom_rows: list[dict[str, Any]],
    effective_layouts: list[dict[str, Any]],
) -> list[str]:
    findings: list[str] = []
    if not customer:
        findings.append("Customer was not found in BC layout audit API.")
        return findings
    if not customer.get("vatRegistrationNumber"):
        findings.append("Customer NIT/VAT registration is missing in BC source data.")
    if not selected_profile:
        findings.append("No document sending profile could be resolved.")
    elif "pdf" not in (selected_profile.get("emailAttachment") or "").lower():
        findings.append("Resolved document sending profile does not clearly attach a PDF.")
    if custom_rows:
        findings.append("Customer-specific invoice report selections exist and may override global layout.")
    if not effective_layouts:
        findings.append("No effective invoice email attachment layout was found.")
    for layout in effective_layouts:
        if not layout.get("explicit_layout_name") and not layout.get("default_layout_selection"):
            findings.append(f"Report {layout.get('report_id')} has no explicit or default layout selection.")
        if any((row.get("isObsolete") for row in layout.get("matched_installed_layouts", []))):
            findings.append(f"Report {layout.get('report_id')} matched an obsolete layout.")
    return findings


def is_invoice_usage(value: Any) -> bool:
    normalized = str(value or "").lower()
    return "invoice" in normalized and "credit" not in normalized


def escape_odata(value: str) -> str:
    return value.replace("'", "''")


if __name__ == "__main__":
    main()
