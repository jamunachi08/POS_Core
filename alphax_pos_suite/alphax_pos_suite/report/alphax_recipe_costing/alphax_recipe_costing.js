frappe.query_reports["AlphaX Recipe Costing"] = {
	filters: [
		{ fieldname: "outlet", label: __("Outlet"), fieldtype: "Link", options: "AlphaX POS Outlet", reqd: 1 },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -29) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "include_unsold", label: __("Include items with a recipe but no sales"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "menu_class") {
			const c = { Star: "green", Plowhorse: "blue", Puzzle: "orange", Dog: "red" }[data.menu_class];
			if (c) value = `<span class="indicator-pill ${c}">${frappe.utils.escape_html(data.menu_class)}</span>`;
		}
		if ((column.fieldname.startsWith("margin") || column.fieldname === "total_margin") && data[column.fieldname] < 0)
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		if (column.fieldname === "food_cost_pct" && data.food_cost_pct > 35)
			value = `<span style="color:var(--orange-600);font-weight:600">${value}</span>`;
		return value;
	},
};
