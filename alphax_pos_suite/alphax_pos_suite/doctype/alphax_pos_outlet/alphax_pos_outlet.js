frappe.ui.form.on('AlphaX POS Outlet', {
  refresh(frm) {
    if (frm.is_new()) return;

    // Setting up a lobby screen should be "copy this link", not "find the
    // key field". The key is generated on first click.
    frm.add_custom_button(__('Customer Display Link'), () => {
      frappe.call({
        method: 'alphax_pos_suite.alphax_pos_suite.display.api.get_display_url',
        args: { outlet: frm.doc.name },
        freeze: true,
      }).then(r => {
        const m = r.message;
        if (!m || !m.url) return;
        frappe.msgprint({
          title: __('Customer Display'),
          indicator: 'blue',
          message: `
            <p>${__('Open this on the lobby screen. No login is needed.')}</p>
            <p><a href="${m.url}" target="_blank"><code>${m.url}</code></a></p>
            <p class="text-muted small">${__('Add &lang=en or &lang=ar to call orders in one language only. Clear the Display Key field and save to revoke every screen.')}</p>`,
        });
        frm.reload_doc();
      });
    }, __('Customer Display'));
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
