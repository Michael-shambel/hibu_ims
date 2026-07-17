
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QDoubleSpinBox, QLineEdit, QDialogButtonBox
)
from services.bank_account_service import BankAccountService
class DepositDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record External Deposit")
        layout = QFormLayout(self)

        self.account_combo = QComboBox()
        accounts = BankAccountService().get_all()  # or pass from parent
        for acc in accounts:
            self.account_combo.addItem(f"{acc.account_name} ({acc.bank_name})", acc.id)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 9999999.99)
        self.amount_spin.setPrefix("$ ")

        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("e.g., Cash, Customer ABC")

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Optional description")

        layout.addRow("Account:", self.account_combo)
        layout.addRow("Amount:", self.amount_spin)
        layout.addRow("Source:", self.source_edit)
        layout.addRow("Description:", self.desc_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        return {
            'account_id': self.account_combo.currentData(),
            'amount': self.amount_spin.value(),
            'source': self.source_edit.text().strip(),
            'description': self.desc_edit.text().strip()
        }