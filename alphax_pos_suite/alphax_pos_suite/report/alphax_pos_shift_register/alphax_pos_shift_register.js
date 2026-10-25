frappe.query_reports["AlphaX POS Shift Register"] = {
    filters: [
        { fieldname: "from_date", label: __("From Trading Day"), fieldtype: "Date",
          default: frappe.datetime.add_days(frappe.datetime.get_today(), -7) },
        { fieldname: "to_date", label: __("To Trading Day"), fieldtype: "Date",
          default: frappe.datetime.get_today() },
        { fieldname: "terminal", label: __("Terminal"), fieldtype: "Link", options: "AlphaX POS Terminal" },
        { fieldname: "user", label: __("Cashier"), fieldtype: "Link", options: "User" },
    ],
};
