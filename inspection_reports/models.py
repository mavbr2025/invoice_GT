from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class SharePointItem:
    id: str
    name: str
    drive_id: str
    path: str
    web_url: str | None
    mime_type: str | None
    size_bytes: int | None = None
    is_folder: bool = False


@dataclass(frozen=True)
class ReportImage:
    name: str
    local_path: Path
    source_path: str
    web_url: str | None = None
    caption: str | None = None
    section: str | None = None


@dataclass(frozen=True)
class InspectionReport:
    task_id: str
    task_name: str
    custom_id: str | None
    clickup_url: str | None
    generated_at: datetime
    fields: dict[str, str]
    images: tuple[ReportImage, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
