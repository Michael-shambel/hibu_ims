#!/usr/bin/env python3
"""
showEvent
"""
import os
import re
from datetime import date
import time
import logging
from fidel import Transliterate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFormLayout, QMessageBox, QFrame, QApplication,
    QGroupBox, QSplitter, QCheckBox, QDialog, QDateEdit,
    QScrollArea, QSizePolicy, QDoubleSpinBox, QGridLayout,
    QRadioButton, QButtonGroup, QCompleter
)
from PySide6.QtCore import Qt, QDate, QTimer, QLocale
from PySide6.QtGui import QFont, QColor, QDoubleValidator
from services.customer_service import CustomerService
from services.bank_account_service import BankAccountService
from services.new_product_service import NewProductService
from services.new_sale_service import NewSaleService
from ui.pages.expense_dialog import ExpenseDialog
from services.expense_service import ExpenseService
from services.base_service import get_session
from ui.pages.bank_transfer_dialog import BankTransferDialog
from ui.components.ethiopian_date import EthiopianDateEdit
from ui.pages.credit_sales_overview_dialog import CreditSalesOverviewDialog
from ui.pages.credit_purchases_overview_dialog import CreditPurchasesOverviewDialog
from services.unusual_sales_alert_service import UnusualSalesAlertService
from services.daily_sales_cache_service import DailySalesCacheService
from models.sale_payment_term import PaymentStatusEnum
from sqlalchemy import func
from models.product_batch import ProductBatch
from telegrambot.bot import send_notification_to_admin_sync, notify_customer_sync
from services.bank_transaction_service import BankTransactionService
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl
from ui.pages.bank_balance_dialog import BankBalanceDialog

logger = logging.getLogger(__name__)

class ModernButton(QPushButton):
    def __init__(self, text="", icon=None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setFont(QFont("Segoe UI", 12, QFont.Bold))
        
        
    def setPrimary(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
        """)
    
    def setSuccess(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
    
    def setDanger(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
    
    def setSecondary(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)

class SelectAllLineEdit(QLineEdit):
    """Line edit that selects all text when clicked."""
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

class NumberLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._formatting = False          # guard against recursion
        self.textEdited.connect(self._format_text)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def _format_text(self, text):
        """Called only when the user edits the text."""
        if self._formatting:
            return
        self._formatting = True

        # Remove existing commas and validate
        plain = text.replace(',', '')
        if plain == '' or plain == '-':
            self.setText(plain)
            self._formatting = False
            return

        # Try to interpret as a number (allow decimals)
        try:
            value = float(plain)
        except ValueError:
            # Invalid input – reset to previous valid state (or empty)
            self.setText('')
            self._formatting = False
            return

        # Format with commas, preserve decimal part as typed
        if '.' in plain:
            int_part, dec_part = plain.split('.', 1)
        else:
            int_part, dec_part = plain, ''
        
        # Format integer part with locale grouping
        # Use system locale (e.g., 1,234,567.89)
        locale = QLocale.system()
        formatted_int = locale.toString(int(int_part) if int_part else 0)
        # Remove any decimals that locale may add (it won't, because we used toString(int))
        
        if dec_part:
            formatted = f"{formatted_int}.{dec_part}"
        else:
            # If user typed a decimal point but no digits yet, keep the dot
            if text.endswith('.'):
                formatted = f"{formatted_int}."
            else:
                formatted = formatted_int

        # Preserve cursor position proportionally
        cursor = self.cursorPosition()
        old_len = len(self.text())
        new_len = len(formatted)
        new_pos = cursor + (new_len - old_len)
        if new_pos < 0:
            new_pos = 0
        elif new_pos > new_len:
            new_pos = new_len

        self.blockSignals(True)
        self.setText(formatted)
        self.setCursorPosition(new_pos)
        self.blockSignals(False)

        self._formatting = False

class AddCustomerDialog(QDialog):
    """Dialog for adding or editing a customer (name, phone, tin_num only)"""
    def __init__(self, parent=None, customer=None):
        super().__init__(parent)
        # self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.customer = customer
        self.customer_service = CustomerService()
        
        mode = "Edit" if customer else "Add"
        self.setWindowTitle(f"{mode} Customer")
        self.setFixedSize(500, 350)  # Smaller size now
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel(f"{mode} Customer")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        header.setStyleSheet("color: #2c3e50;")
        layout.addWidget(header)

        # Form
        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter customer name")
        self.name_input.setFixedHeight(36)
        self.style_input(self.name_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Enter phone number")
        self.phone_input.setFixedHeight(36)
        self.style_input(self.phone_input)

        self.tin_input = QLineEdit()
        self.tin_input.setPlaceholderText("Enter TIN number")
        self.tin_input.setFixedHeight(36)
        self.style_input(self.tin_input)

        # Set font size for labels
        for i in range(form.rowCount()):
            label = form.itemAt(i, QFormLayout.LabelRole)
            if label and label.widget():
                label.widget().setFont(QFont("Segoe UI", 13))

        form.addRow("Name:*", self.name_input)
        form.addRow("Phone:", self.phone_input)
        form.addRow("TIN:", self.tin_input)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if self.customer:
            self.delete_btn = QPushButton("Delete")
            self.delete_btn.setFixedSize(100, 36)
            self.delete_btn.setCursor(Qt.PointingHandCursor)
            self.delete_btn.setFont(QFont("Segoe UI", 13))
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-weight: 600;
                }
                QPushButton:hover { background-color: #c0392b; }
            """)
            self.delete_btn.clicked.connect(self.delete_customer)
            btn_layout.addWidget(self.delete_btn)
            btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(100, 36)
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFont(QFont("Segoe UI", 13))
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)

        self.save_btn = QPushButton("Update" if self.customer else "Add")
        self.save_btn.setFixedSize(100, 36)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setFont(QFont("Segoe UI", 13))
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        self.save_btn.clicked.connect(self.validate_and_accept)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

        # If editing, populate fields
        if self.customer:
            self.populate_fields()

        self.name_input.setFocus()

    def style_input(self, widget):
        widget.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 16px;
                font-weight: 500;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
                background-color: #f8fafc;
            }
        """)

    def populate_fields(self):
        self.name_input.setText(self.customer.name or "")
        self.phone_input.setText(self.customer.phone or "")
        self.tin_input.setText(self.customer.tin_num or "")

    def validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Customer name is required!")
            self.name_input.setFocus()
            return
        self.accept()

    def delete_customer(self):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete customer '{self.customer.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.customer_service.delete(self.customer.id):
                # QMessageBox.information(self, "Success", "Customer deleted.")
                self.done(2)  # Special result code for delete
            else:
                QMessageBox.critical(self, "Error", "Delete failed.")

    def get_customer_data(self):
        return {
            'name': self.name_input.text().strip(),
            'phone': self.phone_input.text().strip() or None,
            'tin_num': self.tin_input.text().strip() or None
        }


class CompactSummaryWidget(QWidget):
    """Compact professional summary widget"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Summary items
        self.summary_grid = QGridLayout()
        self.summary_grid.setHorizontalSpacing(15)
        self.summary_grid.setVerticalSpacing(4)
        
        # Subtotal
        self.subtotal_label = QLabel("Subtotal:")
        self.subtotal_label.setFont(QFont("Segoe UI", 13))
        self.subtotal_value = QLabel("ETB 0.00")
        self.subtotal_value.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.subtotal_value.setStyleSheet("color: #374151;")
        self.subtotal_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # Labour
        self.labour_label = QLabel("Labour:")
        self.labour_label.setFont(QFont("Segoe UI", 13))
        self.labour_value = QLabel("ETB 0.00")
        self.labour_value.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.labour_value.setStyleSheet("color: #dc2626;")
        self.labour_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # Total
        self.total_label = QLabel("<b>TOTAL:</b>")
        self.total_label.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.total_value = QLabel("ETB 0.00")
        self.total_value.setFont(QFont("Segoe UI", 17, QFont.Bold))
        self.total_value.setStyleSheet("color: #059669;")
        self.total_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # Add to grid
        self.summary_grid.addWidget(self.subtotal_label, 0, 0)
        self.summary_grid.addWidget(self.subtotal_value, 0, 1)
        self.summary_grid.addWidget(self.labour_label, 1, 0)
        self.summary_grid.addWidget(self.labour_value, 1, 1)
        self.summary_grid.addWidget(self.total_label, 2, 0)
        self.summary_grid.addWidget(self.total_value, 2, 1)
        
        layout.addLayout(self.summary_grid)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #e5e7eb; margin: 10px 0;")
        layout.addWidget(separator)
    
    def update_summary(self, subtotal, labour, total, item_count):
        """Update summary values"""
        self.subtotal_value.setText(f"ETB {subtotal:,.2f}")
        self.labour_value.setText(f"ETB {labour:,.2f}")
        self.total_value.setText(f"ETB {total:,.2f}")
        # self.items_label.setText(f"Items: {item_count}")


