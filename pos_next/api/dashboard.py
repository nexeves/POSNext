# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Aggregation layer behind the POS Day Book desk page.

A single whitelisted entry point (`get_day_book`) returns every section the page
renders — KPI tiles, charts, the invoice-level ledger and the shift cash
reconciliation — so the page makes exactly one round trip per filter change.

All queries share one condition builder so that a filter the owner picks at the
top of the page applies identically to every number on the screen.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, nowdate

LEDGER_LIMIT = 500
EXPENSE_LIMIT = 200
# The charts plot the leading TOP_N; the detail tables list the full TOP_N_TABLE.
TOP_N = 10
TOP_N_TABLE = 20


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_day_book(filters=None):
	"""Return every dashboard section for the given filter set."""
	frappe.has_permission("Sales Invoice", throw=True)

	filters = parse_filters(filters)

	return {
		"kpis": get_kpis(filters),
		"trend": get_trend(filters),
		"payments": get_payment_split(filters),
		"top_items": get_top_items(filters),
		"top_groups": get_top_item_groups(filters),
		"cashiers": get_cashier_split(filters),
		"expenses": get_expenses(filters),
		"ledger": get_ledger(filters),
		"shifts": get_shift_reconciliation(filters),
		"meta": {
			"currency": get_currency(filters),
			"from_date": filters["from_date"],
			"to_date": filters["to_date"],
			"granularity": get_granularity(filters),
			"pos_only": filters["pos_only"],
		},
	}


def parse_filters(filters):
	"""Normalise the raw filter payload coming from the desk page."""
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except json.JSONDecodeError:
			frappe.throw(_("Could not parse dashboard filters"))

	if not isinstance(filters, dict):
		filters = {}

	# Drop empty strings so `filters.get(...)` reads as "not set".
	filters = {k: v for k, v in filters.items() if v not in (None, "", [])}

	filters["from_date"] = getdate(filters.get("from_date") or nowdate())
	filters["to_date"] = getdate(filters.get("to_date") or nowdate())

	if filters["from_date"] > filters["to_date"]:
		filters["from_date"], filters["to_date"] = filters["to_date"], filters["from_date"]

	# POS-only is the default view; the owner can widen it to all invoices.
	filters["pos_only"] = cint(filters.get("pos_only", 1))

	# A shift is picked as a POS Closing Shift, but invoices carry the *opening*
	# shift, so resolve the link once here rather than in every query.
	if filters.get("shift"):
		filters["opening_shift"] = frappe.db.get_value(
			"POS Closing Shift", filters["shift"], "pos_opening_shift"
		)

	return filters


def get_currency(filters):
	company = filters.get("company") or frappe.defaults.get_user_default("company")
	if company:
		return frappe.get_cached_value("Company", company, "default_currency")
	return frappe.db.get_default("currency")


# ---------------------------------------------------------------------------
# Condition builders
# ---------------------------------------------------------------------------


def get_si_conditions(filters, alias="si", date_field="posting_date"):
	"""Build the shared WHERE fragment for Sales Invoice based queries.

	Only pre-built fragments are interpolated into the SQL; every user supplied
	value is bound through the `%(name)s` params dict.
	"""
	conditions = [
		f"{alias}.docstatus = 1",
		f"{alias}.{date_field} BETWEEN %(from_date)s AND %(to_date)s",
	]

	if filters.get("pos_only"):
		conditions.append(f"{alias}.is_pos = 1")

	if filters.get("company"):
		conditions.append(f"{alias}.company = %(company)s")

	if filters.get("cost_center"):
		conditions.append(f"{alias}.cost_center = %(cost_center)s")

	if filters.get("pos_profile"):
		conditions.append(f"{alias}.pos_profile = %(pos_profile)s")

	if filters.get("cashier"):
		conditions.append(f"{alias}.owner = %(cashier)s")

	if filters.get("opening_shift"):
		conditions.append(f"{alias}.posa_pos_opening_shift = %(opening_shift)s")
	elif filters.get("shift"):
		# Shift selected but it has no opening shift linked — match nothing
		# rather than silently returning the unfiltered figures.
		conditions.append("1 = 0")

	if filters.get("mode_of_payment"):
		conditions.append(
			f"""EXISTS (
				SELECT 1 FROM `tabSales Invoice Payment` mop_f
				WHERE mop_f.parent = {alias}.name
					AND mop_f.mode_of_payment = %(mode_of_payment)s
			)"""
		)

	return " AND ".join(conditions)


