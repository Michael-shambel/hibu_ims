#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QSizePolicy, QGraphicsDropShadowEffect, QApplication, QMessageBox
)
from PySide6.QtCore import Signal, QTimer, QThread
from PySide6.QtGui import QFont, Qt, QCursor, QColor
from services.bank_account_service import BankAccountService
from services.new_sale_service import NewSaleService
from services.purchase_service import PurchaseService
from services.expense_service import ExpenseService
from services.bank_transaction_service import BankTransactionService
from services.combined_credit_service import CombinedCreditService
from ui.pages.sales_card_dialog import SalesDetailDialog, LabourExpenseDialog, AllSalesOverviewDialog
from ui.pages.stock_value_dialog import StockValueDialog
from ui.pages.bank_balance_dialog import BankBalanceDialog
from ui.pages.expense_overview_dialog import ExpenseOverviewDialog
from datetime import date, datetime, timedelta
from ui.utils.worker import Worker
import logging

logger = logging.getLogger(__name__)

class DashboardManager(QWidget):
    refresh_requested = Signal()

    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.bank_account_service = BankAccountService()
        self.sale_service = NewSaleService()
        self.purchase_service = PurchaseService()
        self.expense_service = ExpenseService()   # <-- NEW
        self.bank_transaction_service = BankTransactionService()
        self.combined_credit_service = CombinedCreditService()

        self.today_summary = None
        self.yesterday_summary = None
        self.credit_sales_summary = None
        self.all_sales_count = None
        self.credit_purchases_summary = None
        self.combined_credit_summary = None
        self.despatched_count = None
        self.not_despatched_count = None

        # Store cash expenses for dialogs
        self.cash_expenses_today = 0.0
        self.cash_expenses_yesterday = 0.0

        self.init_ui()
        self.refresh()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(60000)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f5f7fa;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #f0f0f0;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #bdc3c7;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #95a5a6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar:horizontal {
                height: 0px;
            }
        """)
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: #f5f7fa;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.setContentsMargins(15, 15, 15, 25)

        # Row 1: Sales Core (5 cards)
        self.create_sales_core_section()

        # Row 2: Products & Operations (4 cards)
        self.create_products_operations_section()

        # Row 3: Financial Health (3 cards)
        self.create_financial_health_section()

        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)

        self.status_bar = self.create_status_bar()
        main_layout.addWidget(self.status_bar)

    def create_sales_core_section(self):
        section = QGroupBox(" Sales Core")
        section.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #2c3e50;
                border: 2px solid #dce4ec;
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 12px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #3498db;
                background-color: white;
            }
        """)
        section_layout = QVBoxLayout(section)
        section_layout.setSpacing(10)
        section_layout.setContentsMargins(12, 15, 12, 12)

        card_container = QWidget()
        card_layout = QHBoxLayout(card_container)
        card_layout.setSpacing(10)
        card_layout.setContentsMargins(0, 0, 0, 0)

        self.sales_core_cards = {}
        card_info = [
            ("Total Sales", "#3498db", self.show_total_sales_details),
            ("Labour Expense", "#e74c3c", self.show_labour_expense_details),
            ("Yesterday Sales", "#9b59b6", self.show_yesterday_sales),
            ("Credit Sales", "#f39c12", self.show_credit_sales_overview),
            ("Sales Overview", "#27ae60", self.show_all_sales_overview)
        ]

        for title, color, handler in card_info:
            card = self.create_clickable_card(title, "Loading...", color, handler)
            card_layout.addWidget(card)
            self.sales_core_cards[title] = card

        section_layout.addWidget(card_container)
        self.scroll_layout.addWidget(section)

    def create_products_operations_section(self):
        section = QGroupBox(" Products & Operations")
        section.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #2c3e50;
                border: 2px solid #dce4ec;
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 12px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #3498db;
                background-color: white;
            }
        """)
        section_layout = QVBoxLayout(section)
        section_layout.setSpacing(10)
        section_layout.setContentsMargins(12, 15, 12, 12)

        card_container = QWidget()
        card_layout = QHBoxLayout(card_container)
        card_layout.setSpacing(10)
        card_layout.setContentsMargins(0, 0, 0, 0)

        self.products_ops_cards = {}
        card_info = [
            ("Stock Value", "#27ae60", self.show_stock_value_details),
            ("Credit Purchases", "#e74c3c", self.show_credit_purchases_overview),
            ("Combined Credit", "#16a085", self.show_combined_credit_overview),
            # ("Despatched Sales", "#3498db", self.show_despatched_sales),
            ("Not Despatched Sales", "#f39c12", self.show_not_despatched_sales)
        ]

        for title, color, handler in card_info:
            card = self.create_clickable_card(title, "Loading...", color, handler)
            card_layout.addWidget(card)
            self.products_ops_cards[title] = card

        section_layout.addWidget(card_container)
        self.scroll_layout.addWidget(section)

    def create_financial_health_section(self):
        section = QGroupBox(" Financial Health")
        section.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #2c3e50;
                border: 2px solid #dce4ec;
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 12px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #3498db;
                background-color: white;
            }
        """)
        section_layout = QVBoxLayout(section)
        section_layout.setSpacing(10)
        section_layout.setContentsMargins(12, 15, 12, 12)

        card_container = QWidget()
        card_layout = QHBoxLayout(card_container)
        card_layout.setSpacing(10)
        card_layout.setContentsMargins(0, 0, 0, 0)

        self.financial_cards = {}
        card_info = [
            ("Profit", "#27ae60", self.show_profit_details),
            ("Expenses", "#e74c3c", self.show_expenses_details),
            ("Bank Balance", "#3498db", self.show_bank_balance_details)
        ]

        for title, color, handler in card_info:
            card = self.create_clickable_card(title, "Loading...", color, handler)
            card_layout.addWidget(card)
            self.financial_cards[title] = card

        section_layout.addWidget(card_container)
        self.scroll_layout.addWidget(section)

    def create_status_bar(self):
        status_bar = QWidget()
        status_bar.setFixedHeight(30)
        status_bar.setStyleSheet("background-color: #34495e; border-top: 1px solid #2c3e50;")
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(10, 0, 10, 0)

        self.last_updated_label = QLabel("Last updated: --:--")
        self.last_updated_label.setStyleSheet("color: #bdc3c7; font-size: 10px;")
        layout.addWidget(self.last_updated_label)
        layout.addStretch()
        return status_bar

    def create_clickable_card(self, title: str, value: str, color_hex: str, click_handler) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 6px;
                border: 1px solid #E0E0E0;
                min-width: 140px;
                max-width: 160px;
            }}
            QFrame:hover {{
                border: 2px solid {color_hex};
                background-color: #f8f9fa;
            }}
        """)
        card.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        card.setFixedHeight(100)
        card.setCursor(QCursor(Qt.PointingHandCursor))

        card.mousePressEvent = lambda event: click_handler() if event.button() == Qt.LeftButton else None

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background-color: {color_hex};
                color: #FFFFFF;
                font-weight: bold;
                padding: 8px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 10px;
            }}
        """)
        header.setFont(QFont("Segoe UI", 9, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setWordWrap(True)

        value_label = QLabel(value)
        value_label.setObjectName("value_label")
        value_label.setStyleSheet("""
            QLabel {
                background-color: #FFFFFF;
                color: #2c3e50;
                padding: 12px 8px;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                font-size: 13px;
            }
        """)
        value_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)

        indicator = QLabel("Click for details")
        indicator.setStyleSheet("color: #7f8c8d; font-size: 7px; padding: 2px; font-style: italic;")
        indicator.setAlignment(Qt.AlignCenter)

        layout.addWidget(header)
        layout.addWidget(value_label)
        layout.addWidget(indicator)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        return card

    def refresh(self):
        if hasattr(self, '_is_refreshing') and self._is_refreshing:
            return
        self._is_refreshing = True

        if hasattr(self, '_refresh_thread') and self._refresh_thread is not None:
            try:
                if self._refresh_thread.isRunning():
                    self._is_refreshing = False
                    return
                self._refresh_thread.quit()
                self._refresh_thread.wait(1000)
            except RuntimeError:
                pass
            self._refresh_thread = None
            self._refresh_worker = None

        self._refresh_thread = QThread()
        self._refresh_worker = Worker(self._fetch_dashboard_data)
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._on_refresh_data)
        self._refresh_worker.error.connect(self._on_refresh_error)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_worker.finished.connect(self._refresh_worker.deleteLater)
        self._refresh_thread.finished.connect(self._cleanup_thread)
        self._refresh_thread.start()
    
    def _cleanup_thread(self):
        self._refresh_thread = None
        self._refresh_worker = None
        self._is_refreshing = False
    
    def _fetch_dashboard_data(self):
        today = date.today()
        yesterday = today - timedelta(days=1)

        today_summary = self.sale_service.get_daily_sales_summary(today)
        yesterday_summary = self.sale_service.get_daily_sales_summary(yesterday)
        credit_sales_summary = self.sale_service.get_credit_sales_summary()
        all_sales_count = self.sale_service.get_all_sales_count()

        credit_purchases_summary = self.purchase_service.get_credit_purchases_summary()
        combined_credit_summary = self.combined_credit_service.get_combined_credit_summary()
        despatched_count = self.sale_service.count_despatch_status_sales(True)
        not_despatched_count = self.sale_service.count_despatch_status_sales(False)

        # Cash expenses for today and yesterday
        cash_expenses_today = self.expense_service.get_cash_expenses_for_date(today)
        cash_expenses_yesterday = self.expense_service.get_cash_expenses_for_date(yesterday)

        cash_account = self.bank_account_service.get_by_account_number('00000')
        cash_account_id = cash_account.id if cash_account else None
        if cash_account_id:
            cash_transfers_today = self.bank_transaction_service.get_total_debit_for_account_on_date(cash_account_id, today)
            cash_transfers_yesterday = self.bank_transaction_service.get_total_debit_for_account_on_date(cash_account_id, yesterday)
        else:
            cash_transfers_today = 0.0
            cash_transfers_yesterday = 0.0

        # Cash receipts from credit sales (credit to cash account)
        cash_receipts_today = self.bank_transaction_service.get_total_credit_for_sales_on_date(cash_account_id, today) if cash_account_id else 0.0
        cash_receipts_yesterday = self.bank_transaction_service.get_total_credit_for_sales_on_date(cash_account_id, yesterday) if cash_account_id else 0.0

        # Cash payments for credit purchases (debit from cash account)
        cash_payments_today = self.bank_transaction_service.get_total_debit_for_purchases_on_date(cash_account_id, today) if cash_account_id else 0.0
        cash_payments_yesterday = self.bank_transaction_service.get_total_debit_for_purchases_on_date(cash_account_id, yesterday) if cash_account_id else 0.0

        # 🆕 Opening cash balances (yesterday's closing balance)
        if cash_account_id:
            opening_cash_balance_today = self.bank_transaction_service.get_balance_before_date(
                cash_account_id, today
            )
            opening_cash_balance_yesterday = self.bank_transaction_service.get_balance_before_date(
                cash_account_id, yesterday
            )
        else:
            opening_cash_balance_today = 0.0
            opening_cash_balance_yesterday = 0.0

        profit = "Loading..."
        expenses = "Loading..."
        bank_balance = "Loading..."
        stock_value = "Loading..."

        return {
            'today': today,
            'yesterday': yesterday,
            'today_summary': today_summary,
            'yesterday_summary': yesterday_summary,
            'credit_sales_summary': credit_sales_summary,
            'all_sales_count': all_sales_count,
            'credit_purchases_summary': credit_purchases_summary,
            'combined_credit_summary': combined_credit_summary,
            'despatched_count': despatched_count,
            'not_despatched_count': not_despatched_count,
            'cash_expenses_today': cash_expenses_today,
            'cash_expenses_yesterday': cash_expenses_yesterday,
            'cash_transfers_today': cash_transfers_today,
            'cash_transfers_yesterday': cash_transfers_yesterday,
            'cash_receipts_today': cash_receipts_today,
            'cash_receipts_yesterday': cash_receipts_yesterday,
            'cash_payments_today': cash_payments_today,
            'cash_payments_yesterday': cash_payments_yesterday,
            'opening_cash_balance_today': opening_cash_balance_today,        # 🆕
            'opening_cash_balance_yesterday': opening_cash_balance_yesterday, # 🆕
            'profit': profit,
            'expenses': expenses,
            'bank_balance': bank_balance,
            'stock_value': stock_value,
        }
    
    def _on_refresh_data(self, data):
        self.current_date = data['today']
        self.yesterday_date = data['yesterday']
        self.today_summary = data['today_summary']
        self.yesterday_summary = data['yesterday_summary']
        self.credit_sales_summary = data['credit_sales_summary']
        self.all_sales_count = data['all_sales_count']
        self.credit_purchases_summary = data['credit_purchases_summary']
        self.combined_credit_summary = data['combined_credit_summary']
        self.despatched_count = data['despatched_count']
        self.not_despatched_count = data['not_despatched_count']
        self.cash_expenses_today = data['cash_expenses_today']
        self.cash_expenses_yesterday = data['cash_expenses_yesterday']
        self.cash_transfers_today = data['cash_transfers_today']
        self.cash_transfers_yesterday = data['cash_transfers_yesterday']
        self.cash_receipts_today = data['cash_receipts_today']
        self.cash_receipts_yesterday = data['cash_receipts_yesterday']
        self.cash_payments_today = data['cash_payments_today']
        self.cash_payments_yesterday = data['cash_payments_yesterday']
        self.opening_cash_balance_today = data['opening_cash_balance_today']           # 🆕
        self.opening_cash_balance_yesterday = data['opening_cash_balance_yesterday']   # 🆕

        self._update_card_value_in_dict(self.sales_core_cards, "Total Sales", f"${data['today_summary']['total_sales_amount']:,.2f}")
        self._update_card_value_in_dict(self.sales_core_cards, "Labour Expense", f"${data['today_summary']['total_labour_expense']:,.2f}")
        self._update_card_value_in_dict(self.sales_core_cards, "Yesterday Sales", f"${data['yesterday_summary']['total_sales_amount']:,.2f}")
        self._update_card_value_in_dict(self.sales_core_cards, "Credit Sales", f"${data['credit_sales_summary']['total_unpaid']:,.2f} Unpaid")
        self._update_card_value_in_dict(self.sales_core_cards, "Sales Overview", str(data['all_sales_count']))

        self._update_card_value_in_dict(self.products_ops_cards, "Stock Value", data['stock_value'])
        self._update_card_value_in_dict(self.products_ops_cards, "Credit Purchases", f"${data['credit_purchases_summary']['total_unpaid']:,.2f} Unpaid")
        self._update_card_value_in_dict(self.products_ops_cards, "Combined Credit", f"{data['combined_credit_summary']['matched_count']} Matched")
        self._update_card_value_in_dict(self.products_ops_cards, "Despatched Sales", str(data['despatched_count']))
        self._update_card_value_in_dict(self.products_ops_cards, "Not Despatched Sales", str(data['not_despatched_count']))

        self._update_card_value_in_dict(self.financial_cards, "Profit", data['profit'])
        self._update_card_value_in_dict(self.financial_cards, "Expenses", data['expenses'])
        self._update_card_value_in_dict(self.financial_cards, "Bank Balance", data['bank_balance'])

        current_time = datetime.now().strftime("%H:%M:%S")
        self.last_updated_label.setText(f"Last updated: {current_time}")
        self.last_updated_label.setStyleSheet("color: #bdc3c7; font-size: 10px;")
        self.refresh_requested.emit()

        self._is_refreshing = False
        
    def _on_refresh_error(self, error):
        logger.error(f"Dashboard refresh error: {error}")
        self._is_refreshing = False
        # Automatic refresh runs every 60s with no user interaction, so a blocking
        # QMessageBox would nag the user repeatedly on any transient error. Surface
        # the failure quietly in the status bar instead and keep showing last-good data.
        current_time = datetime.now().strftime("%H:%M:%S")
        self.last_updated_label.setText(f"Refresh failed at {current_time} (showing last known data)")
        self.last_updated_label.setStyleSheet("color: #e74c3c; font-size: 10px;")

    def _update_card_value_in_dict(self, card_dict, card_title, new_value):
        card = card_dict.get(card_title)
        if card:
            value_label = card.findChild(QLabel, "value_label")
            if value_label:
                value_label.setText(new_value)

    # ─── Click handlers that open SalesDetailDialog ───
    def show_total_sales_details(self):
        if self.today_summary is None:
            QMessageBox.warning(self, "Not Ready", "Data is still loading. Please wait a moment.")
            return
        dialog = SalesDetailDialog(
            self, "Today's Sales Summary", self.today_summary, self.current_user,
            cash_expenses=self.cash_expenses_today,
            cash_transfers=self.cash_transfers_today,
            cash_receipts=self.cash_receipts_today,
            cash_payments=self.cash_payments_today,
            opening_cash_balance=self.opening_cash_balance_today,   # 🆕
            date=self.current_date
        )
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_yesterday_sales(self):
        if self.yesterday_summary is None:
            QMessageBox.warning(self, "Not Ready", "Data is still loading. Please wait a moment.")
            return
        dialog = SalesDetailDialog(
            self, "Yesterday's Sales Summary", self.yesterday_summary, self.current_user,
            cash_expenses=self.cash_expenses_yesterday,
            cash_transfers=self.cash_transfers_yesterday,
            cash_receipts=self.cash_receipts_yesterday,
            cash_payments=self.cash_payments_yesterday,
            opening_cash_balance=self.opening_cash_balance_yesterday,  # 🆕
            date=self.yesterday_date
        )
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    # ─── Other handlers (unchanged) ───
    def show_labour_expense_details(self):
        data = self.sale_service.get_sales_with_labour_expense(date.today())
        dialog = LabourExpenseDialog(self, "Labour Expense Details", data, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_credit_sales_overview(self):
        from ui.pages.credit_sales_overview_dialog import CreditSalesOverviewDialog
        dialog = CreditSalesOverviewDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_all_sales_overview(self):
        dialog = AllSalesOverviewDialog(self, self.current_user)
        dialog.edit_sale_requested.connect(self._on_edit_sale_from_overview)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()
    
    def _on_edit_sale_from_overview(self, sale_id):
        """Switch to the SalesManager page and load the selected sale for editing."""
        main_window = self.window()
        if hasattr(main_window, 'pages') and "Sales" in main_window.pages:
            # Switch to Sales page using the main window's switch_page method
            main_window.switch_page("Sales")
            # Load the sale for editing
            main_window.pages["Sales"].load_sale_for_edit(sale_id)
        else:
            logger.warning("Could not find Sales page on main window")

    def show_credit_purchases_overview(self):
        from ui.pages.credit_purchases_overview_dialog import CreditPurchasesOverviewDialog
        dialog = CreditPurchasesOverviewDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_combined_credit_overview(self):
        from ui.pages.combined_credit_overview_dialog import CombinedCreditOverviewDialog
        dialog = CombinedCreditOverviewDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_despatched_sales(self):
        from ui.pages.sales_card_dialog import DespatchSalesDialog
        sales = self.sale_service.get_despatch_status_sales(True)
        dialog = DespatchSalesDialog(self, "Despatched Sales", sales, self.current_user, is_despatched=True)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_not_despatched_sales(self):
        sales = self.sale_service.get_despatch_status_sales(False)
        from ui.pages.sales_card_dialog import DespatchSalesDialog
        dialog = DespatchSalesDialog(self, "Not Despatched Sales", sales, self.current_user, is_despatched=False)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_stock_value_details(self):
        dialog = StockValueDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_profit_details(self):
        from ui.pages.sales_card_dialog import ProfitDialog
        dialog = ProfitDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_expenses_details(self):
        dialog = ExpenseOverviewDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()

    def show_bank_balance_details(self):
        dialog = BankBalanceDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.finished.connect(self.refresh)
        dialog.show()