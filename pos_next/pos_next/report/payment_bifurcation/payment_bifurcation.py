import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)

	return columns, data, None, chart

def get_columns():
	return [
		{
			"label": _("Payment Mode"),
			"fieldname": "mode_of_payment",
			"fieldtype": "Data",
			"width": 220
		},
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"width": 160
		},
		{
			"label": _("Percentage"),
			"fieldname": "percentage",
			"fieldtype": "Percent",
			"width": 120
		}
	]

def get_data(filters):

	branch_condition = ""

	if filters.get("branch"):
		branch_condition = " AND si.cost_center = %(branch)s "

	branch_condition_due = ""

	if filters.get("branch"):
		branch_condition_due = " AND cost_center = %(branch)s "


	data = frappe.db.sql(
		f"""
		SELECT

			sip.mode_of_payment,

			SUM(sip.amount) AS amount

		FROM `tabSales Invoice Payment` sip

		INNER JOIN `tabSales Invoice` si

			ON si.name = sip.parent

		WHERE

			si.docstatus = 1

			AND si.is_pos = 1

			AND si.posting_date
				BETWEEN %(from_date)s
				AND %(to_date)s

			{branch_condition}

		GROUP BY sip.mode_of_payment

		ORDER BY amount DESC
		""",
		filters,
		as_dict=True
	)

	total = sum(d.amount for d in data)

	for d in data:
		d.percentage = (d.amount / total * 100) if total else 0

	due = frappe.db.sql(
		f"""
		SELECT

			SUM(outstanding_amount)

		FROM `tabSales Invoice`

		WHERE

			docstatus = 1

			AND is_pos = 1

			AND posting_date BETWEEN %(from_date)s AND %(to_date)s

			{branch_condition_due}
		""",
		filters
	)[0][0] or 0

	if due > 0:
		data.append({
			"mode_of_payment": "Due",
			"amount": due,
			"percentage": 0
		})

		total = sum(d.amount for d in data)

		for d in data:
			d.percentage = (d.amount / total * 100) if total else 0

	return data

	


def get_chart(data):

	return {
		"data": {
			"labels": [d.mode_of_payment for d in data],
			"datasets": [
				{
					"values": [d.amount for d in data]
				}
			]
		},
		"type": "donut",
		"height": 300
	}