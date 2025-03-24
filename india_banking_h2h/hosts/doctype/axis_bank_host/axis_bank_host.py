# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.core.api.file import create_new_folder
from frappe.utils import cstr, getdate

from india_banking_h2h.hosts.base_host import BaseHost
from india_banking_h2h.utils import get_existing_doc, get_id


class AxisBankHost(BaseHost):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.doc = frappe._dict(kwargs.get("doc", {}))

	def initiate_payment(self):
		payment_details = self.doc
		unique_id = get_id(payment_details.name)

		existing_payment = get_existing_doc("Payment Log", unique_id)

		if existing_payment:
			if existing_payment.status == "Pending Upload":
				self.process_payment(log_id=existing_payment.name)
			return existing_payment.get_summary_details()

		log_id = self.create_payment_log(payment_details)
		if log_id:
			frappe.db.commit()
			log_doc = frappe.get_doc("Payment Log", log_id)
			frappe.log_error("Log Doc", log_doc.as_dict())
			return self.process_payment(log_id=log_id)
		else:
			frappe.throw("Failed to create payment log")

	def get_payment_status(self):
		payment_details = frappe._dict(self.doc)
		unique_id = get_id(payment_details.name)

		existing_payment = get_existing_doc("Payment Log", unique_id)

		if existing_payment:
			return existing_payment.get_summary_details()

		return {"message": "Payment not found"}

	def create_payment_log(self, payment_details):
		payment_log_doc = frappe.new_doc("Payment Log")
		payment_log_doc.payment_log_id = get_id(self.doc.name)
		payment_log_doc.payment_status = "Pending Upload"

		for pd in payment_details.summary:
			payment_log_doc.append(
				"payment_summary",
				{
					"payment_id": pd.get("name", ""),
					"status": "Pending Upload",
				},
			)
		payment_log_doc.insert()

		request = self.make_payment_file(payment_log_doc.name)

		frappe.db.set_value(
			"Payment Log",
			payment_log_doc.name,
			"payment_file",
			request.get("file_url", ""),
		)
		frappe.db.set_value(
			"Payment Log",
			payment_log_doc.name,
			"request",
			json.dumps(request.get("request_data", "")),
		)

		return payment_log_doc.name

	def get_mode_of_transfer(self, mode_of_transfer):
		if mode_of_transfer == "RTGS":
			return "RT"
		elif mode_of_transfer == "NEFT":
			return "NE"
		elif "A2A" in mode_of_transfer:
			return "FT"
		elif mode_of_transfer == "IMPS":
			return "PA"
		else:
			return "RT"

	def make_payment_file(self, payment_log_id):
		payment_details = self.doc
		file_content = ""
		request_data = {}
		for summary in payment_details.summary:
			summary = frappe._dict(summary)
			payment_dic = {
				"Identifier": "P",
				"TXN_PAYMODE": self.get_mode_of_transfer(summary.mode_of_transfer),
				"CORP_CODE": self.corporate_code,
				"CUST_UNIQ_REF": summary.name,
				"CORP_ACC_NUM": self.account_number,
				"VALUE_DATE": getdate().strftime("%Y-%m-%d"),
				"TXN_CRNCY": "INR",
				"TXN_AMOUNT": summary.amount,
				"BENE_NAME": summary.party_name,
				"BENE_CODE": summary.party_name,
				"BENE_ACC_NUM": summary.bank_account_no,
				"BENE_AC_TYPE": "11",
				"BENE_ADDR_1": "",
				"BENE_ADDR_2": "",
				"BENE_ADDR_3": "",
				"BENE_CITY": "",
				"BENE_STATE": "",
				"BENE_PINCODE": "",
				"BENE_IFSC_CODE": summary.branch_code,
				"BENE_BANK_NAME": summary.beneficiary_bank_name,
				"BASE_CODE": self.base_code,
				"CHEQUE_NUMBER": summary.cheque_number,
				"CHEQUE_DATE": getdate().strftime("%Y-%m-%d"),
				"PAYABLE_LOCATION": "",
				"PRINT_LOCATION": "",
				"BENE_EMAIL_ADDR1": summary.email,
				"BENE_EMAIL_ADDR2": "",
				"BENE_MOBILE_NO": summary.mobile_number,
				"RUN_IDENTIFICATION": "",
				"CMPY_CODE": summary.company_code,
				"PRODUCT_CODE": summary.product_code,
				"ENRICHMENT1": "",
				"ENRICHMENT2": "",
				"ENRICHMENT3": "",
				"ENRICHMENT4": "",
				"ENRICHMENT5": "",
				"PayType": "VEND",
				"TRANSMISSION_DATE": getdate().strftime("%Y-%m-%d %H-%M-%S"),
				"ORIG_USERID": summary.userid,
				"USER_DEPARTMENT": summary.user_department,
				"BENE_LEI": summary.bene_lei,
				"Add_Info1": "",
				"Add_Info2": "",
				"Add_Info3": "",
				"Add_Info4": "",
			}

			request_data[summary.name] = payment_dic
			line = "^".join([cstr(value) or "" for value in payment_dic.values()])
			file_content += line + "\r\n\r\n"

		if file_content:
			create_new_folder("Payment Log", "Home")
			file = frappe.new_doc("File")
			file.file_name = payment_log_id + ".txt"
			file.content = file_content
			file.folder = "Home/Payment Log"
			file.attached_to_doctype = "Payment Log"
			file.attached_to_name = payment_log_id
			file.attached_to_field = "payment_file"
			file.insert()

			return {
				"file_url": file.file_url,
				"request_data": request_data,
			}
		else:
			frappe.throw("No payment file created")
