from india_banking_h2h.install import (
	create_bank_doctype,
	create_default_banks,
	create_host_settings,
)


def execute():
	create_bank_doctype()
	create_default_banks()
	create_host_settings()
