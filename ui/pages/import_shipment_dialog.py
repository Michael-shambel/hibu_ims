#!/usr/bin/env python3
"""
Import Shipment Dialog – TAB 1 ONLY (Shipment Details)
UI with modern Basic Information section (like Purchase Details dialog).
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

# Import modern widgets from product_dialog
from ui.pages.product_dialog import ModernComboBox, ModernDoubleSpinBox
from ui.components.ethiopian_date import EthiopianDateEdit
from ui.components.universal_crud_dialog import UniversalCRUDDialog
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService


class ImportShipmentDialog(QDialog):
    """Single-tab dialog for shipment details (UI only)."""

    def __init__(self, parent=None, current_user=None, mode="create", shipment_id=None):
        super().__init__(parent)
        self.current_user = current_user
        self.mode = mode          # 'create', 'edit', 'view'
        self.shipment_id = shipment_id

        # --- ADD THIS BLOCK ---
        # Enable minimize and maximize buttons
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        # Keep it modal so it blocks the main window
        self.setWindowModality(Qt.WindowModal)
        # -----------------------

        self.setWindowTitle("Import Shipment" if mode != "view" else "View Shipment")
        # Remove or keep the min size; since we want full screen, we set min to 0
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

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

        # Bank: ModernComboBox + Add button
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

        # ---- Product Table (unchanged) ----
        products_group = QGroupBox("Products")
        products_layout = QVBoxLayout(products_group)

        self.product_table = QTableWidget()
        self.product_table.setColumnCount(9)
        self.product_table.setHorizontalHeaderLabels([
            "Item #", "Product Name", "Unit", "Cartons",
            "Qty/Carton", "Total Qty", "Unit Price (RMB)",
            "CBM/Carton", "Total CBM"
        ])
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.product_table.setAlternatingRowColors(True)
        products_layout.addWidget(self.product_table)

        # ---- Product Toolbar ----
        prod_btn_layout = QHBoxLayout()
        self.add_prod_btn = QPushButton("➕ Add Product")
        self.add_prod_btn.clicked.connect(lambda: QMessageBox.information(self, "Coming Soon", "Add product dialog will be implemented in the next phase."))
        self.import_excel_btn = QPushButton("📂 Import from Excel")
        self.import_excel_btn.clicked.connect(lambda: QMessageBox.information(self, "Coming Soon", "Excel import will be implemented in the next phase."))
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

    def open_supplier_dialog(self):
        """Open UniversalCRUDDialog for suppliers."""
        dialog = UniversalCRUDDialog('supplier', SupplierService, self)
        if dialog.exec():
            self.populate_suppliers()

    def remove_selected_product(self):
        selected =  self.product_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a product row to remove.")
            return
        row = selected[0].row()
        self.product_table.removeRow(row)

        if self.product_table.rowCount() == 0:
            self.product_table.setRowCount(1)

            for col in range(self.product_table.columnCount()):
                self.product_table.setItem(0, col, QTableWidgetItem(""))

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