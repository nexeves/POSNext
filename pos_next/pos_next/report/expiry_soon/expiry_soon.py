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
			"width": 140,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Batch No"),
			"fieldname": "batch_no",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 150,
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
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Expiry Date"),
			"fieldname": "expiry_date",
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"label": _("Days Left"),
			"fieldname": "days_left",
			"fieldtype": "Int",
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
		conditions += " AND sle.warehouse = %(warehouse)s"

	days = filters.get("days", 30)

	data = frappe.db.sql(
		f"""
		SELECT

			i.name AS item_code,
			i.item_name,
			b.name AS batch_no,
			sle.warehouse,
			SUM(sle.actual_qty) AS qty,
			b.expiry_date,
			DATEDIFF(
				b.expiry_date,
				CURDATE()
			) AS days_left

		FROM `tabBatch` b

		INNER JOIN `tabStock Ledger Entry` sle
			ON sle.batch_no = b.name

		INNER JOIN `tabItem` i
			ON i.name = sle.item_code

		WHERE

			b.expiry_date IS NOT NULL

			AND b.expiry_date >= CURDATE()

			AND b.expiry_date <= DATE_ADD(
				CURDATE(),
				INTERVAL %(days)s DAY
			)

			{conditions}

		GROUP BY
			b.name,
			sle.warehouse

		HAVING
			qty > 0

		ORDER BY
			b.expiry_date ASC
		""",
		{"days": days, **filters},
		as_dict=True,
	)

	for row in data:

		if row.days_left <= 7:
			row.status = "Critical"

		elif row.days_left <= 15:
			row.status = "Warning"

		else:
			row.status = "Normal"

	return data