def run(query, filters, as_dict=True):
	"""Execute a query with the filter dict as bound parameters."""
	return frappe.db.sql(query, filters, as_dict=as_dict)


def with_period(filters, from_date, to_date):
	"""Copy of the filters pointing at a different period (for comparisons)."""
	period = filters.copy()
	period["from_date"] = from_date
	period["to_date"] = to_date
	return period


def get_previous_period(filters):
	"""The immediately preceding window of equal length."""
	days = date_diff(filters["to_date"], filters["from_date"]) + 1
	prev_to = add_days(filters["from_date"], -1)
	prev_from = add_days(prev_to, -(days - 1))
	return with_period(filters, prev_from, prev_to)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


def get_kpis(filters):
	"""Return the KPI tiles, each with its previous-period comparison."""
	current = collect_totals(filters)
	previous = collect_totals(get_previous_period(filters))

	# label, key, fieldtype, tone — tone drives the tile accent on the page.
	spec = [
		(_("Gross Sales"), "gross_sales", "Currency", "positive"),
		(_("Returns"), "returns_amount", "Currency", "negative"),
		(_("Net Sales"), "net_sales", "Currency", "primary"),
		(_("Discount"), "total_discount", "Currency", "warning"),
		(_("Tax"), "total_tax", "Currency", "neutral"),
		(_("Write Off"), "write_off", "Currency", "warning"),
		(_("Invoices"), "invoice_count", "Int", "neutral"),
		(_("Returns Count"), "return_count", "Int", "negative"),
		(_("Avg Ticket"), "avg_ticket", "Currency", "primary"),
		(_("Items Sold"), "items_sold", "Float", "neutral"),
		(_("Collected"), "collected", "Currency", "positive"),
		(_("Cash Collected"), "cash_collected", "Currency", "positive"),
		(_("Credit / Outstanding"), "outstanding", "Currency", "warning"),
		(_("POS Expense"), "pos_expense", "Currency", "negative"),
		(_("Purchase"), "purchase", "Currency", "neutral"),
		(_("Net Cash Position"), "net_cash", "Currency", "primary"),
	]

	kpis = []
	for label, key, fieldtype, tone in spec:
		value = flt(current.get(key))
		prev_value = flt(previous.get(key))
		kpis.append(
			{
				"key": key,
				"label": label,
				"fieldtype": fieldtype,
				"tone": tone,
				"value": value,
				"prev_value": prev_value,
				"delta_pct": pct_change(value, prev_value),
			}
		)

	return kpis


def pct_change(value, prev_value):
	if not prev_value:
		return None
	return flt((value - prev_value) / abs(prev_value) * 100, 2)


def collect_totals(filters):
	"""All scalar figures for one period, as a flat dict."""
	totals = get_invoice_totals(filters)
	totals.update(get_payment_totals(filters))
	totals["pos_expense"] = get_pos_expense(filters)
	totals["purchase"] = get_purchase_total(filters)

	totals["avg_ticket"] = (
		flt(totals["gross_sales"]) / totals["invoice_count"] if totals["invoice_count"] else 0.0
	)
	totals["net_cash"] = flt(totals["cash_collected"]) - flt(totals["pos_expense"])

	return totals


def get_invoice_totals(filters):
	"""Sales Invoice aggregates.

	Returns carry `is_return = 1` with negative totals, so gross and returns are
	split explicitly instead of letting them net each other out.
	"""
	conditions = get_si_conditions(filters)

	row = run(
		f"""
		SELECT
			SUM(CASE WHEN si.is_return = 0 THEN si.base_grand_total ELSE 0 END) AS gross_sales,
			ABS(SUM(CASE WHEN si.is_return = 1 THEN si.base_grand_total ELSE 0 END)) AS returns_amount,
			SUM(si.base_grand_total) AS net_sales,
			SUM(si.base_discount_amount) AS total_discount,
			SUM(si.base_total_taxes_and_charges) AS total_tax,
			SUM(si.base_write_off_amount) AS write_off,
			SUM(CASE WHEN si.is_return = 0 THEN 1 ELSE 0 END) AS invoice_count,
			SUM(CASE WHEN si.is_return = 1 THEN 1 ELSE 0 END) AS return_count,
			SUM(si.total_qty) AS items_sold,
			SUM(si.outstanding_amount) AS outstanding
		FROM `tabSales Invoice` si
		WHERE {conditions}
		""",
		filters,
	)

	row = row[0] if row else {}

	return {
		"gross_sales": flt(row.get("gross_sales")),
		"returns_amount": flt(row.get("returns_amount")),
		"net_sales": flt(row.get("net_sales")),
		"total_discount": flt(row.get("total_discount")),
		"total_tax": flt(row.get("total_tax")),
		"write_off": flt(row.get("write_off")),
		"invoice_count": cint(row.get("invoice_count")),
		"return_count": cint(row.get("return_count")),
		"items_sold": flt(row.get("items_sold")),
		"outstanding": flt(row.get("outstanding")),
	}


