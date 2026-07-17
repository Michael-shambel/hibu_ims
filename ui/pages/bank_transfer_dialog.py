#!/usr/bin/env python3
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QDateEdit, QTextEdit, QRadioButton,
    QButtonGroup, QMessageBox, QFrame, QFormLayout, QScrollArea,
    QWidget, QApplication, QGroupBox
)
from PySide6.QtCore import Qt, QDate, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QDoubleValidator, QFont, QColor, QLinearGradient, QBrush, QPalette
from ui.components.ethiopian_date import EthiopianDateConverter
from services.bank_account_service import BankAccountService
from services.bank_transaction_service import BankTransactionService

logger = logging.getLogger(__name__)

class BankTransferDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.account_service = BankAccountService()
        self.transaction_service = BankTransactionService()

        self.setWindowTitle("Transfer Funds")
        self.setMinimumSize(600, 650)
        self.resize(600, 650)
        # Remove help button
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setup_ui()
        self.load_accounts()
        self.setup_connections()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== HEADER ====================
        header_widget = QWidget()
        header_widget.setFixedHeight(120)
        header_widget.setAutoFillBackground(True)

        # Gradient background
        palette = header_widget.palette()
        gradient = QLinearGradient(0, 0, 0, header_widget.height())
        gradient.setColorAt(0, QColor("#3498db"))
        gradient.setColorAt(1, QColor("#2980b9"))
        palette.setBrush(header_widget.backgroundRole(), QBrush(gradient))
        header_widget.setPalette(palette)

        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 20, 30, 20)

        top_row = QHBoxLayout()

        # Title
        self.title_label = QLabel("Bank Transfer")
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.title_label.setStyleSheet("color: white;")
        top_row.addWidget(self.title_label)
        top_row.addStretch()

        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ecf0f1;
                border: 2px solid rgba(236, 240, 241, 0.3);
                border-radius: 18px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(231, 76, 60, 0.3);
                border-color: #e74c3c;
            }
        """)
        self.close_btn.clicked.connect(self.reject)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        top_row.addWidget(self.close_btn)

        header_layout.addLayout(top_row)

        # Subtitle
        self.subtitle = QLabel("Transfer money between accounts or to external payee")
        self.subtitle.setFont(QFont("Segoe UI", 11))
        self.subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.8);")
        header_layout.addWidget(self.subtitle)
        header_layout.addStretch()

        main_layout.addWidget(header_widget)

        # ==================== SCROLL AREA ====================
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #f8f9fa;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        container = QWidget()
        container.setStyleSheet("background-color: #f8f9fa;")
        scroll_layout = QVBoxLayout(container)
        scroll_layout.setContentsMargins(30, 30, 30, 30)
        scroll_layout.setSpacing(25)

        # ========== FORM GROUP ==========
        form_group = QGroupBox("Transfer Details")
        form_group.setFont(QFont("Segoe UI", 12, QFont.Bold))
        form_group.setStyleSheet("""
            QGroupBox {
                color: #2c3e50;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                margin-top: 16px;
                padding-top: 12px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
            }
        """)

        form_layout = QFormLayout(form_group)
        form_layout.setContentsMargins(20, 25, 20, 25)
        form_layout.setSpacing(20)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Transfer type (radio buttons)
        type_widget = QWidget()
        type_layout = QHBoxLayout(type_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(15)

        self.internal_radio = QRadioButton("Between my accounts")
        self.internal_radio.setChecked(True)
        self.external_radio = QRadioButton("To external account")
        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.internal_radio)
        self.type_group.addButton(self.external_radio)

        # Style radio buttons
        radio_style = """
            QRadioButton {
                font-size: 14px;
                color: #2c3e50;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            QRadioButton::indicator:checked {
                image: url(:/icons/radio_checked.png);  /* fallback, you can use a real icon or rely on OS */
                background-color: #3498db;
                border-radius: 9px;
            }
        """
        self.internal_radio.setStyleSheet(radio_style)
        self.external_radio.setStyleSheet(radio_style)

        type_layout.addWidget(self.internal_radio)
        type_layout.addWidget(self.external_radio)
        type_layout.addStretch()

        form_layout.addRow("Transfer Type:", type_widget)

        # From account
        self.from_account_combo = QComboBox()
        self.from_account_combo.setMinimumHeight(35)
        self.from_account_combo.setStyleSheet("""
            QComboBox {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                padding: 5px 10px;
                background-color: white;
                font-size: 14px;
                min-height: 25px;
            }
            QComboBox:focus {
                border-color: #3498db;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #7f8c8d;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                border: 2px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #3498db;
                selection-color: white;
            }
        """)
        form_layout.addRow("From Account:", self.from_account_combo)

        # To account (internal)
        self.to_account_combo = QComboBox()
        self.to_account_combo.setMinimumHeight(35)
        self.to_account_combo.setStyleSheet(self.from_account_combo.styleSheet())
        form_layout.addRow("To Account:", self.to_account_combo)

        # External payee
        self.external_payee_edit = QLineEdit()
        self.external_payee_edit.setPlaceholderText("Recipient name / account")
        self.external_payee_edit.setMinimumHeight(35)
        self.external_payee_edit.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                padding: 5px 10px;
                background-color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
        """)
        self.external_payee_edit.hide()
        form_layout.addRow("Payee:", self.external_payee_edit)

        # Amount
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("0.00")
        self.amount_edit.setValidator(QDoubleValidator(0.00, 999999999.99, 2))
        self.amount_edit.setMinimumHeight(35)
        self.amount_edit.setStyleSheet(self.external_payee_edit.styleSheet())
        form_layout.addRow("Amount:", self.amount_edit)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMinimumHeight(35)
        self.date_edit.setStyleSheet("""
            QDateEdit {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                padding: 5px 10px;
                background-color: white;
                font-size: 14px;
            }
            QDateEdit:focus {
                border-color: #3498db;
            }
            QDateEdit::drop-down {
                border: none;
                width: 30px;
            }
            QDateEdit::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #7f8c8d;
                margin-right: 5px;
            }
        """)
        form_layout.addRow("Date:", self.date_edit)

        # # Description
        # self.desc_edit = QTextEdit()
        # self.desc_edit.setMaximumHeight(80)
        # self.desc_edit.setPlaceholderText("Optional description")
        # self.desc_edit.setStyleSheet("""
        #     QTextEdit {
        #         border: 2px solid #e0e0e0;
        #         border-radius: 6px;
        #         padding: 5px 10px;
        #         background-color: white;
        #         font-size: 14px;
        #     }
        #     QTextEdit:focus {
        #         border-color: #3498db;
        #     }
        # """)
        # form_layout.addRow("Description:", self.desc_edit)

        # # Reference
        # self.ref_edit = QLineEdit()
        # self.ref_edit.setPlaceholderText("Optional reference number")
        # self.ref_edit.setMinimumHeight(35)
        # self.ref_edit.setStyleSheet(self.external_payee_edit.styleSheet())
        # form_layout.addRow("Reference:", self.ref_edit)

        scroll_layout.addWidget(form_group)
        scroll_layout.addStretch()
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area, 1)

        # ==================== BUTTONS ====================
        button_widget = QWidget()
        button_widget.setFixedHeight(90)
        button_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #e0e0e0;
            }
        """)

        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(30, 20, 30, 20)
        button_layout.setSpacing(15)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumSize(120, 45)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 14px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
            QPushButton:pressed {
                background-color: #c8c8c8;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.transfer_btn = QPushButton("Transfer")
        self.transfer_btn.setMinimumSize(150, 45)
        self.transfer_btn.setCursor(Qt.PointingHandCursor)
        self.transfer_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2ecc71, stop:1 #27ae60);
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 14px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #27ae60, stop:1 #219a52);
            }
        """)
        self.transfer_btn.clicked.connect(self.do_transfer)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.transfer_btn)

        main_layout.addWidget(button_widget)

    def setup_connections(self):
        self.internal_radio.toggled.connect(self.toggle_transfer_type)
        self.from_account_combo.currentIndexChanged.connect(self.update_to_account_combo)

    def load_accounts(self):
        """Populate combo boxes with active accounts."""
        accounts = self.account_service.get_all()  # gets non-deleted accounts
        self.from_account_combo.clear()
        self.to_account_combo.clear()

        for acc in accounts:
            if acc.is_active:
                display = f"{acc.account_name} ({acc.bank_name})"
                self.from_account_combo.addItem(display, acc.id)
                self.to_account_combo.addItem(display, acc.id)

        # Set default: From Account = ID 17, To Account = ID 16
        idx = self.from_account_combo.findData(17)
        if idx >= 0:
            self.from_account_combo.setCurrentIndex(idx)

        idx = self.to_account_combo.findData(16)
        if idx >= 0:
            self.to_account_combo.setCurrentIndex(idx)

    def update_to_account_combo(self):
        """Remove the selected from account from to_account_combo to prevent self-transfer."""
        from_id = self.from_account_combo.currentData()
        if from_id is None:
            return

        # Save current selection if possible
        current_to_id = self.to_account_combo.currentData()

        self.to_account_combo.clear()
        accounts = self.account_service.get_all()
        for acc in accounts:
            if acc.is_active and acc.id != from_id:
                display = f"{acc.account_name} ({acc.bank_name})"
                self.to_account_combo.addItem(display, acc.id)

        # Try to reselect previously selected account if still available
        if current_to_id and current_to_id != from_id:
            index = self.to_account_combo.findData(current_to_id)
            if index >= 0:
                self.to_account_combo.setCurrentIndex(index)

    def toggle_transfer_type(self):
        if self.internal_radio.isChecked():
            self.to_account_combo.show()
            self.external_payee_edit.hide()
            # Update the label for the row (the row's label is part of the form layout, but we'll just show/hide widgets)
        else:
            self.to_account_combo.hide()
            self.external_payee_edit.show()

    def validate_inputs(self) -> bool:
        # From account
        if self.from_account_combo.currentData() is None:
            QMessageBox.warning(self, "Validation Error", "Please select a source account.")
            return False

        # Amount
        try:
            amount = float(self.amount_edit.text())
            if amount <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Please enter a valid positive amount.")
            return False

        # Transfer type specific
        if self.internal_radio.isChecked():
            if self.to_account_combo.currentData() is None:
                QMessageBox.warning(self, "Validation Error", "Please select a destination account.")
                return False
        else:
            if not self.external_payee_edit.text().strip():
                QMessageBox.warning(self, "Validation Error", "Please enter the payee name.")
                return False

        return True

    def do_transfer(self):
        if not self.validate_inputs():
            return

        from_id = self.from_account_combo.currentData()
        amount = float(self.amount_edit.text())
        tx_date = self.date_edit.date().toPython()
        reference = None

        # Get source account info
        from_account = self.account_service.get_by_id(from_id)
        from_bank = from_account.bank_name if from_account else "Unknown"

        if self.internal_radio.isChecked():
            to_id = self.to_account_combo.currentData()
            to_account = self.account_service.get_by_id(to_id)
            to_bank = to_account.bank_name if to_account else "Unknown"
            description = f"Transfer: {from_bank} → {to_bank}"
            
            success = self.transaction_service.transfer_between_accounts(
                from_account_id=from_id,
                to_account_id=to_id,
                amount=amount,
                transaction_date=tx_date,
                description=description,
                reference=reference
            )
            if success:
                QMessageBox.information(self, "Success", "Transfer completed successfully.")
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Transfer failed. Please check logs.")
        else:
            payee = self.external_payee_edit.text().strip()
            description = f"Transfer: {from_bank} → {payee}"
            
            tx = self.transaction_service.create_external_transfer(
                from_account_id=from_id,
                amount=amount,
                transaction_date=tx_date,
                payee=payee,
                description=description,
                reference=reference
            )
            if tx:
                QMessageBox.information(self, "Success", "External transfer recorded.")
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to record external transfer.")