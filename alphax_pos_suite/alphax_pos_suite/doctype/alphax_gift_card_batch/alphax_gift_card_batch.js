frappe.ui.form.on('AlphaX Gift Card Batch', {
	refresh(frm) {
		const A = 'alphax_pos_suite.alphax_pos_suite.giftcard.api';
		if (frm.doc.status === 'Draft' && !frm.is_new()) {
			frm.add_custom_button(__('Generate cards'), () => frappe.call({ method: `${A}.generate_batch`, args: { batch: frm.doc.name }, freeze: true }).then(() => frm.reload_doc()));
		}
		if (frm.doc.status === 'Generated') {
			frm.add_custom_button(__('Activate (payment received)'), () => frappe.prompt(
				{ fieldname: 'outlet', label: __('Outlet'), fieldtype: 'Link', options: 'AlphaX POS Outlet', reqd: 1 },
				(v) => frappe.call({ method: `${A}.activate_batch`, args: { batch: frm.doc.name, outlet: v.outlet }, freeze: true }).then(() => frm.reload_doc())));
		}
	},
});
