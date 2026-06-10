frappe.pages['alphax-pos-setup'].on_page_load = function(wrapper) {
  frappe.ui.make_app_page({
    parent: wrapper,
    title: 'AlphaX Bonanza POS — Setup Wizard',
    single_column: true
  });

  const step = (num, title, body, links) => {
    const buttons = (links || []).map(l => `<a class="btn btn-${l.primary ? 'primary' : 'default'} btn-sm mr-2" href="${l.href}">${l.label}</a>`).join('');
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
        <b>AlphaX Bonanza POS Pack</b> is installed ✅
        <div class="mt-2">This wizard helps you configure <b>Outlet → Terminal → POS Profile</b> plus Restaurant boosters (Floors, Tables, KDS, Recipes, Offers).</div>
      </div>

      <div class="alert alert-warning">
        <b>KSA tip:</b> If you use <b>Inclusive VAT</b>, avoid setting <b>Item Tax Template</b> at item line level unless required.
        Bonanza can warn you in POS Settings.
      </div>

      ${step(1, 'POS Settings',
        'Enable/disable boosters: Recipe Consumption, KDS, approvals, inclusive VAT warnings, and more.',
        [
          {label: 'Open Settings', href: '#Form/AlphaX POS Settings/AlphaX POS Settings', primary: true}
        ])}

      ${step(2, 'Outlet (Branch + Warehouse)',
        'Create outlets with default warehouse and company/branch mapping.',
        [
          {label: 'Open Outlets', href: '#List/AlphaX POS Outlet/List', primary: true}
        ])}

      ${step(3, 'Terminal + POS Profile',
        'Create terminals and link them to POS Profile + Outlet. Configure payment modes and terminal capture if required.',
        [
          {label: 'Open Terminals', href: '#List/AlphaX POS Terminal/List', primary: true},
          {label: 'Open POS Profiles', href: '#List/POS Profile/List'}
        ])}

      ${step(4, 'Restaurant Setup (Floors, Tables, Sessions)',
        'Enable Table Management and create floors/tables. Use table sessions for dine-in flow.',
        [
          {label: 'Floors', href: '#List/AlphaX POS Floor/List', primary: true},
          {label: 'Tables', href: '#List/AlphaX POS Table/List'}
        ])}

      ${step(5, 'Kitchen Display System (KDS)',
        'Create Kitchen Stations, map items to stations, and start KDS ticket flow.',
        [
          {label: 'Kitchen Stations', href: '#List/AlphaX POS Kitchen Station/List', primary: true},
          {label: 'Item → Station', href: '#List/AlphaX POS Item Station/List'}
        ])}

      ${step(6, 'Recipes → Auto Stock Consumption',
        'Create recipes for sold items to automatically create Material Issue Stock Entry when POS Sales Invoice submits.',
        [
          {label: 'Recipes', href: '#List/AlphaX POS Recipe/List', primary: true},
          {label: 'Processing Log', href: '#List/AlphaX POS Processing Log/List'}
        ])}

      ${step(7, 'Offers / Combos',
        'Create offer definitions and attach offer items / alternate items.',
        [
          {label: 'Offers', href: '#List/AlphaX POS Offer/List', primary: true}
        ])}

      ${step(8, 'Start POS',
        'Create orders and submit to generate Sales Invoice + payments + (optional) Stock Consumption.',
        [
          {label: 'POS Orders', href: '#List/AlphaX POS Order/List', primary: true}
        ])}

      <hr/>
      <small class="text-muted">AlphaX Bonanza POS Pack • Booster build (v0.3.0)</small>
    </div>
  `;

  $(wrapper).html(html);
};
