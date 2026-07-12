#!/usr/bin/env python3
"""Build the MTM Guatemala Word layout from BC report 1306 standard DOCX."""

from __future__ import annotations

import copy
import os
import random
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
W = NS["w"]
XML = NS["xml"]
REPORT_TAG = "#Nav: Standard_Sales_Invoice/1306"
PREFIX_MAPPINGS = (
    "xmlns:ns0='urn:microsoft-dynamics-nav/reports/Standard_Sales_Invoice/1306/'"
)


def qn(name: str) -> str:
    return f"{{{W}}}{name}"


def xml_qn(name: str) -> str:
    return f"{{{XML}}}{name}"


def text_of(element: etree._Element) -> str:
    return "".join(t.text or "" for t in element.xpath(".//w:t", namespaces=NS))


def sdt_alias(sdt: etree._Element) -> str:
    alias = sdt.find("./w:sdtPr/w:alias", namespaces=NS)
    return alias.get(qn("val"), "") if alias is not None else ""


def sdt_xpath(sdt: etree._Element) -> str:
    binding = sdt.find("./w:sdtPr/w:dataBinding", namespaces=NS)
    return binding.get(qn("xpath"), "") if binding is not None else ""


def find_sdt(root: etree._Element, field_name: str) -> etree._Element:
    suffix = f"/Header/{field_name}"
    for sdt in root.xpath(".//w:sdt", namespaces=NS):
        if sdt_alias(sdt).endswith(suffix) or sdt_xpath(sdt).endswith(
            f"/ns0:{field_name}[1]"
        ):
            return sdt
    raise ValueError(f"Unable to find content control for {field_name}")


def set_all_text(element: etree._Element, value: str) -> None:
    text_nodes = element.xpath(".//w:t", namespaces=NS)
    if not text_nodes:
        raise ValueError("Cannot set text on element without w:t")
    text_nodes[0].text = value
    if value[:1].isspace() or value[-1:].isspace():
        text_nodes[0].set(xml_qn("space"), "preserve")
    for node in text_nodes[1:]:
        node.text = ""


def make_static_sdt(sdt: etree._Element, value: str) -> None:
    """Keep the visible control but stop BC from overwriting this static label."""
    pr = sdt.find("./w:sdtPr", namespaces=NS)
    if pr is not None:
        for binding in pr.xpath("./w:dataBinding", namespaces=NS):
            pr.remove(binding)
        tag = pr.find("./w:tag", namespaces=NS)
        if tag is not None:
            tag.set(qn("val"), "")
        alias = pr.find("./w:alias", namespaces=NS)
        if alias is not None:
            alias.set(qn("val"), value)
    set_all_text(sdt, value)


def next_sdt_id(root: etree._Element) -> str:
    seen = {
        int(node.get(qn("val")))
        for node in root.xpath(".//w:sdtPr/w:id", namespaces=NS)
        if node.get(qn("val"), "").lstrip("-").isdigit()
    }
    while True:
        candidate = random.randint(-2_000_000_000, -1)
        if candidate not in seen:
            return str(candidate)


def clone_bound_sdt(
    template: etree._Element, root: etree._Element, field_name: str
) -> etree._Element:
    sdt = copy.deepcopy(template)
    pr = sdt.find("./w:sdtPr", namespaces=NS)
    if pr is None:
        raise ValueError("Template content control has no properties")

    alias = pr.find("./w:alias", namespaces=NS)
    if alias is None:
        alias = etree.SubElement(pr, qn("alias"))
    alias.set(qn("val"), f"#Nav: /Header/{field_name}")

    tag = pr.find("./w:tag", namespaces=NS)
    if tag is None:
        tag = etree.SubElement(pr, qn("tag"))
    tag.set(qn("val"), REPORT_TAG)

    sdt_id = pr.find("./w:id", namespaces=NS)
    if sdt_id is None:
        sdt_id = etree.SubElement(pr, qn("id"))
    sdt_id.set(qn("val"), next_sdt_id(root))

    binding = pr.find("./w:dataBinding", namespaces=NS)
    if binding is None:
        binding = etree.SubElement(pr, qn("dataBinding"))
    binding.set(qn("prefixMappings"), PREFIX_MAPPINGS)
    binding.set(
        qn("xpath"),
        f"/ns0:NavWordReportXmlPart[1]/ns0:Header[1]/ns0:{field_name}[1]",
    )

    set_all_text(sdt, field_name)
    return sdt


def make_run(text: str, *, bold: bool = False) -> etree._Element:
    run = etree.Element(qn("r"))
    if bold:
        rpr = etree.SubElement(run, qn("rPr"))
        etree.SubElement(rpr, qn("b"))
        etree.SubElement(rpr, qn("bCs"))
    t = etree.SubElement(run, qn("t"))
    if text[:1].isspace() or text[-1:].isspace():
        t.set(xml_qn("space"), "preserve")
    t.text = text
    return run


def make_paragraph(
    ppr_template: etree._Element | None, children: list[etree._Element]
) -> etree._Element:
    paragraph = etree.Element(qn("p"))
    if ppr_template is not None:
        paragraph.append(copy.deepcopy(ppr_template))
    for child in children:
        paragraph.append(child)
    return paragraph


