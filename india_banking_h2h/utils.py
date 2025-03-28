import random
import re
import string

import frappe
from frappe.model.document import Document

from india_banking_h2h.defaults import DEFAULT_HOSTS


@frappe.whitelist()
def get_default_hosts():
	return DEFAULT_HOSTS


def get_id(length: int = 10, text: str = "") -> str:
	"""
	Generate a random string ID of a specified length, optionally prefixed with a given text.
	If the `length` parameter is a string, it will be used as the prefix text, and
	the length of the generated ID will be equal to the length of this string.
	Args:
	        length (int): The desired length of the generated ID. Defaults to 10.
	        text (str): An optional prefix text to include in the generated ID. Defaults to an empty string.
	Returns:
	        str: A randomly generated string ID of the specified length, optionally prefixed with the given text.
	"""

	if isinstance(length, str):
		text = "".join(re.findall(r"[0-9a-zA-Z]", length))
		return text
	elif isinstance(length, int):
		text = "".join(re.findall(r"[0-9a-zA-Z]", text))
		text_length = len(text)
		if text_length >= length:
			return text[:length]
		else:
			length = length - text_length
			return text + "".join(
				random.choices(string.ascii_lowercase + string.digits, k=length)
			)


def get_existing_doc(doctype: str, filters: dict = None) -> Document | None:
	"""
	Retrieve an existing document object from the database based on the specified filters or document name.

	Args:
	        doctype (str): The name of the DocType to search for.
	        filters (dict): A dictionary of filters to apply when searching for the document. Defaults to None.

	Returns:
	        Document | None: The document object if found, otherwise None.
	"""
	if isinstance(filters, str):
		filters = {"name": filters}
	if filters:
		doc = frappe.get_all(doctype, filters=filters, limit_page_length=1)
		return frappe.get_doc(doctype, doc[0].name) if doc else None
	return None
