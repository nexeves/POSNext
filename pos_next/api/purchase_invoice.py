import frappe


def update_item_prices(doc, method):
    selling_price_list = "Standard Selling"

    for row in doc.items:
        if not row.custom_selling_amount:
            continue

        # Get batch from Purchase Invoice Item
        batch_no = row.batch_no

        filters = {
            "item_code": row.item_code,
            "price_list": selling_price_list,
            "batch_no": batch_no
        }

        existing = frappe.db.get_value(
            "Item Price",
            filters,
            "name"
        )

        if existing:
            # Update existing Item Price
            item_price = frappe.get_doc("Item Price", existing)
            item_price.price_list_rate = row.custom_selling_amount
            item_price.batch_no = batch_no
            item_price.save(ignore_permissions=True)

        else:
            # Create new Item Price
            item_price = frappe.new_doc("Item Price")
            item_price.item_code = row.item_code
            item_price.price_list = selling_price_list
            item_price.price_list_rate = row.custom_selling_amount
            item_price.selling = 1
            item_price.currency = doc.currency
            item_price.batch_no = batch_no
            item_price.insert(ignore_permissions=True)

    frappe.db.commit()