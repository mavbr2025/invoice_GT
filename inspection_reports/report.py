from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from textwrap import wrap
from typing import Iterable, Sequence

from PIL import Image, ImageOps

from inspection_reports.models import InspectionReport, ReportImage


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN * 2)
ASSET_DIR = Path(__file__).with_name("assets")

MTM_DEEP_BLUE = "#10108C"
MTM_GOLD = "#C9A24A"
MTM_PORCELAIN = "#F7F5EF"
MTM_PAPER = "#FCFBF8"
MTM_GRAPHITE = "#151821"
MTM_MUTED = "#6E7483"
MTM_LINE = "#D9D5CB"
MTM_GRID = "#F0EEE7"
PHOTO_BACKGROUND = "#E9E6DE"
PASS_BACKGROUND = "#E7F3DF"
PASS_FOREGROUND = "#2D6235"
NA_BACKGROUND = "#E9EBF1"
NA_FOREGROUND = "#5A6070"
REJECT_BACKGROUND = "#FBE6E6"
REJECT_FOREGROUND = "#8F1C1C"

CHECKPOINTS = (
    ("360 degree overview", "360 Overview Result"),
    ("Door adjustment and operation", "Door Result"),
    ("Floor placement / interior floor", "Floor Result"),
    ("Emergency exits", "Emergency exits Result"),
    ("Window operation", "Window Result"),
    ("Seat appearance and fixation", "Seat Appearance / Fixation Result"),
    ("Tire and wheel condition", "Tire and Wheel Result"),
    ("Car keys in glove box", "Car keys in glove box"),
    ("Accessories", "Accessories Result"),
    ("Corrosion", "Corrosion Result"),
    ("Painting", "Painting Result"),
    ("Glass", "Glass Result"),
    ("Exterior lights", "Exterior Lights Result"),
    ("Mirrors", "Mirrors Result"),
    ("Nameplate", "Branding Result"),
)


