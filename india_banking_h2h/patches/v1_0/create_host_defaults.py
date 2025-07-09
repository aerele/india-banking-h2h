import click

from india_banking_h2h.install import (
	create_bank_doctype,
	create_default_banks,
	create_host_settings,
)


def execute():
	click.secho("* Updating India Banking Host to Host Customisations")
	create_bank_doctype()
	create_default_banks()
	create_host_settings()
