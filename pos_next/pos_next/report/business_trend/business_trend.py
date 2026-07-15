# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
	if not filters:
		filters = {}

	columns = get_columns()

	data = get_data(filters)

	chart = get_chart(data)

	return columns, data, None, chart


def get_columns() -> list[dict]:
	"""Return columns for the report.

	One field definition per column, just like a DocType field definition.
	"""
	return [
		{
			"label": _("Date"),
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 120
		},
		{
			"label": _("Sales"),
			"fieldname": "sales",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Purchase"),
			"fieldname": "purchase",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Expense"),
			"fieldname": "expense",
			"fieldtype": "Currency",
			"width": 150
		}
	]


def get_data(filters):

	branch_condition = ""

	if filters.get("branch"):
		branch_condition = " AND cost_center = %(branch)s "

	sales = frappe.db.sql(
		f"""
		SELECT
			posting_date,
			SUM(grand_total) AS sales
		FROM `tabSales Invoice`
		WHERE
			docstatus = 1
			AND is_pos = 1
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			{branch_condition}
		GROUP BY posting_date
		""",
		filters,
		as_dict=True
	)

	purchase = frappe.db.sql(
		f"""
		SELECT
			posting_date,
			SUM(grand_total) AS purchase
		FROM `tabPurchase Invoice`
		WHERE
			docstatus = 1
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY posting_date
		""",
		filters,
		as_dict=True
	)

	expense = frappe.db.sql(
		f"""
		SELECT
			posting_date,
			SUM(total_debit) AS expense
		FROM `tabJournal Entry`
		WHERE
			docstatus = 1
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND custom_created_from_pos = 1
		GROUP BY posting_date
		""",
		filters,
		as_dict=True
	)

	return merge_data(sales, purchase, expense)

def merge_data(sales, purchase, expense):

	result = {}

	for row in sales:
		result.setdefault(row.posting_date, {})
		result[row.posting_date]["sales"] = row.sales

	for row in purchase:
		result.setdefault(row.posting_date, {})
		result[row.posting_date]["purchase"] = row.purchase

	for row in expense:
		result.setdefault(row.posting_date, {})
		result[row.posting_date]["expense"] = row.expense

	data = []

	for date in sorted(result):

		data.append({
			"date": date,
			"sales": result[date].get("sales", 0),
			"purchase": result[date].get("purchase", 0),
			"expense": result[date].get("expense", 0)
		})

	return data

def get_chart(data):

	return {
		"data": {
			"labels": [d["date"] for d in data],
			"datasets": [
				{
					"name": "Sales",
					"values": [d["sales"] for d in data]
				},
				{
					"name": "Purchase",
					"values": [d["purchase"] for d in data]
				},
				{
					"name": "Expense",
					"values": [d["expense"] for d in data]
				}
			]
		},
		"type": "line",
		"height": 300
	}