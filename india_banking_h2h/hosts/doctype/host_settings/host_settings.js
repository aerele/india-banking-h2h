// Copyright (c) 2025, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Host Settings", {
  refresh(frm) {
    frappe.call("india_banking_h2h.utils.get_default_hosts").then((r) => {
      frm.set_query("host", "hosts", function (frm, cdt, cdn) {
        return {
          filters: {
            name: ["in", r.message],
          },
        };
      });
    });
  },
});
