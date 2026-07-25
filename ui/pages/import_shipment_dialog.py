#!/usr/bin/env python3
"""
Import Shipment Dialog – TAB 1 ONLY (Shipment Details)
UI with modern Basic Information section (like Purchase Details dialog).
parse_excel_file()
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QFileDialog
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

# Import modern widgets from product_dialog
from ui.pages.product_dialog import ModernComboBox, ModernDoubleSpinBox, ModernLineEdit, ModernSpinBox, ProductCompleter
from ui.components.ethiopian_date import EthiopianDateEdit
from ui.components.universal_crud_dialog import UniversalCRUDDialog
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService
from services.new_product_service import NewProductService

# ------------------------------------------------------------------
# Excel Preview Dialog (UPDATED)
# ------------------------------------------------------------------
class ExcelPreviewDialog(QDialog):
    """Dialog to preview Excel data and assign local names before import."""
    
    def __init__(self, excel_data, product_service, parent=None):
        super().__init__(parent)
        self.excel_data = excel_data
        self.product_service = product_service
        self.setWindowTitle("Preview Excel Data")
        self.setModal(True)
        self.setMinimumSize(1200, 650)
        
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModal)
        
        self.init_ui()
        
    def init_ui(self):
        """Build the preview dialog UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- Title ---
        title = QLabel("📋 Verify Excel Data & Assign Local Names")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title)
        
        sub_title = QLabel("Type the local product name for each item. Autocomplete will suggest existing products from your database.")
        sub_title.setFont(QFont("Segoe UI", 10))
        sub_title.setStyleSheet("color: #7f8c8d; margin-bottom: 10px;")
        main_layout.addWidget(sub_title)
        
        # --- Table ---
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(10)
        self.preview_table.setHorizontalHeaderLabels([
            "#", "Item Code", "Local Name", "CTNS",
            "QTY", "T.QTY", "PRICE (RMB)",
            "AMOUNT (RMB)", "CBM", "T.CBM"
        ])
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeToContents)
        
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(self.preview_table)
        
        # --- Populate table ---
        self.populate_table()
        
        # --- Bottom Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.cancel_btn = QPushButton("✖ Cancel")
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
        
        self.import_btn = QPushButton("✅ Import to Shipment")
        self.import_btn.setFixedSize(180, 40)
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        self.import_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.import_btn)
        
        main_layout.addLayout(btn_layout)
    
    def populate_table(self):
        """Fill the table with Excel data and add editable Local Name fields with autocomplete."""
        self.preview_table.setRowCount(len(self.excel_data))
        
        total_cartons = 0
        total_qty = 0
        total_amount = 0.0
        total_cbm = 0.0
        
        for row, data in enumerate(self.excel_data):
            # Column 0: Row number
            self.preview_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            
            # Column 1: Item Code (full, e.g., "3033674-35cm")
            item_code = data.get("item_code", "")
            self.preview_table.setItem(row, 1, QTableWidgetItem(item_code))
            
            # Column 2: Local Name (Editable QLineEdit with Autocomplete)
            local_name_edit = QLineEdit()
            local_name_edit.setPlaceholderText("Type local product name...")
            local_name_edit.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #d1d5db;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border: 2px solid #3498db;
                }
            """)
            # --- Add autocomplete and connect signal ---
            completer = ProductCompleter(self.product_service, parent=self)
            completer.setLineEdit(local_name_edit)
            # IMPORTANT: Connect the signal to the class method
            completer.productSelected.connect(lambda pid, r=row: self.on_local_name_selected(r, pid))
            self.preview_table.setCellWidget(row, 2, local_name_edit)
            
            # Column 3: CTNS (Cartons)
            cartons = data.get("cartons", 0)
            self.preview_table.setItem(row, 3, QTableWidgetItem(str(cartons)))
            total_cartons += cartons
            
            # Column 4: QTY (per carton)
            qty_per = data.get("qty_per_carton", 0)
            self.preview_table.setItem(row, 4, QTableWidgetItem(str(qty_per)))
            
            # Column 5: T.QTY (computed: CTNS × QTY, read-only)
            total_qty_row = cartons * qty_per
            qty_item = QTableWidgetItem(str(total_qty_row))
            qty_item.setFlags(qty_item.flags() & ~Qt.ItemIsEditable)
            qty_item.setBackground(QColor(240, 240, 240))
            self.preview_table.setItem(row, 5, qty_item)
            total_qty += total_qty_row
            
            # Column 6: PRICE (Unit Price)
            unit_price = data.get("unit_price_rmb", 0.0)
            self.preview_table.setItem(row, 6, QTableWidgetItem(f"{unit_price:.2f}"))
            
            # Column 7: AMOUNT (computed: T.QTY × PRICE, read-only)
            row_amount = total_qty_row * unit_price
            total_amount += row_amount
            amt_item = QTableWidgetItem(f"{row_amount:.2f}")
            amt_item.setFlags(amt_item.flags() & ~Qt.ItemIsEditable)
            amt_item.setBackground(QColor(240, 240, 240))
            self.preview_table.setItem(row, 7, amt_item)
            
            # Column 8: CBM (per carton)
            cbm = data.get("cbm_per_carton", 0.0)
            self.preview_table.setItem(row, 8, QTableWidgetItem(f"{cbm:.3f}"))
            
            # Column 9: T.CBM (computed: CTNS × CBM, read-only)
            row_cbm = cartons * cbm
            total_cbm += row_cbm
            cbm_item = QTableWidgetItem(f"{row_cbm:.3f}")
            cbm_item.setFlags(cbm_item.flags() & ~Qt.ItemIsEditable)
            cbm_item.setBackground(QColor(240, 240, 240))
            self.preview_table.setItem(row, 9, cbm_item)
        
        # --- Add Summary Row (Footer) ---
        footer_row = self.preview_table.rowCount()
        self.preview_table.insertRow(footer_row)
        
        bold_font = QFont("Segoe UI", 10, QFont.Bold)
        
        # Label
        summary_label = QTableWidgetItem("TOTAL")
        summary_label.setFont(bold_font)
        summary_label.setBackground(QColor(230, 240, 255))
        self.preview_table.setItem(footer_row, 0, summary_label)
        
        # Span columns 1-2
        self.preview_table.setSpan(footer_row, 1, 1, 2)
        
        # CTNS total
        ctns_item = QTableWidgetItem(str(total_cartons))
        ctns_item.setFont(bold_font)
        ctns_item.setBackground(QColor(230, 240, 255))
        self.preview_table.setItem(footer_row, 3, ctns_item)
        
        # T.QTY total
        qty_item = QTableWidgetItem(str(total_qty))
        qty_item.setFont(bold_font)
        qty_item.setBackground(QColor(230, 240, 255))
        self.preview_table.setItem(footer_row, 5, qty_item)
        
        # AMOUNT total
        amt_item = QTableWidgetItem(f"{total_amount:,.2f}")
        amt_item.setFont(bold_font)
        amt_item.setBackground(QColor(230, 240, 255))
        amt_item.setForeground(QColor(39, 174, 96))  # Green
        self.preview_table.setItem(footer_row, 7, amt_item)
        
        # T.CBM total
        cbm_item = QTableWidgetItem(f"{total_cbm:.3f}")
        cbm_item.setFont(bold_font)
        cbm_item.setBackground(QColor(230, 240, 255))
        cbm_item.setForeground(QColor(52, 152, 219))  # Blue
        self.preview_table.setItem(footer_row, 9, cbm_item)
    
    # ------------------------------------------------------------------
    # This is a proper class method (NOT nested inside populate_table)
    # ------------------------------------------------------------------
    def on_local_name_selected(self, row, product_id):
        """
        Called when a product is selected from autocomplete.
        You can use this to auto-fill other fields like Unit.
        """
        product = self.product_service.get_by_id(product_id)
        if product:
            # For example, auto-fill unit in the main table later
            # Right now we just store the selection
            pass
    
    def get_import_data(self):
        """Extract the data from the table, including the local names."""
        imported = []
        # Stop before the summary row (last row)
        for row in range(self.preview_table.rowCount() - 1):
            # Get the Local Name
            local_name_widget = self.preview_table.cellWidget(row, 2)
            local_name = local_name_widget.text().strip() if local_name_widget else ""
            
            if not local_name:
                continue
            
            # Get other data (columns: 1=Item Code, 3=CTNS, 4=QTY, 6=PRICE, 8=CBM)
            item_code = self.preview_table.item(row, 1).text() if self.preview_table.item(row, 1) else ""
            cartons = int(self.preview_table.item(row, 3).text()) if self.preview_table.item(row, 3) else 0
            qty_per = int(self.preview_table.item(row, 4).text()) if self.preview_table.item(row, 4) else 0
            unit_price = float(self.preview_table.item(row, 6).text()) if self.preview_table.item(row, 6) else 0.0
            cbm = float(self.preview_table.item(row, 8).text()) if self.preview_table.item(row, 8) else 0.0
            
            imported.append({
                "item_number": item_code,
                "product_name": local_name,
                "unit": "pcs",
                "cartons": cartons,
                "qty_per_carton": qty_per,
                "unit_price_rmb": unit_price,
                "cbm_per_carton": cbm,
            })
        return imported
    
# ------------------------------------------------------------------
# Add Product Line Dialog (used by ImportShipmentDialog)
# ------------------------------------------------------------------
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
        self.completer = ProductCompleter(self.product_service, parent=self)
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


# ------------------------------------------------------------------
# Main Import Shipment Dialog
# ------------------------------------------------------------------
class ImportShipmentDialog(QDialog):
    """Single-tab dialog for shipment details (UI only)."""

    def __init__(self, parent=None, current_user=None, mode="create", shipment_id=None):
        super().__init__(parent)
        self.current_user = current_user
        self.mode = mode          # 'create', 'edit', 'view'
        self.shipment_id = shipment_id
        self.product_service = NewProductService()
        self._updating = False

        # Enable minimize and maximize buttons
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModal)

        self.setWindowTitle("Import Shipment" if mode != "view" else "View Shipment")
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

        self.init_ui()

    def init_ui(self):
        """Build the UI with a single tab."""
        main_layout = QVBoxLayout(self)

        # ----- Tab 1: Shipment Details -----
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ---- Basic Information Section (MODERN) ----
        header_group = QGroupBox("Basic Information")
        header_layout = QFormLayout(header_group)

        # Supplier: ModernComboBox + Add button
        supplier_container = QWidget()
        supplier_layout = QHBoxLayout(supplier_container)
        supplier_layout.setContentsMargins(0, 0, 0, 0)
        supplier_layout.setSpacing(5)

        self.supplier_combo = ModernComboBox("Supplier")
        self.supplier_combo.combo_box.setEditable(True)
        self.supplier_combo.combo_box.lineEdit().setPlaceholderText("Select or type supplier...")
        supplier_layout.addWidget(self.supplier_combo, 1)

        self.add_supplier_btn = QPushButton("+")
        self.add_supplier_btn.setFixedSize(45, 45)
        self.add_supplier_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white;
                border: none; border-radius: 8px; font-weight: bold; font-size: 18px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.add_supplier_btn.clicked.connect(self.open_supplier_dialog)
        supplier_layout.addWidget(self.add_supplier_btn)

        header_layout.addRow("Supplier:", supplier_container)

        # Bank: ModernComboBox (no + button for now)
        bank_container = QWidget()
        bank_layout = QHBoxLayout(bank_container)
        bank_layout.setContentsMargins(0, 0, 0, 0)
        bank_layout.setSpacing(5)

        self.bank_combo = ModernComboBox("LC Bank")
        self.bank_combo.combo_box.setEditable(True)
        self.bank_combo.combo_box.lineEdit().setPlaceholderText("Select or type bank...")
        bank_layout.addWidget(self.bank_combo, 1)

        header_layout.addRow("LC Bank:", bank_container)

        # Proforma Date: EthiopianDateEdit
        self.date_edit = EthiopianDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        header_layout.addRow("Proforma Date:", self.date_edit)

        # Exchange Rate: ModernDoubleSpinBox
        self.rate_spin = ModernDoubleSpinBox("Exchange Rate", 0.01, 200.0, 4, "")
        self.rate_spin.spin_box.setValue(7.85)
        self.rate_spin.spin_box.setPrefix("1 RMB = ")
        self.rate_spin.spin_box.setSuffix(" ETB")
        header_layout.addRow("Exchange Rate:", self.rate_spin)

        layout.addWidget(header_group)

        # ---- Product Table (NOW WITH 10 COLUMNS) ----
        products_group = QGroupBox("Products")
        products_layout = QVBoxLayout(products_group)

        self.product_table = QTableWidget()
        self.product_table.setColumnCount(10)
        self.product_table.setHorizontalHeaderLabels([
            "Item #", "Product Name", "Unit", "Cartons",
            "Qty/Carton", "Total Qty", "Unit Price (RMB)",
            "Total Amount (RMB)", "CBM/Carton", "Total CBM"
        ])
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.product_table.setAlternatingRowColors(True)
        # Connect item changed signal for auto-calculation
        self.product_table.itemChanged.connect(self.on_table_item_changed)
        products_layout.addWidget(self.product_table)

        # ---- Product Toolbar ----
        prod_btn_layout = QHBoxLayout()
        self.add_prod_btn = QPushButton("➕ Add Product")
        self.add_prod_btn.clicked.connect(self.open_add_product_dialog)

        self.import_excel_btn = QPushButton("📂 Import from Excel")
        self.import_excel_btn.clicked.connect(self.open_excel_import_dialog)

        self.remove_prod_btn = QPushButton("🗑️ Remove Selected")
        self.remove_prod_btn.clicked.connect(self.remove_selected_product)

        prod_btn_layout.addWidget(self.add_prod_btn)
        prod_btn_layout.addWidget(self.import_excel_btn)
        prod_btn_layout.addWidget(self.remove_prod_btn)
        prod_btn_layout.addStretch()
        products_layout.addLayout(prod_btn_layout)

        layout.addWidget(products_group)

        # ---- Bottom Buttons ----
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save Draft")
        self.save_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 8px 20px;")
        self.save_btn.clicked.connect(lambda: QMessageBox.information(self, "Coming Soon", "Save logic will be implemented in the next phase."))

        self.cancel_btn = QPushButton("✖ Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Add the tab to the main layout
        main_layout.addWidget(tab)

        # If viewing, disable editing
        if self.mode == "view":
            self.set_read_only(True)

        # Populate combos with real data from database
        self.populate_suppliers()
        self.populate_banks()

    # ------------------------------------------------------------------
    # Populate combo boxes from database
    # ------------------------------------------------------------------
    def populate_suppliers(self):
        """Load suppliers from database into ModernComboBox."""
        service = SupplierService()
        suppliers = service.get_all()
        self.supplier_combo.clear()
        self.supplier_combo.addItem("Select Supplier", None)
        for sup in suppliers:
            self.supplier_combo.addItem(sup.supplier_name, sup.id)

    def populate_banks(self):
        """Load bank accounts from database into ModernComboBox."""
        service = BankAccountService()
        banks = service.get_all()
        self.bank_combo.clear()
        self.bank_combo.addItem("Select Bank", None)
        for bank in banks:
            display = f"{bank.bank_name} - {bank.account_name}"
            self.bank_combo.addItem(display, bank.id)

    # ------------------------------------------------------------------
    # Open dialogs for adding new suppliers/banks
    # ------------------------------------------------------------------
    def open_supplier_dialog(self):
        """Open UniversalCRUDDialog for suppliers."""
        dialog = UniversalCRUDDialog('supplier', SupplierService, self)
        if dialog.exec():
            self.populate_suppliers()

    # ------------------------------------------------------------------
    # Product Table Actions
    # ------------------------------------------------------------------
    def open_add_product_dialog(self):
        """Open the dialog to add a product line."""
        dialog = AddProductLineDialog(self.product_service, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            self.add_product_row_to_table(data)

    def add_product_row_to_table(self, data):
        """Add a product row to the table using the provided data."""
        self.product_table.blockSignals(True)
        
        row = self.product_table.rowCount()
        self.product_table.insertRow(row)
        
        # Column 0: Item #
        self.product_table.setItem(row, 0, QTableWidgetItem(data.get("item_number", "")))
        
        # Column 1: Product Name
        self.product_table.setItem(row, 1, QTableWidgetItem(data["product_name"]))
        
        # Column 2: Unit (ComboBox)
        unit_combo = QComboBox()
        unit_combo.addItems(["pcs", "kg", "set", "box", "m", "L"])
        idx = unit_combo.findText(data.get("unit", "pcs"))
        if idx >= 0:
            unit_combo.setCurrentIndex(idx)
        self.product_table.setCellWidget(row, 2, unit_combo)
        
        # Column 3: Cartons
        self.product_table.setItem(row, 3, QTableWidgetItem(str(data["cartons"])))
        
        # Column 4: Qty/Carton
        self.product_table.setItem(row, 4, QTableWidgetItem(str(data["qty_per_carton"])))
        
        # Column 5: Total Qty (calculated, read-only)
        total_qty = data["cartons"] * data["qty_per_carton"]
        qty_item = QTableWidgetItem(str(total_qty))
        qty_item.setFlags(qty_item.flags() & ~Qt.ItemIsEditable)
        qty_item.setBackground(QColor(240, 240, 240))
        self.product_table.setItem(row, 5, qty_item)
        
        # Column 6: Unit Price (RMB)
        self.product_table.setItem(row, 6, QTableWidgetItem(f"{data['unit_price_rmb']:.2f}"))
        
        # Column 7: Total Amount (RMB) (calculated, read-only) - NEW!
        total_amount = total_qty * data["unit_price_rmb"]
        amount_item = QTableWidgetItem(f"{total_amount:.2f}")
        amount_item.setFlags(amount_item.flags() & ~Qt.ItemIsEditable)
        amount_item.setBackground(QColor(240, 240, 240))
        self.product_table.setItem(row, 7, amount_item)
        
        # Column 8: CBM/Carton
        self.product_table.setItem(row, 8, QTableWidgetItem(f"{data.get('cbm_per_carton', 0.0):.3f}"))
        
        # Column 9: Total CBM (calculated, read-only)
        total_cbm = data["cartons"] * data.get("cbm_per_carton", 0.0)
        cbm_item = QTableWidgetItem(f"{total_cbm:.3f}")
        cbm_item.setFlags(cbm_item.flags() & ~Qt.ItemIsEditable)
        cbm_item.setBackground(QColor(240, 240, 240))
        self.product_table.setItem(row, 9, cbm_item)
        
        self.product_table.blockSignals(False)

    def remove_selected_product(self):
        """Remove the currently selected product row from the table."""
        selected = self.product_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select a row to remove.")
            return

        row = selected[0].row()
        self.product_table.removeRow(row)

        # If no rows left, add an empty row so the user can add more
        if self.product_table.rowCount() == 0:
            self.product_table.setRowCount(1)
            for col in range(self.product_table.columnCount()):
                self.product_table.setItem(0, col, QTableWidgetItem(""))

    def on_table_item_changed(self, item):
        """
        Auto-calculate Total Qty, Total Amount, and Total CBM.
        Triggered when Cartons, Qty/Carton, Unit Price, or CBM/Carton changes.
        """
        if self._updating:
            return
        
        row = item.row()
        col = item.column()
        
        # Only react to changes in Cartons (3), Qty/Carton (4), Unit Price (6), or CBM/Carton (8)
        if col not in (3, 4, 6, 8):
            return
        
        self._updating = True
        try:
            # Get the current values
            cartons_item = self.product_table.item(row, 3)
            qty_per_item = self.product_table.item(row, 4)
            price_item = self.product_table.item(row, 6)
            cbm_item = self.product_table.item(row, 8)
            
            if not all([cartons_item, qty_per_item, price_item, cbm_item]):
                return
            
            cartons = float(cartons_item.text() or 0)
            qty_per = float(qty_per_item.text() or 0)
            unit_price = float(price_item.text() or 0)
            cbm = float(cbm_item.text() or 0)
            
            # Calculate totals
            total_qty = int(cartons * qty_per)
            total_amount = total_qty * unit_price
            total_cbm = cartons * cbm
            
            # Update Total Qty (column 5)
            total_qty_item = self.product_table.item(row, 5)
            if total_qty_item:
                total_qty_item.setText(str(total_qty))
            
            # Update Total Amount (column 7) - NEW!
            total_amt_item = self.product_table.item(row, 7)
            if total_amt_item:
                total_amt_item.setText(f"{total_amount:.2f}")
            
            # Update Total CBM (column 9)
            total_cbm_item = self.product_table.item(row, 9)
            if total_cbm_item:
                total_cbm_item.setText(f"{total_cbm:.3f}")
        
        except Exception:
            # Silently ignore conversion errors (e.g., empty cells)
            pass
        finally:
            self._updating = False

    # ------------------------------------------------------------------
    # Excel Import
    # ------------------------------------------------------------------
    def parse_excel_file(self, file_path):
        """Parse the Excel file and return a list of product dicts."""
        try:
            import pandas as pd
        except ImportError:
            QMessageBox.critical(self, "Error", "pandas library is required. Please install: pip install pandas openpyxl")
            return []
        
        try:
            df = pd.read_excel(file_path, header=None)
        except Exception as e:
            QMessageBox.critical(self, "Read Error", f"Could not read Excel file:\n{str(e)}")
            return []
        
        # --- Step 1: Find the header row ---
        header_row = None
        for idx, row in df.iterrows():
            row_text = " ".join(str(v) for v in row.values if pd.notna(v))
            if ("ITEM NO" in row_text or "产品名称" in row_text) and "CTNS" in row_text and "QTY" in row_text:
                header_row = idx
                break
        
        if header_row is None:
            QMessageBox.warning(self, "Format Error", 
                            "Header row not found.\n"
                            "Ensure the Excel contains columns: 'ITEM NO', 'CTNS', 'QTY', 'PRICE', 'CBM'")
            return []
        
        # --- Step 2: Map columns with SUBSTRING matching (and exclude total columns) ---
        header = df.iloc[header_row]
        col_map = {}
        
        print("=== EXCEL HEADER ===")
        for i, col_name in enumerate(header):
            col_str = str(col_name).strip() if pd.notna(col_name) else ""
            print(f"  Column {i}: '{col_str}'")
        
        for i, col_name in enumerate(header):
            col_str = str(col_name).strip() if pd.notna(col_name) else ""
            if not col_str:
                continue
            
            col_upper = col_str.upper()
            
            # NAME columns
            if "ITEM" in col_upper or "产品" in col_upper or "NAME" in col_upper or "名称" in col_upper:
                col_map["name"] = i
                print(f"  -> 'name' mapped to column {i} ('{col_str}')")
            # CTNS columns
            elif "CTNS" in col_upper or "件数" in col_upper or "CARTON" in col_upper:
                col_map["cartons"] = i
                print(f"  -> 'cartons' mapped to column {i} ('{col_str}')")
            # QTY columns: must contain "QTY" or "装箱", but exclude "T." or "T.QTY"
            elif ("QTY" in col_upper or "装箱" in col_upper) and not col_upper.startswith("T.") and "T.QTY" not in col_upper:
                col_map["qty_per"] = i
                print(f"  -> 'qty_per' mapped to column {i} ('{col_str}')")
            # PRICE columns
            elif "PRICE" in col_upper or "单价" in col_upper:
                col_map["price"] = i
                print(f"  -> 'price' mapped to column {i} ('{col_str}')")
            # CBM columns: must contain "CBM" or "体积", but exclude "T." or "T.CBM"
            elif ("CBM" in col_upper or "体积" in col_upper) and not col_upper.startswith("T.") and "T.CBM" not in col_upper:
                col_map["cbm_per"] = i
                print(f"  -> 'cbm_per' mapped to column {i} ('{col_str}')")
        
        # --- Step 3: Verify required columns found ---
        required = ["name", "cartons", "qty_per", "price"]
        missing = [r for r in required if r not in col_map]
        
        if missing:
            found_info = ", ".join([f"{k}: '{header[v]}'" for k, v in col_map.items()])
            QMessageBox.warning(self, "Format Error", 
                            f"Required columns not found: {', '.join(missing)}\n\n"
                            f"Found columns: {found_info}\n\n"
                            "Need: 'ITEM NO', 'CTNS', 'QTY', 'PRICE' (and optionally 'CBM')")
            return []
        
        # --- Step 4: Extract product data ---
        products = []
        
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            raw_name = str(row[col_map["name"]]) if pd.notna(row[col_map["name"]]) else ""
            if not raw_name.strip() or raw_name.strip().lower().startswith("total"):
                break
            
            item_code = raw_name.strip()
            
            try:
                cartons = int(float(row[col_map["cartons"]]))
                qty_per = int(float(row[col_map["qty_per"]]))
                price = float(row[col_map["price"]])
                # Get CBM if column exists, else 0.0
                if "cbm_per" in col_map and pd.notna(row[col_map["cbm_per"]]):
                    # Try to convert to float; if it fails, default to 0.0
                    try:
                        cbm = float(row[col_map["cbm_per"]])
                    except (ValueError, TypeError):
                        cbm = 0.0
                else:
                    cbm = 0.0
            except (ValueError, TypeError) as e:
                continue
            
            if cartons <= 0 or qty_per <= 0 or price <= 0:
                continue
            
            products.append({
                "item_code": item_code,
                "cartons": cartons,
                "qty_per_carton": qty_per,
                "unit_price_rmb": price,
                "cbm_per_carton": cbm,
            })
        
        print(f"=== EXTRACTED {len(products)} PRODUCTS ===")
        if products:
            print(f"First product: {products[0]}")
        
        return products

    def open_excel_import_dialog(self):
        """Open file dialog, parse Excel, and show preview dialog."""
        from PySide6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Proforma Excel File",
            "",
            "Excel Files (*.xlsx *.xls)"
        )
        if not file_path:
            return
        
        # Parse the Excel file
        excel_data = self.parse_excel_file(file_path)
        if not excel_data:
            return
        
        # Show preview dialog (pass product_service for autocomplete)
        preview = ExcelPreviewDialog(excel_data, self.product_service, self)
        if preview.exec() == QDialog.Accepted:
            imported_products = preview.get_import_data()
            if not imported_products:
                QMessageBox.information(self, "No Data", "No products with local names were selected for import.")
                return
            
            # Add each product to the main table
            for product_data in imported_products:
                self.add_product_row_to_table(product_data)
            
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {len(imported_products)} products."
            )

    # ------------------------------------------------------------------
    # Read-only mode
    # ------------------------------------------------------------------
    def set_read_only(self, enabled):
        """Make all widgets read-only."""
        for widget in self.findChildren(QComboBox):
            widget.setEnabled(not enabled)
        for widget in self.findChildren(QDateEdit):
            widget.setEnabled(not enabled)
        for widget in self.findChildren(QDoubleSpinBox):
            widget.setEnabled(not enabled)
        for widget in self.findChildren(QSpinBox):
            widget.setEnabled(not enabled)
        for widget in self.findChildren(QPushButton):
            widget.setEnabled(not enabled)
        self.product_table.setEditTriggers(
            QTableWidget.NoEditTriggers if enabled else QTableWidget.DoubleClicked
        )
        self.save_btn.setVisible(not enabled)