#!/usr/bin/env python3
"""Build the MTM GT invoice RDLC layout from the current FacturaGTM layout."""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw, ImageFont


RDL_NS = "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"
RD_NS = "http://schemas.microsoft.com/SQLServer/reporting/reportdesigner"
NS = {"r": RDL_NS, "rd": RD_NS}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGO_ASSET_PATH = PROJECT_ROOT / "assets" / "mtm-logix-logo.png"
PAGE_LEFT = "0.39in"
PAGE_RIGHT = "8.10in"
PAGE_WIDTH = "7.71in"
PAGE_TOP = "0.39in"
PAGE_BOTTOM = "9.58in"
PAGE_FRAME_HEIGHT = "9.19in"
CONTENT_LEFT = "0.50in"
CONTENT_WIDTH = "7.50in"
HEADER_SPLIT = "4.25in"
HEADER_RIGHT_WIDTH = "3.85in"
BC_FONT_FAMILY = "Aptos"
TEXT_COLOR = "#111111"


def qn(name: str) -> str:
    return f"{{{RDL_NS}}}{name}"


def rd_qn(name: str) -> str:
    return f"{{{RD_NS}}}{name}"


def child(parent: etree._Element, name: str, text: str | None = None) -> etree._Element:
    node = etree.SubElement(parent, qn(name))
    if text is not None:
        node.text = text
    return node


def style(parent: etree._Element, values: dict[str, str]) -> etree._Element:
    style_node = child(parent, "Style")
    for key, value in values.items():
        child(style_node, key, value)
    return style_node


def textbox(
    name: str,
    value: str,
    top: str,
    left: str,
    height: str,
    width: str,
    *,
    font_size: str = "8pt",
    font_weight: str = "Normal",
    color: str = "Black",
    text_align: str = "Left",
    border: str = "None",
    background: str | None = None,
) -> etree._Element:
    box = etree.Element(qn("Textbox"), Name=name)
    child(box, "CanGrow", "true")
    child(box, "KeepTogether", "true")
    paragraphs = child(box, "Paragraphs")
    paragraph = child(paragraphs, "Paragraph")
    text_runs = child(paragraph, "TextRuns")
    text_run = child(text_runs, "TextRun")
    child(text_run, "Value", value)
    style(text_run, {"FontSize": font_size, "FontWeight": font_weight, "Color": color, "FontFamily": BC_FONT_FAMILY})
    style(paragraph, {"TextAlign": text_align})
    etree.SubElement(box, rd_qn("DefaultName")).text = name
    child(box, "Top", top)
    child(box, "Left", left)
    child(box, "Height", height)
    child(box, "Width", width)
    style_node = child(box, "Style")
    border_node = child(style_node, "Border")
    child(border_node, "Style", border)
    if background is not None:
        child(style_node, "BackgroundColor", background)
    for padding in ("PaddingLeft", "PaddingRight", "PaddingTop", "PaddingBottom"):
        child(style_node, padding, "2pt")
    return box


def paragraph(value: str, *, size: str, weight: str = "Normal", color: str = TEXT_COLOR) -> etree._Element:
    p = etree.Element(qn("Paragraph"))
    runs = child(p, "TextRuns")
    run = child(runs, "TextRun")
    child(run, "Value", value)
    style(run, {"FontSize": size, "FontWeight": weight, "Color": color, "FontFamily": BC_FONT_FAMILY})
    style(p, {})
    return p


