# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.core.api.file import create_new_folder
from frappe.utils import cstr, get_datetime, getdate

from india_banking_h2h.hosts.base_host import BaseHost
from india_banking_h2h.utils import get_existing_doc, get_id


class ICICIBankHost(BaseHost):
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
			return "RTGS"
		elif mode_of_transfer == "NEFT":
			return "NEFT"
		elif "A2A" in mode_of_transfer:
			return "FT"
		elif mode_of_transfer == "IMPS":
			return "IMPS"
		else:
			return "NEFT"

	def make_payment_file(self, payment_log_id):
		payment_details = self.doc
		file_content = ""
		request_data = {}
		for summary in payment_details.summary:
			summary = frappe._dict(summary)

			payment_dic = {
				"EntityCode": summary.entity_code,
				"PayableAmount": summary.amount,
				"PaymentDate": get_datetime().strftime("%Y-%m-%d %H-%M-%S"),
				"TransactionID": summary.name,
				"FinacialYear": "",
				"OfferingCode": summary.offering_code,
				"LotNo": summary.lot_no,
				"mark": self.get_mode_of_transfer(summary.mode_of_transfer),
				"BuyerCode": summary.buyer_code,
				"BuyerName": summary.buyer_name,
				"BuyerInvoiceNo": summary.invoice_no,
				"BuyerInvoiceDate": summary.invoice_date,
				"TotalTaxAmount": summary.total_tax_amount,
				"TotalInvoiceAmount": summary.total_invoice_amount,
				"PlatformFees": summary.platform_fees,
				"TCSDeduction": summary.tcs_deduction,
				"TDSDeduction": summary.tds_deduction,
				"OtherDeductions": summary.other_deductions,
				"NetPayableAmount": summary.net_payable_amount,
			}

			self.validate_payment_field(payment_dic)

			request_data[summary.name] = payment_dic
			line = "|".join([cstr(value) or "" for value in payment_dic.values()])
			file_content += line + "\r\n"

		if file_content:
			filename = (
				self.client_code
				+ "_FC_"
				+ getdate().strftime("%d%m%y")
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
		if status_code in ["SUCCESS", "PROCESSED"]:
			return "Processed"
		elif status_code in ["REJECTED", "RETURN"]:
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
			data.message = status_data.status_description
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
			"entity_code",
			"payable_amount",
			"payment_date",
			"transaction_id",
			"finacial_year",
			"offering_code",
			"lot_no",
			"mark",
			"buyer_code",
			"buyer_name",
			"buyer_invoice_no",
			"buyer_invoice_date",
			"total_tax_amount",
			"TotalInvoiceAmount",
			"platform_fees",
			"tcs_deduction",
			"tds_deduction",
			"other_deductions",
			"net_payable_amount",
			"status",
			"utr_number",
			"liquidation_date",
			"status_remarks",
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
						staus_dict.get("utr_number", "")
					] = self.get_formated_summary_details(staus_dict)
				else:
					formated_response["response_data"].append(status_details)
		return formated_response

	def validate_payment_field(self, data):
		# (mandatory, depends_on, condition, expected)
		mandatory = (1, 0, None, None)
		optional = (0, 0, None, None)

		condition_map = {
			"EntityCode": mandatory,
			"PayableAmount": mandatory,
			"PaymentDate": optional,
			"TransactionID": optional,
			"FinacialYear": optional,
			"OfferingCode": optional,
			"LotNo": optional,
			"mark": optional,
			"BuyerCode": optional,
			"BuyerName": optional,
			"BuyerInvoiceNo": optional,
			"BuyerInvoiceDate": optional,
			"TotalTaxAmount": optional,
			"TotalInvoiceAmount": optional,
			"PlatformFees": optional,
			"TCSDeduction": optional,
			"TDSDeduction": optional,
			"OtherDeductions": optional,
			"NetPayableAmount": optional,
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
