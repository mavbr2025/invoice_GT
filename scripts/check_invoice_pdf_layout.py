from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Check an invoice PDF against a layout config.")
    parser.add_argument("pdf", type=Path, help="PDF file to inspect.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/invoice_layouts/gt.toml"),
        help="Invoice layout TOML config.",
    )
    parser.add_argument("--customer-number", default="C00081", help="BC customer number in config.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args()

    config = load_config(args.config)
    result = check_pdf(args.pdf, config=config, customer_number=args.customer_number)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_human(result)

    raise SystemExit(0 if result["ok"] else 1)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def check_pdf(pdf_path: Path, *, config: dict[str, Any], customer_number: str) -> dict[str, Any]:
    text = extract_pdf_text(pdf_path)
    layout = config["layout"]
    company = config["company"]
    customer = (config.get("customers") or {}).get(customer_number)
    if not customer:
        raise SystemExit(f"Customer {customer_number} is not configured.")

    checks: list[dict[str, Any]] = []
    lower_text = text.lower()

    for required in layout.get("required_text", []):
        checks.append(
            {
                "name": f"required text: {required}",
                "ok": required.lower() in lower_text,
                "expected": "present",
            }
        )

    for forbidden in layout.get("forbidden_text", []):
        checks.append(
            {
                "name": f"forbidden text: {forbidden}",
                "ok": forbidden.lower() not in lower_text,
                "expected": "absent",
            }
        )

    issuer_nit = str(company.get("issuer_nit") or "").strip()
    if layout.get("issuer_nit_required") and issuer_nit:
        checks.append(
            regex_check(
                "issuer NIT is labeled",
                text,
                rf"\bNIT\s*:?\s*{re.escape(issuer_nit)}\b",
            )
        )

    customer_nit = str(customer.get("nit") or "").strip()
    if layout.get("customer_nit_required") and customer_nit:
        checks.append(
            regex_check(
                "customer NIT value is present",
                text,
                rf"\b{re.escape(customer_nit)}\b",
            )
        )
        if layout.get("customer_nit_label_required"):
            checks.append(
                regex_check(
                    "customer NIT is labeled",
                    text,
                    rf"\bNIT\s*:?\s*{re.escape(customer_nit)}\b",
                )
            )

    ok = all(check["ok"] for check in checks)
    return {
        "ok": ok,
        "pdf": str(pdf_path),
        "config": layout.get("name"),
        "customer_number": customer_number,
        "checks": checks,
    }


def regex_check(name: str, text: str, pattern: str) -> dict[str, Any]:
    return {
        "name": name,
        "ok": re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None,
        "expected": pattern,
    }


def extract_pdf_text(pdf_path: Path) -> str:
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    if shutil.which("pdftotext"):
        completed = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit("Install poppler pdftotext or pypdf to inspect PDF text.") from exc

    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def print_human(result: dict[str, Any]) -> None:
    status = "PASS" if result["ok"] else "FAIL"
    print(f"{status} {result['pdf']}")
    for check in result["checks"]:
        marker = "ok" if check["ok"] else "fail"
        print(f"- {marker}: {check['name']}")


if __name__ == "__main__":
    main()