def build_watermark_png() -> str:
    img = Image.new("RGBA", (1700, 900), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 320)
    except OSError:
        font = ImageFont.load_default()

    text = "INVOICE"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((1700 - tw) / 2, (900 - th) / 2), text, font=font, fill=(205, 205, 205, 128))
    img = img.rotate(32, expand=True, resample=Image.Resampling.BICUBIC)
    alpha = img.getchannel("A")
    visible = alpha.getbbox()
    if visible is not None:
        margin = 80
        left = max(visible[0] - margin, 0)
        top = max(visible[1] - margin, 0)
        right = min(visible[2] + margin, img.width)
        bottom = min(visible[3] + margin, img.height)
        img = img.crop((left, top, right, bottom))

    output = io.BytesIO()
    img.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def build_fel_badge_png() -> str:
    img = Image.new("RGBA", (360, 220), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 96)
        small_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.rounded_rectangle((8, 8, 352, 212), radius=22, outline=(17, 17, 17, 255), width=5, fill=(255, 255, 255, 255))
    text = "FEL"
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(((360 - (bbox[2] - bbox[0])) / 2, 38), text, font=font, fill=(17, 17, 17, 255))
    caption = "Guatemala"
    cb = draw.textbbox((0, 0), caption, font=small_font)
    draw.text(((360 - (cb[2] - cb[0])) / 2, 145), caption, font=small_font, fill=(70, 70, 70, 255))

    output = io.BytesIO()
    img.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def image_file_to_base64(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required image asset not found: {path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def ensure_embedded_image(root: etree._Element, name: str, image_data: str) -> None:
    embedded_images = root.find("r:EmbeddedImages", namespaces=NS)
    if embedded_images is None:
        language = root.find("r:Language", namespaces=NS)
        embedded_images = etree.Element(qn("EmbeddedImages"))
        root.insert(list(root).index(language), embedded_images)

    for existing in embedded_images.findall("r:EmbeddedImage", namespaces=NS):
        if existing.get("Name") == name:
            embedded_images.remove(existing)

    image = child(embedded_images, "EmbeddedImage")
    image.set("Name", name)
    child(image, "MIMEType", "image/png")
    child(image, "ImageData", image_data)


def image_item(
    name: str,
    embedded_name: str,
    top: str,
    left: str,
    height: str,
    width: str,
    *,
    z_index: str | None = None,
) -> etree._Element:
    item = etree.Element(qn("Image"), Name=name)
    child(item, "Source", "Embedded")
    child(item, "Value", embedded_name)
    child(item, "Sizing", "FitProportional")
    child(item, "Top", top)
    child(item, "Left", left)
    child(item, "Height", height)
    child(item, "Width", width)
    style_node = child(item, "Style")
    border_node = child(style_node, "Border")
    child(border_node, "Style", "None")
    if z_index is not None:
        child(item, "ZIndex", z_index)
    return item


def rectangle_item(name: str, top: str, left: str, height: str, width: str) -> etree._Element:
    item = etree.Element(qn("Rectangle"), Name=name)
    child(item, "ReportItems")
    child(item, "KeepTogether", "true")
    child(item, "Top", top)
    child(item, "Left", left)
    child(item, "Height", height)
    child(item, "Width", width)
    style_node = child(item, "Style")
    border_node = child(style_node, "Border")
    child(border_node, "Style", "Solid")
    child(border_node, "Width", "0.5pt")
    child(border_node, "Color", TEXT_COLOR)
    return item


def database_image_item(
    name: str,
    value: str,
    mime_type: str,
    top: str,
    left: str,
    height: str,
    width: str,
) -> etree._Element:
    item = etree.Element(qn("Image"), Name=name)
    child(item, "Source", "Database")
    child(item, "Value", value)
    child(item, "MIMEType", mime_type)
    child(item, "Sizing", "FitProportional")
    child(item, "Top", top)
    child(item, "Left", left)
    child(item, "Height", height)
    child(item, "Width", width)
    visibility = child(item, "Visibility")
    child(visibility, "Hidden", '=Len(First(Fields!MTM_FEL_QR_Code.Value, "DataSet_Result")) = 0')
    style_node = child(item, "Style")
    border_node = child(style_node, "Border")
    child(border_node, "Style", "None")
    return item


def line_item(name: str, top: str, left: str, height: str, width: str, *, color: str = "#111111") -> etree._Element:
    item = etree.Element(qn("Line"), Name=name)
    child(item, "Top", top)
    child(item, "Left", left)
    child(item, "Height", height)
    child(item, "Width", width)
    style_node = child(item, "Style")
    border_node = child(style_node, "Border")
    child(border_node, "Style", "Solid")
    child(border_node, "Color", color)
    return item


def set_child_text(parent: etree._Element, tag: str, value: str) -> None:
    node = parent.find(f"r:{tag}", namespaces=NS)
    if node is None:
        child(parent, tag, value)
    else:
        node.text = value


def report_body_items(root: etree._Element) -> etree._Element:
    report_items = root.find(".//r:Body/r:ReportItems", namespaces=NS)
    if report_items is None:
        raise RuntimeError("ReportItems not found")
    return report_items


def ensure_dataset_field(root: etree._Element, field_name: str) -> None:
    fields = root.find(".//r:DataSet[@Name='DataSet_Result']/r:Fields", namespaces=NS)
    if fields is None:
        raise RuntimeError("DataSet_Result fields not found")
    for field in fields.findall("r:Field", namespaces=NS):
        if field.get("Name") == field_name:
            return

    field = child(fields, "Field")
    field.set("Name", field_name)
    child(field, "DataField", field_name)


def find_body_item(root: etree._Element, name: str) -> etree._Element | None:
    return root.find(f".//r:Body/r:ReportItems/*[@Name='{name}']", namespaces=NS)


def set_position(item: etree._Element, *, top: str | None = None, left: str | None = None, height: str | None = None, width: str | None = None) -> None:
    values = {"Top": top, "Left": left, "Height": height, "Width": width}
    for tag, value in values.items():
        if value is not None:
            set_child_text(item, tag, value)


def set_border(item: etree._Element, border: str) -> None:
    style_node = item.find("r:Style", namespaces=NS)
    if style_node is None:
        style_node = child(item, "Style")
    border_node = style_node.find("r:Border", namespaces=NS)
    if border_node is None:
        border_node = child(style_node, "Border")
    set_child_text(border_node, "Style", border)


def set_border_width(item: etree._Element, width: str) -> None:
    style_node = item.find("r:Style", namespaces=NS)
    if style_node is None:
        style_node = child(item, "Style")
    border_node = style_node.find("r:Border", namespaces=NS)
    if border_node is None:
        border_node = child(style_node, "Border")
    set_child_text(border_node, "Width", width)


def set_textbox_value(box: etree._Element, value: str) -> None:
    value_node = box.find(".//r:TextRun/r:Value", namespaces=NS)
    if value_node is None:
        raise RuntimeError(f"value node not found for {box.get('Name')}")
    value_node.text = value


def set_textbox_text_runs(
    box: etree._Element,
    runs: list[tuple[str, str] | tuple[str, str, str]],
    *,
    text_align: str = "Left",
) -> None:
    paragraphs = box.find("r:Paragraphs", namespaces=NS)
    if paragraphs is None:
        paragraphs = child(box, "Paragraphs")
    for node in list(paragraphs):
        paragraphs.remove(node)

    paragraph_node = child(paragraphs, "Paragraph")
    text_runs = child(paragraph_node, "TextRuns")
    for run_spec in runs:
        value = run_spec[0]
        font_weight = run_spec[1]
        font_size = run_spec[2] if len(run_spec) > 2 else "8pt"
        text_run = child(text_runs, "TextRun")
        child(text_run, "Value", value)
        style(
            text_run,
            {
                "FontSize": font_size,
                "FontWeight": font_weight,
                "Color": TEXT_COLOR,
                "FontFamily": BC_FONT_FAMILY,
            },
        )
    style(paragraph_node, {"TextAlign": text_align})


def set_textbox_single_run(
    box: etree._Element,
    value: str,
    *,
    font_size: str = "8pt",
    font_weight: str = "Normal",
    text_align: str = "Left",
) -> None:
    set_textbox_text_runs(
        box,
        [(value, font_weight, font_size)],
        text_align=text_align,
    )


def set_text_runs(
    box: etree._Element,
    *,
    font_size: str | None = None,
    font_weight: str | None = None,
    color: str | None = None,
    font_family: str | None = None,
) -> None:
    for text_run in box.findall(".//r:TextRun", namespaces=NS):
        style_node = text_run.find("r:Style", namespaces=NS)
        if style_node is None:
            style_node = child(text_run, "Style")
        set_child_text(style_node, "FontFamily", font_family or BC_FONT_FAMILY)
        if font_size is not None:
            set_child_text(style_node, "FontSize", font_size)
        if font_weight is not None:
            set_child_text(style_node, "FontWeight", font_weight)
        if color is not None:
            set_child_text(style_node, "Color", color)


def set_textbox_padding(box: etree._Element, value: str) -> None:
    style_node = box.find("r:Style", namespaces=NS)
    if style_node is None:
        style_node = child(box, "Style")
    for padding in ("PaddingLeft", "PaddingRight", "PaddingTop", "PaddingBottom"):
        set_child_text(style_node, padding, value)


def set_textbox_border(
    box: etree._Element,
    style_value: str,
    *,
    width: str = "0.5pt",
    color: str = "#111111",
) -> None:
    style_node = box.find("r:Style", namespaces=NS)
    if style_node is None:
        style_node = child(box, "Style")
    border_node = style_node.find("r:Border", namespaces=NS)
    if border_node is None:
        border_node = child(style_node, "Border")
    set_child_text(border_node, "Style", style_value)
    if style_value != "None":
        set_child_text(border_node, "Width", width)
        set_child_text(border_node, "Color", color)


def clear_side_borders(box: etree._Element) -> None:
    style_node = box.find("r:Style", namespaces=NS)
    if style_node is None:
        return
    for border_name in ("TopBorder", "BottomBorder", "LeftBorder", "RightBorder"):
        node = style_node.find(f"r:{border_name}", namespaces=NS)
        if node is not None:
            style_node.remove(node)


def set_textbox_background(box: etree._Element, color: str | None) -> None:
    style_node = box.find("r:Style", namespaces=NS)
    if style_node is None:
        style_node = child(box, "Style")
    background = style_node.find("r:BackgroundColor", namespaces=NS)
    if color is None:
        if background is not None:
            style_node.remove(background)
        return
    if background is None:
        background = child(style_node, "BackgroundColor")
    background.text = color


def set_first_paragraph_alignment(box: etree._Element, alignment: str) -> None:
    paragraph_style = box.find(".//r:Paragraph/r:Style", namespaces=NS)
    if paragraph_style is None:
        paragraph = box.find(".//r:Paragraph", namespaces=NS)
        if paragraph is None:
            return
        paragraph_style = child(paragraph, "Style")
    set_child_text(paragraph_style, "TextAlign", alignment)


def remove_empty_tablix_rows(tablix: etree._Element) -> None:
    rows = tablix.find("r:TablixBody/r:TablixRows", namespaces=NS)
    members = tablix.find("r:TablixRowHierarchy/r:TablixMembers", namespaces=NS)
    if rows is None:
        return

    for index in range(len(rows) - 1, -1, -1):
        row = rows[index]
        values = [(value.text or "").strip() for value in row.findall(".//r:Value", namespaces=NS)]
        if values and all(value == "" for value in values):
            rows.remove(row)
            if members is not None and len(members) > index:
                members.remove(members[index])


def set_report_body_height(root: etree._Element, height: str) -> None:
    body = root.find(".//r:Body", namespaces=NS)
    if body is None:
        raise RuntimeError("Body not found")
    set_child_text(body, "Height", height)


def set_tablix_column_widths(tablix: etree._Element, widths: list[str]) -> None:
    columns = tablix.findall("r:TablixBody/r:TablixColumns/r:TablixColumn", namespaces=NS)
    if len(columns) != len(widths):
        raise RuntimeError(f"{tablix.get('Name')} column count mismatch")
    for column, width in zip(columns, widths):
        set_child_text(column, "Width", width)


def normalize_palette(root: etree._Element) -> None:
    for color in root.findall(".//r:Color", namespaces=NS):
        if color.text == "Blue":
            color.text = "#111111"
        elif color.text == "LightGrey":
            color.text = "#4D4D4D"


def update_issuer_block(root: etree._Element) -> None:
    ensure_embedded_image(root, "MTMLogixLogo", image_file_to_base64(LOGO_ASSET_PATH))
    report_items = report_body_items(root)

    for item in list(report_items):
        if item.get("Name") in {"Image7", "MTMLogixLogoImage"}:
            report_items.remove(item)

    report_items.append(image_item("MTMLogixLogoImage", "MTMLogixLogo", "0.56in", CONTENT_LEFT, "0.62in", "1.85in"))

    commercial_name = find_body_item(root, "Nombre_comercial")
    if commercial_name is not None:
        set_textbox_value(commercial_name, '=""')
        set_position(commercial_name, top="0.10in", left="0.25in", height="0.01in", width="0.01in")

    issuer = find_body_item(root, "Name")
    if issuer is None:
        raise RuntimeError("Name textbox not found")

    paragraphs = issuer.find("r:Paragraphs", namespaces=NS)
    if paragraphs is None:
        paragraphs = child(issuer, "Paragraphs")
    for node in list(paragraphs):
        paragraphs.remove(node)

    paragraphs.append(paragraph('=UCase(First(Fields!Name.Value, "DataSet_Result"))', size="8pt"))
    paragraphs.append(paragraph('=First(Fields!Company_NIT.Value, "DataSet_Result")', size="8pt"))
    paragraphs.append(paragraph('=UCase(First(Fields!Address.Value, "DataSet_Result"))', size="8pt"))
    paragraphs.append(paragraph('=UCase(First(Fields!Company_Address_2.Value, "DataSet_Result"))', size="8pt"))
    paragraphs.append(paragraph('=UCase(First(Fields!Company_City.Value, "DataSet_Result") & ", " & First(Fields!Company_Pais.Value, "DataSet_Result") & ", C.A.  CODIGO POSTAL: " & First(Fields!Company_Post_Code.Value, "DataSet_Result"))', size="8pt"))
    set_position(issuer, top="1.28in", left=CONTENT_LEFT, height="0.76in", width="3.55in")


def update_title_and_fel_box(root: etree._Element) -> None:
    report_items = report_body_items(root)
    for item in list(report_items):
        if item.get("Name") in {"Tablix1", "MTMInvoiceTitle", "MTMInvoiceSubtitle"}:
            report_items.remove(item)

    report_items.append(
        textbox(
            "MTMInvoiceTitle",
            "FACTURA ELECTRONICA",
            "0.58in",
            HEADER_SPLIT,
            "0.28in",
            HEADER_RIGHT_WIDTH,
            font_size="13pt",
            font_weight="Normal",
            text_align="Center",
        )
    )
    report_items.append(
        textbox(
            "MTMInvoiceSubtitle",
            "DOCUMENTO TRIBUTARIO ELECTRONICO",
            "0.92in",
            HEADER_SPLIT,
            "0.24in",
            HEADER_RIGHT_WIDTH,
            font_size="9.5pt",
            font_weight="Bold",
            text_align="Center",
        )
    )

    fel_box = find_body_item(root, "Tablix2")
    if fel_box is None:
        raise RuntimeError("Tablix2 not found")
    remove_empty_tablix_rows(fel_box)
    set_position(fel_box, top="1.25in", left="4.55in", height="0.90in", width="3.25in")
    set_border(fel_box, "Solid")
    set_border_width(fel_box, "0.5pt")
    for textbox_node in fel_box.findall(".//r:Textbox", namespaces=NS):
        set_border(textbox_node, "Solid")
        set_border_width(textbox_node, "0.5pt")
        set_text_runs(textbox_node, font_size="8pt", color="#111111")
        set_textbox_padding(textbox_node, "1.5pt")
    for row in fel_box.findall("r:TablixBody/r:TablixRows/r:TablixRow", namespaces=NS):
        set_child_text(row, "Height", "0.18in")

    serie_value = fel_box.find(".//r:Textbox[@Name='Textbox31']//r:Value", namespaces=NS)
    if serie_value is not None:
        serie_value.text = '=Left(First(Fields!Fiscal_Invoice_Number_PAC.Value, "DataSet_Result"), 8)'


def update_customer_block(root: etree._Element) -> None:
    box = root.find(".//r:Textbox[@Name='Bill_to_Name']", namespaces=NS)
    if box is None:
        raise RuntimeError("Bill_to_Name textbox not found")

    paragraphs = box.find("r:Paragraphs", namespaces=NS)
    if paragraphs is None:
        paragraphs = child(box, "Paragraphs")
    for node in list(paragraphs):
        paragraphs.remove(node)

    paragraphs.append(paragraph("FACTURAR A", size="8.5pt", weight="Normal"))
    paragraphs.append(paragraph('=UCase(First(Fields!Bill_to_Name.Value, "DataSet_Result"))', size="9.25pt", weight="Bold"))
    paragraphs.append(paragraph('=First(Fields!Curp.Value, "DataSet_Result")', size="8.5pt"))
    paragraphs.append(paragraph('=UCase(First(Fields!Bill_to_Address.Value, "DataSet_Result"))', size="8.5pt"))

    for tag, value in {
        "Top": "2.52in",
        "Left": CONTENT_LEFT,
        "Height": "1.00in",
        "Width": "3.55in",
    }.items():
        node = box.find(f"r:{tag}", namespaces=NS)
        if node is not None:
            node.text = value


def tablix_textbox(
    name: str,
    value: str,
    *,
    font_size: str = "8pt",
    font_weight: str = "Normal",
    text_align: str = "Left",
    background: str | None = None,
    can_grow: bool = True,
    padding: str = "1.5pt",
) -> etree._Element:
    box = etree.Element(qn("Textbox"), Name=name)
    child(box, "CanGrow", "true" if can_grow else "false")
    child(box, "KeepTogether", "true")
    paragraphs = child(box, "Paragraphs")
    paragraph_node = child(paragraphs, "Paragraph")
    text_runs = child(paragraph_node, "TextRuns")
    text_run = child(text_runs, "TextRun")
    child(text_run, "Value", value)
    style(
        text_run,
        {
            "FontSize": font_size,
            "FontWeight": font_weight,
            "Color": TEXT_COLOR,
            "FontFamily": BC_FONT_FAMILY,
        },
    )
    style(paragraph_node, {"TextAlign": text_align})
    etree.SubElement(box, rd_qn("DefaultName")).text = name
    set_textbox_border(box, "Solid", width="0.5pt", color=TEXT_COLOR)
    set_textbox_padding(box, padding)
    if background is not None:
        set_textbox_background(box, background)
    return box


def add_tablix_cell(row: etree._Element, box: etree._Element | None, colspan: int | None = None) -> None:
    cell = child(row.find("r:TablixCells", namespaces=NS), "TablixCell")
    if box is None and colspan is None:
        return
    contents = child(cell, "CellContents")
    if box is not None:
        contents.append(box)
    if colspan is not None:
        child(contents, "ColSpan", str(colspan))


def shipment_tablix() -> etree._Element:
    table = etree.Element(qn("Tablix"), Name="MTMShipmentInfoGrid")
    body = child(table, "TablixBody")
    columns = child(body, "TablixColumns")
    child(child(columns, "TablixColumn"), "Width", "0.90in")
    child(child(columns, "TablixColumn"), "Width", "2.35in")
    rows = child(body, "TablixRows")

    shipment_rows = [
        ("MTMShipmentPO", "PO:", '=First(Fields!MTM_PO_Number.Value, "DataSet_Result")', "0.17in", "7.7pt"),
        (
            "MTMShipmentBooking",
            '=First(Fields!MTM_Booking_Label.Value, "DataSet_Result")',
            '=First(Fields!MTM_Booking.Value, "DataSet_Result")',
            "0.17in",
            "7.7pt",
        ),
        (
            "MTMShipmentContainers",
            '=First(Fields!MTM_Containers_Label.Value, "DataSet_Result")',
            '=First(Fields!MTM_Containers.Value, "DataSet_Result")',
            "0.56in",
            "6.3pt",
        ),
    ]
    for name, label, value, height, font_size in shipment_rows:
        row = child(rows, "TablixRow")
        child(row, "Height", height)
        child(row, "TablixCells")
        add_tablix_cell(
            row,
            tablix_textbox(
                f"{name}Label",
                label,
                font_size=font_size,
                font_weight="Bold",
                can_grow=False,
                padding="1pt",
            ),
        )
        add_tablix_cell(
            row,
            tablix_textbox(
                f"{name}Value",
                value or "",
                font_size=font_size,
                can_grow=False,
                padding="1pt",
            ),
        )

    column_hierarchy = child(table, "TablixColumnHierarchy")
    column_members = child(column_hierarchy, "TablixMembers")
    child(column_members, "TablixMember")
    child(column_members, "TablixMember")
    row_hierarchy = child(table, "TablixRowHierarchy")
    row_members = child(row_hierarchy, "TablixMembers")
    for _ in shipment_rows:
        child(row_members, "TablixMember")

    child(table, "Top", "2.78in")
    child(table, "Left", "4.55in")
    child(table, "Height", "0.90in")
    child(table, "Width", "3.25in")
    child(table, "ZIndex", "6")
    style_node = child(table, "Style")
    border_node = child(style_node, "Border")
    child(border_node, "Style", "Solid")
    child(border_node, "Width", "0.5pt")
    child(border_node, "Color", TEXT_COLOR)
    return table


def update_shipment_block(root: etree._Element) -> None:
    report_items = report_body_items(root)
    for item in list(report_items):
        if item.get("Name") in {"MTMShipmentInfoBox", "MTMShipmentInfoGrid", "MTMShipmentInfoTitle"}:
            report_items.remove(item)

    report_items.append(
        textbox(
            "MTMShipmentInfoTitle",
            "INFORMACION DE EMBARQUE",
            "2.46in",
            "4.55in",
            "0.24in",
            "3.25in",
            font_size="9.5pt",
            font_weight="Bold",
            text_align="Center",
        )
    )
    report_items.append(shipment_tablix())


def remove_payment_footer(root: etree._Element) -> None:
    markers = ("Banco:", "Cuenta No.", "A nombre de:", "Realizar pagos")
    report_items = root.find(".//r:Body/r:ReportItems", namespaces=NS)
    if report_items is None:
        return
    for item in list(report_items):
        values = [v.text or "" for v in item.findall(".//r:Value", namespaces=NS)]
        if any(marker in value for marker in markers for value in values):
            report_items.remove(item)


def remove_invoice_watermark(root: etree._Element) -> None:
    report_items = report_body_items(root)

    for item in list(report_items):
        if item.get("Name") in {
            "MTMInvoiceWatermarkImage",
        }:
            report_items.remove(item)


def fiscal_textbox(name: str, runs: list[tuple[str, str] | tuple[str, str, str]], top: str, left: str, height: str, width: str) -> etree._Element:
    box = textbox(name, "", top, left, height, width, font_size="7.5pt")
    set_textbox_text_runs(box, runs)
    set_textbox_border(box, "None")
    set_textbox_padding(box, "1pt")
    return box


def remove_body_fiscal_certification_block(root: etree._Element) -> None:
    report_items = report_body_items(root)
    for item in list(report_items):
        if item.get("Name") in {
            "Textbox38",
            "Textbox39",
            "Date_Time_Stamped",
            "MTMFiscalCertificationBox",
            "MTMFELBadge",
            "MTMCertifierQRPlaceholder",
            "MTMCertifierQRCaption",
            "MTMCertifierQRImage",
            "MTMFiscalPageNo",
        }:
            report_items.remove(item)


def fiscal_certification_box(top: str = "0.00in") -> etree._Element:
    box = rectangle_item("MTMFiscalCertificationBox", top, CONTENT_LEFT, "0.78in", CONTENT_WIDTH)
    box_items = box.find("r:ReportItems", namespaces=NS)
    if box_items is None:
        raise RuntimeError("MTMFiscalCertificationBox report items not found")

    box_items.append(
        textbox(
            "MTMFiscalTitle",
            "INFORMACION FISCAL",
            "0.05in",
            "0.10in",
            "0.18in",
            "2.10in",
            font_size="8.5pt",
            font_weight="Bold",
        )
    )
    box_items.append(
        fiscal_textbox(
            "MTMFiscalAuthorization",
            [
                ("Numero de Autorizacion: ", "Bold", "7.5pt"),
                ('=First(Fields!Fiscal_Invoice_Number_PAC.Value, "DataSet_Result")', "Normal", "7.5pt"),
            ],
            "0.24in",
            "0.10in",
            "0.16in",
            "4.95in",
        )
    )
    box_items.append(
        fiscal_textbox(
            "MTMFiscalCertificationDate",
            [
                ("Fecha de Certificacion: ", "Bold", "7.5pt"),
                ('=First(Fields!Date_Time_Stamped.Value, "DataSet_Result")', "Normal", "7.5pt"),
            ],
            "0.40in",
            "0.10in",
            "0.16in",
            "4.95in",
        )
    )
    box_items.append(
        fiscal_textbox(
            "MTMFiscalCertifier",
            [
                ("Certificador: ", "Bold", "7.5pt"),
                ('=IIF(Len(First(Fields!MTM_FEL_QR_Code.Value, "DataSet_Result")) = 0, "Pendiente de certificacion FEL", "INFILE / FEL")', "Normal", "7.5pt"),
            ],
            "0.56in",
            "0.10in",
            "0.16in",
            "4.95in",
        )
    )
    box_items.append(image_item("MTMFELBadge", "MTMFELBadgeImageData", "0.12in", "5.52in", "0.46in", "0.58in"))
    box_items.append(
        database_image_item(
            "MTMCertifierQRImage",
            '=System.Convert.FromBase64String(First(Fields!MTM_FEL_QR_Code.Value, "DataSet_Result"))',
            "image/png",
            "0.10in",
            "6.24in",
            "0.54in",
            "0.54in",
        )
    )
    box_items.append(
        textbox(
            "MTMCertifierQRCaption",
            "VALIDACION FEEL",
            "0.65in",
            "5.72in",
            "0.13in",
            "1.60in",
            font_size="6.5pt",
            font_weight="Bold",
            text_align="Center",
        )
    )
    return box


def update_fiscal_certification_block(root: etree._Element) -> None:
    ensure_embedded_image(root, "MTMFELBadgeImageData", build_fel_badge_png())
    remove_body_fiscal_certification_block(root)


def update_page_footer(root: etree._Element) -> None:
    page = root.find(".//r:Page", namespaces=NS)
    if page is None:
        raise RuntimeError("Page node not found")

    for existing in page.findall("r:PageFooter", namespaces=NS):
        page.remove(existing)

    footer = etree.Element(qn("PageFooter"))
    child(footer, "Height", "1.02in")
    child(footer, "PrintOnFirstPage", "true")
    child(footer, "PrintOnLastPage", "true")
    footer_items = child(footer, "ReportItems")
    footer_items.append(fiscal_certification_box("0.00in"))
    footer_items.append(
        textbox(
            "MTMFiscalPageNo",
            '="PAGINA " & Globals!PageNumber & " DE " & Globals!TotalPages',
            "0.86in",
            "0.48in",
            "0.14in",
            "0.90in",
            font_size="6.75pt",
            font_weight="Normal",
            text_align="Left",
        )
    )
    style(footer, {})

    page.insert(0, footer)


def add_section_lines(root: etree._Element) -> None:
    report_items = report_body_items(root)
    for item in list(report_items):
        name = item.get("Name") or ""
        if name.startswith("MTMInvoiceLine") or name == "Line1":
            report_items.remove(item)

    lines = [
        ("MTMInvoiceLineTop", PAGE_TOP, PAGE_LEFT, "0in", PAGE_WIDTH),
        ("MTMInvoiceLineLeft", PAGE_TOP, PAGE_LEFT, PAGE_FRAME_HEIGHT, "0in"),
        ("MTMInvoiceLineRight", PAGE_TOP, PAGE_RIGHT, PAGE_FRAME_HEIGHT, "0in"),
        ("MTMInvoiceLineBottom", PAGE_BOTTOM, PAGE_LEFT, "0in", PAGE_WIDTH),
        ("MTMInvoiceLineHeaderBottom", "2.35in", PAGE_LEFT, "0in", PAGE_WIDTH),
        ("MTMInvoiceLineHeaderSplit", PAGE_TOP, HEADER_SPLIT, "1.96in", "0in"),
        ("MTMInvoiceLineCustomerBottom", "3.68in", PAGE_LEFT, "0in", PAGE_WIDTH),
        ("MTMInvoiceLineCustomerSplit", "2.35in", HEADER_SPLIT, "1.33in", "0in"),
    ]
    for args in lines:
        line = line_item(*args)
        set_border_width(line, "0.5pt")
        report_items.append(line)


def update_positions_and_styles(root: etree._Element) -> None:
    positions = {
        "Line1": {"top": "3.68in", "left": PAGE_LEFT, "width": PAGE_WIDTH},
        "Tablix5": {"top": "3.88in", "left": CONTENT_LEFT, "width": CONTENT_WIDTH},
        "Tablix3": {"top": "7.22in", "left": CONTENT_LEFT, "width": CONTENT_WIDTH},
    }
    for name, pos in positions.items():
        item = find_body_item(root, name)
        if item is not None:
            set_position(item, **pos)

    for tablix_name in ("Tablix5", "Tablix3"):
        item = find_body_item(root, tablix_name)
        if item is None:
            continue
        if tablix_name == "Tablix5":
            set_tablix_column_widths(item, ["0.92in", "3.63in", "1.75in", "1.20in"])
        elif tablix_name == "Tablix3":
            set_tablix_column_widths(item, ["2.04in", "2.63in", "1.72in", "1.11in"])
        for textbox_node in item.findall(".//r:Textbox", namespaces=NS):
            set_text_runs(textbox_node, font_size="8.5pt", color=TEXT_COLOR)
            set_textbox_padding(textbox_node, "1.5pt")


def update_line_items_table(root: etree._Element) -> None:
    table = find_body_item(root, "Tablix5")
    if table is None:
        raise RuntimeError("Tablix5 not found")

    set_border(table, "Solid")
    set_border_width(table, "0.5pt")
    set_tablix_column_widths(table, ["0.92in", "3.63in", "1.75in", "1.20in"])

    header_names = {"Textbox54", "Textbox56", "Textbox60", "Textbox62"}
    for textbox_node in table.findall(".//r:Textbox", namespaces=NS):
        clear_side_borders(textbox_node)
        set_textbox_border(textbox_node, "Solid", width="0.5pt", color="#111111")
        set_text_runs(textbox_node, font_size="7.5pt", color=TEXT_COLOR)
        set_textbox_padding(textbox_node, "2pt")

        if textbox_node.get("Name") in header_names:
            set_textbox_background(textbox_node, "#C7C7C7")
            set_text_runs(textbox_node, font_size="8pt", color=TEXT_COLOR)
        else:
            set_textbox_background(textbox_node, "White")
            set_child_text(textbox_node, "CanGrow", "false")
            set_child_text(textbox_node, "KeepTogether", "true")

        if textbox_node.get("Name") == "Description":
            set_text_runs(textbox_node, font_size="7.25pt", color=TEXT_COLOR)
            set_textbox_padding(textbox_node, "1.5pt")

    for row in table.findall("r:TablixBody/r:TablixRows/r:TablixRow", namespaces=NS):
        if row.find(".//r:Textbox[@Name='Description']", namespaces=NS) is not None:
            set_child_text(row, "Height", "0.36in")
        else:
            set_child_text(row, "Height", "0.23in")

    money_expressions = {
        "Amount_Including_VAT": '=Fields!Divisa.Value & " " & Format(Fields!Unit_Price.Value, "#,##0.00")',
        "UnitarioTotal": '=Fields!Divisa.Value & " " & Format(Fields!Quantity.Value * Fields!Unit_Price.Value, "#,##0.00")',
    }
    for name, expression in money_expressions.items():
        money_box = table.find(f".//r:Textbox[@Name='{name}']", namespaces=NS)
        if money_box is not None:
            set_textbox_single_run(money_box, expression, font_size="7.5pt", text_align="Right")


def update_settlement_band(root: etree._Element) -> None:
    table = find_body_item(root, "Tablix3")
    if table is None:
        raise RuntimeError("Tablix3 not found")

    set_position(table, top="7.22in", left=CONTENT_LEFT, height="0.86in", width=CONTENT_WIDTH)
    set_tablix_column_widths(table, ["2.35in", "2.25in", "1.40in", "1.50in"])
    set_border(table, "Solid")
    set_border_width(table, "0.5pt")

    rows_parent = table.find("r:TablixBody/r:TablixRows", namespaces=NS)
    members_parent = table.find("r:TablixRowHierarchy/r:TablixMembers", namespaces=NS)
    if rows_parent is None:
        raise RuntimeError("Tablix3 rows not found")

    while len(rows_parent) > 3:
        rows_parent.remove(rows_parent[-1])
        if members_parent is not None and len(members_parent):
            members_parent.remove(members_parent[-1])

    row_heights = ["0.22in", "0.22in", "0.32in"]
    rows = table.findall("r:TablixBody/r:TablixRows/r:TablixRow", namespaces=NS)
    for row, height in zip(rows, row_heights):
        set_child_text(row, "Height", height)

    first_row_cells = rows[0].findall("r:TablixCells/r:TablixCell", namespaces=NS) if rows else []
    if len(first_row_cells) >= 2:
        first_contents = first_row_cells[0].find("r:CellContents", namespaces=NS)
        if first_contents is not None and first_contents.find("r:ColSpan", namespaces=NS) is None:
            child(first_contents, "ColSpan", "2")
        for node in list(first_row_cells[1]):
            first_row_cells[1].remove(node)

    left_names = {"Textbox17", "Textbox14", "Textbox10"}
    total_label_names = {"Textbox41", "Textbox42", "Textbox43"}
    total_value_names = {"Textbox19", "Textbox16", "Textbox13"}
    final_names = {"Textbox43", "Textbox13"}

    for textbox_node in table.findall(".//r:Textbox", namespaces=NS):
        clear_side_borders(textbox_node)
        set_textbox_border(textbox_node, "Solid", width="0.5pt", color=TEXT_COLOR)
        set_textbox_padding(textbox_node, "2pt")
        set_textbox_background(textbox_node, "White")
        set_text_runs(textbox_node, font_size="8pt", color=TEXT_COLOR)

        name = textbox_node.get("Name")
        if name in left_names:
            set_first_paragraph_alignment(textbox_node, "Left")
        if name in total_label_names:
            set_first_paragraph_alignment(textbox_node, "Center")
        if name in total_value_names:
            set_first_paragraph_alignment(textbox_node, "Right")
        if name in {"Textbox10", "Textbox43"}:
            set_text_runs(textbox_node, font_size="8pt", font_weight="Bold", color=TEXT_COLOR)
        if name in final_names:
            set_textbox_background(textbox_node, "#EDEDED")
            set_text_runs(textbox_node, font_size="8.25pt", font_weight="Bold", color=TEXT_COLOR)

    total_in_words = table.find(".//r:Textbox[@Name='Textbox10']", namespaces=NS)
    if total_in_words is not None:
        set_textbox_text_runs(
            total_in_words,
            [
                ("TOTAL EN LETRA: ", "Bold"),
                ('=First(Fields!TotalLetra.Value, "DataSet_Result")', "Normal"),
            ],
        )

    # Bind the ISR disclaimer to the report dataset so INT/NAT account prefixes control it.
    disclaimer = table.find(".//r:Textbox[@Name='Textbox17']", namespaces=NS)
    if disclaimer is not None:
        set_textbox_value(disclaimer, '=First(Fields!MTM_ISR_Comment.Value, "DataSet_Result")')
        set_text_runs(disclaimer, font_size="7.75pt", font_weight="Normal", color=TEXT_COLOR)

    money_expressions = {
        "Textbox19": '=First(Fields!Divisa.Value, "DataSet_Result") & " " & Format(First(Fields!MontoTotalSinIva.Value, "DataSet_Result"), "#,##0.00")',
        "Textbox16": '=First(Fields!Divisa.Value, "DataSet_Result") & " " & Format(First(Fields!MontoIVA.Value, "DataSet_Result"), "#,##0.00")',
        "Textbox13": '=First(Fields!Divisa.Value, "DataSet_Result") & " " & Format(First(Fields!TotalConIVA.Value, "DataSet_Result"), "#,##0.00")',
    }
    for name, expression in money_expressions.items():
        money_box = table.find(f".//r:Textbox[@Name='{name}']", namespaces=NS)
        if money_box is not None:
            weight = "Bold" if name == "Textbox13" else "Normal"
            set_textbox_single_run(money_box, expression, font_size="8.25pt", font_weight=weight, text_align="Right")


def update_static_text(root: etree._Element) -> None:
    replacements = {
        "FACTRURA A": "FACTURAR A",
        "Factura Electrónica": "FACTURA ELECTRONICA",
        "DOCUMENTO TRIBUTARIO ELECTRÓNICO": "DOCUMENTO TRIBUTARIO ELECTRONICO",
        "Informacion Fiscal": "INFORMACION FISCAL",
    }
    for value in root.findall(".//r:Value", namespaces=NS):
        if value.text in replacements:
            value.text = replacements[value.text]


def update_dataset_bindings(root: etree._Element) -> None:
    ensure_dataset_field(root, "MTM_Line_Description")
    ensure_dataset_field(root, "MTM_Invoice_Date_Text")

    description_box = root.find(".//r:Textbox[@Name='Description']", namespaces=NS)
    if description_box is not None:
        set_textbox_value(description_box, "=Fields!MTM_Line_Description.Value")

    date_box = root.find(".//r:Textbox[@Name='Textbox27']", namespaces=NS)
    if date_box is not None:
        set_textbox_value(date_box, '=First(Fields!MTM_Invoice_Date_Text.Value, "DataSet_Result")')


def build(input_path: Path, output_path: Path) -> None:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    root = etree.parse(str(input_path), parser).getroot()

    ensure_dataset_field(root, "MTM_FEL_QR_Code")
    ensure_dataset_field(root, "MTM_PO_Number")
    ensure_dataset_field(root, "MTM_Booking_Label")
    ensure_dataset_field(root, "MTM_Booking")
    ensure_dataset_field(root, "MTM_Containers_Label")
    ensure_dataset_field(root, "MTM_Containers")
    ensure_dataset_field(root, "MTM_Line_Description")
    ensure_dataset_field(root, "MTM_Invoice_Date_Text")
    set_report_body_height(root, "9.60in")
    normalize_palette(root)
    update_issuer_block(root)
    update_title_and_fel_box(root)
    update_static_text(root)
    update_dataset_bindings(root)
    update_customer_block(root)
    update_shipment_block(root)
    update_positions_and_styles(root)
    update_line_items_table(root)
    update_settlement_band(root)
    update_fiscal_certification_block(root)
    update_page_footer(root)
    add_section_lines(root)
    remove_payment_footer(root)
    remove_invoice_watermark(root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(root).write(
        str(output_path),
        pretty_print=True,
        xml_declaration=True,
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_mtm_gt_invoice_rdl.py INPUT.rdl OUTPUT.rdl")
        return 2
    build(Path(sys.argv[1]), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
