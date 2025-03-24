import json

import frappe

from india_banking_h2h.hosts import get_host


@frappe.whitelist()
def connect(**kwargs):
	if not kwargs:
		return None

	payload = (
		frappe._dict(json.loads(kwargs))
		if isinstance(kwargs, str)
		else frappe._dict(kwargs)
	)

	try:
		host = get_host(payload)

		if isinstance(host, frappe.model.document.Document):
			return host.get_response(payload.method)
		else:
			return host

	except Exception:
		frappe.log_error("Host Error", frappe.get_traceback(with_context=True))
		return {"status": "Request Failure", "message": frappe.get_traceback()}
