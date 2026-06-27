from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from business_central_client.client import BusinessCentralClient
from business_central_client.config import Settings as BusinessCentralSettings
from clickup_integration.client import ClickUpClient
from clickup_integration.config import ClickUpSettings
from clickup_integration.invoice_sync import (
    InvoiceAutomationSettings,
    prepare_clickup_bc_sales_invoice_preview,
)
from clickup_integration.mapping import summarize_task_for_customer_mapping


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local HTML/JSON model invoice preview for an AIR shipment without writing to BC or ClickUp."
    )
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--team-id", default="8451352")
    parser.add_argument("--custom-task-ids", action="store_true", default=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output/air_invoice_model"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()

    if args.env_file.exists():
        load_dotenv(args.env_file)

    clickup = ClickUpClient(ClickUpSettings.from_env())
    task = clickup.get_task(args.task_id, custom_task_ids=args.custom_task_ids, team_id=args.team_id)
    summary = summarize_task_for_customer_mapping(task)

    invoice_settings = InvoiceAutomationSettings.from_env()
    summary = force_ready_status_for_preview(summary, invoice_settings)

    bc_client = BusinessCentralClient(BusinessCentralSettings.from_env())
    preview = prepare_clickup_bc_sales_invoice_preview(
        clickup_summary=summary,
        bc_client=bc_client,
        settings=invoice_settings,
    )
    customer_cards = load_customer_cards_for_preview(preview, bc_client)

    output_dir = args.output_dir / str(summary.get("custom_id") or args.task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "preview.json"
    json_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")

    html_paths = []
    for invoice in preview.get("proposed_bc_invoices") or []:
        group = str(invoice.get("invoice_group") or "invoice").upper()
        html_path = output_dir / f"{summary.get('custom_id') or args.task_id}-{group}-air-model.html"
        html_path.write_text(
            render_invoice_html(summary, preview, invoice, customer_cards=customer_cards),
            encoding="utf-8",
        )
        html_paths.append(str(html_path))

    index_path = output_dir / "index.html"
    index_path.write_text(render_index_html(summary, preview, html_paths), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": preview.get("status"),
                "task": summary.get("custom_id") or args.task_id,
                "product_validation": preview.get("product_validation"),
                "shipment_metadata": preview.get("shipment_metadata"),
                "preview_json": str(json_path),
                "index_html": str(index_path),
                "invoice_html": html_paths,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def force_ready_status_for_preview(
    summary: dict[str, Any],
    settings: InvoiceAutomationSettings,
) -> dict[str, Any]:
    forced = {**summary, "status": settings.ready_status}
    for field in forced.get("custom_fields", {}).values():
        if field.get("id") in settings.invoice_status_field_ids:
            ready_option_id = _dropdown_option_id(field, settings.ready_status)
            if ready_option_id is not None:
                field["value"] = ready_option_id
    return forced


def _dropdown_option_id(field: dict[str, Any], option_name: str) -> str | int | None:
    normalized_target = option_name.strip().lower()
    for option in (field.get("type_config") or {}).get("options") or []:
        if str(option.get("name") or "").strip().lower() == normalized_target:
            return option.get("orderindex") if option.get("orderindex") is not None else option.get("id")
    return None


def load_customer_cards_for_preview(
    preview: dict[str, Any],
    bc_client: BusinessCentralClient,
) -> dict[str, dict[str, Any]]:
    market = str(preview.get("market") or "GT").strip().upper() or "GT"
    cards: dict[str, dict[str, Any]] = {}
    for invoice in preview.get("proposed_bc_invoices") or []:
        payload = invoice.get("proposed_bc_payload") or {}
        customer_id = str(payload.get("customerId") or "").strip()
        customer_number = str(payload.get("customerNumber") or "").strip()
        cache_key = customer_id or customer_number
        if not cache_key or cache_key in cards:
            continue
        try:
            if customer_id:
                card = bc_client.get_customer_by_id(customer_id, market=market)
            else:
                card = resolve_customer_card_by_number(bc_client, customer_number, market=market)
        except Exception as exc:  # pragma: no cover - diagnostic value is rendered locally.
            card = {
                "number": customer_number,
                "id": customer_id,
                "displayName": "CLIENTE NO DISPONIBLE EN PREVIEW LOCAL",
                "preview_error": str(exc),
            }
        cards[cache_key] = card or {}
        if customer_id:
            cards[customer_id] = cards[cache_key]
        if customer_number:
            cards[customer_number] = cards[cache_key]
    return cards


def resolve_customer_card_by_number(
    bc_client: BusinessCentralClient,
    customer_number: str,
    *,
    market: str,
) -> dict[str, Any] | None:
    escaped = customer_number.replace("'", "''")
    rows = bc_client.find_entities("customers", filters=f"number eq '{escaped}'", top=2, market=market)
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError(f"More than one Business Central customer matched {customer_number}.")
    return rows[0]


def render_index_html(summary: dict[str, Any], preview: dict[str, Any], html_paths: list[str]) -> str:
    links = "\n".join(
        f'<li><a href="{html.escape(Path(path).name)}">{html.escape(Path(path).name)}</a></li>'
        for path in html_paths
    )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{esc(summary.get("custom_id"))} Air Invoice Model</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <main class="page">
    <h1>MODELO LOCAL DE FACTURA AIR</h1>
    <p class="muted">Este preview no crea, publica, timbra, envia ni sube facturas.</p>
    <dl class="summary">
      <dt>Tarea</dt><dd>{esc(summary.get("custom_id"))}</dd>
      <dt>Shipment</dt><dd>{esc(summary.get("name"))}</dd>
      <dt>Estado preview</dt><dd>{esc(preview.get("status"))}</dd>
      <dt>Validacion producto</dt><dd>{esc((preview.get("product_validation") or {}).get("status"))}</dd>
    </dl>
    <h2>Archivos</h2>
    <ul>{links}</ul>
  </main>
</body>
</html>
"""


def render_invoice_html(
    summary: dict[str, Any],
    preview: dict[str, Any],
    invoice: dict[str, Any],
    *,
    customer_cards: dict[str, dict[str, Any]],
) -> str:
    metadata = preview.get("shipment_metadata") or {}
    invoice_group = str(invoice.get("invoice_group") or "").upper()
    payload = invoice.get("proposed_bc_payload") or {}
    lines = [line for line in invoice.get("proposed_bc_line_payloads") or [] if line.get("lineType") != "Comment"]
    comments = [line for line in invoice.get("proposed_bc_line_payloads") or [] if line.get("lineType") == "Comment"]
    customer = customer_cards.get(str(payload.get("customerId") or "")) or customer_cards.get(
        str(payload.get("customerNumber") or "")
    ) or {}
    total = sum(float(line.get("unitPrice") or 0) * float(line.get("quantity") or 0) for line in lines)
    issue_reference = payload.get("externalDocumentNumber") or f"{summary.get('custom_id')}-{invoice_group}"
    label_2 = "AWB:" if is_air(metadata) else "BOOKING:"
    value_2 = metadata.get("awb") if is_air(metadata) else metadata.get("booking")
    label_3 = "" if is_air(metadata) else "CONTENEDORES:"
    value_3 = "" if is_air(metadata) else metadata.get("containers")
    comment_rows = "".join(f"<li>{esc(line.get('description'))}</li>" for line in comments)
    line_rows = [
        f"""
        <tr>
          <td class="qty">{esc(line.get("quantity"))}</td>
          <td>{esc(line.get("description"))}</td>
          <td class="money">USD {float(line.get("unitPrice") or 0):,.2f}</td>
          <td class="money">USD {(float(line.get("unitPrice") or 0) * float(line.get("quantity") or 0)):,.2f}</td>
        </tr>
        """
        for line in lines
    ]
    for _ in range(max(0, 8 - len(line_rows))):
        line_rows.append('<tr class="empty-line"><td>&nbsp;</td><td></td><td></td><td></td></tr>')
    line_rows_html = "".join(line_rows)
    logo_src = logo_data_uri()
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{esc(summary.get("custom_id"))} {esc(invoice_group)} Air Model</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <main class="invoice">
    <header class="top-grid">
      <section class="issuer">
        <img class="logo" src="{esc(logo_src)}" alt="MTM Logix">
        <strong>MTM LOGIX GUATEMALA, SOCIEDAD ANONIMA</strong>
        <span>NIT: 109582985</span>
        <span>7A AVENIDA 2-30, ZONA 4</span>
        <span>EDIFICIO SEPTIMO, OFICINA 306</span>
        <span>CIUDAD DE GUATEMALA, GT, C.A. CODIGO POSTAL: 01004</span>
      </section>
      <section class="doc-box">
        <h1>FACTURA ELECTRONICA</h1>
        <strong>DOCUMENTO TRIBUTARIO ELECTRONICO</strong>
        <table>
          <tr><th>SERIE:</th><td>MODELO LOCAL</td></tr>
          <tr><th>NO.:</th><td>PENDIENTE BC</td></tr>
          <tr><th>FECHA:</th><td>MODELO LOCAL</td></tr>
          <tr><th>SERIE INTERNA:</th><td>{esc(invoice_group)}</td></tr>
          <tr><th>NO. INTERNO:</th><td>{esc(issue_reference)}</td></tr>
        </table>
        <p class="model-note">PREVIEW LOCAL - NO TIMBRADO - NO ENVIADO</p>
      </section>
    </header>

    <section class="middle-grid">
      <section class="bill-to">
        <h2>FACTURAR A</h2>
        <strong>{esc(customer_display_name(customer, payload))}</strong>
        <span>NIT: {esc(customer_tax_id(customer))}</span>
        <span>{esc(customer_address_line(customer))}</span>
        {customer_preview_error(customer)}
      </section>
      <section class="shipment">
        <h2>INFORMACION DE EMBARQUE</h2>
        <table>
          <tr><th>PO:</th><td>{esc(metadata.get("shipment_number"))}</td></tr>
          <tr><th>{esc(label_2)}</th><td>{esc(value_2)}</td></tr>
          {shipment_optional_row(label_3, value_3)}
        </table>
      </section>
    </section>

    <table class="lines">
      <thead>
        <tr><th>CANTIDAD</th><th>DESCRIPCION</th><th>PRECIO UNITARIO</th><th>VALOR</th></tr>
      </thead>
      <tbody>{line_rows_html}</tbody>
    </table>

    <section class="settlement-band">
      <div class="disclaimer">{esc(disclaimer_for_group(invoice_group))}</div>
      <table>
        <tr><th>SUBTOTAL</th><td>USD {total:,.2f}</td></tr>
        <tr><th>IMPUESTO</th><td>USD 0.00</td></tr>
        <tr><th>TOTAL</th><td>USD {total:,.2f}</td></tr>
      </table>
    </section>
    <section class="amount-words">
      <strong>TOTAL EN LETRA:</strong> MODELO LOCAL PARA VALIDACION DE DISENO - USD {total:,.2f}
    </section>

    <footer class="fiscal-box">
      <div>
        <h2>INFORMACION FISCAL</h2>
        <p><strong>Numero de Autorizacion:</strong> Pendiente de certificacion FEL</p>
        <p><strong>Fecha de Certificacion:</strong> Pendiente de certificacion FEL</p>
        <p><strong>Certificador:</strong> Pendiente de certificacion FEL</p>
        <small>PAGINA 1 DE 1</small>
      </div>
      <div class="fel-mark">FEL<br><span>Guatemala</span></div>
      <div class="qr-placeholder">QR</div>
      <strong class="feel">VALIDACION FEEL</strong>
    </footer>

  </main>
  <section class="debug">
    <h2>MTM META LOCAL</h2>
    <ul>{comment_rows}</ul>
  </section>
</body>
</html>
"""


def shipment_optional_row(label: str, value: Any) -> str:
    if not str(label or "").strip() and not str(value or "").strip():
        return ""
    return f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"


def customer_display_name(customer: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(
        customer.get("displayName")
        or customer.get("name")
        or payload.get("customerNumber")
        or "CLIENTE PENDIENTE"
    ).strip()


def customer_tax_id(customer: dict[str, Any]) -> str:
    return str(customer.get("taxRegistrationNumber") or customer.get("vatRegistrationNumber") or "").strip()


def customer_address_line(customer: dict[str, Any]) -> str:
    parts = [
        customer.get("addressLine1"),
        customer.get("addressLine2"),
        customer.get("city"),
        customer.get("state"),
        customer.get("country") or customer.get("countryRegionCode"),
        customer.get("postalCode"),
    ]
    return ", ".join(str(part).strip() for part in parts if str(part or "").strip())


def customer_preview_error(customer: dict[str, Any]) -> str:
    error = str(customer.get("preview_error") or "").strip()
    if not error:
        return ""
    return f'<span class="preview-error">PREVIEW: {esc(error)}</span>'


def logo_data_uri() -> str:
    logo_path = REPO_ROOT / "bc_extension" / "mtm_gt_invoice_standard" / "assets" / "mtm-logix-logo.png"
    if not logo_path.exists():
        return ""
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def is_air(metadata: dict[str, Any]) -> bool:
    product = str(metadata.get("product") or "").strip().upper()
    return product in {"AIR", "AEREO"}


def disclaimer_for_group(invoice_group: str) -> str:
    if invoice_group == "INT":
        return (
            "SUJETO A PAGOS TRIMESTRALES ISR. SERVICIOS NO AFECTOS. NO AFECTO AL IVA "
            "(FUERA DEL HECHO GENERADOR ART. 3, 7 Y 8, LEY DEL IVA)."
        )
    return "SUJETO A PAGOS TRIMESTRALES ISR"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


BASE_CSS = """
@page { size: letter; margin: 0.38in; }
* { box-sizing: border-box; }
body { margin: 0; background: #f3f4f6; color: #111; font-family: "Noto Sans", Aptos, Arial, sans-serif; }
.page, .invoice { width: 7.72in; min-height: 10.1in; margin: 24px auto; background: white; }
.page { padding: 0.34in; border: 1px solid #111; }
.invoice { display: flex; flex-direction: column; padding: 0; border: 1.2px solid #111; overflow: hidden; }
h1, h2 { margin: 0; letter-spacing: 0; }
h1 { font-size: 13pt; font-weight: 500; }
h2 { font-size: 9.5pt; font-weight: 700; }
.muted { color: #555; }
.summary { display: grid; grid-template-columns: 1.4in 1fr; gap: 6px 12px; }
.summary dt { font-weight: 700; }
.top-grid, .middle-grid { display: grid; grid-template-columns: 1fr 3.45in; border-bottom: 1px solid #111; }
.top-grid { min-height: 1.96in; }
.middle-grid { min-height: 1.33in; }
.issuer, .doc-box, .bill-to, .shipment { padding: 0.13in; }
.issuer, .bill-to { border-right: 1px solid #111; }
.issuer span, .bill-to span { display: block; font-size: 8.5pt; margin-top: 2px; }
.issuer strong, .bill-to strong { display: block; font-size: 8.4pt; line-height: 1.25; }
.logo { display: block; width: 1.62in; height: auto; margin-bottom: 0.20in; }
.doc-box { text-align: center; }
.doc-box strong { display: block; margin-top: 0.12in; font-size: 9.5pt; }
.model-note { margin: 0.08in 0 0; font-size: 7pt; font-weight: 700; }
.doc-box table, .shipment table, .settlement-band table { border-collapse: collapse; width: 100%; margin-top: 0.14in; font-size: 7.7pt; }
.doc-box th, .doc-box td, .shipment th, .shipment td, .settlement-band th, .settlement-band td { border: 1px solid #111; padding: 2px 4px; text-align: left; line-height: 1.2; }
.doc-box th, .shipment th, .settlement-band th { width: 0.98in; font-weight: 700; background: #f4f4f4; }
.shipment h2 { text-align: center; margin-bottom: 0.06in; }
.shipment td { overflow-wrap: anywhere; }
.lines { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 8.4pt; }
.lines th, .lines td { border: 1px solid #111; padding: 5px 6px; vertical-align: top; line-height: 1.2; }
.lines th { background: #c9c9c9; font-size: 9.2pt; text-align: center; font-weight: 500; }
.lines th:nth-child(1), .lines td:nth-child(1) { width: 0.82in; text-align: center; }
.lines th:nth-child(3), .lines td:nth-child(3) { width: 1.60in; }
.lines th:nth-child(4), .lines td:nth-child(4) { width: 1.25in; }
.lines tbody tr { height: 0.45in; }
.lines tbody tr.empty-line { height: 0.40in; }
.money { text-align: right; white-space: nowrap; }
.settlement-band { display: grid; grid-template-columns: 1fr 2.45in; margin-top: auto; border-top: 1px solid #111; font-size: 7.6pt; }
.disclaimer { border-right: 1px solid #111; padding: 5px 6px; font-weight: 700; line-height: 1.25; }
.settlement-band table { margin: 0; }
.settlement-band th, .settlement-band td { text-align: right; font-size: 8.8pt; }
.settlement-band tr:last-child th, .settlement-band tr:last-child td { font-weight: 700; }
.amount-words { display: grid; grid-template-columns: 1.25in 1fr; min-height: 0.26in; border-top: 1px solid #111; border-bottom: 1px solid #111; padding: 5px 6px; font-size: 7.7pt; }
.fiscal-box { margin: 0.30in 0.12in 0.16in; min-height: 1.05in; border: 1px solid #111; padding: 0.12in 0.16in; display: grid; grid-template-columns: 1fr 0.75in 0.62in 1.0in; gap: 0.16in; align-items: center; font-size: 7.3pt; }
.fiscal-box h2 { margin-bottom: 0.09in; }
.fiscal-box p { margin: 0.03in 0; }
.fiscal-box small { display: block; margin-top: 0.13in; font-size: 6.8pt; }
.fel-mark { border: 1px solid #111; border-radius: 4px; text-align: center; font-size: 17pt; font-weight: 700; padding: 0.06in 0; }
.fel-mark span { display: block; font-size: 5.6pt; font-weight: 400; }
.qr-placeholder { width: 0.52in; height: 0.52in; border: 1px solid #111; display: flex; align-items: center; justify-content: center; font-size: 8pt; font-weight: 700; justify-self: center; }
.feel { align-self: end; text-align: right; font-size: 7.5pt; }
.debug { page-break-before: always; margin: 24px auto; width: 7.72in; background: white; padding: 0.28in; border: 1px solid #ddd; font-size: 7pt; color: #444; }
@media print {
  body { background: white; }
  .page, .invoice { margin: 0; }
  .debug { display: none; }
}
"""


if __name__ == "__main__":
    main()
