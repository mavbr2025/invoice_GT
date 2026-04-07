from __future__ import annotations

import argparse
import json

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings as BusinessCentralSettings
from clickup_integration.auth import (
    build_authorization_url,
    exchange_code_for_token,
    format_env_update,
    wait_for_oauth_callback,
)
from clickup_integration.bc_sync import (
    apply_clickup_to_bc_customer_sync,
    prepare_clickup_to_bc_customer_sync,
)
from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings
from clickup_integration.create_preview import prepare_clickup_bc_customer_create_preview
from clickup_integration.create_preview import (
    apply_clickup_bc_customer_create,
    prepare_clickup_bc_created_customer_writeback,
)
from clickup_integration.matcher import match_clickup_customer_to_bc
from clickup_integration.mapping import summarize_task_for_customer_mapping
from clickup_integration.writeback import prepare_clickup_bc_writeback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ClickUp integration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_url_parser = subparsers.add_parser(
        "auth-url",
        help="Generate the ClickUp OAuth authorization URL",
    )
    auth_url_parser.add_argument("--state")

    exchange_parser = subparsers.add_parser(
        "exchange-code",
        help="Exchange a ClickUp OAuth authorization code for an access token",
    )
    exchange_parser.add_argument("--code", required=True)

    listen_parser = subparsers.add_parser(
        "oauth-listen",
        help="Wait for a local ClickUp OAuth callback and exchange the code",
    )
    listen_parser.add_argument("--state")

    subparsers.add_parser(
        "workspaces",
        help="List the ClickUp workspaces authorized for the current access token",
    )

    task_parser = subparsers.add_parser(
        "task",
        help="Fetch a ClickUp task for mapping review",
    )
    task_parser.add_argument("--task-id", required=True)
    task_parser.add_argument("--custom-task-ids", action="store_true")
    task_parser.add_argument("--team-id")
    task_parser.add_argument("--include-subtasks", action="store_true")

    match_parser = subparsers.add_parser(
        "match-customer",
        help="Fetch a ClickUp customer task and search Business Central for candidate matches",
    )
    match_parser.add_argument("--task-id", required=True)
    match_parser.add_argument("--custom-task-ids", action="store_true")
    match_parser.add_argument("--team-id")

    create_preview_parser = subparsers.add_parser(
        "preview-create-customer",
        help="Build a dry-run BC customer creation preview from a ClickUp current customer task",
    )
    create_preview_parser.add_argument("--task-id", required=True)
    create_preview_parser.add_argument("--custom-task-ids", action="store_true")
    create_preview_parser.add_argument("--team-id")

    create_apply_parser = subparsers.add_parser(
        "create-customer-in-bc",
        help="Create a new BC customer from a ClickUp current customer task and write the BC data back to ClickUp",
    )
    create_apply_parser.add_argument("--task-id", required=True)
    create_apply_parser.add_argument("--custom-task-ids", action="store_true")
    create_apply_parser.add_argument("--team-id")
    create_apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the BC creation and ClickUp write-back payloads without sending them",
    )

    writeback_parser = subparsers.add_parser(
        "writeback-customer-match",
        help="Write the best BC match back into ClickUp custom fields for a current customer task",
    )
    writeback_parser.add_argument("--task-id", required=True)
    writeback_parser.add_argument("--custom-task-ids", action="store_true")
    writeback_parser.add_argument("--team-id")
    writeback_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the ClickUp field updates without sending them",
    )

    sync_to_bc_parser = subparsers.add_parser(
        "sync-customer-to-bc",
        help="Push approved shared customer fields from ClickUp into the matched BC customer",
    )
    sync_to_bc_parser.add_argument("--task-id", required=True)
    sync_to_bc_parser.add_argument("--custom-task-ids", action="store_true")
    sync_to_bc_parser.add_argument("--team-id")
    sync_to_bc_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the BC patch without sending it",
    )

    fields_parser = subparsers.add_parser(
        "list-custom-fields",
        help="Fetch the custom fields available on a ClickUp list",
    )
    fields_parser.add_argument("--list-id")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    require_oauth = args.command in {"auth-url", "exchange-code", "oauth-listen"}
    settings = ClickUpSettings.from_env(require_oauth=require_oauth)

    if args.command == "auth-url":
        print(build_authorization_url(settings, state=args.state))
        return

    if args.command == "exchange-code":
        token = exchange_code_for_token(settings, code=args.code)
        _print(
            {
                "access_token": token.access_token,
                "token_type": token.token_type,
                "env_update": format_env_update(token),
            }
        )
        return

    if args.command == "oauth-listen":
        print("Open this URL in your browser:")
        print(build_authorization_url(settings, state=args.state))
        callback = wait_for_oauth_callback(settings)
        token = exchange_code_for_token(settings, code=callback["code"])
        payload = {
            "callback": callback,
            "access_token": token.access_token,
            "token_type": token.token_type,
            "env_update": format_env_update(token),
        }
        _print(payload)
        return

    client = ClickUpClient(settings)

    if args.command == "workspaces":
        _print(client.get_authorized_workspaces())
        return

    if args.command == "task":
        task = client.get_task(
            args.task_id,
            custom_task_ids=args.custom_task_ids,
            team_id=args.team_id,
            include_subtasks=args.include_subtasks,
        )
        _print(summarize_task_for_customer_mapping(task))
        return

    if args.command == "match-customer":
        task = client.get_task(
            args.task_id,
            custom_task_ids=args.custom_task_ids,
            team_id=args.team_id,
            include_subtasks=False,
        )
        summary = summarize_task_for_customer_mapping(task)
        bc_settings = BusinessCentralSettings.from_env()
        bc_client = BusinessCentralClient(bc_settings)
        _print(match_clickup_customer_to_bc(clickup_summary=summary, bc_client=bc_client))
        return

    if args.command == "preview-create-customer":
        task = client.get_task(
            args.task_id,
            custom_task_ids=args.custom_task_ids,
            team_id=args.team_id,
            include_subtasks=False,
        )
        summary = summarize_task_for_customer_mapping(task)
        bc_settings = BusinessCentralSettings.from_env()
        bc_client = BusinessCentralClient(bc_settings)
        current_match = match_clickup_customer_to_bc(clickup_summary=summary, bc_client=bc_client)
        _print(
            prepare_clickup_bc_customer_create_preview(
                clickup_summary=summary,
                current_match_result=current_match,
                bc_client=bc_client,
            )
        )
        return

    if args.command == "create-customer-in-bc":
        task = client.get_task(
            args.task_id,
            custom_task_ids=args.custom_task_ids,
            team_id=args.team_id,
            include_subtasks=False,
        )
        summary = summarize_task_for_customer_mapping(task)
        bc_settings = BusinessCentralSettings.from_env()
        bc_client = BusinessCentralClient(bc_settings)
        current_match = match_clickup_customer_to_bc(clickup_summary=summary, bc_client=bc_client)

        if args.dry_run:
            preview = prepare_clickup_bc_customer_create_preview(
                clickup_summary=summary,
                current_match_result=current_match,
                bc_client=bc_client,
            )
            _print({"mode": "dry_run", "preview": preview, "match_result": current_match})
            return

        result = apply_clickup_bc_customer_create(
            clickup_summary=summary,
            current_match_result=current_match,
            bc_client=bc_client,
        )
        if result.get("status") != "applied":
            _print({"mode": "blocked", "result": result})
            return

        payload = result["writeback"]
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["number"],
            payload["bc_customer_number"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["id"],
            payload["bc_customer_id"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["link"],
            payload["bc_customer_link"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["legal_name"],
            payload["bc_legal_name"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["status"],
            payload["bc_match_status"],
        )
        _print({"mode": "applied", "result": result})
        return

    if args.command == "writeback-customer-match":
        task = client.get_task(
            args.task_id,
            custom_task_ids=args.custom_task_ids,
            team_id=args.team_id,
            include_subtasks=False,
        )
        summary = summarize_task_for_customer_mapping(task)
        bc_settings = BusinessCentralSettings.from_env()
        bc_client = BusinessCentralClient(bc_settings)
        match_result = match_clickup_customer_to_bc(clickup_summary=summary, bc_client=bc_client)
        payload = prepare_clickup_bc_writeback(
            clickup_summary=summary,
            match_result=match_result,
            bc_client=bc_client,
        )

        if args.dry_run:
            _print({"mode": "dry_run", "writeback": payload, "match_result": match_result})
            return

        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["number"],
            payload["bc_customer_number"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["id"],
            payload["bc_customer_id"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["link"],
            payload["bc_customer_link"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["legal_name"],
            payload["bc_legal_name"],
        )
        client.set_task_custom_field_value(
            payload["task_id"],
            payload["field_ids"]["status"],
            payload["bc_match_status"],
        )
        _print({"mode": "applied", "writeback": payload, "match_result": match_result})
        return

    if args.command == "sync-customer-to-bc":
        task = client.get_task(
            args.task_id,
            custom_task_ids=args.custom_task_ids,
            team_id=args.team_id,
            include_subtasks=False,
        )
        summary = summarize_task_for_customer_mapping(task)
        bc_settings = BusinessCentralSettings.from_env()
        bc_client = BusinessCentralClient(bc_settings)

        if args.dry_run:
            _print(
                {
                    "mode": "dry_run",
                    "sync": prepare_clickup_to_bc_customer_sync(
                        clickup_summary=summary,
                        bc_client=bc_client,
                    ),
                }
            )
            return

        _print(
            {
                "mode": "applied",
                "sync": apply_clickup_to_bc_customer_sync(
                    clickup_summary=summary,
                    bc_client=bc_client,
                ),
            }
        )
        return

    if args.command == "list-custom-fields":
        list_id = args.list_id or settings.default_customer_list_id
        if not list_id:
            parser.error(
                "--list-id is required unless CLICKUP_DEFAULT_CUSTOMER_LIST_ID is set."
            )
        _print(client.get_list_custom_fields(list_id))
        return

    parser.error(f"Unsupported command: {args.command}")


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
