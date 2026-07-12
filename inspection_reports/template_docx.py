from __future__ import annotations

import shutil
import subprocess
import zipfile
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from lxml import etree
from PIL import Image, ImageOps

from inspection_reports.models import InspectionReport, ReportImage


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NS = {"w": W_NS, "r": R_NS, "a": A_NS, "wp": WP_NS, "pic": PIC_NS, "rel": PKG_REL_NS}
IMAGE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
EMU_PER_INCH = 914400


INFO_TABLE_MAP = {
    "Destination Country": "Destination Country",
    "Color": "Color",
    "Port of Loading": "Port of Loading",
    "Motor": "Motor",
    "VIN Number": "VIN number",
    "Line": "Line",
    "Inspection date": "Inspection Date",
    "Model": "Model",
    "Brand": "Brand",
    "# Seats": "Number of seats",
}

CHECKPOINT_MAP = {
    "360° Overview": ("360 Overview Result", "360 Overview Comment"),
    "Door Adjustment and Operation": ("Door Result", ""),
    "Floor Placement / Interior Floor": ("Floor Result", ""),
    "Emergency Exits": ("Emergency exits Result", ""),
    "Window Operation": ("Window Result", ""),
    "Seat Appearance and Fixation": ("Seat Appearance / Fixation Result", ""),
    "Tire and Wheel Condition": ("Tire and Wheel Result", ""),
    "Car keys in glove box": ("Car keys in glove box", ""),
    "Accessories": ("Accessories Result", ""),
    "Corrosion": ("Corrosion Result", ""),
    "Painting": ("Painting Result", ""),
    "Glass": ("Glass Result", ""),
    "Exterior Lights": ("Exterior Lights Result", ""),
    "Mirrors": ("Mirrors Result", ""),
    "Nameplate": ("Branding Result", ""),
}

COMMENT_FIELD_NAMES = (
    "Inspection AI Exec Summary",
    "Inspection Result Summary",
)


def build_docx_from_template(
    *,
    report: InspectionReport,
    template_path: Path,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as tmp:
        working_path = Path(tmp) / "report.docx"
        shutil.copyfile(template_path, working_path)
        _patch_document_xml(working_path, report)
        _replace_image_sections(working_path, report)
        shutil.copyfile(working_path, output_path)

    return output_path


def convert_docx_to_pdf(docx_path: Path, output_dir: Path) -> Path | None:
    soffice = _find_soffice()
    if not soffice:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(soffice),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "LibreOffice failed to convert template DOCX to PDF: "
            + (result.stderr or result.stdout)
        )

    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    return pdf_path if pdf_path.exists() else None


def template_section_image_counts(template_path: Path) -> dict[str, int]:
    with zipfile.ZipFile(template_path, "r") as source:
        document_root = etree.fromstring(source.read("word/document.xml"))
    return {
        section: len(rids)
        for section, rids in _section_image_rids(document_root).items()
    }


def _patch_document_xml(docx_path: Path, report: InspectionReport) -> None:
    with zipfile.ZipFile(docx_path, "r") as source:
        document_xml = source.read("word/document.xml")
        file_payloads = {name: source.read(name) for name in source.namelist()}

    root = etree.fromstring(document_xml)
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError("Template document is missing word/body.")

    tables = body.findall("w:tbl", NS)
    if len(tables) < 2:
        raise ValueError("Template document must contain vehicle and checkpoint tables.")

    _patch_title(body, report)
    _patch_comments(body, report)
    _patch_info_table(tables[0], report)
    _patch_checkpoint_table(tables[1], report)

    file_payloads["word/document.xml"] = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    _rewrite_zip(docx_path, file_payloads)


def _patch_title(body: etree._Element, report: InspectionReport) -> None:
    for paragraph in body.findall("w:p", NS):
        text = _block_text(paragraph)
        if text.startswith("Inspection Report"):
            _set_block_text(paragraph, f"Inspection Report {report.task_name}")
            return


def _patch_comments(body: etree._Element, report: InspectionReport) -> None:
    found_heading = False
    comment = _first_report_field(report, COMMENT_FIELD_NAMES)
    for child in body.iterchildren():
        if child.tag == _w("p") and _block_text(child) == "Comments":
            found_heading = True
            continue
        if found_heading and child.tag == _w("p"):
            _set_block_text(child, comment)
            return


