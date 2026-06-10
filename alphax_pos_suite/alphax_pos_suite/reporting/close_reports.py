import frappe
from frappe.utils import cint, flt, now_datetime


def _get_close_source(terminal_name, default="AlphaX POS Order"):
    if terminal_name and frappe.db.exists("AlphaX POS Terminal", terminal_name):
        src = frappe.get_value("AlphaX POS Terminal", terminal_name, "alphax_close_report_source")
        if src:
            return src
    return default


def _get_terminal_profile(terminal_name):
    if not terminal_name:
        return None
    if frappe.db.exists("AlphaX POS Terminal", terminal_name):
        t = frappe.get_doc("AlphaX POS Terminal", terminal_name)
        return getattr(t, "pos_profile", None)
    return None


def build_shift_close_context(shift_doc):
    terminal = shift_doc.pos_terminal
    profile = _get_terminal_profile(terminal)
    company = None
    if terminal and frappe.db.exists("AlphaX POS Terminal", terminal):
        company = frappe.get_value("AlphaX POS Terminal", terminal, "company")

    from_dt = shift_doc.opened_on
    to_dt = shift_doc.closed_on or now_datetime()

    source = _get_close_source(terminal, default="AlphaX POS Order")

    if source == "Sales Invoice":
        orders = frappe.get_all(
            "Sales Invoice",
            filters={
                "docstatus": 1,
                "is_pos": 1,
                "posting_date": ["between", [from_dt.date(), to_dt.date()]],
            },
            fields=["name", "grand_total", "is_return", "discount_amount", "posting_date", "posting_time"],
        )
    else:
        orders = frappe.get_all(
            "AlphaX POS Order",
            filters={
                "pos_terminal": terminal,
                "docstatus": 1,
                "posting_date": ["between", [from_dt.date(), to_dt.date()]],
            },
            fields=[
                "name",
                "grand_total",
                "is_return",
                "discount_amount",
                "tip_amount",
                "service_charge_amount",
                "sales_invoice",
                "posting_date",
                "posting_time",
            ],
        )

    sales_value = 0.0
    return_value = 0.0
    discount = 0.0

    for o in orders:
        gt = flt(o.get("grand_total") or 0)
        if cint(o.get("is_return") or 0) == 1:
            return_value += gt
        else:
            sales_value += gt
        discount += flt(o.get("discount_amount") or 0)

    mop_map = {}

    if source == "Sales Invoice":
        for o in orders:
            try:
                doc = frappe.get_doc("Sales Invoice", o["name"])
            except Exception:
                continue
            for p in (doc.payments or []):
                mop = p.mode_of_payment
                mop_map[mop] = mop_map.get(mop, 0.0) + flt(p.amount or 0)
    else:
        for o in orders:
            try:
                doc = frappe.get_doc("AlphaX POS Order", o["name"])
            except Exception:
                continue
            for p in (doc.payments or []):
                mop = p.mode_of_payment
                mop_map[mop] = mop_map.get(mop, 0.0) + flt(p.amount or 0)

    payment_rows = [{"mode_of_payment": k, "system_amount": v} for k, v in sorted(mop_map.items())]

    expected_cash = flt(shift_doc.expected_cash or 0)
    closing_cash = flt(shift_doc.closing_cash or 0)
    variance = flt(shift_doc.variance or (closing_cash - expected_cash))

    return {
        "report_type": "Shift Close",
        "company": company,
        "terminal": terminal,
        "pos_profile": profile,
        "posting_date": (shift_doc.closed_on or now_datetime()).date().isoformat(),
        "from_time": str(from_dt),
        "to_time": str(to_dt),
        "sales_count": len([x for x in orders if not cint(x.get("is_return") or 0)]),
        "sales_value": round(sales_value, 2),
        "return_value": round(return_value, 2),
        "net_sales": round(sales_value - return_value, 2),
        "discount_amount": round(discount, 2),
        "payments": payment_rows,
        "expected_cash": round(expected_cash, 2),
        "actual_cash": round(closing_cash, 2),
        "variance": round(variance, 2),
    }


