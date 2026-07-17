from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDoubleSpinBox, QCheckBox, QHBoxLayout, QPushButton, QLabel,
    QMessageBox
)
from PySide6.QtCore import Qt
from models.bank_account import AccountTypeEnum
from services.bank_transaction_service import BankTransactionService
from datetime import date
import logging

logger = logging.getLogger(__name__)

class BankAccountDialog(QDialog):
    def __init__(self, parent=None, account=None, balance=None):
        super().__init__(parent)
        self.account = account
        self.original_balance = balance if balance is not None else 0.0
        self.transaction_service = BankTransactionService()
        self.setWindowTitle("Bank Account" + (" - Edit" if account else " - Create"))
        self.setMinimumWidth(450)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        
        # Account Name
        self.account_name_edit = QLineEdit()
        self.account_name_edit.setPlaceholderText("e.g., Main Business Account")
        self.account_name_edit.setMaxLength(100)
        form_layout.addRow("Account Name:*", self.account_name_edit)
        
        # Bank Name
        self.bank_name_edit = QLineEdit()
        self.bank_name_edit.setPlaceholderText("e.g., Commercial Bank of Ethiopia")
        self.bank_name_edit.setMaxLength(100)
        form_layout.addRow("Bank Name:*", self.bank_name_edit)
        
        # Account Number
        self.account_number_edit = QLineEdit()
        self.account_number_edit.setPlaceholderText("e.g., 1000234567890")
        self.account_number_edit.setMaxLength(50)
        form_layout.addRow("Account Number:*", self.account_number_edit)
        
        # Account Type
        self.account_type_combo = QComboBox()
        for atype in AccountTypeEnum:
            self.account_type_combo.addItem(atype.value.title(), atype)
        form_layout.addRow("Account Type:*", self.account_type_combo)
        
        # Initial/Current Balance - NOW EDITABLE FOR BOTH CREATE AND EDIT
        self.balance_spin = QDoubleSpinBox()
        self.balance_spin.setRange(-9999999.99, 9999999.99)  # Allow negative for adjustments
        self.balance_spin.setPrefix("$ ")
        self.balance_spin.setDecimals(2)
        self.balance_spin.setSingleStep(100)
        
        # Set initial value
        if self.account:
            self.balance_spin.setValue(self.original_balance)
            # In edit mode, make it editable but with a different style to indicate it's changeable
            self.balance_spin.setEnabled(True)
            self.balance_spin.setStyleSheet("background-color: white;")
            balance_label = "Current Balance:*"
            
            # Add a small hint label about balance adjustment
            hint_label = QLabel("(Changing balance will create an adjustment transaction)")
            hint_label.setStyleSheet("color: #7f8c8d; font-size: 10px; font-style: italic;")
            form_layout.addRow("", hint_label)
        else:
            self.balance_spin.setValue(0.0)
            self.balance_spin.setEnabled(True)
            balance_label = "Initial Balance:*"
        
        form_layout.addRow(balance_label, self.balance_spin)
        
        # Active Status - NOW VISIBLE AND EDITABLE FOR EDIT MODE
        self.active_check = QCheckBox("Account is active")
        self.active_check.setChecked(True)
        if self.account:
            self.active_check.setChecked(bool(self.account.is_active))
            form_layout.addRow("Status:", self.active_check)
        # For new accounts, we don't show the checkbox - they're active by default
        
        # Required fields note
        note_label = QLabel("* Required fields")
        note_label.setStyleSheet("color: gray; font-size: 11px;")
        note_label.setAlignment(Qt.AlignRight)
        form_layout.addRow("", note_label)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.save_btn.clicked.connect(self.save_and_close)
        self.save_btn.setDefault(True)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # If editing, populate fields
        if self.account:
            self.populate_fields()
    
    def validate_account_number(self, account_number):
        """Basic account number validation"""
        if len(account_number) < 5:
            return False, "Account number is too short (minimum 5 characters)"
        if not any(c.isdigit() for c in account_number):
            return False, "Account number should contain at least one digit"
        return True, ""
    
    def save_and_close(self):
        """Validate and save data"""
        # Required field validation
        account_name = self.account_name_edit.text().strip()
        if not account_name:
            QMessageBox.warning(self, "Validation Error", "Account name is required!")
            self.account_name_edit.setFocus()
            return
            
        bank_name = self.bank_name_edit.text().strip()
        if not bank_name:
            QMessageBox.warning(self, "Validation Error", "Bank name is required!")
            self.bank_name_edit.setFocus()
            return
            
        account_number = self.account_number_edit.text().strip()
        if not account_number:
            QMessageBox.warning(self, "Validation Error", "Account number is required!")
            self.account_number_edit.setFocus()
            return
        
        # Account number format validation
        is_valid, message = self.validate_account_number(account_number)
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", message)
            self.account_number_edit.setFocus()
            return
        
        # For edit mode, handle balance change confirmation
        if self.account:
            new_balance = self.balance_spin.value()
            if abs(new_balance - self.original_balance) > 0.01:  # If balance changed
                diff = new_balance - self.original_balance
                direction = "CREDIT" if diff > 0 else "DEBIT"
                
                reply = QMessageBox.question(
                    self,
                    "Confirm Balance Change",
                    f"You are changing the balance from ${self.original_balance:,.2f} to ${new_balance:,.2f}.\n\n"
                    f"This will create a {direction} adjustment transaction of ${abs(diff):,.2f}.\n\n"
                    "Do you want to proceed?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
        
        # Balance validation for new accounts
        if not self.account and self.balance_spin.value() < 0:
            reply = QMessageBox.question(
                self,
                "Negative Balance",
                "You're creating an account with a negative balance. Is this correct?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.balance_spin.setFocus()
                return
            
        self.accept()
    
    def populate_fields(self):
        """Populate fields with existing account data"""
        self.account_name_edit.setText(self.account.account_name or "")
        self.bank_name_edit.setText(self.account.bank_name or "")
        self.account_number_edit.setText(self.account.account_number or "")
        
        # Set account type using userData
        if self.account.account_type:
            index = self.account_type_combo.findData(self.account.account_type)
            if index >= 0:
                self.account_type_combo.setCurrentIndex(index)
        
        self.active_check.setChecked(bool(self.account.is_active))
    
    def get_data(self):
        """Get form data as dictionary"""
        account_type_data = self.account_type_combo.currentData()
        
        data = {
            "account_name": self.account_name_edit.text().strip(),
            "bank_name": self.bank_name_edit.text().strip(),
            "account_number": self.account_number_edit.text().strip(),
            "account_type": account_type_data,
            "is_active": self.active_check.isChecked() if self.account else True
        }
        
        # Only include initial_balance for new accounts
        if not self.account:
            data["initial_balance"] = self.balance_spin.value()
        
        return data
    
    def get_balance_change(self):
        """Return the balance change information if any"""
        if not self.account:
            return None
        
        new_balance = self.balance_spin.value()
        if abs(new_balance - self.original_balance) <= 0.01:
            return None
        
        diff = new_balance - self.original_balance
        return {
            'new_balance': new_balance,
            'difference': diff,
            'direction': 'CREDIT' if diff > 0 else 'DEBIT',
            'amount': abs(diff)
        }