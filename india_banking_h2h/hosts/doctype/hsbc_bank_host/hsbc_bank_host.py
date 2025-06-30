# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import json
import os
import stat
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring

import frappe
import gnupg
import paramiko
from frappe.core.api.file import create_new_folder
from frappe.utils import cint, cstr, get_datetime, getdate
from frappe.utils.file_manager import get_file_path

from india_banking_h2h.hosts.base_host import BaseHost
from india_banking_h2h.utils import get_existing_doc, get_id


class HSBCBankHost(BaseHost):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.doc = frappe._dict(kwargs.get("doc", {}))
		self.encrypt_payment_file = True

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
			{
				"payment_file": request.get("file_url", ""),
				"request": request.get("request_data", ""),
			},
		)
		if commit:
			frappe.db.commit()

		return payment_log_doc.name

	def get_status(self, status):
		if status in ["ACWC"]:
			return "Processed"
		return ""

	def get_formated_response(self, data):
		if not data:
			return ""

		root = ET.fromstring(data)

		status_data = {}
		for tx_info in root.findall(".//TxInfAndSts") or []:
			instr_id = tx_info.findtext("OrgnlInstrId")
			end_to_end_id = tx_info.findtext("OrgnlEndToEndId")
			tx_status = tx_info.findtext("TxSts")

			instd_amt_el = tx_info.find(".//InstdAmt")
			instd_amt = instd_amt_el.text if instd_amt_el is not None else None
			currency = (
				instd_amt_el.attrib.get("Ccy") if instd_amt_el is not None else None
			)

			collection_date = tx_info.findtext(".//ReqdColltnDt")
			debtor_name = tx_info.findtext(".//Dbtr/Nm")
			debtor_id = tx_info.findtext(".//Dbtr/Id/OrgId/Othr/Id")
			creditor_name = tx_info.findtext(".//Cdtr/Nm")

			status_data[instr_id] = {
				"end_to_end_id": end_to_end_id,
				"status": self.get_status(tx_status),
				"status_code": tx_status,
				"amount": instd_amt,
				"currency": currency,
				"collection_date": collection_date,
				"debtor_name": debtor_name,
				"debtor_id": debtor_id,
				"creditor_name": creditor_name,
				"utr_number": "",
			}

		formated_response = {
			"invalid_response": [],
			"summary_data": status_data,
		}

		return formated_response

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

		xml_dict = self.build_xml_dict()
		root_tag = list(xml_dict.keys())[0]
		root_value = xml_dict[root_tag]
		root = build_element(root_tag, root_value)

		xml_str = tostring(root, encoding="utf-8")
		file_content = parseString(xml_str).toprettyxml(indent="    ")

		if file_content:
			filename = (
				"HSBC_" + getdate().strftime("%d%m%y") + "_" + payment_log_id + ".xml"
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
				"request_data": file_content,
			}
		else:
			frappe.throw("No payment file created")

	def build_xml_dict(self):
		payment_details = frappe._dict(self.doc)
		unique_id = get_id(payment_details.name)

		xml_dict = {
			"Document": {
				"@xmlns": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03",
				"@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
				"CstmrCdtTrfInitn": {
					"GrpHdr": {
						"MsgId": unique_id,
						"CreDtTm": get_datetime().strftime("%Y-%m-%dT%H:%M:%S"),
						"NbOfTxs": cstr(len(payment_details.summary)),
						"CtrlSum": cstr(payment_details.total),
						"InitgPty": {
							"Id": {
								"OrgId": {
									"Othr": {
										"Id": self.pc_id,
									}
								}
							}
						},
					},
					"PmtInf": {
						"PmtInfId": unique_id,
						"PmtMtd": "TRF",
						"PmtTpInf": {
							"SvcLvl": {
								"Cd": "URNS"
								if payment_details.mode_of_transfer == "NEFT"
								else "URGP"
							}
						},
						"ReqdExctnDt": get_datetime().strftime("%Y-%m-%d"),
						"Dbtr": {
							"Nm": payment_details.company_bank_account
							or payment_details.company,
							"PstlAdr": {
								"StrtNm": "",
								"PstCd": "",
								"TwnNm": "",
								"CtrySubDvsn": "",
								"Ctry": "",
							},
						},
						"DbtrAcct": {
							"Id": {
								"Othr": {
									"Id": self.name,
								}
							},
							"Ccy": self.currency,
						},
						"DbtrAgt": {
							"FinInstnId": {
								"BIC": getattr(self, "ifsc_code", "HSBCINBB"),
								"PstlAdr": {
									"Ctry": "IN",
								},
							}
						},
						**self.get_transactions(),
					},
				},
			}
		}

		return xml_dict

	def get_transactions(self):
		transactions = {}
		payment_details = frappe._dict(self.doc)
		for summary in payment_details.summary:
			summary = frappe._dict(summary)
			tx_dict = {
				f"CdtTrfTxInf-{summary.name}": {
					"PmtId": {
						"InstrId": summary.name,
						"EndToEndId": summary.name,
					},
					"Amt": {"InstdAmt": {"@Ccy": "INR", "#text": cstr(summary.amount)}},
					"ChrgBr": "DEBT",
					"CdtrAgt": {
						"FinInstnId": {
							"ClrSysMmbId": {
								"MmbId": summary.branch_code,
							},
							"PstlAdr": {
								"Ctry": "IN",
							},
						}
					},
					"Cdtr": {
						"Nm": summary.party or summary.party_name,
						"PstlAdr": {
							"Ctry": "IN",
						},
					},
					"CdtrAcct": {
						"Id": {
							"Othr": {
								"Id": summary.bank_account_no,
							}
						}
					},
					"RltdRmtInf": {
						"RmtLctnMtd": "EMAL",
						"RmtLctnElctrncAdr": summary.email,
						"RmtLctnPstlAdr": {
							"Nm": summary.party or summary.party_name,
							"Adr": {
								"Ctry": "IN",
							},
						},
					},
					"RmtInf": {
						"Ustrd": summary.remarks or "",
						"Strd": {
							"RfrdDocInf": {
								"Nb": summary.payment_entry or summary.journal_entry,
								"RltdDt": getdate(
									payment_details.posting_date
								).strftime("%Y-%m-%d"),
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
					},
				}
			}
			transactions.update(tx_dict)

		return transactions

	def upload_payment_files_to_server(self, filename, payment_file_path, log_id):
		payment_log_doc = frappe.get_doc("Payment Log", log_id)

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

			payment_file = Path(payment_file_path)

			try:
				sftp.stat(payment_file.name)
			except FileNotFoundError:
				pass
			else:
				payment_log_doc.reload()
				return payment_log_doc.get_summary_details()

			sftp.put(payment_file, payment_file.name, confirm=False)

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

	def get_status_from_server(self):
		if not self.reversefeed_folder:
			return
		file_dict = {}

		transport = None
		sftp = None
		try:
			gpg = self.init_gpg()

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
				file_name = file_name[-50:]
				if frappe.db.exists("Status Log", {"source_file_name": file_name}):
					continue

				status_file_path = os.path.join(self.reversefeed_folder, file_name)

				decrypted_data = None
				with open(status_file_path, "rb") as f:
					decrypted = gpg.decrypt_file(
						f,
						always_trust=True,
						passphrase=self.get_password("pgp_private_key_password")
						if self.pgp_private_key_password
						else None,
					)
					if not decrypted.ok:
						frappe.throw(
							"Decryption failed:",
							frappe.get_traceback(with_context=True),
						)

					if decrypted.valid:
						decrypted_data = decrypted.data
					else:
						frappe.log_error(
							"Decrypted file is not valid", decrypted.stderr
						)

					if decrypted_data:
						file_dict.setdefault(
							file_name, self.get_formated_response(decrypted_data)
						)

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

	def get_encrypt_payment_file(self, log_id):
		if encrypted_file_url := frappe.get_value(
			"Payment Log", log_id, "encrypted_file"
		):
			return encrypted_file_url

		payment_log_doc = frappe.get_doc("Payment Log", log_id)

		gpg = self.init_gpg()

		recipient_fingerprint = self.hsbc_finger_print
		signer_fingerprint = self.client_finger_print

		file_url = ""
		payment_file_path = get_file_path(payment_log_doc.payment_file)

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
					"File", {"file_url": payment_log_doc.payment_file}, "file_name"
				)
				create_new_folder("Encrypted", "Home/Payment Log")

				file = frappe.new_doc("File")
				file.content = encrypted.data
				file.file_name = file_name + ".pgp"
				file.folder = "Home/Payment Log/Encrypted"
				file.attached_to_doctype = "Payment Log"
				file.attached_to_name = log_id
				file.attached_to_field = "encrypted_file"
				file.file_type = "pgp"
				file.insert()

				frappe.db.set_value(
					"Payment Log", log_id, "encrypted_file", file.file_url
				)

				file_url = file.file_url

			else:
				frappe.log_error("Encryption failed:", encrypted.stderr)
				frappe.throw("Encryption failed please check the logs for more details")

		if file_url:
			frappe.db.set_value("Payment Log", log_id, "encrypted_file", file_url)
			return file_url
		else:
			frappe.throw("Failed to encrypt payment file")

	def decrypt_file(self, encrypted_file):
		if not encrypted_file:
			frappe.throw("Payment file not found")

		gpg = self.init_gpg()

		encrypted_file_path = get_file_path(encrypted_file)
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

		return decrypted_data
