import frappe
from frappe import _


def execute(filters=None):

	columns = get_columns()
	data = get_data(filters)

	return columns, data

def get_columns():

	return [

		{
			"label":"Item",
			"fieldname":"item_code",
			"fieldtype":"Link",
			"options":"Item",
			"width":220
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

		sii.item_code,

		SUM(sii.qty) qty,

		SUM(sii.amount) amount

	FROM `tabSales Invoice Item` sii

	INNER JOIN `tabSales Invoice` si

		ON si.name=sii.parent

	WHERE

		si.docstatus=1

		AND si.is_pos=1

		AND si.posting_date
			BETWEEN %(from_date)s
			AND %(to_date)s

		{branch_condition}

	GROUP BY sii.item_code

	ORDER BY amount DESC

	LIMIT 10

	""",filters,as_dict=True)

	total=sum(d.amount for d in data)

	for d in data:

		d.percentage=(d.amount/total*100) if total else 0

	return data