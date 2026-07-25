from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from ui.pages.product_dialog import ModernLineEdit, ProductCompleter

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
        
        # --- Set default row height for ALL rows ---
        self.preview_table.verticalHeader().setDefaultSectionSize(70)  # <-- LARGE ROWS
        
        total_cartons = 0
        total_qty = 0
        total_amount = 0.0
        total_cbm = 0.0
        
        for row, data in enumerate(self.excel_data):
            # Column 0: Row number
            self.preview_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            
            # Column 1: Item Code
            item_code = data.get("item_code", "")
            self.preview_table.setItem(row, 1, QTableWidgetItem(item_code))
            
            # Column 2: Local Name (ModernLineEdit with Autocomplete)
            local_name_edit = ModernLineEdit("Local Name", "Type local product name...")
            local_name_edit.setMinimumHeight(55)  # <-- TALL ENOUGH FOR EASY TYPING
            
            # Set up the completer
            completer = ProductCompleter(self.product_service, parent=self)
            completer.setLineEdit(local_name_edit.line_edit)
            completer.productSelected.connect(lambda pid, r=row: self.on_local_name_selected(r, pid))
            local_name_edit.textChanged.connect(completer.update)
            self.preview_table.setCellWidget(row, 2, local_name_edit)
            
            # Column 3: CTNS
            cartons = data.get("cartons", 0)
            self.preview_table.setItem(row, 3, QTableWidgetItem(str(cartons)))
            total_cartons += cartons
            
            # Column 4: QTY
            qty_per = data.get("qty_per_carton", 0)
            self.preview_table.setItem(row, 4, QTableWidgetItem(str(qty_per)))
            
            # Column 5: T.QTY (computed)
            total_qty_row = cartons * qty_per
            qty_item = QTableWidgetItem(str(total_qty_row))
            qty_item.setFlags(qty_item.flags() & ~Qt.ItemIsEditable)
            qty_item.setBackground(QColor(240, 240, 240))
            self.preview_table.setItem(row, 5, qty_item)
            total_qty += total_qty_row
            
            # Column 6: PRICE
            unit_price = data.get("unit_price_rmb", 0.0)
            self.preview_table.setItem(row, 6, QTableWidgetItem(f"{unit_price:.2f}"))
            
            # Column 7: AMOUNT (computed)
            row_amount = total_qty_row * unit_price
            total_amount += row_amount
            amt_item = QTableWidgetItem(f"{row_amount:.2f}")
            amt_item.setFlags(amt_item.flags() & ~Qt.ItemIsEditable)
            amt_item.setBackground(QColor(240, 240, 240))
            self.preview_table.setItem(row, 7, amt_item)
            
            # Column 8: CBM
            cbm = data.get("cbm_per_carton", 0.0)
            self.preview_table.setItem(row, 8, QTableWidgetItem(f"{cbm:.3f}"))
            
            # Column 9: T.CBM (computed)
            row_cbm = cartons * cbm
            total_cbm += row_cbm
            cbm_item = QTableWidgetItem(f"{row_cbm:.3f}")
            cbm_item.setFlags(cbm_item.flags() & ~Qt.ItemIsEditable)
            cbm_item.setBackground(QColor(240, 240, 240))
            self.preview_table.setItem(row, 9, cbm_item)
        
        # --- Add Summary Row (Footer) ---
        footer_row = self.preview_table.rowCount()
        self.preview_table.insertRow(footer_row)
        self.preview_table.setRowHeight(footer_row, 50)  # <-- SUMMARY ROW HEIGHT (slightly smaller)
        
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
    # Method called when a product is selected from autocomplete
    # ------------------------------------------------------------------
    def on_local_name_selected(self, row, product_id):
        """
        Called when a product is selected from autocomplete.
        You can auto-fill other fields here if needed.
        """
        product = self.product_service.get_by_id(product_id)
        if product:
            # Optionally, you could pre-fill the Unit field in the main table
            # For now, we just store the selection
            pass
    
    def get_import_data(self):
        """Extract the data from the table, including the local names."""
        imported = []
        # Stop before the summary row (last row)
        for row in range(self.preview_table.rowCount() - 1):
            # Get the Local Name from ModernLineEdit
            local_name_widget = self.preview_table.cellWidget(row, 2)
            if isinstance(local_name_widget, ModernLineEdit):
                local_name = local_name_widget.text().strip()
            else:
                local_name = local_name_widget.text().strip() if hasattr(local_name_widget, 'text') else ""
            
            # Get other data (columns: 1=Item Code, 3=CTNS, 4=QTY, 6=PRICE, 8=CBM)
            item_code = self.preview_table.item(row, 1).text() if self.preview_table.item(row, 1) else ""
            cartons = int(self.preview_table.item(row, 3).text()) if self.preview_table.item(row, 3) else 0
            qty_per = int(self.preview_table.item(row, 4).text()) if self.preview_table.item(row, 4) else 0
            unit_price = float(self.preview_table.item(row, 6).text()) if self.preview_table.item(row, 6) else 0.0
            cbm = float(self.preview_table.item(row, 8).text()) if self.preview_table.item(row, 8) else 0.0
            
            # Use local_name (which may be empty) – do NOT fall back to item_code
            imported.append({
                "item_number": item_code,
                "product_name": local_name,  # May be empty
                "unit": "pcs",
                "cartons": cartons,
                "qty_per_carton": qty_per,
                "unit_price_rmb": unit_price,
                "cbm_per_carton": cbm,
            })
        return imported