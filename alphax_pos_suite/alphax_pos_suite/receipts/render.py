"""Till receipt renderer for AlphaX Receipt Templates.

Server-side, escaped, no Jinja in templates: a template is an ordered list of
blocks, each with a type, alignment, size and optional bilingual text. The
same function backs the print format, the designer preview and the bridge.
"""

from __future__ import annotations

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, escape_html, flt, get_datetime

from alphax_pos_suite.alphax_pos_suite.receipts import zatca_qr

TITLE_EN = "Simplified Tax Invoice"
TITLE_AR = "فاتورة ضريبية مبسطة"

DEFAULT_BLOCKS = [
	{"block_type": "Logo", "align": "Center"},
	{"block_type": "Company & VAT", "align": "Center", "bold": 1},
	{"block_type": "Outlet & Address", "align": "Center"},
	{"block_type": "Title", "align": "Center", "bold": 1, "text_en": TITLE_EN, "text_ar": TITLE_AR},
	{"block_type": "Divider"},
	{"block_type": "Invoice Details", "align": "Start"},
	{"block_type": "Customer", "align": "Start"},
	{"block_type": "Divider"},
	{"block_type": "Items"},
	{"block_type": "Divider"},
	{"block_type": "Totals"},
	{"block_type": "VAT Breakdown"},
	{"block_type": "Payments"},
	{"block_type": "Loyalty & Gift Balance", "align": "Center"},
	{"block_type": "ZATCA QR", "align": "Center", "qr_size_mm": 30},
	{"block_type": "Text", "align": "Center", "text_en": "Thank you for visiting {outlet}", "text_ar": "شكراً لزيارتكم"},
]

# What a KSA simplified tax invoice must show, and the block that shows it.
REQUIRED = [
	("Title", _("the title “Simplified Tax Invoice / فاتورة ضريبية مبسطة”")),
	("Company & VAT", _("seller name and VAT registration number")),
	("Invoice Details", _("invoice number, date and time")),
	("Items", _("goods or services with quantity and price")),
	("Totals", _("total including VAT")),
	("VAT Breakdown", _("VAT amount")),
	("ZATCA QR", _("the ZATCA QR code")),
]


def compliance(blocks: list[dict]) -> list[str]:
	shown = {b.get("block_type") for b in blocks if not cint(b.get("hidden"))}
	missing = [why for t, why in REQUIRED if t not in shown]
	title = next((b for b in blocks if b.get("block_type") == "Title" and not cint(b.get("hidden"))), None)
	if title and TITLE_EN.lower() not in (title.get("text_en") or "").lower() and TITLE_AR not in (title.get("text_ar") or ""):
		missing.append(_("the title must read “Simplified Tax Invoice” or “فاتورة ضريبية مبسطة”"))
	return missing


def template_for(outlet: str | None):
	name = frappe.db.get_value("AlphaX POS Outlet", outlet, "receipt_template") if outlet else None
	if not name:
		name = frappe.db.get_value("AlphaX Receipt Template", {"is_default": 1}, "name")
	if name:
		t = frappe.get_cached_doc("AlphaX Receipt Template", name)
		return t.as_dict(), [b.as_dict() for b in t.blocks]
	return {"paper_width_mm": "80", "language": "Arabic and English", "base_font_pt": 9}, DEFAULT_BLOCKS


# ------------------------------------------------------------------ helpers


def _money(v) -> str:
	return f"{flt(v):,.2f}"


def _fill(text: str, ctx: dict) -> str:
	for k, v in ctx.items():
		text = text.replace("{" + k + "}", str(v or ""))
	return text


def _bi(en: str, ar: str, lang: str) -> str:
	if lang == "English":
		return escape_html(en)
	if lang == "Arabic":
		return f'<span dir="rtl">{escape_html(ar)}</span>'
	return f'{escape_html(en)} <span dir="rtl">{escape_html(ar)}</span>' if en != ar else escape_html(en)


def _row(label_en, label_ar, value, lang, strong=False):
	v = f"<b>{escape_html(value)}</b>" if strong else escape_html(value)
	return f'<div class="r"><span>{_bi(label_en, label_ar, lang)}</span><span class="n">{v}</span></div>'


def qr_text(doc) -> str | None:
	"""The ZATCA QR payload: the stamped Phase-2 QR when present, else Phase 1 built here."""
	for f in zatca_qr.PHASE2_FIELDS:
		v = doc.get(f)
		if v and isinstance(v, str) and zatca_qr.is_tlv(v.strip()):
			return v.strip()
	company = frappe.get_cached_doc("Company", doc.company)
	vat_no = doc.get("company_tax_id") or company.get("tax_id")
	if not vat_no:
		return None
	ts = get_datetime(f"{doc.posting_date} {doc.posting_time or '00:00:00'}")
	try:
		import zoneinfo

		from frappe.utils.data import get_system_timezone

		ts = ts.replace(tzinfo=zoneinfo.ZoneInfo(get_system_timezone())).astimezone(zoneinfo.ZoneInfo("UTC"))
	except Exception:
		pass
	vat = flt(doc.get("base_total_taxes_and_charges") or doc.get("total_taxes_and_charges"))
	total = flt(doc.get("base_grand_total") or doc.get("grand_total"))
	return zatca_qr.phase1_tlv(company.company_name, vat_no, ts.strftime("%Y-%m-%dT%H:%M:%SZ"), total, vat)


