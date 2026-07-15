import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Brand"),
			"fieldname": "brand",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{
			"label": _("Qty"),
			"fieldname": "actual_qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 120,
		},
	]


def get_data(filters):

	conditions = ""

	if filters.get("warehouse"):
		conditions += " AND b.warehouse = %(warehouse)s"

	data = frappe.db.sql(
		f"""
		SELECT
			b.item_code,
			i.item_name,
			i.item_group,
			i.brand,
			b.warehouse,
			b.actual_qty

		FROM `tabBin` b

		INNER JOIN `tabItem` i
			ON i.name = b.item_code

		WHERE
			i.disabled = 0
			AND b.actual_qty <= 0
			{conditions}

		ORDER BY
			i.item_group,
			i.item_name
		""",
		filters,
		as_dict=True,
	)

	for row in data:

		if row.actual_qty < 0:
			row.status = "Negative Stock"
		else:
			row.status = "Out of Stock"

	return data