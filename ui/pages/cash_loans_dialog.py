#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QScrollArea,
    QFrame,
    QCompleter,
    QGridLayout,
    QSizePolicy
)
from ui.pages.expense_dialog import (
    ModernComboBox, ModernInput, ModernEthiopianDateEdit, NumberLineEdit
)
from ui.pages.sales_page import AddCustomerDialog, SelectAllLineEdit
from PySide6.QtCore import QDate, Qt, QStringListModel, QTimer
from PySide6.QtGui import QColor, QFont, QDoubleValidator


from models.cash_loan import CashLoanDirectionEnum
from services.bank_account_service import BankAccountService
from services.cash_loan_service import CashLoanService
from services.customer_service import CustomerService
from services.supplier_service import SupplierService
from ui.components.ethiopian_date import EthiopianDateConverter


class CashLoansOverviewDialog(QDialog):
    def __init__(self, parent, current_user, initial_search=""):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Cash Loans")
        self.setMinimumSize(1200, 750)   # slightly narrower
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.initial_search = initial_search
        self.service = CashLoanService()
        self.rows = []
        self.filtered_rows = []
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setGeometry(QApplication.primaryScreen().availableGeometry())
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(18)

        # ---- Top row ----
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        new_btn = QPushButton("➕ New Loan")
        new_btn.setFixedSize(140, 44)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        new_btn.setStyleSheet(self._button_style("#27ae60", "#219a52"))
        new_btn.clicked.connect(self.new_loan)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFixedSize(130, 44)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        refresh_btn.setStyleSheet(self._button_style("#3498db", "#2980b9"))
        refresh_btn.clicked.connect(self.load_data)

        search_label = QLabel("🔍 Search:")
        search_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        search_label.setStyleSheet("color: #2c3e50;")

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by name, type, amount...")
        self.search_edit.setMinimumHeight(42)
        self.search_edit.setFont(QFont("Segoe UI", 14))
        self.search_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
        """)
        self.search_edit.textChanged.connect(self.filter_table)

        top_layout.addWidget(new_btn)
        top_layout.addWidget(refresh_btn)
        top_layout.addWidget(search_label)
        top_layout.addWidget(self.search_edit, 1)
        layout.addLayout(top_layout)

        # ---- Summary Card ----
        self.summary_label = QLabel("Open loans: 0")
        self.summary_label.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.summary_label.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 14px 20px;
                color: #2c3e50;
            }
        """)
        layout.addWidget(self.summary_label)

        # ---- Table ----
        self.table = QTableWidget()
        headers = [
            "Person", "Direction", "Principal", "Paid",
            "Remaining", "Bank Account", "Actions", "History"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        # Set minimum widths (columns will stretch beyond if space allows)
        self.table.setColumnWidth(0, 180)  # Person minimum
        self.table.setColumnWidth(1, 120)  # Direction minimum
        self.table.setColumnWidth(2, 110)  # Principal
        self.table.setColumnWidth(3, 110)  # Paid
        self.table.setColumnWidth(4, 120)  # Remaining
        self.table.setColumnWidth(5, 180)  # Bank Account minimum
        self.table.setColumnWidth(6, 230)  # Actions minimum (two buttons)
        self.table.setColumnWidth(7, 100)  # History

        # Stretch the main columns to fill available width
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)          # Person
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Direction
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Principal
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Paid
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Remaining
        header.setSectionResizeMode(5, QHeaderView.Stretch)          # Bank Account
        header.setSectionResizeMode(6, QHeaderView.Stretch)          # Actions
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents) # History

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 14px;
                font-weight: bold;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 12px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        layout.addWidget(self.table, 1)

    def load_data(self):
        self.rows = self.service.get_open_loans()
        self.filtered_rows = self.rows.copy()
        self.update_summary()
        if self.initial_search:
            self.search_edit.setText(self.initial_search)
            self.initial_search = ""
        else:
            self.populate_table()

    def update_summary(self):
        summary = self.service.get_cash_loan_summary()
        direction_color = "#27ae60" if summary['net_direction'] == "Receivable" else "#e74c3c"
        self.summary_label.setText(
            f"📊 <b>Open loans:</b> {summary['open_count']}    "
            f"💰 <b>YABEDERKUT:</b> ${summary['total_receivable']:,.2f}    "
            f"💳 <b>YETEBEDERKUT:</b> ${summary['total_payable']:,.2f}    "
            f"⚖️ <b>Net:</b> <span style='color:{direction_color};'>${summary['abs_net_balance']:,.2f} {summary['net_direction']}</span>"
        )

    def populate_table(self, data=None):
        if data is None:
            data = self.filtered_rows
        self.table.setRowCount(len(data))
        for row, loan in enumerate(data):
            # 0: Person
            self.table.setItem(row, 0, self._text_item(loan["person_name"]))

            # 1: Direction
            direction_item = self._text_item(loan["direction_label"])
            direction_item.setTextAlignment(Qt.AlignCenter)
            if loan["direction"] == CashLoanDirectionEnum.GIVEN.value:
                direction_item.setForeground(QColor("#27ae60"))
            else:
                direction_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 1, direction_item)

            # 2: Principal
            self.table.setItem(row, 2, self._amount_item(loan["principal_amount"]))
            # 3: Paid
            self.table.setItem(row, 3, self._amount_item(loan["paid_amount"]))
            # 4: Remaining
            remaining_item = self._amount_item(loan["remaining"])
            remaining_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 4, remaining_item)

            # 5: Bank Account
            self.table.setItem(row, 5, self._text_item(loan.get("bank_account", "")))

            # 6: Actions (Repay + Cancel)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(8, 4, 8, 4)
            actions_layout.setSpacing(8)

            repay_btn = QPushButton("💳 Repay")
            repay_btn.setFixedSize(100, 40)
            repay_btn.setCursor(Qt.PointingHandCursor)
            repay_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
            repay_btn.setStyleSheet(self._button_style("#8e44ad", "#7d3c98"))
            repay_btn.clicked.connect(lambda checked, row=loan: self.record_repayment(row))
            actions_layout.addWidget(repay_btn)

            if self.is_user_admin():
                cancel_btn = QPushButton("❌ Cancel")
                cancel_btn.setFixedSize(100, 40)
                cancel_btn.setCursor(Qt.PointingHandCursor)
                cancel_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
                cancel_btn.setStyleSheet(self._button_style("#e74c3c", "#c0392b"))
                cancel_btn.clicked.connect(lambda checked, row=loan: self.cancel_loan(row))
                actions_layout.addWidget(cancel_btn)

            self.table.setCellWidget(row, 6, actions_widget)

            # 7: History
            history_btn = QPushButton("📜 History")
            history_btn.setFixedSize(100, 40)
            history_btn.setCursor(Qt.PointingHandCursor)
            history_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
            history_btn.setStyleSheet(self._button_style("#f39c12", "#e67e22"))
            history_btn.clicked.connect(lambda checked, lid=loan["loan_id"]: self.show_payment_history(lid))
            self.table.setCellWidget(row, 7, history_btn)

    def _text_item(self, value):
        item = QTableWidgetItem(str(value or ""))
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        return item

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${float(value or 0):,.2f}")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def filter_table(self, text):
        text = text.lower().strip()
        if not text:
            self.filtered_rows = self.rows.copy()
        else:
            filtered = []
            for loan in self.rows:
                searchable = [
                    loan["person_name"],
                    loan["direction_label"],
                    f"${loan['principal_amount']:,.2f}",
                    f"${loan['remaining']:,.2f}",
                ]
                if any(text in value.lower() for value in searchable):
                    filtered.append(loan)
            self.filtered_rows = filtered
        self.populate_table()

    def new_loan(self):
        dialog = CashLoanEntryDialog(self, self.current_user)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            success, error = self.service.create_cash_loan(**data)
            if success:
                QMessageBox.information(self, "Success", "Cash loan recorded.")
                self.load_data()
            else:
                QMessageBox.critical(self, "Error", error or "Failed to record cash loan.")

    def record_repayment(self, loan):
        dialog = CashLoanRepaymentDialog(self, self.current_user, loan)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            success, error = self.service.record_repayment(loan["loan_id"], **data)
            if success:
                QMessageBox.information(self, "Success", "Loan repayment recorded.")
                self.load_data()
            else:
                QMessageBox.critical(self, "Error", error or "Failed to record repayment.")

    def cancel_loan(self, loan):
        if not self.is_user_admin():
            QMessageBox.warning(self, "Permission Denied", "Only admin can cancel loans.")
            return
        reply = QMessageBox.question(
            self,
            "Confirm Cancel",
            f"Are you sure you want to cancel this loan for {loan['person_name']}?\n\n"
            "This will delete the loan and its original bank transaction.\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        success, error = self.service.cancel_loan(loan["loan_id"])
        if success:
            QMessageBox.information(self, "Success", "Loan cancelled successfully.")
            self.load_data()
        else:
            QMessageBox.critical(self, "Error", error or "Failed to cancel loan.")

    def show_payment_history(self, loan_id):
        dialog = LoanPaymentHistoryDialog(loan_id, self)
        dialog.exec()

    def is_user_admin(self):
        if not self.current_user:
            return False
        if isinstance(self.current_user, dict):
            return self.current_user.get('is_admin') or self.current_user.get('role') == 'admin'
        return getattr(self.current_user, 'is_admin', False)

    @staticmethod
    def _button_style(color, hover_color):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {hover_color}; }}
        """


# ===================================================================
# CashLoanEntryDialog (unchanged from original)
# ===================================================================
class CashLoanEntryDialog(QDialog):
    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.current_user = current_user
        self.customers = []
        self.suppliers = []
        self.accounts = []
        self.setWindowTitle("New Cash Loan")
        # self.setMinimumSize(700, 650)
        # self.setMaximumSize(800, 800)
        self.setWindowState(Qt.WindowMaximized)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.init_ui()
        self.load_lists()

    # ---------- Helper to create a labeled input ----------
    def _labeled_line_edit(self, label_text: str):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet("color: #6b7280; margin: 0px; padding: 0px;")
        layout.addWidget(lbl)

        edit = QLineEdit()
        edit.setMinimumHeight(40)
        edit.setStyleSheet("""
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
        layout.addWidget(edit)
        return container, edit

    def _labeled_combo(self, label_text: str):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet("color: #6b7280; margin: 0px; padding: 0px;")
        layout.addWidget(lbl)

        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setFixedHeight(60)                     # fixed tall height
        combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                background-color: white;
                padding-right: 80px;                /* make room for the 80px button */
            }
            QComboBox:focus {
                border: 1px solid #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 80px;                        /* massive button */
                subcontrol-origin: padding;
                subcontrol-position: right center;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 14px solid transparent;
                border-right: 14px solid transparent;
                border-top: 18px solid #6b7280;     /* huge arrow */
                margin: 0px;                        /* centre it */
            }
            QComboBox QAbstractItemView {
                border: 1px solid #d1d5db;
                background-color: white;
                selection-background-color: #e3f2fd;
                font-size: 14px;
                padding: 6px;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                min-height: 30px;
            }
        """)

        line_edit = SelectAllLineEdit()
        line_edit.setStyleSheet(combo.styleSheet())
        combo.setLineEdit(line_edit)

        layout.addWidget(combo)
        return container, combo

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #f8f9fa; border: none; }")

        container = QWidget()
        container.setStyleSheet("background-color: #f8f9fa;")
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(30, 20, 30, 20)
        form_layout.setSpacing(15)

        # ---- Card ----
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        # Remove maximum width – let it stretch
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(35, 25, 35, 25)   # bigger padding
        card_layout.setHorizontalSpacing(30)             # more space between columns
        card_layout.setVerticalSpacing(15)               # more space between rows

        # ---- Row 0: Person Source (col 0) | Select Person + Add (col 1) ----
        source_container, self.source_combo = self._labeled_combo("Person Source")
        self.source_combo.addItem("Manual person", "manual")
        self.source_combo.addItem("Existing customer", "customer")
        self.source_combo.addItem("Existing supplier", "supplier")
        self.source_combo.currentIndexChanged.connect(self.on_source_changed)
        card_layout.addWidget(source_container, 0, 0)

        # Entity combo + Add button
        entity_widget = QWidget()
        entity_layout = QHBoxLayout(entity_widget)
        entity_layout.setContentsMargins(0, 0, 0, 0)
        entity_layout.setSpacing(8)

        entity_container, self.entity_combo = self._labeled_combo("Select Person")
        self.entity_combo.currentIndexChanged.connect(self.on_entity_changed)
        entity_layout.addWidget(entity_container, 1)

        self.add_entity_btn = QPushButton("➕")
        self.add_entity_btn.setFixedSize(45, 45)   # slightly larger
        self.add_entity_btn.setCursor(Qt.PointingHandCursor)
        self.add_entity_btn.setToolTip("Add new customer or supplier")
        self.add_entity_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.add_entity_btn.clicked.connect(self.add_entity)
        entity_layout.addWidget(self.add_entity_btn)

        card_layout.addWidget(entity_widget, 0, 1)

        # ---- Row 1: Name (col 0) | Phone (col 1) ----
        name_container, self.name_input = self._labeled_line_edit("Name")
        self.name_input.setPlaceholderText("Person name")
        card_layout.addWidget(name_container, 1, 0)

        phone_container, self.phone_input = self._labeled_line_edit("Phone")
        self.phone_input.setPlaceholderText("Phone number")
        card_layout.addWidget(phone_container, 1, 1)

        # ---- Row 2: Loan Type (col 0) | Amount (col 1) ----
        direction_container, self.direction_combo = self._labeled_combo("Loan Type")
        self.direction_combo.addItem("ABEDIR", CashLoanDirectionEnum.GIVEN)
        self.direction_combo.addItem("TEBEDER", CashLoanDirectionEnum.RECEIVED)
        card_layout.addWidget(direction_container, 2, 0)

        # Amount
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
        self.amount_spin.setMinimumHeight(46)
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
        card_layout.addWidget(amount_widget, 2, 1)

        # ---- Row 3: Bank Account (col 0) | Loan Date (col 1) ----
        bank_container, self.bank_combo = self._labeled_combo("Bank/Cash Account")
        card_layout.addWidget(bank_container, 3, 0)

        self.loan_date_edit = ModernEthiopianDateEdit("Loan Date")
        self.loan_date_edit.setDate(QDate.currentDate())
        card_layout.addWidget(self.loan_date_edit, 3, 1)

        # ---- Row 4: Note (span both columns) ----
        note_container, self.note_edit = self._labeled_line_edit("Note (optional)")
        self.note_edit.setPlaceholderText("Optional note")
        card_layout.addWidget(note_container, 4, 0, 1, 2)

        # ---- End of card ----
        form_layout.addWidget(card)
        form_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # ---- Button Bar ----
        button_bar = QWidget()
        button_bar.setFixedHeight(80)
        button_bar.setStyleSheet("""
            QWidget { background-color: white; border-top: 1px solid #e0e0e0; }
        """)
        btn_layout = QHBoxLayout(button_bar)
        btn_layout.setContentsMargins(30, 15, 30, 15)
        btn_layout.setSpacing(15)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumSize(100, 40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                padding: 10px 20px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Loan")
        save_btn.setMinimumSize(150, 45)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(CashLoansOverviewDialog._button_style("#27ae60", "#219a52"))
        save_btn.clicked.connect(self.validate_and_accept)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)

        main_layout.addWidget(button_bar)

    # ---------- Core logic (unchanged) ----------
    def load_lists(self):
        self.customers = CustomerService().get_all()
        self.suppliers = SupplierService().get_all()
        self.accounts = BankAccountService().get_all()
        self.populate_bank_combo()
        self.on_source_changed()

    def populate_bank_combo(self):
        self.bank_combo.clear()
        self.bank_combo.addItem("-- Select Account --", None)
        priority_ids = [14, 17, 16, 15, 12, 13]
        account_map = {acc.id: acc for acc in self.accounts if getattr(acc, "is_active", True)}
        for account_id in priority_ids:
            account = account_map.pop(account_id, None)
            if account:
                self.bank_combo.addItem(self.account_label(account), account.id)
        for account in account_map.values():
            self.bank_combo.addItem(self.account_label(account), account.id)
        if self.bank_combo.count() > 1:
            self.bank_combo.setCurrentIndex(1)

    def on_source_changed(self):
        source = self.source_combo.currentData()
        self.entity_combo.clear()
        self.entity_combo.setEnabled(source != "manual")
        self.name_input.setReadOnly(source != "manual")
        self.phone_input.setReadOnly(source != "manual")
        self.add_entity_btn.setVisible(source != "manual")

        if source == "customer":
            for customer in self.customers:
                display = f"{customer.name} ({customer.phone or 'No phone'})"
                self.entity_combo.addItem(display, customer)
        elif source == "supplier":
            for supplier in self.suppliers:
                display = f"{supplier.supplier_name} ({supplier.contact_phone or 'No phone'})"
                self.entity_combo.addItem(display, supplier)
        else:
            self.name_input.clear()
            self.phone_input.clear()
            self.entity_combo.setCompleter(None)
            return

        self._setup_entity_completer()
        self.on_entity_changed()

    def _setup_entity_completer(self):
        texts = [self.entity_combo.itemText(i) for i in range(self.entity_combo.count())]
        if not texts:
            self.entity_combo.setCompleter(None)
            return

        model = QStringListModel(texts)
        completer = QCompleter()
        completer.setModel(model)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.popup().setStyleSheet("""
            QListView {
                font-size: 14px;
                padding: 4px;
                background-color: white;
                border: 1px solid #d1d5db;
            }
            QListView::item {
                padding: 8px;
                min-height: 30px;
                border-bottom: 1px solid #e5e7eb;
            }
            QListView::item:selected {
                background-color: #e3f2fd;
            }
        """)
        self.entity_combo.setCompleter(completer)

    def on_entity_changed(self):
        source = self.source_combo.currentData()
        entity = self.entity_combo.currentData()
        if source == "customer" and entity:
            self.name_input.setText(entity.name or "")
            self.phone_input.setText(entity.phone or "")
        elif source == "supplier" and entity:
            self.name_input.setText(entity.supplier_name or "")
            self.phone_input.setText(entity.contact_phone or "")

    def add_entity(self):
        source = self.source_combo.currentData()
        if source == "customer":
            dialog = AddCustomerDialog(self)
            if dialog.exec() == QDialog.Accepted:
                data = dialog.get_customer_data()
                new_customer = CustomerService().create(data)
                if new_customer:
                    self.customers = CustomerService().get_all()
                    self.on_source_changed()
                    idx = self.entity_combo.findData(new_customer.id)
                    if idx >= 0:
                        self.entity_combo.setCurrentIndex(idx)
        elif source == "supplier":
            QMessageBox.information(self, "Not Implemented", "Adding suppliers from here is not yet supported.\nPlease use the Suppliers page.")
        else:
            return

    def validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        amount_text = self.amount_spin.text().strip()
        try:
            amount = float(amount_text.replace(',', ''))
        except ValueError:
            amount = 0.0
        if amount <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than zero.")
            return
        if self.bank_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select a bank/cash account.")
            return
        self.accept()

    def get_data(self):
        source = self.source_combo.currentData()
        entity = self.entity_combo.currentData()
        customer_id = entity.id if source == "customer" and entity else None
        supplier_id = entity.id if source == "supplier" and entity else None
        amount_text = self.amount_spin.text().strip()
        amount = float(amount_text.replace(',', '')) if amount_text else 0.0
        return {
            "person_name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "direction": self.direction_combo.currentData(),
            "amount": amount,
            "bank_account_id": self.bank_combo.currentData(),
            "user_id": self.current_user_id(),
            "loan_date": self.loan_date_edit.date().toPython(),
            "due_date": None,   # due date not used in UI
            "notes": self.note_edit.text().strip(),
            "customer_id": customer_id,
            "supplier_id": supplier_id,
        }

    def current_user_id(self):
        if isinstance(self.current_user, dict):
            return self.current_user.get("id")
        return getattr(self.current_user, "id", None) if self.current_user else None

    @staticmethod
    def account_label(account):
        label = f"{account.bank_name} - {account.account_name}" if account.bank_name else account.account_name
        if account.account_number:
            label += f" ({account.account_number})"
        return label

    # ---------- Core logic with defaults ----------
    def load_lists(self):
        self.customers = CustomerService().get_all()
        self.suppliers = SupplierService().get_all()
        self.accounts = BankAccountService().get_all()
        self.populate_bank_combo()

        # Set default Person Source to "Existing customer"
        idx = self.source_combo.findData("customer")
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)          # this triggers on_source_changed
        else:
            # fallback: by text
            for i in range(self.source_combo.count()):
                if self.source_combo.itemText(i).lower() == "existing customer":
                    self.source_combo.setCurrentIndex(i)
                    break

        # Apply other defaults (customer selection, amount, bank)
        # Use singleShot to let UI settle after the combo population
        QTimer.singleShot(0, self.apply_defaults)

    # ---------- NEW: Apply default selections ----------
    def apply_defaults(self):
        """
        Apply defaults after lists are loaded and source is set.
        """
        # 2. Select person "ekub" (case-insensitive partial match)
        for i in range(self.entity_combo.count()):
            text = self.entity_combo.itemText(i).lower()
            if "ekub" in text:
                self.entity_combo.setCurrentIndex(i)
                break

        # 3. Set amount to 21200
        self.amount_spin.setText("21200")

        # 4. Set bank/cash account to "CASH - SHOPE(00000)"
        # Find account with account_number "00000" and bank_name "CASH"
        for i in range(self.bank_combo.count()):
            account_id = self.bank_combo.itemData(i)
            if account_id:
                account = next((a for a in self.accounts if a.id == account_id), None)
                if account and account.account_number == "00000" and account.bank_name and account.bank_name.lower() == "cash":
                    self.bank_combo.setCurrentIndex(i)
                    break


# ===================================================================
# CashLoanRepaymentDialog (unchanged from original)
# ===================================================================
class CashLoanRepaymentDialog(QDialog):
    def __init__(self, parent, current_user, loan):
        super().__init__(parent)
        self.current_user = current_user
        self.loan = loan
        self.accounts = []
        self.setWindowTitle(f"Record Loan Repayment - {loan['person_name']}")
        self.setMinimumSize(800, 600)
        # self.setMinimumWidth(560)
        self.init_ui()
        self.load_accounts()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #f8f9fa; border: none; }")

        container = QWidget()
        container.setStyleSheet("background-color: #f8f9fa;")
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(30, 20, 30, 20)
        form_layout.setSpacing(15)

        # ---- Card ----
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(35, 25, 35, 25)
        card_layout.setHorizontalSpacing(30)
        card_layout.setVerticalSpacing(15)

        # ---- Loan info header (spans both columns) ----
        info_label = QLabel(
            f"<b>Repaying for:</b> {self.loan['person_name']}<br>"
            f"<b>Remaining:</b> ${self.loan['remaining']:,.2f}<br>"
            f"<b>Direction:</b> {self.loan['direction_label']}"
        )
        info_label.setFont(QFont("Segoe UI", 13))
        info_label.setStyleSheet("padding: 10px; background-color: #f0f4f8; border-radius: 6px;")
        card_layout.addWidget(info_label, 0, 0, 1, 2)

        # ---- Amount ----
        amount_widget = QWidget()
        amount_layout = QVBoxLayout(amount_widget)
        amount_layout.setContentsMargins(0, 0, 0, 0)
        amount_layout.setSpacing(1)
        amount_label = QLabel("Amount")
        amount_label.setFont(QFont("Segoe UI", 9))
        amount_label.setStyleSheet("color: #6b7280; margin: 0px; padding: 0px;")
        amount_layout.addWidget(amount_label)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, max(0.01, self.loan["remaining"]))
        self.amount_spin.setDecimals(2)
        self.amount_spin.setSingleStep(100)
        self.amount_spin.setPrefix("$ ")
        self.amount_spin.setValue(self.loan["remaining"])
        self.amount_spin.setMinimumHeight(46)
        self.amount_spin.setStyleSheet("""
            QDoubleSpinBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                background-color: white;
            }
            QDoubleSpinBox:focus {
                border: 1px solid #3b82f6;
            }
        """)
        amount_layout.addWidget(self.amount_spin)
        card_layout.addWidget(amount_widget, 1, 0)

        # ---- Bank Account ----
        bank_container, self.bank_combo = self._labeled_combo("Bank/Cash Account")
        card_layout.addWidget(bank_container, 1, 1)

        # ---- Payment Date (Ethiopian) ----
        self.date_edit = ModernEthiopianDateEdit("Payment Date")
        self.date_edit.setDate(QDate.currentDate())
        card_layout.addWidget(self.date_edit, 2, 0)

        # ---- Note ----
        note_container, self.note_edit = self._labeled_line_edit("Note (optional)")
        self.note_edit.setPlaceholderText("Optional note")
        card_layout.addWidget(note_container, 2, 1)

        # ---- End of card ----
        form_layout.addWidget(card)
        form_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # ---- Button Bar ----
        button_bar = QWidget()
        button_bar.setFixedHeight(80)
        button_bar.setStyleSheet("""
            QWidget { background-color: white; border-top: 1px solid #e0e0e0; }
        """)
        btn_layout = QHBoxLayout(button_bar)
        btn_layout.setContentsMargins(30, 15, 30, 15)
        btn_layout.setSpacing(15)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumSize(100, 40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                padding: 10px 20px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Record Payment")
        save_btn.setMinimumSize(150, 45)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(CashLoansOverviewDialog._button_style("#8e44ad", "#7d3c98"))
        save_btn.clicked.connect(self.validate_and_accept)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)

        main_layout.addWidget(button_bar)

    # Helper methods (reuse from CashLoanEntryDialog)
    def _labeled_line_edit(self, label_text: str):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet("color: #6b7280; margin: 0px; padding: 0px;")
        layout.addWidget(lbl)

        edit = QLineEdit()
        edit.setMinimumHeight(40)
        edit.setStyleSheet("""
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
        layout.addWidget(edit)
        return container, edit

    def _labeled_combo(self, label_text: str):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet("color: #6b7280; margin: 0px; padding: 0px;")
        layout.addWidget(lbl)

        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMinimumHeight(46)
        combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                background-color: white;
            }
            QComboBox:focus {
                border: 1px solid #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #d1d5db;
                background-color: white;
                selection-background-color: #e3f2fd;
                font-size: 14px;
                padding: 6px;
            }
        """)
        layout.addWidget(combo)
        return container, combo

    def load_accounts(self):
        self.accounts = BankAccountService().get_all()
        self.bank_combo.clear()
        self.bank_combo.addItem("Select Account", None)
        for account in self.accounts:
            if getattr(account, "is_active", True):
                self.bank_combo.addItem(CashLoanEntryDialog.account_label(account), account.id)
        if self.bank_combo.count() > 1:
            self.bank_combo.setCurrentIndex(1)

    def validate_and_accept(self):
        if self.bank_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select a bank/cash account.")
            return
        self.accept()

    def get_data(self):
        return {
            "amount": self.amount_spin.value(),
            "bank_account_id": self.bank_combo.currentData(),
            "user_id": self.current_user_id(),
            "payment_date": self.date_edit.date().toPython(),
            "notes": self.note_edit.text().strip(),
        }

    def current_user_id(self):
        if isinstance(self.current_user, dict):
            return self.current_user.get("id")
        return getattr(self.current_user, "id", None) if self.current_user else None


# ===================================================================
# NEW: Loan Payment History Dialog
# ===================================================================
class LoanPaymentHistoryDialog(QDialog):
    def __init__(self, loan_id, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Loan Payment History")
        self.setMinimumSize(700, 450)
        self.loan_id = loan_id
        self.service = CashLoanService()
        self.current_user = getattr(parent, 'current_user', None)  # try to get user from parent
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Payment History for Loan #{self.loan_id}")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Date (Ethiopian)", "Amount", "Bank Account", "Note", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 60)

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 12))
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 6px;
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
        layout.addWidget(self.table, 1)

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(100, 40)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def load_data(self):
        payments = self.service.get_payment_history(self.loan_id)
        self.table.setRowCount(len(payments))
        is_admin = self.is_user_admin()

        for row, p in enumerate(payments):
            # Convert Gregorian date to Ethiopian format
            greg_date = p['payment_date']  # Python date
            try:
                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_date)
                eth_date_str = f"{eth_year:04d}-{eth_month:02d}-{eth_day:02d}"
            except Exception:
                eth_date_str = greg_date.strftime("%Y-%m-%d")  # fallback to Gregorian

            date_item = QTableWidgetItem(eth_date_str)
            date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, date_item)

            # Amount
            amount_item = QTableWidgetItem(f"${p['amount']:,.2f}")
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, amount_item)

            # Bank Account
            self.table.setItem(row, 2, QTableWidgetItem(p['bank_account']))

            # Note
            self.table.setItem(row, 3, QTableWidgetItem(p['notes'] or ""))

            # Actions: Delete button (admin only)
            if is_admin:
                delete_btn = QPushButton("🗑️")
                delete_btn.setFixedSize(40, 40)
                delete_btn.setToolTip("Delete this payment")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 16px;
                    }
                    QPushButton:hover { background-color: #c0392b; }
                """)
                payment_id = p.get('payment_id')
                if payment_id:
                    delete_btn.clicked.connect(
                        lambda checked, pid=payment_id: self.delete_payment(pid)
                    )
                else:
                    delete_btn.setEnabled(False)
                self.table.setCellWidget(row, 4, delete_btn)
            else:
                self.table.setItem(row, 4, QTableWidgetItem(""))

        if self.table.rowCount() == 0:
            self.table.setRowCount(1)
            empty_item = QTableWidgetItem("No payments recorded.")
            empty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setSpan(0, 0, 1, 5)
            self.table.setItem(0, 0, empty_item)

    def delete_payment(self, payment_id):
        if not self.is_user_admin():
            QMessageBox.warning(self, "Permission Denied", "Only admin can delete payments.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this payment?\n\n"
            "This action cannot be undone and the loan balance will be recalculated.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        user_id = self.current_user_id()
        success, message = self.service.delete_payment(payment_id, user_id)
        if success:
            QMessageBox.information(self, "Success", "Payment deleted successfully.")
            self.load_data()  # refresh the table
            # Also notify the parent (if any) to refresh the overview
            if self.parent():
                # If parent is a dialog with a load_data method, call it
                if hasattr(self.parent(), 'load_data'):
                    self.parent().load_data()
        else:
            QMessageBox.critical(self, "Error", f"Failed to delete payment:\n{message}")

    def is_user_admin(self):
        user = self.current_user or getattr(self.parent(), 'current_user', None)
        if not user:
            return False
        if isinstance(user, dict):
            return user.get('is_admin') or user.get('role') == 'admin'
        return getattr(user, 'is_admin', False)

    def current_user_id(self):
        user = self.current_user or getattr(self.parent(), 'current_user', None)
        if not user:
            return None
        if isinstance(user, dict):
            return user.get('id')
        return getattr(user, 'id', None)