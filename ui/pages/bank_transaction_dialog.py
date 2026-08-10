#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDateEdit, QComboBox, QMessageBox, QAbstractItemView, QWidget,
    QFormLayout, QDoubleSpinBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QFont

from services.bank_transaction_service import BankTransactionService
from services.bank_account_service import BankAccountService
from models.bank_transactions import TransactionDirectionEnum
from ui.components.ethiopian_date import EthiopianDateConverter
import logging

logger = logging.getLogger(__name__)


class BankTransactionHistoryDialog(QDialog):
    def __init__(self, account_id: int, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.transaction_service = BankTransactionService()
        self.account_service = BankAccountService()

        self.setWindowTitle("Bank Account Transaction History")
        self.setMinimumSize(1000, 600)
        self.setModal(True)

        self.account = self.account_service.get_by_id(account_id)

        if not self.account:
            QMessageBox.critical(self, "Error", "Bank account not found.")
            self.reject()
            return
        
        self.setup_ui()
        self.load_transactions()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel(f"Transaction History: {self.account.account_name} ({self.account.bank_name})")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        # Summary Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        self.credit_card = self.create_summary_card("Total Credit", "$0.00", "#27ae60")
        cards_layout.addWidget(self.credit_card)

        self.debit_card = self.create_summary_card("Total Debit", "$0.00", "#e74c3c")
        cards_layout.addWidget(self.debit_card)

        self.balance_card = self.create_summary_card("Current Balance", "$0.00", "#3498db")
        cards_layout.addWidget(self.balance_card)

        layout.addLayout(cards_layout)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        filter_layout.addWidget(QLabel("From:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-3))
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setStyleSheet("padding: 5px; border: 1px solid #bdc3c7; border-radius: 4px;")
        filter_layout.addWidget(self.start_date_edit)

        filter_layout.addWidget(QLabel("To:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setStyleSheet("padding: 5px; border: 1px solid #bdc3c7; border-radius: 4px;")
        filter_layout.addWidget(self.end_date_edit)

        filter_layout.addWidget(QLabel("Direction:"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("All", None)
        self.direction_combo.addItem("Credit", TransactionDirectionEnum.CREDIT)
        self.direction_combo.addItem("Debit", TransactionDirectionEnum.DEBIT)
        self.direction_combo.setStyleSheet("padding: 5px; border: 1px solid #bdc3c7; border-radius: 4px;")
        filter_layout.addWidget(self.direction_combo)

        self.apply_filter_btn = QPushButton("Apply Filters")
        self.apply_filter_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.apply_filter_btn.clicked.connect(self.apply_filters)
        filter_layout.addWidget(self.apply_filter_btn)

        self.reset_filter_btn = QPushButton("Reset")
        self.reset_filter_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.reset_filter_btn.clicked.connect(self.reset_filters)
        filter_layout.addWidget(self.reset_filter_btn)

        # NEW: Reset History button
        self.reset_history_btn = QPushButton("🔄 Reset History (Permanent)")
        self.reset_history_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.reset_history_btn.clicked.connect(self.reset_transaction_history)
        filter_layout.addWidget(self.reset_history_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date", "Credit", "Debit", "Balance", "Description", "Actions"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #e0e0e0;
                font-weight: 600;
            }
        """)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Credit
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Debit
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Balance
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # Description
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Actions

        layout.addWidget(self.table)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #6c7a7d;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def create_summary_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
                padding: 10px;
            }}
        """)
        card.setFixedHeight(150)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; color: #7f8c8d;")

        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        value_label.setAlignment(Qt.AlignLeft)

        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)

        card.value_label = value_label
        return card

    def apply_filters(self):
        self.load_transactions()

    def reset_filters(self):
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-3))
        self.end_date_edit.setDate(QDate.currentDate())
        self.direction_combo.setCurrentIndex(0)
        self.load_transactions()
    
    # NEW: Reset transaction history with custom starting balance
    def reset_transaction_history(self):
        # Custom dialog for starting balance
        dialog = QDialog(self)
        dialog.setWindowTitle("Reset Transaction History")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        warning = QLabel(
            f"This will HIDE all current transactions for account '{self.account.account_name}'.\n"
            "They remain in the database but will no longer appear.\n"
            "Future transactions will build from the starting balance you set.\n\n"
            "THIS ACTION CANNOT BE UNDONE."
        )
        warning.setStyleSheet("color: #e74c3c; font-weight: bold;")
        layout.addWidget(warning)

        form_layout = QFormLayout()
        balance_spin = QDoubleSpinBox()
        balance_spin.setRange(-999999999.99, 999999999.99)
        balance_spin.setDecimals(2)
        balance_spin.setPrefix("$ ")
        balance_spin.setValue(0.00)
        form_layout.addRow("New Starting Balance:", balance_spin)
        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Yes).setText("Reset")
        button_box.button(QDialogButtonBox.Yes).setStyleSheet("background-color: #e74c3c; color: white;")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() != QDialog.Accepted:
            return

        new_starting_balance = balance_spin.value()

        # Final confirmation
        reply = QMessageBox.question(
            self,
            "Final Confirmation",
            f"Reset history for '{self.account.account_name}' with starting balance ${new_starting_balance:,.2f}?\n\n"
            "All past transactions will be hidden and cannot be restored.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        success = self.account_service.reset_transaction_history(self.account_id, new_starting_balance)
        if success:
        #     QMessageBox.information(self, "Reset Complete",
        #                             f"Transaction history has been reset.\n"
        #                             f"Starting balance set to ${new_starting_balance:,.2f}.\n"
        #                             "All previous transactions are now hidden.\n"
        #                             "The current balance card reflects the new starting balance.")
            self.load_transactions()
        else:
            QMessageBox.critical(self, "Error", "Failed to reset transaction history.")
    
    def load_transactions(self):
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()
        direction = self.direction_combo.currentData()

        try:
            transactions = self.transaction_service.get_transactions(
                account_id=self.account_id,
                start_date=start_date,
                end_date=end_date,
                direction=direction
            )

            self.table.setRowCount(0)
            total_credit = 0.0
            total_debit = 0.0

            # Get the actual current balance (includes reset marker if any)
            actual_current_balance = self.transaction_service.get_balance(self.account_id)

            # Recalculate running balance from the first displayed transaction
            running_balance = 0.0
            if transactions:
                first_date = transactions[0].transaction_date
                # Include reset marker in balance_before? The marker is excluded from transactions list,
                # but its balance_after is already the starting balance. We can get it directly.
                # Simpler: compute running_balance by starting from the balance before the first displayed transaction,
                # which we can get from the latest transaction before that date (including the reset marker).
                # However, since we excluded the reset marker, we need a separate method.
                # For correctness, we can get the balance before the first tx using get_balance_before_date.
                balance_before = self.transaction_service.get_balance_before_date(
                    self.account_id, first_date, exclude_transaction_id=None
                )
                running_balance = balance_before

            for tx in transactions:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setRowHeight(row, 35)

                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(tx.transaction_date)
                eth_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year}"

                date_item = QTableWidgetItem(eth_date_str)
                date_item.setToolTip(f"Gregorian: {tx.transaction_date.strftime('%Y-%m-%d')}")
                date_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 0, date_item)

                if tx.direction == TransactionDirectionEnum.CREDIT:
                    running_balance += tx.amount
                    credit = tx.amount
                    debit = 0.0
                else:
                    running_balance -= tx.amount
                    credit = 0.0
                    debit = tx.amount

                credit_item = QTableWidgetItem(f"${credit:,.2f}" if credit > 0 else "")
                credit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if credit > 0:
                    credit_item.setForeground(QColor("#27ae60"))
                self.table.setItem(row, 1, credit_item)

                debit_item = QTableWidgetItem(f"${debit:,.2f}" if debit > 0 else "")
                debit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if debit > 0:
                    debit_item.setForeground(QColor("#e74c3c"))
                self.table.setItem(row, 2, debit_item)

                balance_item = QTableWidgetItem(f"${running_balance:,.2f}")
                balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                balance_item.setFont(QFont("Arial", 10, QFont.Bold))
                self.table.setItem(row, 3, balance_item)

                desc_item = QTableWidgetItem(tx.description or "")
                self.table.setItem(row, 4, desc_item)

                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)
                actions_layout.setSpacing(2)

                delete_btn = QPushButton("🗑️")
                delete_btn.setFixedSize(30, 30)
                delete_btn.setToolTip("Delete this transaction")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 16px;
                    }
                    QPushButton:hover {
                        background-color: #c0392b;
                    }
                """)
                delete_btn.clicked.connect(lambda checked, tid=tx.id: self.delete_transaction(tid))
                actions_layout.addWidget(delete_btn)

                self.table.setCellWidget(row, 5, actions_widget)

                total_credit += credit
                total_debit += debit

            self.credit_card.value_label.setText(f"${total_credit:,.2f}")
            self.debit_card.value_label.setText(f"${total_debit:,.2f}")
            self.balance_card.value_label.setText(f"${actual_current_balance:,.2f}")
            self.balance_card.setToolTip("Current balance of this bank account (includes all transactions after reset)")

            if not transactions:
                self.table.setRowCount(1)
                self.table.setRowHeight(0, 35)
                empty_item = QTableWidgetItem("No transactions found for the selected period.")
                empty_item.setTextAlignment(Qt.AlignCenter)
                self.table.setSpan(0, 0, 1, 6)
                self.table.setItem(0, 0, empty_item)

        except Exception as e:
            logger.error(f"Error loading transactions: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load transactions: {str(e)}")

    def delete_transaction(self, transaction_id: int):
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete this transaction?\n\n"
            "This action cannot be undone and may affect account balances.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        try:
            success = self.transaction_service.delete(transaction_id)
            if success:
                QMessageBox.information(self, "Success", "Transaction deleted successfully.")
                self.load_transactions()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete transaction.")
        except Exception as e:
            logger.error(f"Error deleting transaction {transaction_id}: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")