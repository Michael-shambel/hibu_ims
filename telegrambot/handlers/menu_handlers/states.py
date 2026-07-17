# states.py
from enum import IntEnum

class ConversationStates(IntEnum):
    ROLE_SELECTION = 0
    ADMIN_MENU = 1
    SALES_TEAM_MENU = 2
    SUPPLIER_MENU = 3
    CUSTOMER_MENU = 4
    TRANSACTION_REPORTS_MENU = 5
    ETHIOPIAN_MONTH_SELECTION = 6
    ETHIOPIAN_DATE_SELECTION = 7
    PRODUCT_REPORTS_MENU = 8
    CREDIT_REPORTS_MENU = 9
    SELECT_SUPPLIER_FOR_CREDIT_PURCHASE = 10
    SELECT_DATE_GROUP_FOR_CREDIT_PURCHASE = 11
    SALES_TEAM_AUTH_USERNAME = 12
    SALES_TEAM_AUTH_PASSWORD = 13
    SALES_TEAM_MENU_MAIN = 14
    CUSTOMER_AUTH_PHONE = 15
    CUSTOMER_AUTH_SUCCESS = 16
    CUSTOMER_MENU_MAIN = 17
    SUPPLIER_AUTH_PHONE = 18
    SUPPLIER_MENU_MAIN = 19
    BANK_MENU = 20
    BANK_TRANSFER_FROM_ACCOUNT = 21
    BANK_TRANSFER_TO_ACCOUNT = 22
    BANK_TRANSFER_AMOUNT = 23
    BANK_TRANSFER_REASON = 24
    BANK_TRANSFER_EXTERNAL_PAYEE = 25
    EXPENSE_MENU = 26
    EXPENSE_TYPE_SELECTION = 27
    EXPENSE_BANK_ACCOUNT_SELECTION = 28
    EXPENSE_CATEGORY_SELECTION = 29
    EXPENSE_AMOUNT_ENTRY = 30
    EXPENSE_NOTES_ENTRY = 31


# Update the tuple - change range from 17 to 18
(ROLE_SELECTION, ADMIN_MENU, SALES_TEAM_MENU, SUPPLIER_MENU, CUSTOMER_MENU,
 TRANSACTION_REPORTS_MENU, ETHIOPIAN_MONTH_SELECTION, ETHIOPIAN_DATE_SELECTION,
 PRODUCT_REPORTS_MENU, CREDIT_REPORTS_MENU, SELECT_SUPPLIER_FOR_CREDIT_PURCHASE,
 SELECT_DATE_GROUP_FOR_CREDIT_PURCHASE, SALES_TEAM_AUTH_USERNAME,
 SALES_TEAM_AUTH_PASSWORD, SALES_TEAM_MENU_MAIN, CUSTOMER_AUTH_PHONE,
 CUSTOMER_AUTH_SUCCESS, CUSTOMER_MENU_MAIN, SUPPLIER_AUTH_PHONE, SUPPLIER_MENU_MAIN, BANK_MENU,
 BANK_TRANSFER_FROM_ACCOUNT, BANK_TRANSFER_TO_ACCOUNT, BANK_TRANSFER_AMOUNT, BANK_TRANSFER_REASON,
 BANK_TRANSFER_EXTERNAL_PAYEE, EXPENSE_MENU, EXPENSE_TYPE_SELECTION, EXPENSE_BANK_ACCOUNT_SELECTION,
 EXPENSE_CATEGORY_SELECTION, EXPENSE_AMOUNT_ENTRY, EXPENSE_NOTES_ENTRY) = range(32)


# Role constants for consistent usage
ROLE_ADMIN = "admin"
ROLE_SALES_TEAM = "sales_team"
ROLE_SUPPLIER = "supplier"
ROLE_CUSTOMER = "customer"

# Callback data constants (avoid hardcoded strings)
class CallbackData:
    # Role selection
    ROLE_ADMIN = "role_admin"
    ROLE_SALES_TEAM = "role_storeteam"   # keep old naming for compatibility
    ROLE_SUPPLIER = "role_supplier"
    ROLE_CUSTOMER = "role_customer"
    
    # Admin menu
    SALES_REPORTS = "sales_reports"
    PRODUCT_REPORTS = "product_reports"
    CREDIT_REPORTS = "credit_reports"
    BANK_TRANSFER = "bank_transfer"
    
    # Sales reports submenu
    SALES_TRANSACTIONS = "sales_transactions"
    SALES_BY_PAYMENT = "sales_by_payment"
    CREDIT_STATUS = "credit_status"
    BACK_TO_ADMIN = "back_to_admin"

    # New date selection callbacks
    SELECT_MONTH = "select_month_"
    SELECT_DATE = "select_date_"
    CONFIRM_DATE = "confirm_date"
    CANCEL_DATE = "cancel_date"

    STOCK_VALUATION = "stock_valuation"
    LOW_STOCK = "low_stock"
    STOCK_IN_HISTORY = "stock_in_history"

    PURCHASE_ITEM_HISTORY = "purchase_item_history"
    PURCHASE_PAYMENT_HISTORY = "purchase_payment_history"

    SELECT_SUPPLIER_PREFIX = "select_supplier_"
    SELECT_DATE_GROUP_PREFIX = "select_date_group_"
    BACK_TO_SUPPLIER_SELECTION = "back_to_supplier_selection"
    
    # Customer menu (ADD THESE)
    CUSTOMER_CREDIT_ITEMS = "customer_credit_items"
    CUSTOMER_CREDIT_PAYMENTS = "customer_credit_payments"

    SUPPLIER_CREDIT_ITEMS = "supplier_credit_items"
    SUPPLIER_CREDIT_PAYMENTS = "supplier_credit_payments"

    BANK_GET_TOTAL_BALANCE = "bank_get_total_balance"
    BANK_GET_INFO = "bank_get_info"
    BANK_TRANSFER_FUNDS = "bank_transfer_funds"
    BANK_ACCOUNT_PREFIX = "bank_acct_"
    BANK_BACK_TO_MENU = "bank_back_to_menu"

    EXPENSE_REPORT = "expense_report"
    RECORD_EXPENSE = "record_expense"
    EXPENSE_TYPE_BUSINESS = "expense_type_business"
    EXPENSE_TYPE_PERSONAL = "expense_type_personal"
    
    # General
    CANCEL = "cancel"

# Persistent keyboard button texts
class ButtonText:
    START_MENU = "🔄 Start Menu"
    CANCEL = "❌ Cancel"
    BACK_TO_ADMIN = "🔙 Back to Admin"
    SALES_REPORTS = "📊 Sales Reports"
    PRODUCT_REPORTS = "📦 Product Reports"
    CREDIT_REPORT = "💰 Credit Report"
    BANK_TRANSFER = "🏦 Bank Transfer"

ETHIOPIAN_MONTHS = [
    ("መስከረም", "01"),
    ("ጥቅምት", "02"),
    ("ህዳር", "03"),
    ("ታህሳስ", "04"),
    ("ጥር", "05"),
    ("የካቲት", "06"),
    ("መጋቢት", "07"),
    ("ሚያዝያ", "08"),
    ("ግንቦት", "09"),
    ("ሰኔ", "10"),
    ("ሐምሌ", "11"),
    ("ነሐሴ", "12"),
    ("ጳጉሜ", "13")
]