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

	const $body = $(`
		<div class="axf-wrap">
			<div class="axf-head"></div>
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
@media (max-width:768px){.axf-stage{flex:0 0 232px}}
`;
		$(`<style id="axf-styles">${css}</style>`).appendTo(document.head);
	}

	load();
};
