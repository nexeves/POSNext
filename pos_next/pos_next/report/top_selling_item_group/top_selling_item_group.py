import frappe
from frappe import _


def execute(filters=None):

	columns = get_columns()
	data = get_data(filters)

	return columns, data

def get_columns():

	return [

		{
            "label": "Item Group",
            "fieldname": "item_group",
            "fieldtype": "Data",
            "width": 220
        },

		{
			"label":"Qty",
			"fieldname":"qty",
			"fieldtype":"Float",
			"width":100
		},

		{
			"label":"Sales Value",
			"fieldname":"amount",
			"fieldtype":"Currency",
			"width":140
		},

		{
			"label":"Contribution %",
			"fieldname":"percentage",
			"fieldtype":"Percent",
			"width":120
		}

	]

def get_data(filters):

	branch_condition=""

	if filters.get("branch"):
		branch_condition=" AND si.cost_center=%(branch)s "

	data=frappe.db.sql(f"""

	SELECT
		i.item_group,
		SUM(sii.qty) AS qty,
		SUM(sii.amount) AS amount
	FROM `tabSales Invoice Item` sii
	INNER JOIN `tabSales Invoice` si
		ON si.name = sii.parent
	INNER JOIN `tabItem` i
		ON i.name = sii.item_code
	WHERE
		si.docstatus = 1
		AND si.is_pos = 1
		AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
	GROUP BY i.item_group
	ORDER BY amount DESC
	LIMIT 10;

	""",filters,as_dict=True)

	total=sum(d.amount for d in data)

	for d in data:

		d.percentage=(d.amount/total*100) if total else 0

	return data