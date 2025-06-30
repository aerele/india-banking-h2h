import json
import logging
import os

import frappe
import paramiko
from frappe.model.document import Document
from frappe.utils import cint


class BaseHost(Document):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.validate_user_permission()

	def is_active(self):
		if not self.active:
			frappe.throw("Host is inactive. Please contact admin.")

	def validate_user_permission(self):
		if not frappe.has_permission("Payment Log", "write"):
			frappe.throw("Not permitted", frappe.PermissionError)

	def get_ssh_client(self):
		try:
			logging.basicConfig(level=logging.DEBUG)
			paramiko_logger = logging.getLogger("paramiko")
			paramiko_logger.setLevel(logging.DEBUG)

			ssh = paramiko.SSHClient()
			ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			filepath = frappe.utils.file_manager.get_file_path(self.private_key)
			private_key = paramiko.RSAKey.from_private_key_file(filepath)

			ssh.connect(
				hostname=self.hostname,
				port=cint(self.port) if self.port else 22,
				username=self.get_password("username") if self.username else None,
				# password= self.get_password("password") if self.password else None,
				pkey=private_key,
				timeout=60,
			)

			transport = ssh.get_transport()
			transport.set_keepalive(30)

			stdin, stdout, stderr = ssh.exec_command("echo 'SSH Connection Successful'")
			connection_test = stdout.read().decode().strip()
			if connection_test != "SSH Connection Successful":
				ssh.close()
				frappe.log_error(
					"SSH Connection Failed",
					f"Failed to connect to server {self.hostname}",
				)
				frappe.throw("SSH Connection Failed")
			return ssh
		except Exception:
			if ssh:
				ssh.close()
			frappe.log_error(
				f"SSH Connection Failed {self.hostname}",
				frappe.get_traceback(with_context=True),
			)
			frappe.throw("SSH Connection Failed")

	def generate_new_payment_file(self, log_id):
		request = self.make_payment_file(log_id)
		frappe.db.set_value(
			"Payment Log",
			log_id,
			{
				"payment_file": request.get("file_url", ""),
				"request": json.dumps(request.get("request_data", "")),
			},
		)
		frappe.db.commit()
		if self.encrypt_payment_file:
			return self.get_encrypt_payment_file(log_id)

		return frappe.db.get_value("Payment Log", log_id, "payment_file")

	def process_payment(self, log_id):
		payment_file_url = frappe.db.get_value("Payment Log", log_id, "payment_file")

		if not payment_file_url:
			payment_file_url = self.generate_new_payment_file(log_id)

		if payment_file_url and self.encrypt_payment_file:
			payment_file_url = frappe.db.get_value(
				"Payment Log", log_id, "encrypted_file"
			)
			if not payment_file_url:
				payment_file_url = self.get_encrypt_payment_file(log_id)

		if not payment_file_url:
			frappe.throw("Payment Failed: Payment file not found")

		payment_file = frappe.get_doc("File", {"file_url": payment_file_url})

		filename = payment_file.file_name
		payment_file_path = frappe.utils.file_manager.get_file_path(
			payment_file.file_url
		)

		return self.upload_payment_files_to_server(filename, payment_file_path, log_id)

	def upload_payment_files_to_server(self, filename, payment_file_path, log_id):
		payment_log_doc = frappe.get_doc("Payment Log", log_id)
		ssh = self.get_ssh_client()

		try:
			sftp = ssh.open_sftp()
			source_payment_file = payment_file_path
			target_file = os.path.join(f"{self.payment_folder}", filename)

			try:
				sftp.stat(target_file)
			except FileNotFoundError:
				pass
			else:
				payment_log_doc.reload()
				return payment_log_doc.get_summary_details()

			sftp.put(source_payment_file, target_file)

		except Exception:
			frappe.log_error(
				"File Upload Failed", frappe.get_traceback(with_context=True)
			)
			frappe.throw("File Upload Failed")
		else:
			frappe.db.set_value("Payment Log", log_id, "status", "Uploaded")
		finally:
			sftp.close()
			ssh.close()

		payment_log_doc.reload()
		return payment_log_doc.get_summary_details()

	def get_status_from_server(self):
		if not self.reversefeed_folder:
			return
		file_dict = {}
		try:
			ssh = self.get_ssh_client()
			sftp = ssh.open_sftp()
			reversefeed_files = [
				item.filename
				for item in sftp.listdir_attr(self.reversefeed_folder)
				if (item.st_mode & 0o100000)
				and item.filename.startswith("axis_reversefeed")
			]
			for file_name in reversefeed_files:
				file_name = file_name[-50:]
				if frappe.db.exists("Status Log", {"source_file_name": file_name}):
					continue

				status_file_path = os.path.join(self.reversefeed_folder, file_name)

				with sftp.open(status_file_path, "r") as file:
					status_file_content = (
						file.read().decode()
					)  # Read and decode content
					if status_file_content:
						file_dict.setdefault(
							file_name, self.get_formated_response(status_file_content)
						)
		except FileNotFoundError:
			frappe.log_error(
				"Status File not found", "The file was not found on the server."
			)
		except Exception:
			frappe.log_error(
				"Fetching Status Failed", frappe.get_traceback(with_context=True)
			)
		finally:
			sftp.close()
			ssh.close()

		return file_dict
