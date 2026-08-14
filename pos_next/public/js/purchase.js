frappe.ui.form.on("Purchase Invoice Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.item_code) {
            frappe.model.set_value(
                cdt,
                cdn,
                "custom_selling_amount",
                0
            );
            return;
        }

        frappe.call({
            method: "pos_next.api.purchase.get_standard_selling_rate",
            args: {
                item_code: row.item_code
            },
            callback(r) {
                if (r.message !== undefined) {
                    console.log("Selling amount ----",r)
                    frappe.model.set_value(
                        cdt,
                        cdn,
                        "custom_selling_amount",
                        r.message || 0
                    );
                }
            }
        });
    }
});