def qr_image(doc) -> str | None:
	for f in zatca_qr.PHASE2_FIELDS:
		v = doc.get(f)
		if v and isinstance(v, str) and (v.startswith("/files/") or v.startswith("/private/files/")):
			return v  # an image the ZATCA app attached
	text = qr_text(doc)
	return zatca_qr.png_data_uri(text) if text else None


# ------------------------------------------------------------------ render


def render(doc, template: dict | None = None, blocks: list[dict] | None = None) -> str:
	if template is None or blocks is None:
		template, blocks = template_for(doc.get("alphax_outlet"))
	lang = template.get("language") or "Arabic and English"
	width = cint(template.get("paper_width_mm") or 80)
	base = cint(template.get("base_font_pt") or 9)
	company = frappe.get_cached_doc("Company", doc.company)
	outlet = frappe.db.get_value("AlphaX POS Outlet", doc.get("alphax_outlet"), ["outlet_name", "name"], as_dict=True) or {}
	ctx = {
		"invoice": doc.name,
		"date": frappe.utils.format_datetime(f"{doc.posting_date} {doc.posting_time or ''}", "yyyy-MM-dd HH:mm"),
		"outlet": outlet.get("outlet_name") or outlet.get("name") or "",
		"cashier": frappe.utils.get_fullname(doc.owner),
	}
	parts = []
	for b in blocks:
		if cint(b.get("hidden")):
			continue
		t = b.get("block_type")
		style = f'text-align:{ {"Center": "center", "Start": "start", "End": "end"}.get(b.get("align") or "Center", "center") };'
		if cint(b.get("font_size")):
			style += f"font-size:{cint(b.get('font_size'))}pt;"
		if cint(b.get("bold")):
			style += "font-weight:700;"
		html = ""
		if t == "Logo":
			logo = template.get("logo") or company.get("company_logo")
			if logo:
				html = f'<img src="{escape_html(logo)}" style="max-width:60%;max-height:22mm">'
		elif t in ("Title", "Text"):
			en = _fill(b.get("text_en") or "", ctx)
			ar = _fill(b.get("text_ar") or "", ctx)
			if lang == "English":
				html = escape_html(en)
			elif lang == "Arabic":
				html = f'<div dir="rtl">{escape_html(ar or en)}</div>'
			else:
				html = escape_html(en) + (f'<div dir="rtl">{escape_html(ar)}</div>' if ar else "")
		elif t == "Company & VAT":
			vat = doc.get("company_tax_id") or company.get("tax_id") or ""
			html = escape_html(company.company_name)
			if vat:
				html += f"<div>{_bi('VAT No.', 'الرقم الضريبي', lang)}: {escape_html(vat)}</div>"
			if company.get("registration_details") or company.get("company_registration"):
				cr = company.get("company_registration") or ""
				if cr:
					html += f"<div>{_bi('CR', 'السجل التجاري', lang)}: {escape_html(cr)}</div>"
		elif t == "Outlet & Address":
			addr = ""
			if doc.get("company_address"):
				a = frappe.db.get_value("Address", doc.company_address, ["address_line1", "city"], as_dict=True) or {}
				addr = ", ".join(x for x in (a.get("address_line1"), a.get("city")) if x)
			html = escape_html(ctx["outlet"]) + (f"<div>{escape_html(addr)}</div>" if addr else "")
		elif t == "Invoice Details":
			html = _row("Invoice", "رقم الفاتورة", doc.name, lang) + _row("Date", "التاريخ", ctx["date"], lang)
			if doc.get("is_return") and doc.get("return_against"):
				html += _row("Return of", "مرتجع للفاتورة", doc.return_against, lang)
			if doc.get("alphax_table"):
				html += _row("Table", "الطاولة", doc.alphax_table, lang)
		elif t == "Customer":
			if doc.get("customer_name") and doc.customer_name not in ("Walk-in Customer", "Guest"):
				html = _row("Customer", "العميل", doc.customer_name, lang)
		elif t == "Items":
			rows = "".join(
				f'<tr><td>{escape_html(it.item_name)}</td><td class="n">{flt(it.qty):g}</td>'
				f'<td class="n">{_money(it.rate)}</td><td class="n">{_money(it.amount)}</td></tr>'
				for it in doc.items
			)
			html = (f'<table><tr><th>{_bi("Item", "الصنف", lang)}</th><th class="n">{_bi("Qty", "الكمية", lang)}</th>'
			        f'<th class="n">{_bi("Price", "السعر", lang)}</th><th class="n">{_bi("Total", "المجموع", lang)}</th></tr>{rows}</table>')
		elif t == "Totals":
			html = _row("Total excl. VAT", "الإجمالي غير شامل الضريبة", _money(doc.net_total), lang)
			if flt(doc.get("discount_amount")):
				html += _row("Discount", "الخصم", _money(doc.discount_amount), lang)
			html += _row("VAT", "ضريبة القيمة المضافة", _money(doc.total_taxes_and_charges), lang)
			html += f'<div class="g">{_row("Total incl. VAT", "الإجمالي شامل الضريبة", _money(doc.rounded_total or doc.grand_total), lang, True)}</div>'
		elif t == "VAT Breakdown":
			html = "".join(_row(tx.description or tx.account_head, tx.description or "", _money(tx.tax_amount), "English" if lang == "English" else lang)
			               for tx in doc.get("taxes") or [] if flt(tx.tax_amount))
		elif t == "Payments":
			html = "".join(_row(p.mode_of_payment, p.mode_of_payment, _money(p.amount), lang) for p in doc.get("payments") or [] if flt(p.amount))
			if flt(doc.get("change_amount")):
				html += _row("Change", "الباقي", _money(doc.change_amount), lang)
		elif t == "Loyalty & Gift Balance":
			html = _gift_lines(doc, lang)
		elif t == "ZATCA QR":
			src = qr_image(doc)
			mm = cint(b.get("qr_size_mm") or 30)
			html = f'<img src="{escape_html(src)}" style="width:{mm}mm;height:{mm}mm">' if src else \
				f'<i>{_bi("QR unavailable: set the company VAT number", "تعذّر رمز QR: أضف الرقم الضريبي للشركة", lang)}</i>'
		elif t == "Divider":
			parts.append('<hr>')
			continue
		elif t == "Spacer":
			parts.append('<div style="height:3mm"></div>')
			continue
		if html:
			parts.append(f'<div class="b" style="{style}">{html}</div>')

	css = f"""
	.axr{{width:{width - 6}mm;margin:0 auto;font-family:'Noto Sans Arabic','Segoe UI',Tahoma,sans-serif;font-size:{base}pt;color:#000;line-height:1.3}}
	.axr .b{{margin:1.2mm 0}} .axr hr{{border:0;border-top:1px dashed #000;margin:1.5mm 0}}
	.axr table{{width:100%;border-collapse:collapse}} .axr th{{font-size:{max(base - 1, 6)}pt;border-bottom:1px solid #000;text-align:start}}
	.axr td,.axr th{{padding:.5mm 0;vertical-align:top}} .axr .n{{text-align:end;white-space:nowrap;font-variant-numeric:tabular-nums}}
	.axr .r{{display:flex;justify-content:space-between;gap:2mm}} .axr .g{{font-size:{base + 2}pt;border-top:1px solid #000;padding-top:.8mm}}
	@page{{size:{width}mm auto;margin:0}}
	"""
	return f'<style>{css}</style><div class="axr">{"".join(parts)}</div>'