def build_inspection_report_pdf(report: InspectionReport, output_path: Path) -> Path:
    """Build the print-first MTM Logix Command Era inspection report."""
    try:
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "reportlab is required to generate inspection PDFs. "
            "Install dependencies with: python3 -m pip install -r requirements.txt"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font, font_bold = _register_fonts()
    sections = _group_images_by_folder(report.images)
    evidence_pages = sum(max(1, len(tuple(_chunks(images, 4)))) for _, images in sections)
    total_pages = 2 + evidence_pages if sections else 2

    pdf = canvas.Canvas(str(output_path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)
    vin = _field(report, "VIN number") or report.task_name
    pdf.setTitle(f"{vin} - Inspection Report")
    pdf.setAuthor("MTM Logix")
    pdf.setSubject("Inspection Report")

    _draw_cover_page(pdf, report, sections, font, font_bold)
    pdf.showPage()
    _draw_summary_page(pdf, report, page_number=2, total_pages=total_pages, font=font, font_bold=font_bold)
    pdf.showPage()

    page_number = 3
    for section, images in sections:
        for page_images in _chunks(images, 4):
            _draw_evidence_page(
                pdf,
                report=report,
                section=section,
                images=page_images,
                page_number=page_number,
                total_pages=total_pages,
                font=font,
                font_bold=font_bold,
            )
            pdf.showPage()
            page_number += 1

    pdf.save()
    return output_path


def build_report_model(
    *,
    task_id: str,
    task_name: str,
    custom_id: str | None,
    clickup_url: str | None,
    fields: dict[str, str],
    images: tuple[ReportImage, ...],
    notes: tuple[str, ...] = (),
) -> InspectionReport:
    return InspectionReport(
        task_id=task_id,
        task_name=task_name,
        custom_id=custom_id,
        clickup_url=clickup_url,
        generated_at=datetime.now(timezone.utc),
        fields=fields,
        images=images,
        notes=notes,
    )


def _register_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular_path = ASSET_DIR / "fonts" / "NotoSans-Regular.ttf"
    bold_path = ASSET_DIR / "fonts" / "NotoSans-Bold.ttf"
    regular_name = "MTMLogixNotoSans"
    bold_name = "MTMLogixNotoSansBold"
    registered = set(pdfmetrics.getRegisteredFontNames())
    if regular_path.exists() and bold_path.exists():
        if regular_name not in registered:
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if bold_name not in registered:
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        return regular_name, bold_name
    return "Helvetica", "Helvetica-Bold"


def _draw_cover_page(pdf, report: InspectionReport, sections, font: str, font_bold: str) -> None:
    from reportlab.lib.colors import HexColor

    _draw_light_page(pdf)
    _draw_logo(pdf, MARGIN, 690, 190)
    pdf.setFillColor(HexColor(MTM_GOLD))
    pdf.setFont(font_bold, 7.8)
    pdf.drawString(MARGIN, 626, "VERIFIED DOCUMENT")
    pdf.setFillColor(HexColor(MTM_DEEP_BLUE))
    pdf.setFont(font_bold, 27)
    pdf.drawString(MARGIN, 582, "Inspection Report")
    pdf.setFillColor(HexColor(MTM_GRAPHITE))
    pdf.setFont(font, 10.2)
    pdf.drawString(MARGIN, 547, "Evidence-led assessment of vehicle condition and delivery readiness.")
    pdf.setStrokeColor(HexColor(MTM_GOLD))
    pdf.setLineWidth(1)
    pdf.line(MARGIN, 514, 188, 514)

    vin = _field(report, "VIN number") or report.task_name
    vehicle = " ".join(value for value in (_field(report, "Brand"), _field(report, "Model")) if value)
    destination = _field(report, "Destination Country")
    inspection_date = _format_date(_field(report, "Inspection Date"))
    detail_line = "  |  ".join(value.upper() for value in (vehicle, destination, inspection_date) if value)

    pdf.setFillColor(HexColor(MTM_DEEP_BLUE))
    pdf.setFont(font_bold, 10.6)
    pdf.drawString(MARGIN, 484, _clip(vin, 56))
    pdf.setFillColor(HexColor(MTM_MUTED))
    pdf.setFont(font, 7.8)
    pdf.drawString(MARGIN, 466, _clip(detail_line, 96))
    _draw_status_chip(pdf, _overall_status(report), MARGIN, 430, 128, font, font_bold)

    hero_image = _cover_image(sections)
    if hero_image:
        _draw_cover_image(pdf, hero_image.local_path, MARGIN, 96, CONTENT_WIDTH, 292)
        pdf.setStrokeColor(HexColor(MTM_GOLD))
        pdf.setLineWidth(0.75)
        pdf.rect(MARGIN, 96, CONTENT_WIDTH, 292, fill=0, stroke=1)
    else:
        pdf.setFillColor(HexColor(MTM_PORCELAIN))
        pdf.rect(MARGIN, 96, CONTENT_WIDTH, 292, fill=1, stroke=0)
        pdf.setFillColor(HexColor(MTM_MUTED))
        pdf.setFont(font, 10)
        pdf.drawCentredString(PAGE_WIDTH / 2, 235, "No inspection photos were matched for this report.")

    pdf.setFillColor(HexColor(MTM_MUTED))
    pdf.setFont(font, 6.7)
    pdf.drawRightString(PAGE_WIDTH - MARGIN, 59, "MTM LOGIX  |  BEYOND VISIBILITY. INTO COMMAND.")


def _draw_summary_page(
    pdf,
    report: InspectionReport,
    *,
    page_number: int,
    total_pages: int,
    font: str,
    font_bold: str,
) -> None:
    from reportlab.lib.colors import HexColor

    _draw_light_page(pdf)
    _draw_header(pdf)
    _draw_section_heading(
        pdf,
        "01 / INSPECTION SUMMARY",
        "Vehicle condition, at a glance",
        "Structured findings and source details for the inspected unit.",
        font,
        font_bold,
    )
    _draw_status_chip(pdf, _overall_status(report), 376, 648, 194, font, font_bold)

    _draw_panel(pdf, MARGIN, 491, CONTENT_WIDTH, 124)
    pdf.setFillColor(HexColor(MTM_DEEP_BLUE))
    pdf.setFont(font_bold, 9.2)
    pdf.drawString(58, 588, "UNIT PROFILE")
    _draw_label_value(pdf, "Vehicle", _vehicle_name(report), 58, 560, font, font_bold)
    _draw_label_value(pdf, "VIN", _field(report, "VIN number") or report.task_name, 296, 560, font, font_bold)
    _draw_label_value(pdf, "Destination", _field(report, "Destination Country"), 58, 519, font, font_bold)
    _draw_label_value(pdf, "Inspection date", _format_date(_field(report, "Inspection Date")), 296, 519, font, font_bold)

    _draw_panel(pdf, MARGIN, 364, CONTENT_WIDTH, 99)
    pdf.setFillColor(HexColor(MTM_DEEP_BLUE))
    pdf.setFont(font_bold, 9.2)
    pdf.drawString(58, 436, "INSPECTION NOTE")
    note = _inspection_note(report)
    pdf.setFillColor(HexColor(MTM_GRAPHITE))
    pdf.setFont(font, 8.8)
    for index, line in enumerate(wrap(note, 92)[:3] or ["No inspection note was provided."]):
        pdf.drawString(58, 411 - index * 18, line)

    pdf.setFillColor(HexColor(MTM_DEEP_BLUE))
    pdf.setFont(font_bold, 9.2)
    pdf.drawString(MARGIN, 329, "CONTROL POINTS")
    _draw_checkpoints(pdf, report, font, font_bold)
    _draw_footer(pdf, report, page_number, total_pages, font)


def _draw_evidence_page(
    pdf,
    *,
    report: InspectionReport,
    section: str,
    images: Sequence[ReportImage],
    page_number: int,
    total_pages: int,
    font: str,
    font_bold: str,
) -> None:
    from reportlab.lib.colors import HexColor

    _draw_light_page(pdf)
    _draw_header(pdf)
    _draw_section_heading(
        pdf,
        "02 / PHOTO EVIDENCE",
        section,
        f"{len(images)} verified photo{'s' if len(images) != 1 else ''} from this inspection section.",
        font,
        font_bold,
        right=f"{len(images)} VERIFIED PHOTO{'S' if len(images) != 1 else ''}",
    )
    for image, (x, y, width, height) in zip(images, _photo_slots(len(images))):
        _draw_photo_card(
            pdf,
            image=image,
            x=x,
            y=y,
            width=width,
            height=height,
            font_bold=font_bold,
        )
    _draw_footer(pdf, report, page_number, total_pages, font)


def _draw_light_page(pdf) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setFillColor(HexColor(MTM_PORCELAIN))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor(MTM_PAPER))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor(MTM_GRID))
    pdf.setLineWidth(0.35)
    for x in range(40, PAGE_WIDTH, 36):
        pdf.line(x, 0, x, PAGE_HEIGHT)
    for y in range(18, PAGE_HEIGHT, 36):
        pdf.line(0, y, PAGE_WIDTH, y)


