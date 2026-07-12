from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only health check for the Business Central Banxico exchange-rate sync."
    )
    parser.add_argument("--market", default="MX", help="Business Central market profile.")
    parser.add_argument("--currency", default="USD", help="Currency code to check.")
    parser.add_argument(
        "--job-description",
        default="Actualizar USD desde BANXICO",
        help="Business Central job queue description to monitor.",
    )
    parser.add_argument(
        "--job-object-id",
        type=int,
        default=50139,
        help="Business Central job queue codeunit/object id to monitor.",
    )
    parser.add_argument(
        "--max-stale-days",
        type=int,
        default=4,
        help="Maximum allowed calendar-day age for the latest exchange-rate row.",
    )
    parser.add_argument(
        "--timezone",
        default="America/Mexico_City",
        help="Timezone used to calculate today's date.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    market_key = args.market.strip().upper()
    currency_code = args.currency.strip().upper()
    market = settings.get_market(market_key)
    if not market:
        return emit(
            {
                "ok": False,
                "market": market_key,
                "currency": currency_code,
                "issues": [f"Market profile {market_key} is not configured."],
            },
            exit_code=2,
        )

    client = BusinessCentralClient(settings)
    company_url = f"{settings.api_base_url}/companies({market.company_id})"

    job = None
    latest_rate = None
    future_rates: list[dict] = []
    connection_error = None

    today = date.today()
    try:
        today = date.today() if not args.timezone else date_from_timezone(args.timezone)
    except Exception:
        pass

    try:
        job = find_job_queue_entry(
            client=client,
            company_url=company_url,
            description=args.job_description,
            object_id=args.job_object_id,
        )
        latest_rate = find_latest_rate(
            client=client,
            company_url=company_url,
            currency_code=currency_code,
            latest_allowed_date=today,
        )
        future_rates = find_future_rates(
            client=client,
            company_url=company_url,
            currency_code=currency_code,
            today=today,
        )
    except Exception as exc:
        connection_error = f"{type(exc).__name__}: {exc}"

    issues: list[str] = []
    if connection_error:
        issues.append(f"Failed to query Business Central APIs: {connection_error}")
    if not job:
        issues.append(
            f"Job queue entry was not found for description {args.job_description!r} "
            f"or object id {args.job_object_id}."
        )
    else:
        status = (job.get("status") or "").strip()
        if status != "Ready":
            issues.append(
                f"Job queue entry status is {status!r}; expected 'Ready'. "
                f"Error: {job.get('errorMessage') or 'none'}"
            )

    stale_days = None
    if not latest_rate:
        issues.append(f"No {currency_code} currency exchange-rate rows were found.")
    else:
        starting_date = parse_iso_date(latest_rate.get("startingDate"))
        if not starting_date:
            issues.append(
                f"Latest {currency_code} rate has an invalid startingDate: "
                f"{latest_rate.get('startingDate')!r}."
            )
        else:
            stale_days = (today - starting_date).days
            if stale_days > args.max_stale_days:
                issues.append(
                    f"Latest {currency_code} rate is {stale_days} calendar days old "
                    f"({starting_date.isoformat()}); allowed maximum is {args.max_stale_days}."
                )
    if future_rates:
        future_summary = ", ".join(
            f"{rate.get('startingDate')}={rate.get('relationalExchangeRateAmount')}"
            for rate in future_rates[:10]
        )
        issues.append(
            f"Found future-dated {currency_code} exchange-rate rows after {today.isoformat()}: "
            f"{future_summary}."
        )

    summary = {
        "ok": not issues,
        "market": market_key,
        "company_id": market.company_id,
        "currency": currency_code,
        "today": today.isoformat(),
        "max_stale_days": args.max_stale_days,
        "stale_days": stale_days,
        "connection_error": connection_error,
        "job": summarize_job(job),
        "latest_rate": summarize_rate(latest_rate),
        "future_rates": [summarize_rate(rate) for rate in future_rates],
        "issues": issues,
    }
    return emit(summary, exit_code=0 if not issues else 2)


def find_job_queue_entry(
    *,
    client: BusinessCentralClient,
    company_url: str,
    description: str,
    object_id: int,
) -> dict | None:
    rows = client._request(
        "GET",
        f"{company_url}/jobQueueEntries",
        params={"$top": 200},
    ).get("value", [])
    rows = sorted(
        rows,
        key=lambda row: (
            row.get("earliestStartDateTime") or "",
            row.get("lastModifiedDateTime") or "",
        ),
        reverse=True,
    )
    normalized_description = description.casefold()
    for row in rows:
        if (row.get("description") or "").casefold() == normalized_description:
            return row
    for row in rows:
        if row.get("objectIdToRun") == object_id:
            return row
    return None


def find_latest_rate(
    *,
    client: BusinessCentralClient,
    company_url: str,
    currency_code: str,
    latest_allowed_date: date | None = None,
) -> dict | None:
    escaped_currency = currency_code.replace("'", "''")
    filters = f"currencyCode eq '{escaped_currency}'"
    if latest_allowed_date:
        filters += f" and startingDate le {latest_allowed_date.isoformat()}"
    rows = client._request(
        "GET",
        f"{company_url}/currencyExchangeRates",
        params={
            "$filter": filters,
            "$orderby": "startingDate desc",
            "$top": 1,
        },
    ).get("value", [])
    return rows[0] if rows else None


def find_future_rates(
    *,
    client: BusinessCentralClient,
    company_url: str,
    currency_code: str,
    today: date,
) -> list[dict]:
    escaped_currency = currency_code.replace("'", "''")
    return client._request(
        "GET",
        f"{company_url}/currencyExchangeRates",
        params={
            "$filter": f"currencyCode eq '{escaped_currency}' and startingDate gt {today.isoformat()}",
            "$orderby": "startingDate asc",
            "$top": 10,
        },
    ).get("value", [])


def summarize_job(job: dict | None) -> dict | None:
    if not job:
        return None
    keys = (
        "id",
        "jobQueueEntryId",
        "description",
        "status",
        "scheduled",
        "objectTypeToRun",
        "objectIdToRun",
        "objectCaptionToRun",
        "earliestStartDateTime",
        "lastReadyState",
        "lastModifiedDateTime",
        "errorMessage",
    )
    return {key: job.get(key) for key in keys}


def summarize_rate(rate: dict | None) -> dict | None:
    if not rate:
        return None
    keys = (
        "id",
        "currencyCode",
        "startingDate",
        "exchangeRateAmount",
        "relationalCurrencyCode",
        "relationalExchangeRateAmount",
        "lastModifiedDateTime",
    )
    return {key: rate.get(key) for key in keys}


def parse_iso_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def date_from_timezone(timezone_name: str) -> date:
    from datetime import datetime

    return datetime.now(ZoneInfo(timezone_name)).date()


def emit(payload: dict, *, exit_code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
