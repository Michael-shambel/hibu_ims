#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QFormLayout, QWidget, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class AddCostItemDialog(QDialog):
    """Dialog for adding a new cost item (using CostType from DB)."""
    
    def __init__(self, cost_type_service, parent=None):
        super().__init__(parent)
        self.cost_type_service = cost_type_service
        self.setWindowTitle("Add Cost Item")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setMaximumHeight(350)
        
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModal)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("➕ Add Cost Item")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title)
        
        # Form
        form_widget = QWidget()
        form_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 10px;
            }
        """)
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(15)
        
        # Cost Type (ComboBox loaded from DB) + Manage button
        type_container = QWidget()
        type_layout = QHBoxLayout(type_container)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(5)

        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                background-color: white;
            }
            QComboBox:focus {
                border: 2px solid #3498db;
            }
        """)
        type_layout.addWidget(self.type_combo, 1)

        self.manage_types_btn = QPushButton("⚙️")
        self.manage_types_btn.setFixedSize(30, 30)
        self.manage_types_btn.setToolTip("Manage Cost Types")
        self.manage_types_btn.setCursor(Qt.PointingHandCursor)
        self.manage_types_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.manage_types_btn.clicked.connect(self.manage_cost_types)
        type_layout.addWidget(self.manage_types_btn)

        form_layout.addRow("Cost Type:", type_container)
        
        # Amount
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 1000000000.0)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setPrefix("ETB ")
        self.amount_spin.setStyleSheet("""
            QDoubleSpinBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                background-color: white;
            }
            QDoubleSpinBox:focus {
                border: 2px solid #3498db;
            }
        """)
        form_layout.addRow("Amount:", self.amount_spin)
        
        layout.addWidget(form_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(100, 36)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.add_btn = QPushButton("Add Cost")
        self.add_btn.setFixedSize(120, 36)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.add_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.add_btn)
        
        layout.addLayout(btn_layout)
        
        # Load initial data
        self.load_cost_types()
        self.amount_spin.setFocus()
    
    def load_cost_types(self):
        """Load cost types from the database."""
        self.type_combo.clear()
        cost_types = self.cost_type_service.get_active()
        for ct in cost_types:
            self.type_combo.addItem(ct.name, ct.id)
        # If no types, allow typing
        self.type_combo.setEditable(True)
        if self.type_combo.count() > 0:
            self.type_combo.setCurrentIndex(0)
    
    def manage_cost_types(self):
        """Open the Cost Type management dialog."""
        from ui.components.universal_crud_dialog import UniversalCRUDDialog
        from services.cost_type_service import CostTypeService
        
        dialog = UniversalCRUDDialog('cost_type', CostTypeService, self)
        if dialog.exec():
            self.load_cost_types()  # Refresh the combo box
    
    def get_data(self):
        """Return the cost data as a dict."""
        return {
            "cost_type_id": self.type_combo.currentData(),
            "cost_type_name": self.type_combo.currentText().strip(),
            "amount": self.amount_spin.value(),
        }
    
    def validate_inputs(self):
        """Validate the inputs."""
        if not self.type_combo.currentText().strip():
            QMessageBox.warning(self, "Validation", "Cost Type is required.")
            return False
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than 0.")
            return False
        return True
    
    def accept(self):
        """Validate before closing."""
        if self.validate_inputs():
            super().accept()