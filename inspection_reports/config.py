from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


DEFAULT_REPORT_FIELD_NAMES = (
    "Brand",
    "Model",
    "Color",
    "Motor",
    "Destination Country",
    "Inspection Date",
    "VIN Picture",
    "Nameplate",
    "360 Overview Result",
    "360 Overview Comment",
    "Corrosion Result",
    "Accessories Result",
    "Door Result",
    "Floor Result",
    "Emergency exits Result",
    "Window Result",
    "Seat Appearance / Fixation Result",
    "Glass Result",
    "Tire and Wheel Result",
    "Exterior Lights Result",
    "Painting Result",
    "Mirrors Result",
    "VIN number",
    "Inspection Result Summary",
    "Line",
    "Branding Result",
    "Car keys in glove box",
    "OneDrive Pictures",
    "Number of seats",
    "Inspector Name",
    "Rate Type",
    "Previo en origen (USD)",
    "Detención al cliente (DB)",
    "Proforma Invoice",
    "Type of cargo",
    "Origin Inspection Report",
    "Proforma",
    "Excel report",
    "Cargo Inspection Invoice",
    "Inspection Final Report URL",
    "Magna Shipments",
)

DEFAULT_IMAGE_MATCH_FIELD_NAMES = (
    "VIN number",
)

DEFAULT_SHAREPOINT_FOLDER_FIELD_NAMES = (
    "OneDrive Pictures",
)
DEFAULT_PICTURE_FOLDER_FIELD_IDS = (
    "1bfac08a-6df3-4ea4-a581-5f4b41a97bb1",
)

DEFAULT_REPORT_LINK_FIELD_NAMES = (
    "Inspection Report Link",
    "Inspection Report",
    "Physical Inspection Report",
)
DEFAULT_REPORT_ATTACHMENT_FIELD_IDS = (
    "3a454367-98b8-4a8f-96d5-6f8872b1ada1",
)
DEFAULT_REPORT_ATTACHMENT_FIELD_NAMES = (
    "Origin Inspection Report",
)
DEFAULT_COMMENT_FIELD_NAMES = (
    "Inspection AI Exec Summary",
)

DEFAULT_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_ALLOWED_STATUSES = ("passed",)
DEFAULT_SECTION_FOLDER_PREFIXES = (
    "Car Information=01-Car Information",
    "Car Information=1.Car Information",
    "General / 360° Overview=02-General360",
    "General / 360° Overview=2.General360",
    "Corrosion Details=03-Corrosion",
    "Corrosion Details=3.Corrosion",
    "Accessories=04-Accessories",
    "Accessories=4.Accessories",
    "Door Adjustment and Operation=05-Door",
    "Door Adjustment and Operation=5.Door",
    "Floor Placement=06-Floor",
    "Floor Placement=6.Floor",
    "Window Operation and Condition=08-Window",
    "Window Operation and Condition=8.Window",
    "Glass Condition=09-Glass",
    "Glass Condition=9.Glass",
    "Inner Appearance and Fixation of Seats=10-Inner",
    "Inner Appearance and Fixation of Seats=10.Inner",
    "Tire and Wheel Condition=11-Tire",
    "Tire and Wheel Condition=11.Tire",
    "Exterior Lights Condition=12-Exterior",
    "Exterior Lights Condition=12.Exterior",
    "Painting Condition=13-Painting",
    "Painting Condition=13.Painting",
    "Mirrors Condition=14-Mirrors",
    "Mirrors Condition=14.Mirrors",
)


