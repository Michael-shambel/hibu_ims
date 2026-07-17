from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QLineEdit, QMessageBox, QApplication, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QDate, QLocale, QTimer
from PySide6.QtGui import QDoubleValidator, QFont
from services.bank_account_service import BankAccountService
from services.new_sale_service import NewSaleService
from services.purchase_service import PurchaseService
from ui.components.ethiopian_date import EthiopianDateEdit
from telegrambot.bot import notify_supplier_purchase_sync, notify_customer_sync
from datetime import date
import logging

logger = logging.getLogger(__name__)


class NumberLineEdit(QLineEdit):
    """Line edit that auto‑formats numbers with thousand‑separator commas."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._formatting = False
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

        try:
            value = float(plain)
        except ValueError:
            self.setText('')
            self._formatting = False
            return

        # Format with commas, preserve decimal part as typed
        if '.' in plain:
            int_part, dec_part = plain.split('.', 1)
        else:
            int_part, dec_part = plain, ''
        
        locale = QLocale.system()
        formatted_int = locale.toString(int(int_part) if int_part else 0)
        
        if dec_part:
            formatted = f"{formatted_int}.{dec_part}"
        else:
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


class CreditPaymentDialog(QDialog):
    def __init__(self, parent, customer_id, customer_name, total_due, current_user, transaction_type='sale'):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.total_due = total_due
        self.current_user = current_user
        self.transaction_type = transaction_type
        self.bank_service = BankAccountService()
        self.sale_service = NewSaleService() if transaction_type == 'sale' else None
        self.purchase_service = PurchaseService() if transaction_type == 'purchase' else None

        self.entity_label = "Customer" if transaction_type == 'sale' else "Supplier"
        self.setWindowTitle(f"Record {self.entity_label} Payment for {customer_name}")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.add_payment_row(self.total_due)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel(f"<b>{self.entity_label}:</b> {self.customer_name}  |  <b>Total Due:</b> ETB {self.total_due:,.2f}")
        header.setStyleSheet("font-size: 16px; padding: 10px; background-color: #f0f0f0; border-radius: 6px;")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        main_layout.addWidget(header)

        # Ethiopian Date Input
        date_row = QHBoxLayout()
        date_label = QLabel("Payment Date (Ethiopian):")
        date_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.eth_date_edit = EthiopianDateEdit()
        self.eth_date_edit.setDate(QDate.currentDate())
        date_row.addWidget(date_label)
        date_row.addWidget(self.eth_date_edit)
        date_row.addStretch()
        main_layout.addLayout(date_row)

        # Table container
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Amount (ETB)", "Bank Account", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(2, 70)

        self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.table.verticalHeader().setDefaultSectionSize(60)
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
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setMinimumHeight(250)

        table_layout.addWidget(self.table)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(table_container)
        scroll.setMinimumHeight(300)
        main_layout.addWidget(scroll, 1)

        # Control row
        control_layout = QHBoxLayout()
        control_layout.setSpacing(15)

        self.add_btn = QPushButton("➕ Add Payment")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setFixedSize(140, 40)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #374151;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.add_btn.clicked.connect(self.add_payment_row)

        self.total_label = QLabel("Total: ETB 0.00")
        self.total_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.total_label.setStyleSheet("font-weight: bold; color: #059669;")

        self.remaining_label = QLabel(f"Remaining: ETB {self.total_due:,.2f}")
        self.remaining_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.remaining_label.setStyleSheet("color: #dc2626;")

        control_layout.addWidget(self.add_btn)
        control_layout.addStretch()
        control_layout.addWidget(self.total_label)
        control_layout.addWidget(self.remaining_label)
        main_layout.addLayout(control_layout)

        # Note field
        note_layout = QHBoxLayout()
        note_label = QLabel("Note (optional):")
        note_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Enter a note for this payment...")
        self.note_edit.setMinimumHeight(40)
        self.note_edit.setStyleSheet("font-size: 14px; padding: 8px;")
        note_layout.addWidget(note_label)
        note_layout.addWidget(self.note_edit)
        main_layout.addLayout(note_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        save_btn = QPushButton("Save Payment")
        save_btn.setFixedSize(140, 45)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        save_btn.clicked.connect(self.save_payment)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(120, 45)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
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
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)
        main_layout.addSpacing(10)

    # --- Table row management ---
    def add_payment_row(self, amount=0.0):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Use NumberLineEdit for comma‑formatted input
        amount_edit = NumberLineEdit()
        amount_edit.setPlaceholderText("0.00")
        amount_edit.setAlignment(Qt.AlignRight)
        amount_edit.setMinimumHeight(40)
        amount_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        validator = QDoubleValidator(0.01, 99999999.99, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        amount_edit.setValidator(validator)
        if amount > 0:
            amount_edit.setText(f"{amount:,.2f}")
        amount_edit.textChanged.connect(self.update_totals)
        self.table.setCellWidget(row, 0, amount_edit)

        # Bank combo with the same priority ordering as SalesManager
        bank_combo = QComboBox()
        bank_combo.setMinimumHeight(40)
        bank_combo.setStyleSheet("font-size: 14px; padding: 5px;")
        bank_combo.addItem("Select Bank", None)

        accounts = self.bank_service.get_all()
        # Priority order matching SalesManager
        priority_ids = [14, 17, 16, 15, 12, 13]
        account_map = {acc.id: acc for acc in accounts}

        # First add priority accounts in the specified order
        for pid in priority_ids:
            if pid in account_map:
                acc = account_map.pop(pid)
                display = f"{acc.bank_name} - {acc.account_name}"
                if acc.account_number:
                    display += f" ({acc.account_number})"
                bank_combo.addItem(display, acc.id)

        # Then add the remaining accounts
        for acc in account_map.values():
            display = f"{acc.bank_name} - {acc.account_name}"
            if acc.account_number:
                display += f" ({acc.account_number})"
            bank_combo.addItem(display, acc.id)

        # Default selection: pick ID 14 if it exists, otherwise fallback to index 1 if only one account
        if 14 in [a.id for a in accounts]:
            idx = bank_combo.findData(14)
            if idx >= 0:
                bank_combo.setCurrentIndex(idx)
        elif len(accounts) == 1:
            bank_combo.setCurrentIndex(1)

        self.table.setCellWidget(row, 1, bank_combo)

        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(40, 40)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #dc2626;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #fecaca; }
        """)
        delete_btn.clicked.connect(lambda: self.remove_payment_row(row))
        self.table.setCellWidget(row, 2, delete_btn)

        self.update_totals()

    def remove_payment_row(self, row):
        if self.table.rowCount() > 1:
            self.table.removeRow(row)
        else:
            amount_edit = self.table.cellWidget(0, 0)
            if amount_edit:
                amount_edit.clear()
            bank_combo = self.table.cellWidget(0, 1)
            if bank_combo:
                bank_combo.setCurrentIndex(0)
        self.update_totals()

    def update_totals(self):
        total = 0.0
        for row in range(self.table.rowCount()):
            amount_edit = self.table.cellWidget(row, 0)
            if amount_edit and isinstance(amount_edit, QLineEdit):
                text = amount_edit.text().strip()
                if text:
                    try:
                        total += float(text.replace(',', ''))
                    except ValueError:
                        pass
        self.total_label.setText(f"Total: ETB {total:,.2f}")
        remaining = self.total_due - total
        self.remaining_label.setText(f"Remaining: ETB {remaining:,.2f}")

    def get_payments(self):
        payments = []
        for row in range(self.table.rowCount()):
            amount_edit = self.table.cellWidget(row, 0)
            bank_combo = self.table.cellWidget(row, 1)
            if not amount_edit or not bank_combo:
                continue
            text = amount_edit.text().strip()
            if not text:
                continue
            try:
                amount = float(text.replace(',', ''))
            except ValueError:
                continue
            if amount <= 0:
                continue
            bank_id = bank_combo.currentData()
            if bank_id is None:
                continue
            payments.append((amount, bank_id))
        return payments

    def save_payment(self):
        payments = self.get_payments()
        note = self.note_edit.text().strip() if self.note_edit else ""

        if not payments:
            QMessageBox.warning(self, "Validation", "Please enter at least one valid payment.")
            return

        total = sum(p[0] for p in payments)
        if total > self.total_due + 0.01:
            QMessageBox.warning(
                self,
                "Validation",
                f"Total payments (ETB {total:,.2f}) exceed the due amount (ETB {self.total_due:,.2f})."
            )
            return

        gregorian_qdate = self.eth_date_edit.date()
        payment_date = date(gregorian_qdate.year(), gregorian_qdate.month(), gregorian_qdate.day())

        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        success = False
        error_msg = ""

        if self.transaction_type == 'sale':
            success = self.sale_service.record_customer_payment(
                self.customer_id, payments, user_id, note, payment_date
            )
            if not success:
                error_msg = "Failed to record sale payment."
        else:
            success, error_msg = self.purchase_service.record_supplier_payment(
                self.customer_id, payments, user_id, note, payment_date
            )

        if success:
            if self.transaction_type == 'sale':
                notify_customer_sync(self.customer_id)
            else:
                notify_supplier_purchase_sync(self.customer_id)
            self.accept()
        else:
            QMessageBox.critical(self, "Payment Failed", error_msg or "Failed to record payment.")