def _gift_lines(doc, lang) -> str:
	out = ""
	try:
		cards = json.loads(doc.get("alphax_gift_cards") or "[]")
	except ValueError:
		cards = []
	for c in cards:
		bal = frappe.db.get_value("AlphaX Gift Card", {"code_hash": c.get("hash")}, ["masked_code", "balance"], as_dict=True) if c.get("hash") else None
		if bal:
			out += _row(f"Gift card {bal.masked_code} balance", f"رصيد بطاقة الهدية {bal.masked_code}", _money(bal.balance), lang)
	if flt(doc.get("alphax_loyalty_redeem_points")):
		out += _row("Points redeemed", "النقاط المستبدلة", f"{flt(doc.alphax_loyalty_redeem_points):g}", lang)
	return out


# ------------------------------------------------------------------ jinja / api


def alphax_receipt(doc) -> str:
	"""Jinja: {{ alphax_receipt(doc) }} — Frappe registers jinja methods by function name."""
	from markupsafe import Markup

	return Markup(render(doc))


def alphax_zatca_qr(doc) -> str:
	"""Jinja: {{ alphax_zatca_qr(doc) }} — data URI or file URL of the QR image."""
	return qr_image(doc) or ""


@frappe.whitelist()
def preview(template: str, invoice: str | None = None):
	"""Designer preview: render the unsaved template against an invoice."""
	frappe.has_permission("AlphaX Receipt Template", "write", throw=True)
	t = frappe.parse_json(template)
	blocks = t.pop("blocks", []) or []
	if not invoice:
		invoice = frappe.db.get_value("Sales Invoice", {"docstatus": 1, "is_pos": 1}, "name", order_by="creation desc")
	if not invoice:
		return {"html": "<p>" + escape_html(_("Submit one POS sale to preview against.")) + "</p>", "missing": compliance(blocks), "invoice": None}
	doc = frappe.get_doc("Sales Invoice", invoice)
	doc.check_permission("read")
	return {"html": render(doc, t, blocks), "missing": compliance(blocks), "invoice": invoice}


@frappe.whitelist()
def default_blocks():
	return DEFAULT_BLOCKS