def clear_to_tcpr(cell: etree._Element) -> None:
    for child in list(cell):
        if child.tag != qn("tcPr"):
            cell.remove(child)


def make_cell(
    template_cell: etree._Element,
    paragraph: etree._Element,
) -> etree._Element:
    cell = copy.deepcopy(template_cell)
    clear_to_tcpr(cell)
    cell.append(paragraph)
    return cell


def content_cell_from_sdt(sdt: etree._Element) -> etree._Element:
    cell = sdt.find("./w:sdtContent/w:tc", namespaces=NS)
    if cell is None:
        raise ValueError("Expected table-cell content control")
    return cell


def first_paragraph(cell: etree._Element) -> etree._Element:
    paragraph = cell.find("./w:p", namespaces=NS)
    if paragraph is None:
        raise ValueError("Expected a paragraph in table cell")
    return paragraph


def update_document_xml(root: etree._Element) -> None:
    customer_cell_template = content_cell_from_sdt(find_sdt(root, "CustomerAddress1"))
    company_cell_template = content_cell_from_sdt(find_sdt(root, "CompanyAddress1"))
    customer_ppr = first_paragraph(customer_cell_template).find(
        "./w:pPr", namespaces=NS
    )
    company_ppr = first_paragraph(company_cell_template).find("./w:pPr", namespaces=NS)

    vat_template = find_sdt(root, "CompanyLegalOffice")
    customer_nit = clone_bound_sdt(vat_template, root, "VATRegistrationNo")
    company_nit = clone_bound_sdt(vat_template, root, "CompanyVATRegistrationNo")

    address_table = root.find(".//w:body/w:tbl", namespaces=NS)
    if address_table is None:
        raise ValueError("Unable to find address table")
    rows = address_table.findall("./w:tr", namespaces=NS)
    if not rows:
        raise ValueError("Address table has no rows")

    label_row = etree.Element(qn("tr"))
    trpr = rows[0].find("./w:trPr", namespaces=NS)
    if trpr is not None:
        label_row.append(copy.deepcopy(trpr))
    label_row.append(
        make_cell(
            customer_cell_template,
            make_paragraph(customer_ppr, [make_run("FACTURAR A", bold=True)]),
        )
    )
    label_row.append(
        make_cell(company_cell_template, make_paragraph(company_ppr, [make_run("")]))
    )
    address_table.insert(address_table.index(rows[0]), label_row)

    nit_row = etree.Element(qn("tr"))
    if trpr is not None:
        nit_row.append(copy.deepcopy(trpr))
    nit_row.append(
        make_cell(
            customer_cell_template,
            make_paragraph(
                customer_ppr,
                [make_run("NIT: ", bold=True), customer_nit],
            ),
        )
    )
    nit_row.append(
        make_cell(
            company_cell_template,
            make_paragraph(
                company_ppr,
                [make_run("NIT: ", bold=True), company_nit],
            ),
        )
    )
    address_table.insert(address_table.index(rows[-1]) + 1, nit_row)

    body = root.find(".//w:body", namespaces=NS)
    if body is None:
        raise ValueError("Unable to find document body")
    for child in list(body):
        if "PaymentServiceText_Url" in text_of(child):
            body.remove(child)


def update_header_xml(root: etree._Element) -> None:
    try:
        title = find_sdt(root, "DocumentTitle_Lbl")
    except ValueError:
        return
    make_static_sdt(title, "Factura Electrónica")


def update_footer_xml(root: etree._Element) -> None:
    for field in ("CompanyVATRegistrationNo_Lbl", "CompanyVATRegNo_Lbl"):
        try:
            make_static_sdt(find_sdt(root, field), "NIT:")
        except ValueError:
            pass

    for table in root.xpath(".//w:tbl", namespaces=NS):
        for row in list(table.findall("./w:tr", namespaces=NS)):
            row_text = text_of(row)
            if any(
                marker in row_text
                for marker in (
                    "CompanyBank",
                    "CompanyIBAN",
                    "CompanySWIFT",
                    "CompanyGiro",
                    "CompanyCustomGiro",
                )
            ):
                table.remove(row)


def write_modified_docx(input_path: Path, output_path: Path) -> None:
    replacements: dict[str, bytes] = {}
    with ZipFile(input_path, "r") as zin:
        for part_name in (
            "word/document.xml",
            "word/header1.xml",
            "word/header2.xml",
            "word/header3.xml",
            "word/footer1.xml",
            "word/footer2.xml",
            "word/footer3.xml",
        ):
            if part_name not in zin.namelist():
                continue
            parser = etree.XMLParser(remove_blank_text=False)
            root = etree.fromstring(zin.read(part_name), parser)
            if part_name == "word/document.xml":
                update_document_xml(root)
            elif part_name.startswith("word/header"):
                update_header_xml(root)
            elif part_name.startswith("word/footer"):
                update_footer_xml(root)
            replacements[part_name] = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=False
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = replacements.get(item.filename)
                if data is None:
                    data = zin.read(item.filename)
                zout.writestr(item, data)
        os.replace(tmp_path, output_path)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_gt_sales_invoice_layout_docx.py INPUT.docx OUTPUT.docx")
        return 2
    write_modified_docx(Path(sys.argv[1]), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