def _draw_logo(pdf, x: float, y: float, width: float) -> None:
    logo_path = ASSET_DIR / "mtm_logix_command_signature.png"
    if not logo_path.exists():
        return
    pdf.drawImage(str(logo_path), x, y, width=width, height=width * 364 / 1493, mask="auto")


def _draw_header(pdf) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setFillColor(HexColor(MTM_PAPER))
    pdf.rect(0, 730, PAGE_WIDTH, 62, fill=1, stroke=0)
    _draw_logo(pdf, MARGIN, 741, 128)
    pdf.setStrokeColor(HexColor(MTM_GOLD))
    pdf.setLineWidth(0.8)
    pdf.line(MARGIN, 729, PAGE_WIDTH - MARGIN, 729)


def _draw_section_heading(
    pdf,
    number: str,
    title: str,
    subtitle: str,
    font: str,
    font_bold: str,
    *,
    right: str = "",
) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setFillColor(HexColor(MTM_GOLD))
    pdf.setFont(font_bold, 7.4)
    pdf.drawString(MARGIN, 690, number)
    pdf.setFillColor(HexColor(MTM_GRAPHITE))
    pdf.setFont(font_bold, 19)
    pdf.drawString(MARGIN, 661, _clip(title, 48))
    pdf.setFillColor(HexColor(MTM_MUTED))
    pdf.setFont(font, 8.5)
    pdf.drawString(MARGIN, 643, _clip(subtitle, 105))
    if right:
        pdf.drawRightString(PAGE_WIDTH - MARGIN, 690, right)


def _draw_panel(pdf, x: float, y: float, width: float, height: float) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setFillColor(HexColor(MTM_PAPER))
    pdf.roundRect(x, y, width, height, 5, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor(MTM_LINE))
    pdf.setLineWidth(0.55)
    pdf.roundRect(x, y, width, height, 5, fill=0, stroke=1)


def _draw_label_value(pdf, label: str, value: str, x: float, y: float, font: str, font_bold: str) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setFillColor(HexColor(MTM_MUTED))
    pdf.setFont(font_bold, 6.3)
    pdf.drawString(x, y, label.upper())
    pdf.setFillColor(HexColor(MTM_GRAPHITE))
    pdf.setFont(font_bold, 9.1)
    pdf.drawString(x, y - 14, _clip(value or "-", 31))