def get_payment_totals(filters):
	"""Amounts actually tendered, split out by cash vs everything else."""
	conditions = get_si_conditions(filters)

	row = run(
		f"""
		SELECT
			SUM(sip.base_amount) AS collected,
			SUM(CASE WHEN mop.type = 'Cash' THEN sip.base_amount ELSE 0 END) AS cash_collected
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		LEFT JOIN `tabMode of Payment` mop ON mop.name = sip.mode_of_payment
		WHERE {conditions}
		""",
		filters,
	)

	row = row[0] if row else {}

	return {
		"collected": flt(row.get("collected")),
		"cash_collected": flt(row.get("cash_collected")),
	}


def get_je_conditions(filters):
	"""Shared WHERE fragment for the POS-linked Journal Entries.

	Every query runs through `Journal Entry Account` so the KPI, the by-account
	split and the entry list are all summing the same debit rows — a Journal
	Entry has no parent cost center, it lives on the accounts row.
	"""
	conditions = [
		"je.docstatus = 1",
		"je.custom_created_from_pos = 1",
		"je.posting_date BETWEEN %(from_date)s AND %(to_date)s",
		"jea.debit > 0",
	]

	if filters.get("company"):
		conditions.append("je.company = %(company)s")

	if filters.get("pos_profile"):
		conditions.append("je.custom_pos_profile = %(pos_profile)s")

	if filters.get("opening_shift"):
		# custom_pos_shift links to the POS *Opening* Shift, while the filter is
		# picked as a Closing Shift — compare against the resolved opening shift.
		conditions.append("je.custom_pos_shift = %(opening_shift)s")
	elif filters.get("shift"):
		conditions.append("1 = 0")

	if filters.get("cost_center"):
		conditions.append("jea.cost_center = %(cost_center)s")

	return " AND ".join(conditions)


def get_pos_expense(filters):
	"""Total of the Journal Entries raised from the POS (shift expenses)."""
	row = run(
		f"""
		SELECT SUM(jea.debit) AS expense
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE {get_je_conditions(filters)}
		""",
		filters,
	)

	return flt(row[0].get("expense")) if row else 0.0


