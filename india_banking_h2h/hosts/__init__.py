import importlib

import frappe
from frappe import _, scrub


def import_host(host_path, host_name):
	module = importlib.import_module(host_path)
	return getattr(module, host_name)


def check_host(bank):
	filters = {
		"parent": "Host Settings",
		"bank": bank,
	}

	host = frappe.get_value(
		"Host Map",
		filters,
		"host",
	)
	if not host:
		frappe.throw(
			_("There is no host map in the host settings."),
			title=_("Connection failed"),
		)

	return host


def get_bank_host(bank):
	host = check_host(bank)
	path = f"{scrub(host)}.{scrub(host)}"
	host_path = f"india_banking_h2h.hosts.doctype.{path}"

	try:
		return import_host(host_path, host.replace(" ", "")), host
	except ImportError:
		frappe.log_error(
			_("Host not found for bank {bank}").format(bank=bank),
			frappe.get_traceback(with_context=True),
		)

		frappe.throw(_("Not Implemented"), title=_("Connection failed"))


def get_host(payload):
	doc = frappe._dict(payload.doc)
	BankHost, host_name = get_bank_host(doc.company_bank)

	class Host(BankHost):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self.is_active()

		def get_response(self, method):
			if method and hasattr(self, method):
				return getattr(self, method)()
			else:
				frappe.throw(_("Invalid Method"))

	try:
		return Host(
			host_name,
			doc.company_account_number,
			doc=doc,
			payment_doc=payload,
		)
	except frappe.exceptions.DoesNotExistError:
		frappe.throw(
			title=_("Connection failed"),
			msg=_("Host not found for Account Number {0}").format(
				doc.company_account_number
			),
		)

	except Exception:
		return {"message": frappe.get_traceback()}
