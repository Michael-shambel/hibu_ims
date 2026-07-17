#!/usr/bin/env python3
import sys
from wsgiref import headers
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QWidget, QLabel, QMessageBox, QScrollArea, QTabWidget,
    QFrame, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect,QLineEdit, QApplication
)
from models.sale_payment_term import PaymentStatusEnum
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QCursor, QColor
from functools import partial
from datetime import date, timedelta, datetime
from ui.components.ethiopian_date import EthiopianDateConverter
from ui.pages.credit_payment_dialog import CreditPaymentDialog
from services.new_sale_service import NewSaleService
from services.expense_service import ExpenseService
from services.purchase_service import PurchaseService
from services.bank_account_service import BankAccountService
from services.new_product_service import NewProductService
from ui.utils.worker import Worker
from telegrambot.bot import notify_store_team_sync, is_bot_ready
from ui.pages.expense_overview_dialog import ExpenseOverviewDialog
from fidel import Transliterate
import re
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SalesDetailDialog(QDialog):
    def __init__(self, parent, title: str, summary: dict, current_user=None,
                 cash_expenses: float = 0.0, cash_transfers: float = 0.0,
                 cash_receipts: float = 0.0, cash_payments: float = 0.0,
                 opening_cash_balance: float = 0.0, date=None):   # 🆕 parameter
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        
        self.setWindowTitle(title)

        screen = QApplication.primaryScreen().availableGeometry()
        desired_height = min(int(screen.height() * 0.8), 800) 
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
        self.summary = summary
        self.all_details = self._group_sales_by_sale(summary['details'].copy())
        self.current_user = current_user
        self.selected_sale_ids = set()
        self.current_filter = "all"
        self.current_bank_filter = None   # Track which bank is selected (None = all banks)
        self.search_text = ""
        self.cash_expenses = cash_expenses
        self.cash_transfers = cash_transfers
        self.cash_receipts = cash_receipts
        self.cash_payments = cash_payments
        self.opening_cash_balance = opening_cash_balance
        self.bank_breakdown_widget = None
        self.date = date

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.populate_table()

    # ---------- Grouping / Data helpers ----------
    def _group_sales_by_sale(self, details: list) -> list:
        """
        Group payment records by sale_id.
        Returns a list of sales with aggregated payment info, including payment_status.
        """
        sales_dict = {}
        
        for record in details:
            sale_id = record['sale_id']
            
            if sale_id not in sales_dict:
                sales_dict[sale_id] = {
                    'sale_id': sale_id,
                    'customer_name': record['customer_name'],
                    'total_amount': record.get('full_total', record['total_amount']),
                    'labour_expense': record['labour_expense'],
                    'delivery_name': record.get('delivery_name', ''),
                    'delivery_place': record.get('delivery_place', ''),
                    'delivery_phone': record.get('delivery_phone', ''),
                    'delivery_plate': record.get('delivery_plate', ''),
                    'payments': [],
                    'has_cash_payment': False,
                    'has_bank_payment': False,
                    'has_credit_payment': False
                }
            
            payment_type = record['payment_type'].lower()
            is_cash = 'cash' in payment_type
            is_bank = not is_cash and 'credit' not in payment_type and 'partial' not in payment_type
            
            payment_info = {
                'payment_type': record['payment_type'],
                'payment_amount': record['payment_amount'],
                'is_cash': is_cash,
                'is_bank': is_bank
            }
            sales_dict[sale_id]['payments'].append(payment_info)
            
            if is_cash:
                sales_dict[sale_id]['has_cash_payment'] = True
            elif is_bank:
                sales_dict[sale_id]['has_bank_payment'] = True
            else:
                sales_dict[sale_id]['has_credit_payment'] = True
        
        # Compute paid amount (cash+bank only) and payment_status
        for sale_data in sales_dict.values():
            total = sale_data['total_amount']
            paid = sum(p['payment_amount'] for p in sale_data['payments'] if p['is_cash'] or p['is_bank'])
            unpaid = total - paid
            
            sale_data['paid_amount'] = paid
            sale_data['unpaid'] = unpaid
            
            # Determine payment_status based on unpaid balance
            has_cash = sale_data['has_cash_payment']
            has_bank = sale_data['has_bank_payment']
            
            if unpaid <= 0.01:   # fully paid
                if has_cash and has_bank:
                    payment_status = 'Mixed'
                elif has_cash:
                    payment_status = 'Cash'
                elif has_bank:
                    payment_status = 'Bank'
                else:
                    payment_status = 'Unknown'
            else:                # unpaid > 0
                if paid > 0:
                    payment_status = 'Partial'
                else:
                    payment_status = 'Credit'
            
            sale_data['payment_status'] = payment_status
        
        return list(sales_dict.values())

    # ---------- UI Setup ----------
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dce4ec;
                background-color: #f8f9fa;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                color: #2c3e50;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #3498db;
                color: white;
            }
        """)

        # ===== TAB 1: Sales Details =====
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(0, 0, 0, 0)

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f8f9fa;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(25)

        # ---------- Summary Cards ----------
        cards_container = QWidget()
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setSpacing(20)

        credit_sales = sum(sale['unpaid'] for sale in self.all_details)

        card_info = [
            ("Cash Sales", f"${self.summary['cash_total']:,.2f}", "#2ecc71", "cash"),
            ("Credit Sales", f"${credit_sales:,.2f}", "#e74c3c", "credit"),
            ("Bank Sales", f"${self.summary['bank_total']:,.2f}", "#f39c12", "bank"),
            ("Total Paid", f"${self.summary['cash_total'] + self.summary['bank_total']:,.2f}", "#27ae60", "paid"),
            ("Total Invoiced", f"${self.summary.get('total_invoiced_full', self.summary['total_sales_amount']):,.2f}", "#3498db", "all"),
        ]
        self.cards = {}
        for title, value, color, filter_type in card_info:
            card = self.create_summary_card(title, value, color, filter_type)
            cards_layout.addWidget(card)
            self.cards[title] = card

        content_layout.addWidget(cards_container)

        self.bank_breakdown_widget = QWidget()
        self.bank_breakdown_widget.setVisible(False)
        self.bank_breakdown_layout = QHBoxLayout(self.bank_breakdown_widget)
        self.bank_breakdown_layout.setContentsMargins(0, 10, 0, 10)
        self.bank_breakdown_layout.setSpacing(15)
        content_layout.addWidget(self.bank_breakdown_widget)

        # ---------- Search ----------
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by any field...")
        self.search_edit.setMinimumHeight(35)
        self.search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.search_edit.textChanged.connect(self.filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()
        content_layout.addLayout(search_layout)

        # ---------- Detailed Table ----------
        self.table = QTableWidget()
        headers = [
            "",
            "Customer Name",
            "Payment Status",
            "Total Amount",
            "Delivery Address",
            "Actions"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(5, 140)

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
                border-radius: 4px;
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
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)

        content_layout.addWidget(self.table, 1)

        tab1_layout.addWidget(content_widget)
        self.tab_widget.addTab(tab1, "  Sales Details  ")

        # ===== TAB 2: Cash Account Summary (updated) =====
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(30, 30, 30, 30)

        # Compute cash summary values
        cash_sales = self.summary.get('cash_total', 0.0)
        credit_labour = sum(
            sale['labour_expense'] for sale in self.all_details
            if sale['payment_status'] in ('Credit', 'Partial')
        )
        closing_balance = (self.opening_cash_balance + cash_sales + self.cash_receipts
                           - self.cash_expenses
                           - self.cash_transfers - self.cash_payments)

        title_lbl = QLabel("Cash Account Summary")
        title_lbl.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title_lbl.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        tab2_layout.addWidget(title_lbl)

        # Card data – now includes opening balance and closing balance
        card_data = [
            ("Opening Balance",   f"${self.opening_cash_balance:,.2f}", "#1abc9c"),
            ("Cash Sales",        f"${cash_sales:,.2f}",                "#2ecc71"),
            ("Credit Receipts",   f"${self.cash_receipts:,.2f}",        "#3498db"),
            ("Cash Expenses",     f"${self.cash_expenses:,.2f}",        "#e74c3c"),
            # ("Credit Labour",     f"${credit_labour:,.2f}",             "#f39c12"),
            ("Cash Transfers",    f"${self.cash_transfers:,.2f}",       "#9b59b6"),
            ("Purchase Payments", f"${self.cash_payments:,.2f}",        "#e67e22"),
            ("Remaining Cash",    f"${closing_balance:,.2f}",
             "#27ae60" if closing_balance >= 0 else "#e74c3c"),          # 🆕 now based on closing_balance
        ]

        # First row: indices 0‑3
        row1_widget = QWidget()
        row1_layout = QHBoxLayout(row1_widget)
        row1_layout.setSpacing(20)
        for i in range(4):
            title, value, color = card_data[i]
            card = self.create_cash_summary_card(title, value, color)
            row1_layout.addWidget(card)
        tab2_layout.addWidget(row1_widget)

        # Second row: indices 4‑7
        row2_widget = QWidget()
        row2_layout = QHBoxLayout(row2_widget)
        row2_layout.setSpacing(20)
        for i in range(4, 7):
            title, value, color = card_data[i]
            card = self.create_cash_summary_card(title, value, color)
            row2_layout.addWidget(card)
        tab2_layout.addWidget(row2_widget)

        tab2_layout.addStretch()

        self.tab_widget.addTab(tab2, "  Cash Account Summary  ")

        main_layout.addWidget(self.tab_widget, 1)

    # ---------- Card creation ----------
    def create_cash_summary_card(self, title, value, color_hex):
        """Non-clickable summary card for cash tab."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 2px solid #E0E0E0;
                min-width: 200px;
                max-width: 240px;
            }}
        """)
        card.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        card.setFixedHeight(120)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {color_hex}, stop:1 #2c3e50);
                color: #FFFFFF;
                font-weight: bold;
                padding: 12px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 12px;
            }}
        """)
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setWordWrap(True)

        value_label = QLabel(value)
        value_label.setStyleSheet("""
            QLabel {
                background-color: #FFFFFF;
                color: #2c3e50;
                padding: 20px 10px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        value_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(header)
        layout.addWidget(value_label)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        return card

    def create_summary_card(self, title, value, color_hex, filter_type):
        """Create a modern summary card with hover effect and click handler."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 2px solid #E0E0E0;
                min-width: 200px;
                max-width: 240px;
            }}
            QFrame:hover {{
                border: 2px solid {color_hex};
                background-color: #f8f9fa;
            }}
        """)
        card.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        card.setFixedHeight(120)
        card.setCursor(Qt.PointingHandCursor)

        # Store filter type and color for later use
        card.filter_type = filter_type
        card.color_hex = color_hex

        # Click event
        card.mousePressEvent = lambda event: self.on_card_clicked(event, card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {color_hex}, stop:1 #2c3e50);
                color: #FFFFFF;
                font-weight: bold;
                padding: 12px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 12px;
            }}
        """)
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setWordWrap(True)

        value_label = QLabel(value)
        value_label.setObjectName("value_label")
        value_label.setStyleSheet("""
            QLabel {
                background-color: #FFFFFF;
                color: #2c3e50;
                padding: 20px 10px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        value_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(header)
        layout.addWidget(value_label)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        return card

    # ---------- Card click & filtering ----------
    def on_card_clicked(self, event, card):
        """Handle card click to filter table."""
        if event.button() == Qt.LeftButton:
            # If the Bank Sales card is clicked, always reset to all banks
            if card.filter_type == "bank":
                self.current_bank_filter = None
            self.apply_filter(card.filter_type)
            self.highlight_active_card(card)

    def highlight_active_card(self, active_card):
        """Change border of active card to indicate selection."""
        for title, card in self.cards.items():
            if card == active_card:
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: #FFFFFF;
                        border-radius: 8px;
                        border: 3px solid {card.color_hex};
                        min-width: 200px;
                        max-width: 240px;
                    }}
                """)
            else:
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: #FFFFFF;
                        border-radius: 8px;
                        border: 2px solid #E0E0E0;
                        min-width: 200px;
                        max-width: 240px;
                    }}
                """)

    def apply_filter(self, filter_type):
        self.current_filter = filter_type

        # Clear the bank-specific filter when not in bank mode
        if filter_type != "bank":
            self.current_bank_filter = None

        if filter_type == "all":
            filtered = self.all_details
        elif filter_type == "paid":
            filtered = [d for d in self.all_details if d.get('has_cash_payment', False) or d.get('has_bank_payment', False)]
        elif filter_type == "cash":
            filtered = [d for d in self.all_details if d.get('has_cash_payment', False)]
        elif filter_type == "bank":
            if self.current_bank_filter:
                # Show only sales that contain a payment matching the selected bank
                filtered = []
                for d in self.all_details:
                    if d.get('has_bank_payment', False):
                        if any(p['payment_type'] == self.current_bank_filter and p['is_bank'] for p in d.get('payments', [])):
                            filtered.append(d)
            else:
                # No specific bank selected – all bank sales
                filtered = [d for d in self.all_details if d.get('has_bank_payment', False)]
        elif filter_type == "credit":
            filtered = [d for d in self.all_details if d.get('unpaid', 0) > 0.01]
        else:
            filtered = self.all_details

        self.populate_table(filtered, self.current_filter)

        # Show/hide bank breakdown
        if filter_type == "bank":
            self._update_bank_breakdown()
        else:
            if self.bank_breakdown_widget:
                self.bank_breakdown_widget.setVisible(False)

    # ---------- Bank breakdown with clickable buttons ----------
    def _update_bank_breakdown(self):
        """Show bank breakdown widget with clickable bank buttons."""
        if not self.bank_breakdown_widget:
            return
        breakdown = self._compute_bank_breakdown()
        if not breakdown:
            self.bank_breakdown_widget.setVisible(False)
            return

        # Clear existing labels/buttons
        for i in reversed(range(self.bank_breakdown_layout.count())):
            widget = self.bank_breakdown_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Add an "All Banks" reset button if a specific bank is currently selected
        if self.current_bank_filter is not None:
            reset_btn = QPushButton("All Banks")
            reset_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            reset_btn.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: white;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: none;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #7f8c8d; }
            """)
            reset_btn.setCursor(Qt.PointingHandCursor)
            reset_btn.clicked.connect(self._on_bank_filter_reset)
            self.bank_breakdown_layout.addWidget(reset_btn)

        # Create a clickable button for each bank account
        for bank_name, total in breakdown.items():
            btn = QPushButton(f"{bank_name}: ${total:,.2f}")
            btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)

            # Highlight the currently selected bank
            if self.current_bank_filter == bank_name:
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

            # Connect click event (default argument to capture current bank_name)
            btn.clicked.connect(lambda checked, bn=bank_name: self._on_bank_button_clicked(bn))
            self.bank_breakdown_layout.addWidget(btn)

        self.bank_breakdown_widget.setVisible(True)

    def _on_bank_button_clicked(self, bank_name):
        """Filter table to show only sales that include a payment from this bank."""
        self.current_bank_filter = bank_name
        self.apply_filter("bank")   # reapply bank filter with specific bank active

    def _on_bank_filter_reset(self):
        """Clear bank filter and show all bank sales."""
        self.current_bank_filter = None
        self.apply_filter("bank")

    def _compute_bank_breakdown(self) -> dict:
        """Return dict mapping bank account display name -> total amount for bank payments."""
        from collections import defaultdict
        breakdown = defaultdict(float)
        for detail in self.summary.get('details', []):
            payment_type = detail.get('payment_type', '')
            amount = detail.get('payment_amount', 0.0)
            if payment_type != "Cash" and "Credit" not in payment_type and "Partial" not in payment_type:
                breakdown[payment_type] += amount
        return dict(breakdown)

    # ---------- Table population ----------
    def populate_table(self, details=None, filter_type="all"):
        """Populate table with given details, using filter_type to compute displayed totals."""
        if details is None:
            details = self.all_details
            filter_type = "all"

        self.table.setRowCount(len(details))
        self.expanded_rows = set()

        for row, sale in enumerate(details):
            # Expand/Collapse button
            expand_btn = QPushButton("▶")
            expand_btn.setFixedSize(40, 40)
            expand_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            expand_btn.clicked.connect(lambda checked, r=row: self.toggle_row_expansion(r))
            self.table.setCellWidget(row, 0, expand_btn)

            # Customer Name
            cust_item = QTableWidgetItem(sale.get('customer_name', ''))
            cust_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 1, cust_item)

            # Payment Status
            status = sale.get('payment_status', 'Unknown')
            status_item = QTableWidgetItem(status)
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            if status == 'Cash':
                status_item.setForeground(QColor("#27ae60"))
            elif status == 'Bank':
                status_item.setForeground(QColor("#f39c12"))
            elif status == 'Mixed':
                status_item.setForeground(QColor("#9b59b6"))
            elif status in ['Credit', 'Partial']:
                status_item.setForeground(QColor("#e74c3c"))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, status_item)

            # Total Amount (filtered)
            filtered_total = self._get_filtered_total(sale, filter_type)
            amount_item = QTableWidgetItem(f"${filtered_total:,.2f}")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, amount_item)

            # Delivery Address
            parts = []
            if sale.get('delivery_name'):
                parts.append(sale['delivery_name'])
            if sale.get('delivery_phone'):
                parts.append(sale['delivery_phone'])
            if sale.get('delivery_place'):
                parts.append(sale['delivery_place'])
            if sale.get('delivery_plate'):
                parts.append(sale['delivery_plate'])
            delivery_str = ' - '.join(parts) if parts else ''
            delivery_item = QTableWidgetItem(delivery_str)
            delivery_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 4, delivery_item)

            # Actions
            actions_widget = self.create_action_buttons(sale)
            self.table.setCellWidget(row, 5, actions_widget)

            # Store payments for expansion
            self.table.setProperty(f"row_{row}_payments", sale.get('payments', []))

        if hasattr(self, 'search_edit'):
            self.filter_table(self.search_edit.text())

    def _get_filtered_total(self, sale, filter_type):
        total_amount = sale.get('total_amount', 0)
        if filter_type == "all":
            return total_amount
        elif filter_type == "paid":
            return sum(p['payment_amount'] for p in sale.get('payments', []) if p['is_cash'] or p['is_bank'])
        elif filter_type == "cash":
            return sum(p['payment_amount'] for p in sale.get('payments', []) if p['is_cash'])
        elif filter_type == "bank":
            if self.current_bank_filter:
                # Show only the amount from the specific bank selected
                return sum(p['payment_amount'] for p in sale.get('payments', []) 
                        if p['is_bank'] and p['payment_type'] == self.current_bank_filter)
            else:
                # All banks: sum all bank payments
                return sum(p['payment_amount'] for p in sale.get('payments', []) if p['is_bank'])
        elif filter_type == "credit":
            return sale.get('unpaid', total_amount)
        else:
            return total_amount

    # ---------- Expand/Collapse ----------
    def toggle_row_expansion(self, row):
        """Expand or collapse a row to show payment details."""
        if hasattr(self, 'expanded_rows') and row in self.expanded_rows:
            self.collapse_row(row)
            self.expanded_rows.remove(row)
            btn = self.table.cellWidget(row, 0)
            if btn:
                btn.setText("▶")
        else:
            self.expand_row(row)
            self.expanded_rows.add(row)
            btn = self.table.cellWidget(row, 0)
            if btn:
                btn.setText("▼")

    def expand_row(self, parent_row):
        payments = self.table.property(f"row_{parent_row}_payments")
        if not payments:
            return
        
        for i, payment in enumerate(payments):
            insert_pos = parent_row + i + 1 + len([r for r in self.expanded_rows if r < parent_row])
            self.table.insertRow(insert_pos)
            
            if payment['is_cash']:
                icon = "💰"
            elif payment['is_bank']:
                icon = "🏦"
            else:
                icon = "📝"
            
            icon_item = QTableWidgetItem(icon)
            icon_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            icon_item.setForeground(QColor("#7f8c8d"))
            icon_item.setFlags(icon_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(insert_pos, 0, icon_item)
            
            type_item = QTableWidgetItem(payment['payment_type'])
            type_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            type_item.setForeground(QColor("#7f8c8d"))
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(insert_pos, 2, type_item)
            
            amount_item = QTableWidgetItem(f"${payment['payment_amount']:,.2f}")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amount_item.setForeground(QColor("#7f8c8d"))
            self.table.setItem(insert_pos, 3, amount_item)
            
            for col in range(self.table.columnCount()):
                item = self.table.item(insert_pos, col)
                if item:
                    item.setBackground(QColor("#f8f9fa"))
        
        self.table.resizeRowsToContents()

    def collapse_row(self, parent_row):
        rows_to_remove = []
        current_row = parent_row + 1
        
        while current_row < self.table.rowCount():
            if self.table.cellWidget(current_row, 0) is None and self.table.item(current_row, 0) is not None:
                rows_to_remove.append(current_row)
                current_row += 1
            else:
                break
        
        for r in reversed(rows_to_remove):
            self.table.removeRow(r)

    # ---------- Search ----------
    def filter_table(self, text):
        self.search_text = text
        search_lower = text.lower()

        for row in range(self.table.rowCount()):
            if not search_lower:
                self.table.setRowHidden(row, False)
                continue

            match = False
            for col in range(1, 5):
                item = self.table.item(row, col)
                if item and search_lower in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    # ---------- Action buttons & operations ----------
    def create_action_buttons(self, sale):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(8)

        view_btn = QPushButton("👁️")
        view_btn.setFixedSize(40, 40)
        view_btn.setToolTip("View Sale Details")
        view_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        view_btn.clicked.connect(lambda: self.view_sale(sale.get('sale_id')))

        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(40, 40)
        delete_btn.setToolTip("Delete Sale")
        if not self.is_user_admin():
            delete_btn.setEnabled(False)
            delete_btn.setStyleSheet("background-color: #bdc3c7; color: white; border: none; border-radius: 6px; font-size: 18px;")
        else:
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #c0392b; }
            """)
            delete_btn.clicked.connect(lambda: self.delete_sale(sale.get('sale_id')))

        layout.addWidget(view_btn)
        layout.addWidget(delete_btn)
        return widget

    def view_sale(self, sale_id):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        sale = service.get_sale_with_items(sale_id)
        if not sale:
            QMessageBox.warning(self, "Not Found", f"Sale #{sale_id} not found.")
            return
        if not sale.items:
            QMessageBox.information(self, "No Items", "This sale has no items.")
            return
        dialog = SaleItemsDialog(self, f"Sale #{sale.id} Items", sale, self.current_user)
        dialog.exec()

    def delete_sale(self, sale_id):
        if not self.is_user_admin():
            QMessageBox.warning(self, "Permission Denied", "Only admin can delete sales.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete sale #{sale_id}?\n\nThis will permanently remove all related records and restore inventory.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            from services.new_sale_service import NewSaleService
            service = NewSaleService()
            user_id = None
            if self.current_user:
                if isinstance(self.current_user, dict):
                    user_id = self.current_user.get('id')
                else:
                    user_id = getattr(self.current_user, 'id', None)
            if service.delete_sale_cascade(sale_id, user_id):
                QMessageBox.information(self, "Deleted", f"Sale #{sale_id} and all related records deleted.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Delete failed.")

    def is_user_admin(self):
        if not self.current_user:
            return False
        if isinstance(self.current_user, dict):
            return self.current_user.get('is_admin') or self.current_user.get('role') == 'admin'
        return getattr(self.current_user, 'is_admin', False)

    def refresh_data(self):
        """Re-fetch data for the same date and update UI."""
        if self.date is None:
            logger.warning("Cannot refresh SalesDetailDialog: no date set")
            return

        service = NewSaleService()
        new_summary = service.get_daily_sales_summary(self.date)
        if new_summary is None:
            QMessageBox.warning(self, "Refresh Failed", "Could not fetch updated data.")
            return

        # Update the stored summary and re-group details
        self.summary = new_summary
        self.all_details = self._group_sales_by_sale(new_summary['details'].copy())

        # Update summary card values
        credit_sales = sum(sale['unpaid'] for sale in self.all_details)
        card_values = {
            "Cash Sales":   f"${new_summary['cash_total']:,.2f}",
            "Credit Sales": f"${credit_sales:,.2f}",
            "Bank Sales":   f"${new_summary['bank_total']:,.2f}",
            "Total Paid":   f"${new_summary['cash_total'] + new_summary['bank_total']:,.2f}",
            "Total Invoiced": f"${new_summary.get('total_invoiced_full', new_summary['total_sales_amount']):,.2f}"
        }
        for title, card in self.cards.items():
            if title in card_values:
                value_label = card.findChild(QLabel, "value_label")
                if value_label:
                    value_label.setText(card_values[title])

        # Re-apply the current filter (this also repopulates the table)
        self.apply_filter(self.current_filter)


class LabourExpenseDialog(QDialog):
    """Dialog for labour expense details with card filtering."""
    def __init__(self, parent, title, data, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        screen = QApplication.primaryScreen().availableGeometry()
        desired_height = min(int(screen.height() * 0.8), 700)
        desired_height = max(desired_height, 500)
        self.setMinimumSize(900, 500)
        self.resize(1200, desired_height)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.sale_service = NewSaleService()
        self.raw_data = []          # all fetched data
        self.filtered_data = []    # data currently displayed
        self.current_filter = "all"  # "all" or "credit"
        self.cards = {}            # to highlight active card

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== CONTENT ====================
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f8f9fa;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(25)

        # Summary cards container (will be populated after data loads)
        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(20)
        content_layout.addWidget(self.cards_container)

        # Table label
        table_label = QLabel("Labour Expense Transactions")
        table_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        table_label.setStyleSheet("color: #2c3e50; margin-top: 10px;")
        content_layout.addWidget(table_label)

        # Table
        self.table = QTableWidget()
        headers = [
            "Customer Name", "Total Amount", "Labour Expense",
            "Delivery Name", "Bank Accounts"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setStretchLastSection(False)

        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(4, 150)

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
                border-radius: 4px;
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
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        content_layout.addWidget(self.table, 1)

        # Loading indicator
        self.loading_label = QLabel("Loading labour expense data...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        content_layout.addWidget(self.loading_label)

        # ==================== END CONTENT ====================
        main_layout.addWidget(content_widget, 1)

    def create_summary_card(self, title, value, color_hex, filter_type):
        """Create a clickable summary card that filters the table."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 2px solid #E0E0E0;
                min-width: 200px;
                max-width: 240px;
            }}
            QFrame:hover {{
                border: 2px solid {color_hex};
                background-color: #f8f9fa;
            }}
        """)
        card.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        card.setFixedHeight(130)
        card.setCursor(Qt.PointingHandCursor)
        card.filter_type = filter_type
        card.color_hex = color_hex

        # Click event
        card.mousePressEvent = lambda event: self.on_card_clicked(event, card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {color_hex}, stop:1 #2c3e50);
                color: #FFFFFF;
                font-weight: bold;
                padding: 14px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 14px;
            }}
        """)
        header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setWordWrap(True)

        value_label = QLabel(value)
        value_label.setStyleSheet("""
            QLabel {
                background-color: #FFFFFF;
                color: #2c3e50;
                padding: 20px 10px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        value_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(header)
        layout.addWidget(value_label)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        return card

    def on_card_clicked(self, event, card):
        """Handle card click to filter table."""
        if event.button() == Qt.LeftButton:
            self.apply_filter(card.filter_type)
            self.highlight_active_card(card)

    def apply_filter(self, filter_type):
        """Filter the data and repopulate the table."""
        self.current_filter = filter_type
        if filter_type == "all":
            self.filtered_data = self.raw_data.copy()
        elif filter_type == "credit":
            self.filtered_data = [d for d in self.raw_data if d.get('is_credit_sale', False)]
        else:
            self.filtered_data = self.raw_data.copy()
        self.populate_table()

    def highlight_active_card(self, active_card):
        """Change border of active card to indicate selection."""
        for card in self.cards.values():
            if card == active_card:
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: #FFFFFF;
                        border-radius: 8px;
                        border: 3px solid {card.color_hex};
                        min-width: 200px;
                        max-width: 240px;
                    }}
                """)
            else:
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: #FFFFFF;
                        border-radius: 8px;
                        border: 2px solid #E0E0E0;
                        min-width: 200px;
                        max-width: 240px;
                    }}
                """)

    def load_data(self):
        self.loading_label.show()
        self.table.hide()
        self.cards_container.hide()
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
        """Fetch labour expense data for today in background."""
        return self.sale_service.get_sales_with_labour_expense(date.today())

    def _on_data_loaded(self, data):
        self.raw_data = data
        self.filtered_data = data.copy()
        self.populate_cards()
        self.populate_table()
        self.loading_label.hide()
        self.cards_container.show()
        self.table.show()

    def _on_error(self, error):
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load labour expense data:\n{error}")
        self.loading_label.hide()
        self.cards_container.show()
        self.table.show()

    def populate_cards(self):
        """Create summary cards and store references for highlighting."""
        total_labour = sum(item['labour_expense'] for item in self.raw_data)
        credit_labour = sum(
            item['labour_expense'] for item in self.raw_data
            if item.get('is_credit_sale', False) and item.get('unpaid', 0) > 0.01
        )
        # Clear existing cards
        for i in reversed(range(self.cards_layout.count())):
            widget = self.cards_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.cards.clear()

        card_info = [
            ("Total Labour Expense", f"${total_labour:,.2f}", "#e74c3c", "all"),
            ("Credit Labour Expense", f"${credit_labour:,.2f}", "#9b59b6", "credit"),
        ]

        for title, value, color, filter_type in card_info:
            card = self.create_summary_card(title, value, color, filter_type)
            self.cards_layout.addWidget(card)
            self.cards[filter_type] = card   # store reference for highlighting

        # Highlight the currently active filter
        active_card = self.cards.get(self.current_filter)
        if active_card:
            self.highlight_active_card(active_card)

    def populate_table(self):
        """Populate table with filtered data."""
        data = self.filtered_data if hasattr(self, 'filtered_data') else self.raw_data
        self.table.setRowCount(len(data))
        for row, sale in enumerate(data):
            # Customer Name
            name_item = QTableWidgetItem(sale.get('customer_name', ''))
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, name_item)

            # Total Amount
            total_item = QTableWidgetItem(f"${sale.get('total_amount', 0):,.2f}")
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, total_item)

            # Labour Expense
            labour_item = QTableWidgetItem(f"${sale.get('labour_expense', 0):,.2f}")
            labour_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            labour_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, labour_item)

            # Delivery Name
            deliv_name = QTableWidgetItem(sale.get('delivery_name', ''))
            deliv_name.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 3, deliv_name)

            # Bank Accounts
            banks = sale.get('bank_accounts', [])
            bank_str = ', '.join(banks) if banks else ''
            bank_item = QTableWidgetItem(bank_str)
            bank_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 4, bank_item)

class SaleItemsDialog(QDialog):
    """Display items of a sale – works with both relationship items and JSON items_data."""
    def __init__(self, parent, title, sale, current_user=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        screen = QApplication.primaryScreen().availableGeometry()
        desired_height = min(int(screen.height() * 0.6), 600)   # 60% of screen, max 600
        desired_height = max(desired_height, 400)
        self.setMinimumSize(600, 400)
        self.resize(800, desired_height)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.sale = sale
        self.current_user = current_user
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        headers = ["Product", "Quantity", "Dozen", "Unit Price", "Total", "Despatched"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        # header.setSectionResizeMode(0, QHeaderView.Stretch)

        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        # === ELDERLY‑FRIENDLY: large bold font, tall rows ===
        self.table.setColumnWidth(0, 250)
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
                border-radius: 4px;
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
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.populate_table()
        layout.addWidget(self.table)

        # --- Close button (larger, bold) ---
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)   # bigger
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        btn_close.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(btn_close)
        layout.addLayout(button_layout)

    def populate_table(self):
        items = []
        if hasattr(self.sale, 'items') and self.sale.items:
            items = self.sale.items
        elif hasattr(self.sale, 'items_data') and self.sale.items_data:
            items = self.sale.items_data

        # Aggregate items by product name
        aggregated = {}
        for item in items:
            if isinstance(item, dict):
                product_name = item.get('product_name', '')
                quantity = item.get('quantity', 0)
                dozen = item.get('dozen', 1)
                unit_price = item.get('unit_price', 0.0)
                total = item.get('total', 0.0)
                for_despatch = item.get('for_despatch', False)
            else:
                product_name = item.batch.product.name if item.batch and item.batch.product else "N/A"
                quantity = item.quantity
                dozen = item.dozen
                unit_price = item.unit_price
                total = item.total
                for_despatch = item.for_despatch

            if product_name not in aggregated:
                aggregated[product_name] = {
                    'product_name': product_name,
                    'quantity': 0,
                    'dozen': dozen,
                    'unit_price': unit_price,
                    'total': 0.0,
                    'for_despatch': for_despatch,
                }
            aggregated[product_name]['quantity'] += quantity
            aggregated[product_name]['total'] += total

        # Convert to sorted list
        aggregated_list = sorted(aggregated.values(), key=lambda x: x['product_name'])

        self.table.setRowCount(len(aggregated_list))
        total_sum = 0.0

        for row, item in enumerate(aggregated_list):
            # Product name
            name_item = QTableWidgetItem(item['product_name'])
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, name_item)

            # Quantity
            qty_item = QTableWidgetItem(str(item['quantity']))
            qty_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, qty_item)

            # Dozen
            dozen_item = QTableWidgetItem(str(item['dozen']))
            dozen_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            dozen_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, dozen_item)

            # Unit Price
            price_item = QTableWidgetItem(f"${item['unit_price']:,.2f}")
            price_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, price_item)

            # Total
            total_item = QTableWidgetItem(f"${item['total']:,.2f}")
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, total_item)

            # Despatched status
            status = "Yes" if item['for_despatch'] else "No"
            status_item = QTableWidgetItem(status)
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            if item['for_despatch']:
                status_item.setForeground(QColor("#27ae60"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 5, status_item)

            total_sum += item['total']

        # Add total row
        total_row = len(aggregated_list)
        self.table.insertRow(total_row)

        total_label = QTableWidgetItem("TOTAL")
        total_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        total_label.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setItem(total_row, 0, total_label)

        # Span the TOTAL label across columns 0-3
        self.table.setSpan(total_row, 0, 1, 4)

        total_amount_item = QTableWidgetItem(f"${total_sum:,.2f}")
        total_amount_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
        total_amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(total_row, 4, total_amount_item)

        # Empty cell for despatched column in total row
        total_despatch = QTableWidgetItem("")
        self.table.setItem(total_row, 5, total_despatch)

        # Resize rows to fit content
        self.table.resizeRowsToContents()

class DespatchSalesDialog(QDialog):
    AMHARIC_OVERRIDES = {}

    def __init__(self, parent, title, sales, current_user, is_despatched):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
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
        self.all_sales = sales                # unfiltered list
        self.filtered_sales = sales            # currently displayed list
        self.current_user = current_user
        self.is_despatched = is_despatched
        self.extra_despatch_note = ""
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.populate_table()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f8f9fa;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(15)

        # ---------- Search Bar ----------
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 10)

        search_label = QLabel("Search:")
        search_label.setStyleSheet("font-weight: bold;")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by any field (customer, phone, date, amount...)")
        self.search_edit.textChanged.connect(self.filter_table)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()

        content_layout.addLayout(search_layout)

        # Table
        self.table = QTableWidget()
        self.setup_table_headers()
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
                border-radius: 4px;
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

        content_layout.addWidget(self.table, 1)


        main_layout.addWidget(content_widget, 1)

    def setup_table_headers(self):
        """Common headers for both views."""
        headers = [
            "Sale Date (Ethiopian)",
            "Customer",
            "Delivery Address",
            "Total Amount",
            "Items",
            "Actions"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.Stretch)           # Customer
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # Delivery Address
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Amount
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Items
        header.setSectionResizeMode(5, QHeaderView.Fixed)             # Actions
        self.table.setColumnWidth(5, 100)

    def populate_table(self):
        """Fill table with filtered sales data."""
        self.table.setRowCount(len(self.filtered_sales))
        for row, sale in enumerate(self.filtered_sales):
            # Ethiopian date
            date_str = self._to_ethiopian_date_str(sale.created_at) if sale.created_at else ""
            self.table.setItem(row, 0, QTableWidgetItem(date_str))

            # Customer
            customer = sale.customer.name if sale.customer else "N/A"
            self.table.setItem(row, 1, QTableWidgetItem(customer))

            # Delivery Address (merged)
            parts = []
            if sale.delivery_name:
                parts.append(sale.delivery_name)
            if sale.delivery_phone:
                parts.append(sale.delivery_phone)
            if sale.delivery_place:
                parts.append(sale.delivery_place)
            if sale.delivery_Plate:
                parts.append(sale.delivery_Plate)
            delivery_str = ' - '.join(parts) if parts else ''
            self.table.setItem(row, 2, QTableWidgetItem(delivery_str))

            # Total amount
            total_item = QTableWidgetItem(f"${sale.total_amount:,.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, total_item)

            # Items count
            count = len(sale.items) if sale.items else 0
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, count_item)

            # Action button
            btn_text = "👁️ View" if self.is_despatched else "👁️ View & Mark"
            btn = QPushButton(btn_text)
            btn.setFixedSize(100, 36)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            btn.clicked.connect(lambda checked, s=sale: self.handle_view(s))
            self.table.setCellWidget(row, 5, btn)

        if hasattr(self, 'search_edit'):
            self.filter_table(self.search_edit.text())

    def _to_ethiopian_date_str(self, dt: datetime) -> str:
        if not dt:
            return ""
        try:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(dt.date())
            return f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        except Exception:
            return dt.strftime("%Y-%m-%d")  # fallback

    def filter_table(self, text):
        """Hide rows that do not contain the search text in any visible column (0‑7)."""
        search_lower = text.lower()

        for row in range(self.table.rowCount()):
            if not search_lower:
                self.table.setRowHidden(row, False)
                continue

            match = False
            for col in range(5):   # column 8 is Actions, we skip it
                item = self.table.item(row, col)
                if item and search_lower in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

        # Update status label
        visible = self.table.rowCount() - sum(1 for r in range(self.table.rowCount()) if self.table.isRowHidden(r))
        # self.status_label.setText(f"Showing {visible} of {self.table.rowCount()} sales")

    def handle_view(self, sale):
        """Open appropriate dialog based on despatch status."""
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        full_sale = service.get_sale_with_items(sale.id)
        if not full_sale or full_sale.is_deleted: 
            QMessageBox.warning(self, "Error", "Could not load sale details.")
            return

        if self.is_despatched:
            # View‑only items
            from ui.pages.sales_card_dialog import SaleItemsDialog
            dialog = SaleItemsDialog(self, f"Sale #{sale.id} Items", full_sale, self.current_user)
            dialog.exec()
        else:
            # Items dialog with mark despatched capability
            self.open_items_with_mark(full_sale)

    def open_items_with_mark(self, sale):
        """Custom dialog that shows sale items with a 'Mark Despatched' button per item."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sale #{sale.id} Items - Mark Despatched")
        dialog.setMinimumSize(1000, 500)

        layout = QVBoxLayout(dialog)

        # Extra note + Mark All controls
        controls_layout = QHBoxLayout()
        note_label = QLabel("Additional note:")
        note_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        note_edit = QLineEdit()
        note_edit.setPlaceholderText("Optional message to include in despatch notification...")
        note_edit.setMinimumHeight(32)
        note_edit.setStyleSheet("font-size:13px;")
        mark_all_btn = QPushButton("✔️ Mark All")
        mark_all_btn.setFixedSize(120, 36)
        mark_all_btn.setCursor(Qt.PointingHandCursor)
        mark_all_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; border-radius: 4px;")

        controls_layout.addWidget(note_label)
        controls_layout.addWidget(note_edit)
        controls_layout.addWidget(mark_all_btn)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Table
        table = QTableWidget()
        headers = ["Product", "Quantity", "Dozen", "Unit Price", "Total", "Status", "Action"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        table.setColumnWidth(6, 100)

        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
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
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setFont(QFont("Segoe UI", 11))
        table.verticalHeader().setDefaultSectionSize(40)

        # Populate
        items = sale.items
        table.setRowCount(len(items))
        from services.new_sale_item_service import NewSaleItemService
        item_service = NewSaleItemService()

        for row, item in enumerate(items):
            # Product
            product_name = item.batch.product.name if item.batch and item.batch.product else "N/A"
            table.setItem(row, 0, QTableWidgetItem(product_name))
            # Quantity
            table.setItem(row, 1, QTableWidgetItem(str(item.quantity)))
            # Dozen
            table.setItem(row, 2, QTableWidgetItem(str(item.dozen)))
            # Unit price
            price_item = QTableWidgetItem(f"${item.unit_price:,.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 3, price_item)
            # Total
            total_item = QTableWidgetItem(f"${item.total:,.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 4, total_item)
            # Status
            status = "Despatched" if item.for_despatch else "Pending"
            status_item = QTableWidgetItem(status)
            if item.for_despatch:
                status_item.setForeground(QColor("#27ae60"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            table.setItem(row, 5, status_item)

            # Action button (only if not despatched)
            if not item.for_despatch:
                btn = QPushButton("✅ Mark")
                btn.setFixedSize(80, 30)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #27ae60;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 11px;
                    }
                    QPushButton:hover { background-color: #229954; }
                """)
                # Closure to capture row/item and read note field
                def make_on_mark(iid=item.id, r=row, s=sale):
                    def on_mark():
                        self.extra_despatch_note = note_edit.text() or ""
                        self.mark_item_and_refresh(iid, table, r, s)
                    return on_mark

                btn.clicked.connect(make_on_mark())
                table.setCellWidget(row, 6, btn)
            else:
                # Placeholder (no button)
                placeholder = QLabel("  ")
                table.setCellWidget(row, 6, placeholder)

        layout.addWidget(table)

        # Connect Mark All button
        def on_mark_all():
            extra_text = note_edit.text().strip()
            self.extra_despatch_note = extra_text

            # --- NEW: Update the sale's delivery_name in the database ---
            if extra_text:
                from services.new_sale_service import NewSaleService
                sale_service = NewSaleService()
                
                # Get current delivery name (or empty string)
                current_delivery = sale.delivery_name or ""
                # Append the note (in parentheses)
                new_delivery = f"{current_delivery} ({extra_text})"
                
                # Update the database
                sale_service.update(sale.id, {'delivery_name': new_delivery})
                
                # Update the local sale object so the notification uses the combined address
                sale.delivery_name = new_delivery
            # ----------------------------------------------------------

            # Now mark all items as despatched
            for r, it in enumerate(items):
                if not it.for_despatch:
                    self.mark_item_and_refresh(it.id, table, r, sale, show_message=False)
            
            QMessageBox.information(dialog, "Marked", "All items marked as despatched (where applicable).")

        mark_all_btn.clicked.connect(on_mark_all)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(100, 35)
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        dialog.exec()

    def mark_item_and_refresh(self, item_id, table, row, sale=None, show_message=True):
        """Mark item as despatched and refresh the row in the dialog."""
        from services.new_sale_item_service import NewSaleItemService
        service = NewSaleItemService()
        if service.mark_item_despatched(item_id):
            # Update the row to show despatched status and remove button
            table.item(row, 5).setText("Despatched")
            table.item(row, 5).setForeground(QColor("#27ae60"))
            table.removeCellWidget(row, 6)  # Remove button
            placeholder = QLabel("  ")
            table.setCellWidget(row, 6, placeholder)
            if show_message:
                QMessageBox.information(table, "Success", "Item marked as despatched.")

            # Check if ALL items are now despatched → send notification
            if sale:
                all_despatched = True
                for r in range(table.rowCount()):
                    status_item = table.item(r, 5)
                    if status_item and status_item.text() != "Despatched":
                        all_despatched = False
                        break
                if all_despatched:
                    self._send_despatch_notification(sale, getattr(self, 'extra_despatch_note', None))
        else:
            QMessageBox.critical(table, "Error", "Failed to mark item as despatched.")

    def _to_amharic(self, text: str) -> str:
        """Convert product name to Amharic. Never raises exceptions."""
        if not text:
            return text
        key = text.strip().upper()
        if key in self.AMHARIC_OVERRIDES:
            return self.AMHARIC_OVERRIDES[key]
        try:
            processed = text.lower().strip()
            cleaned = re.sub(r'\s+', ' ', processed)
            amharic = Transliterate(cleaned).transliterate()
            return amharic if amharic else text
        except Exception:
            return text

    def _send_despatch_notification(self, sale, extra_text: str = None):
        """Send a despatch confirmation message to the store team using the same Amharic format as new sales."""
        try:
            # if not is_bot_ready():
            #     logger.warning("Bot not ready, despatch notification skipped.")
            #     return

            # Ethiopian date & time
            now = datetime.now()
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(date.today())
            hour = now.hour
            minute = now.minute
            time_str = f"{hour:02d}:{minute:02d}"

            eth_month_names_am = [
                "መስከረም", "ጥቅምት", "ህዳር", "ታህሳስ", "ጥር", "የካቲት",
                "መጋቢት", "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ"
            ]
            month_name = eth_month_names_am[eth_month - 1] if 1 <= eth_month <= 13 else str(eth_month)
            eth_weekday_num = date.today().isoweekday()
            eth_weekdays = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሑድ"]
            eth_weekday = eth_weekdays[eth_weekday_num - 1]
            eth_date_str = f"{eth_weekday} {eth_day} {month_name} {eth_year}  {time_str}"

            # Aggregate sale items (non‑deleted)
            aggregated = {}
            for item in sale.items:
                if item.is_deleted:
                    continue
                name = item.batch.product.name if item.batch and item.batch.product else "Unknown"
                qty = item.quantity
                aggregated[name] = aggregated.get(name, 0) + qty

            product_lines = []
            num = 1
            for name, qty in aggregated.items():
                display_name = self._to_amharic(name)
                qty_display = int(qty) if qty.is_integer() else f"{qty:.1f}"
                product_lines.append(f"{num} = {display_name}\t({name}):\t\tብዛት፡\t{qty_display}")
                num += 1
            products_text = "\n\n".join(product_lines)

            # Delivery address (transliterated)
            delivery_name = sale.delivery_name or "N/A"
            delivery_address = self._to_amharic(delivery_name)

            # Build message – exactly like the new‑sale notification, but for despatch
            message = (
                f"🚚 <b> የሚወጣ ትእዛዝ!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🚨🚨🚨🚨አሁን የሚወጣ ትዕዛዝ 🚨🚨🚨🚨🚨\n"
                f"📅 <b>የኢትዮጵያ ቀን / ሰዓት</b>\n"
                f"   {eth_date_str}\n\n"
                f"📝 <b>Sale ID:</b> #{sale.id}\n\n"
                f"📦 <b>የተላኩ እቃዎች</b>\n"
                f"{products_text}"
                # f"\n\n📍 <b>አድራሻ</b>\n"
                # f"   {delivery_address} ({delivery_name})\n"
            )

            # Append extra note if provided
            if extra_text:
                extra_text = extra_text.strip()
                if extra_text:
                    message += f"\n\n<b>ተጨማሪ መረጃ:</b> {extra_text}\n"

            notify_store_team_sync(message, sale_id=sale.id, notification_type='despatch_notification')

        except Exception as e:
            logger.error(f"Failed to send despatch notification: {e}")

class CustomerSalesListDialog(QDialog):
    """Displays credit sales for a customer, grouped by date."""
    def __init__(self, parent, customer_name, sale_ids, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Credit Sales - {customer_name}")
        self.setMinimumSize(800, 400)
        self.resize(1000, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.customer_name = customer_name
        self.sale_ids = sale_ids
        self.current_user = current_user
        self.grouped_data = []          # list of dicts per date group
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()
        self.thread = None
        self.worker = None

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.table = QTableWidget()
        headers = ["Sale Date (Ethiopian)", "Total Amount", "Paid Amount", "Remaining", "Status", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in (1, 2, 3):
            # header.setSectionResizeMode(col, QHeaderView.Stretch)
            self.table.setColumnWidth(col, 140)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(4, 120)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 140)  # wider for larger button

        self.table.setAlternatingRowColors(True)

        # === ELDERLY-FRIENDLY: large bold font, tall rows ===
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
                border-radius: 4px;
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

        layout.addWidget(self.table, 1)

        # Close button - larger
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def _to_ethiopian_date_str(self, dt):
        if not dt:
            return ""
        try:
            from ui.components.ethiopian_date import EthiopianDateConverter
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(dt)
            return f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        except Exception:
            return dt.strftime("%Y-%m-%d")

    def load_data(self):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        sales = service.get_credit_sales_by_ids(self.sale_ids)

        # Group by sale_date (date part)
        date_groups = {}
        for sale in sales:
            date_key = sale['sale_date'].date() if sale['sale_date'] else None
            if date_key not in date_groups:
                date_groups[date_key] = {
                    'total_amount': 0.0,
                    'paid_amount': 0.0,
                    'remaining': 0.0,
                    'sale_ids': [],
                    'payment_term_ids': [],
                }
            date_groups[date_key]['total_amount'] += sale['total_amount']
            date_groups[date_key]['paid_amount'] += sale['paid_amount']
            date_groups[date_key]['remaining'] += sale['remaining']
            date_groups[date_key]['sale_ids'].append(sale['sale_id'])
            date_groups[date_key]['payment_term_ids'].append(sale['payment_term_id'])

        # Convert to list, sort by date (newest first)
        self.grouped_data = []
        for date_key, data in date_groups.items():
            if data['remaining'] <= 0:
                status = 'Paid'
            elif data['paid_amount'] > 0:
                status = 'Partial'
            else:
                status = 'Unpaid'

            self.grouped_data.append({
                'sale_date': date_key,
                'total_amount': data['total_amount'],
                'paid_amount': data['paid_amount'],
                'remaining': data['remaining'],
                'status': status,
                'sale_ids': data['sale_ids'],
                'payment_term_ids': data['payment_term_ids'],
            })

        # Sort: newest first
        self.grouped_data.sort(key=lambda x: x['sale_date'], reverse=True)
        self.grouped_data.sort(key=lambda x: x['sale_date'], reverse=True)

        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.grouped_data))
        for row, group in enumerate(self.grouped_data):
            # Date column
            date_str = self._to_ethiopian_date_str(group['sale_date']) if group['sale_date'] else "Unknown Date"
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            # Total Amount
            total_item = QTableWidgetItem(f"${group['total_amount']:,.2f}")
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, total_item)

            # Paid Amount
            paid_item = QTableWidgetItem(f"${group['paid_amount']:,.2f}")
            paid_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            paid_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, paid_item)

            # Remaining
            rem_item = QTableWidgetItem(f"${group['remaining']:,.2f}")
            rem_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            rem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, rem_item)

            # Status
            status_item = QTableWidgetItem(group['status'])
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            if group['status'] == 'Paid':
                status_item.setForeground(QColor("#27ae60"))
            elif group['status'] == 'Partial':
                status_item.setForeground(QColor("#f39c12"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 4, status_item)

            # View Items button - larger
            view_btn = QPushButton("View Items")
            view_btn.setFixedSize(110, 40)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            view_btn.clicked.connect(lambda checked, ids=group['sale_ids'], date_obj=group['sale_date']: self.view_items(ids, date_obj))
            self.table.setCellWidget(row, 5, view_btn)

    def view_items(self, sale_ids, date_obj):
        """Show all items from all sales in this group, with a total row."""
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        all_items = []
        for sid in sale_ids:
            sale = service.get_sale_with_items(sid)
            if sale and sale.items:
                for item in sale.items:
                    # Convert to dict for easy display
                    product_name = item.batch.product.name if item.batch and item.batch.product else "N/A"
                    all_items.append({
                        'product_name': product_name,
                        'quantity': item.quantity,
                        'dozen': item.dozen,
                        'unit_price': item.unit_price,
                        'total': item.total,
                        'for_despatch': item.for_despatch,
                    })

        if not all_items:
            QMessageBox.information(self, "No Items", "No items found for these sales.")
            return

        # Open dialog with aggregated items
        date_str = self._to_ethiopian_date_str(date_obj) if date_obj else "Unknown Date"
        dialog = AggregatedSaleItemsDialog(
            self,
            f"Items for {self.customer_name} on {date_str}",
            all_items,
            self.current_user
        )
        dialog.exec()
    
    def closeEvent(self, event):
        if hasattr(self, 'thread') and self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(1000)
        event.accept()

class CreditPaymentHistoryDialog(QDialog):
    def __init__(self, parent, customer_name, customer_id, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Payment History - {customer_name}")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.customer_id = customer_id
        self.current_user = current_user
        self.transactions = []          # combined history list
        self.thread = None
        self.worker = None
        self.is_loading = False
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Loading indicator (hidden initially)
        self.loading_label = QLabel("Loading payment history, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        layout.addWidget(self.loading_label)

        # Table
        self.table = QTableWidget()
        headers = ["Date", "Balance", "Credit", "Debit", "Bank Account", "Remaining", "Note", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self.table.setColumnWidth(7, 80)

        # Elderly‑friendly styling
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

        layout.addWidget(self.table, 1)

        # Close button – larger
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def _to_ethiopian_date_str(self, dt):
        if not dt:
            return ""
        try:
            from ui.components.ethiopian_date import EthiopianDateConverter
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(dt)
            return f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        except Exception:
            return dt.strftime("%Y-%m-%d")

    def load_data(self):
        """Start background thread to fetch payment history."""
        if self.is_loading:
            return
        self.is_loading = True
        self.loading_label.show()
        self.table.hide()

        self.thread = QThread()
        self.worker = Worker(self._fetch_data)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_data_loaded)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_data(self):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        return service.get_customer_combined_history(self.customer_id)

    def on_data_loaded(self, transactions):
        self.transactions = transactions
        self.populate_table()
        self.loading_label.hide()
        self.table.show()
        self.is_loading = False

    def on_error(self, error):
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load payment history:\n{error}")
        self.loading_label.hide()
        self.table.show()
        self.is_loading = False

    def populate_table(self):
        """Show most recent transactions first."""
        display_tx = list(reversed(self.transactions))

        self.table.setRowCount(len(display_tx))
        for row, tx in enumerate(display_tx):
            # Date
            date_str = self._to_ethiopian_date_str(tx['date']) if tx['date'] else ""
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            # Balance (before)
            balance_item = QTableWidgetItem(f"${tx['balance_before']:,.2f}")
            balance_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, balance_item)

            # Credit (green for new sales)
            if tx['type'] == 'credit_sale':
                credit_amount = tx['amount']   # positive
                debit_amount = 0.0
            else:
                credit_amount = 0.0
                debit_amount = -tx['amount']   # amount is negative for payments

            credit_item = QTableWidgetItem(f"${credit_amount:,.2f}" if credit_amount > 0 else "")
            credit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            credit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if credit_amount > 0:
                credit_item.setForeground(QColor("#27ae60"))
            self.table.setItem(row, 2, credit_item)

            debit_item = QTableWidgetItem(f"${debit_amount:,.2f}" if debit_amount > 0 else "")
            debit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            debit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if debit_amount > 0:
                debit_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 3, debit_item)

            # Bank Account (only for payments)
            bank_display = tx.get('bank_account_display', 'New Credit') if tx['type'] == 'payment' else 'New Credit'
            bank_item = QTableWidgetItem(bank_display)
            bank_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 4, bank_item)

            # Remaining (balance after)
            remaining_item = QTableWidgetItem(f"${tx['balance_after']:,.2f}")
            remaining_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            remaining_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 5, remaining_item)

            # Note
            note_item = QTableWidgetItem(tx.get('notes', ''))
            note_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 6, note_item)

            # Actions – delete button for payment groups (admin only)
            if tx['type'] == 'payment' and self.is_user_admin():
                delete_btn = QPushButton("🗑️")
                delete_btn.setFixedSize(40, 40)
                delete_btn.setToolTip("Delete this payment group")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        font-size: 18px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #c0392b; }
                """)
                # Use all transaction ids for grouped deletion
                tx_ids = tx.get('all_transaction_ids', [])
                delete_btn.clicked.connect(lambda checked, ids=tx_ids: self.delete_payment_group(ids))
                self.table.setCellWidget(row, 7, delete_btn)
            else:
                self.table.setItem(row, 7, QTableWidgetItem(""))

    def is_user_admin(self):
        if not self.current_user:
            return False
        if isinstance(self.current_user, dict):
            return self.current_user.get('is_admin') or self.current_user.get('role') == 'admin'
        return getattr(self.current_user, 'is_admin', False)

    def delete_payment_group(self, transaction_ids):
        """Delete all payment transactions in a grouped payment."""
        if not transaction_ids:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Delete this payment group? This will remove all linked transactions and update the customer's balance.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        success = service.delete_payment_group(transaction_ids, user_id)
        if success:
            QMessageBox.information(self, "Success", "Payment group deleted.")
            self.load_data()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete payment group.")

    def closeEvent(self, event):
        """Stop background thread before closing to avoid accessing deleted widgets."""
        try:
            if self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(1000)
        except RuntimeError:
            # Underlying C++ object already deleted – nothing to do
            pass
        event.accept()


class SalePaymentHistoryDialog(QDialog):
    """Displays payment transactions for a specific sale."""
    def __init__(self, parent, sale_id: int, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Payment History - Sale #{sale_id}")
        self.setMinimumSize(800, 400)
        self.resize(900, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.sale_id = sale_id
        self.current_user = current_user
        self.payments = []
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Search bar - enlarged
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by amount, bank...")
        self.search_edit.setMinimumHeight(35)
        self.search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.search_edit.textChanged.connect(self.filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        # Table - elderly-friendly styling
        self.table = QTableWidget()
        headers = ["Date", "Amount", "Bank Account", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 80)  # wider for larger delete button

        self.table.setAlternatingRowColors(True)
        
        # Large fonts and tall rows
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

        layout.addWidget(self.table, 1)

        # Close button - larger
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        # Status label - larger font
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        layout.addWidget(self.status_label)

    def load_data(self):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        self.payments = service.get_payments_by_sale(self.sale_id)

        self.table.setRowCount(len(self.payments))
        for row, pmt in enumerate(self.payments):
            # Date
            date_str = pmt['payment_date'].strftime("%Y-%m-%d %H:%M") if pmt['payment_date'] else ""
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            # Amount
            amount_item = QTableWidgetItem(f"${pmt['amount']:,.2f}")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, amount_item)

            # Bank
            bank_display = pmt['bank_account_name']
            if pmt['bank_name']:
                bank_display = f"{pmt['bank_name']} - {bank_display}"
            bank_item = QTableWidgetItem(bank_display)
            bank_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 2, bank_item)

            # Delete button (admin only) - larger
            if self.is_user_admin():
                delete_btn = QPushButton("🗑️")
                delete_btn.setFixedSize(40, 40)
                delete_btn.setToolTip("Delete this payment")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        font-size: 18px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #c0392b; }
                """)
                delete_btn.clicked.connect(lambda checked, t_id=pmt['transaction_id']: self.delete_payment(t_id))
                self.table.setCellWidget(row, 3, delete_btn)
            else:
                self.table.setItem(row, 3, QTableWidgetItem(""))

        self.update_status()

    def filter_table(self, text):
        search_lower = text.lower()
        for row in range(self.table.rowCount()):
            if not search_lower:
                self.table.setRowHidden(row, False)
                continue
            match = False
            for col in range(3):
                item = self.table.item(row, col)
                if item and search_lower in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)
        self.update_status()

    def update_status(self):
        visible = self.table.rowCount() - sum(1 for r in range(self.table.rowCount()) if self.table.isRowHidden(r))
        self.status_label.setText(f"Showing {visible} of {self.table.rowCount()} payments")

    def is_user_admin(self):
        if not self.current_user:
            return False
        if isinstance(self.current_user, dict):
            return self.current_user.get('is_admin') or self.current_user.get('role') == 'admin'
        return getattr(self.current_user, 'is_admin', False)

    def delete_payment(self, transaction_id):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this payment?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        success = service.delete_payment_transaction(transaction_id, user_id)
        if success:
            QMessageBox.information(self, "Success", "Payment deleted successfully.")
            self.load_data()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete payment.")



class AllSalesOverviewDialog(QDialog):
    """Dialog showing all sales with filtering, view, payment history, delete."""
    edit_sale_requested = Signal(int)
    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("All Sales Overview")
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
        self.page_size = 50
        self.current_page = 1
        self.total_pages = 1
        self.is_loading = False
        self.all_loaded = False
        self.current_search = ""
        self.current_date_search = ""
        self._closed = False
        self.thread = None
        self.worker = None
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_page(reset=True)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f8f9fa;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(15)

        # Search bar - enlarged
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by sale ID, customer, or product...")
        self.search_edit.setMinimumHeight(35)
        self.search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.search_edit.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)

        date_label = QLabel("Date:")
        date_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        search_layout.addWidget(date_label)

        self.date_search_edit = QLineEdit()
        self.date_search_edit.setPlaceholderText("DD/MM/YYYY (Ethiopian)")
        self.date_search_edit.setMinimumHeight(35)
        self.date_search_edit.setMaximumWidth(150)
        self.date_search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.date_search_edit.textChanged.connect(self.on_date_search_changed)
        search_layout.addWidget(self.date_search_edit)

        clear_date_btn = QPushButton("Clear Date")
        clear_date_btn.setFixedHeight(35)
        clear_date_btn.setCursor(Qt.PointingHandCursor)
        clear_date_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        clear_date_btn.clicked.connect(self.clear_date_search)
        search_layout.addWidget(clear_date_btn)

        search_layout.addStretch()
        content_layout.addLayout(search_layout)

        # Table - elderly-friendly styling
        self.table = QTableWidget()
        headers = [
            "Sale ID", "Date (Ethiopian)", "Customer", "Delivery Address", "Total Amount",
            "Payment Status", "Actions"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(6, 160)  # wider for larger buttons

        self.table.setAlternatingRowColors(True)
        
        # Large fonts and tall rows
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

        # Connect scroll bar for lazy loading
        self.table.verticalScrollBar().valueChanged.connect(self.on_scroll)

        content_layout.addWidget(self.table, 1)

        # Loading indicator
        self.loading_label = QLabel("Loading sales data, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        content_layout.addWidget(self.loading_label)


        main_layout.addWidget(content_widget, 1)

    def on_search_changed(self, text):
        self.current_search = text
        self.load_page(reset=True)
    
    def on_date_search_changed(self, text):
        """Called when date search text changes."""
        self.current_date_search = text
        self.load_page(reset=True)

    def clear_date_search(self):
        """Clear the date search field."""
        self.date_search_edit.clear()

    def parse_ethiopian_date(self, date_str: str) -> Optional[date]:
        """
        Parse Ethiopian date string (DD/MM/YYYY) and return Gregorian date.
        Returns None if invalid format or date doesn't exist.
        """
        if not date_str or not date_str.strip():
            return None
        
        date_str = date_str.strip()
        import re
        parts = re.split(r'[/\-\.]', date_str)
        
        if len(parts) != 3:
            return None
        
        try:
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            
            if month < 1 or month > 13:
                return None
            if day < 1 or day > 30:
                return None
            if month == 13 and day > 6:
                return None
            
            from ui.components.ethiopian_date import EthiopianDateConverter
            greg_date = EthiopianDateConverter.to_gregorian(year, month, day)
            return greg_date
        except (ValueError, Exception):
            return None

    def get_filter_date(self) -> Optional[date]:
        """Parse the date search field and return Gregorian date or None."""
        return self.parse_ethiopian_date(self.date_search_edit.text())

    def load_page(self, reset=False):
        if self.is_loading or (not reset and self.all_loaded):
            return
        self.is_loading = True

        if reset:
            self.current_page = 1
            self.all_loaded = False
            self.table.setRowCount(0)
            self.loading_label.show()
            self.table.hide()

        if reset:
            self.thread = QThread()
            self.worker = Worker(self._fetch_page_data)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self._on_page_loaded)
            self.worker.error.connect(self._on_page_error)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.thread.start()
        else:
            self._fetch_and_append()
    
    def _fetch_page_data(self):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        filter_date = self.get_filter_date()
        sales, total = service.get_all_sales_paginated(
            page=self.current_page,
            page_size=self.page_size,
            search=self.current_search,
            filter_date=filter_date
        )
        return sales, total
    
    def _on_page_loaded(self, result):
        if self._closed:
            return
        sales, total = result
        self.total_pages = (total + self.page_size - 1) // self.page_size
        self.append_rows(sales)

        if self.current_page >= self.total_pages:
            self.all_loaded = True

        self.current_page += 1
        self.is_loading = False
        # self.update_status()

        self.loading_label.hide()
        self.table.show()
    
    def _on_page_error(self, error):
        if self._closed:
            return
        self.is_loading = False
        self.loading_label.setText(f"Error loading sales: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load sales data:\n{error}")
        self.loading_label.hide()
        self.table.show()
    
    def _fetch_and_append(self):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        filter_date = self.get_filter_date()
        sales, total = service.get_all_sales_paginated(
            page=self.current_page,
            page_size=self.page_size,
            search=self.current_search,
            filter_date=filter_date
        )
        self.total_pages = (total + self.page_size - 1) // self.page_size
        self.append_rows(sales)

        if self.current_page >= self.total_pages:
            self.all_loaded = True

        self.current_page += 1
        self.is_loading = False

    def append_rows(self, sales):
        start_row = self.table.rowCount()
        self.table.setRowCount(start_row + len(sales))
        for offset, sale in enumerate(sales):
            row = start_row + offset
            
            # Sale ID
            id_item = QTableWidgetItem(str(sale.id))
            id_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, id_item)

            # Ethiopian date
            date_str = self._to_ethiopian_date_str(sale.created_at)
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 1, date_item)

            # Customer
            customer = sale.customer.name if sale.customer else "N/A"
            cust_item = QTableWidgetItem(customer)
            cust_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 2, cust_item)

            # Delivery Address - elide with tooltip
            parts = []
            if sale.delivery_name:
                parts.append(sale.delivery_name)
            if sale.delivery_phone:
                parts.append(sale.delivery_phone)
            if sale.delivery_place:
                parts.append(sale.delivery_place)
            if sale.delivery_Plate:
                parts.append(sale.delivery_Plate)
            delivery_str = ' - '.join(parts) if parts else ''
            delivery_item = QTableWidgetItem(delivery_str)
            delivery_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            delivery_item.setToolTip(delivery_str if delivery_str else "No delivery address")
            self.table.setItem(row, 3, delivery_item)

            # Total Amount
            amount_item = QTableWidgetItem(f"${sale.total_amount:,.2f}")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, amount_item)

            # Payment Status
            status = self._get_payment_status(sale)
            status_item = QTableWidgetItem(status)
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "Paid":
                status_item.setForeground(QColor("#27ae60"))
            elif status in ["Credit", "Partial"]:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 5, status_item)

            # Actions - larger buttons
            actions_widget = self.create_action_buttons(sale)
            self.table.setCellWidget(row, 6, actions_widget)

    def _to_ethiopian_date_str(self, dt):
        if not dt:
            return ""
        try:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(dt.date())
            return f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        except Exception:
            return dt.strftime("%Y-%m-%d")

    def _get_payment_status(self, sale):
        if not sale.payment_terms:
            return "Unknown"
        term = sale.payment_terms[0]
        if term.payment_status == PaymentStatusEnum.PAID:
            return "Paid"
        elif term.payment_status == PaymentStatusEnum.CREDIT:
            return "Credit"
        elif term.payment_status == PaymentStatusEnum.PARTIAL:
            return "Partial"
        else:
            return term.payment_status.value.capitalize() if term.payment_status else "Unknown"

    def create_action_buttons(self, sale):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        # View items button
        view_btn = QPushButton("👁️")
        view_btn.setFixedSize(40, 40)
        view_btn.setToolTip("View Items")
        view_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        view_btn.clicked.connect(lambda: self.view_sale_items(sale.id))

        if not sale.items_data:
            edit_btn = QPushButton("✏️")
            edit_btn.setFixedSize(40, 40)
            edit_btn.setToolTip("Edit this sale")
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1e8449; }
            """)
            edit_btn.clicked.connect(lambda: self.edit_sale_requested.emit(sale.id))

        # Payment history button
        hist_btn = QPushButton("📜")
        hist_btn.setFixedSize(40, 40)
        hist_btn.setToolTip("Payment History")
        hist_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        hist_btn.clicked.connect(lambda: self.show_payment_history(sale.id))

        # Delete button
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(40, 40)
        delete_btn.setToolTip("Delete Sale")
        if self.is_user_admin():
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #c0392b; }
            """)
            delete_btn.clicked.connect(lambda: self.delete_sale(sale.id))
        else:
            delete_btn.setEnabled(False)
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #bdc3c7;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                }
            """)

        layout.addWidget(view_btn)
        layout.addWidget(hist_btn)
        if not sale.items_data:
            layout.addWidget(edit_btn) # type: ignore
        layout.addWidget(delete_btn)
        return widget

    def view_sale_items(self, sale_id):
        from services.new_sale_service import NewSaleService
        service = NewSaleService()
        sale = service.get_sale_with_items(sale_id)
        if sale and sale.items:
            dialog = SaleItemsDialog(self, f"Sale #{sale_id} Items", sale, self.current_user)
            dialog.setModal(False)
            dialog.show()
        else:
            QMessageBox.information(self, "No Items", "This sale has no items.")

    def show_payment_history(self, sale_id):
        dialog = SalePaymentHistoryDialog(self, sale_id, self.current_user)
        dialog.setModal(False)
        dialog.show()

    def delete_sale(self, sale_id):
        if not self.is_user_admin():
            QMessageBox.warning(self, "Permission Denied", "Only admin can delete sales.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete sale #{sale_id}?\n\nThis will permanently remove all related records and restore inventory.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            from services.new_sale_service import NewSaleService
            service = NewSaleService()
            user_id = None
            if self.current_user:
                if isinstance(self.current_user, dict):
                    user_id = self.current_user.get('id')
                else:
                    user_id = getattr(self.current_user, 'id', None)
            if service.delete_sale_cascade(sale_id, user_id):
                QMessageBox.information(self, "Deleted", f"Sale #{sale_id} deleted.")
                self.load_page(reset=True)
            else:
                QMessageBox.critical(self, "Error", "Delete failed.")

    def on_scroll(self, value):
        scrollbar = self.table.verticalScrollBar()
        if value >= scrollbar.maximum() - 100 and not self.is_loading and not self.all_loaded:
            self.load_page()

    
    def filter_table(self, text):
        """Hide rows that do not contain the search text in any visible column."""
        search_lower = text.lower()

        for row in range(self.table.rowCount()):
            if not search_lower:
                self.table.setRowHidden(row, False)
                continue

            match = False
            for col in range(6):
                item = self.table.item(row, col)
                if item and search_lower in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    
    def edit_sale(self, sale):
        """Emit signal to open this sale in the sales manager for editing."""
        self.edit_sale_requested.emit(sale.id)

    def is_user_admin(self):
        if not self.current_user:
            return False
        if isinstance(self.current_user, dict):
            return self.current_user.get('is_admin') or self.current_user.get('role') == 'admin'
        return getattr(self.current_user, 'is_admin', False)

    def closeEvent(self, event):
        """Stop background thread before closing to avoid accessing deleted widgets."""
        self._closed = True
        try:
            if hasattr(self, 'thread') and self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(2000)
        except RuntimeError:
            # Underlying C++ object already deleted – nothing to do
            pass
        event.accept()



class AggregatedSaleItemsDialog(QDialog):
    """Displays items from multiple sales, with a total row."""
    def __init__(self, parent, title, items, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        screen = QApplication.primaryScreen().availableGeometry()
        desired_height = min(int(screen.height() * 0.6), 600)
        desired_height = max(desired_height, 400)
        self.setMinimumSize(600, 400)
        self.resize(800, desired_height)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.items = items
        self.current_user = current_user
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        headers = ["Product", "Quantity", "Dozen", "Unit Price", "Total", "Despatched"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        # header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.table.setColumnWidth(0, 300)
        self.table.setAlternatingRowColors(True)

        # === ONLY STYLING CHANGES – NO LOGIC ALTERATION ===
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
                border-radius: 4px;
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

        self.populate_table()  # original logic unchanged
        layout.addWidget(self.table)

        # Close button – only size and font changed
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        btn_close.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(btn_close)
        layout.addLayout(button_layout)

    def populate_table(self):
        """Aggregate items by product name, with a total row."""
        # Aggregate quantities and totals by product name
        aggregated = {}
        for item in self.items:
            name = item['product_name']
            if name not in aggregated:
                aggregated[name] = {
                    'product_name': name,
                    'quantity': 0,
                    'dozen': item['dozen'],  # assume dozen is consistent for the same product
                    'unit_price': item['unit_price'],  # assume unit price is consistent
                    'total': 0.0,
                    'for_despatch': item['for_despatch'],  # assume consistent
                }
            aggregated[name]['quantity'] += item['quantity']
            aggregated[name]['total'] += item['total']
        
        # Convert to sorted list
        aggregated_list = sorted(aggregated.values(), key=lambda x: x['product_name'])
        
        self.table.setRowCount(len(aggregated_list))
        total_sum = 0.0
        
        for row, item in enumerate(aggregated_list):
            # Product name
            name_item = QTableWidgetItem(item['product_name'])
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, name_item)

            # Quantity
            qty_item = QTableWidgetItem(str(item['quantity']))
            qty_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, qty_item)

            # Dozen
            dozen_item = QTableWidgetItem(str(item['dozen']))
            dozen_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            dozen_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, dozen_item)

            # Unit Price
            price_item = QTableWidgetItem(f"${item['unit_price']:,.2f}")
            price_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, price_item)

            # Total
            total_item = QTableWidgetItem(f"${item['total']:,.2f}")
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, total_item)

            # Despatched status
            status = "Yes" if item['for_despatch'] else "No"
            status_item = QTableWidgetItem(status)
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            if item['for_despatch']:
                status_item.setForeground(QColor("#27ae60"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 5, status_item)

            total_sum += item['total']

        # Add total row
        total_row = len(aggregated_list)
        self.table.insertRow(total_row)
        
        total_label = QTableWidgetItem("TOTAL")
        total_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        total_label.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setItem(total_row, 0, total_label)
        
        # Span the TOTAL label across columns 0-3
        self.table.setSpan(total_row, 0, 1, 4)
        
        total_amount_item = QTableWidgetItem(f"${total_sum:,.2f}")
        total_amount_item.setFont(QFont("Segoe UI", 14, QFont.Bold))
        total_amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(total_row, 4, total_amount_item)
        
        # Optionally add a despatched placeholder for the total row
        total_despatch = QTableWidgetItem("")
        self.table.setItem(total_row, 5, total_despatch)

class ProfitDialog(QDialog):
    """Profit dashboard with cards styled identically to main dashboard cards."""

    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Profit Dashboard")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 800)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.sale_service = NewSaleService()
        self.expense_service = ExpenseService()
        self.purchase_service = PurchaseService()
        self.bank_account_service = BankAccountService()
        self.new_product_service = NewProductService()
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Profit Dashboard")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        main_layout.addWidget(title)

        self.loading_label = QLabel("Loading profit data, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: #f5f7fa; border: none;")

        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.cards_layout = QGridLayout(scroll_content)
        self.cards_layout.setSpacing(25)
        self.cards_layout.setContentsMargins(30, 30, 30, 30)

        for i in range(3):
            self.cards_layout.setColumnStretch(i, 1)
        for i in range(2):
            self.cards_layout.setRowStretch(i, 1)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        btn_close = QPushButton("Close")
        btn_close.setFixedSize(100, 35)
        btn_close.setCursor(Qt.PointingHandCursor)
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
        main_layout.addWidget(btn_close, alignment=Qt.AlignRight)

    # ---------- Ethiopian calendar helpers ----------
    def _ethiopian_month_start(self, eth_year: int, eth_month: int) -> date:
        return EthiopianDateConverter.to_gregorian(eth_year, eth_month, 1)

    def _add_ethiopian_months(self, eth_year: int, eth_month: int, months: int) -> Tuple[int, int]:
        total_months = eth_year * 13 + (eth_month - 1) + months
        new_year = total_months // 13
        new_month = (total_months % 13) + 1
        return new_year, new_month

    # ---------- Data loading ----------
    def load_data(self):
        """Start background thread to fetch data for all periods."""
        self.loading_label.show()
        self.thread = QThread()
        self.worker = Worker(self._fetch_all_periods_data)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_data_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_all_periods_data(self):
        today_greg = date.today()
        eth_year, eth_month, _ = EthiopianDateConverter.to_ethiopian(today_greg)

        # ---- 5 period cards ----
        periods = [
            ("Today", today_greg, today_greg),
            ("This Month", self._ethiopian_month_start(eth_year, eth_month), today_greg),
            ("3 Months", self._ethiopian_month_start(*self._add_ethiopian_months(eth_year, eth_month, -3)), today_greg),
            ("6 Months", self._ethiopian_month_start(*self._add_ethiopian_months(eth_year, eth_month, -6)), today_greg),
            ("1 Year", self._ethiopian_month_start(*self._add_ethiopian_months(eth_year, eth_month, -12)), today_greg),
        ]

        results = []
        for name, start, end in periods:
            selling = self.sale_service.get_total_selling_price_for_period(start, end)
            cost = self.sale_service.get_total_cost_price_for_period(start, end)
            expenses = self.expense_service.get_total_expenses_for_period(start, end)
            results.append((name, start, end, selling, cost, expenses))

        # ---- Asset snapshot ----
        from services.bank_account_service import BankAccountService
        from services.new_product_service import NewProductService

        bank_service = BankAccountService()
        product_service = NewProductService()

        cash = bank_service.get_total_balance_all_accounts()
        inventory = product_service.get_total_inventory_value()
        receivables = self.sale_service.get_credit_sales_summary()['total_unpaid']
        payables = self.purchase_service.get_credit_purchases_summary()['total_unpaid']

        # ---- This Year (Ethiopian year to date) ----
        year_start_greg = self._ethiopian_month_start(eth_year, 1)   # Meskerem 1
        year_selling = self.sale_service.get_total_selling_price_for_period(year_start_greg, today_greg)
        year_cost = self.sale_service.get_total_cost_price_for_period(year_start_greg, today_greg)
        year_expenses = self.expense_service.get_total_expenses_for_period(year_start_greg, today_greg)
        this_year_profit = year_selling - year_cost - year_expenses

        this_year_drawings = self.expense_service.get_personal_expenses_for_period(year_start_greg, today_greg)

        asset_data = {
            'cash': cash,
            'inventory': inventory,
            'receivables': receivables,
            'payables': payables,
            'this_year_profit': this_year_profit,
            'this_year_drawings': this_year_drawings,
        }

        return results, asset_data

    def _on_data_loaded(self, results):
        # results is now a tuple (periods_list, asset_data)
        periods_list, asset_data = results
        self._clear_cards()

        # Extract this month's profit (second item, index 1)
        this_month_profit = 0.0
        if len(periods_list) > 1:
            _, _, _, selling, cost, expenses = periods_list[1]
            this_month_profit = selling - cost - expenses

        row, col = 0, 0
        for name, start, end, selling, cost, expenses in periods_list:
            card = self._create_period_card_with_data(name, start, end, selling, cost, expenses)
            self.cards_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        # Add asset card in the last position (now 6th card, fills row 1 col 2)
        asset_card = self._create_asset_card(asset_data, this_month_profit)
        self.cards_layout.addWidget(asset_card, row, col)

        self.loading_label.hide()

    def _on_data_error(self, error):
        self.loading_label.setText(f"Error loading profit data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load profit data:\n{error}")
        self.loading_label.hide()

    def _clear_cards(self):
        for i in reversed(range(self.cards_layout.count())):
            widget = self.cards_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

    # ---------- Card creation (with clickable Expenses) ----------
    def _create_period_card_with_data(self, period_name: str, start_date: date, end_date: date,
                                      selling: float, cost: float, expenses: float) -> QFrame:
        gross = selling - cost
        net = gross - expenses
        margin = (net / selling * 100) if selling > 0 else 0.0

        card = QFrame()
        card.setFixedHeight(320)
        card.setMinimumWidth(260)
        card.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 1px solid #E0E0E0;
            }
            QFrame:hover {
                border: 2px solid #3498db;
                background-color: #f8f9fa;
            }
        """)
        card.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(period_name)
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498db, stop:1 #2c3e50);
                color: #FFFFFF;
                font-weight: bold;
                padding: 12px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 12px;
            }
        """)
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(header)

        content = QWidget()
        content.setStyleSheet("background-color: #FFFFFF;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(15, 15, 15, 15)

        def add_row(label_text: str, value_text: str, color: str = "#2c3e50",
                    click_handler: callable = None):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)

            label = QLabel(label_text)
            label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            label.setStyleSheet("color: #2c3e50;")

            if click_handler:
                value = QPushButton(value_text)
                value.setFlat(True)
                value.setCursor(QCursor(Qt.PointingHandCursor))
                value.setStyleSheet("""
                    QPushButton {
                        border: none;
                        color: #2980b9;
                        font-weight: bold;
                        text-decoration: underline;
                        font-size: 10pt;
                        text-align: right;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        color: #1a5276;
                    }
                """)
                value.clicked.connect(click_handler)
            else:
                value = QLabel(value_text)
                value.setFont(QFont("Segoe UI", 10, QFont.Bold))
                value.setStyleSheet(f"color: {color};")
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            row_layout.addWidget(label)
            row_layout.addStretch()
            row_layout.addWidget(value)
            content_layout.addWidget(row)

        add_row("Selling Price", f"${selling:,.2f}", "#2c3e50")
        add_row("Cost Price", f"${cost:,.2f}", "#e67e22")
        add_row("Gross Profit", f"${gross:,.2f}", "#27ae60")

        # Expenses – clickable → opens ExpenseOverviewDialog filtered to this period
        add_row("Expenses", f"${expenses:,.2f}", "#e74c3c",
                click_handler=lambda checked=False, s=start_date, e=end_date: self._open_expense_overview(s, e))

        net_color = "#27ae60" if net >= 0 else "#e74c3c"
        add_row("Net Profit", f"${net:,.2f}", net_color)

        margin_label = QLabel(f"Net Margin: {margin:.1f}%")
        margin_label.setAlignment(Qt.AlignCenter)
        margin_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        margin_label.setStyleSheet("color: #7f8c8d; margin-top: 5px;")
        content_layout.addWidget(margin_label)

        layout.addWidget(content)

        # Card‑level click – opens appropriate drill‑down dialog
        def on_click(event):
            if event.button() == Qt.LeftButton:
                if period_name == "This Month":
                    from ui.pages.sales_card_dialog import MonthlyProfitSummaryDialog
                    dialog = MonthlyProfitSummaryDialog(self, period_name, start_date, end_date, self.current_user)
                    dialog.exec()
                elif period_name in ("3 Months", "6 Months", "1 Year"):
                    from ui.pages.sales_card_dialog import MonthlySummaryDialog
                    dialog = MonthlySummaryDialog(self, period_name, start_date, end_date, self.current_user)
                    dialog.exec()
                else:   # Today
                    from ui.pages.sales_card_dialog import ProfitDetailDialog
                    dialog = ProfitDetailDialog(self, period_name, start_date, end_date, self.current_user)
                    dialog.exec()

        card.mousePressEvent = on_click
        return card

    # ---------- Helper to open expense overview ----------
    def _open_expense_overview(self, start_date: date, end_date: date):
        """Open ExpenseOverviewDialog filtered to the given date range."""
        dialog = ExpenseOverviewDialog(
            self,
            current_user=self.current_user,
            start_date=start_date,
            end_date=end_date
        )
        dialog.exec()
    
    def _create_asset_card(self, asset_data: dict, this_month_profit: float) -> QFrame:
        cash = asset_data['cash']
        inventory = asset_data['inventory']
        receivables = asset_data['receivables']
        payables = asset_data['payables']
        this_year_profit = asset_data['this_year_profit']
        this_year_drawings = asset_data['this_year_drawings']

        total_assets = cash + inventory + receivables
        total_liabilities = payables
        net_worth = total_assets - total_liabilities
        retained = this_year_profit - this_year_drawings

        card = QFrame()
        card.setFixedHeight(360)
        card.setMinimumWidth(280)
        card.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 2px solid #f39c12;
            }
        """)
        card.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("💰 General Assets")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f39c12, stop:1 #e67e22);
                color: #FFFFFF;
                font-weight: bold;
                padding: 12px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 13px;
            }
        """)
        header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(header)

        content = QWidget()
        content.setStyleSheet("background-color: #FFFFFF;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(15, 18, 15, 15)

        def add_row(label_text: str, value_text: str, color: str = "#2c3e50",
                    bold: bool = True, value_size: int = 11):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)

            label = QLabel(label_text)
            label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            label.setStyleSheet("color: #2c3e50;")

            value = QLabel(value_text)
            value.setFont(QFont("Segoe UI", value_size, QFont.Bold if bold else QFont.Normal))
            value.setStyleSheet(f"color: {color};")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            row_layout.addWidget(label)
            row_layout.addStretch()
            row_layout.addWidget(value)
            content_layout.addWidget(row)

        # Assets section
        add_row("Cash at Bank",    f"${cash:,.2f}",          "#27ae60")
        add_row("STOCK",       f"${inventory:,.2f}",     "#2980b9")
        add_row("YABEDERNEW",     f"${receivables:,.2f}",   "#8e44ad")
        add_row("━ Assets",        f"${total_assets:,.2f}",  "#2c3e50")
        add_row("YETEBEDERNEW",        f"${payables:,.2f}",      "#e74c3c")
        content_layout.addWidget(QLabel(""))   # tiny spacer

        net_color = "#27ae60" if net_worth >= 0 else "#e74c3c"
        add_row("📈 CAPITAL", f"${net_worth:,.2f}", net_color, bold=True, value_size=12)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #bdc3c7; margin: 8px 0;")
        content_layout.addWidget(line)

        # This Year section
        profit_color = "#27ae60" if this_year_profit >= 0 else "#e74c3c"
        add_row("This Year Profit", f"${this_year_profit:,.2f}", profit_color)
        add_row("COST", f"${this_year_drawings:,.2f}", "#e67e22")

        retained_color = "#27ae60" if retained >= 0 else "#e74c3c"
        add_row("CURRENT PROFIT", f"${retained:,.2f}", retained_color, bold=True, value_size=12)

        layout.addWidget(content)
        return card

