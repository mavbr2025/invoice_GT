from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business_central_client.auth import TokenProvider
from business_central_client.config import Settings


COMPLETED_STATUSES = {"completed", "installed", "succeeded", "success"}
FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Upload and deploy a Business Central extension through the supported "
            "Automation API, then verify its terminal deployment status."
        )
    )
    parser.add_argument("--app", type=Path, help="Compiled .app package.")
    parser.add_argument("--name", required=True, help="Expected extension name.")
    parser.add_argument("--version", required=True, help="Expected extension version.")
    parser.add_argument("--market", default="GT", help="Configured market/company key.")
    parser.add_argument("--env-file", type=Path, help="Optional dotenv file.")
    parser.add_argument("--timeout", type=int, default=300, help="Poll timeout in seconds.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Read and verify the requested deployed version without uploading a package.",
    )
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file, override=True)

    app_path = args.app.expanduser().resolve() if args.app else None
    if not args.verify_only:
        if app_path is None:
            raise SystemExit("--app is required unless --verify-only is used.")
        if not app_path.is_file():
            raise SystemExit(f"Extension package does not exist: {app_path}")

    settings = Settings.from_env()
    market = settings.get_market(args.market)
    company_id = market.company_id if market else settings.company_id
    if not company_id:
        raise SystemExit(f"No Business Central company is configured for market {args.market}.")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {TokenProvider(settings).get_token()}",
            "Accept": "application/json",
            "User-Agent": settings.user_agent,
        }
    )
    base_url = (
        "https://api.businesscentral.dynamics.com/"
        f"v2.0/{settings.environment}/api/microsoft/automation/v2.0/"
        f"companies({company_id})"
    )

    upload_id = ""
    if not args.verify_only:
        upload = _request_json(
            session,
            "POST",
            f"{base_url}/extensionUpload",
            timeout=settings.timeout_seconds,
            json={"schedule": "Current version", "schemaSyncMode": "Add"},
        )
        upload_id = str(upload.get("systemId") or upload.get("id") or "").strip()
        if not upload_id:
            raise RuntimeError(f"Business Central did not return an extension upload ID: {upload}")

        content_response = session.patch(
            f"{base_url}/extensionUpload({upload_id})/extensionContent",
            headers={"Content-Type": "application/octet-stream", "If-Match": "*"},
            data=app_path.read_bytes(),
            timeout=max(settings.timeout_seconds, 120),
        )
        _raise_with_detail(content_response)

        upload_response = session.post(
            f"{base_url}/extensionUpload({upload_id})/Microsoft.NAV.upload",
            headers={"Content-Type": "application/json"},
            json={},
            timeout=max(settings.timeout_seconds, 120),
        )
        _raise_with_detail(upload_response)

    deployment = _wait_for_deployment(
        session,
        base_url=base_url,
        expected_name=args.name,
        expected_version=args.version,
        timeout_seconds=args.timeout,
        request_timeout=settings.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "status": "deployment_verified" if args.verify_only else "deployed_and_verified",
                "environment": settings.environment,
                "company_id": company_id,
                "extension": {
                    "name": deployment.get("name"),
                    "version": deployment.get("appVersion"),
                    "deploymentStatus": deployment.get("status"),
                    "startedOn": deployment.get("startedOn"),
                },
                "upload_id": upload_id,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def _wait_for_deployment(
    session: requests.Session,
    *,
    base_url: str,
    expected_name: str,
    expected_version: str,
    timeout_seconds: int,
    request_timeout: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_match: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = session.get(
            f"{base_url}/extensionDeploymentStatus",
            timeout=request_timeout,
        )
        _raise_with_detail(response)
        rows = response.json().get("value", [])
        matches = [
            row
            for row in rows
            if str(row.get("name") or "").strip() == expected_name
            and str(row.get("appVersion") or "").strip() == expected_version
        ]
        if matches:
            last_match = max(matches, key=lambda row: str(row.get("startedOn") or ""))
            status = str(last_match.get("status") or "").strip().lower()
            if status in COMPLETED_STATUSES:
                return last_match
            if status in FAILED_STATUSES:
                raise RuntimeError(
                    "Business Central extension deployment failed: "
                    + json.dumps(last_match, sort_keys=True, default=str)
                )
        time.sleep(3)

    raise TimeoutError(
        "Timed out waiting for Business Central extension deployment. "
        f"Last matching status: {json.dumps(last_match, sort_keys=True, default=str)}"
    )


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int,
    **kwargs: Any,
) -> dict[str, Any]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    _raise_with_detail(response)
    return response.json()


def _raise_with_detail(response: requests.Response) -> None:
    if response.ok:
        return
    detail = response.text.strip()
    raise requests.HTTPError(
        f"{response.status_code} {response.reason} for {response.request.method} "
        f"{response.url}. Business Central detail: {detail}",
        response=response,
    )


if __name__ == "__main__":
    main()
