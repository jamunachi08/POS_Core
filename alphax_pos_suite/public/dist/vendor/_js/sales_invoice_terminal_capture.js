frappe.ui.form.on('Sales Invoice Payment', {
  aps_capture_terminal(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.mode_of_payment) {
      frappe.msgprint(__('Please select Mode of Payment first.'));
      return;
    }

    frappe.db.get_value('Mode of Payment', row.mode_of_payment, ['capture_terminal_data','aps_capture_terminal_data','act_capture_terminal_data'])
      .then(r => {
        const d = r.message || {};
        const enabled = !!(d.capture_terminal_data || d.aps_capture_terminal_data || d.act_capture_terminal_data);
        if (!enabled) {
          frappe.msgprint(__('Capture Terminal Data is not enabled for this Mode of Payment.'));
          return;
        }

        frappe.model.set_value(cdt, cdn, 'aps_txn_status', 'PENDING');
        frappe.model.set_value(cdt, cdn, 'aps_captured_on', frappe.datetime.now_datetime());

        const dialog = new frappe.ui.Dialog({
          title: __('Terminal Capture (Testing)'),
          fields: [
            {fieldtype:'Select', fieldname:'status', label:__('Status'), options:'Approved\nDeclined\nError', default:'Approved', reqd:1},
            {fieldtype:'Data', fieldname:'rrn', label:__('RRN'), default: row.aps_rrn || row.reference_no || ''},
            {fieldtype:'Data', fieldname:'auth_code', label:__('Auth Code'), default: row.aps_auth_code || ''},
            {fieldtype:'Data', fieldname:'terminal_id', label:__('Terminal ID (TID)'), default: row.aps_terminal_id || ''},
            {fieldtype:'Data', fieldname:'merchant_id', label:__('Merchant ID (MID)'), default: row.aps_merchant_id || ''},
            {fieldtype:'Data', fieldname:'card_brand', label:__('Card/Tender Brand'), default: row.aps_card_brand || row.mode_of_payment},
          ],
          primary_action_label: __('Save'),
          primary_action(values) {
            frappe.model.set_value(cdt, cdn, 'aps_txn_status', values.status);
            frappe.model.set_value(cdt, cdn, 'aps_rrn', values.rrn || '');
            frappe.model.set_value(cdt, cdn, 'aps_auth_code', values.auth_code || '');
            frappe.model.set_value(cdt, cdn, 'aps_terminal_id', values.terminal_id || '');
            frappe.model.set_value(cdt, cdn, 'aps_merchant_id', values.merchant_id || '');
            frappe.model.set_value(cdt, cdn, 'aps_card_brand', values.card_brand || row.mode_of_payment);
            frappe.model.set_value(cdt, cdn, 'aps_captured_on', frappe.datetime.now_datetime());
            dialog.hide();
          }
        });
        dialog.show();
      });
  }
});
