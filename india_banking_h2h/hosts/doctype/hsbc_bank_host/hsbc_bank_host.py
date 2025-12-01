# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import csv
import json
import os
import stat
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring

import frappe
import gnupg
import paramiko
from frappe.core.api.file import create_new_folder
from frappe.utils import cint, cstr, flt, get_datetime, getdate
from frappe.utils.file_manager import get_file_path

from india_banking_h2h.hosts.base_host import BaseHost
from india_banking_h2h.utils import get_existing_doc, get_id


class HSBCBankHost(BaseHost):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.doc = frappe._dict(kwargs.get("doc", {}))
		self.encrypt_payment_file = True
		self.summary_details = {}

	def is_h2h_enabled(self):
		if not self.active:
			frappe.throw(
				"Host is not active. Please enable the host to initiate payment."
			)

	def initiate_payment(self):
		self.is_h2h_enabled()

		payment_details = self.doc
		unique_id = get_id(payment_details.name)

		existing_payment = get_existing_doc("Payment Log", unique_id)

		if existing_payment:
			if existing_payment.status == "Pending Upload":
				return self.process_payment(log_id=existing_payment.name)

			return existing_payment.get_summary_details()

		log_id = self.create_payment_log(payment_details, commit=True)
		if log_id:
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

		self.make_payment_file(payment_log_doc.name)

		if commit:
			frappe.db.commit()

		return payment_log_doc.name

	def process_payment(self, log_id):
		self.make_payment_file(log_id)
		if self.encrypt_payment_file:
			self.encrypt_payment_files(log_id)

		return self.upload_payment_files_to_server(log_id)

	def get_status(self, status):
		if status in ["ACCP", "ACWC"]:
			return "Accepted"
		elif status in ["RJCT"]:
			return "Rejected"
		elif status in ["ACSC"]:
			return "Processed"
		elif status in ["ACSP"]:
			return "Pending"
		return ""

	def status_code_and_description(self, status_code):
		return {
			"Returned": ("Failed", "Transaction returned by bene bank"),
			"Processed by HSBC": (
				"Processed",
				"If the transaction is from HSBC to HSBC",
			),
			"Fresh Inwards": ("", "Late return or a fresh inward"),
			"Credit Confirmed": (
				"Processed",
				"Transaction settled in Beneficiary account",
			),
			"N": ("Accepted", "N10 msg yet to be received from bene bank"),
			"Rejected by HUB": (
				"Rejected",
				"Txn rejected due to insufficient funds etc.",
			),
			"Cancelled by HSBC": ("Rejected", "Txn cancelled by bank"),
			"Sent to bene bank": ("Processed", "RTGS settled at bene bank"),
		}.get(status_code, ("Request Failure", f"Invalid status code: {status_code}"))

	def format_response(self, status_log_id):
		data = frappe.db.get_value("Status Log", status_log_id, "decrypted_data")
		if not data:
			return
		is_report_data = (
			status_log_id.lower().endswith("csv")
			or status_log_id.lower().startswith("inpp")
			or status_log_id.lower().startswith("inbulk")
		)
		formated_response = {}
		if is_report_data:
			io_object = StringIO(data)
			csv_reader = csv.DictReader(io_object)

			csv_data = list(csv_reader)

			for data in csv_data:
				if data:
					transaction_id = data.get("Customer Reference Number")
					tx_status = data.get("Status")
					status, status_description = self.status_code_and_description(
						tx_status
					)

					formated_response[transaction_id] = {
						"unique_id": transaction_id,
						"value_date": data.get("Value Date"),
						"party_name": data.get("Beneficiary Name"),
						"party_account_no": data.get("Beneficiary Account Number"),
						"party_ifsc_code": data.get("Beneficiary Bank IFS"),
						"amount": data.get("Amount"),
						"bank_ref_no": data.get("Bank Ref no"),
						"positive_return_confirm_time": data.get(
							"Positive/Return Confirm Time"
						),
						"return_reject_reason": data.get("Return/Reject Reason"),
						"return_utr_no": data.get("Return UTR No"),
						"return_ifsc_code": data.get("Return IFSC Code"),
						"status_code": tx_status,
						"status": status,
						"status_description": status_description,
						"utr_number": data.get("Transaction Reference no"),
					}
		else:
			ns = {"ns": "urn:iso:std:iso:20022:tech:xsd:pain.002.001.03"}

			root = ET.fromstring(data)
			msg_id = root.find(".//ns:OrgnlGrpInfAndSts/ns:OrgnlMsgId", ns).text
			group_status = root.find(".//ns:OrgnlGrpInfAndSts/ns:GrpSts", ns).text
			group_status_description = ""
			try:
				group_status_description = root.find(
					".//ns:OrgnlGrpInfAndSts/ns:StsRsnInf/ns:AddtlInf", ns
				)
				if group_status_description is None:
					group_status_description = root.find(
						".//ns:OrgnlPmtInfAndSts/ns:TxInfAndSts/ns:StsRsnInf/ns:AddtlInf",
						ns,
					)
				if group_status_description is not None:
					group_status_description = group_status_description.text
			except Exception as e:
				group_status_description = "Payment Rejected: " + str(e)

			payment_for = ""
			if "_neft" in msg_id:
				payment_for = "_neft"
			elif "_a2" in msg_id:
				payment_for = "_a2"
			elif "_imps" in msg_id:
				payment_for = "_imps"
			elif "_rtgs" in msg_id:
				payment_for = "_rtgs"
			elif "_payroll" in msg_id:
				payment_for = "_payroll"

			payment_id = msg_id[: -len(payment_for)]

			if group_status == "RJCT":
				self.update_group_rejected_status(
					formated_response,
					payment_id,
					group_status,
					group_status_description,
				)
			else:
				for tx in root.findall(".//ns:TxInfAndSts", ns):
					tx_id = tx.find("ns:StsId", ns)
					tx_status = tx.find("ns:TxSts", ns)
					instr_id = tx.find("ns:OrgnlInstrId", ns)
					end_to_end_id = tx.find("ns:OrgnlEndToEndId", ns)
					amount = tx.find(".//ns:Amt/ns:InstdAmt", ns)
					currency = amount.attrib.get("Ccy") if amount is not None else "N/A"

					tx_id = tx_id.text if tx_id is not None else ""
					tx_status = tx_status.text if tx_status is not None else ""
					instr_id = instr_id.text if instr_id is not None else ""
					end_to_end_id = (
						end_to_end_id.text if end_to_end_id is not None else ""
					)
					amount = amount.text if amount is not None else ""

					formated_response[instr_id] = {
						"unique_id": end_to_end_id,
						"status": self.get_status(tx_status),
						"status_code": tx_status,
						"amount": amount,
						"currency": currency,
						"transaction_id": tx_id,
						"utr_number": "",
					}

		if formated_response:
			frappe.db.set_value(
				"Status Log", status_log_id, "response", json.dumps(formated_response)
			)

		status_log = frappe.get_doc("Status Log", status_log_id)
		status_log.reload()
		status_log.update_payment_status()

	def update_group_rejected_status(
		self, formated_response, payment_id, tx_status, reject_reason
	):
		logs = frappe.db.get_all(
			"Payment Log Summary",
			{"parent": payment_id, "parenttype": "Payment Log"},
			pluck="payment_id",
		)
		if logs:
			for logid in logs:
				formated_response[logid] = {
					"unique_id": logid,
					"status": self.get_status(tx_status),
					"status_code": tx_status,
					"message": reject_reason,
				}

	def build_xml_from_dict(self, parent, data):
		if isinstance(data, dict):
			for key, value in data.items():
				if key.startswith("@"):
					parent.set(key[1:], str(value))
					continue
				elif key == "#text":
					parent.text = str(value)
					return

				if isinstance(value, (dict, list)):
					if key.startswith("CdtTrfTxInf-"):
						key = "CdtTrfTxInf"
					child = SubElement(parent, key)
					self.build_xml_from_dict(child, value)
				else:
					child = SubElement(parent, key)
					child.text = str(value)
		elif isinstance(data, list):
			for item in data:
				item_tag = parent.tag[:-1] if parent.tag.endswith("s") else parent.tag
				child = SubElement(parent, item_tag)
				self.build_xml_from_dict(child, item)
		else:
			parent.text = str(data)

	def make_payment_file(self, payment_log_id):
		payment_log_doc = frappe.get_doc("Payment Log", payment_log_id)
		self.update_summary_details()

		requested_data = {}
		file_urls = {}

		for mot in self.to_be_generate_mot:
			if payment_log_doc.get(mot + "_payment_file"):
				continue

			def build_element(tag, value):
				attrs = {}
				text = None
				if isinstance(value, dict):
					for k in list(value.keys()):
						if k.startswith("@"):
							attrs[k[1:]] = value.pop(k)
						elif k == "#text":
							text = value.pop(k)
				elem = Element(tag, attrs)
				if text:
					elem.text = text

				self.build_xml_from_dict(elem, value)
				return elem

			xml_dict = self.build_xml_dict(mot)
			root_tag = list(xml_dict.keys())[0]
			root_value = xml_dict[root_tag]
			root = build_element(root_tag, root_value)

			xml_str = tostring(root, encoding="utf-8")
			file_content = parseString(xml_str).toprettyxml(indent="    ")

			if file_content:
				filename = (
					"HSBC_"
					+ getdate().strftime("%d%m%y")
					+ "_"
					+ payment_log_id
					+ "_"
					+ mot
					+ ".xml"
				)
				create_new_folder("Payment Log", "Home")
				file = frappe.new_doc("File")
				file.file_name = filename
				file.content = file_content
				file.folder = "Home/Payment Log"
				file.attached_to_doctype = "Payment Log"
				file.attached_to_name = payment_log_id
				file.attached_to_field = f"{mot}_payment_file"
				file.insert()

				frappe.db.set_value(
					"Payment Log", payment_log_id, f"{mot}_payment_file", file.file_url
				)

				requested_data[mot] = file_content
				file_urls[f"{mot}_payment_file"] = file.file_url

		values = file_urls
		values["request"] = json.dumps(requested_data)
		frappe.db.set_value("Payment Log", payment_log_id, values)

	def get_mode_of_transfer(self, mot):
		if mot == "payroll":
			return "NURG"
		elif mot in ["rtgs", "a2"]:
			return "URGP"
		elif mot == "imps":
			return "IMPS"
		else:
			return "URNS"

	def update_summary_details(self):
		file_mot = []
		payment_details = frappe._dict(self.doc)

		for summary in payment_details.summary:
			summary = frappe._dict(summary)
			mot = ""
			if summary.party_type == "Employee" and self.enable_payroll_payment:
				mot = "payroll"
				if self.summary_details.get(mot):
					self.summary_details[mot]["summary"].append(summary)
					self.summary_details[mot]["total"] += summary.amount
				else:
					self.summary_details[mot] = {}
					self.summary_details[mot]["summary"] = [summary]
					self.summary_details[mot]["total"] = summary.amount
			elif "rtgs" in summary.mode_of_transfer.lower():
				mot = "rtgs"
				if self.summary_details.get(mot):
					self.summary_details[mot]["summary"].append(summary)
					self.summary_details[mot]["total"] += summary.amount
				else:
					self.summary_details[mot] = {}
					self.summary_details[mot]["summary"] = [summary]
					self.summary_details[mot]["total"] = summary.amount
			elif (
				"imps" in summary.mode_of_transfer.lower() and self.enable_imps_payment
			):
				mot = "imps"
				if self.summary_details.get(mot):
					self.summary_details[mot]["summary"].append(summary)
					self.summary_details[mot]["total"] += summary.amount
				else:
					self.summary_details[mot] = {}
					self.summary_details[mot]["summary"] = [summary]
					self.summary_details[mot]["total"] = summary.amount
			else:
				mot = "neft"
				if self.summary_details.get(mot):
					self.summary_details[mot]["summary"].append(summary)
					self.summary_details[mot]["total"] += summary.amount
				else:
					self.summary_details[mot] = {}
					self.summary_details[mot]["summary"] = [summary]
					self.summary_details[mot]["total"] = summary.amount

			file_mot.append(mot)

		self.to_be_generate_mot = list(set(file_mot))

	def build_xml_dict(self, mot):
		payment_details = frappe._dict(self.doc)

		unique_id = get_id(payment_details.name)

		company_address = {}
		if payment_details.company_address:
			company_address = json.loads(payment_details.company_address)
		address = frappe._dict(company_address)

		payment_dict = frappe._dict(
			{
				"unique_id": f"{unique_id}_{mot}",
				"company_name": payment_details.company,
				"summary_details": self.summary_details[mot]["summary"],
				"total": self.summary_details[mot]["total"],
				"street_name": ", ".join(address.get("AddressLine", [])),
				"building_no": address.get("AddressLine", [1])[0],
				"post_code": address.get("PostCode"),
				"town_name": address.get("TownName"),
				"country": address.get("Country", "").upper(),
			}
		)

		xml_dict = {
			"Document": {
				"@xmlns": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03",
				"@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
				"CstmrCdtTrfInitn": {
					"GrpHdr": {
						"MsgId": payment_dict.unique_id,
						"CreDtTm": get_datetime().strftime("%Y-%m-%dT%H:%M:%S"),
						"Authstn": {
							"Cd": "FDET"
							if mot == "payroll"
							else self.file_authorisation,
						},
						"NbOfTxs": cstr(len(payment_dict.summary_details)),
						"CtrlSum": cstr(
							flt(payment_dict.total, 2)
						),  # max possible rounding for bank is 2 decimal like .99 consider 1RS
						"InitgPty": {
							**(
								{"Nm": payment_dict.company_name}
								if mot == "payroll"
								else {}
							),
							"Id": {
								"OrgId": {
									"Othr": {
										"Id": self.pc_id,
									}
								}
							},
						},
					},
					"PmtInf": {
						"PmtInfId": payment_dict.unique_id,
						"PmtMtd": "TRF",  # Credit Transfer
						"PmtTpInf": {
							"SvcLvl": {"Cd": self.get_mode_of_transfer(mot)},
							**(
								{
									"LclInstrm": {"Prtry": "SALA"},
									"CtgyPurp": {"Cd": "SALA"},
								}
								if mot == "payroll"
								else {}
							),
						},
						"ReqdExctnDt": get_datetime().strftime("%Y-%m-%d"),
						"Dbtr": {
							"Nm": payment_dict.company_name,
							"PstlAdr": {
								"StrtNm": payment_dict.street_name or "",
								**(
									{"BldgNb": payment_dict.building_no or ""}
									if mot == "payroll"
									else {}
								),
								"PstCd": payment_dict.post_code or "",
								"TwnNm": payment_dict.town_name or "IND",
								"CtrySubDvsn": "",
								"Ctry": payment_dict.country or "IN",
							},
						},
						"DbtrAcct": {
							"Id": {
								"Othr": {
									"Id": self.account_number,
								}
							},
							"Ccy": "INR",
						},
						"DbtrAgt": {
							"FinInstnId": {
								"BIC": getattr(self, "ifsc_code", "HSBCINBB"),
								**({"Nm": "HSBC India"} if mot == "payroll" else {}),
								"PstlAdr": {
									"Ctry": "IN",
								},
							}
						},
						**({"ChrgBr": "DEBT"} if mot == "payroll" else {}),
						**self.get_transactions(mot, payment_dict.summary_details),
					},
				},
			}
		}

		return xml_dict

	def get_transactions(self, mot, summary_details):
		transactions = {}
		for summary in summary_details:
			tx_dict = {
				f"CdtTrfTxInf-{summary.name}": {
					"PmtId": {
						"InstrId": summary.name,
						"EndToEndId": summary.name,
					},
					"Amt": {"InstdAmt": {"@Ccy": "INR", "#text": cstr(summary.amount)}},
					**({"ChrgBr": "DEBT"} if mot == "payroll" else {}),
					"ChrgBr": "DEBT",
					"CdtrAgt": {
						"FinInstnId": {
							"ClrSysMmbId": {
								"MmbId": summary.branch_code,
							},
							**({"Nm": summary.bank} if mot == "payroll" else {}),
							"PstlAdr": {
								"Ctry": "IN",
							},
						}
					},
					"Cdtr": {
						"Nm": summary.party_name or summary.party,
						"PstlAdr": {"TwnNm": "IND", "Ctry": "IN"},
					},
					"CdtrAcct": {
						"Id": {
							"Othr": {
								"Id": summary.bank_account_no,
							}
						}
					},
					**(
						{
							"RltdRmtInf": {
								"RmtLctnMtd": "EMAL",
								"RmtLctnElctrncAdr": summary.email,
								"RmtLctnPstlAdr": {
									"Nm": summary.party_name or summary.party,
									"Adr": {
										"Ctry": "IN",
									},
								},
							},
						}
						if mot != "payroll"
						else {}
					),
					"RmtInf": {
						"Ustrd": f"SALARY for {summary.party}"
						if mot == "payroll"
						else f"Payment Reference {get_id(self.doc.name)}-{summary.name}",
						**(
							{
								"Strd": {
									"RfrdDocInf": {
										"Nb": summary.payment_entry
										or summary.journal_entry,
										"RltdDt": getdate().strftime("%Y-%m-%d"),
									},
									"RfrdDocAmt": {
										"DuePyblAmt": {
											"@Ccy": "INR",
											"#text": cstr(summary.amount),
										}
									},
									"CdtrRefInf": {
										"Tp": {"CdOrPrtry": {"Prtry": "/TDSA/0.00"}},
										"Ref": "/NAMT/0.50",
									},
									"AddtlRmtInf": "/NARR/" + summary.remarks
									if summary.remarks
									else "",
								},
							}
							if mot != "payroll"
							else {}
						),
					},
				}
			}
			transactions.update(tx_dict)

		return transactions

	def upload_payment_files_to_server(self, log_id):
		payment_log_doc = frappe.get_doc("Payment Log", log_id)

		not_uploaded_encrypted_payment_files = []

		if payment_log_doc.payroll_encrypted_payment_file:
			if not payment_log_doc.uploaded_payroll:
				not_uploaded_encrypted_payment_files.append(
					("payroll", payment_log_doc.payroll_encrypted_payment_file)
				)

		if payment_log_doc.neft_encrypted_payment_file:
			if not payment_log_doc.uploaded_neft:
				not_uploaded_encrypted_payment_files.append(
					("neft", payment_log_doc.neft_encrypted_payment_file)
				)

		if payment_log_doc.rtgs_encrypted_payment_file:
			if not payment_log_doc.uploaded_rtgs:
				not_uploaded_encrypted_payment_files.append(
					("rtgs", payment_log_doc.rtgs_encrypted_payment_file)
				)

		if payment_log_doc.imps_encrypted_payment_file:
			if not payment_log_doc.uploaded_imps:
				not_uploaded_encrypted_payment_files.append(
					("imps", payment_log_doc.imps_encrypted_payment_file)
				)

		if not not_uploaded_encrypted_payment_files:
			payment_log_doc.reload()
			return payment_log_doc.get_summary_details()

		transport = None
		sftp = None
		try:
			key = paramiko.RSAKey.from_private_key_file(
				get_file_path(self.sftp_private_key)
			)

			transport = paramiko.Transport((self.hostname, cint(self.port) or 10022))
			transport.connect(username=self.username, pkey=key)

			sftp = paramiko.SFTPClient.from_transport(transport)
			sftp.chdir(self.payment_folder)
			for mot, encrypted_payment_file in not_uploaded_encrypted_payment_files:
				payment_file_path = get_file_path(encrypted_payment_file)
				payment_file = Path(payment_file_path)

				try:
					sftp.stat(payment_file.name)
				except FileNotFoundError:
					pass

				sftp.put(payment_file, payment_file.name, confirm=False)
				frappe.db.set_value(
					"Payment Log",
					log_id,
					"uploaded_" + mot,
					1,
				)
			else:
				frappe.db.set_value(
					"Payment Log",
					log_id,
					"status",
					"Uploaded",
				)
		except Exception:
			frappe.log_error(
				"Payment File Upload Failed",
				frappe.get_traceback(with_context=True),
			)
			frappe.db.set_value(
				"Payment Log",
				log_id,
				"status",
				"Pending Upload",
			)
		finally:
			if sftp:
				sftp.close()
			if transport:
				transport.close()

		payment_log_doc.reload()
		return payment_log_doc.get_summary_details()

	def get_status_from_server(self, force_fetch=False):
		"""Fetch status files from SFTP server and process them."""
		if not self.reversefeed_folder:
			if force_fetch:
				frappe.throw("Reversefeed folder is not configured")
			return

		# First, check the status of existing logs
		self.check_status()

		# Skip fetching if auto_fetch is disabled and not forced
		if not self.auto_fetch and not force_fetch:
			return

		file_dict = {}

		transport = None
		sftp = None
		try:
			key = paramiko.RSAKey.from_private_key_file(
				get_file_path(self.sftp_private_key)
			)

			transport = paramiko.Transport((self.hostname, cint(self.port) or 10022))
			transport.connect(username=self.username, pkey=key)

			sftp = paramiko.SFTPClient.from_transport(transport)
			sftp.chdir(self.reversefeed_folder)

			reversefeed_files = [
				item.filename
				for item in sftp.listdir_attr()
				if (item.st_mode & 0o100000)
			]
			for file_name in reversefeed_files:
				file_type = "TXT"
				if file_name.lower().endswith("csv"):
					file_type = "CSV"
				else:
					if frappe.db.exists("Status Log", {"source_file_name": file_name}):
						self.decrypt_file(file_name)
						self.format_response(file_name)
						continue

				create_new_folder("Status Log", "Home")

				r_file = frappe.new_doc("File")
				r_file.file_name = file_name
				r_file.content = file_name.encode()
				r_file.folder = "Home/Status Log"
				r_file.attached_to_doctype = "Status Log"
				r_file.attached_to_name = file_name
				r_file.file_type = file_type
				r_file.is_private = 1
				r_file.attached_to_field = "status_file"
				r_file.insert()

				status_log = frappe.new_doc("Status Log")
				status_log.source_file_name = file_name
				status_log.status_file = r_file.file_url
				status_log.host = self.doctype
				status_log.host_name = self.name
				status_log.save()

				source_status_file_path = file_name
				target_status_file_path = get_file_path(r_file.file_url)

				if source_status_file_path and target_status_file_path:
					try:
						sftp.stat(source_status_file_path)
					except Exception:
						frappe.log_error("Payment status file not found!")
					else:
						sftp.get(source_status_file_path, target_status_file_path)
						frappe.db.commit()

				self.decrypt_file(status_log.name, target_status_file_path)
				self.format_response(status_log.name)

		except FileNotFoundError:
			frappe.log_error(
				"Status file not found", "The status file was not found on the server."
			)
		except Exception:
			frappe.log_error(
				"Fetching Status Failed", frappe.get_traceback(with_context=True)
			)
		finally:
			if transport:
				transport.close()
			if sftp:
				sftp.close()

		return file_dict

	def init_gpg(self):
		gpg_home = "/tmp/.gnupg_hsbc"
		os.makedirs(gpg_home, exist_ok=True)
		os.chmod(gpg_home, stat.S_IRWXU)
		gpg = gnupg.GPG(gnupghome=gpg_home)

		# Import Client Private key
		with open(get_file_path(self.pgp_private_key), "rb") as f:
			gpg.import_keys(f.read())

		# Import Client Public Key
		with open(get_file_path(self.pgp_public_key), "rb") as f:
			gpg.import_keys(f.read())

		# Import HSBC Public Key
		with open(get_file_path(self.hsbc_pgp_public_key), "rb") as f:
			gpg.import_keys(f.read())

		return gpg

	def encrypt_payment_files(self, log_id):
		payment_log_doc = frappe.get_doc("Payment Log", log_id)
		payment_files = (
			(
				"payroll",
				payment_log_doc.payroll_payment_file,
				payment_log_doc.payroll_encrypted_payment_file,
			),
			(
				"neft",
				payment_log_doc.neft_payment_file,
				payment_log_doc.neft_encrypted_payment_file,
			),
			(
				"rtgs",
				payment_log_doc.rtgs_payment_file,
				payment_log_doc.rtgs_encrypted_payment_file,
			),
			(
				"imps",
				payment_log_doc.imps_payment_file,
				payment_log_doc.imps_encrypted_payment_file,
			),
		)

		to_be_enc_mot = [
			(mot, file_url)
			for mot, file_url, encrypted_file_url in payment_files
			if file_url and not encrypted_file_url
		]

		gpg = self.init_gpg()

		recipient_fingerprint = self.hsbc_finger_print
		signer_fingerprint = self.client_finger_print

		encrypted_file_urls = {}
		for mot, payment_file in to_be_enc_mot:
			payment_file_path = get_file_path(payment_file)

			with open(payment_file_path, "rb") as f:
				encrypted = gpg.encrypt_file(
					f,
					recipients=[recipient_fingerprint],
					sign=signer_fingerprint,
					always_trust=True,
					passphrase=self.get_password("pgp_private_key_password")
					if self.pgp_private_key_password
					else None,
				)

				if encrypted.ok:
					file_name = frappe.get_value(
						"File", {"file_url": payment_file}, "file_name"
					)
					create_new_folder("Encrypted", "Home/Payment Log")

					file = frappe.new_doc("File")
					file.content = encrypted.data
					file.file_name = file_name + ".pgp"
					file.folder = "Home/Payment Log/Encrypted"
					file.attached_to_doctype = "Payment Log"
					file.attached_to_name = log_id
					file.is_private = 1
					file.attached_to_field = f"{mot}_encrypted_payment_file"
					file.file_type = "pgp"
					file.insert()

					encrypted_file_urls[f"{mot}_encrypted_payment_file"] = file.file_url
				else:
					frappe.log_error(f"Encryption failed-> {mot}", encrypted.stderr)
					frappe.throw(
						"Encryption failed please check the logs for more details"
					)

		if encrypted_file_urls:
			frappe.db.set_value("Payment Log", log_id, encrypted_file_urls)
		elif to_be_enc_mot:
			frappe.throw("Failed to encrypt payment file")

	def decrypt_file(self, status_log_id, encrypted_file=None):
		encrypted_file_path = encrypted_file
		if not encrypted_file_path:
			encrypted_file = frappe.db.get_value(
				"Status Log", status_log_id, "status_file"
			)
			encrypted_file_path = get_file_path(encrypted_file)

		if not encrypted_file:
			frappe.throw("Payment file not found")

		gpg = self.init_gpg()

		decrypted_data = None
		with open(encrypted_file_path, "rb") as f:
			decrypted = gpg.decrypt_file(
				f,
				always_trust=True,
				passphrase=self.get_password("pgp_private_key_password")
				if self.pgp_private_key_password
				else None,
			)
			if not decrypted.ok:
				frappe.throw(
					"Decryption failed:", frappe.get_traceback(with_context=True)
				)

			if decrypted.valid:
				decrypted_data = decrypted.data
			else:
				frappe.log_error("Decrypted file is not valid", decrypted.stderr)

		if decrypted_data:
			frappe.db.set_value(
				"Status Log", status_log_id, "decrypted_data", decrypted_data.decode()
			)

	@frappe.whitelist()
	def force_fetch_status(self):
		self.is_active()
		return self.get_status_from_server(force_fetch=True)
