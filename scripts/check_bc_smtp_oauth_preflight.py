#!/usr/bin/env python3
"""Validate Exchange Online SMTP app authentication without sending email."""

from __future__ import annotations

import argparse
import base64
import json
import smtplib
import ssl
from pathlib import Path

import requests


TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
TOKEN_SCOPE = "https://outlook.office365.com/.default"
SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587


def _decode_claims(access_token: str) -> dict[str, object]:
    payload = access_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire an app-only SMTP token and authenticate without sending mail."
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret-file", type=Path, required=True)
    parser.add_argument("--mailbox", required=True)
    args = parser.parse_args()

    client_secret = args.client_secret_file.read_text(encoding="utf-8").strip()
    if not client_secret:
        raise SystemExit("Client secret file is empty.")

    token_response = requests.post(
        TOKEN_URL.format(tenant_id=args.tenant_id),
        data={
            "client_id": args.client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": TOKEN_SCOPE,
        },
        timeout=30,
    )
    if not token_response.ok:
        detail = token_response.json()
        print(
            json.dumps(
                {
                    "stage": "token",
                    "status": "failed",
                    "http_status": token_response.status_code,
                    "error": detail.get("error", ""),
                    "error_description": detail.get("error_description", ""),
                },
                indent=2,
            )
        )
        raise SystemExit(1)

    access_token = token_response.json()["access_token"]
    claims = _decode_claims(access_token)
    token_evidence = {
        "aud": claims.get("aud"),
        "appid": claims.get("appid"),
        "roles": claims.get("roles", []),
        "tid": claims.get("tid"),
    }

    if token_evidence["roles"]:
        print(
            json.dumps(
                {
                    "stage": "token_claims",
                    "status": "failed",
                    "message": (
                        "This deployment uses Exchange Application RBAC. The Entra "
                        "application token must not contain application-role claims, "
                        "because they trigger the legacy mailbox-permission path."
                    ),
                    "token": token_evidence,
                    "sent_email": False,
                },
                indent=2,
            )
        )
        raise SystemExit(1)

    auth_text = f"user={args.mailbox}\x01auth=Bearer {access_token}\x01\x01"
    auth_b64 = base64.b64encode(auth_text.encode("utf-8")).decode("ascii")

    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    try:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        code, response = smtp.docmd("AUTH", f"XOAUTH2 {auth_b64}")
        result = {
            "stage": "smtp_auth",
            "status": "succeeded" if code == 235 else "failed",
            "smtp_code": code,
            "smtp_response": response.decode("utf-8", errors="replace"),
            "token": token_evidence,
            "sent_email": False,
        }
        print(json.dumps(result, indent=2))
        if code != 235:
            raise SystemExit(1)
    finally:
        try:
            smtp.quit()
        except smtplib.SMTPException:
            smtp.close()


if __name__ == "__main__":
    main()
