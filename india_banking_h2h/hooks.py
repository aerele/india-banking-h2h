app_name = "india_banking_h2h"
app_title = "India Banking H2H"
app_publisher = "Aerele Technologies Private Limited"
app_description = "India Banking H2H is a Frappe-based application designed for secure and automated Host-to-Host (H2H) bank integrations. It facilitates seamless payment processing by generating structured payment files and securely transferring them to a configured bank server via SFTP. The app ensures efficient and compliant financial transactions by integrating with ERP systems and banking networks."
app_email = "hello@aerele.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "india_banking_h2h",
# 		"logo": "/assets/india_banking_h2h/logo.png",
# 		"title": "India Banking H2H",
# 		"route": "/india_banking_h2h",
# 		"has_permission": "india_banking_h2h.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/india_banking_h2h/css/india_banking_h2h.css"
# app_include_js = "/assets/india_banking_h2h/js/india_banking_h2h.js"

# include js, css files in header of web template
# web_include_css = "/assets/india_banking_h2h/css/india_banking_h2h.css"
# web_include_js = "/assets/india_banking_h2h/js/india_banking_h2h.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "india_banking_h2h/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "india_banking_h2h/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "india_banking_h2h.utils.jinja_methods",
# 	"filters": "india_banking_h2h.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "india_banking_h2h.install.before_install"
after_install = "india_banking_h2h.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "india_banking_h2h.uninstall.before_uninstall"
# after_uninstall = "india_banking_h2h.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "india_banking_h2h.utils.before_app_install"
# after_app_install = "india_banking_h2h.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "india_banking_h2h.utils.before_app_uninstall"
# after_app_uninstall = "india_banking_h2h.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "india_banking_h2h.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"india_banking_h2h.tasks.all"
# 	],
# 	"daily": [
# 		"india_banking_h2h.tasks.daily"
# 	],
# 	"hourly": [
# 		"india_banking_h2h.tasks.hourly"
# 	],
# 	"weekly": [
# 		"india_banking_h2h.tasks.weekly"
# 	],
# 	"monthly": [
# 		"india_banking_h2h.tasks.monthly"
# 	],
# }

scheduler_events = {
	"cron": {
		"*/5 * * * *": "india_banking_h2h.tasks.fetch_payment_status",
	},
}

# Testing
# -------

# before_tests = "india_banking_h2h.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "india_banking_h2h.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "india_banking_h2h.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["india_banking_h2h.utils.before_request"]
# after_request = ["india_banking_h2h.utils.after_request"]

# Job Events
# ----------
# before_job = ["india_banking_h2h.utils.before_job"]
# after_job = ["india_banking_h2h.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"india_banking_h2h.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