def _draw_checkpoints(pdf, report: InspectionReport, font: str, font_bold: str) -> None:
    from reportlab.lib.colors import HexColor

    populated = [(label, _field(report, field)) for label, field in CHECKPOINTS]
    columns = ((MARGIN, 274), (321, PAGE_WIDTH - MARGIN))
    for column_index, (left, right) in enumerate(columns):
        values = populated[column_index * 8 : (column_index + 1) * 8]
        for row_index, (label, result) in enumerate(values):
            y = 300 - row_index * 28
            pdf.setStrokeColor(HexColor(MTM_LINE))
            pdf.setLineWidth(0.45)
            pdf.line(left, y - 8, right, y - 8)
            pdf.setFillColor(HexColor(MTM_GRAPHITE))
            pdf.setFont(font, 7.7)
            pdf.drawString(left, y, _clip(label, 35))
            _draw_status_chip(pdf, result or "-", right - 54, y - 6, 48, font, font_bold)


def _draw_status_chip(pdf, result: str, x: float, y: float, width: float, font: str, font_bold: str) -> None:
    from reportlab.lib.colors import HexColor

    label, background, foreground = _status_style(result)
    pdf.setFillColor(HexColor(background))
    pdf.roundRect(x, y, width, 18, 9, fill=1, stroke=0)
    pdf.setFillColor(HexColor(foreground))
    pdf.setFont(font_bold, 6.7)
    pdf.drawCentredString(x + width / 2, y + 6.2, _clip(label.upper(), 16))


def _draw_photo_card(
    pdf,
    *,
    image: ReportImage,
    x: float,
    y: float,
    width: float,
    height: float,
    font_bold: str,
) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setFillColor(HexColor(PHOTO_BACKGROUND))
    pdf.roundRect(x, y, width, height, 4, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor(MTM_LINE))
    pdf.setLineWidth(0.45)
    pdf.roundRect(x, y, width, height, 4, fill=0, stroke=1)
    image_area_height = height - 27
    padding = 7

    try:
        with Image.open(image.local_path) as source:
            photo = ImageOps.exif_transpose(source).convert("RGB")
            scale = min(
                (width - (padding * 2)) / photo.width,
                (image_area_height - (padding * 2)) / photo.height,
            )
            draw_width = photo.width * scale
            draw_height = photo.height * scale
            draw_x = x + ((width - draw_width) / 2)
            draw_y = y + 23 + ((image_area_height - draw_height) / 2)
            pdf.drawImage(
                _jpeg_image_reader(photo, max_size=(1200, 1200), quality=70),
                draw_x,
                draw_y,
                width=draw_width,
                height=draw_height,
            )
    except (FileNotFoundError, OSError):
        pdf.setFillColor(HexColor(MTM_MUTED))
        pdf.setFont(font_bold, 8)
        pdf.drawCentredString(x + (width / 2), y + (height / 2), "Image unavailable")

    pdf.setFillColor(HexColor(MTM_PAPER))
    pdf.rect(x, y, width, 23, fill=1, stroke=0)
    pdf.setFillColor(HexColor(MTM_GRAPHITE))
    pdf.setFont(font_bold, 6.7)
    pdf.drawString(x + 7, y + 7.4, _clip(image.caption or image.name, 39).upper())


