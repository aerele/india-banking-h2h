import json

import frappe

from india_banking_h2h.defaults import DEFAULT_HOSTS


def fetch_payment_status():
	for host in DEFAULT_HOSTS:
		host_doc_list = frappe.get_all(host)
		for docname in host_doc_list:
			host_doc = frappe.get_doc(host, docname)
			if host_doc.active:
				status_data = host_doc.get_status_from_server()
				if status_data:
					for source_file_name, data in status_data.items():
						status_log = frappe.new_doc("Status Log")
						status_log.source_file_name = source_file_name
						status_log.response = (
							json.dumps(data.get("summary_data"))
							if data.get("summary_data")
							else ""
						)
						status_log.error = (
							json.dumps(data.get("invalid_response"))
							if data.get("invalid_response")
							else ""
						)
						status_log.update_payment_status()
						status_log.save()