def _patch_info_table(table: etree._Element, report: InspectionReport) -> None:
    for row in table.findall("w:tr", NS):
        cells = row.findall("w:tc", NS)
        for index in range(0, len(cells) - 1, 2):
            label = _block_text(cells[index])
            field_name = INFO_TABLE_MAP.get(label)
            if field_name is None:
                continue
            value = report.fields.get(field_name)
            if label == "VIN Number" and not value:
                value = report.task_name
            _set_block_text(cells[index + 1], value or "")


def _patch_checkpoint_table(table: etree._Element, report: InspectionReport) -> None:
    _make_checkpoint_table_two_columns(table)
    rows = table.findall("w:tr", NS)
    for row in rows[1:]:
        cells = row.findall("w:tc", NS)
        if len(cells) < 2:
            continue
        checkpoint = _block_text(cells[0])
        result_field, _note_field = CHECKPOINT_MAP.get(checkpoint, ("", ""))
        if result_field:
            _set_block_text(cells[1], report.fields.get(result_field) or "")


def _make_checkpoint_table_two_columns(table: etree._Element) -> None:
    total_width = _table_grid_width(table) or 9360
    checkpoint_width = int(total_width * 0.74)
    result_width = total_width - checkpoint_width
    widths = (checkpoint_width, result_width)

    grid = table.find("w:tblGrid", NS)
    if grid is None:
        grid = etree.Element(_w("tblGrid"))
        properties = table.find("w:tblPr", NS)
        insert_at = 1 if properties is not None else 0
        table.insert(insert_at, grid)
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        column = etree.Element(_w("gridCol"))
        column.set(_w("w"), str(width))
        grid.append(column)

    for row in table.findall("w:tr", NS):
        cells = list(row.findall("w:tc", NS))
        for cell in cells[2:]:
            row.remove(cell)
        for index, cell in enumerate(row.findall("w:tc", NS)[:2]):
            _set_cell_width(cell, widths[index])


def _table_grid_width(table: etree._Element) -> int | None:
    widths: list[int] = []
    for column in table.findall("w:tblGrid/w:gridCol", NS):
        try:
            widths.append(int(column.get(_w("w")) or ""))
        except ValueError:
            return None
    return sum(widths) if widths else None


def _set_cell_width(cell: etree._Element, width: int) -> None:
    properties = cell.find("w:tcPr", NS)
    if properties is None:
        properties = etree.Element(_w("tcPr"))
        cell.insert(0, properties)

    width_node = properties.find("w:tcW", NS)
    if width_node is None:
        width_node = etree.Element(_w("tcW"))
        properties.insert(0, width_node)
    width_node.set(_w("w"), str(width))
    width_node.set(_w("type"), "dxa")


