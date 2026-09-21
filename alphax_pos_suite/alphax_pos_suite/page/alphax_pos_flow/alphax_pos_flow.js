/* AlphaX POS — Process Flow board.
 *
 * Renders the end-to-end cycle as swimlanes in system sequence. Every card
 * is a real document type, so the board is how an operator navigates rather
 * than a diagram kept somewhere else.
 *
 * Nothing here decides access. The server returns only the nodes this user
 * may read, so a cashier and an accountant loading the same route get
 * different boards.
 */

frappe.pages["alphax-pos-flow"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AlphaX POS Process Flow"),
		single_column: true,
	});

	const state = { flow: null, lang: "en", counts: 1, data: null };

	page.set_secondary_action(__("Refresh"), () => load());

	page.add_inner_button(__("العربية / EN"), () => {
		state.lang = state.lang === "ar" ? "en" : "ar";
		render();
	});

	page.add_inner_button(__("Toggle counts"), () => {
		state.counts = state.counts ? 0 : 1;
		load();
	});

	page.set_primary_action(__("Setup & Install"), () => openSetup(), "tool");

	const $body = $(`
		<div class="axf-wrap">
			<div class="axf-head"></div>
			<div class="axf-ready"></div>
			<div class="axf-board"><div class="axf-loading text-muted">${__("Loading…")}</div></div>
		</div>
	`).appendTo(page.main);

	injectStyles();

	function load() {
		frappe.call({
			method: "alphax_pos_suite.alphax_pos_suite.pos.flow_api.get_flow",
			args: { flow: state.flow, with_counts: state.counts },
			callback: (r) => {
				state.data = r.message || {};
				render();
			},
		});
		loadReadiness();
	}

	// ------------------------------------------------------------ readiness
	const SETUP = "alphax_pos_suite.alphax_pos_suite.pos.flow_setup";

	function loadReadiness(then) {
		frappe.call({
			method: `${SETUP}.get_readiness`,
			error: () => $body.find(".axf-ready").empty(),   // cashier: no banner
			callback: (r) => {
				state.ready = r.message || null;
				renderBanner();
				then && then(state.ready);
			},
		});
	}

	function renderBanner() {
		const rd = state.ready;
		const $r = $body.find(".axf-ready").empty();
		if (!rd || rd.ready) return;
		const pendingSite = rd.site.filter((i) => i.required && !["ok", "skipped", "info"].includes(i.status)).length;
		const pendingTerm = rd.terminals.filter((t) => t.status !== "ok").length;
		const total = pendingSite + pendingTerm;
		if (!total) return;
		$(`
			<div class="axf-banner">
				<span class="axf-banner-dot"></span>
				<span>${__("{0} setup item(s) need attention before this flow can run end to end.", [total])}</span>
				<a class="axf-btn axf-btn-new axf-banner-go">${__("Review & install")}</a>
			</div>
		`).appendTo($r).find(".axf-banner-go").on("click", () => openSetup());
	}

	const BADGE = {
		ok: ["✓", "axf-s-ok"], missing: ["!", "axf-s-miss"], blocked: ["⧗", "axf-s-block"],
		device: ["⌁", "axf-s-dev"], skipped: ["–", "axf-s-skip"], info: ["i", "axf-s-info"],
	};

	function openSetup() {
		loadReadiness((rd) => {
			if (!rd) {
				frappe.msgprint(__("Setup status is available to supervisors and managers."));
				return;
			}
			showSetupDialog(rd);
		});
	}

	function showSetupDialog(rd) {
		const d = new frappe.ui.Dialog({
			title: __("AlphaX POS — Setup & Install"),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: rd.auto_pending.length && rd.can_run
				? __("Install {0} missing item(s)", [rd.auto_pending.length])
				: __("Close"),
			primary_action: () => {
				if (!(rd.auto_pending.length && rd.can_run)) { d.hide(); return; }
				runSetup(rd.auto_pending, d);
			},
		});

		const L = (i) => (state.lang === "ar" && i.label_ar ? i.label_ar : i.label);
		const esc = frappe.utils.escape_html;

		const siteRows = rd.site.map((i) => {
			const [sym, cls] = BADGE[i.status] || BADGE.info;
			let action = "";
			if (i.kind === "auto" && i.status === "missing" && rd.can_run) {
				action = `<a class="axf-btn axf-btn-new" data-run="${i.key}">${__("Install")}</a>`;
			} else if (i.kind === "wizard" && i.status === "missing") {
				action = `<a class="axf-btn axf-btn-new" data-route="${i.route}">${__("Open wizard")}</a>`;
			} else if (i.route && (i.kind === "manual" || i.status === "info")) {
				action = `<a class="axf-btn" data-route="${i.route}">${__("Open")}</a>`;
			}
			const kind = { auto: __("Automatic"), wizard: __("Wizard"), manual: __("By hand") }[i.kind] || "";
			return `
				<div class="axf-row">
					<span class="axf-s ${cls}">${sym}</span>
					<div class="axf-row-main">
						<div class="axf-row-title">${esc(L(i))}
							${i.count !== null && i.count !== undefined ? `<span class="axf-count">${i.count}</span>` : ""}
							<span class="axf-kind">${kind}</span></div>
						${i.detail ? `<div class="axf-row-detail">${esc(i.detail)}</div>` : ""}
					</div>
					<div class="axf-row-act">${action}</div>
				</div>`;
		}).join("");

		const termRows = rd.terminals.length ? rd.terminals.map((t) => {
			const [sym, cls] = BADGE[t.status] || BADGE.info;
			const facts = [
				t.outlet ? esc(t.outlet) : "",
				t.bridge_installed ? __("Bridge {0}", [esc(t.bridge_version || "online")]) : __("No bridge"),
				t.devices ? __("{0} device(s)", [t.devices]) : "",
				t.pc_hostname ? esc(t.pc_hostname) + (t.hostname_is_os_string ? ` <b class="axf-warn">${__("(OS string, not a hostname)")}</b>` : "") : "",
			].filter(Boolean).join(" · ");
			const act = (t.status === "device" || (t.needs_bridge && !t.bridge_installed))
				? `<a class="axf-btn axf-btn-new" data-bridge="${esc(t.terminal)}">${__("Download bridge")}</a>`
				: `<a class="axf-btn" data-route="/app/alphax-pos-terminal/${encodeURIComponent(t.terminal)}">${__("Open")}</a>`;
			return `
				<div class="axf-row">
					<span class="axf-s ${cls}">${sym}</span>
					<div class="axf-row-main">
						<div class="axf-row-title">${esc(t.terminal)}</div>
						<div class="axf-row-detail">${facts}</div>
						${t.detail ? `<div class="axf-row-detail">${esc(t.detail)}</div>` : ""}
					</div>
					<div class="axf-row-act">${act}</div>
				</div>`;
		}).join("") : `<div class="axf-row-detail" style="padding:8px 0">${__("No terminals yet — the setup wizard creates the first one.")}</div>`;

		d.fields_dict.body.$wrapper.html(`
			<div class="axf-setup">
				<div class="axf-legend-s">
					<span><span class="axf-s axf-s-ok">✓</span> ${__("Ready")}</span>
					<span><span class="axf-s axf-s-miss">!</span> ${__("Missing")}</span>
					<span><span class="axf-s axf-s-dev">⌁</span> ${__("Needs the PC")}</span>
					<span><span class="axf-s axf-s-skip">–</span> ${__("Not needed")}</span>
				</div>
				<h5>${__("Site")}</h5>
				${siteRows}
				<h5>${__("Terminals")}</h5>
				<p class="axf-note">${__("PC hostname, hardware UUID, MAC and bridge state can only come from the AlphaX Bridge running on that PC — a browser cannot read them. Download the installer, run it on the till itself, and these fields fill in on its first heartbeat.")}</p>
				${termRows}
				${!rd.bridge_kit_available ? `<p class="axf-note axf-warn">${__("No bridge installer is bundled with this build. Run scripts/sync_bridge_kit.ps1 and redeploy to enable one-click downloads.")}</p>` : ""}
			</div>
		`);

		const $w = d.fields_dict.body.$wrapper;
		$w.find("[data-run]").on("click", function () { runSetup([$(this).data("run")], d); });
		$w.find("[data-route]").on("click", function () {
			d.hide();
			const r = $(this).data("route");
			frappe.set_route(r.replace(/^\/app\//, ""));
		});
		$w.find("[data-bridge]").on("click", function () { downloadBridge($(this).data("bridge")); });

		d.show();
	}

	function runSetup(keys, dialog) {
		frappe.call({
			method: `${SETUP}.run_setup`,
			args: { keys: JSON.stringify(keys) },
			freeze: true,
			freeze_message: __("Installing…"),
			callback: (r) => {
				const res = (r.message && r.message.results) || [];
				const ok = res.filter((x) => x.ok).length;
				frappe.show_alert({
					message: __("{0} of {1} step(s) completed", [ok, res.length]),
					indicator: ok === res.length ? "green" : "orange",
				}, 7);
				res.filter((x) => !x.ok).forEach((x) =>
					frappe.show_alert({ message: `${x.key}: ${x.message}`, indicator: "red" }, 10));
				dialog && dialog.hide();
				load();
				setTimeout(openSetup, 400);
			},
		});
	}

	function downloadBridge(terminal) {
		frappe.call({
			method: `${SETUP}.bridge_download`,
			args: { terminal, os_name: "windows" },
			callback: (r) => {
				const m = r.message || {};
				if (m.mode === "bundled" && m.url) {
					window.open(m.url, "_blank");
					frappe.msgprint({ title: __("Bridge installer"), message: frappe.utils.escape_html(m.note || ""), indicator: "blue" });
				} else {
					const steps = (m.plan && (m.plan.steps || m.plan.instructions)) || [];
					frappe.msgprint({
						title: __("Bridge installer"),
						indicator: "orange",
						message: `<p>${frappe.utils.escape_html(m.note || "")}</p>` +
							(steps.length ? "<ol>" + steps.map((x) => `<li>${frappe.utils.escape_html(String(x))}</li>`).join("") + "</ol>" : ""),
					});
				}
			},
		});
	}

	function t(node, field) {
		const ar = node[field + "_ar"];
		return state.lang === "ar" && ar ? ar : node[field];
	}

	function render() {
		const d = state.data || {};
		const rtl = state.lang === "ar";
		$body.attr("dir", rtl ? "rtl" : "ltr");

		if (!d.stages || !d.stages.length) {
			$body.find(".axf-head").empty();
			$body.find(".axf-board").html(
				`<div class="axf-empty">${__("No part of this flow is visible to your roles.")}</div>`
			);
			return;
		}

		const title = state.lang === "ar" && d.flow_name_ar ? d.flow_name_ar : d.flow_name;
		$body.find(".axf-head").html(`
			<div class="axf-title">${frappe.utils.escape_html(title || "")}</div>
			<div class="axf-desc">${frappe.utils.escape_html(d.description || "")}</div>
			<div class="axf-meta">
				<span>${frappe.utils.escape_html(d.user || "")}</span>
				<span>${(d.user_roles || []).map(frappe.utils.escape_html).join(" · ")}</span>
				<span>${__("Showing {0} of {1} steps", [d.visible_nodes, d.total_nodes])}</span>
			</div>
		`);

		// Group consecutive stages into their lane.
		const lanes = [];
		(d.stages || []).forEach((st) => {
			if (!lanes.length || lanes[lanes.length - 1].name !== st.lane) {
				lanes.push({ name: st.lane, colour: st.colour, stages: [] });
			}
			lanes[lanes.length - 1].stages.push(st);
		});

		const $board = $body.find(".axf-board").empty();

		lanes.forEach((lane) => {
			const $lane = $(`
				<div class="axf-lane" style="--lane:${lane.colour || "#12303F"}">
					<div class="axf-lane-label">
						<span class="axf-lane-name">${frappe.utils.escape_html(lane.name)}</span>
					</div>
					<div class="axf-stages"></div>
				</div>
			`);

			lane.stages.forEach((st) => {
				const $stage = $(`
					<div class="axf-stage">
						<div class="axf-stage-head">
							<span class="axf-seq">${st.sequence}</span>
							<span class="axf-stage-name">${frappe.utils.escape_html(
								state.lang === "ar" && st.stage_label_ar ? st.stage_label_ar : st.stage_label
							)}</span>
							${st.actor ? `<span class="axf-actor">${frappe.utils.escape_html(st.actor)}</span>` : ""}
						</div>
						<div class="axf-nodes"></div>
					</div>
				`);

				const $nodes = $stage.find(".axf-nodes");
				(st.nodes || []).forEach((n) => $nodes.append(nodeCard(n)));
				$lane.find(".axf-stages").append($stage);
			});

			$board.append($lane);
		});
	}

	function nodeCard(n) {
		const label = frappe.utils.escape_html(t(n, "node_label"));
		const std = n.is_erpnext_standard;
		const count = n.count === null || n.count === undefined ? "" : n.count;

		const $card = $(`
			<div class="axf-node ${std ? "is-std" : "is-alphax"}">
				<div class="axf-node-top">
					<span class="axf-node-label">${label}</span>
					${count !== "" ? `<span class="axf-count">${count}</span>` : ""}
				</div>
				${n.description ? `<div class="axf-node-desc">${frappe.utils.escape_html(n.description)}</div>` : ""}
				<div class="axf-node-foot">
					<span class="axf-tag">${std ? __("Standard") : "AlphaX"}</span>
					<span class="axf-actions"></span>
				</div>
			</div>
		`);

		const $actions = $card.find(".axf-actions");

		if (n.route) {
			$("<a class='axf-btn'></a>")
				.text(__("Open"))
				.on("click", (e) => {
					e.stopPropagation();
					openNode(n);
				})
				.appendTo($actions);
		}

		if (n.can_create && n.document_type) {
			$("<a class='axf-btn axf-btn-new'></a>")
				.text(__("New"))
				.on("click", (e) => {
					e.stopPropagation();
					frappe.new_doc(n.document_type);
				})
				.appendTo($actions);
		}

		$card.on("click", () => n.route && openNode(n));
		return $card;
	}

	function openNode(n) {
		if (n.is_single && n.document_type) {
			// A Single has no list. Routing it to List raised TableMissingError.
			frappe.set_route("Form", n.document_type);
			return;
		}
		if (n.node_type === "DocType" && n.document_type && n.filters && Object.keys(n.filters).length) {
			frappe.set_route("List", n.document_type, n.filters);
			return;
		}
		if (n.route && n.route.startsWith("/app/")) {
			frappe.set_route(n.route.replace("/app/", ""));
			return;
		}
		if (n.route) {
			window.open(n.route, "_blank");
		}
	}

	function injectStyles() {
		if (document.getElementById("axf-styles")) return;
		const css = `
.axf-wrap{padding:4px 0 40px}
.axf-title{font-size:18px;font-weight:600;color:var(--heading-color)}
.axf-desc{color:var(--text-muted);font-size:13px;margin-top:2px;max-width:760px}
.axf-meta{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0 14px;font-size:11.5px;color:var(--text-muted)}
.axf-meta span{background:var(--fg-color);border:1px solid var(--border-color);
 border-radius:999px;padding:2px 10px}
.axf-lane{display:flex;gap:12px;align-items:stretch;margin-bottom:14px}
.axf-lane-label{flex:0 0 34px;background:var(--lane);border-radius:8px;
 display:flex;align-items:center;justify-content:center;padding:8px 0}
.axf-lane-name{writing-mode:vertical-rl;transform:rotate(180deg);color:#fff;
 font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}
[dir="rtl"] .axf-lane-name{transform:none}
.axf-stages{flex:1 1 auto;display:flex;gap:12px;overflow-x:auto;padding-bottom:4px}
.axf-stage{flex:0 0 268px;background:var(--fg-color);border:1px solid var(--border-color);
 border-radius:8px;padding:10px 11px}
.axf-stage-head{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:9px;
 padding-bottom:7px;border-bottom:1px solid var(--border-color)}
.axf-seq{background:var(--lane);color:#fff;border-radius:5px;font-size:11px;font-weight:700;
 padding:1px 7px;flex:0 0 auto}
.axf-stage-name{font-weight:600;font-size:13px;color:var(--heading-color)}
.axf-actor{font-size:10.5px;color:var(--text-muted);width:100%}
.axf-nodes{display:flex;flex-direction:column;gap:7px}
.axf-node{border:1px solid var(--border-color);border-radius:7px;padding:8px 9px;
 background:var(--card-bg,var(--fg-color));cursor:pointer;transition:.12s}
.axf-node:hover{border-color:var(--lane);box-shadow:0 1px 6px rgba(0,0,0,.07)}
.axf-node.is-std{border-inline-start:3px solid var(--text-muted)}
.axf-node.is-alphax{border-inline-start:3px solid var(--lane)}
.axf-node-top{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.axf-node-label{font-size:12.5px;font-weight:550;color:var(--text-color)}
.axf-count{font-size:11px;font-weight:700;color:var(--text-muted);
 background:var(--control-bg);border-radius:999px;padding:0 7px;flex:0 0 auto}
.axf-node-desc{font-size:11px;color:var(--text-muted);margin-top:3px;line-height:1.4}
.axf-node-foot{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
.axf-tag{font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted)}
.axf-actions{display:flex;gap:6px}
.axf-btn{font-size:11px;padding:1px 8px;border-radius:4px;border:1px solid var(--border-color);
 color:var(--text-muted);cursor:pointer}
.axf-btn:hover{color:var(--text-color);border-color:var(--lane)}
.axf-btn-new{border-color:var(--lane);color:var(--lane)}
.axf-empty{padding:40px;text-align:center;color:var(--text-muted)}
.axf-banner{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px;
 padding:10px 14px;border-radius:8px;border:1px solid var(--yellow-300,#f5d48a);
 background:var(--yellow-50,#fffaeb);color:var(--text-color);font-size:13px}
.axf-banner-dot{width:8px;height:8px;border-radius:50%;background:var(--yellow-500,#e0a800)}
.axf-banner-go{margin-inline-start:auto}
.axf-setup h5{margin:14px 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted)}
.axf-row{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--border-color)}
.axf-row-main{flex:1 1 auto;min-width:0}
.axf-row-title{font-weight:550;font-size:13px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.axf-row-detail{font-size:11.5px;color:var(--text-muted);margin-top:2px}
.axf-row-act{flex:0 0 auto}
.axf-kind{font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);font-weight:400}
.axf-s{flex:0 0 22px;height:22px;width:22px;border-radius:50%;display:inline-grid;place-items:center;
 font-size:12px;font-weight:700}
.axf-s-ok{background:var(--green-100,#dcfce7);color:var(--green-700,#15803d)}
.axf-s-miss{background:var(--red-100,#fee2e2);color:var(--red-700,#b91c1c)}
.axf-s-block{background:var(--yellow-100,#fef3c7);color:var(--yellow-700,#a16207)}
.axf-s-dev{background:var(--blue-100,#dbeafe);color:var(--blue-700,#1d4ed8)}
.axf-s-skip,.axf-s-info{background:var(--control-bg);color:var(--text-muted)}
.axf-legend-s{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--text-muted)}
.axf-legend-s span{display:inline-flex;align-items:center;gap:5px}
.axf-note{font-size:12px;color:var(--text-muted);margin:4px 0 6px}
.axf-warn{color:var(--red-600,#dc2626)}
@media (max-width:768px){.axf-stage{flex:0 0 232px}}
`;
		$(`<style id="axf-styles">${css}</style>`).appendTo(document.head);
	}

	load();
};
