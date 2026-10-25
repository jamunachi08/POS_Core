frappe.pages['alphax-pos-setup'].on_page_load = function(wrapper) {
  frappe.ui.make_app_page({
    parent: wrapper,
    title: 'AlphaX POS — Advanced Configuration',
    single_column: true
  });

  // Frappe v15 uses path-based desk routes (/app/<doctype-slug>[/<name>]),
  // NOT the old hash routes (#List/... , #Form/...). Build correct hrefs so
  // the desk router handles the click natively.
  const slug = (dt) => (frappe.router && frappe.router.slug)
    ? frappe.router.slug(dt)
    : (dt || '').toLowerCase().replace(/ /g, '-');

  const routeHref = (l) => {
    const base = '/app/' + slug(l.doctype);
    return l.view === 'form'
      ? base + '/' + encodeURIComponent(l.name || l.doctype)
      : base;  // list view
  };

  const step = (num, title, body, links) => {
    const buttons = (links || []).map(l =>
      `<a class="btn btn-${l.primary ? 'primary' : 'default'} btn-sm mr-2" href="${routeHref(l)}">${l.label}</a>`
    ).join('');
    return `
      <div class="card mb-3">
        <div class="card-body">
          <h4 class="mb-2">${num}) ${title}</h4>
          <div class="text-muted">${body}</div>
          <div class="mt-3">${buttons}</div>
        </div>
      </div>
    `;
  };

  const html = `
    <div class="p-4">
      <div class="alert alert-success">
        <b>AlphaX POS</b> is installed ✅
        <div class="mt-2"><b>New here?</b> Use the one-click guided wizard — it sets up everything for you. The cards below are for advanced, manual configuration.</div>
        <div class="mt-2"><a class="btn btn-primary" href="/app/alphax-pos-setup-wizard">▶ Run the guided setup wizard</a></div>
      </div>

      <div class="alert alert-warning">
        <b>KSA tip:</b> If you use <b>Inclusive VAT</b>, avoid setting <b>Item Tax Template</b> at item line level unless required.
        Bonanza can warn you in POS Settings.
      </div>

      ${step(1, 'POS Settings',
        'Enable/disable boosters: Recipe Consumption, KDS, approvals, inclusive VAT warnings, and more.',
        [
          {label: 'Open Settings', view: 'form', doctype: 'AlphaX POS Settings', name: 'AlphaX POS Settings', primary: true}
        ])}

      ${step(2, 'Outlet (Branch + Warehouse)',
        'Create outlets with default warehouse and company/branch mapping.',
        [
          {label: 'Open Outlets', view: 'list', doctype: 'AlphaX POS Outlet', primary: true}
        ])}

      ${step(3, 'Terminal + POS Profile',
        'Create terminals and link them to POS Profile + Outlet. Configure payment modes and terminal capture if required.',
        [
          {label: 'Open Terminals', view: 'list', doctype: 'AlphaX POS Terminal', primary: true},
          {label: 'Open POS Profiles', view: 'list', doctype: 'POS Profile'}
        ])}

      ${step(4, 'Restaurant Setup (Floors, Tables, Sessions)',
        'Enable Table Management and create floors/tables. Use table sessions for dine-in flow.',
        [
          {label: 'Floors', view: 'list', doctype: 'AlphaX POS Floor', primary: true},
          {label: 'Tables', view: 'list', doctype: 'AlphaX POS Table'}
        ])}

      ${step(5, 'Kitchen Display System (KDS)',
        'Create Kitchen Stations, map items to stations, and start KDS ticket flow.',
        [
          {label: 'Kitchen Stations', view: 'list', doctype: 'AlphaX POS Kitchen Station', primary: true},
          {label: 'Item → Station', view: 'list', doctype: 'AlphaX POS Item Station'}
        ])}

      ${step(6, 'Recipes → Auto Stock Consumption',
        'Create recipes for sold items to automatically create Material Issue Stock Entry when POS Sales Invoice submits.',
        [
          {label: 'Recipes', view: 'list', doctype: 'AlphaX POS Recipe', primary: true},
          {label: 'Processing Log', view: 'list', doctype: 'AlphaX POS Processing Log'}
        ])}

      ${step(7, 'Offers / Combos',
        'Create offer definitions and attach offer items / alternate items.',
        [
          {label: 'Offers', view: 'list', doctype: 'AlphaX POS Offer', primary: true}
        ])}

      ${step(8, 'Start POS',
        'Create orders and submit to generate Sales Invoice + payments + (optional) Stock Consumption.',
        [
          {label: 'POS Orders', view: 'list', doctype: 'AlphaX POS Order', primary: true},
          {label: 'Open Cashier', view: 'page', doctype: 'alphax-cashier'}
        ])}

      <hr/>
      <small class="text-muted">AlphaX Bonanza POS Pack • Booster build</small>
    </div>
  `;

  $(wrapper).html(html);
};
