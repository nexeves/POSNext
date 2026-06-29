# pos_next/api/shift_expense.py

import frappe

@frappe.whitelist()
def get_shift_expenses(shift):
    
    expenses = frappe.get_all(
        "Journal Entry",
        filters={
            "docstatus": 1,
            "custom_created_from_pos": 1,
            "custom_pos_shift": shift
        },
        fields=[
            "name",
            "posting_date",
            "user_remark"
        ]
    )

    total_expense = 0

    for expense in expenses:

        amount = frappe.db.sql("""
            SELECT debit_in_account_currency
            FROM `tabJournal Entry Account`
            WHERE parent=%s
            LIMIT 1
        """, expense.name)

        amount = amount[0][0] if amount else 0

        expense["amount"] = amount
        total_expense += amount

    return {
        "expenses": expenses,
        "total_expense": total_expense
    }