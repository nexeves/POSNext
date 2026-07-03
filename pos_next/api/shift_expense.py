# pos_next/api/shift_expense.py

import frappe

@frappe.whitelist()
def get_shift_expenses(shift):
    
    fields = [
        "name",
        "posting_date",
        "user_remark",
    ]

    if frappe.db.has_column("Journal Entry", "mode_of_payment"):
        fields.append("mode_of_payment")
    if frappe.db.has_column("Journal Entry", "total_debit"):
        fields.append("total_debit")

    expenses = frappe.get_all(
        "Journal Entry",
        filters={
            "docstatus": 1,
            "custom_created_from_pos": 1,
            "custom_pos_shift": shift,
        },
        fields=fields,
        order_by="posting_date asc",
    )

    total_expense = 0
    for expense in expenses:
        if expense.get("total_debit") is None:
            total_debit = frappe.db.sql(
                """
                SELECT SUM(debit_in_account_currency)
                FROM `tabJournal Entry Account`
                WHERE parent=%s
                """,
                expense.name,
            )
            expense["total_debit"] = total_debit[0][0] if total_debit and total_debit[0][0] is not None else 0

        total_expense += (expense.get("total_debit"))

    return {
        "expenses": expenses,
        "total_expense": total_expense,
    }