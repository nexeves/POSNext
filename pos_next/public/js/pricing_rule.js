frappe.ui.form.on("Pricing Rule", {
    refresh(frm) {
        frm.set_query("custom_batch", "items", function (doc, cdt, cdn) {
            const row = locals[cdt][cdn];

            return {
                filters: {
                    item: row.item_code
                }
            };
        });
    }
});
