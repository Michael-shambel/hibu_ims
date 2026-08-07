from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QGroupBox, QWidget, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.pages.product_dialog import ModernLineEdit, ModernSpinBox, ModernDoubleSpinBox, ProductCompleter, ShipmentProductCompleter
class AddProductLineDialog(QDialog):
    """Dialog for adding a product line to the shipment."""
    
    def __init__(self, product_service, parent=None):
        super().__init__(parent)
        self.product_service = product_service
        self.setWindowTitle("Add Product Line")
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMaximumHeight(650)
        
        # Enable minimize/maximize
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModal)
        
        self.init_ui()
        
    def init_ui(self):
        """Build the add product dialog UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- Title ---
        title = QLabel("➕ Add Product to Shipment")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        main_layout.addWidget(title)
        
        # --- Form ---
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
        
        # Product Name (with autocomplete)
        self.name_input = ModernLineEdit("Product Name", "Start typing product name...")
        self.completer = ShipmentProductCompleter(self.product_service, parent=self)
        self.completer.setLineEdit(self.name_input.line_edit)
        self.completer.productSelected.connect(self.on_product_selected)
        self.name_input.textChanged.connect(self.completer.update)
        form_layout.addRow("Product Name:", self.name_input)
        
        # Item Number (Supplier SKU)
        self.item_number_input = ModernLineEdit("Item #", "Supplier's item number")
        form_layout.addRow("Item #:", self.item_number_input)
        
        # Unit (auto-filled by completer)
        self.unit_input = ModernLineEdit("Unit", "e.g., pcs, kg, set")
        form_layout.addRow("Unit:", self.unit_input)
        
        # Cartons
        self.cartons_input = ModernSpinBox("Cartons", 1, 10000)
        self.cartons_input.spin_box.valueChanged.connect(self.update_preview)
        form_layout.addRow("Cartons:", self.cartons_input)
        
        # Qty per Carton
        self.qty_per_input = ModernSpinBox("Qty/Carton", 1, 10000)
        self.qty_per_input.spin_box.valueChanged.connect(self.update_preview)
        form_layout.addRow("Qty/Carton:", self.qty_per_input)
        
        # Unit Price (RMB)
        self.price_input = ModernDoubleSpinBox("Unit Price (RMB)", 0.01, 1000000.0, 2, "¥")
        self.price_input.spin_box.valueChanged.connect(self.update_preview)
        form_layout.addRow("Unit Price (RMB):", self.price_input)
        
        # CBM per Carton
        self.cbm_input = ModernDoubleSpinBox("CBM/Carton", 0.0, 1000.0, 3, "")
        self.cbm_input.spin_box.valueChanged.connect(self.update_preview)
        form_layout.addRow("CBM/Carton:", self.cbm_input)
        
        main_layout.addWidget(form_widget)
        
        # --- Preview Section ---
        preview_group = QGroupBox("Preview")
        preview_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
            }
        """)
        preview_layout = QHBoxLayout(preview_group)
        
        self.preview_qty_label = QLabel("Total Qty: 0")
        self.preview_qty_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.preview_qty_label.setStyleSheet("color: #27ae60;")
        
        self.preview_cbm_label = QLabel("Total CBM: 0.000")
        self.preview_cbm_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.preview_cbm_label.setStyleSheet("color: #3498db;")
        
        preview_layout.addWidget(self.preview_qty_label)
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_cbm_label)
        
        main_layout.addWidget(preview_group)
        
        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(120, 40)
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
        
        self.add_btn = QPushButton("✅ Add to List")
        self.add_btn.setFixedSize(140, 40)
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
        
        main_layout.addLayout(btn_layout)
        
        # Initial preview
        self.update_preview()
    
    def on_product_selected(self, product_id):
        """When a product is selected via autocomplete, fill unit."""
        product = self.product_service.get_by_id(product_id)
        if product:
            self.unit_input.setText(product.unit or "")
    
    def update_preview(self):
        """Update the preview labels with current values."""
        try:
            cartons = self.cartons_input.value()
            qty_per = self.qty_per_input.value()
            cbm = self.cbm_input.value()
            
            total_qty = cartons * qty_per
            total_cbm = cartons * cbm
            
            self.preview_qty_label.setText(f"Total Qty: {total_qty:,}")
            self.preview_cbm_label.setText(f"Total CBM: {total_cbm:.3f}")
        except Exception:
            self.preview_qty_label.setText("Total Qty: 0")
            self.preview_cbm_label.setText("Total CBM: 0.000")
    
    def validate_inputs(self):
        """Validate that required fields are filled."""
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation", "Product Name is required.")
            return False
        if self.cartons_input.value() <= 0:
            QMessageBox.warning(self, "Validation", "Cartons must be greater than 0.")
            return False
        if self.qty_per_input.value() <= 0:
            QMessageBox.warning(self, "Validation", "Qty per Carton must be greater than 0.")
            return False
        if self.price_input.value() <= 0:
            QMessageBox.warning(self, "Validation", "Unit Price must be greater than 0.")
            return False
        return True
    
    def get_data(self):
        """Return the product data as a dict."""
        return {
            "item_number": self.item_number_input.text().strip() or None,
            "product_name": self.name_input.text().strip(),
            "unit": self.unit_input.text().strip() or "pcs",
            "cartons": self.cartons_input.value(),
            "qty_per_carton": self.qty_per_input.value(),
            "unit_price_rmb": self.price_input.value(),
            "cbm_per_carton": self.cbm_input.value(),
        }
    
    def accept(self):
        """Validate before closing."""
        if self.validate_inputs():
            super().accept()