import frappe
from frappe.utils import flt, nowdate


@frappe.whitelist()
def get_expense_accounts():

	company = frappe.defaults.get_user_default("Company")

	accounts = frappe.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"root_type": "Expense"
		},
		fields=["name"],
		order_by="name"
	)

	return [d.name for d in accounts]


@frappe.whitelist()
def get_pos_profile_mops(pos_profile):

	if not pos_profile:
		return []

	mops = []

	try:
		rows = frappe.get_all(
			"POS Payment Method",
			filters={"parent": pos_profile},
			fields=["mode_of_payment"]
		)

		mops = [d.mode_of_payment for d in rows]

	except Exception:
		pass

	return mops


@frappe.whitelist()
def create_expense_entry(data):

	data = frappe.parse_json(data)

	amount = flt(data.get("amount"))

	expense_account = data.get("expense_account")
	mode_of_payment = data.get("mode_of_payment")
	remarks = data.get("remarks")

	pos_profile = data.get("pos_profile")
	opening_shift = data.get("opening_shift")

	if not amount:
		frappe.throw("Amount is required")

	if not expense_account:
		frappe.throw("Expense Account is required")

	if not mode_of_payment:
		frappe.throw("Mode of Payment is required")

	company = frappe.defaults.get_user_default("Company")

	payment_account = frappe.db.get_value(
		"Mode of Payment Account",
		{
			"parent": mode_of_payment,
			"company": company,
		},
		"default_account",
	)

	if not payment_account:
		frappe.throw(
			f"No account configured for Mode of Payment {mode_of_payment}"
		)

	je = frappe.new_doc("Journal Entry")

	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = nowdate()

	# Standard field
	je.user_remark = remarks

	# Custom fields
	if hasattr(je, "custom_pos_profile"):
		je.custom_pos_profile = pos_profile

	if hasattr(je, "custom_pos_shift"):
		je.custom_pos_shift = opening_shift

	if hasattr(je, "custom_created_from_pos"):
		je.custom_created_from_pos = 1

	je.append(
		"accounts",
		{
			"account": expense_account,
			"debit_in_account_currency": amount,
		},
	)

	je.append(
		"accounts",
		{
			"account": payment_account,
			"credit_in_account_currency": amount,
		},
	)

	je.insert(ignore_permissions=True)
	je.submit()

	return {
		"journal_entry": je.name,
	}

@frappe.whitelist()
def get_shift_expenses(opening_shift):
    expenses = frappe.get_all(
        "Journal Entry",
        filters={
            "custom_created_from_pos": 1,
            "custom_pos_shift": opening_shift,
            "docstatus": 1,
        },
        fields=[
            "name",
            "posting_date",
            "user_remark",
            "total_debit",
        ],
        order_by="posting_date asc",
    )

    total_expense = sum(
        flt(d.get("total_debit"))
        for d in expenses
    )

    return {
        "expenses": expenses,
        "total_expense": total_expense,
    }