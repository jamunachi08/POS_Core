frappe.pages['alphax_apos'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'AlphaX αPOS',
        single_column: true
    });

    $(wrapper).find('.layout-main-section').html(`
        <div class="apos-hero">
          <h2>AlphaX αPOS</h2>
          <p>Phase-1 base installed successfully. Next phases will add full POS UI (colorful keypad, table layout, split bills, editable bundles).</p>
        </div>
    `);
};