def _patch_media(docx_path: Path, report: InspectionReport) -> None:
    with zipfile.ZipFile(docx_path, "r") as source:
        payloads = {name: source.read(name) for name in source.namelist()}

    document_root = etree.fromstring(payloads["word/document.xml"])
    rels_root = etree.fromstring(payloads["word/_rels/document.xml.rels"])
    images_by_section = _selected_images_by_section(report.images)
    selected_counts = {section: len(images) for section, images in images_by_section.items()}
    _prune_image_placeholders(document_root, selected_counts)

    rel_targets = {
        rel.get("Id"): "word/" + (rel.get("Target") or "").lstrip("/")
        for rel in rels_root.findall("rel:Relationship", NS)
        if (rel.get("Target") or "").startswith("media/")
    }
    section_rids = _section_image_rids(document_root)

    for section, rids in section_rids.items():
        section_images = images_by_section.get(section, ())
        for index, rid in enumerate(rids):
            target = rel_targets.get(rid)
            if not target:
                continue
            if index < len(section_images):
                payloads[target] = _image_as_jpeg(section_images[index].local_path)

    payloads["word/document.xml"] = etree.tostring(
        document_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    _rewrite_zip(docx_path, payloads)


def _replace_image_sections(docx_path: Path, report: InspectionReport) -> None:
    with zipfile.ZipFile(docx_path, "r") as source:
        payloads = {name: source.read(name) for name in source.namelist()}

    document_root = etree.fromstring(payloads["word/document.xml"])
    rels_root = etree.fromstring(payloads["word/_rels/document.xml.rels"])
    body = document_root.find("w:body", NS)
    if body is None:
        raise ValueError("Template document is missing word/body.")

    heading_template = _remove_template_image_sections(body)
    _force_single_column_layout(document_root)
    _drop_unused_media(payloads, rels_root, document_root)

    insert_at = _section_insert_index(body)
    next_rid = _next_relationship_number(rels_root)
    next_doc_pr_id = _next_doc_pr_id(document_root)
    media_index = 1

    for section, images in _images_by_folder_section(report.images).items():
        if not images:
            continue
        heading = _build_section_heading(section, heading_template)
        body.insert(insert_at, heading)
        insert_at += 1

        relationships: list[tuple[ReportImage, str, int, int]] = []
        for image in _select_section_images(section, images):
            rid = f"rId{next_rid}"
            next_rid += 1
            media_name = f"media/report-image-{media_index:03d}.jpeg"
            media_index += 1
            payloads[f"word/{media_name}"] = _image_as_jpeg(image.local_path)
            rel = etree.SubElement(rels_root, f"{{{PKG_REL_NS}}}Relationship")
            rel.set("Id", rid)
            rel.set("Type", IMAGE_REL_TYPE)
            rel.set("Target", media_name)
            width, height = _image_extent(image.local_path)
            relationships.append((image, rid, width, height))

        table = _build_dynamic_image_table(relationships, next_doc_pr_id)
        next_doc_pr_id += len(relationships)
        body.insert(insert_at, table)
        insert_at += 1

    payloads["word/document.xml"] = etree.tostring(
        document_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    payloads["word/_rels/document.xml.rels"] = etree.tostring(
        rels_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    _rewrite_zip(docx_path, payloads)


def _section_image_rids(document_root: etree._Element) -> dict[str, tuple[str, ...]]:
    body = document_root.find("w:body", NS)
    if body is None:
        return {}

    current_section: str | None = None
    mapping: dict[str, list[str]] = defaultdict(list)
    for child in body.iterchildren():
        if child.tag == _w("p"):
            text = _block_text(child)
            if text in _template_section_names():
                current_section = text
        if current_section:
            for blip in child.findall(".//a:blip", NS):
                rid = blip.get(_r("embed"))
                if rid:
                    mapping[current_section].append(rid)
    return {section: tuple(rids) for section, rids in mapping.items()}


def _images_by_section(images: tuple[ReportImage, ...]) -> dict[str, tuple[ReportImage, ...]]:
    grouped: dict[str, list[ReportImage]] = defaultdict(list)
    for image in sorted(images, key=lambda item: item.source_path):
        if image.section:
            grouped[image.section].append(image)
    return {section: tuple(values) for section, values in grouped.items()}


def _images_by_folder_section(images: tuple[ReportImage, ...]) -> dict[str, tuple[ReportImage, ...]]:
    grouped: dict[str, list[ReportImage]] = {}
    labels: dict[str, str] = {}
    for image in sorted(images, key=lambda item: item.source_path):
        folder = _parent_folder_path(image.source_path)
        label = image.section or _folder_label_from_path(folder)
        labels[folder] = label
        grouped.setdefault(folder, []).append(image)

    result: dict[str, tuple[ReportImage, ...]] = {}
    label_counts: dict[str, int] = {}
    for folder, values in grouped.items():
        label = labels[folder]
        label_counts[label] = label_counts.get(label, 0) + 1
        unique_label = label if label_counts[label] == 1 else f"{label} {label_counts[label]}"
        result[unique_label] = tuple(values)
    return result


def _selected_images_by_section(images: tuple[ReportImage, ...]) -> dict[str, tuple[ReportImage, ...]]:
    return {
        section: _select_section_images(section, section_images)
        for section, section_images in _images_by_section(images).items()
    }


def _select_section_images(section: str, images: tuple[ReportImage, ...]) -> tuple[ReportImage, ...]:
    if section != "Car Information":
        return images

    remaining = list(images)
    selected: list[ReportImage] = []
    for token in ("vin", "nameplate"):
        match = next(
            (
                image
                for image in remaining
                if token in image.name.lower() or token in image.source_path.lower()
            ),
            None,
        )
        if match:
            selected.append(match)
            remaining.remove(match)
    selected.extend(remaining)
    return tuple(selected)


def _prune_image_placeholders(
    document_root: etree._Element,
    selected_counts: dict[str, int],
) -> None:
    body = document_root.find("w:body", NS)
    if body is None:
        return

    current_section: str | None = None
    remaining_by_section = dict(selected_counts)
    for child in list(body.iterchildren()):
        if child.tag == _w("p"):
            text = _block_text(child)
            if text in _template_section_names():
                current_section = text
            continue

        if child.tag != _w("tbl") or not current_section or not _table_has_images(child):
            continue

        keep_count = remaining_by_section.get(current_section, 0)
        kept_count = _prune_table_images(child, keep_count)
        remaining_by_section[current_section] = max(0, keep_count - kept_count)
        if not _table_has_images(child):
            body.remove(child)


def _prune_table_images(table: etree._Element, keep_count: int) -> int:
    kept_count = 0
    max_cells = max((len(row.findall("w:tc", NS)) for row in table.findall("w:tr", NS)), default=1)
    for row in list(table.findall("w:tr", NS)):
        cells = list(row.findall("w:tc", NS))
        row_has_image = any(_cell_has_image(cell) for cell in cells)

        if row_has_image:
            for cell in cells:
                if _cell_has_image(cell):
                    if kept_count < keep_count:
                        kept_count += len(cell.findall(".//a:blip", NS))
                    else:
                        row.remove(cell)
                elif _is_empty_cell(cell):
                    row.remove(cell)
            if not any(_cell_has_image(cell) for cell in row.findall("w:tc", NS)):
                table.remove(row)
                continue
            _span_single_cell_row(row, max_cells)
            continue

        if keep_count <= 0 or _is_empty_row(row):
            table.remove(row)
            continue

        for index, cell in enumerate(list(row.findall("w:tc", NS)), start=1):
            if index > keep_count:
                row.remove(cell)
        _span_single_cell_row(row, max_cells)

    return min(kept_count, keep_count)


def _table_has_images(table: etree._Element) -> bool:
    return bool(table.findall(".//a:blip", NS))


def _cell_has_image(cell: etree._Element) -> bool:
    return bool(cell.findall(".//a:blip", NS))


def _is_empty_row(row: etree._Element) -> bool:
    return all(_is_empty_cell(cell) for cell in row.findall("w:tc", NS))


def _is_empty_cell(cell: etree._Element) -> bool:
    return not _block_text(cell) and not _cell_has_image(cell)


def _span_single_cell_row(row: etree._Element, span: int) -> None:
    cells = row.findall("w:tc", NS)
    if len(cells) != 1 or span <= 1:
        return

    cell = cells[0]
    _center_cell_content(cell)
    properties = cell.find("w:tcPr", NS)
    if properties is None:
        properties = etree.Element(_w("tcPr"))
        cell.insert(0, properties)
    grid_span = properties.find("w:gridSpan", NS)
    if grid_span is None:
        grid_span = etree.Element(_w("gridSpan"))
        properties.append(grid_span)
    grid_span.set(_w("val"), str(span))


def _center_cell_content(cell: etree._Element) -> None:
    for paragraph in cell.findall(".//w:p", NS):
        properties = paragraph.find("w:pPr", NS)
        if properties is None:
            properties = etree.Element(_w("pPr"))
            paragraph.insert(0, properties)
        justification = properties.find("w:jc", NS)
        if justification is None:
            justification = etree.Element(_w("jc"))
            properties.append(justification)
        justification.set(_w("val"), "center")


def _remove_template_image_sections(body: etree._Element) -> etree._Element | None:
    children = list(body.iterchildren())
    start_index: int | None = None
    heading_template: etree._Element | None = None
    for index, child in enumerate(children):
        if child.tag == _w("p") and _block_text(child) in _template_section_names():
            start_index = index
            heading_template = deepcopy(child)
            break
    if start_index is None:
        return None

    for child in children[start_index:]:
        if child.tag != _w("sectPr"):
            body.remove(child)
    return heading_template


def _section_insert_index(body: etree._Element) -> int:
    children = list(body.iterchildren())
    for index, child in enumerate(children):
        if child.tag == _w("sectPr"):
            return index
    return len(children)


def _drop_unused_media(
    payloads: dict[str, bytes],
    rels_root: etree._Element,
    document_root: etree._Element,
) -> None:
    used_rids = {
        rid
        for blip in document_root.findall(".//a:blip", NS)
        if (rid := blip.get(_r("embed")))
    }
    for rel in list(rels_root.findall("rel:Relationship", NS)):
        if rel.get("Type") != IMAGE_REL_TYPE or rel.get("Id") in used_rids:
            continue
        target = rel.get("Target") or ""
        payloads.pop("word/" + target.lstrip("/"), None)
        rels_root.remove(rel)


def _force_single_column_layout(document_root: etree._Element) -> None:
    for section_properties in document_root.findall(".//w:sectPr", NS):
        columns = section_properties.find("w:cols", NS)
        if columns is None:
            columns = etree.SubElement(section_properties, _w("cols"))
        columns.attrib.pop(_w("num"), None)


def _build_section_heading(
    section: str,
    heading_template: etree._Element | None,
) -> etree._Element:
    if heading_template is not None:
        heading = deepcopy(heading_template)
        _set_block_text(heading, section)
        return heading

    paragraph = etree.Element(_w("p"))
    run = etree.SubElement(paragraph, _w("r"))
    text = etree.SubElement(run, _w("t"))
    text.text = section
    return paragraph


def _build_dynamic_image_table(
    images: list[tuple[ReportImage, str, int, int]],
    first_doc_pr_id: int,
) -> etree._Element:
    table_width = 9360
    column_width = table_width // 2
    table = etree.Element(_w("tbl"))
    properties = etree.SubElement(table, _w("tblPr"))
    table_width_node = etree.SubElement(properties, _w("tblW"))
    table_width_node.set(_w("w"), str(table_width))
    table_width_node.set(_w("type"), "dxa")
    borders = etree.SubElement(properties, _w("tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = etree.SubElement(borders, _w(edge))
        border.set(_w("val"), "single")
        border.set(_w("sz"), "4")
        border.set(_w("space"), "0")
        border.set(_w("color"), "808080")

    grid = etree.SubElement(table, _w("tblGrid"))
    for _ in range(2):
        column = etree.SubElement(grid, _w("gridCol"))
        column.set(_w("w"), str(column_width))

    for row_index in range(0, len(images), 2):
        row_images = images[row_index : row_index + 2]
        row = etree.SubElement(table, _w("tr"))
        if len(row_images) == 1:
            cell = _build_image_cell(
                row_images[0],
                width=table_width,
                doc_pr_id=first_doc_pr_id + row_index,
                grid_span=2,
            )
            row.append(cell)
            continue

        for offset, image in enumerate(row_images):
            row.append(
                _build_image_cell(
                    image,
                    width=column_width,
                    doc_pr_id=first_doc_pr_id + row_index + offset,
                )
            )
    return table


def _build_image_cell(
    image: tuple[ReportImage, str, int, int],
    *,
    width: int,
    doc_pr_id: int,
    grid_span: int | None = None,
) -> etree._Element:
    report_image, rid, image_width, image_height = image
    cell = etree.Element(_w("tc"))
    properties = etree.SubElement(cell, _w("tcPr"))
    cell_width = etree.SubElement(properties, _w("tcW"))
    cell_width.set(_w("w"), str(width))
    cell_width.set(_w("type"), "dxa")
    if grid_span:
        span = etree.SubElement(properties, _w("gridSpan"))
        span.set(_w("val"), str(grid_span))
    vertical_align = etree.SubElement(properties, _w("vAlign"))
    vertical_align.set(_w("val"), "center")

    paragraph = etree.SubElement(cell, _w("p"))
    paragraph_properties = etree.SubElement(paragraph, _w("pPr"))
    justification = etree.SubElement(paragraph_properties, _w("jc"))
    justification.set(_w("val"), "center")
    run = etree.SubElement(paragraph, _w("r"))
    run.append(_build_drawing(report_image.name, rid, image_width, image_height, doc_pr_id))
    return cell


def _build_drawing(
    name: str,
    rid: str,
    width: int,
    height: int,
    doc_pr_id: int,
) -> etree._Element:
    drawing = etree.Element(_w("drawing"))
    inline = etree.SubElement(drawing, _wp("inline"))
    inline.set("distT", "0")
    inline.set("distB", "0")
    inline.set("distL", "0")
    inline.set("distR", "0")
    extent = etree.SubElement(inline, _wp("extent"))
    extent.set("cx", str(width))
    extent.set("cy", str(height))
    effect_extent = etree.SubElement(inline, _wp("effectExtent"))
    for side in ("l", "t", "r", "b"):
        effect_extent.set(side, "0")
    doc_pr = etree.SubElement(inline, _wp("docPr"))
    doc_pr.set("id", str(doc_pr_id))
    doc_pr.set("name", f"Picture {doc_pr_id}")
    doc_pr.set("descr", name)
    frame_properties = etree.SubElement(inline, _wp("cNvGraphicFramePr"))
    etree.SubElement(frame_properties, _a("graphicFrameLocks")).set("noChangeAspect", "1")

    graphic = etree.SubElement(inline, _a("graphic"))
    graphic_data = etree.SubElement(graphic, _a("graphicData"))
    graphic_data.set("uri", PIC_NS)
    picture = etree.SubElement(graphic_data, _pic("pic"))
    non_visual = etree.SubElement(picture, _pic("nvPicPr"))
    c_nv_pr = etree.SubElement(non_visual, _pic("cNvPr"))
    c_nv_pr.set("id", "0")
    c_nv_pr.set("name", name)
    etree.SubElement(non_visual, _pic("cNvPicPr"))
    blip_fill = etree.SubElement(picture, _pic("blipFill"))
    blip = etree.SubElement(blip_fill, _a("blip"))
    blip.set(_r("embed"), rid)
    stretch = etree.SubElement(blip_fill, _a("stretch"))
    etree.SubElement(stretch, _a("fillRect"))
    shape_properties = etree.SubElement(picture, _pic("spPr"))
    transform = etree.SubElement(shape_properties, _a("xfrm"))
    offset = etree.SubElement(transform, _a("off"))
    offset.set("x", "0")
    offset.set("y", "0")
    shape_extent = etree.SubElement(transform, _a("ext"))
    shape_extent.set("cx", str(width))
    shape_extent.set("cy", str(height))
    geometry = etree.SubElement(shape_properties, _a("prstGeom"))
    geometry.set("prst", "rect")
    etree.SubElement(geometry, _a("avLst"))
    return drawing


def _image_extent(path: Path) -> tuple[int, int]:
    max_width = int(3.1 * EMU_PER_INCH)
    max_height = int(2.25 * EMU_PER_INCH)
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return max(1, int(width * scale)), max(1, int(height * scale))


def _next_relationship_number(rels_root: etree._Element) -> int:
    highest = 0
    for rel in rels_root.findall("rel:Relationship", NS):
        rel_id = rel.get("Id") or ""
        if rel_id.startswith("rId") and rel_id[3:].isdigit():
            highest = max(highest, int(rel_id[3:]))
    return highest + 1


def _next_doc_pr_id(document_root: etree._Element) -> int:
    highest = 0
    for node in document_root.findall(".//wp:docPr", NS):
        try:
            highest = max(highest, int(node.get("id") or "0"))
        except ValueError:
            continue
    return highest + 1


def _parent_folder_path(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _folder_label_from_path(path: str) -> str:
    name = path.rsplit("/", 1)[-1] if path else ""
    cleaned = " ".join(name.replace("_", " ").replace("-", " ").split())
    return cleaned or "Inspection Photos"


def _template_section_names() -> set[str]:
    return {
        "Car Information",
        "General / 360° Overview",
        "Corrosion Details",
        "Door Adjustment and Operation",
        "Floor Placement",
        "Window Operation and Condition",
        "Inner Appearance and Fixation of Seats",
        "Tire and Wheel Condition",
        "Exterior Lights Condition",
        "Glass Condition",
        "Painting Condition",
        "Mirrors Condition",
        "Accessories",
    }


def _block_text(element: etree._Element) -> str:
    return " ".join("".join(text for text in element.xpath(".//w:t/text()", namespaces=NS)).split())


def _set_block_text(element: etree._Element, value: Any) -> None:
    texts = element.findall(".//w:t", NS)
    value = "" if value is None else str(value)
    if not texts:
        return
    texts[0].text = value
    for node in texts[1:]:
        node.text = ""


def _first_report_field(report: InspectionReport, field_names: tuple[str, ...]) -> str:
    for field_name in field_names:
        value = report.fields.get(field_name)
        if value:
            return str(value)
    return ""


def _single_line(value: Any, *, max_chars: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _image_as_jpeg(path: Path) -> bytes:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality=90)
        return output.getvalue()


def _rewrite_zip(path: Path, payloads: dict[str, bytes]) -> None:
    tmp_path = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, payload in payloads.items():
            target.writestr(name, payload)
    tmp_path.replace(path)


def _find_soffice() -> Path | None:
    for candidate in (
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _w(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def _r(name: str) -> str:
    return f"{{{R_NS}}}{name}"


def _a(name: str) -> str:
    return f"{{{A_NS}}}{name}"


def _wp(name: str) -> str:
    return f"{{{WP_NS}}}{name}"


def _pic(name: str) -> str:
    return f"{{{PIC_NS}}}{name}"