def recompute_day_close(day_close_doc):
    cash_total = 0.0
    for d in (day_close_doc.denominations or []):
        amt = flt(d.denomination or 0) * cint(d.qty or 0)
        d.amount = amt
        cash_total += amt
    day_close_doc.cash_total = cash_total

    variance = 0.0
    for p in (day_close_doc.payments or []):
        p.difference = flt(p.counter_amount or 0) - flt(p.system_amount or 0)
        variance += p.difference
    day_close_doc.variance = variance

    terminal = day_close_doc.pos_terminal
    source = (day_close_doc.data_source or "AlphaX POS Order")

    if source == "Sales Invoice":
        orders = frappe.get_all(
            "Sales Invoice",
            filters={"docstatus": 1, "is_pos": 1, "posting_date": day_close_doc.posting_date},
            fields=["name", "grand_total", "is_return", "discount_amount"],
        )
    else:
        filters = {"pos_terminal": terminal, "docstatus": 1, "posting_date": day_close_doc.posting_date}
        orders = frappe.get_all(
            "AlphaX POS Order",
            filters=filters,
            fields=["name", "grand_total", "is_return", "discount_amount"],
        )

    sales_value = 0.0
    return_value = 0.0
    discount = 0.0

    for o in orders:
        gt = flt(o.get("grand_total") or 0)
        if cint(o.get("is_return") or 0) == 1:
            return_value += gt
        else:
            sales_value += gt
        discount += flt(o.get("discount_amount") or 0)

    mop_map = {}

    if source == "Sales Invoice":
        for o in orders:
            try:
                doc = frappe.get_doc("Sales Invoice", o["name"])
            except Exception:
                continue
            for pp in (doc.payments or []):
                mop_map[pp.mode_of_payment] = mop_map.get(pp.mode_of_payment, 0.0) + flt(pp.amount or 0)
    else:
        for o in orders:
            try:
                doc = frappe.get_doc("AlphaX POS Order", o["name"])
            except Exception:
                continue
            for pp in (doc.payments or []):
                mop_map[pp.mode_of_payment] = mop_map.get(pp.mode_of_payment, 0.0) + flt(pp.amount or 0)

    existing = {r.mode_of_payment: r for r in (day_close_doc.payments or []) if r.mode_of_payment}
    if not day_close_doc.payments:
        day_close_doc.payments = []
        existing = {}

    for mop, amt in mop_map.items():
        if mop in existing:
            existing[mop].system_amount = amt
        else:
            day_close_doc.append("payments", {"mode_of_payment": mop, "system_amount": amt, "counter_amount": amt})

    day_close_doc.sales_count = len([x for x in orders if not cint(x.get("is_return") or 0)])
    day_close_doc.sales_value = sales_value
    day_close_doc.return_value = return_value
    day_close_doc.net_sales = sales_value - return_value
    day_close_doc.discount_amount = discount


def build_day_close_context(day_close_doc):
    return {
        "report_type": "Day Close",
        "company": day_close_doc.company,
        "terminal": day_close_doc.pos_terminal,
        "pos_profile": day_close_doc.pos_profile,
        "posting_date": str(day_close_doc.posting_date),
        "from_time": str(day_close_doc.from_time or ""),
        "to_time": str(day_close_doc.to_time or ""),
        "sales_count": int(day_close_doc.sales_count or 0),
        "sales_value": round(flt(day_close_doc.sales_value or 0), 2),
        "return_value": round(flt(day_close_doc.return_value or 0), 2),
        "net_sales": round(flt(day_close_doc.net_sales or 0), 2),
        "vat": round(flt(day_close_doc.vat_amount or 0), 2),
        "discount_amount": round(flt(day_close_doc.discount_amount or 0), 2),
        "cash_total": round(flt(day_close_doc.cash_total or 0), 2),
        "variance": round(flt(day_close_doc.variance or 0), 2),
        "payments": [
            {
                "mode_of_payment": r.mode_of_payment,
                "system_amount": flt(r.system_amount or 0),
                "counter_amount": flt(r.counter_amount or 0),
                "difference": flt(r.difference or 0),
            }
            for r in (day_close_doc.payments or [])
        ],
    }


