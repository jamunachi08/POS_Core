frappe.listview_settings['AlphaX POS Central Kitchen Request'] = {
	get_indicator: function(doc) {
		const status = (doc.status || 'Draft');
		if (status === 'Fulfilled') return [__('Fulfilled'), 'green', 'status,=,Fulfilled'];
		if (status === 'Dispatched') return [__('Dispatched'), 'blue', 'status,=,Dispatched'];
		if (status === 'Submitted') return [__('Submitted'), 'orange', 'status,=,Submitted'];
		if (status === 'Cancelled') return [__('Cancelled'), 'red', 'status,=,Cancelled'];
		return [__(status), 'gray', `status,=,${status}`];
	}
};