class SalesManager(QWidget):
    """load_products_combo showEvent"""
    
    AMHARIC_OVERRIDES = {}
    
    def __init__(self, current_user=None):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Quick Sales")
        self.editing_sale_id = None
        self.customer_service = CustomerService()
        self.bank_account_service = BankAccountService()
        self.product_service = NewProductService()
        self.sale_service = NewSaleService()
        self.expense_service = ExpenseService()
        
        self.current_user = current_user
        self.is_credit_mode = False  # Default to Live Mode
        self.max_cost_cache = {}   # was self.min_cost_cache
        self._warned_rows = set()

        self.temp_sale_date = None          # QDate object (Gregorian)
        self.temp_date_timestamp = None     # time.time()
        self.date_expiry_seconds = 2 * 60 * 60   # 2 hours
        self.date_expiry_timer = QTimer(self)
        self.date_expiry_timer.setSingleShot(True)
        self.date_expiry_timer.timeout.connect(self._reset_date_if_expired)
        self.credit_count_timer = QTimer(self)
        self.credit_count_timer.timeout.connect(self.update_same_day_credit_count)
        self.credit_count_timer.start(5000)
        self.daily_cache = DailySalesCacheService()


        
        self.init_ui()
        
        self.load_customers()

        self.new_sale()
        self.refresh_all_product_combos("")
        self.sale_date_edit.dateChanged.connect(self._on_sale_date_manually_changed)

    def init_ui(self):
        """bank_combo Available 60"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== TITLE BAR ====================
        title_bar = QWidget()
        title_bar.setFixedHeight(42)
        title_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2c3e50, stop:1 #3498db);
                border-radius: 6px;
            }
        """)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 15, 0)

        # ===== LABOUR EXPENSE SECTION (Qty × Rate) moved to title bar =====
        labour_widget = QWidget()
        labour_layout = QHBoxLayout(labour_widget)
        labour_layout.setContentsMargins(0, 0, 0, 0)
        labour_layout.setSpacing(5)

        # Qty (read-only, auto-calculated from product table)
        self.labour_qty = QLineEdit()
        self.labour_qty.setReadOnly(False)
        self.labour_qty.setFixedHeight(28)
        self.labour_qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.labour_qty.setFont(QFont("Segoe UI", 11))
        self.labour_qty.setMaximumWidth(60)
        self.labour_qty.setStyleSheet("background-color: #f8f9fa; border: 1px solid #d1d5db; border-radius: 4px; padding: 2px 6px;")
        labour_layout.addWidget(self.labour_qty)

        multiply_label = QLabel("×")
        multiply_label.setFont(QFont("Segoe UI", 11))
        multiply_label.setStyleSheet("color: white;")
        labour_layout.addWidget(multiply_label)

        # Rate (editable, default 70)
        self.labour_rate = QDoubleSpinBox()
        self.labour_rate.setRange(0, 999999.99)
        self.labour_rate.setDecimals(0)
        self.labour_rate.setValue(70.0)
        self.labour_rate.setFixedHeight(28)
        self.labour_rate.setMaximumWidth(80)
        self.labour_rate.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
        self.labour_rate.setFont(QFont("Segoe UI", 11))
        self.labour_rate.setAlignment(Qt.AlignRight)
        self.labour_rate.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 2px 6px;
                color: #000000;
            }
        """)
        self.labour_rate.valueChanged.connect(self.update_labour_total)
        self.labour_qty.textChanged.connect(self.update_labour_total)
        line_edit = self.labour_rate.lineEdit()
        def select_all():
            line_edit.selectAll()
        line_edit.focusInEvent = lambda event: select_all()
        labour_layout.addWidget(self.labour_rate)

        equal_label = QLabel("=")
        equal_label.setFont(QFont("Segoe UI", 11))
        equal_label.setStyleSheet("color: white;")
        labour_layout.addWidget(equal_label)

        # Total (read-only, calculated)
        self.labour_total = QLineEdit()
        self.labour_total.setReadOnly(True)
        self.labour_total.setFixedHeight(28)
        self.labour_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.labour_total.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.labour_total.setMaximumWidth(90)
        self.labour_total.setStyleSheet("background-color: #e9ecef; border: 1px solid #d1d5db; border-radius: 4px; padding: 2px 6px; font-weight: bold;")
        labour_layout.addWidget(self.labour_total)

        self.sale_date_edit = EthiopianDateEdit()
        self.sale_date_edit.setFixedHeight(32)
        self.sale_date_edit.setToolTip("Select the Ethiopian date for this sale")
        self.sale_date_edit.setFont(QFont("Segoe UI", 12))

        # Style the spinboxes inside the EthiopianDateEdit
        self.sale_date_edit.setStyleSheet("""
            QSpinBox {
                border: 1px solid #d1d5db;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 14px;
                background-color: white;
            }
            QSpinBox:focus {
                border: 1px solid #3b82f6;
            }
        """)

        
        title_layout.addWidget(self.sale_date_edit)
        title_layout.addStretch()

        # Credit Sales Overview button
        credit_sales_btn = QPushButton("📋 Credit Sales")
        credit_sales_btn.setFixedHeight(34)
        credit_sales_btn.setCursor(Qt.PointingHandCursor)
        credit_sales_btn.setFont(QFont("Segoe UI", 12))
        credit_sales_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        credit_sales_btn.clicked.connect(self.open_credit_sales_overview)

        # Credit Purchases Overview button
        credit_purchases_btn = QPushButton("📋 Credit Purchases")
        credit_purchases_btn.setFixedHeight(34)
        credit_purchases_btn.setCursor(Qt.PointingHandCursor)
        credit_purchases_btn.setFont(QFont("Segoe UI", 12))
        credit_purchases_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        credit_purchases_btn.clicked.connect(self.open_credit_purchases_overview)

        self.same_day_credit_btn = QPushButton("⏱️ Same-day (0)")
        self.same_day_credit_btn.setFixedHeight(34)
        self.same_day_credit_btn.setCursor(Qt.PointingHandCursor)
        self.same_day_credit_btn.setFont(QFont("Segoe UI", 12))
        self.same_day_credit_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        self.same_day_credit_btn.clicked.connect(self.show_unpaid_same_day_credits)

        all_sales_btn = QPushButton("📊 All Sales")
        all_sales_btn.setFixedHeight(34)
        all_sales_btn.setCursor(Qt.PointingHandCursor)
        all_sales_btn.setFont(QFont("Segoe UI", 12))
        all_sales_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1e8449;
            }
        """)
        all_sales_btn.clicked.connect(self.open_all_sales_overview)

        self.transfer_btn = QPushButton("🔄 Transfer Funds")
        self.transfer_btn.setFixedHeight(34)
        self.transfer_btn.setCursor(Qt.PointingHandCursor)
        self.transfer_btn.setFont(QFont("Segoe UI", 12))
        self.transfer_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.transfer_btn.clicked.connect(self.open_transfer_dialog)

        #Expense DIALOG
        add_expense_btn = QPushButton("💰 Add Expense")
        add_expense_btn.setFixedHeight(34)
        add_expense_btn.setCursor(Qt.PointingHandCursor)
        add_expense_btn.setFont(QFont("Segoe UI", 12))
        add_expense_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        add_expense_btn.clicked.connect(self.add_expense)


        title_layout.addWidget(self.same_day_credit_btn)
        title_layout.addWidget(all_sales_btn)
       
        title_layout.addWidget(add_expense_btn)
        # title_layout.addWidget(self.mode_toggle)
        title_layout.addWidget(credit_sales_btn)
        title_layout.addWidget(credit_purchases_btn)
        title_layout.addWidget(self.transfer_btn)
        title_layout.addWidget(labour_widget)

        main_layout.addWidget(title_bar)

        # ==================== MAIN CONTENT ====================
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)  # Prevent panels from collapsing

        # Left panel (Table)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(8)

        # Table header
        table_header = QWidget()
        table_header_layout = QHBoxLayout(table_header)
        table_header_layout.setContentsMargins(5, 0, 5, 0)

        # table_title = QLabel("📦 PRODUCTS LIST")
        # table_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        # table_title.setStyleSheet("color: #2c3e50;")

        # Add Row button
        add_row_btn = QPushButton("➕ Add Row")
        add_row_btn.setFixedHeight(34)
        add_row_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        add_row_btn.setCursor(Qt.PointingHandCursor)
        add_row_btn.setFont(QFont("Segoe UI", 12))
        add_row_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(52, 152, 219, 0.15);
                color: #2c3e50;
                border: 1px solid rgba(52, 152, 219, 0.3);
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(52, 152, 219, 0.25);
                border-color: rgba(52, 152, 219, 0.4);
            }
        """)
        add_row_btn.clicked.connect(self.add_new_row)

        # Clear All button
        clear_all_btn = QPushButton("🗑️ Clear All")
        clear_all_btn.setFixedHeight(34)
        clear_all_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        clear_all_btn.setCursor(Qt.PointingHandCursor)
        clear_all_btn.setFont(QFont("Segoe UI", 12))
        clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(231, 76, 60, 0.15);
                color: #2c3e50;
                border: 1px solid rgba(231, 76, 60, 0.3);
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(231, 76, 60, 0.25);
                border-color: rgba(231, 76, 60, 0.4);
            }
        """)
        clear_all_btn.clicked.connect(self.clear_all_rows)

        bank_btn = QPushButton("🏦 Bank Accounts")
        bank_btn.setFixedHeight(34)
        bank_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bank_btn.setCursor(Qt.PointingHandCursor)
        bank_btn.setFont(QFont("Segoe UI", 12))
        bank_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(39, 174, 96, 0.15);
                color: #2c3e50;
                border: 1px solid rgba(39, 174, 96, 0.3);
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(39, 174, 96, 0.25);
                border-color: rgba(39, 174, 96, 0.4);
            }
        """)
        bank_btn.clicked.connect(self.open_bank_balance_dialog)
        
        # table_header_layout.addWidget(table_title)
        table_header_layout.addWidget(add_row_btn)
        table_header_layout.addWidget(clear_all_btn)
        table_header_layout.addWidget(bank_btn)
        table_header_layout.addStretch()

        left_layout.addWidget(table_header)

        self.sales_table = self.create_excel_table()
        self.sales_table.itemChanged.connect(self.on_table_item_changed)
        self.sales_table.itemChanged.connect(self.update_labour_qty)
        # self.sales_table.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        left_layout.addWidget(self.sales_table, 1)

        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setFrameShape(QFrame.NoFrame)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(10)

        # ===== CUSTOMER SECTION =====
        customer_layout = QHBoxLayout()
        customer_layout.setSpacing(4)
        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(QComboBox.NoInsert)
        self.customer_combo.setFixedHeight(45)
        self.customer_combo.setMaximumWidth(500)  
        self.customer_combo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.customer_combo.setStyleSheet("""
            QComboBox {
                font-size: 14px;
                font-weight: bold;
                padding: 6px;
            }
            QComboBox QAbstractItemView {
                font-size: 14px;
                font-weight: bold;
                padding: 4px;
            }
        """)
        self.add_customer_btn = QPushButton("➕")
        self.add_customer_btn.setFixedSize(45, 45)
        self.customer_combo.setLineEdit(SelectAllLineEdit())
        self.add_customer_btn.clicked.connect(self.open_add_customer_dialog)
        customer_layout.addWidget(self.customer_combo, 1)
        customer_layout.addWidget(self.add_customer_btn)
        right_layout.addLayout(customer_layout)


        # ===== PAYMENT MODE SELECTION =====
        mode_widget = QWidget()
        mode_widget.setMaximumWidth(500)  # match other controls in this panel (customer_combo, payments_table)
        mode_layout = QHBoxLayout(mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        # Shared "toggle button" look-and-feel for the Paid / Credit selector,
        # styled consistently with the DESPATCH column toggle. Padding kept tight
        # so these don't request more width than the panel already allows.
        TOGGLE_BASE_STYLE = """
            QRadioButton {{
                spacing: 0px;
                padding: 7px 12px;
                border-radius: 6px;
                border: 2px solid #d1d5db;
                background-color: #f8fafc;
                color: #475569;
            }}
            QRadioButton::indicator {{
                width: 0px;
                height: 0px;
            }}
            QRadioButton:hover {{
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }}
            QRadioButton:checked {{
                background-color: {checked_bg};
                border: 2px solid {checked_border};
                color: white;
            }}
            QRadioButton:checked:hover {{
                background-color: {checked_border};
            }}
        """

        self.cash_radio = QRadioButton("💰 Paid (Cash/Bank)")
        self.cash_radio.setFont(QFont("Segoe UI", 13))
        self.cash_radio.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.cash_radio.setChecked(True)
        self.cash_radio.setCursor(Qt.PointingHandCursor)
        self.cash_radio.toggled.connect(self.on_payment_type_changed)
        self.cash_radio.setStyleSheet(
            TOGGLE_BASE_STYLE.format(checked_bg="#2ecc71", checked_border="#27ae60")
        )

        self.credit_radio = QRadioButton("📝 Credit")
        self.credit_radio.setFont(QFont("Segoe UI", 13))
        self.credit_radio.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.credit_radio.setCursor(Qt.PointingHandCursor)
        self.credit_radio.toggled.connect(self.on_credit_toggled)
        self.credit_radio.setStyleSheet(
            TOGGLE_BASE_STYLE.format(checked_bg="#f39c12", checked_border="#e67e22")
        )

        self.admin_detail_checkbox = QCheckBox("Notify Admin")
        self.admin_detail_checkbox.setFont(QFont("Segoe UI", 10))
        self.admin_detail_checkbox.setChecked(False)
        self.admin_detail_checkbox.setToolTip("Send detailed product list to admin after saving")

        # NEW: Send Telegram checkbox
        self.send_telegram_checkbox = QCheckBox("Send Txt")
        self.send_telegram_checkbox.setFont(QFont("Segoe UI", 10))
        self.send_telegram_checkbox.setChecked(True)   # default on
        self.send_telegram_checkbox.setToolTip("Uncheck to prevent sending order notification to store team")

        mode_layout.addWidget(self.cash_radio)
        mode_layout.addWidget(self.credit_radio)
        mode_layout.addWidget(self.admin_detail_checkbox)
        mode_layout.addWidget(self.send_telegram_checkbox)
        mode_layout.addStretch()

        right_layout.addWidget(mode_widget)
        
        self.credit_term_combo = QComboBox()
        self.credit_term_combo.addItem("Long-term (7 days)", 7)
        self.credit_term_combo.addItem("Same-day (pay by end of day)", 0)
        self.credit_term_combo.setVisible(False)
        self.credit_term_combo.setFont(QFont("Segoe UI", 14, QFont.Bold))  # Changed
        self.credit_term_combo.setFixedHeight(32)
        self.credit_term_combo.setStyleSheet("""
            QComboBox {
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.credit_term_combo.currentIndexChanged.connect(self._on_credit_term_changed)

        right_layout.addWidget(self.credit_term_combo)

        self.same_day_message_input = QLineEdit()
        self.same_day_message_input.setPlaceholderText("Optional: Add a note or reason for same-day credit...")
        self.same_day_message_input.setMaximumHeight(80)
        self.same_day_message_input.setFont(QFont("Segoe UI", 12))
        self.same_day_message_input.setVisible(False)

        right_layout.addWidget(self.same_day_message_input)

        # ===== PAYMENTS TABLE (for multiple bank splits) =====
        self.payments_table = QTableWidget()
        self.payments_table.setColumnCount(3)
        self.payments_table.setMaximumHeight(150)
        self.payments_table.setMaximumWidth(500)  
        self.payments_table.setHorizontalHeaderLabels(["Amount (ETB)", "Bank Account", ""])
        self.payments_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.payments_table.setColumnWidth(0, 115)                    # fixed width for amount
        self.payments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.payments_table.setColumnWidth(1, 245)                   # fixed width for bank name
        self.payments_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.payments_table.setColumnWidth(2, 40) 
        self.payments_table.setAlternatingRowColors(True)
        self.payments_table.verticalHeader().setVisible(False)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.payments_table.setMinimumHeight(120)
        self.payments_table.setFont(QFont("Segoe UI", 13))
        self.payments_table.horizontalHeader().setFont(QFont("Segoe UI", 10, QFont.Bold))

        right_layout.addWidget(self.payments_table)

        payment_controls = QHBoxLayout()
        self.add_payment_btn = QPushButton("➕ Add Payment")
        self.add_payment_btn.setCursor(Qt.PointingHandCursor)
        self.add_payment_btn.setFont(QFont("Segoe UI", 12))
        self.add_payment_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #374151;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.add_payment_btn.clicked.connect(self.add_payment_row)

        self.payment_total_label = QLabel("Total: ETB 0.00")
        self.payment_total_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.payment_total_label.setStyleSheet("color: #059669;")

        self.payment_remaining_label = QLabel("0.00 ETB :Remaining")
        self.payment_remaining_label.setFont(QFont("Segoe UI", 13))
        self.payment_remaining_label.setStyleSheet("color: #dc2626;")

        payment_controls.addWidget(self.add_payment_btn)
        payment_controls.addWidget(self.payment_total_label)
        payment_controls.addWidget(self.payment_remaining_label)
        payment_controls.addStretch()

        right_layout.addLayout(payment_controls)

        self.payment_type_group = QButtonGroup(self)

        # ===== DELIVERY SECTION =====
        delivery_layout = QHBoxLayout()
        delivery_name_label = QLabel("Name:")
        delivery_name_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        delivery_layout.addWidget(delivery_name_label)
        self.delivery_name = QLineEdit()
        self.delivery_name.setPlaceholderText("Recipient")
        self.delivery_name.setFixedHeight(40)
        self.delivery_name.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.delivery_name.setStyleSheet("""
            QLineEdit {
                font-size: 16px;
                font-weight: bold;
                padding: 8px;
            }
        """)
        delivery_layout.addWidget(self.delivery_name, 1)
        self.setup_delivery_name_completer()

        right_layout.addLayout(delivery_layout)

        # ===== SUMMARY SECTION =====
        self.summary_widget = CompactSummaryWidget()
        right_layout.addWidget(self.summary_widget)

        # ===== ACTION BUTTONS =====
        action_container = QWidget()
        action_layout = QVBoxLayout(action_container)
        action_layout.setSpacing(8)

        # Save button
        self.save_btn = QPushButton("💾 SAVE SALE")
        self.save_btn.setMinimumHeight(34)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2ecc71, stop:1 #27ae60);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-weight: 600;
                font-size: 14px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #27ae60, stop:1 #2ecc71);
            }
        """)
        self.save_btn.clicked.connect(self.save_sale)


        action_layout.addWidget(self.save_btn)

        right_layout.addWidget(action_container)
        right_layout.addStretch()

        self.right_scroll.setWidget(right_content)

        # Add panels to splitter
        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(self.right_scroll)
        content_splitter.setStretchFactor(0, 2)  # Table gets more space
        content_splitter.setStretchFactor(1, 1)  # Controls get less space
        main_layout.addWidget(content_splitter, 1)
        self.create_payments_table()
        # print("payments_group parent:", self.payments_group.parent())
    
    def auto_fill_remaining_payment(self):
        """If exactly one payment row is empty, fill it with the remaining grand total."""
        grand_total = getattr(self, '_current_grand_total', 0.0)
        if grand_total <= 0:
            return

        empty_rows = []
        total_other = 0.0

        for row in range(self.payments_table.rowCount()):
            amount_edit = self.payments_table.cellWidget(row, 0)
            if not amount_edit or not isinstance(amount_edit, QLineEdit):
                continue
            text = amount_edit.text().strip()
            if not text:
                empty_rows.append(row)
            else:
                try:
                    total_other += float(text.replace(',', ''))
                except ValueError:
                    empty_rows.append(row)

        if len(empty_rows) != 1:
            return

        remaining = round(grand_total - total_other, 2)
        if remaining <= 0:
            return

        target_row = empty_rows[0]
        target_edit = self.payments_table.cellWidget(target_row, 0)
        if target_edit:
            target_edit.blockSignals(True)
            target_edit.setText(f"{remaining:,.2f}")
            target_edit.blockSignals(False)
            self.update_payment_summary()   # ← ADD THIS LINE

    def _on_credit_term_changed(self, index):
        term_data = self.credit_term_combo.itemData(index) if index >= 0 else None
        if term_data == 0:  # Same-day credit
            # Extract the current grand total from the summary widget
            total_text = self.summary_widget.total_value.text().replace("ETB ", "").replace(",", "")
            try:
                total = float(total_text)
                self.same_day_message_input.setText(f"{total:,.2f}")
            except ValueError:
                self.same_day_message_input.clear()
        # If switched to a different term, leave the note as is (user can edit)
    
    def _get_max_cost_price(self, product_id: int) -> float:
        """Return the maximum cost price among all non‑deleted batches of a product."""
        if product_id in self.max_cost_cache:
            return self.max_cost_cache[product_id]
        try:
            with get_session() as session:
                result = session.query(func.max(ProductBatch.cost_price)).filter(
                    ProductBatch.product_id == product_id,
                    ProductBatch.is_deleted == False,
                    ProductBatch.available_quantity > 0
                ).scalar()
            max_cost = float(result) if result else 0.0
        except Exception as e:
            logger.error(f"Failed to get max cost for product {product_id}: {e}")
            max_cost = 0.0
        self.max_cost_cache[product_id] = max_cost
        return max_cost
    
    def open_all_sales_overview(self):
        """Open the All Sales Overview dialog."""
        from ui.pages.sales_card_dialog import AllSalesOverviewDialog
        dialog = AllSalesOverviewDialog(self, self.current_user)
        dialog.edit_sale_requested.connect(self.load_sale_for_edit)
        dialog.setModal(False)
        dialog.show()

    def load_sale_for_edit(self, sale_id: int):
        """Populate the sales form with data from an existing live‑mode sale."""
        try:
            sale = self.sale_service.get_sale_with_items(sale_id)
            if not sale:
                QMessageBox.warning(self, "Error", f"Sale #{sale_id} not found.")
                return

            # 1. Customer
            if sale.customer_id:
                idx = self.customer_combo.findData(sale.customer_id)
                if idx >= 0:
                    self.customer_combo.setCurrentIndex(idx)

            # 2. Delivery name
            self.delivery_name.setText(sale.delivery_name or "")

            # 3. Payment mode & credit term
            is_credit = False
            credit_term_days = None
            if sale.payment_terms:
                for pt in sale.payment_terms:
                    if pt.payment_status in [PaymentStatusEnum.CREDIT, PaymentStatusEnum.PARTIAL]:
                        is_credit = True
                        if pt.due_date and sale.created_at:
                            delta = pt.due_date - sale.created_at.date()
                            credit_term_days = delta.days
                        break

            if is_credit:
                self.credit_radio.setChecked(True)
                self.cash_radio.setChecked(False)
                self.credit_term_combo.setVisible(True)
                self.same_day_message_input.setVisible(True)
                if credit_term_days is not None:
                    idx_term = self.credit_term_combo.findData(credit_term_days)
                    if idx_term < 0:
                        idx_term = 0
                    self.credit_term_combo.setCurrentIndex(idx_term)
                else:
                    self.credit_term_combo.setCurrentIndex(0)
            else:
                self.cash_radio.setChecked(True)
                self.credit_radio.setChecked(False)
                self.credit_term_combo.setVisible(False)
                self.same_day_message_input.setVisible(False)

            # 4. Populate items
            self.sales_table.setRowCount(0)
            self.sales_table.blockSignals(True)

            for item in sale.items:
                if item.is_deleted:
                    continue

                self.add_live_mode_row()                     # creates a new row
                row = self.sales_table.rowCount() - 1

                # Set product combo – BLOCK SIGNALS to avoid auto‑adding a new row
                product = item.batch.product if item.batch else None
                product_id = product.id if product else None
                combo = self.sales_table.cellWidget(row, 0)
                if combo and isinstance(combo, QComboBox) and product_id:
                    found = False
                    combo.blockSignals(True)                  # <-- prevent on_product_selected
                    for i in range(combo.count()):
                        prod = combo.itemData(i)
                        if prod and hasattr(prod, 'id') and prod.id == product_id:
                            combo.setCurrentIndex(i)
                            found = True
                            break
                    if not found and product:
                        display = f"{product.name} (A/V: {product.available_quantity})"
                        combo.addItem(display, product)
                        combo.setCurrentIndex(combo.count() - 1)
                    combo.blockSignals(False)

                # Fill cells
                self.sales_table.item(row, 1).setText(str(item.quantity))
                self.sales_table.item(row, 2).setText(str(item.dozen))
                self.sales_table.item(row, 3).setText(f"{item.unit_price:.2f}")

                # Calculate row total
                self.update_row_total(row)

                # Despatch checkbox
                despatch_widget = self.sales_table.cellWidget(row, 5)
                if despatch_widget:
                    cb = despatch_widget.findChild(QCheckBox)
                    if cb:
                        cb.setChecked(item.for_despatch)

            self.sales_table.blockSignals(False)

            # 5. Labour – preserve original total
            self.update_labour_qty()
            total_qty = float(self.labour_qty.text()) if self.labour_qty.text() else 0.0
            if total_qty > 0:
                rate = sale.labour_expense / total_qty
            else:
                rate = 0.0
            self.labour_rate.setValue(rate)
            self.labour_total.setText(f"{sale.labour_expense:.2f}")

            # 6. Payments table
            self.payments_table.setRowCount(0)
            if not is_credit and sale.payment_terms:
                term = sale.payment_terms[0]
                for pay in term.payment_transactions:
                    if pay.is_deleted:
                        continue
                    self.add_payment_row(amount=pay.amount, bank_account_id=pay.bank_account_id)

            # 7. Sale date 50.0
            if sale.created_at:
                qdate = QDate(sale.created_at.year, sale.created_at.month, sale.created_at.day)
                self.sale_date_edit.setDate(qdate)

            self.editing_sale_id = sale_id

            # 8. Update totals and payments AFTER all rows are present
            self.update_totals()
            self.update_payment_summary()

            # Add exactly one empty row at the bottom for convenience
            self.add_new_row()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load sale for editing: {e}")
            logger.exception("Loading sale for edit failed")

    def _get_today_sold(self, product_id: int) -> float:
        return self.daily_cache.get_today_sold(product_id)

    def _add_to_daily_cache(self, product_id: int, quantity: float):
        self.daily_cache.add_to_daily_cache(product_id, quantity)
    
    def update_same_day_credit_count(self):
        """Fetch the count of unpaid same‑day credits and update the button."""
        try:
            count = self.sale_service.count_unpaid_same_day_credits()
            self.same_day_credit_btn.setText(f"⏱️ Same-day ({count})")
            
            if count > 0:
                self.same_day_credit_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 2px 10px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: #c0392b;
                    }
                """)
            else:
                self.same_day_credit_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e67e22;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 2px 10px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: #d35400;
                    }
                """)
        except Exception as e:
            logger.error(f"Failed to update same-day credit count: {e}")

    def show_unpaid_same_day_credits(self):
        """Open the Credit Sales Overview dialog, pre‑filtered to short‑term unpaid credits."""
        dialog = CreditSalesOverviewDialog(self, self.current_user, filter_short_term_only=True)
        dialog.setModal(False)
        dialog.show()
    
    def on_credit_toggled(self, checked):
        """Show credit term combo only when Credit is selected."""
        self.credit_term_combo.setVisible(checked)
        self.same_day_message_input.setVisible(checked)

    def update_labour_qty(self):
        """Calculate total quantity from all valid product rows (excluding the last empty row)."""
        total_qty = 0
        for row in range(self.sales_table.rowCount()):
            # Skip the last row if it has no product (i.e., empty new row)
            if row == self.sales_table.rowCount() - 1:
                # Check if this last row has any product selected/entered
                if self.is_credit_mode:
                    product_edit = self.sales_table.cellWidget(row, 0)
                    if not product_edit or not product_edit.text().strip():
                        continue  # skip empty last row
                else:
                    combo = self.sales_table.cellWidget(row, 0)
                    if not combo or combo.currentIndex() <= 0:
                        continue  # skip empty last row

            # Get quantity from column 1
            qty_item = self.sales_table.item(row, 1)
            if qty_item:
                try:
                    qty = float(qty_item.text())
                    if qty > 0:
                        total_qty += qty
                except ValueError:
                    pass

        # Update the display (show as integer if whole number, else with decimals)
        if total_qty.is_integer():
            self.labour_qty.setText(str(int(total_qty)))
        else:
            self.labour_qty.setText(f"{total_qty:.2f}")
        
        # Recalculate total
        self.update_labour_total()

    def update_labour_total(self):
        """Update the total labour expense field (qty × rate)."""
        try:
            qty_text = self.labour_qty.text().strip()
            qty = float(qty_text) if qty_text else 0.0
        except ValueError:
            qty = 0.0
        
        rate = self.labour_rate.value()
        total = qty * rate
        
        self.labour_total.setText(f"{total:.2f}")
        # Update the summary totals
        self.update_totals()

    def open_credit_sales_overview(self):
        """Open the Credit Sales Overview dialog."""
        dialog = CreditSalesOverviewDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.show()

    def open_credit_purchases_overview(self):
        """Open the Credit Purchases Overview dialog."""
        dialog = CreditPurchasesOverviewDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.show()
    
    def open_bank_balance_dialog(self):
        """Open the Bank Balance dialog from the dashboard."""
        dialog = BankBalanceDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.show()
    
    def setup_delivery_name_completer(self):
        """Set up autocomplete for delivery name field"""
        # Create completer
        self.delivery_completer = QCompleter()
        self.delivery_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.delivery_completer.setFilterMode(Qt.MatchContains)  # Match anywhere in the string
        self.delivery_completer.setMaxVisibleItems(15)
        self.delivery_completer.activated.connect(self._on_completer_activated)

        self.delivery_completer.popup().setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.delivery_completer.popup().setStyleSheet("""
            QListView {
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
            }
            QListView::item {
                padding: 10px;
                margin: 2px;
                min-height: 40px;
                border-bottom: 1px solid #e5e7eb;
            }
        """)
        
        # Set up the model for the completer
        self.update_delivery_completer_model()
        
        # Connect text changed signal for dynamic updates
        self.delivery_name.textChanged.connect(self.on_delivery_name_changed)
        
        # Set the completer to the line edit
        self.delivery_name.setCompleter(self.delivery_completer)
    
    def _on_completer_activated(self, text):
        """Ensure the selected item is visible when activated"""
        pass

    def update_delivery_completer_model(self, filter_text: str = ""):
        """Update the completer's model with delivery names from the database"""
        from PySide6.QtCore import QStringListModel # type: ignore
        
        try:
            # Get unique delivery names from the service
            names = self.sale_service.get_delivery_names_with_frequency(filter_text)
            
            # Create and set the model
            model = QStringListModel(names)
            self.delivery_completer.setModel(model)
        except Exception as e:
            logger.error(f"Failed to load delivery names for completer: {e}")

    def on_delivery_name_changed(self, text: str):
        """Handle delivery name text changes to update completer suggestions"""
        # Only update if we have at least 2 characters to avoid too many DB queries
        if len(text.strip()) >= 2:
            self.update_delivery_completer_model(text)
    
    def add_expense(self):
        dlg = ExpenseDialog(self, read_only=False)
        dlg.exec()
    
    def open_transfer_dialog(self):
        dlg = BankTransferDialog(self)
        if dlg.exec():
            pass

    def create_payments_table(self):
        """Initialize payments table structure load_customers despatch_check save_sale"""
        self.payments_table.setRowCount(0)
        # Add one empty row by default
        total_text = self.summary_widget.total_value.text().replace("ETB ", "").replace(",", "")
        try:
            amount = float(total_text)
        except:
            amount = 0.0
        self.add_payment_row(amount)
    
    def add_payment_row(self, amount=0.0, bank_account_id=None, payment_method=None):
        """Add a new row to payments table"""
        row = self.payments_table.rowCount()
        self.payments_table.insertRow(row)

        # ----- Amount column -----
        amount_edit = NumberLineEdit()
        amount_edit.setPlaceholderText("0.00")
        amount_edit.setAlignment(Qt.AlignRight)
        amount_edit.setFont(QFont("Segoe UI", 13))

        validator = QDoubleValidator(0.01, 99999999.99, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        amount_edit.setValidator(validator)

        if amount > 0:
            amount_edit.setText(f"{amount:,.2f}")
        amount_edit.textChanged.connect(self.update_payment_summary)
        amount_edit.editingFinished.connect(self.auto_fill_remaining_payment)
        self.payments_table.setCellWidget(row, 0, amount_edit)

        # ----- Bank account column -----
        bank_combo = QComboBox()
        bank_combo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        bank_combo.setStyleSheet("""
            QComboBox {
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        bank_combo.addItem("Select Bank", None)
        accounts = self.bank_account_service.get_all()  # or get_active()

        # Priority order: 14, 17, 16, 15, 12, 13
        priority_ids = [14, 17, 16, 15, 12, 13]
        account_map = {acc.id: acc for acc in accounts}

        # Add priority accounts in exact order (only those that exist)
        for pid in priority_ids:
            if pid in account_map:
                acc = account_map.pop(pid)
                display = f"{acc.bank_name} - {acc.account_name}"
                if acc.account_number:
                    display += f" ({acc.account_number})"
                bank_combo.addItem(display, acc.id)

        # Add remaining accounts (non‑priority) at the end
        for acc in account_map.values():
            display = f"{acc.bank_name} - {acc.account_name}"
            if acc.account_number:
                display += f" ({acc.account_number})"
            bank_combo.addItem(display, acc.id)

        # ---------- FIXED SELECTION LOGIC ----------
        if bank_account_id is not None:
            # Try to select the given bank account ID
            idx = bank_combo.findData(bank_account_id)
            if idx >= 0:
                bank_combo.setCurrentIndex(idx)
            else:
                # Fallback to default priority account 14 if available
                idx = bank_combo.findData(14)
                if idx >= 0:
                    bank_combo.setCurrentIndex(idx)
                else:
                    # If 14 not present, keep "Select Bank" (index 0)
                    bank_combo.setCurrentIndex(0)
        else:
            # No specific ID – use default priority account 14 if it exists
            idx = bank_combo.findData(14)
            if idx >= 0:
                bank_combo.setCurrentIndex(idx)
            else:
                bank_combo.setCurrentIndex(0)
        # ------------------------------------------

        bank_combo.currentIndexChanged.connect(lambda idx, r=row: self.on_payment_bank_changed(r, idx))
        self.payments_table.setCellWidget(row, 1, bank_combo)

        # ----- Delete button -----
        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(30, 30)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #dc2626;
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fecaca;
            }
        """)
        delete_btn.clicked.connect(lambda checked, r=row: self.remove_payment_row(r))
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.addWidget(delete_btn)
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        self.payments_table.setCellWidget(row, 2, btn_widget)

        self.update_payment_summary()

    def remove_payment_row(self, row):
        if self.payments_table.rowCount() > 1:
            self.payments_table.removeRow(row)
        else:
 
            amount_edit = self.payments_table.cellWidget(0, 0)
            if amount_edit:
                amount_edit.clear()  # set text to empty
            bank_combo = self.payments_table.cellWidget(0, 1)
            if bank_combo:
                bank_combo.setCurrentIndex(0)
        self.update_payment_summary()
        self.auto_fill_remaining_payment()

    def update_payment_summary(self):
        """Calculate total payments and remaining amount Amount(ETB)"""
        total_payments = 0.0
        for row in range(self.payments_table.rowCount()):
            amount_edit = self.payments_table.cellWidget(row, 0)
            if amount_edit and isinstance(amount_edit, QLineEdit):
                text = amount_edit.text().strip()
                if text:
                    try:
                        # Strip commas before converting to float
                        total_payments += float(text.replace(',', ''))
                    except ValueError:
                        pass  # ignore invalid entries
        # Get current sale total from summary widget
        total_text = self.summary_widget.total_value.text().replace("ETB ", "").replace(",", "")
        try:
            sale_total = float(total_text)
        except:
            sale_total = 0.0

        remaining = sale_total - total_payments
        
        # Format with commas using system locale
        self.payment_total_label.setText(f"Total: ETB {total_payments:,.2f}")
        self.payment_remaining_label.setText(f"{remaining:,.2f} ETB :Remaining")

    def on_mode_changed(self, checked):
        """Handle mode toggle change"""
        if checked:
            self.mode_toggle.setText("🟣 Credit Mode")
            self.set_credit_mode(True)
        else:
            self.mode_toggle.setText("🔴 Live Mode")
            self.set_credit_mode(False)
    
    def set_credit_mode(self, is_credit_mode):
        self.is_credit_mode = is_credit_mode
        if is_credit_mode:
            self.credit_radio.setChecked(True)
            self.cash_radio.hide()
            self.payments_table.hide()
            self.labour_expense_input.hide()
            self.delivery_name.hide()
            # self.delivery_phone.hide()
            # self.delivery_place.hide()
            # self.delivery_plate.hide()
        else:
            self.cash_radio.show()
            self.cash_radio.setChecked(True)
            self.payments_table.show()
            self.labour_expense_input.show()
            self.delivery_name.show()
            # self.delivery_phone.show()
            # self.delivery_place.show()
            # self.delivery_plate.show()
        self.refresh_table_for_mode()
    
    def refresh_table_for_mode(self):
        """Recreate table rows with appropriate widgets for current mode on_payment_type_changed"""

        rows_data = []
        for row in range(self.sales_table.rowCount()):
            row_data = {}

            if self.is_credit_mode:
                product_edit = self.sales_table.cellWidget(row, 0)
                if product_edit and isinstance(product_edit, QLineEdit):
                    row_data['product'] = product_edit.text()
            else:
                combo = self.sales_table.cellWidget(row, 0)
                if combo and isinstance(combo, QComboBox) and combo.currentIndex() > 0:
                    row_data['product'] = combo.currentData()
                else:
                    row_data['product'] = None

            row_data['quantity'] = self.sales_table.item(row, 1).text() if self.sales_table.item(row, 1) else "1"
            row_data['dozen'] = self.sales_table.item(row, 2).text() if self.sales_table.item(row, 2) else "1"
            row_data['price'] = self.sales_table.item(row, 3).text() if self.sales_table.item(row, 3) else "0.00"
            
     
            despatch_widget = self.sales_table.cellWidget(row, 5)
            if despatch_widget:
                checkbox = despatch_widget.findChild(QCheckBox)
                row_data['for_despatch'] = checkbox.isChecked() if checkbox else False
            else:
                row_data['for_despatch'] = False
            
            rows_data.append(row_data)
        
        self.sales_table.blockSignals(True)

     
        self.sales_table.setRowCount(0)
       

        for i, data in enumerate(rows_data):
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)
            
            if self.is_credit_mode:
                self.add_credit_mode_row(row, data)
            else:
                self.add_live_mode_row(row, data)
        

        if self.sales_table.rowCount() == 0:
            if self.is_credit_mode:
                self.add_credit_mode_row(0, None)
            else:
                self.add_live_mode_row(0, None)
        
    
        self.sales_table.blockSignals(False)
        

        self.update_totals()
        self.update_labour_qty()
    
    def add_live_mode_row(self, row=None, data=None):
        """Add a row for live mode (with product combobox) load"""
        if row is None:
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)
        
    
        product_combo = QComboBox()
        product_combo.setEditable(True)
        product_combo.setInsertPolicy(QComboBox.NoInsert)
        product_combo.setFixedHeight(42)
        product_combo.setFont(QFont("Segoe UI", 16, QFont.Bold)) 
        product_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 3px;
                padding: 6px 10px;
                font-size: 16px;
                font-weight: bold;
                background-color: white;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #6b7280;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #d1d5db;
                background-color: white;
                selection-background-color: #e3f2fd;
                font-size: 16px;
                font-weight: bold;
                padding: 6px;
            }
        """)
        
        self.load_products_combo(product_combo, "")
        if data and data.get('product'):
            
            product_combo.blockSignals(True)
            index = product_combo.findData(data['product'])
            if index >= 0:
                product_combo.setCurrentIndex(index)
            product_combo.blockSignals(False)
        
        product_combo.currentIndexChanged.connect(
            lambda index, combo=product_combo: self.on_product_selected(combo, index)
        )
        self.sales_table.setCellWidget(row, 0, product_combo)
        
   
        self.add_common_row_columns(row, data)
    
    def add_credit_mode_row(self, row=None, data=None):
        """Add a row for credit mode (with text input for product name)"""
        if row is None:
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)
        

        product_edit = QLineEdit()
        product_edit.setPlaceholderText("Enter product name")
        product_edit.setFixedHeight(42)
        product_edit.setFont(QFont("Segoe UI", 15))
        product_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 15px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #8e44ad;
            }
        """)
        
        if data and data.get('product'):
           
            if isinstance(data['product'], str):
                product_edit.setText(data['product'])
            elif hasattr(data['product'], 'name'):
                product_edit.setText(data['product'].name)
        
        self.sales_table.setCellWidget(row, 0, product_edit)
        

        self.add_common_row_columns(row, data)
    
    def add_common_row_columns(self, row, data=None):
        """Add the common columns (Qty, Dozen, Price, Total, Despatch, Delete)"""
    
        qty_value = "1"
        if data and data.get('quantity'):
            qty_value = data['quantity']
        qty_item = QTableWidgetItem(qty_value)
        qty_item.setTextAlignment(Qt.AlignCenter)
        qty_item.setFlags(qty_item.flags() | Qt.ItemIsEditable)
        qty_item.setFont(QFont("Segoe UI", 15))
        self.sales_table.setItem(row, 1, qty_item)
        
        # Dozen
        dozen_value = "1"
        if data and data.get('dozen'):
            dozen_value = data['dozen']
        dozen_item = QTableWidgetItem(dozen_value)
        dozen_item.setTextAlignment(Qt.AlignCenter)
        if self.is_credit_mode:
            dozen_item.setFlags(dozen_item.flags() | Qt.ItemIsEditable)
        else:
            dozen_item.setFlags(dozen_item.flags() & ~Qt.ItemIsEditable)
        dozen_item.setForeground(QColor("#ffffff"))
        dozen_item.setFont(QFont("Segoe UI", 15))
        self.sales_table.setItem(row, 2, dozen_item)
        
        # Price
        price_value = "0.00"
        if data and data.get('price'):
            price_value = data['price']
        price_item = QTableWidgetItem(price_value)
        price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        price_item.setForeground(QColor("#ffffff"))
        price_item.setFont(QFont("Segoe UI", 15))
        self.sales_table.setItem(row, 3, price_item)
        
        # Total
        total_item = QTableWidgetItem("0.00")
        total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
        total_item.setForeground(QColor("#ffffff"))
        total_item.setFont(QFont("Segoe UI", 15))
        self.sales_table.setItem(row, 4, total_item)
        
        # Despatch checkbox
        # Despatch checkbox
        despatch_check = QCheckBox()
        despatch_check.setFont(QFont("Segoe UI", 15))
        despatch_check.setStyleSheet("""
            QCheckBox {
                spacing: 0px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
                border-radius: 4px;
                background-color: #e74c3c;
                border: 2px solid #c0392b;
            }
            QCheckBox::indicator:unchecked {
                background-color: #e74c3c;
                border: 2px solid #c0392b;
            }
            QCheckBox::indicator:checked {
                background-color: #2ecc71;
                border: 2px solid #27ae60;
            }
        """)
        despatch_check.setChecked(True)
        if data and data.get('for_despatch'):
            despatch_check.setChecked(True)
        
        checkbox_widget = QWidget()
        checkbox_layout = QHBoxLayout(checkbox_widget)
        checkbox_layout.addWidget(despatch_check)
        checkbox_layout.setAlignment(Qt.AlignCenter)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.sales_table.setCellWidget(row, 5, checkbox_widget)
        
        # Delete button
        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(40, 40)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFont(QFont("Segoe UI", 15, QFont.Bold))
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #dc2626;
                border: none;
                border-radius: 3px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fecaca;
            }
        """)
        delete_btn.clicked.connect(self.remove_row)
        
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.addWidget(delete_btn)
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        self.sales_table.setCellWidget(row, 6, btn_widget)
        
    
        if data and data.get('price') and data['price'] != "0.00":
            self.update_row_total(row)
    

    def on_payment_type_changed(self, checked):
        """Handle payment type change"""
        if not self.is_credit_mode:
            self.payments_table.setVisible(checked)
            self.add_payment_btn.setVisible(checked)
            self.payment_total_label.setVisible(checked)
            self.payment_remaining_label.setVisible(checked)
    
    def create_excel_table(self):
        """Create Excel-like table for quick sales (7 columns) new_sale"""
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "PRODUCT", 
            "QTY", 
            "DOZEN", 
            "PRICE", 
            "TOTAL", 
            "DESPATCH",
            ""
        ])
        

        header = table.horizontalHeader()
        header.setFont(QFont("Segoe UI", 5, QFont.Bold))
        table.verticalHeader().setVisible(True)
        table.verticalHeader().setDefaultSectionSize(65)
        table.verticalHeader().setMinimumSectionSize(50)
        table.verticalHeader().setFont(QFont("Segoe UI", 5))
        header.setMinimumSectionSize(50)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        # header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        table.setColumnWidth(5, 10)
        table.setColumnWidth(6, 50)
        table.setColumnWidth(1, 60)    # Quantity
        table.setColumnWidth(2, 40)    # Dozen
        table.setColumnWidth(3, 80)    # Unit Price
        table.setColumnWidth(4, 90)    # Total
        
        # Table styling
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QTableWidget.SelectItems)
        table.setSelectionMode(QTableWidget.SingleSelection)
        
        # Set smaller font and row height
        table.setFont(QFont("Segoe UI", 15))
        table.verticalHeader().setDefaultSectionSize(65) 
        
        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: white;  /* Table background is white */
                gridline-color: #cbd5e1;
            }
            QTableWidget::item {
                padding: 8px 6px;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                background-color: #7a9fcf;  /* All row cells are light blue */
            }
            QTableWidget::item:selected {
                background-color: #90caf9;   /* Slightly darker when selected */
                color: #0c4a6e;
            }
            QTableWidget::item:hover {
                background-color: #b0d4ff;   /* Slightly darker on hover */
            }
            QHeaderView::section {
                background-color: #f1f5f9;
                color: #1e293b;
                padding: 10px 4px;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 2px solid #94a3b8;
                font-weight: 700;
                font-size: 15px;
            }
            QHeaderView::section:last {
                border-right: none;
            }
        """)
                    
        return table
    
    def add_new_row(self):
        """Add a new row based on current mode and focus on it"""
        if self.is_credit_mode:
            self.add_credit_mode_row()
        else:
            self.add_live_mode_row()
        
        # Get the newly added row (last row)
        new_row = self.sales_table.rowCount() - 1
        self.update_labour_qty()
        
        # Set focus to the product widget in the new row
        product_widget = self.sales_table.cellWidget(new_row, 0)
        if product_widget:
            product_widget.setFocus()
            if isinstance(product_widget, QLineEdit):
                product_widget.selectAll()
            elif isinstance(product_widget, QComboBox):
                line_edit = product_widget.lineEdit()
                if line_edit:
                    line_edit.selectAll()
                    line_edit.setFocus()
    
    def remove_row(self):
        """Remove the row containing the clicked delete button"""
        button = self.sender()
        if not button:
            return
        
        # Find the row that contains this button
        for row in range(self.sales_table.rowCount()):
            widget = self.sales_table.cellWidget(row, 6)
            if widget and button in widget.findChildren(QPushButton):
                self.sales_table.removeRow(row)
                self.update_totals()
                self.update_labour_qty()
                # If no rows left, add a new empty row
                if self.sales_table.rowCount() == 0:
                    self.add_new_row()
            # break
    
    def on_product_selected(self, combo, index):
        if index <= 0:
            return
        
        row = -1
        for r in range(self.sales_table.rowCount()):
            if self.sales_table.cellWidget(r, 0) is combo:
                row = r
                break
        if row == -1:
            return
        product = combo.itemData(index)
        if not product:
            return
        price_item = self.sales_table.item(row, 3)
        if price_item:
            price_item.setText(f"{product.selling_price:.2f}")
        dozen_item = self.sales_table.item(row, 2)
        if dozen_item:
            dozen_item.setText(str(product.dozen))
        self.update_row_total(row)

        if row == self.sales_table.rowCount() - 1:
            self.add_new_row()
    
    def on_table_item_changed(self, item):
        """Handle table item changes – price cell turns red when below max cost."""
        col = item.column()
        if col in (1, 2, 3):
            try:
                row = item.row()

                text = item.text().strip()
                if not text:
                    if col == 1: 
                        item.setText("1")
                    elif col == 2:
                        item.setText("1")
                    else:
                        item.setText("0.00")
                else:
                    value = float(text)
                    if value <= 0:
                        if col == 3:
                            item.setText("0.00")
                        else:
                            item.setText("1")
                    else:
                        if col in (1,2) and value.is_integer():
                            item.setText(str(int(value)))
                        else:
                            if col == 3:
                                item.setText(f"{value:.2f}")
                            else:
                                item.setText(str(value))
                    
                    # ---- Price vs Cost visual warning (red text only) ----
                    if col == 3:  # Unit Price column
                        combo = self.sales_table.cellWidget(row, 0)
                        if combo and isinstance(combo, QComboBox) and combo.currentIndex() > 0:
                            product = combo.currentData()
                            if product and hasattr(product, 'id'):
                                max_cost = self._get_max_cost_price(product.id)
                                if max_cost > 0 and value < max_cost:
                                    item.setForeground(QColor("red"))
                                else:
                                    item.setForeground(QColor("black"))
                    # ----------------------------------------------------------

                self.update_row_total(row)
        
            except ValueError:
                if col == 1:
                    item.setText("1")
                elif col == 2:
                    item.setText("1")
                else:
                    item.setText("0.00")
                self.update_row_total(item.row())
    
    def update_row_total(self, row):
        """Update total for a specific row: Total = Quantity × Dozen × Unit Price on_table_item_double_clicked"""
        try:
            qty_item = self.sales_table.item(row, 1)
            dozen_item = self.sales_table.item(row, 2)
            price_item = self.sales_table.item(row, 3)
            total_item = self.sales_table.item(row, 4)
            
            if qty_item and dozen_item and price_item and total_item:
                quantity = float(qty_item.text())
                dozen = float(dozen_item.text())
                unit_price = float(price_item.text())
                
                # Calculate total: Quantity × Dozen × Unit Price
                total = quantity * dozen * unit_price
                
                total_item.setText(f"{total:.2f}")
                
                # Update grand totals
                self.update_totals()
        except (ValueError, AttributeError):
            pass
    
    def filter_product_table(self, text):
        """Filter products in the table (by product name in combobox) - only for live mode"""
        if not self.is_credit_mode:
            for row in range(self.sales_table.rowCount()):
                combo = self.sales_table.cellWidget(row, 0)
                if combo:
                    product_name = combo.currentText().lower()
                    if text.lower() in product_name:
                        self.sales_table.setRowHidden(row, False)
                    else:
                        self.sales_table.setRowHidden(row, True)
    
    def update_totals(self):
        """Update all totals including labour expense, and auto-refresh same-day note if needed."""
        subtotal = 0.0
        item_count = 0

        for row in range(self.sales_table.rowCount()):
            if not self.sales_table.isRowHidden(row):
                try:
                    total_item = self.sales_table.item(row, 4)
                    if total_item:
                        total = float(total_item.text())
                        subtotal += total

                        # Count items with actual products
                        if self.is_credit_mode:
                            product_edit = self.sales_table.cellWidget(row, 0)
                            if product_edit and product_edit.text().strip():
                                item_count += 1
                        else:
                            combo = self.sales_table.cellWidget(row, 0)
                            if combo and combo.currentIndex() > 0:
                                item_count += 1
                except (ValueError, AttributeError):
                    continue

        # Get labour expense
        labour_expense = float(self.labour_total.text()) if self.labour_total.text() else 0.0

        # Calculate grand total
        grand_total = subtotal + labour_expense

        # Update summary widget
        self.summary_widget.update_summary(subtotal, labour_expense, grand_total, item_count)

        # Store grand total for use in update_payment_summary
        self._current_grand_total = grand_total

        # Pass grand total (not subtotal) so payments cover the full amount
        self.update_payment_rows_with_subtotal(grand_total)

        # --- Automatic update of the Same-day note ---
        if (
            self.credit_term_combo.isVisible()
            and self.credit_term_combo.currentData() == 0
        ):
            self.same_day_message_input.setText(f"{grand_total:,.2f}")
    
    def update_payment_rows_with_subtotal(self, subtotal):
        """Update payment rows to reflect current subtotal"""
        if self.is_credit_mode or self.payments_table.rowCount() == 0:
            return
        
        # Calculate total of all payment rows except first
        other_payments_total = 0.0
        for row in range(1, self.payments_table.rowCount()):
            amount_edit = self.payments_table.cellWidget(row, 0)
            if amount_edit and isinstance(amount_edit, QLineEdit):
                text = amount_edit.text().strip()
                if text:
                    try:
                        other_payments_total += float(text.replace(',', ''))
                    except ValueError:
                        pass
        
        # Update first row to be subtotal minus other payments
        first_row_amount = max(0, subtotal - other_payments_total)
        
        # Update first payment row
        first_row_amount_edit = self.payments_table.cellWidget(0, 0)
        if first_row_amount_edit and isinstance(first_row_amount_edit, QLineEdit):
            # Block signals temporarily to avoid recursive updates
            first_row_amount_edit.blockSignals(True)
            first_row_amount_edit.setText(f"{first_row_amount:,.2f}")
            first_row_amount_edit.blockSignals(False)
        
        # Update the payment summary
        self.update_payment_summary()

    def load_customers(self):
        """Load customers from service open_add_customer_dialog"""
        try:
            self.customers = self.customer_service.get_all()
            self.customer_combo.clear()

            walking_customer = self.customer_service.get_by_name("walking customer")
            if walking_customer:
                display = walking_customer.name
                if walking_customer.phone:
                    display += f" - {walking_customer.phone}"
                self.customer_combo.addItem(display, walking_customer.id)
            else:
                self.customer_combo.addItem("Select Customer", None)
           
            for customer in self.customers:
                if walking_customer and customer.id == walking_customer.id:
                    continue
                display = customer.name
                if customer.phone:
                    display += f" - {customer.phone}"
                self.customer_combo.addItem(display, customer.id)
            completer = self.customer_combo.completer()
            if completer:
                completer.setCompletionMode(QCompleter.PopupCompletion)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                # Match anywhere in the text (Qt 5.2+)
                if hasattr(completer, 'setFilterMode'):
                    completer.setFilterMode(Qt.MatchContains)
                
                completer.popup().setFont(QFont("Segoe UI", 14, QFont.Bold))
                completer.popup().setStyleSheet("""
                    QListView {
                        font-size: 14px;
                        font-weight: bold;
                        padding: 8px;
                        min-height: 30px;
                    }
                    QListView::item {
                        padding: 8px;
                        min-height: 35px;
                    }
                """)
        except Exception as e:
            logger.error(f"Failed to load customers: {e}")
            self.customer_combo.clear()
            self.customer_combo.addItem("Select Customer", None)
    
    def open_add_customer_dialog(self):
        current_text = self.customer_combo.currentText().strip()
        index = self.customer_combo.currentIndex()
        item_text = self.customer_combo.itemText(index)
        current_id = self.customer_combo.itemData(index)

        customer = None

        if current_id is not None and current_text == item_text:
            customer = self.customer_service.get_by_id(current_id)

        dialog = AddCustomerDialog(self, customer=customer)

        # Prefill for new customer
        if not customer and current_text and current_text != "Select Customer":
            dialog.name_input.setText(current_text)

        result = dialog.exec()

        if result == QDialog.Accepted:
            data = dialog.get_customer_data()

            if customer:
                updated = self.customer_service.update(customer.id, data)
                if updated:
                    self.refresh_customer_combo(select_id=customer.id)
                    # QMessageBox.information(self, "Success", "Customer updated.")
            else:
                new_customer = self.customer_service.create(data)
                if new_customer:
                    self.refresh_customer_combo(select_id=new_customer.id)
                    # QMessageBox.information(self, "Success", "Customer added.")
        
        elif result == 2:
            self.refresh_customer_combo()
    
    def refresh_customer_combo(self, select_id=None):
        """Reload customers and optionally select one by ID."""
        self.load_customers()  # This clears and repopulates
        if select_id:
            index = self.customer_combo.findData(select_id)
            if index >= 0:
                self.customer_combo.setCurrentIndex(index)
    
    def clear_all_rows(self):
        """Clear all rows from the table on_payment_type_changed walking customer"""
        reply = QMessageBox.question(
            self,
            "Clear All Rows",
            "Are you sure you want to clear all rows?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._warned_rows.clear()
            self.sales_table.setRowCount(0)
            self.editing_sale_id = None  
            self.add_new_row()  # Add one empty row
            self.labour_rate.setValue(70)
            self.update_labour_qty()
            self.update_totals()
            self.reset_payments()
            self.delivery_name.clear()
            current_qdate = QDate.currentDate()
            self.sale_date_edit.blockSignals(True)
            self.sale_date_edit.setDate(current_qdate)
            self.sale_date_edit.blockSignals(False)
            self.editing_sale_id = None
            self.send_telegram_checkbox.setChecked(True)
    
    def new_sale(self):
        self.editing_sale_id = None
        self._warned_rows.clear()
        self.sales_table.setRowCount(0)
        self.reset_payments()                      # clear payments table
        self.customer_combo.setCurrentIndex(0)
        self.labour_rate.setValue(70)
        self.update_labour_qty()  # will recalc total
        self.cash_radio.setChecked(True)
        self.delivery_name.clear()
        self.same_day_message_input.clear()
        self.admin_detail_checkbox.setChecked(False)
        self.send_telegram_checkbox.setChecked(True)

        current_qdate = QDate.currentDate()
        if self.temp_sale_date and self.temp_date_timestamp:
            elapsed = time.time() - self.temp_date_timestamp
            if elapsed < self.date_expiry_seconds:
                use_date = self.temp_sale_date
            else:
                use_date = current_qdate
                self._clear_temp_date()
        else:
            use_date = current_qdate

        self.sale_date_edit.blockSignals(True)
        self.sale_date_edit.setDate(use_date)
        self.sale_date_edit.blockSignals(False)
        self.update_delivery_completer_model()
        self.add_new_row()
        self.update_totals()

        self.right_scroll.verticalScrollBar().setValue(0)

        if self.sales_table.rowCount() > 0:
            product_widget = self.sales_table.cellWidget(0, 0)
            if product_widget:
                product_widget.setFocus()
                if isinstance(product_widget, QLineEdit):
                    product_widget.selectAll()
                elif isinstance(product_widget, QComboBox):
                    line_edit = product_widget.lineEdit()
                    if line_edit:
                        line_edit.selectAll()
    
    def _on_sale_date_manually_changed(self, qdate):
        """Handle manual date change by user."""
        # Store the new date and timestamp
        self.temp_sale_date = qdate
        self.temp_date_timestamp = time.time()

        # Restart the expiry timer
        self.date_expiry_timer.stop()
        self.date_expiry_timer.start(self.date_expiry_seconds * 1000)
    
    def _reset_date_if_expired(self):
        """Called when timer expires: reset date to today and clear temp."""
        if self.temp_date_timestamp:
            elapsed = time.time() - self.temp_date_timestamp
            if elapsed >= self.date_expiry_seconds:
                # Expired – reset to today
                self.sale_date_edit.blockSignals(True)
                self.sale_date_edit.setDate(QDate.currentDate())
                self.sale_date_edit.blockSignals(False)
                self._clear_temp_date()

    def _clear_temp_date(self):
        """Clear temporary date data."""
        self.temp_sale_date = None
        self.temp_date_timestamp = None
        self.date_expiry_timer.stop()
    
    def reset_payments(self):
        self.payments_table.setRowCount(0)
        self.add_payment_row()
        self.update_payment_summary()
    
    def save_sale(self):
        """Save the current sale - handles both live and credit modes"""
        # ----- GUARD AGAINST DOUBLE SUBMISSION -----
        if getattr(self, '_saving_in_progress', False):
            return
        self._saving_in_progress = True
        self.save_btn.setEnabled(False)
        # -------------------------------------------

        try:
            # Common validations
            send_telegram = self.send_telegram_checkbox.isChecked()
            customer_id = self.customer_combo.currentData()
            if not customer_id:
                QMessageBox.warning(self, "Validation", "Please select a customer!")
                return

            typed_text = self.customer_combo.currentText().strip()
            selected_index = self.customer_combo.currentIndex()
            selected_text = self.customer_combo.itemText(selected_index) if selected_index >= 0 else ""

            if typed_text and typed_text != selected_text:
                reply = QMessageBox.warning(
                    self,
                    "Unknown Customer",
                    f"'{typed_text}' is not in the customer list.\n\n"
                    "Would you like to add this customer first?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self.open_add_customer_dialog()
                return

            user_id = self._get_user_id()
            if not user_id:
                QMessageBox.warning(self, "Error", "User not identified. Please log in again.")
                return

            is_update = False
            original_sale_id = None
            if self.editing_sale_id is not None:
                reply = QMessageBox.question(
                    self, "Confirm Edit",
                    "Do you want to update this sale?\n\n"
                    "The original sale will be permanently deleted and a new sale will be created with your changes.",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
                original_sale_id = self.editing_sale_id
                if not self.sale_service.delete_sale_cascade(self.editing_sale_id, user_id, send_notification=send_telegram):
                    QMessageBox.critical(self, "Error", "Failed to delete the original sale. Edit aborted.")
                    return
                is_update = True
                self.editing_sale_id = None

            credit_term_days = None
            if self.credit_radio.isChecked():
                credit_term_days = self.credit_term_combo.currentData()

            items = []

            if self.is_credit_mode:
                # Credit mode: use product name text
                for row in range(self.sales_table.rowCount()):
                    product_edit = self.sales_table.cellWidget(row, 0)
                    if not product_edit or not isinstance(product_edit, QLineEdit):
                        continue
                    product_name = product_edit.text().strip()
                    if not product_name:
                        continue

                    try:
                        quantity = float(self.sales_table.item(row, 1).text())
                        dozen = float(self.sales_table.item(row, 2).text())
                        unit_price = float(self.sales_table.item(row, 3).text())
                    except (ValueError, TypeError):
                        continue

                    if quantity <= 0 or unit_price <= 0:
                        continue

                    for_despatch = self.sales_table.cellWidget(row, 5).findChild(QCheckBox).isChecked()

                    items.append({
                        'product_name': product_name,
                        'quantity': quantity,
                        'dozen': dozen,
                        'unit_price': unit_price,
                        'for_despatch': for_despatch
                    })
            else:
                # Live mode: allocate across batches
                pending_allocations = {}

                for row in range(self.sales_table.rowCount()):
                    combo = self.sales_table.cellWidget(row, 0)
                    if not combo or not isinstance(combo, QComboBox):
                        continue

                    line_edit = combo.lineEdit()
                    if line_edit:
                        visible_text = line_edit.text().strip()
                        if not visible_text:
                            continue
                    else:
                        if not combo.currentText().strip():
                            continue

                    if combo.currentIndex() <= 0:
                        continue

                    product = combo.currentData()
                    if not product or not hasattr(product, 'id') or product.id is None:
                        continue

                    try:
                        quantity = float(self.sales_table.item(row, 1).text())
                        dozen = float(self.sales_table.item(row, 2).text())
                        unit_price = float(self.sales_table.item(row, 3).text())
                    except (ValueError, TypeError):
                        continue

                    if quantity <= 0 or unit_price <= 0:
                        continue

                    for_despatch = self.sales_table.cellWidget(row, 5).findChild(QCheckBox).isChecked()

                    # Allocate across batches, accounting for pending allocations in this sale
                    allocations = self.product_service.allocate_batches(
                        product.id,
                        quantity,
                        pending_allocations=pending_allocations
                    )
                    if not allocations:
                        QMessageBox.warning(
                            self,
                            "Stock Error",
                            f"Insufficient stock for '{product.name}'.\n"
                            f"Available: {product.available_quantity}, Requested: {quantity}"
                        )
                        return   # stop the entire sale

                    for batch, allocated_qty in allocations:
                        # Update pending allocations so next rows see reduced availability
                        pending_allocations[batch.id] = pending_allocations.get(batch.id, 0) + allocated_qty

                        items.append({
                            'batch_id': batch.id,
                            'product_id': product.id,
                            'quantity': allocated_qty,
                            'dozen': dozen,
                            'unit_price': unit_price,
                            'for_despatch': for_despatch,
                            'product_name': product.name
                        })

            consolidated = {}
            for item in items:
                # For credit mode, use product_name as part of the key
                if 'batch_id' in item:
                    key = (item['batch_id'], item['unit_price'], item['dozen'], item['for_despatch'])
                else:
                    key = (item['product_name'], item['unit_price'], item['dozen'], item['for_despatch'])

                if key in consolidated:
                    consolidated[key]['quantity'] += item['quantity']
                else:
                    consolidated[key] = item.copy()
            items = list(consolidated.values())
            # ================================================================

            if not items:
                QMessageBox.warning(self, "Validation", "Please add at least one product!")
                return

            # Get common data
            labour_expense = float(self.labour_total.text()) if self.labour_total.text() else 0.0
            delivery_name = self.delivery_name.text().strip()
            if not delivery_name:
                QMessageBox.warning(self, "Validation", "Please add delivery information!")
                return

            delivery_phone = None
            delivery_place = None
            delivery_plate = None

            if self.is_credit_mode:
                self.save_credit_sale(
                    customer_id=customer_id,
                    user_id=user_id,
                    labour_expense=labour_expense,
                    items=items,
                    delivery_name=delivery_name,
                    delivery_phone=delivery_phone,
                    delivery_place=delivery_place,
                    delivery_plate=delivery_plate
                )
            else:
                # Live mode - with payment type and bank
                product_qty_in_sale = {}
                for item in items:
                    if 'product_id' in item:
                        pid = item['product_id']
                        product_qty_in_sale[pid] = product_qty_in_sale.get(pid, 0) + item['quantity']

                flagged = []
                for product_id, qty_sale in product_qty_in_sale.items():
                    today_so_far = self._get_today_sold(product_id)
                    proposed_total = today_so_far + qty_sale
                    if UnusualSalesAlertService.should_alert(product_id, proposed_total):
                        # Get threshold for display (won't be None because should_alert passed)
                        threshold = UnusualSalesAlertService.get_daily_threshold(product_id)
                        product = self.product_service.get_by_id(product_id)
                        flagged.append({
                            'product_name': product.name if product else f"ID {product_id}",
                            'proposed_total': proposed_total,
                            'threshold': threshold,
                            'today_so_far': today_so_far,
                            'sale_qty': qty_sale
                        })

                if flagged:
                    # Play custom sound alert
                    sound_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "ezyZip.wav")
                    try:
                        sound_effect = QSoundEffect()
                        sound_effect.setSource(QUrl.fromLocalFile(sound_path))
                        sound_effect.setVolume(1.0)
                        sound_effect.play()
                    except Exception as e:
                        logger.warning(f"Could not play alert sound: {e}")

                    admin_msg = f"🚨 *Unusual Daily Quantity Alert\n 🚨 ያልተለመደ ዕለታዊ የእቃ ሽያጭ ማስጠንቀቂያ*\n\nCustomer/ደንበኛ: {self.customer_combo.currentText()}\n\n"
                    for f in flagged:
                        admin_msg += f"• {f['product_name']}: {f['proposed_total']:.1f} units today\n\n •  (threshold(ወርሃዊ አማካይ ብዛት): {f['threshold']:.1f})\n"
                    admin_msg += "\nPlease check the cost price.\n እባክዎ የመግዣ ዋጋ ጭማሪ ሊኖር ስለሚችል ያጣሩ!"
                    send_notification_to_admin_sync(admin_msg)

                    max_display = 5
                    if len(flagged) > max_display:
                        display_flagged = flagged[:max_display]
                        extra_count = len(flagged) - max_display
                        extra_line = f"\n... and {extra_count} more item(s).\n"
                    else:
                        display_flagged = flagged
                        extra_line = ""

                    msg = "⚠️ UNUSUAL DAILY QUANTITY ALERT ⚠️\n\n"
                    for f in display_flagged:
                        msg += f"Product: {f['product_name']}\n"
                        msg += f"  Already sold today: {f['today_so_far']:.1f}\n"
                        msg += f"  This sale adds: {f['sale_qty']:.1f}\n"
                        msg += f"  Historical daily threshold: {f['threshold']:.1f}\n\n"
                    msg += extra_line
                    msg += "Please verify the cost price before continuing.\nDo you want to proceed with this sale?"

                    reply = QMessageBox.warning(self, "Cost Price Alert", msg,
                                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply == QMessageBox.No:
                        return

                payment_type = "paid" if self.cash_radio.isChecked() else "credit"
                payments = []

                if payment_type == "paid":
                    for row in range(self.payments_table.rowCount()):
                        amount_edit = self.payments_table.cellWidget(row, 0)
                        bank_combo = self.payments_table.cellWidget(row, 1)
                        if not amount_edit or not bank_combo:
                            continue
                        amount_text = amount_edit.text().strip()
                        if not amount_text:
                            continue
                        try:
                            amount = float(amount_text.replace(',', ''))
                        except ValueError:
                            continue
                        bank_id = bank_combo.currentData()
                        if amount <= 0 or bank_id is None:
                            continue
                        payments.append({
                            'amount': amount,
                            'bank_account_id': bank_id,
                            'payment_method': 'transfer'
                        })

                    if not payments:
                        QMessageBox.warning(self, "Validation", "At least one payment is required for paid sales.")
                        return

                    total_payments = sum(p['amount'] for p in payments)
                    sale_total = float(self.summary_widget.total_value.text().replace("ETB ", "").replace(",", ""))
                    if total_payments > sale_total:
                        QMessageBox.warning(self, "Validation", f"Total payments (ETB {total_payments:,.2f}) exceed sale total (ETB {sale_total:,.2f}).")
                        return

                duplicate = self.sale_service.find_duplicate_sale(
                    customer_id=customer_id,
                    items=items,
                    labour_expense=labour_expense,
                    delivery_name=delivery_name
                )
                if duplicate:
                    reply = QMessageBox.warning(
                        self,
                        "Duplicate Sale Detected",
                        f"A very similar sale was found (ID #{duplicate.id}) on "
                        f"{duplicate.created_at.strftime('%Y-%m-%d %H:%M')}.\n\n"
                        "Do you want to save this sale anyway?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        return

                self.save_live_sale(
                    customer_id=customer_id,
                    user_id=user_id,
                    labour_expense=labour_expense,
                    items=items,
                    payment_type=payment_type,
                    payments=payments,
                    delivery_name=delivery_name,
                    delivery_phone=delivery_phone,
                    delivery_place=delivery_place,
                    delivery_plate=delivery_plate,
                    credit_term_days=credit_term_days,
                    product_qty_in_sale=product_qty_in_sale,
                    original_sale_id=original_sale_id,
                    send_telegram=send_telegram
                )

        finally:
            # ----- RE-ENABLE BUTTON AND CLEAR GUARD -----
            self._saving_in_progress = False
            self.save_btn.setEnabled(True)
            # -------------------------------------------
    
    def save_live_sale(self, customer_id, user_id, labour_expense, items, 
                       payment_type, payments, delivery_name, 
                       delivery_phone, delivery_place, delivery_plate, credit_term_days, product_qty_in_sale=None, original_sale_id=None, send_telegram=True):
        """Save a live sale with inventory impact remove_payment_row"""
        payment_lines = []
        for p in payments:
            bank = self.bank_account_service.get_by_id(p['bank_account_id'])
            bank_name = bank.account_name if bank else "Unknown Bank"
            payment_lines.append(f"  - ETB {p['amount']:,.2f} ({bank_name})")
        payment_details = "<br>".join(payment_lines) if payment_lines else ""

        total_qty = sum(item['quantity'] for item in items)

        selected_qdate = self.sale_date_edit.date()  # Returns QDate in Gregorian
        sale_date = selected_qdate.toPython()


        sale, error = self.sale_service.create_sale(
            customer_id=customer_id,
            user_id=user_id,
            labour_expense=labour_expense,
            sale_items=items,
            payment_type=payment_type,
            credit_term_days=credit_term_days,
            payments=payments,
            delivery_name=delivery_name,
            delivery_place=delivery_place,
            delivery_phone=delivery_phone,
            delivery_plate=delivery_plate,
            sale_date=sale_date
        )
        
        if sale:
            if product_qty_in_sale:
                for pid, qty in product_qty_in_sale.items():
                    self._add_to_daily_cache(pid, qty)
            if send_telegram:
                self._send_order_notification(sale, items, sale_date, original_sale_id=original_sale_id)
            if customer_id:
                notify_customer_sync(customer_id, sale_id=sale.id)
            QApplication.beep()

            if payments:
                affected_accounts = set(p['bank_account_id'] for p in payments if p.get('bank_account_id'))

                if affected_accounts:
                    try:
                        bts = BankTransactionService()
                        with get_session() as session:
                            for acc_id in affected_accounts:
                                bts.recalculate_balances_for_account(session, acc_id)
                        
                        logger.info(f"Recalculated balances after sale edit for accounts: {affected_accounts}")

                    except Exception as e:
                        logger.error(f"Failed to recalculate balances after sale: {e}")
            sale_total = float(self.summary_widget.total_value.text().replace("ETB ", "").replace(",", ""))
            self._send_admin_detail(items, labour_expense, sale_total)
            self.new_sale()
            self.editing_sale_id = None
            self.update_same_day_credit_count()
        else:
            QMessageBox.critical(self, "Error", f"Failed to save sale:\n{error}")
    
    def on_payment_bank_changed(self, row, index):
        """When bank selection changes, maybe auto-set payment method for cash account update_totals"""
        pass
    
    def save_credit_sale(self, customer_id, user_id, labour_expense, items,
                         delivery_name, delivery_phone, delivery_place, delivery_plate):
        """Save a historical credit sale without inventory impact on_table_item_changed"""
        # Calculate total
        total = sum(item['quantity'] * item['dozen'] * item['unit_price'] for item in items) + labour_expense
        
        reply = QMessageBox.question(
            self,
            "Confirm Credit Sale",
            f"<b>Confirm this historical credit sale?</b><br><br>"
            f"Customer: {self.customer_combo.currentText()}<br>"
            f"Payment: CREDIT (historical)<br>"
            f"Items: {len(items)}<br>"
            f"Total: ETB {total:,.2f}<br><br>"
            f"<i>Note: No inventory will be affected.</i>",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return
        
        sale_date = QDate.currentDate().toPython()
        
        # Prepare data for credit sale
        data = {
            'customer_id': customer_id,
            'sale_date': sale_date,
            'reference': None,  # Could add a reference field in UI
            'items': items,
            'labour_expense': labour_expense or 0.0,
            'delivery_name': delivery_name or None,
            'delivery_phone': delivery_phone or None,
            'delivery_place': delivery_place or None,
            'delivery_plate': delivery_plate or None,
            'user_id': user_id
        }
        
        # Call service method
        sale, error = self.sale_service.create_credit_sale(data)
        
        if sale:
            QMessageBox.information(
                self,
                "Credit Sale Saved",
                f"<b>Credit sale #{sale.id} recorded successfully!</b><br><br>"
                f"Total Amount: ETB {sale.total_amount:,.2f}<br>"
                f"<i>No inventory was affected.</i>"
            )
            self.new_sale()
        else:
            QMessageBox.critical(self, "Error", f"Failed to save credit sale:\n{error}")
    
    def load_products_combo(self, combo, search_text=""):
        products = self.product_service.get_available_products(search_text)
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("", None)
        for product in products:
            display_text = f"{product.name} (A/V: {product.available_quantity})"
            combo.addItem(display_text, product)
        combo.blockSignals(False)
        combo.setCurrentIndex(0)

        combo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        combo.setStyleSheet("""
            QComboBox {
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                font-size: 14px;
                font-weight: bold;
                padding: 6px;
            }
        """)

        completer = combo.completer()
        if completer:
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.popup().setFont(QFont("Segoe UI", 14, QFont.Bold))
            completer.popup().setStyleSheet("""
                QListView {
                    font-size: 14px;
                    font-weight: bold;
                    padding: 8px;
                }
                QListView::item {
                    padding: 10px;
                    margin: 2px;
                    min-height: 40px;
                    border-bottom: 1px solid #e5e7eb;
                }
            """)

            if hasattr(completer, 'setFilterMode'):
                completer.setFilterMode(Qt.MatchContains)

    
    def refresh_all_product_combos(self, search_text):
        for row in range(self.sales_table.rowCount()):
            combo = self.sales_table.cellWidget(row, 0)
            if combo and isinstance(combo, QComboBox):
                current_product = combo.currentData() if combo.currentIndex() > 0 else None
                self.load_products_combo(combo, search_text)

                if current_product:
                    index = combo.findData(current_product)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                    else:
                        combo.setCurrentIndex(0)
                        self.clear_row_product_data(row)
                else:
                    combo.setCurrentIndex(0)
    
    def clear_row_product_data(self, row):
        if self.sales_table.item(row, 2):
            self.sales_table.item(row, 2).setText("1")
        if self.sales_table.item(row, 3):
            self.sales_table.item(row, 3).setText("0.00")
        if self.sales_table.item(row, 4):
            self.sales_table.item(row, 4).setText("0.00")
        self.update_totals()
    
    def _get_user_id(self):
        if not self.current_user:
            return None
        if isinstance(self.current_user, dict):
            return self.current_user.get('id')
        elif hasattr(self.current_user, 'id'):
            return self.current_user.id
        return None
    
    def refresh_all_data(self):
        """Refresh all dynamic data while preserving selections. notify_store_team_sync"""
        logger.info("Refreshing all data for SalesManager")
        
        # 1. Check and reset date if expired
        self._reset_date_if_expired()
        
        # 2. Refresh customers
        current_customer_id = self.customer_combo.currentData()
        self.refresh_customer_combo(select_id=current_customer_id)
        
        # 3. Refresh payment table bank combos
        self.refresh_payment_bank_combos()
        
        # 4. Refresh product combos (if live mode)
        if not self.is_credit_mode:
            self.refresh_product_combos()
        
        # 5. Refresh delivery name completer
        self.update_delivery_completer_model("")
    
    def refresh_payment_bank_combos(self):
        """Refresh bank account combos in payment table, preserving selected bank IDs."""
        accounts = self.bank_account_service.get_all()
        if not accounts:
            logger.warning("No bank accounts found for refreshing combos")
            return
        
        # Priority order matching add_payment_row: 3, 6, 5, 1, 2, then the rest
        priority_ids = [14, 17, 16, 15, 12, 13]
        account_map = {acc.id: acc for acc in accounts}
        
        for row in range(self.payments_table.rowCount()):
            bank_combo = self.payments_table.cellWidget(row, 1)
            if not bank_combo or not isinstance(bank_combo, QComboBox):
                continue
            
            current_bank_id = bank_combo.currentData()
            bank_combo.blockSignals(True)
            bank_combo.clear()
            bank_combo.addItem("Select Bank", None)
            
            # Build a copy so we can remove already‑added accounts
            remaining = account_map.copy()
            
            # Add priority accounts in the exact order (only those present)
            for pid in priority_ids:
                if pid in remaining:
                    acc = remaining.pop(pid)
                    display = f"{acc.bank_name} - {acc.account_name}"
                    if acc.account_number:
                        display += f" ({acc.account_number})"
                    bank_combo.addItem(display, acc.id)
            
            # Add all remaining accounts at the end
            for acc in remaining.values():
                display = f"{acc.bank_name} - {acc.account_name}"
                if acc.account_number:
                    display += f" ({acc.account_number})"
                bank_combo.addItem(display, acc.id)
            
            # Restore previous selection, fall back to "Select Bank" if ID no longer exists
            if current_bank_id is not None:
                index = bank_combo.findData(current_bank_id)
                if index >= 0:
                    bank_combo.setCurrentIndex(index)
                else:
                    bank_combo.setCurrentIndex(0)
            else:
                bank_combo.setCurrentIndex(0)
            
            bank_combo.blockSignals(False)
    
    def refresh_product_combos(self):
        """Refresh product combos in sales table, preserving selected product IDs. add_common_row_columns"""
        for row in range(self.sales_table.rowCount()):
            combo = self.sales_table.cellWidget(row, 0)
            if not combo or not isinstance(combo, QComboBox):
                continue
            
            current_product = combo.currentData()
            current_product_id = current_product.id if current_product and hasattr(current_product, 'id') else None
            
            self.load_products_combo(combo, "")
            
            if current_product_id is not None:
                found = False
                for i in range(combo.count()):
                    prod = combo.itemData(i)
                    if prod and hasattr(prod, 'id') and prod.id == current_product_id:
                        combo.setCurrentIndex(i)
                        found = True
                        break
                if not found:
                    # Product no longer available, clear row data
                    combo.setCurrentIndex(0)
                    self.clear_row_product_data(row)
            else:
                combo.setCurrentIndex(0)
    
    def showEvent(self, event):
        super().showEvent(event)
        # Always start with a fresh sale form when switching to this page
        # self.new_sale()
        self.update_same_day_credit_count()
    
    def reset_form(self):
        """Reset the entire sale form to a fresh state (same as new_sale)."""
        self.new_sale()
    
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
    
    def _send_order_notification(self, sale, items, sale_date=None, original_sale_id=None):
        try:
            extra_note = ""
            if self.credit_radio.isChecked() and self.credit_term_combo.currentData() == 0:
                extra_note = self.same_day_message_input.text().strip()
            # Use the passed sale_date directly - it's already a date object from the UI
            if sale_date is None:
                sale_date = date.today()
            
            # 1. Get Ethiopian date and time (using current system time)
            from datetime import datetime
            from ui.components.ethiopian_date import EthiopianDateConverter as EthConv
            
            now = datetime.now()
            eth_year, eth_month, eth_day = EthConv.to_ethiopian(sale_date)
            hour = now.hour
            minute = now.minute
            time_str = f"{hour:02d}:{minute:02d}"
            
            # Ethiopian month names in Amharic (or English, user can decide)
            eth_month_names_am = [
                "መስከረም", "ጥቅምት", "ህዳር", "ታህሳስ", "ጥር", "የካቲት",
                "መጋቢት", "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ"
            ]
            month_name = eth_month_names_am[eth_month - 1] if 1 <= eth_month <= 13 else str(eth_month)
            eth_weekday_num = sale_date.isoweekday()
            eth_weekdays = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሑድ"]
            eth_weekday = eth_weekdays[eth_weekday_num - 1]
            eth_date_str = f"{eth_weekday} {eth_day} {month_name} {eth_year}  {time_str}"
        
            
            # 2. Build message (fast, no I/O)
            delivery_name = self.delivery_name.text().strip()
            delivery_address = self._to_amharic(delivery_name) or "N/A"

            aggregated = {}
            for item in items:
                name = item.get('product_name', 'Unknown')
                qty = item['quantity']
                aggregated[name] = aggregated.get(name, 0) + qty

            product_lines = []
            num = 1
            for name, qty in aggregated.items():
                display_name = self._to_amharic(name)
                qty_display = int(qty) if qty.is_integer() else f"{qty:.1f}"
                product_lines.append(f"{num} = {display_name}\t({name}):\t\tብዛት፡\t{qty_display} ካርቶን")
                num += 1

            products_text = "\n\n".join(product_lines)
            if original_sale_id is not None:
                header = "🔄 <b>የተስተካከለ ትዕዛዝ!</b>"
                update_line = f"📝 <b>Original Sale ID:</b> #{original_sale_id}\n\n"
            else:
                header = "🛒 <b>አዲስ ትዕዛዝ ደርሷል!</b>"
                update_line = f"📝 <b>Sale ID:</b> #{sale.id}\n\n"

            message = (
                f"{header}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📅 <b>የኢትዮጵያ ቀን / ሰዓት</b>\n"
                f"   {eth_date_str}\n\n"
                f"{update_line}"
                f"📦 <b>የታዘዙ እቃዎች</b>\n"
                f"{products_text}"
                f"\n\n📍 <b>አድራሻ</b>\n"
                f"   {delivery_address}({delivery_name})\n\n"
            )
            
            if extra_note:
                message += f"📝 <b>ቀሪ ብር አለው፡</b>\n   {self._to_amharic(extra_note)}({extra_note})\n"
                message += "\n"

            # Check if any item is not for despatch and add a warning note
            not_despatch_items = [item.get('product_name', 'Unknown') for item in items if not item.get('for_despatch', True)]
            if not_despatch_items:
                message += "🚨⚠️🚨 <b>ማስታወሻ:</b> አይወጣም ❌❌❌❌❌\n"
                # for name in not_despatch_items:
                #     message += f"   • {self._to_amharic(name)} ({name})\n"
                
            
            from telegrambot.bot import notify_store_team_sync, is_bot_ready
                
            notify_store_team_sync(message, sale_id=sale.id)

        except Exception as e:
            # Silently swallow any error – never interrupt the sale workflow
            logger.error("❌ Error in _send_order_notification: %s", e, exc_info=True)
    
    def _send_admin_detail(self, items, labour_expense, grand_total):
        """Send a bilingual (Amharic/English) detailed sale summary to the admin."""
        if not self.admin_detail_checkbox.isChecked():
            return

        # Build product lines
        lines = []
        lines.append("📋ዝርዝር ትዕዛዝ / Order Details\n")
        
        for idx, item in enumerate(items, 1):
            name_en = item.get('product_name', 'Unknown')
            name_am = self._to_amharic(name_en)
            qty = int(item.get('quantity', 0))
            dozen = int(item.get('dozen', 1))
            unit_price = item.get('unit_price', 0.0)
            item_total = qty * dozen * unit_price
            
            line = (
                f"{idx}) {name_am} ({name_en})\n"
                f" {qty} ካርቶን X {dozen} x "
                f"  {unit_price:,.2f} = "
                f"  {item_total:,.2f} ETB"
            )
            lines.append(line)
        
        # Labour and grand total
        labour_line = (
            f"\n🛠 የሠራተኛ ወጪ: {labour_expense:,.2f} ETB"
        )
        total_line = (
            f"💰 ጠቅላላ ድምር: {grand_total:,.2f} ETB"
        )
        
        lines.append(labour_line)
        lines.append(total_line)
        
        message = "\n".join(lines)
        
        try:
            from telegrambot.bot import send_notification_to_admin_sync
            send_notification_to_admin_sync(message)
        except Exception as e:
            logger.error("Failed to send admin detail notification: %s", e)