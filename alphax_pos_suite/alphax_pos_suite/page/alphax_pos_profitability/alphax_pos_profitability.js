frappe.pages['alphax-pos-profitability'].on_page_load = function(wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: 'AlphaX POS Profitability',
    single_column: true
  });

  const $container = $(`
    <div class="p-3">
      <div class="form-group">
        <label>Item Code</label>
        <input type="text" class="form-control" id="item_code" placeholder="e.g. ITEM-001">
      </div>
      <button class="btn btn-primary" id="btn_calc">Compute Recipe Cost</button>
      <hr/>
      <pre id="out" style="background:#1111; padding:12px; border-radius:8px;"></pre>
      <p class="text-muted">Cost uses AlphaX POS Recipe components valuation_rate (fallback: Item valuation_rate).</p>
    </div>
  `).appendTo(page.body);

  $container.find('#btn_calc').on('click', () => {
    const item_code = $container.find('#item_code').val();
    frappe.call({
      method: 'alphax_pos_suite.alphax_pos_suite.api.compute_recipe_cost',
      args: { item_code },
      callback: (r) => {
        $container.find('#out').text(JSON.stringify(r.message || {}, null, 2));
      }
    });
  });
}
