frappe.ui.form.on('AlphaX POS Table', {
  refresh(frm) {
    if (frm.is_new()) return;

    frm.add_custom_button(__('Show / Print Order QR'), () => {
      frappe.call({
        method: 'alphax_pos_suite.alphax_pos_suite.api.ensure_table_token',
        args: { table: frm.doc.name, rotate: 0 },
        freeze: true,
        freeze_message: __('Preparing QR…'),
      }).then(r => {
        const m = r.message;
        if (m && m.ok) window.open(m.print_url, '_blank');
        else frappe.msgprint((m && m.message) || __('Could not create token'));
      });
    }, __('Order QR'));

    frm.add_custom_button(__('Rotate Token'), () => {
      frappe.confirm(
        __('Rotate this token? The current printed QR will stop working.'),
        () => {
          frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.api.ensure_table_token',
            args: { table: frm.doc.name, rotate: 1 },
          }).then(r => {
            const m = r.message;
            if (m && m.ok) {
              frappe.show_alert({ message: __('New token issued'), indicator: 'green' });
              window.open(m.print_url, '_blank');
            }
          });
        }
      );
    }, __('Order QR'));
  }
});