class ProfitDetailDialog(QDialog):
    """Shows product‑level profit breakdown for a specific period."""
    def __init__(self, parent, period_name: str, start_date: date, end_date: date, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Profit Details - {period_name}")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.period_name = period_name
        self.start_date = start_date
        self.end_date = end_date
        self.current_user = current_user
        self.sale_service = NewSaleService()
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Profit Breakdown - {self.period_name}")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.table = QTableWidget()
        headers = ["Product", "Quantity Sold", "Total Cost", "Total Selling", "Profit", "ROI (%)", "Margin (%)", "Contribution (%)"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(headers)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

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

        layout.addWidget(self.table, 1)


    def load_data(self):
        data = self.sale_service.get_product_profit_breakdown(self.start_date, self.end_date)
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(item['product_name']))
            self.table.setItem(row, 1, QTableWidgetItem(str(item['quantity'])))
            self.table.setItem(row, 2, self._amount_item(item['total_cost']))
            self.table.setItem(row, 3, self._amount_item(item['total_selling']))
            self.table.setItem(row, 4, self._amount_item(item['profit']))
            self.table.setItem(row, 5, self._percent_item(item['roi']))
            self.table.setItem(row, 6, self._percent_item(item['margin']))
            self.table.setItem(row, 7, self._percent_item(item['contribution']))
        # self.table.resizeColumnsToContents()

    def _text_item(self, value):
        item = QTableWidgetItem(value)
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        return item

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${value:,.2f}")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _percent_item(self, value):
        item = QTableWidgetItem(f"{value:.2f}%")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item


class MonthlyProfitSummaryDialog(QDialog):
    def __init__(self, parent, month_name: str, start_date: date, end_date: date, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Daily Profit - {month_name}")
        self.setMinimumSize(1100, 600)
        self.resize(1300, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.month_name = month_name
        self.start_date = start_date
        self.end_date = end_date
        self.current_user = current_user
        self.sale_service = NewSaleService()
        self.expense_service = ExpenseService()
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Daily Profit Summary - {self.month_name}")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.table = QTableWidget()
        headers = ["Date (Ethiopian)", "Quantity", "Selling Price", "Cost Price", "Gross Profit", "Expenses", "Net Profit", "Margin", "Action"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Date
        for i in range(1, 8):   # Quantity to Margin
            header.setSectionResizeMode(i, QHeaderView.Stretch)
        header.setSectionResizeMode(8, QHeaderView.Fixed)  # Action
        self.table.setColumnWidth(8, 80)

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
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.table, 1)   # stretch factor 1

    def load_data(self):
        from datetime import timedelta
        data = []
        current = self.start_date
        while current <= self.end_date:
            selling = self.sale_service.get_total_selling_price_for_period(current, current)
            cost = self.sale_service.get_total_cost_price_for_period(current, current)
            expenses = self.expense_service.get_total_expenses_for_period(current, current)
            qty = self.sale_service.get_total_quantity_for_period(current, current)
            gross = selling - cost
            net = gross - expenses
            margin = (net / selling * 100) if selling > 0 else 0.0

            data.append({
                'date': current,
                'total_quantity': qty,
                'total_selling': selling,
                'total_cost': cost,
                'gross_profit': gross,
                'expenses': expenses,
                'net_profit': net,
                'margin': margin
            })
            current += timedelta(days=1)

        self.table.setRowCount(len(data))
        for row, day in enumerate(data):
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(day['date'])
            date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
            self.table.setItem(row, 0, self._text_item(date_str))
            self.table.setItem(row, 1, self._text_item(str(day['total_quantity'])))
            self.table.setItem(row, 2, self._amount_item(day['total_selling']))
            self.table.setItem(row, 3, self._amount_item(day['total_cost']))
            self.table.setItem(row, 4, self._amount_item(day['gross_profit']))

            # Expenses as clickable button
            expenses_btn = QPushButton(f"${day['expenses']:,.2f}")
            expenses_btn.setFlat(True)
            expenses_btn.setCursor(QCursor(Qt.PointingHandCursor))
            expenses_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    color: #2980b9;
                    font-weight: bold;
                    text-decoration: underline;
                    font-size: 10pt;
                    text-align: right;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #1a5276;
                }
            """)
            def make_expense_handler(d):
                return lambda checked=False: self._open_expense_overview(d, d)
            expenses_btn.clicked.connect(make_expense_handler(day['date']))
            self.table.setCellWidget(row, 5, expenses_btn)

            net_item = self._amount_item(day['net_profit'])
            net_item.setForeground(QColor("#27ae60" if day['net_profit'] >= 0 else "#e74c3c"))
            self.table.setItem(row, 6, net_item)
            self.table.setItem(row, 7, self._percent_item(day['margin']))

            view_btn = QPushButton("Details")
            view_btn.setFixedSize(70, 30)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            def make_details_handler(d):
                return lambda checked=False: self.show_date_details(d)
            
            view_btn.clicked.connect(make_details_handler(day['date']))
            self.table.setCellWidget(row, 8, view_btn)

        self.table.resizeRowsToContents()
        self.table.horizontalHeader().setStretchLastSection(False)
        for i in range(1, 8):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

    def show_date_details(self, single_date: date):
        dialog = ProfitDetailDialog(
            self,
            single_date.strftime("%Y-%m-%d"),
            single_date,
            single_date,
            self.current_user
        )
        dialog.exec()
    
    def _open_expense_overview(self, start_date: date, end_date: date):
        """Open ExpenseOverviewDialog filtered to the given date range."""
        from ui.pages.expense_overview_dialog import ExpenseOverviewDialog
        dialog = ExpenseOverviewDialog(
            self,
            current_user=self.current_user,
            start_date=start_date,
            end_date=end_date
        )
        dialog.exec()

    def _text_item(self, value):
        item = QTableWidgetItem(value)
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        return item

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${value:,.2f}")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _percent_item(self, value):
        item = QTableWidgetItem(f"{value:.2f}%")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

class MonthlySummaryDialog(QDialog):
    """Shows aggregated profit per month for a date range, with drill‑down to daily view."""
    def __init__(self, parent, range_name: str, start_date: date, end_date: date, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Monthly Profit - {range_name}")
        self.setMinimumSize(1200, 600)  # wider for new column
        self.resize(1400, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.range_name = range_name
        self.start_date = start_date
        self.end_date = end_date
        self.current_user = current_user
        self.sale_service = NewSaleService()
        self.expense_service = ExpenseService()
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Monthly Profit Summary - {self.range_name}")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.table = QTableWidget()
        headers = ["Month (Ethiopian)", "Total Quantity", "Total Selling", "Total Cost", "Gross Profit", "Expenses", "Net Profit", "Change (%)", "Margin", "Action"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Month
        for i in range(1, 7):   # Quantity to Expenses
            header.setSectionResizeMode(i, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Change
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Margin
        header.setSectionResizeMode(9, QHeaderView.Fixed)             # Action
        self.table.setColumnWidth(9, 80)

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
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.table, 1)


    def load_data(self):
        from datetime import timedelta

        # Generate list of months in range
        months = []
        start_eth = EthiopianDateConverter.to_ethiopian(self.start_date)
        end_eth = EthiopianDateConverter.to_ethiopian(self.end_date)

        year, month, _ = start_eth
        while (year < end_eth[0]) or (year == end_eth[0] and month <= end_eth[1]):
            month_start = EthiopianDateConverter.to_gregorian(year, month, 1)
            if month == 13:
                next_year = year + 1
                next_month = 1
            else:
                next_year = year
                next_month = month + 1
            month_end = EthiopianDateConverter.to_gregorian(next_year, next_month, 1) - timedelta(days=1)
            month_start = max(month_start, self.start_date)
            month_end = min(month_end, self.end_date)
            label = f"{month:02d}/{year:04d}"
            months.append((label, month_start, month_end, year, month))

            if month == 13:
                year += 1
                month = 1
            else:
                month += 1
            if year > end_eth[0] or (year == end_eth[0] and month > end_eth[1]):
                break

        # First pass: compute net profit for each month
        month_data = []
        for label, m_start, m_end, yr, mn in months:
            selling = self.sale_service.get_total_selling_price_for_period(m_start, m_end)
            cost = self.sale_service.get_total_cost_price_for_period(m_start, m_end)
            expenses = self.expense_service.get_total_expenses_for_period(m_start, m_end)
            qty = self.sale_service.get_total_quantity_for_period(m_start, m_end)
            gross = selling - cost
            net = gross - expenses
            margin = (net / selling * 100) if selling > 0 else 0.0
            month_data.append({
                'label': label,
                'start': m_start,
                'end': m_end,
                'quantity': qty,
                'selling': selling,
                'cost': cost,
                'gross': gross,
                'expenses': expenses,
                'net': net,
                'margin': margin,
                'year': yr,
                'month': mn
            })

        # Sort by year, month (ascending)
        month_data.sort(key=lambda x: (x['year'], x['month']))

        # Second pass: compute change % from previous month
        for i in range(len(month_data)):
            if i == 0:
                change = None
            else:
                prev_net = month_data[i-1]['net']
                curr_net = month_data[i]['net']
                if prev_net != 0:
                    change = ((curr_net - prev_net) / abs(prev_net)) * 100
                else:
                    change = 100.0 if curr_net > 0 else -100.0 if curr_net < 0 else 0.0
            month_data[i]['change'] = change

        # Populate table
        self.table.setRowCount(len(month_data))
        for row, m in enumerate(month_data):
            self.table.setItem(row, 0, self._text_item(m['label']))
            self.table.setItem(row, 1, self._text_item(str(m['quantity'])))
            self.table.setItem(row, 2, self._amount_item(m['selling']))
            self.table.setItem(row, 3, self._amount_item(m['cost']))
            self.table.setItem(row, 4, self._amount_item(m['gross']))

            # Expenses as clickable button
            expenses_btn = QPushButton(f"${m['expenses']:,.2f}")
            expenses_btn.setFlat(True)
            expenses_btn.setCursor(QCursor(Qt.PointingHandCursor))
            expenses_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    color: #2980b9;
                    font-weight: bold;
                    text-decoration: underline;
                    font-size: 10pt;
                    text-align: right;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #1a5276;
                }
            """)
            def make_expense_handler(start, end):
                return lambda checked=False: self._open_expense_overview(start, end)

            expenses_btn.clicked.connect(make_expense_handler(m['start'], m['end']))
            self.table.setCellWidget(row, 5, expenses_btn)

            net_item = self._amount_item(m['net'])
            net_item.setForeground(QColor("#27ae60" if m['net'] >= 0 else "#e74c3c"))
            self.table.setItem(row, 6, net_item)


            # Change column
            if m['change'] is not None:
                change_val = m['change']
                change_text = f"{change_val:+.2f}%"
                change_item = QTableWidgetItem(change_text)
                change_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
                if change_val > 0:
                    change_item.setForeground(QColor("#27ae60"))
                elif change_val < 0:
                    change_item.setForeground(QColor("#e74c3c"))
                else:
                    change_item.setForeground(QColor("#7f8c8d"))
                change_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 7, change_item)
            else:
                dash_item = QTableWidgetItem("—")
                dash_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
                self.table.setItem(row, 7, dash_item)

            self.table.setItem(row, 8, self._percent_item(m['margin']))

            view_btn = QPushButton("Details")
            view_btn.setFixedSize(70, 30)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            view_btn.clicked.connect(lambda checked, ms=m['start'], me=m['end'], lbl=m['label']: self.show_month_details(lbl, ms, me))
            self.table.setCellWidget(row, 9, view_btn)

        self.table.resizeRowsToContents()
        for i in range(1, 7):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

    def show_month_details(self, month_label: str, start_date: date, end_date: date):
        dialog = MonthlyProfitSummaryDialog(
            self,
            month_label,
            start_date,
            end_date,
            self.current_user
        )
        dialog.exec()
    
    def _open_expense_overview(self, start_date: date, end_date: date):
        """Open ExpenseOverviewDialog filtered to the given date range."""
        from ui.pages.expense_overview_dialog import ExpenseOverviewDialog
        dialog = ExpenseOverviewDialog(
            self,
            current_user=self.current_user,
            start_date=start_date,
            end_date=end_date
        )
        dialog.exec()

    def _text_item(self, value):
        item = QTableWidgetItem(value)
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        return item

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${value:,.2f}")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _percent_item(self, value):
        item = QTableWidgetItem(f"{value:.2f}%")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item