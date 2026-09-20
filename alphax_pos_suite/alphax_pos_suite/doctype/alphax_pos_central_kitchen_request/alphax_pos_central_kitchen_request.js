frappe.ui.form.on('AlphaX POS Central Kitchen Request', {
	refresh(frm) {
		const is_submitted = frm.doc.docstatus === 1;
		const status = (frm.doc.status || '');
		const has_mr = !!(frm.doc.erpnext_material_request || frm.doc.material_request || '');
		const has_se = !!(frm.doc.erpnext_stock_entry || frm.doc.stock_entry || '');

		// --- Create Material Request (manual)
		if (is_submitted && !has_mr && ['Submitted', 'Dispatched'].includes(status)) {
			frm.add_custom_button(__('Create Material Request'), () => {
				frappe.confirm(
					__('This will create an ERPNext Material Request (only if ERPNext is installed and Central Kitchen integration is enabled). Continue?'),
					() => {
						frappe.call({
							method: 'alphax_pos_suite.alphax_pos_suite.api.create_material_request_for_central_kitchen_request',
							args: { request_name: frm.doc.name },
							freeze: true,
							callback: (r) => {
								if (r.message && r.message.ok) {
									frappe.show_alert({ message: __('Material Request created'), indicator: 'green' });
									frm.reload_doc();
								} else {
									frappe.msgprint({
										title: __('Failed'),
										message: (r.message && r.message.message) ? r.message.message : __('Material Request was not created. Check settings and error logs.'),
										indicator: 'red'
									});
								}
							}
						});
					}
				);
			}, __('Actions'));
		}

		// --- Dispatch (marks Dispatched; does not create Stock Entry)
		if (is_submitted && status === 'Submitted') {
			frm.add_custom_button(__('Dispatch'), async () => {
				const d = await frappe.prompt([
					{ fieldname: 'dispatch_notes', label: __('Dispatch Notes'), fieldtype: 'Small Text' }
				], __('Dispatch Request'), __('Dispatch'));

				frappe.call({
					method: 'alphax_pos_suite.alphax_pos_suite.api.dispatch_central_kitchen_request',
					args: { request_name: frm.doc.name, notes: d.dispatch_notes || '' },
					freeze: true,
					callback: (r) => {
						if (r.message && r.message.ok) {
							frappe.show_alert({ message: __('Dispatched'), indicator: 'green' });
							frm.reload_doc();
						} else {
							frappe.msgprint({
								title: __('Failed'),
								message: (r.message && r.message.message) ? r.message.message : __('Could not dispatch. Check error logs.'),
								indicator: 'red'
							});
						}
					}
				});
			}, __('Actions')).addClass('btn-primary');
		}

		// --- Fulfill + Create Stock Entry
		if (is_submitted && !['Fulfilled', 'Cancelled'].includes(status)) {
			frm.add_custom_button(__('Fulfill + Create Stock Entry'), () => {
				frappe.confirm(
					__('This will mark the request as Fulfilled and (optionally) create ERPNext Stock Entry based on settings. Continue?'),
					() => {
						frappe.call({
							method: 'alphax_pos_suite.alphax_pos_suite.api.fulfill_central_kitchen_request',
							args: { request_name: frm.doc.name },
							freeze: true,
							callback: (r) => {
								if (r.message && r.message.ok) {
									frappe.show_alert({ message: __('Fulfilled'), indicator: 'green' });
									frm.reload_doc();
								} else {
									frappe.msgprint({
										title: __('Failed'),
										message: (r.message && r.message.message) ? r.message.message : __('Could not fulfill the request. Check error logs.'),
										indicator: 'red'
									});
								}
							}
						});
					}
				);
			}, __('Actions'));
		}
	}
});