def _draw_cover_image(pdf, path: Path, x: float, y: float, width: float, height: float) -> None:
    try:
        with Image.open(path) as source:
            photo = ImageOps.exif_transpose(source).convert("RGB")
            scale = max(width / photo.width, height / photo.height)
            resized = photo.resize(
                (round(photo.width * scale), round(photo.height * scale)),
                Image.Resampling.LANCZOS,
            )
            left = max(0, (resized.width - round(width)) // 2)
            top = max(0, (resized.height - round(height)) // 2)
            crop = resized.crop((left, top, left + round(width), top + round(height)))
            pdf.drawImage(
                _jpeg_image_reader(crop, max_size=(1600, 1200), quality=74),
                x,
                y,
                width=width,
                height=height,
            )
    except (FileNotFoundError, OSError):
        return


def _draw_footer(pdf, report: InspectionReport | None, page_number: int, total_pages: int, font: str) -> None:
    from reportlab.lib.colors import HexColor

    pdf.setStrokeColor(HexColor(MTM_LINE))
    pdf.setLineWidth(0.55)
    pdf.line(MARGIN, 34, PAGE_WIDTH - MARGIN, 34)
    vin = _field(report, "VIN number") if report else ""
    pdf.setFillColor(HexColor(MTM_MUTED))
    pdf.setFont(font, 6.8)
    pdf.drawString(MARGIN, 19, "MTM LOGIX  |  INSPECTION REPORT")
    pdf.drawRightString(PAGE_WIDTH - MARGIN, 19, f"{vin}  |  {page_number:02d} / {total_pages:02d}")


def _jpeg_image_reader(image: Image.Image, *, max_size: tuple[int, int], quality: int):
    from reportlab.lib.utils import ImageReader

    normalized = image.copy()
    normalized.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    normalized.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)
    return ImageReader(buffer)


def _group_images_by_folder(images: Iterable[ReportImage]) -> tuple[tuple[str, tuple[ReportImage, ...]], ...]:
    grouped: OrderedDict[str, list[ReportImage]] = OrderedDict()
    labels: dict[str, str] = {}
    for image in images:
        folder = _parent_folder(image.source_path)
        grouped.setdefault(folder, []).append(image)
        labels[folder] = image.section or _folder_label(folder)

    label_counts: dict[str, int] = {}
    results: list[tuple[str, tuple[ReportImage, ...]]] = []
    for folder, group in grouped.items():
        label = labels[folder]
        label_counts[label] = label_counts.get(label, 0) + 1
        display_label = label if label_counts[label] == 1 else f"{label} {label_counts[label]}"
        results.append((display_label, tuple(group)))
    return tuple(results)


def _parent_folder(path: str) -> str:
    return str(PurePosixPath(path).parent)


def _folder_label(folder: str) -> str:
    label = PurePosixPath(folder).name.replace("_", " ").replace("-", " ").strip()
    return label or "Inspection photos"


def _cover_image(sections: Sequence[tuple[str, Sequence[ReportImage]]]) -> ReportImage | None:
    for label, images in sections:
        if "360" in label.lower() or "general" in label.lower():
            return images[0] if images else None
    for _, images in sections:
        if images:
            return images[0]
    return None


def _photo_slots(count: int) -> tuple[tuple[float, float, float, float], ...]:
    if count <= 1:
        return ((MARGIN, 100, CONTENT_WIDTH, 500),)
    if count == 2:
        return ((MARGIN, 369, CONTENT_WIDTH, 236), (MARGIN, 100, CONTENT_WIDTH, 236))
    if count == 3:
        return (
            (MARGIN, 374, CONTENT_WIDTH, 231),
            (MARGIN, 100, 256, 236),
            (314, 100, 256, 236),
        )
    return (
        (MARGIN, 374, 256, 231),
        (314, 374, 256, 231),
        (MARGIN, 100, 256, 236),
        (314, 100, 256, 236),
    )


def _chunks(values: Sequence[ReportImage], size: int) -> tuple[tuple[ReportImage, ...], ...]:
    return tuple(tuple(values[index : index + size]) for index in range(0, len(values), size))


def _field(report: InspectionReport | None, name: str) -> str:
    if report is None:
        return ""
    value = report.fields.get(name)
    return str(value).strip() if value is not None else ""


def _vehicle_name(report: InspectionReport) -> str:
    return " ".join(value for value in (_field(report, "Brand"), _field(report, "Model")) if value) or "-"


def _inspection_note(report: InspectionReport) -> str:
    value = _field(report, "Inspection AI Exec Summary") or _field(report, "Inspection Result Summary")
    if value:
        return " ".join(value.split())
    if report.notes:
        return " ".join(report.notes)
    return ""


def _overall_status(report: InspectionReport) -> str:
    values = [(_field(report, field)).lower() for _, field in CHECKPOINTS]
    if any(any(token in value for token in ("reject", "fail", "not pass")) for value in values):
        return "Review required"
    if any(value for value in values):
        return "Inspection passed"
    return "Inspection completed"


def _status_style(result: str) -> tuple[str, str, str]:
    normalized = " ".join(str(result).split()).lower()
    if normalized in {"", "-"}:
        return "-", NA_BACKGROUND, NA_FOREGROUND
    if normalized in {"n/a", "na", "not applicable"}:
        return "N/A", NA_BACKGROUND, NA_FOREGROUND
    if any(token in normalized for token in ("reject", "fail", "not pass")):
        return result, REJECT_BACKGROUND, REJECT_FOREGROUND
    if normalized in {"yes", "yes (2)"}:
        return result, PASS_BACKGROUND, PASS_FOREGROUND
    if "pass" in normalized or "approved" in normalized:
        return "Pass", PASS_BACKGROUND, PASS_FOREGROUND
    return result, NA_BACKGROUND, NA_FOREGROUND


def _format_date(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return value


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."
