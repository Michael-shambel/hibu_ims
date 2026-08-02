from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QTabWidget
)
from ui.pages.product_dialog import (
    ModernComboBox, ModernDoubleSpinBox, ModernLineEdit, ModernSpinBox,
    ProductCompleter, PurchaseDetailsDialog
)
from ui.components.ethiopian_date import EthiopianDateEdit
from .add_product_dialog import AddProductLineDialog
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from ui.pages.product_dialog import ModernLineEdit, ProductCompleter
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService

class Tab1SetupMixin:
    """Contains setup_tab1 and product table methods."""

    def setup_tab1(self):
        """Build Tab 1: Shipment Details."""
        tab1 = QWidget()
        layout = QVBoxLayout(tab1)

        # ---- Basic Information Section (Compact) ----
        header_group = QGroupBox("Basic Information")
        header_layout = QFormLayout(header_group)

        # ---- Button to open the PurchaseDetailsDialog (supplier, payment status, bank, date) ----
        self.basic_info_btn = QPushButton("📋 Set Supplier & Payment Details")
        self.basic_info_btn.setMinimumHeight(40)
        self.basic_info_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.basic_info_btn.clicked.connect(self.open_basic_info_dialog)

        # Summary label (will show selected details)
        self.basic_info_summary = QLabel("No supplier/payment details set. Click the button above.")
        self.basic_info_summary.setWordWrap(True)
        self.basic_info_summary.setStyleSheet("color: #7f8c8d; font-size: 12px;")

        header_layout.addRow(self.basic_info_btn)
        header_layout.addRow(self.basic_info_summary)

        # Exchange Rate: ModernDoubleSpinBox (keep visible)
        self.rate_spin = ModernDoubleSpinBox("Exchange Rate", 0.01, 200.0, 4, "")
        self.rate_spin.spin_box.setValue(17.85)
        self.rate_spin.spin_box.setPrefix("1 RMB = ")
        self.rate_spin.spin_box.setSuffix(" ETB")
        self.rate_spin.spin_box.valueChanged.connect(self.update_total_display)
        header_layout.addRow("Exchange Rate:", self.rate_spin)

        layout.addWidget(header_group)

        # ---- Product Table (unchanged) ----
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
        # Set column widths (unchanged)
        self.product_table.setColumnWidth(0, 100)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.product_table.setColumnWidth(2, 70)
        self.product_table.setColumnWidth(3, 70)
        self.product_table.setColumnWidth(4, 80)
        self.product_table.setColumnWidth(5, 80)
        self.product_table.setColumnWidth(6, 100)
        self.product_table.setColumnWidth(7, 120)
        self.product_table.setColumnWidth(8, 80)
        self.product_table.setColumnWidth(9, 80)
        for col in [0, 2, 3, 4, 5, 6, 7, 8, 9]:
            self.product_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)

        self.product_table.setAlternatingRowColors(True)
        self.product_table.itemChanged.connect(self.on_table_item_changed)
        products_layout.addWidget(self.product_table)

        # ---- Product Toolbar (unchanged) ----
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
        self.tabs.addTab(tab1, "📄 Shipment Details")

    # ---- Open PurchaseDetailsDialog for supplier, payment status, bank, and date ----
    def open_basic_info_dialog(self):
        """Open the PurchaseDetailsDialog to set supplier, payment status, bank, and date."""
        supplier_service = SupplierService()
        bank_service = BankAccountService()

        dialog = PurchaseDetailsDialog(
            supplier_service=supplier_service,
            bank_account_service=bank_service,
            parent=self
        )
        if dialog.exec() == QDialog.Accepted:
            details = dialog.get_details()
            self.basic_info = {
                "supplier_id": details["supplier_id"],
                "payment_status": details["payment_status"],   # "paid" or "credit"
                "proforma_date": details["payment_date"],      # QDate or datetime
                "bank_account_id": details["bank_account_id"], # may be None
            }
            self.update_basic_info_summary()

    def update_basic_info_summary(self):
        """Update the summary label with the selected details."""
        if not hasattr(self, 'basic_info') or not self.basic_info:
            self.basic_info_summary.setText("No supplier/payment details set. Click the button above.")
            self.basic_info_summary.setStyleSheet("color: #7f8c8d; font-size: 12px;")
            return

        info = self.basic_info
        supplier_id = info.get('supplier_id')
        payment_status = info.get('payment_status', 'credit').capitalize()
        date_obj = info.get('proforma_date')
        bank_id = info.get('bank_account_id')

        supplier_name = self._get_supplier_name(supplier_id)
        date_str = date_obj.strftime("%d/%m/%Y") if date_obj else "N/A"
        bank_name = self._get_bank_name(bank_id) if bank_id else "Not set"

        summary = f"Supplier: {supplier_name}  |  Status: {payment_status}  |  Date: {date_str}  |  Bank: {bank_name}"
        self.basic_info_summary.setText(summary)
        self.basic_info_summary.setStyleSheet("color: #2c3e50; font-size: 12px; font-weight: bold;")

    def _get_supplier_name(self, supplier_id):
        if not supplier_id:
            return "N/A"
        supplier = SupplierService().get_by_id(supplier_id)
        return supplier.supplier_name if supplier else f"ID {supplier_id}"

    def _get_bank_name(self, bank_id):
        if not bank_id:
            return "N/A"
        bank = BankAccountService().get_by_id(bank_id)
        if bank:
            return f"{bank.bank_name} - {bank.account_name}"
        return f"ID {bank_id}"

    # ---- All other methods (add_product_row_to_table, remove_selected_product, ...) ----
    # Keep them exactly as they are in your original file – no changes required.
    # I have included them below for completeness, but they are unchanged.
    # ------------------------------------------------------------------
    def add_product_row_to_table(self, data, trigger_calculation=True):
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
        if trigger_calculation:
            self.calculate_landed()

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
        self.calculate_landed()

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
        self.calculate_landed()


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
        # self.product_table.setRowCount(1)
            
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

    def is_row_empty(self, row):
        """Check if a row is empty (no product name)."""
        name_item = self.product_table.item(row, 1)
        return name_item is None or not name_item.text().strip()

    def open_add_product_dialog(self):
        """Open the dialog to add a product line."""
        dialog = AddProductLineDialog(self.product_service, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            self.add_product_row_to_table(data)

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