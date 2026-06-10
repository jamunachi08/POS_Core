frappe.pages['alphax-pos-central-kitchen-dashboard'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Central Kitchen Dashboard'),
		single_column: true
	});

	const $container = $(`
		<div class="ckdash">
			<div class="row">
				<div class="col-sm-3"><div class="card"><div class="card-body"><div class="text-muted">${__('Today')}</div><h3 class="ck-today">0</h3></div></div></div>
				<div class="col-sm-3"><div class="card"><div class="card-body"><div class="text-muted">${__('Submitted')}</div><h3 class="ck-submitted">0</h3></div></div></div>
				<div class="col-sm-3"><div class="card"><div class="card-body"><div class="text-muted">${__('Dispatched')}</div><h3 class="ck-dispatched">0</h3></div></div></div>
				<div class="col-sm-3"><div class="card"><div class="card-body"><div class="text-muted">${__('Fulfilled')}</div><h3 class="ck-fulfilled">0</h3></div></div></div>
			</div>
			<div class="row" style="margin-top: 12px;">
				<div class="col-sm-12">
					<div class="card">
						<div class="card-body">
							<div class="flex justify-between" style="display:flex; justify-content:space-between; align-items:center;">
								<h4 style="margin:0;">${__('Latest Requests')}</h4>
								<div>
									<button class="btn btn-sm btn-default ck-refresh">${__('Refresh')}</button>
									<button class="btn btn-sm btn-primary ck-open-list">${__('Open List')}</button>
								</div>
							</div>
							<div class="ck-latest" style="margin-top:10px;"></div>
						</div>
					</div>
				</div>
			</div>
		</div>
	`);
	$(page.body).append($container);

	function render_latest(rows) {
		if (!rows || !rows.length) {
			$container.find('.ck-latest').html(`<div class="text-muted">${__('No records')}</div>`);
			return;
		}
		const html = rows.map(r => `
			<div class="list-row" style="padding:8px 0; border-bottom:1px solid var(--border-color);">
				<div style="display:flex; justify-content:space-between; align-items:center;">
					<div>
						<a href="#Form/AlphaX POS Central Kitchen Request/${r.name}"><b>${r.name}</b></a>
						<div class="text-muted" style="font-size:12px;">${r.outlet || ''}</div>
					</div>
					<span class="indicator ${r.indicator || 'gray'}">${__(r.status || '')}</span>
				</div>
			</div>
		`).join('');
		$container.find('.ck-latest').html(`<div>${html}</div>`);
	}

	async function refresh() {
		$container.find('.ck-refresh').prop('disabled', true);
		try {
			const r = await frappe.call({ method: 'alphax_pos_suite.alphax_pos_suite.api.get_central_kitchen_dashboard_data' });
			const d = r.message || {};
			$container.find('.ck-today').text(d.today_total || 0);
			$container.find('.ck-submitted').text(d.submitted || 0);
			$container.find('.ck-dispatched').text(d.dispatched || 0);
			$container.find('.ck-fulfilled').text(d.fulfilled || 0);
			render_latest(d.latest || []);
		} finally {
			$container.find('.ck-refresh').prop('disabled', false);
		}
	}

	$container.on('click', '.ck-refresh', refresh);
	$container.on('click', '.ck-open-list', () => {
		frappe.set_route('List', 'AlphaX POS Central Kitchen Request');
	});

	refresh();
};
