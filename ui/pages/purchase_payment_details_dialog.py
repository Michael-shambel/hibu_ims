#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont, QColor, QCursor
from services.base_service import get_session
from models.purchase import Purchase
from models.purchase_payment_term import PurchasePaymentTerm, PaymentStatusEnum
from models.purchase_payment_transaction import PurchasePaymentTransaction
from sqlalchemy.orm import joinedload
from ui.utils.worker import Worker
import logging

logger = logging.getLogger(__name__)


class PurchasePaymentDetailsDialog(QDialog):
    def __init__(self, parent, purchase_id: int, payment_term_id: int, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Purchase #{purchase_id} - Payment Details")
        self.setMinimumSize(800, 500)
        self.resize(900, 600)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.purchase_id = purchase_id
        self.payment_term_id = payment_term_id
        self.current_user = current_user
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Summary cards
        cards_container = QWidget()
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setSpacing(20)

        self.total_label = QLabel("Total: $0.00")
        self.paid_label = QLabel("Paid: $0.00")
        self.remaining_label = QLabel("Remaining: $0.00")
        self.status_label = QLabel("Status: --")

        for lbl in [self.total_label, self.paid_label, self.remaining_label, self.status_label]:
            lbl.setStyleSheet("background-color: #f0f0f0; padding: 8px; border-radius: 4px; font-weight: bold;")
            cards_layout.addWidget(lbl)

        cards_layout.addStretch()
        layout.addWidget(cards_container)

        # Loading indicator
        self.loading_label = QLabel("Loading payment details...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.hide()
        layout.addWidget(self.loading_label)

        # Table for payment transactions
        self.table = QTableWidget()
        headers = ["Payment Date", "Amount", "Bank Account", "Payment Method", "Notes"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 8px;
                font-weight: bold;
                border: none;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFont(QFont("Segoe UI", 11))
        self.table.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.table, 1)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(100, 35)
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def load_data(self):
        self.loading_label.show()
        self.table.hide()
        self.thread = QThread()
        self.worker = Worker(self._fetch_data)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_data(self):
        with get_session() as session:
            # Get payment term
            term = session.query(PurchasePaymentTerm).get(self.payment_term_id)
            if not term:
                return None, None, []

            # Get payment transactions
            payments = session.query(PurchasePaymentTransaction).options(
                joinedload(PurchasePaymentTransaction.bank_account)
            ).filter(
                PurchasePaymentTransaction.purchase_payments_term_id == term.id,
                PurchasePaymentTransaction.is_deleted == False
            ).order_by(PurchasePaymentTransaction.payment_date.desc()).all()

            return term, payments

    def _on_data_loaded(self, result):
        term, payments = result
        if not term:
            self.loading_label.setText("Payment term not found.")
            self.loading_label.show()
            return

        # Update summary
        total = term.total_amount
        paid = term.paid_amount
        remaining = total - paid
        status = term.payment_status.value.capitalize() if term.payment_status else "Unknown"

        self.total_label.setText(f"Total: ${total:,.2f}")
        self.paid_label.setText(f"Paid: ${paid:,.2f}")
        self.remaining_label.setText(f"Remaining: ${remaining:,.2f}")
        self.status_label.setText(f"Status: {status}")

        # Populate table
        self.table.setRowCount(len(payments))
        for row, p in enumerate(payments):
            # Date
            date_item = QTableWidgetItem(p.payment_date.strftime("%Y-%m-%d") if p.payment_date else "")
            self.table.setItem(row, 0, date_item)
            # Amount
            amount_item = QTableWidgetItem(f"${p.amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, amount_item)
            # Bank Account
            bank_str = ""
            if p.bank_account:
                bank_str = f"{p.bank_account.bank_name} - {p.bank_account.account_name}"
            bank_item = QTableWidgetItem(bank_str)
            self.table.setItem(row, 2, bank_item)
            # Payment Method
            method_item = QTableWidgetItem(p.payment_method.value.capitalize() if p.payment_method else "")
            self.table.setItem(row, 3, method_item)
            # Notes
            notes_item = QTableWidgetItem(p.notes or "")
            self.table.setItem(row, 4, notes_item)

        self.loading_label.hide()
        self.table.show()

    def _on_error(self, error):
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load payment details:\n{error}")
        self.loading_label.hide()