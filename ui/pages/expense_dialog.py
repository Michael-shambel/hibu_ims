#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QScrollArea,
    QFrame, QLabel, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QSizePolicy, QCheckBox
)
from PySide6.QtCore import Qt, QDate, Signal, QLocale, QTimer
from PySide6.QtGui import QFont, QDoubleValidator
from models.expense import ExpensePaymentMethod
from services.expense_category_service import ExpenseCategoryService
from services.bank_account_service import BankAccountService
from services.expense_service import ExpenseService
from ui.pages.product_dialog import (
    ModernDoubleSpinBox, ModernComboBox, ModernTextEdit, ModernInput
)
from ui.components.ethiopian_date import EthiopianDateEdit


# ---------- NumberLineEdit (comma formatting, no dollar sign) ----------
class NumberLineEdit(QLineEdit):
    """Line edit that auto‑formats numbers with thousand‑separator commas. content"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._formatting = False
        self.textEdited.connect(self._format_text)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def _format_text(self, text):
        if self._formatting:
            return
        self._formatting = True

        plain = text.replace(',', '')
        if plain in ('', '-'):
            self.setText(plain)
            self._formatting = False
            return

        try:
            value = float(plain)
        except ValueError:
            self.setText('')
            self._formatting = False
            return

        if '.' in plain:
            int_part, dec_part = plain.split('.', 1)
        else:
            int_part, dec_part = plain, ''

        locale = QLocale.system()
        formatted_int = locale.toString(int(int_part) if int_part else 0)

        if dec_part:
            formatted = f"{formatted_int}.{dec_part}"
        else:
            formatted = formatted_int if not text.endswith('.') else f"{formatted_int}."

        # Keep cursor position proportional
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


# ---------- Modern Ethiopian Date Edit ----------
class ModernEthiopianDateEdit(ModernInput):
    """Modern Ethiopian date edit with floating label and three spinboxes"""
    dateChanged = Signal(QDate)

    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.create_input_widget()

    def create_input_widget(self):
        self.ethiopian_date = EthiopianDateEdit()
        self.ethiopian_date.dateChanged.connect(self.on_date_changed)
        self.input_container.layout().addWidget(self.ethiopian_date)

    def on_date_changed(self, qdate):
        if self.dateChanged:
            self.dateChanged.emit(qdate)

    def setDate(self, date):
        self.ethiopian_date.setDate(date)

    def date(self):
        return self.ethiopian_date.date()


# ---------- ExpenseDialog ----------
class ExpenseDialog(QDialog):
    def __init__(self, parent=None, expense=None, read_only=False):
        super().__init__(parent)
        self.expense = expense
        self.read_only = read_only
        self.category_service = ExpenseCategoryService()
        self.bank_service = BankAccountService()
        self.expense_service = ExpenseService()

        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setModal(True)
        self.setMinimumSize(800, 600)
        self.setWindowState(Qt.WindowMaximized)

        self.expense_lines = []
        self.is_edit = expense is not None
        self.update_data = None
        self.bank_display_map = {}
        self.category_display_map = {}
        self.init_ui()
        self.load_data()
        if expense:
            self.populate_fields()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #f8f9fa; border: none; }")

        container = QWidget()
        container.setStyleSheet("background-color: #f8f9fa;")
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(30, 20, 30, 20)
        form_layout.setSpacing(15)

        # --- INPUT SECTION ---
        section = QFrame()
        section.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        self.input_section = section  # store reference for later visual feedback
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(25, 20, 25, 20)
        section_layout.setSpacing(12)

        # Row 1: Bank Account & Category (horizontal, equal width)
        bank_cat_row = QHBoxLayout()
        self.bank_combo = ModernComboBox("Bank Account")
        self.bank_combo.setEnabled(True)
        bank_cat_row.addWidget(self.bank_combo, 1)
        self.category_combo = ModernComboBox("Category")
        bank_cat_row.addWidget(self.category_combo, 1)
        section_layout.addLayout(bank_cat_row)

        # Row 2: Notes & Amount (50/50)
        notes_amount_row = QHBoxLayout()
        self.notes_edit = ModernTextEdit("Notes", "Additional details...")
        notes_amount_row.addWidget(self.notes_edit, 1)

        # Amount: tiny label + tall input
        amount_widget = QWidget()
        amount_layout = QVBoxLayout(amount_widget)
        amount_layout.setContentsMargins(0, 0, 0, 0)
        amount_layout.setSpacing(1)

        amount_label = QLabel("Amount")
        amount_label.setFont(QFont("Segoe UI", 9))
        amount_label.setStyleSheet("color: #6b7280; margin: 0px; padding: 0px;")
        amount_layout.addWidget(amount_label)

        self.amount_spin = NumberLineEdit()
        self.amount_spin.setPlaceholderText("0.00")
        self.amount_spin.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.amount_spin.setFont(QFont("Segoe UI", 14))
        self.amount_spin.setMinimumHeight(46)                  # tall input field
        self.amount_spin.setValidator(QDoubleValidator(0.01, 9999999.99, 2))
        self.amount_spin.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
        """)
        amount_layout.addWidget(self.amount_spin)
        notes_amount_row.addWidget(amount_widget, 1)

        section_layout.addLayout(notes_amount_row)

        # Row 3: Date & Add to List button – equal width (50/50)
        date_btn_row = QHBoxLayout()
        self.date_edit = ModernEthiopianDateEdit("Date")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setEnabled(True)
        date_btn_row.addWidget(self.date_edit, 1)              # 50%

        self.add_line_btn = QPushButton("➕ Add to List")
        self.add_line_btn.setMinimumHeight(44)                 # match date widget height
        self.add_line_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_line_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3498db,stop:1 #2980b9);
                color: white; border: none; border-radius: 6px; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2980b9,stop:1 #2471a3);
            }
        """)
        self.add_line_btn.clicked.connect(self.add_expense_line)
        date_btn_row.addWidget(self.add_line_btn, 1)           # 50%

        section_layout.addLayout(date_btn_row)

        # Personal expense checkbox with improved visual indicator
        personal_row = QHBoxLayout()
        self.personal_checkbox = QCheckBox("Personal Expense (Owner's own use)")
        self.personal_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #2c3e50;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #bdc3c7;
                border-radius: 3px;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #e74c3c;
                border-color: #c0392b;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #c0392b;
            }
        """)
        personal_row.addWidget(self.personal_checkbox)
        personal_row.addStretch()
        section_layout.addLayout(personal_row)

        # Connect checkbox toggling to immediate visual feedback
        self.personal_checkbox.stateChanged.connect(self.on_personal_toggled)

        form_layout.addWidget(section)

        # --- EXPENSE LINES TABLE ---
        table_section = QFrame()
        table_section.setStyleSheet("""
            QFrame { background-color: white; border-radius: 12px; border: 1px solid #e0e0e0; }
        """)
        table_layout = QVBoxLayout(table_section)
        table_layout.setContentsMargins(20, 20, 20, 20)

        table_title = QLabel("Expense Items")
        table_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        table_title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        table_layout.addWidget(table_title)

        self.expense_table = QTableWidget()
        self.expense_table.setColumnCount(5)
        self.expense_table.setHorizontalHeaderLabels(
            ["Notes", "Amount", "Category", "Bank Account", ""]
        )
        self.expense_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.expense_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.expense_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.expense_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.expense_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.expense_table.setAlternatingRowColors(True)
        self.expense_table.verticalHeader().setVisible(False)
        self.expense_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.expense_table.setMinimumHeight(150)
        table_layout.addWidget(self.expense_table)

        self.total_label = QLabel("Total: 0.00")
        self.total_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.total_label.setAlignment(Qt.AlignRight)
        self.total_label.setStyleSheet("color: #2c3e50; margin-top: 5px;")
        table_layout.addWidget(self.total_label)

        form_layout.addWidget(table_section)
        form_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # --- BUTTON BAR ---
        button_bar = QWidget()
        button_bar.setFixedHeight(80)
        button_bar.setStyleSheet("""
            QWidget { background-color: white; border-top: 1px solid #e0e0e0; }
        """)
        btn_layout = QHBoxLayout(button_bar)
        btn_layout.setContentsMargins(30, 15, 30, 15)
        btn_layout.setSpacing(15)

        self.cancel_btn = QPushButton("Cancel" if not self.read_only else "Close")
        self.cancel_btn.setMinimumSize(100, 40)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton { background-color:#e0e0e0; color:#2c3e50; border:none; border-radius:6px; font-weight:600; font-size:13px; padding:10px 20px; }
            QPushButton:hover { background-color:#d5d5d5; }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        if self.read_only:
            btn_layout.addStretch()
            btn_layout.addWidget(self.cancel_btn)
        else:
            self.save_btn = QPushButton("Save All Expenses" if not self.is_edit else "Update Expense")
            self.save_btn.setMinimumSize(150, 45)
            self.save_btn.setCursor(Qt.PointingHandCursor)
            self.save_btn.setStyleSheet("""
                QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2ecc71,stop:1 #27ae60); color:white; border:none; border-radius:8px; font-weight:600; font-size:14px; padding:12px 24px; }
                QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #27ae60,stop:1 #219a52); }
            """)
            if self.is_edit:
                self.save_btn.clicked.connect(self.update_expense)
            else:
                self.save_btn.clicked.connect(self.save_multiple_expenses)
            btn_layout.addStretch()
            btn_layout.addWidget(self.cancel_btn)
            btn_layout.addWidget(self.save_btn)

        main_layout.addWidget(button_bar)

        # For edit mode, hide the line‑adding UI
        if self.is_edit and not self.read_only:
            self.add_line_btn.hide()
            self.expense_table.hide()
            self.total_label.hide()

    # ----------------------------------------------------------------------
    def _parse_amount(self, text: str) -> float:
        try:
            return float(text.replace(',', ''))
        except ValueError:
            return 0.0

    # ----------------------------------------------------------------------
    def load_data(self):
        """Load bank accounts with priority order and default to account 17."""
        accounts = self.bank_service.get_all()
        self.bank_combo.clear()
        self.bank_display_map.clear()
        self.bank_combo.addItem("-- Select Bank Account --", None)

        priority_ids = [14, 17, 16, 15, 12, 13]
        account_map = {acc.id: acc for acc in accounts if acc.is_active and not acc.is_deleted}

        for pid in priority_ids:
            if pid in account_map:
                acc = account_map.pop(pid)
                display = f"{acc.bank_name} - {acc.account_name}"
                if acc.account_number:
                    display += f" ({acc.account_number})"
                self.bank_combo.addItem(display, acc.id)
                self.bank_display_map[acc.id] = display

        for acc in account_map.values():
            display = f"{acc.bank_name} - {acc.account_name}"
            if acc.account_number:
                display += f" ({acc.account_number})"
            self.bank_combo.addItem(display, acc.id)
            self.bank_display_map[acc.id] = display

        idx = self.bank_combo.findData(17)
        if idx >= 0:
            self.bank_combo.setCurrentIndex(idx)

        categories = self.category_service.get_active()
        self.category_combo.clear()
        self.category_display_map.clear()
        self.category_combo.addItem("-- Select Category --", None)
        for cat in categories:
            self.category_combo.addItem(cat.name, cat.id)
            self.category_display_map[cat.id] = cat.name

    def populate_fields(self):
        if self.expense:
            self.amount_spin.setText(f"{self.expense.amount:,.2f}")
            if hasattr(self.expense, "date") and self.expense.date:
                qdate = QDate(self.expense.date.year, self.expense.date.month, self.expense.date.day)
                self.date_edit.setDate(qdate)
            if hasattr(self.expense, "bank_account_id") and self.expense.bank_account_id:
                idx = self.bank_combo.findData(self.expense.bank_account_id)
                if idx >= 0:
                    self.bank_combo.setCurrentIndex(idx)
            if hasattr(self.expense, "category_id") and self.expense.category_id:
                idx = self.category_combo.findData(self.expense.category_id)
                if idx >= 0:
                    self.category_combo.setCurrentIndex(idx)
            
            self.personal_checkbox.setChecked(bool(self.expense.is_personal))

            self.notes_edit.setPlainText(getattr(self.expense, "notes", "") or "")

    # -------------------- Line management --------------------
    def add_expense_line(self):
        if self.bank_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select a bank account.")
            return
        if self.category_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select a category.")
            return

        notes = self.notes_edit.toPlainText().strip()
        amount_text = self.amount_spin.text().strip()
        amount = self._parse_amount(amount_text)
        if amount <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than 0.")
            return

        bank_id = self.bank_combo.currentData()
        cat_id = self.category_combo.currentData()
        bank_name = self.bank_display_map.get(bank_id, "Unknown")
        cat_name = self.category_display_map.get(cat_id, "Unknown")

        line = {
            "notes": notes,
            "amount": amount,
            "bank_account_id": bank_id,
            "bank_name": bank_name,
            "category_id": cat_id,
            "category_name": cat_name,
            "is_personal": self.personal_checkbox.isChecked()
        }
        self.expense_lines.append(line)

        row = self.expense_table.rowCount()
        self.expense_table.insertRow(row)
        self.expense_table.setItem(row, 0, QTableWidgetItem(notes))
        amount_item = QTableWidgetItem(f"{amount:,.2f}")
        amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.expense_table.setItem(row, 1, amount_item)
        self.expense_table.setItem(row, 2, QTableWidgetItem(cat_name))
        self.expense_table.setItem(row, 3, QTableWidgetItem(bank_name))

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 30)
        del_btn.setStyleSheet("""
            QPushButton { background-color:#e74c3c; color:white; border:none; border-radius:4px; font-weight:bold; }
            QPushButton:hover { background-color:#c0392b; }
        """)
        del_btn.clicked.connect(lambda checked, idx=row: self.delete_expense_line(idx))
        self.expense_table.setCellWidget(row, 4, del_btn)

        self.notes_edit.setPlainText("")
        self.amount_spin.clear()
        self.update_total_label()
        self.notes_edit.text_edit.setFocus()

    def delete_expense_line(self, index):
        if 0 <= index < len(self.expense_lines):
            del self.expense_lines[index]
            self.expense_table.removeRow(index)
            for i in range(self.expense_table.rowCount()):
                btn = self.expense_table.cellWidget(i, 4)
                if btn:
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda checked, idx=i: self.delete_expense_line(idx))
            self.update_total_label()

    def update_total_label(self):
        total = sum(line["amount"] for line in self.expense_lines)
        self.total_label.setText(f"Total: {total:,.2f}")

    # -------------------- Data methods --------------------
    def validate_and_accept(self):
        if not self.is_edit and not self.expense_lines:
            QMessageBox.warning(self, "Validation", "Add at least one expense item.")
            return False
        return True

    def get_data(self):
        common = {
            'date': self.date_edit.date().toPython(),
            'payment_method': ExpensePaymentMethod.TRANSFER,
        }
        lines = []
        for line in self.expense_lines:
            lines.append({
                'description': "Expense",
                'amount': line['amount'],
                'category_id': line['category_id'],
                'bank_account_id': line['bank_account_id'],
                'notes': line['notes'],
                'is_personal': line.get('is_personal', False)
            })
        return common, lines

    def save_multiple_expenses(self):
        if not self.validate_and_accept():
            return
        common, lines = self.get_data()
        data = {'common': common, 'lines': lines}
        try:
            success = self.expense_service.create_multiple(data)
            if success:
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to save expenses.")
        except ValueError as e:
            QMessageBox.warning(self, "Insufficient Balance", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save expenses: {str(e)}")

    def update_expense(self):
        if self.bank_combo.currentData() is None or self.category_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select bank account and category.")
            return
        self.update_data = {
            'amount': self._parse_amount(self.amount_spin.text()),
            'notes': self.notes_edit.toPlainText().strip(),
            'bank_account_id': self.bank_combo.currentData(),
            'date': self.date_edit.date().toPython(),
            'description': "Expense",
            'category_id': self.category_combo.currentData(),
            'is_personal': self.personal_checkbox.isChecked()
        }
        self.accept()
    
    def on_personal_toggled(self, state):
        """Provide immediate visual feedback when the personal checkbox is toggled."""
        is_personal = (state == Qt.Checked)
        # Change the input section border color
        if is_personal:
            self.input_section.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border-radius: 12px;
                    border: 2px solid #e74c3c;
                }
            """)
            self.add_line_btn.setText("➕ Add Personal Expense")
        else:
            self.input_section.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border-radius: 12px;
                    border: 1px solid #e0e0e0;
                }
            """)
            self.add_line_btn.setText("➕ Add to List")