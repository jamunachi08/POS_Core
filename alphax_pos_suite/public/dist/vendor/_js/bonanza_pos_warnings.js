frappe.ui.form.on('Sales Invoice', {
  refresh(frm) {
    // Only warn in POS context to avoid noise
    if (!frm.doc.is_pos) return;

    frappe.call({
      method: 'frappe.client.get',
      args: {doctype: 'AlphaX POS Settings', name: 'AlphaX POS Settings'},
      callback: (r) => {
        const settings = r.message || {};
        if (!settings.warn_inclusive_vat_item_tax_template) return;

        // Heuristic: inclusive tax templates commonly have ...
        // We don't hardcode a template name; we just warn if line has template.
        const hasLineTemplate = (frm.doc.items || []).some(i => i.item_tax_template);
        if (hasLineTemplate) {
          frm.dashboard.set_headline_alert(
            __('Bonanza POS: Item Tax Template is set on one or more items. If you use Inclusive VAT, this may cause ZATCA / VAT issues.'),
            'orange'
          );
        }
      }
    });
  }
});
