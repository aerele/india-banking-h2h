# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PaymentLog(Document):
	def get_summary_details(self):
		"""
		summarize the payment log.
		Returns:
		        dict: A dictionary containing the formatted response of the payment log.
		"""
		res_dict = frappe._dict()

		if self.status == "Pending Upload":
			res_dict.payment_status = "Pending Upload"
			res_dict.message = "Payment is pending upload"
			res_dict.summary_details = {}
		elif self.status == "Uploaded":
			res_dict.payment_status = "Uploaded"
			res_dict.message = "Payment is uploaded"
			res_dict.summary_details = {
				sd.payment_id: frappe._dict({"status": sd.status} or {})
				for sd in self.payment_summary
			}
		elif self.status == "Failed":
			res_dict.payment_status = "Failed"
			res_dict.message = "Payment failed"
			res_dict.summary_details = {
				sd.payment_id: frappe._dict({"status": sd.status} or {})
				for sd in self.payment_summary
			}
		elif self.status == "Initiated":
			res_dict.payment_status = "ACCEPTED"
			res_dict.message = "Payment is accepted"
			res_dict.summary_details = {
				sd.payment_id: frappe._dict({"status": sd.status} or {})
				for sd in self.payment_summary
			}
		elif self.status == "Processed":
			res_dict.payment_status = "PROCESSED"
			res_dict.message = "Payment is processed"
			res_dict.summary_details = {
				sd.payment_id: frappe._dict({"status": sd.status} or {})
				for sd in self.payment_summary
			}
		else:
			res_dict.message = "Unknown status"

		return res_dict
