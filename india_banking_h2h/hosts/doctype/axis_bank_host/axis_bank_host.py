# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.core.api.file import create_new_folder
from frappe.utils import cstr, get_datetime, getdate

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
				return self.process_payment(log_id=existing_payment.name)

			return existing_payment.get_summary_details()

		log_id = self.create_payment_log(payment_details, commit=True)
		if log_id:
			frappe.get_doc("Payment Log", log_id)
			return self.process_payment(log_id=log_id)
		else:
			frappe.throw("Failed to create payment log")

	def get_payment_status(self):
		payment_details = frappe._dict(self.doc)
		unique_id = get_id(payment_details.name)

		existing_payment = get_existing_doc("Payment Log", unique_id)

		if existing_payment:
			return existing_payment.get_summary_details(action="get_payment_status")

		return {"message": "Payment not found"}

	def create_payment_log(self, payment_details, commit=False):
		payment_log_doc = frappe.new_doc("Payment Log")
		payment_log_doc.payment_log_id = get_id(self.doc.name)
		payment_log_doc.payment_status = "Pending Upload"
		payment_log_doc.host = self.doctype
		payment_log_doc.host_name = self.name

		for pd in payment_details.summary:
			payment_log_doc.append(
				"payment_summary",
				{
					"payment_id": pd.get("name", ""),
					"status": json.dumps({"payment_status": "Accepted"}),
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
		if commit:
			frappe.db.commit()

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
				"BENE_CODE": summary.party,
				"BENE_ACC_NUM": summary.bank_account_no,
				"BENE_AC_TYPE": "11",
				"BENE_ADDR_1": "",
				"BENE_ADDR_2": "",
				"BENE_ADDR_3": "",
				"BENE_CITY": "",
				"BENE_STATE": "",
				"BENE_PINCODE": "",
				"BENE_IFSC_CODE": summary.branch_code,
				"BENE_BANK_NAME": summary.bank,
				"BASE_CODE": self.base_code,
				"CHEQUE_NUMBER": summary.cheque_number,
				"CHEQUE_DATE": getdate().strftime("%Y-%m-%d"),
				"PAYABLE_LOCATION": "",
				"PRINT_LOCATION": "",
				"BENE_EMAIL_ADDR1": summary.email,
				"BENE_EMAIL_ADDR2": "",
				"BENE_MOBILE_NO": summary.mobile_number,
				"RUN_IDENTIFICATION": "",
				"CMPY_CODE": self.company_code,
				"PRODUCT_CODE": self.product_code,
				"ENRICHMENT1": "",
				"ENRICHMENT2": "",
				"ENRICHMENT3": "",
				"ENRICHMENT4": "",
				"ENRICHMENT5": "",
				"PayType": "VEND",
				"TRANSMISSION_DATE": get_datetime().strftime("%Y-%m-%d %H-%M-%S"),
				"ORIG_USERID": self.userid,
				"USER_DEPARTMENT": self.user_department,
				"BENE_LEI": summary.bene_lei,
				"Add_Info1": "",
				"Add_Info2": "",
				"Add_Info3": "",
				"Add_Info4": "",
			}

			self.validate_payment_field(payment_dic)

			request_data[summary.name] = payment_dic
			line = "^".join([cstr(value) or "" for value in payment_dic.values()])
			file_content += line + "\r\n\r\n"

		if file_content:
			filename = (
				self.corporate_code
				+ "_H2H_"
				+ getdate().strftime("%d%m%Y")
				+ "_"
				+ payment_log_id
				+ ".txt"
			)
			create_new_folder("Payment Log", "Home")
			file = frappe.new_doc("File")
			file.file_name = filename
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

	def get_status(self, status_code):
		if status_c "SUCCESS":
			return "Processed"
		elif status_code == "REJECTED":
			return "Rejected"

	def get_formated_summary_details(self, status_data):
		data = frappe._dict({})
		if status_data:
			status_data = frappe._dict(status_data)
			data.payment_date = status_data.payment_run_date
			data.cheque_number = status_data.cheque_number
			data.status_code = status_data.status_code
			data.status = self.get_status(status_data.status_code)
			data.status_description = status_data.status_description
			data.utr_number = (
				status_data.transaction_utr_number or status_data.cheque_number
			)
			data.amount = status_data.amount
			data.valuation_date = status_data.transaction_value_date

		return data

	def get_formated_response(self, data):
		if isinstance(data, str):
			data = data.split("\n")

		status_field_map = [
			"customer_unique_no",
			"corp_code",
			"payment_run_date",
			"product_code",
			"transaction_utr_number",
			"cheque_number",
			"status_code",
			"status_description",
			"batch_no",
			"vendor_code",
			"transaction_value_date",
			"bank_reference_number",
			"amount",
			"corporate_account_number",
			"corporate_ifsc_code",
			"debit_credit_indicator",
			"beneficiary_account_number",
			"client_batch_no",
		]

		formated_response = {
			"invalid_response": [],
			"summary_data": {},
		}

		for status_details in data:
			if status_details:
				status_details = status_details.split("^")
				if len(status_field_map) == len(status_details):
					staus_dict = dict(zip(status_field_map, status_details))
					formated_response["summary_data"][
						staus_dict.get("customer_unique_no", "")
					] = self.get_formated_summary_details(staus_dict)
				else:
					formated_response["response_data"].append(status_details)
		return formated_response

	def validate_payment_field(self, data):
		# (mandatory, depends_on, condition, expected)
		default = (1, 0, None, None)
		optional = (0, 0, None, None)
		condition_map = {
			"Identifier": default,
			"TXN_PAYMODE": default,
			"CORP_CODE": default,
			"CUST_UNIQ_REF": default,
			"CORP_ACC_NUM": default,
			"VALUE_DATE": default,
			"TXN_CRNCY": default,
			"TXN_AMOUNT": default,
			"BENE_NAME": default,
			"BENE_CODE": default,
			"BENE_ACC_NUM": default,
			"BENE_AC_TYPE": default,
			"BENE_ADDR_1": optional,
			"BENE_ADDR_2": optional,
			"BENE_ADDR_3": optional,
			"BENE_CITY": optional,
			"BENE_STATE": optional,
			"BENE_PINCODE": optional,
			"BENE_IFSC_CODE": default,
			"BENE_BANK_NAME": (0, "TXN_PAYMODE", "in", ["RT", "NE"], "STR"),
			"BASE_CODE": optional,
			"CHEQUE_NUMBER": optional,
			"CHEQUE_DATE": optional,
			"PAYABLE_LOCATION": optional,
			"PRINT_LOCATION": optional,
			"BENE_EMAIL_ADDR1": optional,
			"BENE_EMAIL_ADDR2": optional,
			"BENE_MOBILE_NO": optional,
			"RUN_IDENTIFICATION": optional,
			"CMPY_CODE": optional,
			"PRODUCT_CODE": optional,
			"ENRICHMENT1": optional,
			"ENRICHMENT2": optional,
			"ENRICHMENT3": optional,
			"ENRICHMENT4": optional,
			"ENRICHMENT5": optional,
			"PayType": optional,
			"TRANSMISSION_DATE": optional,
			"ORIG_USERID": optional,
			"USER_DEPARTMENT": optional,
			"BENE_LEI": (0, "TXN_AMOUNT", ">", 500000000, "NUM"),
			"Add_Info1": optional,
			"Add_Info2": optional,
			"Add_Info3": optional,
			"Add_Info4": optional,
		}
		required_fields = []
		for key, val in data.items():
			if not val and condition_map[key][0]:
				required_fields.append(key)
			elif required_key := condition_map[key][1]:
				if condition_map[key][4] == "NUM":
					if (
						data[required_key]
						and frappe.safe_eval(
							f"{data[required_key]} {condition_map[key][2]} {condition_map[key][3]}"
						)
						and not val
					):
						required_fields.append(key)
				else:
					if (
						data[required_key]
						and frappe.safe_eval(
							f"'{data[required_key]}' {condition_map[key][2]} {condition_map[key][3]}"
						)
						and not val
					):
						required_fields.append(key)

		if required_fields:
			frappe.throw(f"Required Field: {required_fields}")
