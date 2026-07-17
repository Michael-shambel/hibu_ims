#!/usr/bin/env python3
"""
Dialog to display transaction history for a specific batch.
"""
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from services.new_batch_transaction_service import NewBachTransactionService
from ui.components.ethiopian_date import EthiopianDateConverter

logger = logging.getLogger(__name__)

class BatchTransactionHistoryDialog(QDialog):
    def __init__(self, batch_id: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.batch_id = batch_id
        self.transaction_service = NewBachTransactionService()
        self.setWindowTitle(f"Batch Transaction History - Batch #{batch_id}")
        self.setMinimumSize(1100, 600)  # Slightly larger to accommodate bigger fonts
        self.init_ui()
        self.load_transactions()

        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Create table with accessibility enhancements
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Date", "Type", "Quantity", "Balance", "Customer", "Delivery Name", "Notes"
        ])

        # --- Larger, bold font for readability ---
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.table.setFont(font)

        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 14px;
                font-weight: bold;
            }
            QHeaderView::section {
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)

        # Set column widths
        self.table.setColumnWidth(0, 120)   # Date
        self.table.setColumnWidth(1, 120)   # Type
        self.table.setColumnWidth(2, 100)   # Quantity
        self.table.setColumnWidth(3, 120)   # Balance
        # Columns 4-6 stretch (Customer, Delivery Name, Notes)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Customer
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Delivery Name
        header.setSectionResizeMode(6, QHeaderView.Stretch)  # Notes

        # Set row height to comfortably display text
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.verticalHeader().setVisible(False)

        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.table)

        # Button layout with larger close button
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(45)
        close_btn_font = QFont("Segoe UI", 12, QFont.Bold)
        close_btn.setFont(close_btn_font)
        close_btn.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def load_transactions(self):
        transactions = self.transaction_service.get_by_batch(self.batch_id)
        if not transactions:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(transactions))

        for row, tx in enumerate(transactions):
            # Set row height explicitly
            self.table.setRowHeight(row, 50)

            # Date (Ethiopian)
            if tx['created_at']:
                greg_date = tx['created_at'].date()
                try:
                    eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_date)
                    date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year}"
                except Exception:
                    date_str = "Invalid date"
            else:
                date_str = ""
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, date_item)

            # Type
            type_item = QTableWidgetItem(tx['type'])
            type_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, type_item)

            # Quantity with sign for adjustments
            qty = tx['quantity']
            qty_display = str(qty)
            if tx['type'] and tx['type'].lower() == 'adjustment':
                if qty > 0:
                    qty_display = f"+{qty}"
                elif qty < 0:
                    qty_display = f"{qty}"  # already negative
            qty_item = QTableWidgetItem(qty_display)
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, qty_item)

            # Balance (right‑aligned)
            balance_item = QTableWidgetItem(f"{tx['running_balance']:,.0f}")
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, balance_item)

            # Customer
            customer_item = QTableWidgetItem(tx['customer_name'] or "")
            self.table.setItem(row, 4, customer_item)

            # Delivery Name
            delivery_item = QTableWidgetItem(tx['delivery_name'] or "")
            self.table.setItem(row, 5, delivery_item)

            # Notes
            notes_item = QTableWidgetItem(tx['notes'] or "")
            self.table.setItem(row, 6, notes_item)