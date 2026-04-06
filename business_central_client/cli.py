from __future__ import annotations

import argparse
import json

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings
from business_central_client.pricing import PricingService


def add_market_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--market",
        help="Market/company profile to use, for example MX or GT",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Business Central connector CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("environments", help="List Business Central environments")
    subparsers.add_parser("companies", help="List companies in the configured environment")

    items_parser = subparsers.add_parser("items", help="List items")
    add_market_argument(items_parser)
    items_parser.add_argument("--top", type=int, default=10)

    customers_parser = subparsers.add_parser("customers", help="List customers")
    add_market_argument(customers_parser)
    customers_parser.add_argument("--top", type=int, default=10)

    price_parser = subparsers.add_parser(
        "price-preview",
        help="Fetch a pricing-oriented preview for a customer and item",
    )
    add_market_argument(price_parser)
    price_parser.add_argument("--customer-number", required=True)
    price_parser.add_argument("--item-number", required=True)
    price_parser.add_argument("--quantity", type=float, default=1)
    price_parser.add_argument(
        "--currency-code",
        help="Invoice/pricing currency, for example MXN, GTQ, or USD",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.from_env()
    client = BusinessCentralClient(settings)

    if args.command == "environments":
        _print(client.get_environments())
        return

    if args.command == "companies":
        _print(client.get_companies())
        return

    if args.command == "items":
        _print(client.get_entities("items", top=args.top, market=args.market))
        return

    if args.command == "customers":
        _print(client.get_entities("customers", top=args.top, market=args.market))
        return

    if args.command == "price-preview":
        service = PricingService(client)
        _print(
            service.preview_price(
                market=args.market,
                customer_number=args.customer_number,
                item_number=args.item_number,
                quantity=args.quantity,
                currency_code=args.currency_code,
            )
        )
        return

    parser.error(f"Unsupported command: {args.command}")


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
