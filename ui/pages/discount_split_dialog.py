#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QDoubleSpinBox, QTextEdit, QPushButton, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

class DiscountSplitDialog(QDialog):
    def __init__(self, batch, parent=None):
        super().__init__(parent)
        self.batch = batch
        product_name = batch.product.name if hasattr(batch, 'product') and batch.product else "Unknown"
        self.setWindowTitle(f"Apply Discount – Batch #{batch.id} ({product_name})")
        self.setMinimumWidth(480)

        # Attributes to retrieve after dialog accepts
        self.new_price = None
        self.note = ""
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        info = QLabel(
            f"<b>Product:</b> {self.batch.product.name if self.batch.product else 'Unknown'}<br>"
            f"<b>Original Unit Price:</b> ETB {self.batch.cost_price:,.2f}<br>"
            f"<b>Remaining Quantity:</b> {self.batch.available_quantity}<br>"
            f"<b>Already Sold:</b> {self.batch.quantity - self.batch.available_quantity}"
        )
        info.setTextFormat(Qt.RichText)
        layout.addWidget(info)

        form = QFormLayout()
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0.01, 9999999.99)
        self.price_spin.setDecimals(2)
        self.price_spin.setValue(self.batch.cost_price)
        self.price_spin.setPrefix("ETB ")
        self.price_spin.setMinimumHeight(35)
        form.addRow("New Unit Price:", self.price_spin)

        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(80)
        self.note_edit.setPlaceholderText("Reason for discount...")
        form.addRow("Note:", self.note_edit)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Apply Discount")
        save_btn.setStyleSheet(
            "background-color: #27ae60; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;"
        )
        save_btn.clicked.connect(self.apply_discount)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def apply_discount(self):
        new_price = self.price_spin.value()
        if new_price >= self.batch.cost_price:
            QMessageBox.warning(self, "Invalid", "Discount must lower the unit price.")
            return

        # Store values so the caller can retrieve them
        self.new_price = new_price
        self.note = self.note_edit.toPlainText().strip()

        self.accept()