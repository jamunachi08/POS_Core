frappe.ui.form.on('AlphaX POS Outlet', {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__('Generate & Print All Table QRs'), () => {
      frappe.call({
        method: 'alphax_pos_suite.alphax_pos_suite.api.generate_outlet_table_tokens',
        args: { outlet: frm.doc.name },
        freeze: true,
        freeze_message: __('Issuing tokens…'),
      }).then(r => {
        const m = r.message;
        if (m && m.ok) {
          frappe.show_alert({ message: __('{0} tables ready', [m.tables]), indicator: 'green' });
          window.open(m.print_all_url, '_blank');
        } else {
          frappe.msgprint((m && m.message) || __('Failed'));
        }
      });
    }, __('Table QR'));
  }
});
