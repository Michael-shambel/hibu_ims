#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QFileDialog
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from ui.pages.product_dialog import ModernComboBox, ModernDoubleSpinBox, ModernLineEdit, ModernSpinBox, ProductCompleter
from ui.components.ethiopian_date import EthiopianDateEdit
from ui.components.universal_crud_dialog import UniversalCRUDDialog
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService
from services.new_product_service import NewProductService
from services.import_shipment_service import ImportShipmentService

from .preview_dialog import ExcelPreviewDialog
from .add_product_dialog import AddProductLineDialog

import logging
logger = logging.getLogger(__name__)


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
        self.rate_spin.spin_box.setValue(17.85)
        self.rate_spin.spin_box.setPrefix("1 RMB = ")
        self.rate_spin.spin_box.setSuffix(" ETB")
        self.rate_spin.spin_box.valueChanged.connect(self.update_total_display)
        header_layout.addRow("Exchange Rate:", self.rate_spin)

        layout.addWidget(header_group)

        # ---- Product Table (NOW WITH 10 COLUMNS) ----
        products_group = QGroupBox("Products")
        products_layout = QVBoxLayout(products_group)

        self.product_table = QTableWidget()
        self.product_table.verticalHeader().setDefaultSectionSize(70)
        self.product_table.setColumnCount(10)
        self.product_table.setHorizontalHeaderLabels([
            "Item #", "Product Name", "Unit", "Cartons",
            "Qty/Carton", "Total Qty", "Unit Price (RMB)",
            "Total Amount (RMB)", "CBM/Carton", "Total CBM"
        ])
        # --- Set column widths ---
        # 0: Item # (compact)
        self.product_table.setColumnWidth(0, 100)
        # 1: Product Name (will stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # 2: Unit
        self.product_table.setColumnWidth(2, 70)
        # 3: Cartons
        self.product_table.setColumnWidth(3, 70)
        # 4: Qty/Carton
        self.product_table.setColumnWidth(4, 80)
        # 5: Total Qty
        self.product_table.setColumnWidth(5, 80)
        # 6: Unit Price (RMB)
        self.product_table.setColumnWidth(6, 100)
        # 7: Total Amount (RMB)
        self.product_table.setColumnWidth(7, 120)
        # 8: CBM/Carton
        self.product_table.setColumnWidth(8, 80)
        # 9: Total CBM
        self.product_table.setColumnWidth(9, 80)

        # For the remaining columns, set resize mode to Fixed so they don't stretch
        for col in [0, 2, 3, 4, 5, 6, 7, 8, 9]:
            self.product_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)

        self.product_table.setAlternatingRowColors(True)
        # Connect item changed signal for auto-calculation
        self.product_table.itemChanged.connect(self.on_table_item_changed)
        products_layout.addWidget(self.product_table)

        # ---- Product Toolbar ----
        prod_btn_layout = QHBoxLayout()
        self.add_prod_btn = QPushButton("➕ Add Product")
        self.add_prod_btn.setMinimumHeight(40)
        self.add_prod_btn.setMinimumWidth(140)
        self.add_prod_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498db, stop:1 #2980b9);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2980b9, stop:1 #2471a3);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2471a3, stop:1 #1a5276);
            }
        """)
        self.add_prod_btn.clicked.connect(self.open_add_product_dialog)

        self.import_excel_btn = QPushButton("📂 Import from Excel")
        self.import_excel_btn.setMinimumHeight(40)
        self.import_excel_btn.setMinimumWidth(160)
        self.import_excel_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2ecc71, stop:1 #27ae60);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #27ae60, stop:1 #219a52);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #219a52, stop:1 #1e8449);
            }
        """)
        self.import_excel_btn.clicked.connect(self.open_excel_import_dialog)

        self.remove_prod_btn = QPushButton("🗑️ Remove Selected")
        self.remove_prod_btn.setMinimumHeight(40)
        self.remove_prod_btn.setMinimumWidth(140)
        self.remove_prod_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e74c3c, stop:1 #c0392b);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c0392b, stop:1 #a93226);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a93226, stop:1 #922b21);
            }
            QPushButton:disabled {
                background: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.remove_prod_btn.clicked.connect(self.remove_selected_product)

        self.clear_all_btn = QPushButton("🗑️ Clear All")
        self.clear_all_btn.setMinimumHeight(40)
        self.clear_all_btn.setMinimumWidth(120)
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f39c12, stop:1 #e67e22);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e67e22, stop:1 #d35400);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #d35400, stop:1 #a04000);
            }
            QPushButton:disabled {
                background: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.clear_all_btn.clicked.connect(self.clear_all_rows)

        prod_btn_layout.addWidget(self.add_prod_btn)
        prod_btn_layout.addWidget(self.import_excel_btn)
        prod_btn_layout.addWidget(self.remove_prod_btn)
        prod_btn_layout.addWidget(self.clear_all_btn)
        prod_btn_layout.addStretch()

        self.total_display_label = QLabel("Total: ¥0.00 RMB  |  ETB 0.00")
        self.total_display_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.total_display_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                background-color: #f8f9fa;
                padding: 6px 16px;
                border-radius: 6px;
                border: 1px solid #e0e0e0;
            }
        """)
        self.total_display_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prod_btn_layout.addWidget(self.total_display_label)
        products_layout.addLayout(prod_btn_layout)

        layout.addWidget(products_group)

        # ---- Bottom Buttons ----
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save Draft")
        self.save_btn.setMinimumHeight(45)
        self.save_btn.setMinimumWidth(160)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2ecc71, stop:1 #27ae60);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #27ae60, stop:1 #219a52);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #219a52, stop:1 #1e8449);
            }
            QPushButton:disabled {
                background: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.save_btn.clicked.connect(self.save_shipment)

        self.cancel_btn = QPushButton("✖ Cancel")
        self.cancel_btn.setMinimumHeight(45)
        self.cancel_btn.setMinimumWidth(140)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e74c3c, stop:1 #c0392b);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c0392b, stop:1 #a93226);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a93226, stop:1 #922b21);
            }
        """)
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

    def clear_all_rows(self):
        """Clear all product rows from the table after confirmation."""
        row_count = self.product_table.rowCount()
        
        # Check if there are any actual product rows (excluding summary row)
        has_products = False
        for row in range(row_count):
            # Skip the summary row
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue
            
            # Check Cartons column (column 3) – if it has a value > 0, it's a product
            cartons_item = self.product_table.item(row, 3)
            if cartons_item:
                try:
                    cartons = float(cartons_item.text() or 0)
                    if cartons > 0:
                        has_products = True
                        break
                except ValueError:
                    pass
            
            # If Cartons is empty or 0, check if there's a Product Name (column 1)
            name_item = self.product_table.item(row, 1)
            if name_item and name_item.text().strip():
                has_products = True
                break
            
            # Check if there's a ModernLineEdit widget in column 1
            name_widget = self.product_table.cellWidget(row, 1)
            if name_widget and isinstance(name_widget, ModernLineEdit):
                if name_widget.text().strip():
                    has_products = True
                    break
        
        if not has_products:
            QMessageBox.information(self, "Table Empty", "There are no products to clear.")
            return
        
        # Confirm with the user
        reply = QMessageBox.question(
            self,
            "Confirm Clear All",
            "Are you sure you want to remove all products from this shipment?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Block signals to avoid triggering itemChanged events
        self.product_table.blockSignals(True)
        
        # Clear the summary row first
        self.clear_summary_row()
        
        # Remove all rows (keep one empty row for adding new products)
        self.product_table.setRowCount(0)
        self.product_table.setRowCount(1)
        
        # Clear all cells in the empty row
        for col in range(self.product_table.columnCount()):
            self.product_table.setItem(0, col, QTableWidgetItem(""))
        
        # Also clear any cell widgets in the empty row
        for col in range(self.product_table.columnCount()):
            self.product_table.setCellWidget(0, col, None)
        
        self.product_table.blockSignals(False)
        
        # Update totals and summary
        self.update_total_display()
        self.update_table_summary()
        
        QMessageBox.information(self, "Cleared", "All products have been removed.")

    def update_total_display(self):
        """Update the total amount display (RMB and ETB)."""
        row_count = self.product_table.rowCount()
        
        if row_count == 0:
            self.total_display_label.setText("Total: ¥0.00 RMB  |  ETB 0.00")
            return
        
        total_amount_rmb = 0.0
        
        for row in range(row_count):
            # Skip the summary row
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue
            
            # Get Total Amount (column 7)
            amount_item = self.product_table.item(row, 7)
            if amount_item:
                try:
                    amount = float(amount_item.text().replace(',', '') or 0)
                    total_amount_rmb += amount
                except ValueError:
                    pass
        
        # Get exchange rate
        exchange_rate = self.rate_spin.spin_box.value()
        total_amount_etb = total_amount_rmb * exchange_rate
        
        # Update the display
        self.total_display_label.setText(
            f"Total: ¥{total_amount_rmb:,.2f} RMB  |  ETB {total_amount_etb:,.2f}"
        )
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
        
        # Column 0: Item # (plain text)
        self.product_table.setItem(row, 0, QTableWidgetItem(data.get("item_number", "")))
        
        # Column 1: Product Name (Editable with Autocomplete)
        name_edit = ModernLineEdit("Product Name", "Type local product name...")
        name_edit.setText(data.get("product_name", ""))
        name_edit.setMinimumHeight(35)
        
        # Set up completer
        completer = ProductCompleter(self.product_service, parent=self)
        completer.setLineEdit(name_edit.line_edit)
        completer.productSelected.connect(lambda pid, r=row: self.on_product_selected_in_table(r, pid))
        name_edit.textChanged.connect(completer.update)
        self.product_table.setCellWidget(row, 1, name_edit)
        
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
        
        # Column 7: Total Amount (RMB) (calculated, read-only)
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
        self.update_table_summary()
        self.update_total_display()

    def remove_selected_product(self):
        """Remove the currently selected product row from the table."""
        selected = self.product_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select a row to remove.")
            return

        row = selected[0].row()
        self.product_table.removeRow(row)
        self.update_table_summary()
        self.update_total_display()

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
        self.update_table_summary()
        self.update_total_display()

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
        
        # Find header row
        header_row = None
        keywords = ["ITEM", "CTNS", "QTY", "PRICE", "CBM"]
        for idx, row in df.iterrows():
            row_text = " ".join(str(v) for v in row.values if pd.notna(v))
            if all(k in row_text.upper() for k in keywords):
                header_row = idx
                break
        
        if header_row is None:
            QMessageBox.warning(self, "Format Error", 
                            "Header row not found.\n"
                            "Ensure the Excel contains columns: 'ITEM NO', 'CTNS', 'QTY', 'PRICE', 'CBM'")
            return []
        
        # Map columns
        header = df.iloc[header_row]
        col_map = {}
        
        column_patterns = {
            "item_number": ["ITEM NO", "ITEM", "ITEM#", "产品编号"],
            "product_name": ["NAME", "产品名称", "DESCRIPTION", "SIZE", "DESC", "Product name", "品名"],
            "cartons": ["CTNS", "件数", "CARTON"],
            "qty_per": ["QTY", "装箱"],
            "price": ["PRICE", "单价", "price"],
            "cbm": ["CBM", "体积"],
        }
        
        for i, col_name in enumerate(header):
            col_str = str(col_name).strip().upper() if pd.notna(col_name) else ""
            if not col_str:
                continue
            for key, patterns in column_patterns.items():
                if key in col_map:
                    continue
                if any(pattern.upper() in col_str for pattern in patterns if pattern):
                    col_map[key] = i
                    break
        
        required = ["item_number", "cartons", "qty_per", "price"]
        missing = [r for r in required if r not in col_map]
        if missing:
            QMessageBox.warning(self, "Format Error", 
                            f"Required columns not found: {', '.join(missing)}")
            return []
        
        # Extract products
        products = []
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            
            # Get item number
            item_val = row[col_map["item_number"]]
            if pd.isna(item_val):
                continue
            item_number = str(item_val).strip()
            if not item_number or item_number.lower().startswith("total"):
                continue
            
            # Get product name (if available)
            if "product_name" in col_map and pd.notna(row[col_map["product_name"]]):
                product_name = str(row[col_map["product_name"]]).strip()
            else:
                product_name = item_number
            
            try:
                cartons = int(float(row[col_map["cartons"]]))
                qty_per = int(float(row[col_map["qty_per"]]))
                price = float(row[col_map["price"]])
                cbm = float(row[col_map["cbm"]]) if "cbm" in col_map and pd.notna(row[col_map["cbm"]]) else 0.0
            except (ValueError, TypeError):
                continue
            
            if cartons <= 0 or qty_per <= 0 or price <= 0:
                continue
            
            products.append({
                "item_code": item_number,
                "product_name": product_name,
                "cartons": cartons,
                "qty_per_carton": qty_per,
                "unit_price_rmb": price,
                "cbm_per_carton": cbm,
            })
        
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
            self.update_total_display()
            
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {len(imported_products)} products."
            )

    def update_table_summary(self):
        """Update the summary row at the bottom of the product table."""
        row_count = self.product_table.rowCount()
        
        # If table is empty or has only 1 row with no data, clear summary
        if row_count == 0 or (row_count == 1 and self.is_row_empty(0)):
            self.clear_summary_row()
            return
        
        total_cartons = 0
        total_amount = 0.0
        total_cbm = 0.0
        
        for row in range(row_count):
            # Skip the summary row itself (if it exists)
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue
            
            # Get Cartons (column 3)
            cartons_item = self.product_table.item(row, 3)
            if cartons_item:
                try:
                    cartons = float(cartons_item.text() or 0)
                    total_cartons += cartons
                except ValueError:
                    pass
            
            # Get Total Amount (column 7)
            amount_item = self.product_table.item(row, 7)
            if amount_item:
                try:
                    amount = float(amount_item.text().replace(',', '') or 0)
                    total_amount += amount
                except ValueError:
                    pass
            
            # Get Total CBM (column 9)
            cbm_item = self.product_table.item(row, 9)
            if cbm_item:
                try:
                    cbm = float(cbm_item.text() or 0)
                    total_cbm += cbm
                except ValueError:
                    pass
        
        # Update or create the summary row
        self.update_summary_row(total_cartons, total_amount, total_cbm)

    def is_row_empty(self, row):
        """Check if a row is empty (no product name)."""
        name_item = self.product_table.item(row, 1)
        return name_item is None or not name_item.text().strip()

    def clear_summary_row(self):
        """Remove the summary row if it exists."""
        row_count = self.product_table.rowCount()
        for row in range(row_count - 1, -1, -1):
            item = self.product_table.item(row, 0)
            if item and item.text() == "TOTAL":
                self.product_table.removeRow(row)
                break

    def update_summary_row(self, total_cartons, total_amount, total_cbm):
        """Update or create the summary row with totals."""
        # Remove existing summary row first
        self.clear_summary_row()
        
        # Add new summary row at the bottom
        row = self.product_table.rowCount()
        self.product_table.insertRow(row)
        self.product_table.setRowHeight(row, 35)
        
        # Bold font for summary
        bold_font = QFont("Segoe UI", 10, QFont.Bold)
        
        # Column 0: "TOTAL" label
        label_item = QTableWidgetItem("TOTAL")
        label_item.setFont(bold_font)
        label_item.setBackground(QColor(230, 240, 255))
        self.product_table.setItem(row, 0, label_item)
        
        # Span columns 1-2
        self.product_table.setSpan(row, 1, 1, 2)
        
        # Column 3: Total Cartons
        cartons_item = QTableWidgetItem(str(int(total_cartons)))
        cartons_item.setFont(bold_font)
        cartons_item.setBackground(QColor(230, 240, 255))
        self.product_table.setItem(row, 3, cartons_item)
        
        # Column 5: Total Qty (leave empty or show total)
        # You could also add total qty here if needed
        
        # Column 7: Total Amount
        amount_item = QTableWidgetItem(f"{total_amount:,.2f}")
        amount_item.setFont(bold_font)
        amount_item.setBackground(QColor(230, 240, 255))
        amount_item.setForeground(QColor(39, 174, 96))  # Green
        self.product_table.setItem(row, 7, amount_item)
        
        # Column 9: Total CBM
        cbm_item = QTableWidgetItem(f"{total_cbm:.3f}")
        cbm_item.setFont(bold_font)
        cbm_item.setBackground(QColor(230, 240, 255))
        cbm_item.setForeground(QColor(52, 152, 219))  # Blue
        self.product_table.setItem(row, 9, cbm_item)


    def on_product_selected_in_table(self, row, product_id):
        """When a product is selected from autocomplete in the main table, update the unit."""
        product = self.product_service.get_by_id(product_id)
        if product:
            # Update the unit combo box in column 2
            unit_combo = self.product_table.cellWidget(row, 2)
            if unit_combo and isinstance(unit_combo, QComboBox):
                idx = unit_combo.findText(product.unit or "pcs")
                if idx >= 0:
                    unit_combo.setCurrentIndex(idx)

    def get_user_id(self):
        """Extract user ID from self.current_user."""
        if not self.current_user:
            return None
        if isinstance(self.current_user, dict):
            return self.current_user.get('id')
        if hasattr(self.current_user, 'id'):
            return self.current_user.id
        return None

    def get_products_from_table(self):
        """Extract product data from the table, skipping empty rows."""
        products = []
        for row in range(self.product_table.rowCount()):
            # Skip the summary row (if it exists)
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue

            # Get product name from ModernLineEdit in column 1
            name_widget = self.product_table.cellWidget(row, 1)
            if isinstance(name_widget, ModernLineEdit):
                product_name = name_widget.text().strip()
            else:
                # Fallback: try QTableWidgetItem
                name_item = self.product_table.item(row, 1)
                product_name = name_item.text().strip() if name_item else ""

            # Skip if no product name or name is empty
            if not product_name:
                continue

            # Get Unit from combo box in column 2
            unit_combo = self.product_table.cellWidget(row, 2)
            if isinstance(unit_combo, QComboBox):
                unit = unit_combo.currentText().strip()
            else:
                unit = "pcs"

            # Get Item # (column 0)
            item_number = self.product_table.item(row, 0).text().strip() if self.product_table.item(row, 0) else ""

            # Get numeric values
            try:
                cartons = float(self.product_table.item(row, 3).text() or 0)
                qty_per = float(self.product_table.item(row, 4).text() or 0)
                unit_price_rmb = float(self.product_table.item(row, 6).text().replace(',', '') or 0)
                cbm_per_carton = float(self.product_table.item(row, 8).text() or 0)
            except ValueError:
                continue  # skip rows with invalid numbers

            if cartons <= 0 or qty_per <= 0 or unit_price_rmb <= 0:
                continue  # skip invalid rows

            products.append({
                "item_number": item_number if item_number else None,
                "product_name": product_name,
                "unit": unit,
                "cartons": int(cartons),
                "qty_per_carton": int(qty_per),
                "unit_price_rmb": unit_price_rmb,
                "cbm_per_carton": cbm_per_carton,
            })
        return products

    def save_shipment(self):
        """Validate and save the shipment as DRAFT."""
        # Validate supplier
        supplier_id = self.supplier_combo.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "Validation", "Please select a supplier.")
            return

        # Validate bank
        bank_id = self.bank_combo.currentData()
        if not bank_id:
            QMessageBox.warning(self, "Validation", "Please select a bank account.")
            return

        # Validate exchange rate
        exchange_rate = self.rate_spin.spin_box.value()
        if exchange_rate <= 0:
            QMessageBox.warning(self, "Validation", "Exchange rate must be greater than 0.")
            return

        # Get user ID
        user_id = self.get_user_id()
        if not user_id:
            QMessageBox.warning(self, "Validation", "User not identified. Please log in again.")
            return

        # Get products
        products = self.get_products_from_table()
        if not products:
            QMessageBox.warning(self, "Validation", "Please add at least one product.")
            return

        # Build data dict
        data = {
            "supplier_id": supplier_id,
            "bank_account_id": bank_id,
            "proforma_date": self.date_edit.date().toPython(),
            "exchange_rate": exchange_rate,
            "created_by_user_id": user_id,
            "products": products,
        }

        # Save via service
        try:
            service = ImportShipmentService()
            shipment = service.create_shipment(data)
            if shipment:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Shipment #{shipment.id} saved as DRAFT."
                )
                self.accept()  # close dialog
            else:
                QMessageBox.critical(self, "Error", "Failed to save shipment.")
        except Exception as e:
            logger.error(f"Error saving shipment: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

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