@dataclass(frozen=True)
class GraphSettings:
    tenant_id: str
    client_id: str
    client_secret: str
    timeout_seconds: int
    user_agent: str

    @property
    def token_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

    @property
    def scope(self) -> str:
        return "https://graph.microsoft.com/.default"

    @classmethod
    def from_env(cls) -> "GraphSettings":
        required = {
            "GRAPH_TENANT_ID": _env("GRAPH_TENANT_ID") or _env("BC_TENANT_ID"),
            "GRAPH_CLIENT_ID": _env("GRAPH_CLIENT_ID") or _env("BC_CLIENT_ID"),
            "GRAPH_CLIENT_SECRET": _env("GRAPH_CLIENT_SECRET") or _env("BC_CLIENT_SECRET"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"Missing required Microsoft Graph environment variables: {joined}. "
                "Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, and GRAPH_CLIENT_SECRET."
            )

        return cls(
            tenant_id=required["GRAPH_TENANT_ID"],
            client_id=required["GRAPH_CLIENT_ID"],
            client_secret=required["GRAPH_CLIENT_SECRET"],
            timeout_seconds=int(_env("GRAPH_TIMEOUT_SECONDS") or "30"),
            user_agent=_env("GRAPH_USER_AGENT") or "ContractingTool/0.1",
        )


@dataclass(frozen=True)
class InspectionReportSettings:
    clickup_list_id: str | None
    clickup_workspace_id: str | None
    clickup_team_id: str | None
    custom_task_ids: bool
    sharepoint_hostname: str | None
    sharepoint_site_path: str | None
    sharepoint_source_folder_url: str | None
    sharepoint_source_folder_path: str | None
    sharepoint_output_folder_url: str | None
    sharepoint_output_folder_path: str | None
    output_dir: Path
    docx_output_dir: Path
    template_docx_path: Path | None
    use_legacy_docx_template: bool
    max_sharepoint_depth: int
    max_images_per_report: int
    template_max_images_per_section: int
    allowed_statuses: tuple[str, ...]
    report_field_names: tuple[str, ...]
    comment_field_ids: tuple[str, ...]
    comment_field_names: tuple[str, ...]
    image_match_field_names: tuple[str, ...]
    sharepoint_folder_field_names: tuple[str, ...]
    picture_folder_field_ids: tuple[str, ...]
    picture_folder_field_names: tuple[str, ...]
    report_link_field_ids: tuple[str, ...]
    report_link_field_names: tuple[str, ...]
    report_attachment_field_ids: tuple[str, ...]
    report_attachment_field_names: tuple[str, ...]
    image_extensions: tuple[str, ...]
    section_folder_prefixes: dict[str, tuple[str, ...]]

    @classmethod
    def from_env(cls) -> "InspectionReportSettings":
        return cls(
            clickup_list_id=_env("INSPECTION_REPORT_CLICKUP_LIST_ID"),
            clickup_workspace_id=_env("CLICKUP_DEFAULT_WORKSPACE_ID"),
            clickup_team_id=_env("CLICKUP_WEBHOOK_TEAM_ID"),
            custom_task_ids=_bool_env("CLICKUP_WEBHOOK_CUSTOM_TASK_IDS", default=False),
            sharepoint_hostname=_env("INSPECTION_REPORT_SHAREPOINT_HOSTNAME"),
            sharepoint_site_path=_env("INSPECTION_REPORT_SHAREPOINT_SITE_PATH"),
            sharepoint_source_folder_url=_env("INSPECTION_REPORT_SOURCE_FOLDER_URL"),
            sharepoint_source_folder_path=_env("INSPECTION_REPORT_SOURCE_FOLDER_PATH"),
            sharepoint_output_folder_url=_env("INSPECTION_REPORT_OUTPUT_FOLDER_URL"),
            sharepoint_output_folder_path=_env("INSPECTION_REPORT_OUTPUT_FOLDER_PATH"),
            output_dir=Path(_env("INSPECTION_REPORT_LOCAL_OUTPUT_DIR") or "output/pdf"),
            docx_output_dir=Path(_env("INSPECTION_REPORT_LOCAL_DOCX_OUTPUT_DIR") or "output/docx"),
            template_docx_path=(
                Path(template_path)
                if (template_path := _env("INSPECTION_REPORT_TEMPLATE_DOCX_PATH"))
                else None
            ),
            use_legacy_docx_template=_bool_env(
                "INSPECTION_REPORT_USE_LEGACY_DOCX_TEMPLATE",
                default=False,
            ),
            max_sharepoint_depth=int(_env("INSPECTION_REPORT_MAX_SHAREPOINT_DEPTH") or "2"),
            max_images_per_report=int(_env("INSPECTION_REPORT_MAX_IMAGES_PER_REPORT") or "30"),
            template_max_images_per_section=int(
                _env("INSPECTION_REPORT_TEMPLATE_MAX_IMAGES_PER_SECTION") or "4"
            ),
            allowed_statuses=_csv_env(
                "INSPECTION_REPORT_ALLOWED_STATUSES",
                DEFAULT_ALLOWED_STATUSES,
            ),
            report_field_names=_csv_env(
                "INSPECTION_REPORT_FIELD_NAMES",
                DEFAULT_REPORT_FIELD_NAMES,
            ),
            comment_field_ids=_csv_env("INSPECTION_REPORT_COMMENT_FIELD_IDS", ()),
            comment_field_names=_csv_env(
                "INSPECTION_REPORT_COMMENT_FIELD_NAMES",
                DEFAULT_COMMENT_FIELD_NAMES,
            ),
            image_match_field_names=_csv_env(
                "INSPECTION_REPORT_IMAGE_MATCH_FIELD_NAMES",
                DEFAULT_IMAGE_MATCH_FIELD_NAMES,
            ),
            sharepoint_folder_field_names=_csv_env(
                "INSPECTION_REPORT_SHAREPOINT_FOLDER_FIELD_NAMES",
                DEFAULT_SHAREPOINT_FOLDER_FIELD_NAMES,
            ),
            picture_folder_field_ids=_csv_env(
                "INSPECTION_REPORT_PICTURE_FOLDER_FIELD_IDS",
                DEFAULT_PICTURE_FOLDER_FIELD_IDS,
            ),
            picture_folder_field_names=_csv_env(
                "INSPECTION_REPORT_PICTURE_FOLDER_FIELD_NAMES",
                DEFAULT_SHAREPOINT_FOLDER_FIELD_NAMES,
            ),
            report_link_field_ids=_csv_env("INSPECTION_REPORT_LINK_FIELD_IDS", ()),
            report_link_field_names=_csv_env(
                "INSPECTION_REPORT_LINK_FIELD_NAMES",
                DEFAULT_REPORT_LINK_FIELD_NAMES,
            ),
            report_attachment_field_ids=_csv_env(
                "INSPECTION_REPORT_ATTACHMENT_FIELD_IDS",
                DEFAULT_REPORT_ATTACHMENT_FIELD_IDS,
            ),
            report_attachment_field_names=_csv_env(
                "INSPECTION_REPORT_ATTACHMENT_FIELD_NAMES",
                DEFAULT_REPORT_ATTACHMENT_FIELD_NAMES,
            ),
            image_extensions=tuple(
                extension.lower()
                for extension in _csv_env(
                    "INSPECTION_REPORT_IMAGE_EXTENSIONS",
                    DEFAULT_IMAGE_EXTENSIONS,
                )
            ),
            section_folder_prefixes=_mapping_env(
                "INSPECTION_REPORT_SECTION_FOLDER_PREFIXES",
                DEFAULT_SECTION_FOLDER_PREFIXES,
            ),
        )

    def require_clickup_list_id(self) -> str:
        if not self.clickup_list_id:
            raise ValueError("INSPECTION_REPORT_CLICKUP_LIST_ID is required for batch runs.")
        return self.clickup_list_id

    def require_sharepoint_location(self) -> tuple[str, str]:
        if not self.sharepoint_hostname or not self.sharepoint_site_path:
            raise ValueError(
                "INSPECTION_REPORT_SHAREPOINT_HOSTNAME and "
                "INSPECTION_REPORT_SHAREPOINT_SITE_PATH are required."
            )
        return self.sharepoint_hostname, self.sharepoint_site_path

    def require_source_folder_path(self) -> str:
        if self.sharepoint_source_folder_url:
            return self.sharepoint_source_folder_url
        if not self.sharepoint_source_folder_path:
            raise ValueError(
                "INSPECTION_REPORT_SOURCE_FOLDER_URL or "
                "INSPECTION_REPORT_SOURCE_FOLDER_PATH is required unless each task has "
                "an inspection photos folder field."
            )
        return self.sharepoint_source_folder_path

    def require_output_folder_path(self) -> str:
        if self.sharepoint_output_folder_url:
            return self.sharepoint_output_folder_url
        if not self.sharepoint_output_folder_path:
            raise ValueError(
                "INSPECTION_REPORT_OUTPUT_FOLDER_URL or "
                "INSPECTION_REPORT_OUTPUT_FOLDER_PATH is required."
            )
        return self.sharepoint_output_folder_path


def _env(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _env(name)
    if not raw:
        return default
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or default


def _bool_env(name: str, *, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def _mapping_env(name: str, default: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    values = _csv_env(name, default)
    mapping: dict[str, list[str]] = {}
    for value in values:
        if "=" not in value:
            continue
        key, pattern = value.split("=", 1)
        key = key.strip()
        pattern = pattern.strip()
        if not key or not pattern:
            continue
        mapping.setdefault(key, []).append(pattern)
    return {key: tuple(patterns) for key, patterns in mapping.items()}
