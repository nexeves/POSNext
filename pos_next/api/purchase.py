import frappe


@frappe.whitelist()
def get_standard_selling_rate(item_code):
    rate = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item_code,
            "price_list": "Standard Selling",
            "selling": 1
        },
        "price_list_rate"
    )

    return rate or 0