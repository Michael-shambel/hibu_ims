from telegram.ext import (
    CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
)
from telegrambot.handlers.menu_handlers.states import (
    EXPENSE_NOTES_ENTRY, ROLE_SELECTION, ADMIN_MENU, TRANSACTION_REPORTS_MENU, CREDIT_REPORTS_MENU,
    ETHIOPIAN_MONTH_SELECTION, ETHIOPIAN_DATE_SELECTION,  PRODUCT_REPORTS_MENU,
    SELECT_SUPPLIER_FOR_CREDIT_PURCHASE, SELECT_DATE_GROUP_FOR_CREDIT_PURCHASE,
    SALES_TEAM_AUTH_USERNAME, SALES_TEAM_AUTH_PASSWORD, SALES_TEAM_MENU_MAIN,
    CUSTOMER_AUTH_PHONE, CUSTOMER_MENU_MAIN, SUPPLIER_AUTH_PHONE, SUPPLIER_MENU_MAIN,
    BANK_MENU, BANK_TRANSFER_FROM_ACCOUNT, BANK_TRANSFER_TO_ACCOUNT,
    BANK_TRANSFER_AMOUNT, BANK_TRANSFER_REASON, BANK_TRANSFER_EXTERNAL_PAYEE,
    EXPENSE_MENU, EXPENSE_TYPE_SELECTION, EXPENSE_BANK_ACCOUNT_SELECTION,
    EXPENSE_CATEGORY_SELECTION, EXPENSE_AMOUNT_ENTRY
)
from telegrambot.handlers.menu_handlers.main_menu import (
    start, cancel, handle_role_selection, admin_menu_handler, handle_persistent_buttons, get_my_id
)
from telegrambot.handlers.menu_handlers.sales_menu import (
    sales_reports_menu,
    sales_submenu_handler,
    sales_reports_text_handler,
    handle_month_selection,
    handle_date_input
)

from telegrambot.handlers.menu_handlers.product_menu import (
    product_submenu_handler, product_reports_text_handler
)

from telegrambot.handlers.menu_handlers.credit_menu import (
    credit_submenu_handler, credit_reports_text_handler
)

from telegrambot.handlers.reports.purchase_reports import (
    supplier_selection_handler, date_group_selection_handler
)

from telegrambot.handlers.menu_handlers.sales_team_auth import (
    ask_sales_team_username,
    receive_username_ask_password,
    receive_password_authenticate,
    sales_team_menu_handler
)

from telegrambot.handlers.menu_handlers.customer_menu import (
    receive_phone_number,
    customer_menu_handler  # ADD THIS IMPORT
)

from telegrambot.handlers.menu_handlers.supplier_menu import (
    receive_supplier_phone, supplier_menu_handler
)

from telegrambot.handlers.menu_handlers.bank_menu import (
    bank_menu_handler,
    bank_menu_callback_handler,
    transfer_from_account_handler,
    transfer_to_account_handler,
    transfer_amount_handler,
    transfer_reason_handler,
    transfer_external_payee_handler
)

from telegrambot.handlers.menu_handlers.expense_menu import (
    expense_menu_entry,
    expense_menu_handler,
    expense_type_selection_handler,
    expense_bank_account_selection_handler,
    expense_category_selection_handler,
    expense_amount_entry_handler,
    expense_notes_entry_handler,
)

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start),
                  CommandHandler('getid', get_my_id)
                ],
    states={
        ROLE_SELECTION: [
            CallbackQueryHandler(handle_role_selection),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        ADMIN_MENU: [
            CallbackQueryHandler(admin_menu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)
        ],
        TRANSACTION_REPORTS_MENU: [
            CallbackQueryHandler(sales_submenu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, sales_reports_text_handler)
        ],
        ETHIOPIAN_MONTH_SELECTION: [
            CallbackQueryHandler(handle_month_selection),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        ETHIOPIAN_DATE_SELECTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_input)
        ],
        PRODUCT_REPORTS_MENU: [
            CallbackQueryHandler(product_submenu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, product_reports_text_handler)
        ],
        CREDIT_REPORTS_MENU: [
            CallbackQueryHandler(credit_submenu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, credit_reports_text_handler)
        ],
        SELECT_SUPPLIER_FOR_CREDIT_PURCHASE: [
            CallbackQueryHandler(supplier_selection_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        SELECT_DATE_GROUP_FOR_CREDIT_PURCHASE: [
            CallbackQueryHandler(date_group_selection_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        SALES_TEAM_AUTH_USERNAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username_ask_password)
        ],
        SALES_TEAM_AUTH_PASSWORD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password_authenticate)
        ],
        SALES_TEAM_MENU_MAIN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, sales_team_menu_handler),
            CallbackQueryHandler(sales_team_menu_handler)
        ],
        CUSTOMER_AUTH_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone_number)
        ],
        # ADD THE NEW CUSTOMER MENU MAIN STATE
        CUSTOMER_MENU_MAIN: [
            CallbackQueryHandler(customer_menu_handler),  # Handle inline button clicks
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)  # Handle persistent keyboard (Start Menu, Cancel)
        ],
        SUPPLIER_AUTH_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_supplier_phone)
        ],
        SUPPLIER_MENU_MAIN: [
            CallbackQueryHandler(supplier_menu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        BANK_MENU: [
            CallbackQueryHandler(bank_menu_callback_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        BANK_TRANSFER_FROM_ACCOUNT: [
            CallbackQueryHandler(transfer_from_account_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        BANK_TRANSFER_TO_ACCOUNT: [
            CallbackQueryHandler(transfer_to_account_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        BANK_TRANSFER_AMOUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount_handler)
        ],
        BANK_TRANSFER_REASON: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_reason_handler)
        ],
        BANK_TRANSFER_EXTERNAL_PAYEE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_external_payee_handler)
        ],
        EXPENSE_MENU: [
            CallbackQueryHandler(expense_menu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        EXPENSE_TYPE_SELECTION: [
            CallbackQueryHandler(expense_type_selection_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        EXPENSE_BANK_ACCOUNT_SELECTION: [
            CallbackQueryHandler(expense_bank_account_selection_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        EXPENSE_CATEGORY_SELECTION: [
            CallbackQueryHandler(expense_category_selection_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_persistent_buttons)
        ],
        EXPENSE_AMOUNT_ENTRY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount_entry_handler)
        ],
        EXPENSE_NOTES_ENTRY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, expense_notes_entry_handler)
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel),
        CommandHandler('start', start),
        CommandHandler('getid', get_my_id),
        CallbackQueryHandler(cancel, pattern='^cancel$'),
    ],
    per_user=True,
    per_chat=True,
    per_message=False,
    name="role_based_conversation",
    persistent=True
)