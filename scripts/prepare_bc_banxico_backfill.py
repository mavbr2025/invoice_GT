from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings


BANXICO_URL = "https://www.banxico.org.mx/tipcamb/tipCamIHAction.do"


@dataclass(frozen=True)
class BanxicoRow:
    date: date
    determination: Decimal | None
    publication_dof: Decimal | None
    obligations: Decimal | None
    effective_fix: Decimal
    effective_source_date: date

    @property
    def carried_forward(self) -> bool:
        return self.determination is None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or apply a Business Central USD/MXN exchange-rate backfill "
            "from Banxico's official Mercado cambiario table."
        )
    )
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD.")
    parser.add_argument("--market", default="MX", help="Business Central market profile.")
    parser.add_argument("--currency", default="USD", help="Business Central currency code.")
    parser.add_argument("--output-dir", default="output", help="Directory for CSV and report files.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert missing rows into Business Central via the published MX_ratesdivisas OData page.",
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    if start_date > end_date:
        raise ValueError("--start must be on or before --end")

    settings = Settings.from_env()
    market_key = args.market.strip().upper()
    currency_code = args.currency.strip().upper()
    market = settings.get_market(market_key)
    if not market:
        raise ValueError(f"Market profile {market_key} is not configured.")

    client = BusinessCentralClient(settings)
    company_url = f"{settings.api_base_url}/companies({market.company_id})"

    # Fetch extra previous dates so a leading weekend/holiday can carry forward
    # the most recent official FIX determination.
    banxico_start = start_date - timedelta(days=14)
    banxico_rows, source_url = fetch_banxico_rows(banxico_start, end_date)
    window_rows = [row for row in banxico_rows if start_date <= row.date <= end_date]

    existing_rows = get_existing_bc_rates(
        client=client,
        company_url=company_url,
        currency_code=currency_code,
        start_date=start_date,
        end_date=end_date,
    )
    existing_by_date = {row["startingDate"]: row for row in existing_rows}

    prepared_rows = []
    for row in window_rows:
        date_key = row.date.isoformat()
        existing = existing_by_date.get(date_key)
        prepared_rows.append(
            {
                "Currency_Code": currency_code,
                "Starting_Date": date_key,
                "Relational_Currency_Code": "",
                "Exchange_Rate_Amount": "1",
                "Relational_Exch_Rate_Amount": decimal_text(row.effective_fix),
                "Adjustment_Exch_Rate_Amount": "1",
                "Relational_Adjmt_Exch_Rate_Amt": decimal_text(row.effective_fix),
                "Fix_Exchange_Rate_Amount": "Currency",
                "Action": "skip_existing" if existing else "insert",
                "Existing_BC_Rate": existing.get("relationalExchangeRateAmount") if existing else "",
                "Banxico_FIX_Date": row.date.isoformat(),
                "Banxico_Determination": decimal_text(row.determination),
                "Banxico_Publication_DOF": decimal_text(row.publication_dof),
                "Banxico_For_Obligations": decimal_text(row.obligations),
                "Effective_Source_Date": row.effective_source_date.isoformat(),
                "Carried_Forward": str(row.carried_forward).lower(),
                "Source_URL": source_url,
            }
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"bc_banxico_backfill_{start_date.isoformat()}_{end_date.isoformat()}"
    csv_path = output_dir / f"{stem}_import.csv"
    report_path = output_dir / f"{stem}_validation.json"

    write_csv(csv_path, prepared_rows)

    apply_result = None
    if args.apply:
        apply_result = apply_missing_rows(
            settings=settings,
            client=client,
            company_name="MTM_MX_PROD",
            rows=[row for row in prepared_rows if row["Action"] == "insert"],
        )

    report = {
        "market": market_key,
        "company_id": market.company_id,
        "currency": currency_code,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "source_url": source_url,
        "csv_path": str(csv_path.resolve()),
        "existing_count": len(existing_rows),
        "prepared_count": len(prepared_rows),
        "insert_count": sum(1 for row in prepared_rows if row["Action"] == "insert"),
        "skip_existing_count": sum(1 for row in prepared_rows if row["Action"] == "skip_existing"),
        "carried_forward_count": sum(1 for row in prepared_rows if row["Carried_Forward"] == "true"),
        "rows": prepared_rows,
        "apply_result": apply_result,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        json.dumps(
            {
                "csv_path": str(csv_path.resolve()),
                "report_path": str(report_path.resolve()),
                "prepared_count": report["prepared_count"],
                "insert_count": report["insert_count"],
                "skip_existing_count": report["skip_existing_count"],
                "carried_forward_count": report["carried_forward_count"],
                "applied": bool(args.apply),
                "apply_result": apply_result,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fetch_banxico_rows(start_date: date, end_date: date) -> tuple[list[BanxicoRow], str]:
    params = {
        "idioma": "sp",
        "fechaInicial": start_date.strftime("%d/%m/%Y"),
        "fechaFinal": end_date.strftime("%d/%m/%Y"),
        "salida": "HTML",
    }
    response = requests.get(
        BANXICO_URL,
        params=params,
        headers={"User-Agent": "MTMLogixBanxicoBackfill/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    text = response.content.decode("ISO-8859-1", errors="replace")
    source_url = f"{BANXICO_URL}?{urlencode(params)}"

    doc = html.fromstring(text)
    cells = [
        normalize_space(cell.text_content())
        for cell in doc.xpath("//td[contains(concat(' ', normalize-space(@class), ' '), ' renglonPar ') or contains(concat(' ', normalize-space(@class), ' '), ' renglonNon ')]")
    ]
    tokens = [cell for cell in cells if is_date_text(cell) or is_rate_text(cell)]
    date_tokens: list[str] = []
    for token in tokens:
        if not is_date_text(token):
            break
        date_tokens.append(token)

    if not date_tokens:
        raise ValueError("Could not parse Banxico date rows from the official table.")

    value_tokens = tokens[len(date_tokens) :]
    expected_values = len(date_tokens) * 3
    if len(value_tokens) < expected_values:
        raise ValueError(
            f"Expected at least {expected_values} Banxico values for {len(date_tokens)} dates; "
            f"found {len(value_tokens)}."
        )

    n = len(date_tokens)
    determination_tokens = value_tokens[:n]
    publication_tokens = value_tokens[n : n * 2]
    obligation_tokens = value_tokens[n * 2 : n * 3]

    raw_rows = []
    for index, token in enumerate(date_tokens):
        raw_rows.append(
            {
                "date": parse_banxico_date(token),
                "determination": parse_rate(determination_tokens[index]),
                "publication_dof": parse_rate(publication_tokens[index]),
                "obligations": parse_rate(obligation_tokens[index]),
            }
        )

    rows: list[BanxicoRow] = []
    last_fix: Decimal | None = None
    last_fix_date: date | None = None
    for raw in sorted(raw_rows, key=lambda item: item["date"]):
        determination = raw["determination"]
        if determination is not None:
            last_fix = determination
            last_fix_date = raw["date"]
        if last_fix is None or last_fix_date is None:
            continue
        rows.append(
            BanxicoRow(
                date=raw["date"],
                determination=determination,
                publication_dof=raw["publication_dof"],
                obligations=raw["obligations"],
                effective_fix=last_fix,
                effective_source_date=last_fix_date,
            )
        )

    return rows, source_url


def get_existing_bc_rates(
    *,
    client: BusinessCentralClient,
    company_url: str,
    currency_code: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    escaped_currency = currency_code.replace("'", "''")
    return client._request(
        "GET",
        f"{company_url}/currencyExchangeRates",
        params={
            "$filter": (
                f"currencyCode eq '{escaped_currency}' "
                f"and startingDate ge {start_date.isoformat()} "
                f"and startingDate le {end_date.isoformat()}"
            ),
            "$orderby": "startingDate asc",
            "$top": 500,
        },
    ).get("value", [])


def apply_missing_rows(
    *,
    settings: Settings,
    client: BusinessCentralClient,
    company_name: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    url = (
        f"https://api.businesscentral.dynamics.com/v2.0/{settings.environment}"
        f"/ODataV4/Company('{company_name}')/MX_ratesdivisas"
    )
    headers = {**client.session.headers, **client._headers()}
    inserted = []
    errors = []

    for row in rows:
        payload = {
            "Currency_Code": row["Currency_Code"],
            "Starting_Date": row["Starting_Date"],
            "Relational_Currency_Code": row["Relational_Currency_Code"],
            "Exchange_Rate_Amount": float(row["Exchange_Rate_Amount"]),
            "Relational_Exch_Rate_Amount": float(row["Relational_Exch_Rate_Amount"]),
            "Adjustment_Exch_Rate_Amount": float(row["Adjustment_Exch_Rate_Amount"]),
            "Relational_Adjmt_Exch_Rate_Amt": float(row["Relational_Adjmt_Exch_Rate_Amt"]),
            "Fix_Exchange_Rate_Amount": row["Fix_Exchange_Rate_Amount"],
        }
        response = requests.post(url, headers=headers, json=payload, timeout=settings.timeout_seconds)
        if 200 <= response.status_code < 300:
            inserted.append(row["Starting_Date"])
        else:
            errors.append(
                {
                    "starting_date": row["Starting_Date"],
                    "status_code": response.status_code,
                    "body": response.text[:2000],
                }
            )
            break

    return {"inserted": inserted, "errors": errors}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_banxico_date(value: str) -> date:
    day, month, year = value.split("/")
    return date(int(year), int(month), int(day))


def parse_rate(value: str) -> Decimal | None:
    cleaned = value.strip()
    if cleaned == "N/E" or not cleaned:
        return None
    return Decimal(cleaned.replace(",", ""))


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value, "f")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_date_text(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2}/\d{2}/\d{4}", value))


def is_rate_text(value: str) -> bool:
    return value == "N/E" or bool(re.fullmatch(r"\d+(?:,\d{3})*(?:\.\d+)?", value))


if __name__ == "__main__":
    sys.exit(main())
