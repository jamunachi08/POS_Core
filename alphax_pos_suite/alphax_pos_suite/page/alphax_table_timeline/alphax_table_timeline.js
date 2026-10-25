/* AlphaX POS — Table Timeline.
 *
 * Tables down the side, the service day across the top, every reservation
 * and every live table session drawn as a bar. A hotel tape chart plots
 * rooms against nights; a restaurant turns the same table several times in
 * an evening, so this plots tables against hours and counts covers rather
 * than keys.
 *
 * The server decides everything that matters — overlaps, turnaround gaps,
 * the covers line, which tables could take a party. This file draws it.
 */

frappe.pages["alphax-table-timeline"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Table Timeline"),
		single_column: true,
	});

	const API = "alphax_pos_suite.alphax_pos_suite.pos.timeline_api";
	const PX_PER_MIN = 2.2;       // 30-minute slot = 66px
	const ROW_LABEL = 132;

	const state = {
		outlet: null, floor: null, date: frappe.datetime.get_today(),
		start_hour: 10, end_hour: 24, lang: "en", data: null,
	};

	try {
		const l = localStorage.getItem("axtt_lang");
		if (l === "ar" || l === "en") state.lang = l;
	} catch (e) { /* private mode */ }

	// ---- toolbar ---------------------------------------------------------
	const outletField = page.add_field({
		fieldtype: "Link", fieldname: "outlet", label: __("Outlet"),
		options: "AlphaX POS Outlet",
		change: () => { state.outlet = outletField.get_value(); load(); },
	});
	const dateField = page.add_field({
		fieldtype: "Date", fieldname: "date", label: __("Date"), default: state.date,
		change: () => { state.date = dateField.get_value() || state.date; load(); },
	});
	const floorField = page.add_field({
		fieldtype: "Link", fieldname: "floor", label: __("Floor"),
		options: "AlphaX POS Floor",
		change: () => { state.floor = floorField.get_value(); load(); },
	});
	dateField.set_value(state.date);

	page.set_secondary_action(__("Refresh"), () => load());
	page.add_inner_button(__("Previous day"), () => shiftDay(-1));
	page.add_inner_button(__("Next day"), () => shiftDay(1));
	page.add_inner_button(__("العربية / EN"), () => {
		state.lang = state.lang === "ar" ? "en" : "ar";
		try { localStorage.setItem("axtt_lang", state.lang); } catch (e) { /* ignore */ }
		render();
	});
	page.set_primary_action(__("New reservation"), () => newReservation(), "add");

	function shiftDay(n) {
		state.date = frappe.datetime.add_days(state.date, n);
		dateField.set_value(state.date);
		load();
	}

	const $body = $(`
		<div class="axtt">
			<div class="axtt-summary"></div>
			<div class="axtt-conflicts"></div>
			<div class="axtt-unassigned"></div>
			<div class="axtt-scroll"><div class="axtt-grid"></div></div>
		</div>
	`).appendTo(page.main);

	injectStyles();

	function load() {
		frappe.call({
			method: `${API}.get_timeline`,
			args: {
				outlet: state.outlet, date: state.date, floor: state.floor,
				start_hour: state.start_hour, end_hour: state.end_hour,
			},
			callback: (r) => {
				state.data = r.message || {};
				if (state.data.outlet && !state.outlet) {
					state.outlet = state.data.outlet;
					outletField.set_value(state.outlet);
				}
				render();
			},
		});
	}

	const esc = (v) => frappe.utils.escape_html(String(v === undefined || v === null ? "" : v));

	function render() {
		const d = state.data || {};
		$body.attr("dir", state.lang === "ar" ? "rtl" : "ltr");

		if (!d.tables || !d.tables.length) {
			$body.find(".axtt-summary").html(
				`<div class="axtt-empty">${esc(d.warning || __("No tables in this outlet yet."))}</div>`);
			$body.find(".axtt-conflicts, .axtt-unassigned, .axtt-grid").empty();
			return;
		}

		const tot = d.totals || {};
		$body.find(".axtt-summary").html(`
			<div class="axtt-stats">
				${stat(__("Tables"), tot.tables)}
				${stat(__("Seats"), tot.seats)}
				${stat(__("Reservations"), tot.reservations)}
				${stat(__("Covers booked"), tot.covers)}
				${stat(__("Peak covers"), tot.peak_covers, tot.peak_covers > tot.seats ? "over" : "")}
				${stat(__("No shows"), tot.no_shows)}
				${stat(__("Turnaround"), (d.turnaround_minutes || 0) + " " + __("min"))}
			</div>`);

		// ---- conflicts ---------------------------------------------------
		const $c = $body.find(".axtt-conflicts").empty();
		if ((d.conflicts || []).length) {
			$c.html(`
				<div class="axtt-warn">
					<b>${__("{0} conflict(s) on this service", [d.conflicts.length])}</b>
					<ul>${d.conflicts.map((x) =>
						`<li><span class="axtt-pill ${x.kind === "overlap" ? "bad" : "warn"}">${
							x.kind === "overlap" ? __("Overlap") : __("Too tight")
						}</span> ${__("Table")} ${esc(x.table_code)} ${esc(x.at)} — ${esc(x.detail)}</li>`
					).join("")}</ul>
				</div>`);
		}

		// ---- unassigned ---------------------------------------------------
		const $u = $body.find(".axtt-unassigned").empty();
		if ((d.unassigned || []).length) {
			const $box = $(`
				<div class="axtt-unbox">
					<b>${__("{0} booking(s) without a table", [d.unassigned.length])}</b>
					<div class="axtt-unrow"></div>
				</div>`).appendTo($u);
			d.unassigned.forEach((b) => {
				$(`<button class="axtt-chip" type="button">${esc(b.label)} · ${
					esc(b.from)} · ${esc(b.covers)}${esc(__("p"))}</button>`)
					.on("click", () => suggest(b))
					.appendTo($box.find(".axtt-unrow"));
			});
		}

		// ---- grid ----------------------------------------------------------
		const span = d.span_minutes || 840;
		const gridW = span * PX_PER_MIN;
		const $g = $body.find(".axtt-grid").empty().css("width", ROW_LABEL + gridW + "px");

		// hour header
		let head = `<div class="axtt-row axtt-head"><div class="axtt-label">${__("Table")}</div>`;
		for (let h = d.start_hour; h < d.end_hour; h++) {
			head += `<div class="axtt-hour" style="width:${60 * PX_PER_MIN}px">${
				String(h % 24).padStart(2, "0")}:00</div>`;
		}
		head += "</div>";
		$g.append(head);

		// covers line
		const slots = d.slots || coversLine(d);
		let pos = `<div class="axtt-row axtt-pos"><div class="axtt-label">${__("Covers held")}</div>`;
		slots.forEach((s) => {
			const pct = Math.min(100, s.occupancy || 0);
			pos += `<div class="axtt-slot ${s.over ? "over" : ""}" style="width:${
				(d.slot_minutes || 30) * PX_PER_MIN}px" title="${esc(s.label)} — ${
				esc(s.covers)}/${esc(s.seats)} ${esc(__("covers"))}, ${esc(s.tables)}/${
				esc(s.table_count)} ${esc(__("tables"))}">
					<span class="axtt-fill" style="height:${pct}%"></span>
					<span class="axtt-slotn">${s.covers || ""}</span>
				</div>`;
		});
		pos += "</div>";
		$g.append(pos);

		// table rows, grouped by floor
		let lastFloor = null;
		d.tables.forEach((t) => {
			if (t.floor !== lastFloor) {
				lastFloor = t.floor;
				$g.append(`<div class="axtt-floor">${esc(t.floor || __("Unassigned floor"))}</div>`);
			}
			const $row = $(`
				<div class="axtt-row axtt-trow">
					<div class="axtt-label">
						<span class="axtt-code">${esc(t.table_code)}</span>
						<span class="axtt-seats">${esc(t.seats)}${esc(__("p"))}</span>
						<span class="axtt-dot ${t.readiness === "Ready" ? "ok"
							: t.readiness === "Needs Cleaning" ? "warn" : "bad"}"
							title="${esc(t.readiness)}"></span>
					</div>
				</div>`);
			for (let h = d.start_hour; h < d.end_hour; h++) {
				$row.append(`<div class="axtt-cell" style="width:${60 * PX_PER_MIN}px"></div>`);
			}
			(t.bars || []).forEach((b) => {
				const left = ROW_LABEL + Math.max(0, b.start_min) * PX_PER_MIN + 2;
				const width = Math.max(26, (b.end_min - b.start_min) * PX_PER_MIN - 4);
				const cls = b.kind === "session" ? "sess"
					: b.status === "Seated" ? "seated"
					: b.status === "No Show" ? "noshow"
					: b.status === "Completed" ? "done" : "booked";
				const $bar = $(`
					<div class="axtt-bar ${cls}" style="inset-inline-start:${left}px;width:${width}px"
						title="${esc(b.label)} · ${esc(b.from)}–${esc(b.to)} · ${esc(b.covers)}${esc(__("p"))}${
							b.allergy ? " · " + esc(b.allergy) : ""}">
						${b.vip ? '<span class="axtt-vip">★</span>' : ""}
						${b.allergy ? '<span class="axtt-alg" title="' + esc(b.allergy) + '">⚠</span>' : ""}
						<span class="axtt-bt">${esc(b.label)}</span>
						<span class="axtt-bc">${esc(b.covers) || ""}</span>
					</div>`);
				$bar.on("click", () => openBar(b, t));
				$row.append($bar);
			});
			$g.append($row);
		});
	}

	function coversLine(d) { return d.slots || []; }

	function stat(label, value, tone) {
		return `<div class="axtt-stat ${tone || ""}"><span>${label}</span><b>${
			esc(value === undefined || value === null ? "—" : value)}</b></div>`;
	}

	// ---- actions ----------------------------------------------------------

	function openBar(b, table) {
		if (b.kind === "session") {
			frappe.set_route("Form", "AlphaX POS Table Session", b.name);
			return;
		}
		const d = new frappe.ui.Dialog({
			title: `${b.label} · ${b.from}–${b.to}`,
			fields: [{ fieldtype: "HTML", fieldname: "b" }],
			primary_action_label: b.status === "Booked" ? __("Seat now") : __("Open"),
			primary_action: () => {
				d.hide();
				if (b.status === "Booked") {
					frappe.call({
						method: `${API}.seat`, args: { reservation: b.name },
						callback: () => {
							frappe.show_alert({ message: __("Seated at {0}", [table.table_code]),
								indicator: "green" }, 6);
							load();
						},
					});
				} else {
					frappe.set_route("Form", "AlphaX POS Table Reservation", b.name);
				}
			},
		});
		const lines = [
			[__("Table"), table.table_code], [__("Covers"), b.covers],
			[__("Status"), b.status], [__("Source"), b.source],
			[__("Phone"), b.phone], [__("Allergies"), b.allergy], [__("Notes"), b.notes],
		].filter((x) => x[1]);
		d.fields_dict.b.$wrapper.html(`
			<div class="axtt-detail">
				${lines.map((x) => `<div><span>${x[0]}</span><b>${esc(x[1])}</b></div>`).join("")}
				<div class="axtt-acts">
					<button class="btn btn-xs" data-act="Completed">${__("Completed")}</button>
					<button class="btn btn-xs" data-act="No Show">${__("No show")}</button>
					<button class="btn btn-xs" data-act="Cancelled">${__("Cancel")}</button>
					<button class="btn btn-xs" data-move="1">${__("Move table")}</button>
				</div>
			</div>`);
		d.fields_dict.b.$wrapper.find("[data-act]").on("click", function () {
			const st = $(this).data("act");
			frappe.call({
				method: `${API}.set_status`, args: { reservation: b.name, status: st },
				callback: () => { d.hide(); load(); },
			});
		});
		d.fields_dict.b.$wrapper.find("[data-move]").on("click", () => { d.hide(); suggest(b); });
		d.show();
	}

	function suggest(b) {
		frappe.call({
			method: `${API}.suggest_tables`, args: { reservation: b.name },
			callback: (r) => {
				const list = r.message || [];
				if (!list.length) {
					return frappe.msgprint({
						title: __("No table fits"), indicator: "orange",
						message: __("Nothing is free for {0} guests at {1}. Change the time, split the party, or extend the service.",
							[b.covers, b.from]),
					});
				}
				const d = new frappe.ui.Dialog({
					title: __("Table for {0} · {1} guests", [b.label, b.covers]),
					fields: [{ fieldtype: "HTML", fieldname: "b" }],
				});
				d.fields_dict.b.$wrapper.html(`
					<p class="axtt-note">${__("Best fit first: the smallest table that still seats the party, so larger tables stay free for larger bookings.")}</p>
					${list.map((x, i) => `
						<div class="axtt-sugg">
							<div><b>${esc(x.table_code)}</b>
								<span>${esc(x.seats)}${esc(__("p"))} · ${esc(x.floor || "")} · ${esc(x.readiness)}</span>
								${x.spare ? `<span class="axtt-spare">${__("{0} seat(s) spare", [x.spare])}</span>` : `<span class="axtt-exact">${__("exact fit")}</span>`}
							</div>
							<button class="btn btn-xs btn-primary" data-i="${i}">${__("Assign")}</button>
						</div>`).join("")}`);
				d.fields_dict.b.$wrapper.find("[data-i]").on("click", function () {
					const pick = list[+$(this).data("i")];
					frappe.call({
						method: `${API}.assign_table`,
						args: { reservation: b.name, table: pick.table },
						callback: () => {
							d.hide();
							frappe.show_alert({ indicator: "green",
								message: __("{0} assigned to {1}", [b.label, pick.table_code]) }, 6);
							load();
						},
					});
				});
				d.show();
			},
		});
	}

	function newReservation() {
		frappe.new_doc("AlphaX POS Table Reservation", {
			outlet: state.outlet, floor: state.floor, reservation_date: state.date,
		});
	}

	function injectStyles() {
		if (document.getElementById("axtt-styles")) return;
		$(`<style id="axtt-styles">
.axtt{padding-bottom:40px}
.axtt-stats{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 12px}
.axtt-stat{background:var(--fg-color);border:1px solid var(--border-color);border-radius:8px;
 padding:6px 12px;min-width:92px}
.axtt-stat span{display:block;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted)}
.axtt-stat b{font-size:16px}
.axtt-stat.over b{color:var(--red-600,#dc2626)}
.axtt-warn{border:1px solid var(--yellow-300,#f5d48a);background:var(--yellow-50,#fffaeb);
 border-radius:8px;padding:9px 13px;margin-bottom:10px;font-size:12.5px}
.axtt-warn ul{margin:5px 0 0;padding-inline-start:18px}
.axtt-pill{font-size:10px;font-weight:700;text-transform:uppercase;border-radius:4px;padding:1px 6px}
.axtt-pill.bad{background:#fee2e2;color:#b91c1c}
.axtt-pill.warn{background:#fef3c7;color:#a16207}
.axtt-unbox{border:1px dashed var(--border-color);border-radius:8px;padding:9px 13px;margin-bottom:10px;font-size:12.5px}
.axtt-unrow{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.axtt-chip{border:1px solid var(--border-color);background:var(--fg-color);border-radius:999px;
 padding:3px 11px;font-size:12px;cursor:pointer}
.axtt-chip:hover{border-color:var(--primary,#1b7f79)}
.axtt-scroll{overflow-x:auto;border:1px solid var(--border-color);border-radius:8px;background:var(--fg-color)}
.axtt-grid{min-width:100%}
.axtt-row{display:flex;position:relative;height:40px;align-items:stretch}
.axtt-head{height:30px;position:sticky;top:0;z-index:3;background:var(--fg-color);
 border-bottom:1px solid var(--border-color)}
.axtt-label{flex:0 0 132px;position:sticky;inset-inline-start:0;z-index:2;background:var(--fg-color);
 border-inline-end:1px solid var(--border-color);display:flex;align-items:center;gap:6px;
 padding:0 9px;font-size:12px}
.axtt-hour{flex:0 0 auto;border-inline-start:1px solid var(--border-color);font-size:10.5px;
 color:var(--text-muted);padding:7px 0 0 5px}
.axtt-cell{flex:0 0 auto;border-inline-start:1px solid var(--border-color)}
.axtt-pos{height:44px;background:var(--control-bg);border-bottom:1px solid var(--border-color)}
.axtt-slot{flex:0 0 auto;position:relative;border-inline-start:1px solid var(--border-color);
 display:flex;align-items:flex-end;justify-content:center}
.axtt-fill{position:absolute;inset-inline:2px;bottom:0;background:var(--primary,#1b7f79);opacity:.22;border-radius:2px 2px 0 0}
.axtt-slot.over .axtt-fill{background:var(--red-500,#ef4444);opacity:.4}
.axtt-slotn{position:relative;font-size:9.5px;color:var(--text-muted);padding-bottom:2px}
.axtt-floor{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);
 padding:7px 10px 3px;background:var(--control-bg);position:sticky;inset-inline-start:0}
.axtt-trow{border-bottom:1px solid var(--border-color)}
.axtt-code{font-weight:600}
.axtt-seats{color:var(--text-muted);font-size:11px}
.axtt-dot{width:7px;height:7px;border-radius:50%;margin-inline-start:auto}
.axtt-dot.ok{background:#16a34a}.axtt-dot.warn{background:#d97706}.axtt-dot.bad{background:#dc2626}
.axtt-bar{position:absolute;top:5px;height:30px;border-radius:5px;display:flex;align-items:center;
 gap:4px;padding:0 7px;font-size:11.5px;color:#fff;cursor:pointer;overflow:hidden;white-space:nowrap}
.axtt-bar.booked{background:#1d5b96}
.axtt-bar.seated{background:#1f6f45}
.axtt-bar.sess{background:#5a6472}
.axtt-bar.done{background:#94a3b8}
.axtt-bar.noshow{background:#a03030;opacity:.55;text-decoration:line-through}
.axtt-bar:hover{filter:brightness(1.12)}
.axtt-bt{overflow:hidden;text-overflow:ellipsis}
.axtt-bc{margin-inline-start:auto;opacity:.85;font-weight:700}
.axtt-vip{color:#fde68a}
.axtt-alg{color:#fecaca}
.axtt-detail div{display:flex;justify-content:space-between;gap:12px;padding:5px 0;
 border-bottom:1px solid var(--border-color);font-size:13px}
.axtt-detail div span{color:var(--text-muted)}
.axtt-acts{display:flex !important;gap:6px;justify-content:flex-start !important;
 border-bottom:0 !important;padding-top:12px !important}
.axtt-sugg{display:flex;align-items:center;justify-content:space-between;gap:10px;
 padding:7px 0;border-bottom:1px solid var(--border-color);font-size:13px}
.axtt-sugg span{color:var(--text-muted);font-size:11.5px;margin-inline-start:7px}
.axtt-spare{color:var(--text-muted)}
.axtt-exact{color:#15803d !important;font-weight:600}
.axtt-note{font-size:12px;color:var(--text-muted)}
.axtt-empty{padding:32px;text-align:center;color:var(--text-muted)}
		</style>`).appendTo(document.head);
	}

	load();
};
