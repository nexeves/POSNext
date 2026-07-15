frappe.query_reports["Expiry Soon"] = {

	filters: [
		{
			fieldname: "days",
			label: __("Expire Within (Days)"),
			fieldtype: "Int",
			default: 30,
			reqd: 1
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse"
		}
	],

	formatter(value, row, column, data, default_formatter) {

		value = default_formatter(value, row, column, data);

		if (!data) {
			return value;
		}

		if (data.status === "Critical") {
			value = `<span style="color:#dc2626;font-weight:bold">${value}</span>`;
		}

		else if (data.status === "Warning") {
			value = `<span style="color:#ea580c;font-weight:bold">${value}</span>`;
		}

		else if (data.status === "Normal") {
			value = `<span style="color:#ca8a04;font-weight:bold">${value}</span>`;
		}

		return value;
	}
};