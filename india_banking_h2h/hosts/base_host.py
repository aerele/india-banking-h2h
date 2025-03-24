import logging
import os

import frappe
import paramiko
from frappe.model.document import Document
from frappe.utils import cint


class BaseHost(Document):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.is_active()
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
			frappe.log_error("stderr", stderr)
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

	def process_payment(self, log_id):
		"""
		Process the payment and return the response.
		Args:
		        log_id (str): The ID of the payment log.
		Returns:
		        dict: A dictionary containing the formatted response of the payment processing.
		"""
		payment_file_url = frappe.db.get_value("Payment Log", log_id, "payment_file")
		if not payment_file_url:
			frappe.throw("Payment file not found")

		payment_doc = frappe.get_doc("File", {"file_url": payment_file_url})

		filename = payment_doc.file_name
		payment_file_path = frappe.utils.file_manager.get_file_path(
			payment_doc.file_url
		)

		return self.upload_payment_files_to_server(filename, payment_file_path, log_id)

	def upload_payment_files_to_server(self, filename, payment_file_path, log_id):
		payment_log_doc = frappe.get_doc("Payment Log", log_id)
		ssh = self.get_ssh_client()
		sftp = ssh.open_sftp()

		try:
			sftp = ssh.open_sftp()
			source_payment_file = payment_file_path
			target_file = os.path.join(f"{self.payment_path}", filename)

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
