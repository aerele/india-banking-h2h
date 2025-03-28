# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class StatusLog(Document):
	def update_payment_status(self):
		if self.response:
			for unique_id, data in json.loads(self.response).items():
				if log_summary := frappe.db.exists(
					"Payment Log Summary", {"payment_id": unique_id}
				):
					frappe.db.set_value(
						"Payment Log Summary",
						log_summary,
						"status",
						json.dumps(data, indent=4),
					)
