from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings


BANGUAT_SOAP_URL = "https://www.banguat.gob.gt/variables/ws/tipocambio.asmx"
BANGUAT_NAMESPACE = "http://www.banguat.gob.gt/variables/ws/"


@dataclass(frozen=True)
class BanguatRow:
    date: date
    currency_id: int
    buy_rate: Decimal
    sell_rate: Decimal

    @property
    def rate(self) -> Decimal:
        if self.buy_rate != self.sell_rate:
            raise ValueError(
                f"Banguat buy/sell rates differ for {self.date.isoformat()}: "
                f"{self.buy_rate} vs {self.sell_rate}"
            )
        return self.sell_rate


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or apply a Business Central USD/GTQ exchange-rate backfill "
            "from Banco de Guatemala's official TipoCambioRango web service."
        )
    )
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD.")
    parser.add_argument("--market", default="GT", help="Business Central market profile.")
    parser.add_argument("--currency", default="USD", help="Business Central currency code.")
    parser.add_argument(
        "--odata-page",
        default=None,
        help="Published OData page name. Defaults to <MARKET>_ratesdivisas.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for CSV and report files.")
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="Include Saturday/Sunday rows. By default, this matches the GT weekday-only job.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert missing rows and update mismatched rows in Business Central.",
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
    company = client.get_company_metadata(market=market_key)
    if not company:
        raise ValueError(f"Could not resolve Business Central company for market {market_key}.")

    company_name = company["name"]
    odata_page = args.odata_page or f"{market_key}_ratesdivisas"
    company_url = f"{settings.api_base_url}/companies({market.company_id})"

    banguat_rows, source_url = fetch_banguat_rows(start_date, end_date)
    window_rows = [
        row
        for row in banguat_rows
        if args.include_weekends or row.date.weekday() < 5
    ]

    existing_rows = get_existing_bc_rates(
        client=client,
        company_url=company_url,
        currency_code=currency_code,
        start_date=start_date,
        end_date=end_date,
    )
    existing_by_date = {
        existing_starting_date(row): row
        for row in existing_rows
        if existing_starting_date(row)
    }

    prepared_rows = []
    for row in window_rows:
        date_key = row.date.isoformat()
        existing = existing_by_date.get(date_key)
        expected_rate = decimal_text(row.rate)
        existing_rate = decimal_text(decimal_from_existing(existing, "Relational_Exch_Rate_Amount"))
        action = "insert"
        if existing:
            action = "skip_existing" if existing_rate == expected_rate else "update_existing"

        prepared_rows.append(
            {
                "Currency_Code": currency_code,
                "Starting_Date": date_key,
                "Relational_Currency_Code": "",
                "Exchange_Rate_Amount": "1",
                "Relational_Exch_Rate_Amount": expected_rate,
                "Adjustment_Exch_Rate_Amount": "1",
                "Relational_Adjmt_Exch_Rate_Amt": expected_rate,
                "Fix_Exchange_Rate_Amount": "Currency",
                "Action": action,
                "Existing_BC_Rate": existing_rate,
                "Banguat_Moneda": str(row.currency_id),
                "Banguat_Compra": decimal_text(row.buy_rate),
                "Banguat_Venta": decimal_text(row.sell_rate),
                "Source_URL": source_url,
            }
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"bc_banguat_backfill_{start_date.isoformat()}_{end_date.isoformat()}"
    csv_path = output_dir / f"{stem}_import.csv"
    report_path = output_dir / f"{stem}_validation.json"

    write_csv(csv_path, prepared_rows)

    apply_result = None
    if args.apply:
        apply_result = apply_rows(
            settings=settings,
            client=client,
            company_name=company_name,
            odata_page=odata_page,
            rows=[
                row
                for row in prepared_rows
                if row["Action"] in {"insert", "update_existing"}
            ],
        )

    report = {
        "market": market_key,
        "company_id": market.company_id,
        "company_name": company_name,
        "currency": currency_code,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "include_weekends": args.include_weekends,
        "source_url": source_url,
        "csv_path": str(csv_path.resolve()),
        "existing_count": len(existing_rows),
        "source_count": len(banguat_rows),
        "prepared_count": len(prepared_rows),
        "insert_count": sum(1 for row in prepared_rows if row["Action"] == "insert"),
        "update_existing_count": sum(1 for row in prepared_rows if row["Action"] == "update_existing"),
        "skip_existing_count": sum(1 for row in prepared_rows if row["Action"] == "skip_existing"),
        "weekend_filtered_count": len(banguat_rows) - len(window_rows),
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
                "update_existing_count": report["update_existing_count"],
                "skip_existing_count": report["skip_existing_count"],
                "weekend_filtered_count": report["weekend_filtered_count"],
                "applied": bool(args.apply),
                "apply_result": apply_result,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fetch_banguat_rows(start_date: date, end_date: date) -> tuple[list[BanguatRow], str]:
    start_text = start_date.strftime("%d/%m/%Y")
    end_text = end_date.strftime("%d/%m/%Y")
    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <TipoCambioRango xmlns="{BANGUAT_NAMESPACE}">
      <fechainit>{start_text}</fechainit>
      <fechafin>{end_text}</fechafin>
    </TipoCambioRango>
  </soap:Body>
</soap:Envelope>"""
    response = requests.post(
        BANGUAT_SOAP_URL,
        data=soap.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{BANGUAT_NAMESPACE}TipoCambioRango"',
            "User-Agent": "MTMLogixBanguatBackfill/1.0",
        },
        timeout=30,
    )
    response.raise_for_status()

    root = etree.fromstring(response.content)
    rows: list[BanguatRow] = []
    for node in root.xpath('//*[local-name()="Var"]'):
        fecha = node.findtext("{*}fecha")
        venta = node.findtext("{*}venta")
        compra = node.findtext("{*}compra")
        moneda = node.findtext("{*}moneda")
        if not fecha or not venta or not compra or not moneda:
            continue
        day, month, year = fecha.split("/")
        rows.append(
            BanguatRow(
                date=date(int(year), int(month), int(day)),
                currency_id=int(moneda),
                buy_rate=Decimal(compra),
                sell_rate=Decimal(venta),
            )
        )

    if not rows:
        raise ValueError("Could not parse Banguat rows from the TipoCambioRango response.")

    return sorted(rows, key=lambda row: row.date), f"{BANGUAT_SOAP_URL}?op=TipoCambioRango"


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


def apply_rows(
    *,
    settings: Settings,
    client: BusinessCentralClient,
    company_name: str,
    odata_page: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    base_url = (
        f"https://api.businesscentral.dynamics.com/v2.0/{settings.environment}"
        f"/ODataV4/Company('{company_name}')/{odata_page}"
    )
    headers = {**client.session.headers, **client._headers()}
    inserted = []
    updated = []
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
        if row["Action"] == "insert":
            response = requests.post(
                base_url,
                headers=headers,
                json=payload,
                timeout=settings.timeout_seconds,
            )
            success_dates = inserted
        else:
            response = requests.patch(
                f"{base_url}({odata_key(row['Currency_Code'], row['Starting_Date'])})",
                headers={**headers, "If-Match": "*"},
                json=payload,
                timeout=settings.timeout_seconds,
            )
            success_dates = updated

        if 200 <= response.status_code < 300:
            success_dates.append(row["Starting_Date"])
        else:
            errors.append(
                {
                    "starting_date": row["Starting_Date"],
                    "action": row["Action"],
                    "status_code": response.status_code,
                    "body": response.text[:2000],
                }
            )
            break

    return {"inserted": inserted, "updated": updated, "errors": errors}


def odata_key(currency_code: str, starting_date: str) -> str:
    escaped_currency = currency_code.replace("'", "''")
    return f"Currency_Code='{escaped_currency}',Starting_Date={starting_date}"


def decimal_from_existing(row: dict[str, Any] | None, key: str) -> Decimal | None:
    if not row:
        return None
    value = row.get(key)
    if value is None:
        value = row.get("relationalExchangeRateAmount")
    if value is None:
        return None
    return Decimal(str(value))


def existing_starting_date(row: dict[str, Any]) -> str | None:
    value = row.get("Starting_Date") or row.get("startingDate")
    return str(value) if value else None


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
