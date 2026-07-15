frappe.query_reports["Out of Stock"] = {

	filters: [
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

		if (data.status === "Out of Stock") {
			value = `<span style="color:#dc2626;font-weight:bold">${value}</span>`;
		}

		if (data.status === "Negative Stock") {
			value = `<span style="color:#7f1d1d;font-weight:bold">${value}</span>`;
		}

		return value;
	}
};