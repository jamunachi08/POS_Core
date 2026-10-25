"""Kitchen briefing writer — a local model narrates; it never computes.

Data-residency rules, enforced in code:

* The endpoint must resolve only to private, loopback or link-local addresses
  (an on-prem or in-VPC model server), or be listed by name in
  ``ai_allowed_hosts`` (a server the operator controls inside the Kingdom).
  Public endpoints that are not listed are refused before any request is made.
* The prompt carries item names, quantities, slots and calendar tags only:
  no customer, cashier, invoice or payment data.
* The reply is rejected if it contains a quantity the engine did not produce,
  so a model cannot invent a number the kitchen then preps to.

When the model is off, unreachable or rejected, a deterministic bilingual
template writes the briefing, so the planner never depends on the model.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

import frappe
from frappe.utils import cint, flt, now_datetime

SETTINGS = "AlphaX POS Forecast Settings"


# ------------------------------------------------------------------ guard


def endpoint_allowed(url: str, allowed_hosts: str | None) -> tuple[bool, str]:
	try:
		parsed = urlparse(url or "")
	except Exception:
		return False, "Endpoint is not a valid URL."
	if parsed.scheme not in ("http", "https") or not parsed.hostname:
		return False, "Endpoint must be an http(s) URL."
	host = parsed.hostname.lower()
	listed = {h.strip().lower() for h in (allowed_hosts or "").splitlines() if h.strip()}
	if host in listed:
		return True, f"{host} is in the allowed hosts list."
	try:
		infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
	except socket.gaierror:
		return False, f"{host} does not resolve."
	addrs = {i[4][0] for i in infos}
	for a in addrs:
		ip = ipaddress.ip_address(a.split("%")[0])
		if not (ip.is_private or ip.is_loopback or ip.is_link_local):
			return False, (
				f"{host} resolves to public address {a}. Sales context stays on your network: "
				"use an on-prem model server or add a host you control to the allowed list."
			)
	return True, f"{host} resolves only to private addresses ({', '.join(sorted(addrs))})."


# ------------------------------------------------------------------ context


def _context(fc) -> dict:
	lines = sorted(fc.lines, key=lambda l: -flt(l.planned_qty))[:15]
	return {
		"outlet": fc.outlet,
		"date": str(fc.forecast_date),
		"weekday": frappe.utils.getdate(fc.forecast_date).strftime("%A"),
		"hijri": fc.hijri_date,
		"calendar": fc.events or "",
		"plan_to": fc.plan_to,
		"total_forecast": round(flt(fc.total_forecast)),
		"items": [
			{
				"item": l.item_name or l.item_code,
				"plan": round(flt(l.planned_qty)),
				"forecast": round(flt(l.forecast_qty)),
				"range": [round(flt(l.low_qty)), round(flt(l.high_qty))],
				"busiest": l.peak_slot or "",
				"why": l.drivers or "",
			}
			for l in lines
		],
	}


def template_briefing(fc) -> str:
	c = _context(fc)
	top = c["items"][:5]
	en = [f"{c['weekday']} {c['date']} ({c['hijri']}) at {c['outlet']}: about {c['total_forecast']} items expected."]
	if c["calendar"]:
		en.append(f"Calendar: {c['calendar']}.")
	if top:
		en.append("Prep first: " + "; ".join(f"{i['item']} {i['plan']} (busiest {i['busiest'] or 'all day'})" for i in top) + ".")
	ar = [f"{c['date']} ({c['hijri']}) في {c['outlet']}: المتوقع نحو {c['total_forecast']} صنفاً."]
	if c["calendar"]:
		ar.append(f"المناسبات: {c['calendar']}.")
	if top:
		ar.append("ابدأ بتحضير: " + "؛ ".join(f"{i['item']} {i['plan']}" for i in top) + ".")
	return " ".join(en) + "\n\n" + " ".join(ar)


def _numbers_ok(text: str, ctx: dict) -> bool:
	allowed = {c["total_forecast"]}
	for i in ctx["items"]:
		allowed.update({i["plan"], i["forecast"], *i["range"]})
	allowed.update(int(x) for x in re.findall(r"\d+", ctx["date"] + " " + (ctx["hijri"] or "")))
	for n in re.findall(r"(?<![\d.])(\d{2,})(?![\d.])", text):
		if int(n) not in allowed:
			return False
	return True


# ------------------------------------------------------------------ writer


def _post(url, payload, key, timeout):
	req = urllib.request.Request(
		url.rstrip("/") + "/chat/completions",
		data=json.dumps(payload).encode(),
		headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
		method="POST",
	)
	with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — host vetted above
		return json.loads(resp.read().decode())


def write_briefing(fc) -> tuple[str, str]:
	s = frappe.get_cached_doc(SETTINGS)
	fallback = template_briefing(fc)
	if not cint(s.get("ai_enabled")) or not s.get("ai_endpoint"):
		return fallback, "Template"
	ok, why = endpoint_allowed(s.ai_endpoint, s.get("ai_allowed_hosts"))
	if not ok:
		frappe.log_error(title="AlphaX forecast briefing: endpoint refused", message=why)
		return fallback, "Template (endpoint refused)"

	ctx = _context(fc)
	system = (
		"You write a short morning briefing for a restaurant kitchen in Saudi Arabia. "
		"Use only the numbers given. Never invent or change a quantity. "
		"Write 3-5 sentences in English, then the same in Arabic. "
		"Say what to prep first, when the rush is, and which calendar effect matters."
	)
	payload = {
		"model": s.get("ai_model") or "qwen2.5:7b-instruct",
		"temperature": 0.2,
		"max_tokens": 450,
		"messages": [
			{"role": "system", "content": system},
			{"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
		],
	}
	try:
		key = s.get_password("ai_api_key", raise_exception=False)
	except Exception:
		key = None
	try:
		data = _post(s.ai_endpoint, payload, key, max(cint(s.get("ai_timeout")) or 30, 5))
		text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
	except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
		frappe.log_error(title="AlphaX forecast briefing: model unreachable", message=str(e)[:500])
		return fallback, "Template (model unreachable)"
	if not text:
		return fallback, "Template (empty reply)"
	if not _numbers_ok(text, ctx):
		frappe.log_error(title="AlphaX forecast briefing: reply rejected", message=text[:1500])
		return fallback, "Template (model invented a number)"
	return text, f"Local model {payload['model']}"


def check_connection() -> dict:
	s = frappe.get_doc(SETTINGS)
	if not s.get("ai_endpoint"):
		return {"ok": False, "message": "Set a model endpoint first."}
	ok, why = endpoint_allowed(s.ai_endpoint, s.get("ai_allowed_hosts"))
	result = {"ok": ok, "message": why}
	if ok:
		try:
			key = s.get_password("ai_api_key", raise_exception=False)
		except Exception:
			key = None
		try:
			data = _post(
				s.ai_endpoint,
				{"model": s.get("ai_model"), "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
				key,
				max(cint(s.get("ai_timeout")) or 30, 5),
			)
			result["message"] += " Model answered." if data.get("choices") else " Endpoint answered without choices."
		except Exception as e:
			result = {"ok": False, "message": f"{why} But the request failed: {str(e)[:200]}"}
	frappe.db.set_single_value(SETTINGS, "ai_last_check", f"{now_datetime():%Y-%m-%d %H:%M} — {result['message']}"[:500])
	return result
