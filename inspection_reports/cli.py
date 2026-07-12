from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings

from inspection_reports.config import GraphSettings, InspectionReportSettings
from inspection_reports.sharepoint import SharePointGraphClient
from inspection_reports.workflow import InspectionReportWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Truck inspection report automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser("one", help="Generate one inspection report from one ClickUp task")
    one.add_argument("--task-id", required=True)
    one.add_argument("--dry-run", action="store_true")

    batch = subparsers.add_parser("batch", help="Generate inspection reports for a ClickUp list")
    batch.add_argument("--dry-run", action="store_true")
    batch.add_argument("--max-tasks", type=int)
    batch.add_argument("--pages", type=int, default=1)

    complete = subparsers.add_parser(
        "complete-list",
        help="Ensure reports are linked for a ClickUp list, then set completed task status.",
    )
    complete.add_argument("--target-status", default="PASSED")
    complete.add_argument("--max-tasks", type=int)
    complete.add_argument("--pages", type=int)

    complete_one = subparsers.add_parser(
        "complete-one",
        help="Ensure one report is linked, then set completed task status.",
    )
    complete_one.add_argument("--task-id", required=True)
    complete_one.add_argument("--target-status", default="PASSED")

    find_task = subparsers.add_parser("find-task", help="Find ClickUp tasks in the report list")
    find_task.add_argument("--query", required=True)
    find_task.add_argument("--pages", type=int)
    find_task.add_argument("--include-closed", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = InspectionReportSettings.from_env()
    clickup = ClickUpClient(ClickUpSettings.from_env())
    sharepoint = SharePointGraphClient(GraphSettings.from_env())
    workflow = InspectionReportWorkflow(
        settings=settings,
        clickup_client=clickup,
        sharepoint_client=sharepoint,
    )

    if args.command == "one":
        _print(asdict(workflow.run_task(args.task_id, dry_run=args.dry_run)))
        return

    if args.command == "batch":
        task_ids = workflow.list_task_ids(max_tasks=args.max_tasks, pages=args.pages)
        results = [
            asdict(workflow.run_task(task_id, dry_run=args.dry_run))
            for task_id in task_ids
        ]
        _print({"count": len(results), "results": results})
        return

    if args.command == "complete-list":
        results = workflow.complete_missing_reports_for_list(
            target_status=args.target_status,
            max_tasks=args.max_tasks,
            pages=args.pages,
        )
        _print({"count": len(results), "results": [asdict(result) for result in results]})
        return

    if args.command == "complete-one":
        task = clickup.get_task(
            args.task_id,
            custom_task_ids=settings.custom_task_ids,
            team_id=settings.clickup_team_id,
            include_subtasks=False,
        )
        result = workflow.complete_missing_report_for_task(
            task,
            target_status=args.target_status,
        )
        _print(asdict(result))
        return

    if args.command == "find-task":
        _print(
            {
                "query": args.query,
                "matches": workflow.find_tasks_by_text(
                    args.query,
                    pages=args.pages,
                    include_closed=args.include_closed,
                ),
            }
        )
        return

    parser.error(f"Unsupported command: {args.command}")


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
