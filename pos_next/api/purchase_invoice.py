import frappe


def get_pricing_rule_title(row, batch_no):
    """Pricing Rule title from a Purchase Invoice row: "Item Name - Item Code - Batch"."""
    item_name = (
        row.item_name
        or frappe.get_cached_value("Item", row.item_code, "item_name")
        or row.item_code
    )
    title = f"{item_name} - {row.item_code}"
    if batch_no:
        title += f" - {batch_no}"

    # title is a Data field (140 chars)
    if len(title) > 140:
        title = title[:137] + "..."
    return title


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


def update_item_buying_prices(doc, method):
    buying_price_list = "Standard Buying"

    for row in doc.items:
        if not row.price_list_rate:
            continue

        # Get batch from Purchase Invoice Item
        batch_no = row.batch_no

        filters = {
            "item_code": row.item_code,
            "price_list": buying_price_list,
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
            item_price.price_list_rate = row.price_list_rate
            item_price.batch_no = batch_no
            item_price.save(ignore_permissions=True)

        else:
            # Create new Item Price
            item_price = frappe.new_doc("Item Price")
            item_price.item_code = row.item_code
            item_price.price_list = buying_price_list
            item_price.price_list_rate = row.price_list_rate
            item_price.buying = 1
            item_price.currency = doc.currency
            item_price.batch_no = batch_no
            item_price.insert(ignore_permissions=True)

    frappe.db.commit()


def update_item_pricing_rules(doc, method):
    for row in doc.items:
        if not row.custom_discount_percentage:
            continue

        # Get batch from Purchase Invoice Item
        batch_no = row.batch_no

        # Pricing Rule has no direct item_code/batch fields (they live in the
        # child table), so look up the existing rule via a join instead -
        # same role the item_code/batch_no filters play for Item Price above.
        # (title is not used as a lookup key: it's set below from the
        # Purchase Invoice row as "Item Name - Item Code - Batch")
        existing = frappe.db.sql(
            """
            select pr.name
            from `tabPricing Rule` pr
            inner join `tabPricing Rule Item Code` pric on pric.parent = pr.name
            where pr.company = %(company)s
                and pr.apply_on = 'Item Code'
                and pric.item_code = %(item_code)s
                and ifnull(pric.custom_batch, '') = %(batch_no)s
            limit 1
            """,
            {"company": doc.company, "item_code": row.item_code, "batch_no": batch_no or ""},
        )
        existing = existing[0][0] if existing else None
        title = get_pricing_rule_title(row, batch_no)

        if existing:
            # Update existing Pricing Rule
            pricing_rule = frappe.get_doc("Pricing Rule", existing)
            pricing_rule.title = title
            pricing_rule.discount_percentage = row.custom_discount_percentage
            pricing_rule.items = []
            pricing_rule.append("items", {"item_code": row.item_code, "custom_batch": batch_no})
            pricing_rule.save(ignore_permissions=True)

        else:
            # Create new Pricing Rule
            pricing_rule = frappe.new_doc("Pricing Rule")
            pricing_rule.title = title
            pricing_rule.apply_on = "Item Code"
            pricing_rule.price_or_product_discount = "Price"
            pricing_rule.selling = 1
            pricing_rule.company = doc.company
            pricing_rule.currency = doc.currency
            pricing_rule.rate_or_discount = "Discount Percentage"
            pricing_rule.apply_discount_on = "Grand Total"
            pricing_rule.discount_percentage = row.custom_discount_percentage
            pricing_rule.append("items", {"item_code": row.item_code, "custom_batch": batch_no})
            pricing_rule.insert(ignore_permissions=True)

    frappe.db.commit()