def get_purchase_total(filters):
	"""Purchase Invoice totals for the same window.

	Purchase Invoice has no parent cost center — it lives on the item rows — so
	a branch filter has to aggregate through `Purchase Invoice Item`.
	"""
	conditions = [
		"pi.docstatus = 1",
		"pi.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]

	if filters.get("company"):
		conditions.append("pi.company = %(company)s")

	if filters.get("cost_center"):
		conditions.append("pii.cost_center = %(cost_center)s")

		query = f"""
			SELECT SUM(pii.base_net_amount) AS purchase
			FROM `tabPurchase Invoice` pi
			INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
			WHERE {" AND ".join(conditions)}
		"""
	else:
		query = f"""
			SELECT SUM(pi.base_net_total) AS purchase
			FROM `tabPurchase Invoice` pi
			WHERE {" AND ".join(conditions)}
		"""

	row = run(query, filters)

	return flt(row[0].get("purchase")) if row else 0.0


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def get_granularity(filters):
	"""Bucket size for the trend chart, derived from the selected range.

	A single day is the true day-book case, so it drops to hourly buckets.
	"""
	days = date_diff(filters["to_date"], filters["from_date"]) + 1

	if days <= 1:
		return "hour"
	if days <= 62:
		return "day"
	return "month"


def get_trend(filters):
	"""Sales vs Returns vs Net over time, with empty buckets filled in."""
	granularity = get_granularity(filters)
	conditions = get_si_conditions(filters)

	bucket = {
		"hour": "HOUR(si.posting_time)",
		"day": "si.posting_date",
		"month": "DATE_FORMAT(si.posting_date, '%%Y-%%m')",
	}[granularity]

	rows = run(
		f"""
		SELECT
			{bucket} AS bucket,
			SUM(CASE WHEN si.is_return = 0 THEN si.base_grand_total ELSE 0 END) AS sales,
			ABS(SUM(CASE WHEN si.is_return = 1 THEN si.base_grand_total ELSE 0 END)) AS returns_amount,
			SUM(si.base_grand_total) AS net
		FROM `tabSales Invoice` si
		WHERE {conditions}
		GROUP BY bucket
		ORDER BY bucket
		""",
		filters,
	)

	values = {str(r["bucket"]): r for r in rows}
	labels, keys = build_buckets(filters, granularity)

	return {
		"granularity": granularity,
		"labels": labels,
		"datasets": [
			{
				"name": _("Sales"),
				"chartType": "bar",
				"values": [flt(values.get(k, {}).get("sales")) for k in keys],
			},
			{
				"name": _("Returns"),
				"chartType": "bar",
				"values": [flt(values.get(k, {}).get("returns_amount")) for k in keys],
			},
			{
				"name": _("Net"),
				"chartType": "line",
				"values": [flt(values.get(k, {}).get("net")) for k in keys],
			},
		],
	}


def build_buckets(filters, granularity):
	"""Every bucket in the range, so gaps render as zero instead of collapsing."""
	if granularity == "hour":
		return [f"{h:02d}:00" for h in range(24)], [str(h) for h in range(24)]

	if granularity == "day":
		labels, keys = [], []
		day = filters["from_date"]
		while day <= filters["to_date"]:
			labels.append(frappe.format(day, {"fieldtype": "Date"}))
			keys.append(str(day))
			day = add_days(day, 1)
		return labels, keys

	labels, keys = [], []
	year, month = filters["from_date"].year, filters["from_date"].month
	end_year, end_month = filters["to_date"].year, filters["to_date"].month
	while (year, month) <= (end_year, end_month):
		key = f"{year}-{month:02d}"
		labels.append(key)
		keys.append(key)
		month += 1
		if month > 12:
			month, year = 1, year + 1
	return labels, keys


def get_payment_split(filters):
	"""Tendered amount per mode of payment, plus a synthetic credit slice."""
	conditions = get_si_conditions(filters)

	rows = run(
		f"""
		SELECT
			sip.mode_of_payment AS label,
			SUM(sip.base_amount) AS value
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE {conditions}
		GROUP BY sip.mode_of_payment
		ORDER BY value DESC
		""",
		filters,
	)

	rows = [{"label": r["label"], "value": flt(r["value"])} for r in rows if flt(r["value"])]

	# Unpaid POS invoices never appear in Sales Invoice Payment, so surface them
	# as their own slice rather than losing them from the split.
	outstanding = run(
		f"""
		SELECT SUM(si.outstanding_amount) AS due
		FROM `tabSales Invoice` si
		WHERE {conditions}
		""",
		filters,
	)
	due = flt(outstanding[0].get("due")) if outstanding else 0.0

	if due > 0:
		rows.append({"label": _("Credit / Due"), "value": due})

	total = sum(r["value"] for r in rows)
	for r in rows:
		r["percentage"] = flt(r["value"] / total * 100, 2) if total else 0.0

	return rows


def get_item_sales_total(filters):
	"""Total item sales value for the period.

	Contribution % is a share of everything sold, not a share of the top slice —
	otherwise the percentages always add up to 100 no matter how narrow the list.
	"""
	conditions = get_si_conditions(filters)

	row = run(
		f"""
		SELECT SUM(sii.base_net_amount) AS total
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {conditions}
		""",
		filters,
	)

	return flt(row[0].get("total")) if row else 0.0


def get_top_items(filters):
	conditions = get_si_conditions(filters)
	total = get_item_sales_total(filters)

	rows = run(
		f"""
		SELECT
			sii.item_code,
			sii.item_name AS label,
			sii.item_group,
			SUM(sii.qty) AS qty,
			SUM(sii.base_net_amount) AS value
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {conditions}
		GROUP BY sii.item_code, sii.item_name, sii.item_group
		ORDER BY value DESC
		LIMIT {TOP_N_TABLE}
		""",
		filters,
	)

	return [
		{
			"item_code": r["item_code"],
			"label": r["label"] or r["item_code"],
			"item_group": r["item_group"] or _("Not Set"),
			"qty": flt(r["qty"]),
			"value": flt(r["value"]),
			"percentage": flt(flt(r["value"]) / total * 100, 2) if total else 0.0,
		}
		for r in rows
	]


def get_top_item_groups(filters):
	conditions = get_si_conditions(filters)
	total = get_item_sales_total(filters)

	rows = run(
		f"""
		SELECT
			sii.item_group AS label,
			COUNT(DISTINCT sii.item_code) AS item_count,
			SUM(sii.qty) AS qty,
			SUM(sii.base_net_amount) AS value
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {conditions}
		GROUP BY sii.item_group
		ORDER BY value DESC
		LIMIT {TOP_N_TABLE}
		""",
		filters,
	)

	return [
		{
			"label": r["label"] or _("Not Set"),
			"item_count": cint(r["item_count"]),
			"qty": flt(r["qty"]),
			"value": flt(r["value"]),
			"percentage": flt(flt(r["value"]) / total * 100, 2) if total else 0.0,
		}
		for r in rows
	]


def get_cashier_split(filters):
	conditions = get_si_conditions(filters)

	rows = run(
		f"""
		SELECT
			si.owner AS cashier,
			SUM(CASE WHEN si.is_return = 0 THEN si.base_grand_total ELSE 0 END) AS value,
			SUM(CASE WHEN si.is_return = 0 THEN 1 ELSE 0 END) AS invoice_count
		FROM `tabSales Invoice` si
		WHERE {conditions}
		GROUP BY si.owner
		ORDER BY value DESC
		LIMIT {TOP_N}
		""",
		filters,
	)

	names = resolve_user_names([r["cashier"] for r in rows])

	return [
		{
			"cashier": r["cashier"],
			"label": names.get(r["cashier"]) or r["cashier"],
			"value": flt(r["value"]),
			"invoice_count": cint(r["invoice_count"]),
		}
		for r in rows
	]


def resolve_user_names(user_ids):
	"""Batch resolve user ids to full names in one query."""
	user_ids = [u for u in set(user_ids) if u]
	if not user_ids:
		return {}

	return {
		u.name: u.full_name
		for u in frappe.get_all("User", filters={"name": ["in", user_ids]}, fields=["name", "full_name"])
	}


# ---------------------------------------------------------------------------
# POS expenses
# ---------------------------------------------------------------------------


def get_expenses(filters):
	"""POS-linked Journal Entries, split by account and listed individually."""
	return {
		"by_account": get_expense_by_account(filters),
		"rows": get_expense_entries(filters),
		"total": get_pos_expense(filters),
	}


def get_expense_by_account(filters):
	total = get_pos_expense(filters)

	rows = run(
		f"""
		SELECT
			jea.account AS label,
			SUM(jea.debit) AS value,
			COUNT(DISTINCT je.name) AS entry_count
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE {get_je_conditions(filters)}
		GROUP BY jea.account
		ORDER BY value DESC
		LIMIT {TOP_N_TABLE}
		""",
		filters,
	)

	return [
		{
			"label": r["label"],
			"entry_count": cint(r["entry_count"]),
			"value": flt(r["value"]),
			"percentage": flt(flt(r["value"]) / total * 100, 2) if total else 0.0,
		}
		for r in rows
	]


def get_expense_entries(filters):
	"""One row per POS expense voucher.

	Grouped over the accounts rows rather than read off `total_debit` so a cost
	center filter narrows the amount to the matching rows, exactly as the KPI does.
	"""
	rows = run(
		f"""
		SELECT
			je.name,
			je.posting_date,
			je.user_remark,
			je.custom_pos_profile AS pos_profile,
			je.custom_pos_shift AS shift,
			je.owner,
			SUM(jea.debit) AS amount,
			GROUP_CONCAT(DISTINCT jea.account ORDER BY jea.account SEPARATOR ', ') AS accounts
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE {get_je_conditions(filters)}
		GROUP BY je.name
		ORDER BY je.posting_date DESC, je.name DESC
		LIMIT {EXPENSE_LIMIT + 1}
		""",
		filters,
	)

	has_more = len(rows) > EXPENSE_LIMIT
	rows = rows[:EXPENSE_LIMIT]

	names = resolve_user_names([r["owner"] for r in rows])
	for r in rows:
		r["raised_by"] = names.get(r["owner"]) or r["owner"]
		r["user_remark"] = (r["user_remark"] or "").strip()

	return {"rows": rows, "has_more": has_more, "limit": EXPENSE_LIMIT}


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def get_ledger(filters):
	"""Invoice-level day book rows."""
	conditions = get_si_conditions(filters)

	rows = run(
		f"""
		SELECT
			si.name,
			si.posting_date,
			si.posting_time,
			si.customer,
			si.customer_name,
			si.owner,
			si.cost_center,
			si.pos_profile,
			si.is_return,
			si.total_qty,
			si.base_grand_total,
			si.base_discount_amount,
			si.base_total_taxes_and_charges,
			si.base_net_total,
			si.outstanding_amount,
			(
				SELECT GROUP_CONCAT(DISTINCT p.mode_of_payment ORDER BY p.mode_of_payment SEPARATOR ', ')
				FROM `tabSales Invoice Payment` p
				WHERE p.parent = si.name
			) AS modes
		FROM `tabSales Invoice` si
		WHERE {conditions}
		ORDER BY si.posting_date DESC, si.posting_time DESC, si.name DESC
		LIMIT {LEDGER_LIMIT + 1}
		""",
		filters,
	)

	has_more = len(rows) > LEDGER_LIMIT
	rows = rows[:LEDGER_LIMIT]

	names = resolve_user_names([r["owner"] for r in rows])
	for r in rows:
		r["cashier"] = names.get(r["owner"]) or r["owner"]
		r["posting_time"] = str(r["posting_time"] or "")[:8]
		r["modes"] = r["modes"] or (_("Credit") if flt(r["outstanding_amount"]) else "")

	return {"rows": rows, "has_more": has_more, "limit": LEDGER_LIMIT}


def get_shift_reconciliation(filters):
	"""Cash position per POS Closing Shift.

	Mirrors the aggregation in the Payments and Cash Control Report, reduced to
	one row per shift with a Balanced / Short / Excess verdict.
	"""
	conditions = [
		"pcs.docstatus = 1",
		"pcs.period_end_date BETWEEN %(from_date)s AND %(to_date)s",
	]

	if filters.get("company"):
		conditions.append("pcs.company = %(company)s")

	if filters.get("pos_profile"):
		conditions.append("pcs.pos_profile = %(pos_profile)s")

	if filters.get("cashier"):
		conditions.append("pcs.user = %(cashier)s")

	if filters.get("shift"):
		conditions.append("pcs.name = %(shift)s")

	if filters.get("mode_of_payment"):
		conditions.append("pd.mode_of_payment = %(mode_of_payment)s")

	# A closing shift carries no cost center of its own — it inherits the one on
	# its POS Profile, so a branch filter has to reach through the profile.
	profile_join = ""
	if filters.get("cost_center"):
		profile_join = "INNER JOIN `tabPOS Profile` pp ON pp.name = pcs.pos_profile"
		conditions.append("pp.cost_center = %(cost_center)s")

	rows = run(
		f"""
		SELECT
			pcs.name AS shift,
			pcs.pos_profile,
			pcs.user,
			pcs.posting_date,
			pcs.period_start_date,
			pcs.period_end_date,
			pcs.grand_total,
			pcs.total_quantity,
			pcs.custom_bank_deposit,
			SUM(pd.opening_amount) AS opening,
			SUM(pd.expected_amount) AS expected,
			SUM(pd.closing_amount) AS closing,
			SUM(pd.difference) AS difference
		FROM `tabPOS Closing Shift` pcs
		LEFT JOIN `tabPOS Closing Shift Detail` pd ON pd.parent = pcs.name
		{profile_join}
		WHERE {" AND ".join(conditions)}
		GROUP BY pcs.name
		ORDER BY pcs.period_end_date DESC
		LIMIT 100
		""",
		filters,
	)

	names = resolve_user_names([r["user"] for r in rows])
	deposits = resolve_deposits([r["custom_bank_deposit"] for r in rows])

	for r in rows:
		r["cashier"] = names.get(r["user"]) or r["user"]
		r["deposit_amount"] = flt(deposits.get(r["custom_bank_deposit"]))
		difference = flt(r["difference"])
		if not difference:
			r["status"] = _("Balanced")
		elif difference < 0:
			r["status"] = _("Short")
		else:
			r["status"] = _("Excess")

	return rows


def resolve_deposits(deposit_names):
	deposit_names = [d for d in set(deposit_names) if d]
	if not deposit_names:
		return {}

	return {
		d.name: d.deposit_amount
		for d in frappe.get_all(
			"Bank Deposits", filters={"name": ["in", deposit_names]}, fields=["name", "deposit_amount"]
		)
	}