def _pick_email_setups(company=None, pos_profile=None, terminal=None, report_type="Both"):
    setups = frappe.get_all(
        "AlphaX POS Report Email Setup",
        filters={"enabled": 1},
        fields=[
            "name",
            "company",
            "pos_profile",
            "terminal",
            "report_type",
            "trigger_on",
            "attach_pdf",
            "include_inline_summary",
            "subject_template",
            "body_template",
            "cc",
            "bcc",
            "send_only_if_variance_gt",
        ],
    )
    scored = []
    for s in setups:
        if s.get("report_type") not in ("Both", report_type):
            continue
        score = 0
        if terminal and s.get("terminal") == terminal:
            score += 100
        elif s.get("terminal"):
            continue
        if pos_profile and s.get("pos_profile") == pos_profile:
            score += 50
        elif s.get("pos_profile"):
            continue
        if company and s.get("company") == company:
            score += 10
        elif s.get("company"):
            continue
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored]


def _render_template(tpl, ctx):
    try:
        return frappe.render_template(tpl or "", ctx)
    except Exception:
        return tpl or ""


def maybe_send_close_email(
    report_type,
    company,
    terminal,
    pos_profile,
    reference_doctype,
    reference_name,
    context,
    print_doctype,
    print_name,
    print_format=None,
):
    setups = _pick_email_setups(company=company, pos_profile=pos_profile, terminal=terminal, report_type=report_type)
    for s in setups:
        if (s.get("trigger_on") or "On Submit") != "On Submit":
            continue

        var_gt = flt(s.get("send_only_if_variance_gt") or 0)
        if var_gt and abs(flt(context.get("variance") or 0)) <= var_gt:
            continue

        recs = frappe.get_doc("AlphaX POS Report Email Setup", s["name"]).recipients or []
        to_list = [r.email for r in recs if getattr(r, "active", 1) and r.email]
        if not to_list:
            continue

        attachments = []
        if int(s.get("attach_pdf") or 0) == 1:
            try:
                pdf = frappe.get_print(print_doctype, print_name, print_format=print_format, as_pdf=True)
                filename = f"{report_type.replace(' ', '_')}_{print_name}.pdf"
                attachments.append({"fname": filename, "fcontent": pdf})
            except Exception:
                pass

        subject = _render_template(
            s.get("subject_template"),
            {**context, "company": company, "terminal": terminal, "report_type": report_type},
        )
        body = _render_template(
            s.get("body_template"),
            {**context, "company": company, "terminal": terminal, "report_type": report_type},
        )

        try:
            frappe.sendmail(
                recipients=to_list,
                cc=(s.get("cc") or "").split(",") if s.get("cc") else None,
                bcc=(s.get("bcc") or "").split(",") if s.get("bcc") else None,
                subject=subject,
                message=body,
                attachments=attachments,
                reference_doctype=reference_doctype,
                reference_name=reference_name,
                now=True,
            )
            _log_email(report_type, reference_doctype, reference_name, ",".join(to_list), s.get("cc") or "", "Sent", "")
        except Exception as e:
            _log_email(report_type, reference_doctype, reference_name, ",".join(to_list), s.get("cc") or "", "Failed", str(e))


def _log_email(report_type, ref_dt, ref_name, to, cc, status, error):
    try:
        d = frappe.new_doc("AlphaX POS Email Log")
        d.report_type = report_type
        d.reference_doctype = ref_dt
        d.reference_name = ref_name
        d.to = to
        d.cc = cc
        d.status = status
        d.error = error
        if status == "Sent":
            d.sent_on = now_datetime()
        d.insert(ignore_permissions=True)
    except Exception:
        pass
