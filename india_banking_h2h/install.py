import click
import frappe

from india_banking_h2h.defaults import (
	BANKS_HOST_MAP,
	STD_BANK_LIST,
)


def after_install():
	click.secho("* Updating India Banking Host to Host Customisations")
	create_default_bank()
	create_host_settings()
	create_bank_doctype()


def create_default_bank():
	click.echo(" -> Creating Default Banks")
	for bank in STD_BANK_LIST:
		if not frappe.db.exists("Bank", bank):
			bank_doc = frappe.new_doc("Bank")
			bank_doc.bank_name = bank
			bank_doc.is_standard = 1
			bank_doc.save()


def create_host_settings():
	click.echo(" -> Updating Host Settings")
	settings_doc = frappe.get_doc("Host Settings")
	hosts_map = [
		{
			"bank": bank,
			"host": host,
		}
		for bank, host in BANKS_HOST_MAP.items()
		if not frappe.db.exists(
			"Host Map",
			{
				"bank": bank,
				"host": host,
			},
		)
	]
	if hosts_map:
		settings_doc.extend("hosts", hosts_map)
		settings_doc.save()


def create_bank_doctype():
	if "erpnext" not in frappe.get_installed_apps() and not frappe.db.exists(
		"DocType", "Bank"
	):
		click.echo(" -> Creating Bank Doctype")
		doc = {
			"doctype": "DocType",
			"name": "Bank",
			"module": "India Banking Connector",
			"is_submittable": 0,
			"istable": 0,
			"editable_grid": 0,
			"issingle": 0,
			"is_tree": 0,
			"custom": 1,
			"permissions": [
				{
					"create": 1,
					"delete": 1,
					"email": 1,
					"export": 1,
					"print": 1,
					"read": 1,
					"report": 1,
					"role": "System Manager",
					"share": 1,
					"write": 1,
					"submit": 0,
				}
			],
			"fields": [
				{"fieldtype": "Section Break"},
				{
					"label": "Bank Name",
					"fieldname": "bank_name",
					"fieldtype": "Data",
				},
			],
		}
		frappe.call("frappe.client.insert", doc=doc)
