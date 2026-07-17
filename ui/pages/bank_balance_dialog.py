from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QApplication, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFrame, QWidget, QGridLayout
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor, QCursor
from services.bank_account_service import BankAccountService
from services.bank_transaction_service import BankTransactionService
from models.bank_transactions import TransactionDirectionEnum
from ui.components.ethiopian_date import EthiopianDateConverter
from datetime import date, datetime
import math


class BankBalanceDialog(QDialog):
    """Bank Account"""
    def __init__(self, parent, current_user=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Bank Balance Overview")
        
        screen = QApplication.primaryScreen().availableGeometry()
        desired_height = min(int(screen.height() * 0.8), 700)
        desired_height = max(desired_height, 500)
        self.setMinimumSize(1000, 500)
        self.resize(1400, desired_height)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        
        self.current_user = current_user
        self.bank_account_service = BankAccountService()
        self.bank_transaction_service = BankTransactionService()
        self.accounts = []
        self.transactions = []
        self.current_account_id = None  # None = All Accounts

        self.init_ui()
        self.load_accounts()
        self.apply_filter()
        
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(15)

        # Summary cards container
        self.cards_container = QWidget()
        cards_layout = QHBoxLayout(self.cards_container)
        cards_layout.setSpacing(20)
        self.summary_cards = {}
        card_info = [
            ("Current Balance", "$0.00", "#3498db"),
            ("Total Credits", "$0.00", "#2ecc71"),
            ("Total Debits", "$0.00", "#e74c3c"),
            ("Net Change", "$0.00", "#f39c12")
        ]
        for title, value, color in card_info:
            card = self._create_summary_card(title, value, color)
            cards_layout.addWidget(card)
            self.summary_cards[title] = card
        main_layout.addWidget(self.cards_container)

        # Filter row with label + vertical container (All Accounts button + 2-row grid)
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 10, 0, 10)
        filter_layout.setSpacing(10)

        # bank_label = QLabel("Bank Account:")
        # bank_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        # filter_layout.addWidget(bank_label)

        # Vertical container: "All Accounts" button on top, grid for individual banks below
        button_vertical_container = QWidget()
        button_vertical_layout = QVBoxLayout(button_vertical_container)
        button_vertical_layout.setContentsMargins(0, 0, 0, 0)
        button_vertical_layout.setSpacing(5)

        # "All Accounts" button (span full width)
        self.all_accounts_btn = QPushButton("All Accounts")
        self.all_accounts_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.all_accounts_btn.setCursor(Qt.PointingHandCursor)
        self.all_accounts_btn.clicked.connect(self._on_all_accounts_clicked)
        self._style_account_button(self.all_accounts_btn, is_active=True)  # initially active
        button_vertical_layout.addWidget(self.all_accounts_btn)

        # Grid for individual bank account buttons (2 rows, dynamic columns)
        self.bank_grid = QGridLayout()
        self.bank_grid.setSpacing(10)
        button_vertical_layout.addLayout(self.bank_grid)

        filter_layout.addWidget(button_vertical_container)
        filter_layout.addStretch()
        main_layout.addWidget(filter_widget)

        # Transactions table
        self.table = QTableWidget()
        headers = ["Date (Ethiopian)", "Description", "Debit", "Credit", "Balance"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.table.verticalHeader().setDefaultSectionSize(55)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 15px;
                font-weight: bold;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 12px;
                font-weight: bold;
                font-size: 15px;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        main_layout.addWidget(self.table, 1)

    def _create_summary_card(self, title, value, color_hex):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 1px solid #E0E0E0;
                min-width: 180px;
                max-width: 220px;
            }}
        """)
        card.setFixedHeight(100)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background-color: {color_hex};
                color: white;
                font-weight: bold;
                padding: 10px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 12px;
            }}
        """)
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))

        value_label = QLabel(value)
        value_label.setObjectName("value_label")
        value_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #2c3e50;
                padding: 15px 10px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFont(QFont("Segoe UI", 14, QFont.Bold))

        layout.addWidget(header)
        layout.addWidget(value_label)
        return card

    def load_accounts(self):
        """Load bank accounts and create clickable filter buttons."""
        self.accounts = self.bank_account_service.get_all()
        self._create_account_buttons()

    def _create_account_buttons(self):
        """
        Place individual bank buttons in a 2-row grid.
        The "All Accounts" button remains separate above the grid.
        """
        # Clear existing grid
        while self.bank_grid.count():
            item = self.bank_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Update "All Accounts" button style
        self._style_account_button(self.all_accounts_btn, is_active=self.current_account_id is None)

        # Build bank buttons
        n = len(self.accounts)
        if n == 0:
            return

        # We want exactly 2 rows. Number of columns = ceil(n / 2)
        cols = math.ceil(n / 2)

        for i, acc in enumerate(self.accounts):
            balance = self.bank_transaction_service.get_balance(acc.id)
            display_name = f"{acc.account_name} ({acc.bank_name})"
            if acc.account_number:
                display_name += f" - {acc.account_number[-4:]}"
            btn_text = f"{display_name}: ${balance:,.2f}"
            btn = QPushButton(btn_text)
            btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, aid=acc.id: self._on_account_button_clicked(aid))
            self._style_account_button(btn, is_active=self.current_account_id == acc.id)

            row = i // cols
            col = i % cols
            self.bank_grid.addWidget(btn, row, col)

        # Make columns equally stretchy
        for c in range(cols):
            self.bank_grid.setColumnStretch(c, 1)

    def _style_account_button(self, btn, is_active=False):
        """Apply yellow/orange styling to match SalesDetailDialog bank buttons."""
        if is_active:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e67e22;
                    color: white;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: 2px solid #d35400;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #d35400; }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f39c12;
                    color: white;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: none;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #e67e22; }
            """)

    def _on_account_button_clicked(self, account_id):
        self.current_account_id = account_id
        self._create_account_buttons()  # refresh button styles
        self.apply_filter()

    def _on_all_accounts_clicked(self):
        self.current_account_id = None
        self._create_account_buttons()
        self.apply_filter()

    def apply_filter(self):
        """Fetch transactions for the selected account (or all) and update UI."""
        account_id = self.current_account_id

        total_credit = 0.0
        total_debit = 0.0
        ending_balance = 0.0
        self.transactions = []

        if account_id:
            # Single account
            self.transactions = self.bank_transaction_service.get_transactions(
                account_id=account_id
            )
            ending_balance = self.bank_transaction_service.get_balance(account_id)
            total_credit = sum(t.amount for t in self.transactions if t.direction == TransactionDirectionEnum.CREDIT)
            total_debit = sum(t.amount for t in self.transactions if t.direction == TransactionDirectionEnum.DEBIT)
        else:
            # All accounts
            for acc in self.accounts:
                txns = self.bank_transaction_service.get_transactions(account_id=acc.id)
                self.transactions.extend(txns)
                credit_sum = sum(t.amount for t in txns if t.direction == TransactionDirectionEnum.CREDIT)
                debit_sum = sum(t.amount for t in txns if t.direction == TransactionDirectionEnum.DEBIT)
                total_credit += credit_sum
                total_debit += debit_sum
                ending_balance += self.bank_transaction_service.get_balance(acc.id)
            self.transactions.sort(key=lambda t: (t.transaction_date, t.id))

        net_change = total_credit - total_debit

        # Update summary cards
        self.summary_cards["Current Balance"].findChild(QLabel, "value_label").setText(f"${ending_balance:,.2f}")
        self.summary_cards["Total Credits"].findChild(QLabel, "value_label").setText(f"${total_credit:,.2f}")
        self.summary_cards["Total Debits"].findChild(QLabel, "value_label").setText(f"${total_debit:,.2f}")
        self.summary_cards["Net Change"].findChild(QLabel, "value_label").setText(f"${net_change:,.2f}")

        self.populate_table()

    def populate_table(self):
        """Populate transaction table with running balance."""
        self.table.setRowCount(len(self.transactions))

        for row, tx in enumerate(self.transactions):
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(tx.transaction_date)
            date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            desc = tx.description or ""
            if tx.reference_number:
                desc += f" (Ref: {tx.reference_number})"
            desc_item = QTableWidgetItem(desc)
            desc_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 1, desc_item)

            debit_text = f"${tx.amount:,.2f}" if tx.direction == TransactionDirectionEnum.DEBIT else ""
            debit_item = QTableWidgetItem(debit_text)
            debit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            debit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, debit_item)

            credit_text = f"${tx.amount:,.2f}" if tx.direction == TransactionDirectionEnum.CREDIT else ""
            credit_item = QTableWidgetItem(credit_text)
            credit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            credit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, credit_item)

            balance_item = QTableWidgetItem(f"${tx.balance_after:,.2f}")
            balance_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, balance_item)

        self.table.resizeRowsToContents()