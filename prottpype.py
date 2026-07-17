#!/usr/bin/env python3
"""
Import Shipment Manager – ETB Landed Cost (FINAL FIX)
- Allocation matrix now correctly shows each cost separately.
- Products as rows, costs as columns.
- Total column and total row highlighted.
"""
import sys
from datetime import date
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QGroupBox, QMessageBox, QDateEdit, QAbstractItemView, QInputDialog,
    QTabWidget, QFileDialog, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# ----------------------------------------------------------------------
# Global data stores
# ----------------------------------------------------------------------
suppliers = [
    "Guangzhou Home Co.",
    "Shenzhen Electronics",
    "Shanghai Textile Group",
    "Yiwu Trading Co.",
]
banks = [
    "Commercial Bank of Ethiopia",
    "Awash Bank",
    "Dashen Bank",
    "Zemen Bank",
]
PREDEFINED_COST_TYPES = [
    "Freight",
    "Inland",
    "Transport Mojjo to Addis",
    "Freight Forwarding",
    "Office",
    "Labour (Loading/Unloading)",
    "Other Cost (Rahel...)",
    "LC Permit",
    "Demurrage",
    "Duty Tax",
    "Other Cost"
]

shipments = []

# ----------------------------------------------------------------------
# QSS Styling
# ----------------------------------------------------------------------
STYLE = """
QMainWindow { background-color: #f5f7fa; }
QGroupBox { font-weight: bold; border: 1px solid #c0c8d0; border-radius: 8px; margin-top: 1ex; padding-top: 10px; background-color: white; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px; background-color: white; }
QTableWidget { gridline-color: #d0d8e0; selection-background-color: #d9e8f7; alternate-background-color: #f9fafb; }
QHeaderView::section { background-color: #e6ecf2; padding: 4px; border: none; font-weight: bold; }
QPushButton { background-color: #e6ecf2; border: 1px solid #b0b8c0; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #d0dae6; }
QPushButton:pressed { background-color: #b0c0d0; }
QPushButton#calculateBtn { background-color: #4a7db5; color: white; }
QPushButton#calculateBtn:hover { background-color: #3a6da5; }
QPushButton#saveBtn { background-color: #28a745; color: white; }
QPushButton#saveBtn:hover { background-color: #218838; }
QPushButton#cancelBtn { background-color: #dc3545; color: white; }
QPushButton#cancelBtn:hover { background-color: #c82333; }
QLabel#totalLabel { font-size: 14pt; font-weight: bold; color: #1a3a5c; }
QLabel#grandTotal { font-size: 16pt; font-weight: bold; color: #1a6b3c; }
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QDateEdit { border: 1px solid #c0c8d0; border-radius: 4px; padding: 4px; background: white; }
QTabWidget::pane { border: 1px solid #c0c8d0; border-radius: 8px; background: white; }
QTabBar::tab { background: #e6ecf2; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: white; border-bottom: 2px solid #4a7db5; }
"""

# ----------------------------------------------------------------------
# Shipment Dialog
# ----------------------------------------------------------------------
class ShipmentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Import Shipment – ETB Landed Cost")
        self.product_lines = []
        self.cost_items = []
        self.product_allocations = []   # list of lists: per product, list of allocated amounts per cost
        self.landed_costs_per_qty = []
        self.landed_costs_per_carton = []
        self.CONTAINER_CBM = 68.0
        self.current_basis = "qty"      # 'qty' or 'carton'
        self.allocation_method = "total_cbm"  # 'fixed_68' or 'total_cbm'
        self.setStyleSheet(STYLE)
        self.init_ui()
        self._load_combos()
        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen)
        self.showMaximized()

    def _make_table_large(self, table):
        font = QFont("Segoe UI", 11)
        table.setFont(font)
        table.verticalHeader().setDefaultSectionSize(38)
        table.horizontalHeader().setFont(QFont("Segoe UI", 11, QFont.Bold))
        table.setAlternatingRowColors(True)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # ---------- Tab 1: Shipment Details ----------
        tab1 = QWidget()
        tabs.addTab(tab1, "📄 Shipment Details")
        tab1_layout = QVBoxLayout(tab1)

        basic_group = QGroupBox("Basic Information")
        basic_form = QFormLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setEditable(True)
        add_supplier_btn = QPushButton("+")
        add_supplier_btn.setFixedSize(30, 30)
        add_supplier_btn.clicked.connect(self.add_supplier)
        supplier_layout = QHBoxLayout()
        supplier_layout.addWidget(self.supplier_combo, 1)
        supplier_layout.addWidget(add_supplier_btn)

        self.bank_combo = QComboBox()
        self.bank_combo.setEditable(True)
        add_bank_btn = QPushButton("+")
        add_bank_btn.setFixedSize(30, 30)
        add_bank_btn.clicked.connect(self.add_bank)
        bank_layout = QHBoxLayout()
        bank_layout.addWidget(self.bank_combo, 1)
        bank_layout.addWidget(add_bank_btn)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())

        basic_form.addRow("Supplier:", supplier_layout)
        basic_form.addRow("LC Bank:", bank_layout)
        basic_form.addRow("Proforma Date:", self.date_edit)
        basic_group.setLayout(basic_form)
        tab1_layout.addWidget(basic_group)

        rate_group = QGroupBox("Exchange Rate")
        rate_form = QFormLayout()
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.01, 200.0)
        self.rate_spin.setDecimals(4)
        self.rate_spin.setValue(7.85)
        self.rate_spin.setPrefix("1 RMB = ")
        self.rate_spin.setSuffix(" ETB")
        self.rate_spin.valueChanged.connect(self.on_data_changed)
        rate_form.addRow("Rate:", self.rate_spin)
        rate_group.setLayout(rate_form)
        tab1_layout.addWidget(rate_group)

        products_group = QGroupBox("Products")
        prod_layout = QVBoxLayout()
        self.products_table = QTableWidget()
        self.products_table.setColumnCount(9)
        self.products_table.setHorizontalHeaderLabels([
            "Product", "Unit", "Cartons", "Qty/Carton",
            "Total Qty", "Unit Price (RMB)", "Total (RMB)",
            "Total (ETB)", "Total CBM"
        ])
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._make_table_large(self.products_table)
        prod_layout.addWidget(self.products_table)

        btn_row = QHBoxLayout()
        add_product_btn = QPushButton("➕ Add Product")
        add_product_btn.clicked.connect(self.add_product_line)
        import_excel_btn = QPushButton("📂 Import from Excel")
        import_excel_btn.clicked.connect(self.import_from_excel)
        btn_row.addWidget(add_product_btn)
        btn_row.addWidget(import_excel_btn)
        prod_layout.addLayout(btn_row)

        total_fob_layout = QHBoxLayout()
        self.total_fob_rmb_label = QLabel("Total FOB (RMB): 0.00")
        self.total_fob_rmb_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        self.total_fob_etb_label = QLabel("Total FOB (ETB): 0.00")
        self.total_fob_etb_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #1a6b3c;")
        total_fob_layout.addWidget(self.total_fob_rmb_label)
        total_fob_layout.addSpacing(30)
        total_fob_layout.addWidget(self.total_fob_etb_label)
        total_fob_layout.addStretch()
        prod_layout.addLayout(total_fob_layout)

        products_group.setLayout(prod_layout)
        tab1_layout.addWidget(products_group)
        tab1_layout.addStretch()

        # ---------- Tab 2: Cost Build‑up (all in ETB) ----------
        tab2 = QWidget()
        tabs.addTab(tab2, "💰 Cost Build‑up")
        tab2_layout = QVBoxLayout(tab2)

        cost_group = QGroupBox("Additional Costs (all in ETB)")
        cost_layout = QVBoxLayout()
        self.cost_table = QTableWidget()
        self.cost_table.setColumnCount(4)
        self.cost_table.setHorizontalHeaderLabels(["Cost Type", "Amount (ETB)", "Currency", "Allocation Basis"])
        self.cost_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._make_table_large(self.cost_table)
        cost_layout.addWidget(self.cost_table)

        add_cost_btn = QPushButton("➕ Add Cost Item")
        add_cost_btn.clicked.connect(self.add_cost_item)
        cost_layout.addWidget(add_cost_btn)

        self.total_extra_cost_label = QLabel("Total Additional Costs (ETB): 0.00")
        self.total_extra_cost_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        cost_layout.addWidget(self.total_extra_cost_label)

        cost_group.setLayout(cost_layout)
        tab2_layout.addWidget(cost_group)

        # --- Allocation Method Toggle ---
        method_group = QGroupBox("Allocation Method")
        method_layout = QHBoxLayout()
        self.fixed_68_radio = QRadioButton("Fixed 68 CBM")
        self.total_cbm_radio = QRadioButton("Total Used CBM")
        self.total_cbm_radio.setChecked(True)
        self.method_group = QButtonGroup()
        self.method_group.addButton(self.fixed_68_radio, 1)
        self.method_group.addButton(self.total_cbm_radio, 2)
        self.method_group.buttonClicked.connect(self.on_method_changed)
        method_layout.addWidget(self.fixed_68_radio)
        method_layout.addWidget(self.total_cbm_radio)
        method_layout.addStretch()
        method_group.setLayout(method_layout)
        tab2_layout.addWidget(method_group)

        # Allocation matrix (transposed: products as rows, cost items as columns)
        alloc_group = QGroupBox("Cost Allocation Breakdown (ETB)")
        alloc_layout = QVBoxLayout()
        self.alloc_table = QTableWidget()
        self.alloc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._make_table_large(self.alloc_table)
        alloc_layout.addWidget(self.alloc_table)
        alloc_group.setLayout(alloc_layout)
        tab2_layout.addWidget(alloc_group)
        tab2_layout.addStretch()

        # ---------- Tab 3: Landed Cost & Margin (all in ETB) ----------
        tab3 = QWidget()
        tabs.addTab(tab3, "📊 Landed Cost & Margin")
        tab3_layout = QVBoxLayout(tab3)

        landed_group = QGroupBox("Landed Cost per Product")
        landed_layout = QVBoxLayout()

        # Basis radio buttons
        basis_group = QGroupBox("Landed Unit Basis")
        basis_layout = QHBoxLayout()
        self.per_qty_radio = QRadioButton("Per Quantity")
        self.per_carton_radio = QRadioButton("Per Carton")
        self.per_qty_radio.setChecked(True)
        self.basis_group = QButtonGroup()
        self.basis_group.addButton(self.per_qty_radio, 1)
        self.basis_group.addButton(self.per_carton_radio, 2)
        self.basis_group.buttonClicked.connect(self.on_basis_changed)
        basis_layout.addWidget(self.per_qty_radio)
        basis_layout.addWidget(self.per_carton_radio)
        basis_layout.addStretch()
        basis_group.setLayout(basis_layout)
        landed_layout.addWidget(basis_group)

        # Table with new columns
        self.landed_table = QTableWidget()
        self.landed_table.setColumnCount(7)
        self.landed_table.setHorizontalHeaderLabels([
            "Product", "Cartons", "Qty", "FOB (ETB)",
            "Allocation (ETB)", "Total Cost (ETB)", "Landed Unit (ETB)"
        ])
        self.landed_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._make_table_large(self.landed_table)
        landed_layout.addWidget(self.landed_table)

        self.grand_total_label = QLabel("Grand Total Landed Cost (ETB): 0.00")
        self.grand_total_label.setObjectName("grandTotal")
        landed_layout.addWidget(self.grand_total_label)

        landed_group.setLayout(landed_layout)
        tab3_layout.addWidget(landed_group)

        # Margin & Pricing
        margin_group = QGroupBox("Margin & Pricing")
        margin_layout = QVBoxLayout()

        sel_layout = QHBoxLayout()
        sel_layout.addWidget(QLabel("Product:"))
        self.margin_product_combo = QComboBox()
        self.margin_product_combo.currentIndexChanged.connect(self.update_margin_display)
        sel_layout.addWidget(self.margin_product_combo, 1)
        margin_layout.addLayout(sel_layout)

        cost_display = QHBoxLayout()
        cost_display.addWidget(QLabel("Landed Unit Cost (ETB):"))
        self.margin_landed_cost_label = QLabel("0.00")
        self.margin_landed_cost_label.setStyleSheet("font-weight: bold; color: #1a6b3c;")
        cost_display.addWidget(self.margin_landed_cost_label)
        cost_display.addStretch()
        margin_layout.addLayout(cost_display)

        margin_input = QHBoxLayout()
        margin_input.addWidget(QLabel("Target Margin (%):"))
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0.0, 1000.0)
        self.margin_spin.setDecimals(2)
        self.margin_spin.setSuffix(" %")
        self.margin_spin.valueChanged.connect(self.calculate_selling_price)
        margin_input.addWidget(self.margin_spin)
        margin_input.addWidget(QLabel("Selling Price (ETB):"))
        self.calculated_selling_price_label = QLabel("0.00")
        self.calculated_selling_price_label.setStyleSheet("font-weight: bold; color: #4a7db5;")
        margin_input.addWidget(self.calculated_selling_price_label)
        margin_input.addStretch()
        margin_layout.addLayout(margin_input)

        market_layout = QHBoxLayout()
        market_layout.addWidget(QLabel("Market Price (ETB):"))
        self.market_price_spin = QDoubleSpinBox()
        self.market_price_spin.setRange(0.0, 100000000.0)
        self.market_price_spin.setDecimals(2)
        self.market_price_spin.setPrefix("ETB ")
        self.market_price_spin.valueChanged.connect(self.calculate_margin_from_market)
        market_layout.addWidget(self.market_price_spin)
        market_layout.addWidget(QLabel("Implied Margin:"))
        self.implied_margin_label = QLabel("0.00 %")
        self.implied_margin_label.setStyleSheet("font-weight: bold; color: #c07200;")
        market_layout.addWidget(self.implied_margin_label)
        market_layout.addStretch()
        margin_layout.addLayout(market_layout)

        margin_group.setLayout(margin_layout)
        tab3_layout.addWidget(margin_group)

        # Buttons
        btn_layout = QHBoxLayout()
        calculate_btn = QPushButton("🔄 Recalculate")
        calculate_btn.setObjectName("calculateBtn")
        calculate_btn.clicked.connect(self.calculate_landed)
        save_btn = QPushButton("💾 Save Proforma")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self.save_shipment)
        cancel_btn = QPushButton("✖ Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(calculate_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        # Initial data
        self.refresh_products_table()
        self.refresh_cost_table()
        self.calculate_landed()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_combos(self):
        for s in suppliers:
            self.supplier_combo.addItem(s)
        for b in banks:
            self.bank_combo.addItem(b)

    def add_supplier(self):
        name, ok = QInputDialog.getText(self, "Add Supplier", "Supplier name:")
        if ok and name.strip():
            suppliers.append(name.strip())
            self.supplier_combo.addItem(name.strip())
            self.supplier_combo.setCurrentText(name.strip())

    def add_bank(self):
        name, ok = QInputDialog.getText(self, "Add Bank", "Bank name:")
        if ok and name.strip():
            banks.append(name.strip())
            self.bank_combo.addItem(name.strip())
            self.bank_combo.setCurrentText(name.strip())

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    def add_product_line(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Product")
        form = QFormLayout(dlg)
        name_edit = QLineEdit()
        unit_combo = QComboBox()
        unit_combo.addItems(["pcs", "kg", "set", "box", "m", "L"])
        cartons_spin = QSpinBox()
        cartons_spin.setRange(1, 10000)
        qty_per_carton_spin = QSpinBox()
        qty_per_carton_spin.setRange(1, 10000)
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.01, 1000000)
        price_spin.setDecimals(2)
        price_spin.setPrefix("RMB ")
        cbm_spin = QDoubleSpinBox()
        cbm_spin.setRange(0.0, 1000.0)
        cbm_spin.setDecimals(3)
        cbm_spin.setSuffix(" CBM")

        form.addRow("Product Name:", name_edit)
        form.addRow("Unit:", unit_combo)
        form.addRow("Cartons:", cartons_spin)
        form.addRow("Qty per Carton:", qty_per_carton_spin)
        form.addRow("Unit Price (RMB):", price_spin)
        form.addRow("CBM per Carton:", cbm_spin)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        form.addRow(ok_btn)

        if dlg.exec() == QDialog.Accepted:
            cartons = cartons_spin.value()
            qty_per = qty_per_carton_spin.value()
            cbm_per = cbm_spin.value()
            product = {
                "name": name_edit.text().strip(),
                "unit": unit_combo.currentText(),
                "cartons": cartons,
                "qty_per_carton": qty_per,
                "qty": cartons * qty_per,
                "unit_price_rmb": price_spin.value(),
                "cbm_per_carton": cbm_per,
                "total_cbm": cartons * cbm_per
            }
            self.product_lines.append(product)
            self.refresh_products_table()
            self.calculate_landed()

    def import_from_excel(self):
        if not HAS_PANDAS:
            QMessageBox.warning(self, "Missing Library", "Install pandas and openpyxl")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Proforma Excel File", "",
            "Excel Files (*.xlsx *.xls)"
        )
        if not file_path:
            return
        try:
            df = pd.read_excel(file_path, header=None)
        except Exception as e:
            QMessageBox.critical(self, "Read Error", f"Could not read file:\n{str(e)}")
            return

        header_row_idx = None
        for idx, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values if pd.notna(v))
            if "ITEM NO" in row_str or "产品名称" in row_str or "CTNS" in row_str:
                header_row_idx = idx
                break
        if header_row_idx is None:
            QMessageBox.warning(self, "Format Error", "Could not locate header row.")
            return

        header = df.iloc[header_row_idx].values
        col_map = {}
        for i, col_name in enumerate(header):
            col_name = str(col_name).strip()
            if "ITEM NO" in col_name or "产品名称" in col_name:
                col_map["name"] = i
            elif "CTNS" in col_name or "件数" in col_name:
                col_map["cartons"] = i
            elif "QTY" in col_name or "装箱" in col_name:
                col_map["qty_per"] = i
            elif "PRICE" in col_name or "单价" in col_name:
                col_map["price"] = i
            elif "CBM" in col_name or "体积" in col_name:
                col_map["cbm_per"] = i

        if not all(k in col_map for k in ["name", "cartons", "qty_per", "price"]):
            QMessageBox.warning(self, "Format Error", "Required columns not found.")
            return

        products = []
        for idx in range(header_row_idx + 1, len(df)):
            row = df.iloc[idx]
            name = str(row.iloc[col_map["name"]]) if pd.notna(row.iloc[col_map["name"]]) else None
            if not name or name.strip() == "" or name.strip() == "nan":
                continue
            try:
                cartons = float(row.iloc[col_map["cartons"]]) if pd.notna(row.iloc[col_map["cartons"]]) else 0
                qty_per = float(row.iloc[col_map["qty_per"]]) if pd.notna(row.iloc[col_map["qty_per"]]) else 0
                price = float(row.iloc[col_map["price"]]) if pd.notna(row.iloc[col_map["price"]]) else 0.0
                cbm_per = float(row.iloc[col_map["cbm_per"]]) if "cbm_per" in col_map and pd.notna(row.iloc[col_map["cbm_per"]]) else 0.0
            except (ValueError, TypeError):
                continue
            if cartons <= 0 or qty_per <= 0 or price <= 0:
                continue
            total_qty = int(cartons * qty_per)
            total_cbm = cartons * cbm_per
            product = {
                "name": name.strip(),
                "unit": "pcs",
                "cartons": int(cartons),
                "qty_per_carton": int(qty_per),
                "qty": total_qty,
                "unit_price_rmb": price,
                "cbm_per_carton": cbm_per,
                "total_cbm": total_cbm
            }
            products.append(product)

        if not products:
            QMessageBox.information(self, "No Products", "No valid product rows found.")
            return
        if self.product_lines:
            reply = QMessageBox.question(
                self, "Replace Products",
                f"Replace current products with {len(products)} imported?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self.product_lines = products
        self.refresh_products_table()
        self.calculate_landed()
        QMessageBox.information(self, "Import Complete", f"Imported {len(products)} products.")

    def refresh_products_table(self):
        self.products_table.setRowCount(len(self.product_lines))
        total_fob_rmb = 0.0
        total_fob_etb = 0.0
        rate = self.rate_spin.value()
        for i, p in enumerate(self.product_lines):
            self.products_table.setItem(i, 0, QTableWidgetItem(p["name"]))
            self.products_table.setItem(i, 1, QTableWidgetItem(p["unit"]))
            self.products_table.setItem(i, 2, QTableWidgetItem(str(p["cartons"])))
            self.products_table.setItem(i, 3, QTableWidgetItem(str(p["qty_per_carton"])))
            self.products_table.setItem(i, 4, QTableWidgetItem(str(p["qty"])))
            self.products_table.setItem(i, 5, QTableWidgetItem(f"¥{p['unit_price_rmb']:.2f}"))
            total_rmb = p["qty"] * p["unit_price_rmb"]
            self.products_table.setItem(i, 6, QTableWidgetItem(f"¥{total_rmb:.2f}"))
            total_etb = total_rmb * rate
            self.products_table.setItem(i, 7, QTableWidgetItem(f"{total_etb:,.2f}"))
            self.products_table.setItem(i, 8, QTableWidgetItem(f"{p.get('total_cbm', 0):.3f}"))
            total_fob_rmb += total_rmb
            total_fob_etb += total_etb
        self.total_fob_rmb_label.setText(f"Total FOB (RMB): ¥{total_fob_rmb:,.2f}")
        self.total_fob_etb_label.setText(f"Total FOB (ETB): {total_fob_etb:,.2f}")

    # ------------------------------------------------------------------
    # Costs
    # ------------------------------------------------------------------
    def add_cost_item(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Cost Item")
        form = QFormLayout(dlg)
        type_combo = QComboBox()
        type_combo.setEditable(True)
        type_combo.addItems(PREDEFINED_COST_TYPES)
        type_combo.setCurrentIndex(0)

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0, 100000000)
        amount_spin.setDecimals(2)

        currency_combo = QComboBox()
        currency_combo.addItems(["ETB", "RMB"])
        currency_combo.setCurrentIndex(0)

        allocation_combo = QComboBox()
        allocation_combo.addItems(["By CBM", "By Value", "By Quantity", "By Weight"])
        allocation_combo.setCurrentIndex(0)

        form.addRow("Cost Type:", type_combo)
        form.addRow("Amount:", amount_spin)
        form.addRow("Currency:", currency_combo)
        form.addRow("Allocation Basis:", allocation_combo)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        form.addRow(ok_btn)

        if dlg.exec() == QDialog.Accepted:
            item = {
                "type": type_combo.currentText().strip(),
                "amount": amount_spin.value(),
                "currency": currency_combo.currentText(),
                "allocation": allocation_combo.currentText(),
            }
            self.cost_items.append(item)
            self.refresh_cost_table()
            self.calculate_landed()

    def refresh_cost_table(self):
        self.cost_table.setRowCount(len(self.cost_items))
        total_extra_etb = 0.0
        rate = self.rate_spin.value()
        for i, item in enumerate(self.cost_items):
            if item["currency"] == "RMB":
                display_amount = item["amount"] * rate
            else:
                display_amount = item["amount"]
            self.cost_table.setItem(i, 0, QTableWidgetItem(item["type"]))
            self.cost_table.setItem(i, 1, QTableWidgetItem(f"{display_amount:,.2f}"))
            self.cost_table.setItem(i, 2, QTableWidgetItem(item["currency"]))
            self.cost_table.setItem(i, 3, QTableWidgetItem(item["allocation"]))
            total_extra_etb += display_amount
        self.total_extra_cost_label.setText(f"Total Additional Costs (ETB): {total_extra_etb:,.2f}")

    # ------------------------------------------------------------------
    # Allocation method toggle
    # ------------------------------------------------------------------
    def on_method_changed(self):
        if self.fixed_68_radio.isChecked():
            self.allocation_method = "fixed_68"
        else:
            self.allocation_method = "total_cbm"
        self.calculate_landed()

    def on_basis_changed(self):
        if self.per_qty_radio.isChecked():
            self.current_basis = "qty"
        else:
            self.current_basis = "carton"
        self.update_landed_table()
        self.update_margin_display()

    # ------------------------------------------------------------------
    # Main calculation – now stores allocations per product
    # ------------------------------------------------------------------
    def calculate_landed(self):
        if not self.product_lines:
            self.product_allocations = []
            self.landed_costs_per_qty = []
            self.landed_costs_per_carton = []
            self.landed_table.setRowCount(0)
            self.alloc_table.setRowCount(0)
            self.grand_total_label.setText("Grand Total Landed Cost (ETB): 0.00")
            self.update_margin_product_combo()
            return

        rate = self.rate_spin.value()
        container_cbm = self.CONTAINER_CBM  # 68.0

        # Compute FOB in ETB
        for p in self.product_lines:
            p['fob_unit_etb'] = p['unit_price_rmb'] * rate
            p['total_fob_etb'] = p['qty'] * p['fob_unit_etb']

        # Compute total CBM of all products
        total_product_cbm = sum(p['total_cbm'] for p in self.product_lines)

        # --- Build allocation matrix per product ---
        # self.product_allocations[i] = list of allocated amounts for product i, one per cost
        self.product_allocations = []
        for p in self.product_lines:
            product_alloc = []
            for item in self.cost_items:
                # Convert cost to ETB
                if item['currency'] == 'RMB':
                    cost_etb = item['amount'] * rate
                else:
                    cost_etb = item['amount']

                if item['allocation'] == "By CBM":
                    if self.allocation_method == "fixed_68":
                        allocated = (cost_etb / container_cbm) * p['total_cbm']
                    else:
                        if total_product_cbm > 0:
                            allocated = (cost_etb / total_product_cbm) * p['total_cbm']
                        else:
                            allocated = 0.0
                elif item['allocation'] == "By Value":
                    total_fob_etb = sum(prod['total_fob_etb'] for prod in self.product_lines)
                    if total_fob_etb > 0:
                        allocated = cost_etb * (p['total_fob_etb'] / total_fob_etb)
                    else:
                        allocated = 0.0
                elif item['allocation'] == "By Quantity":
                    total_qty = sum(prod['qty'] for prod in self.product_lines)
                    if total_qty > 0:
                        allocated = cost_etb * (p['qty'] / total_qty)
                    else:
                        allocated = 0.0
                elif item['allocation'] == "By Weight":
                    total_weight = sum(prod['qty'] for prod in self.product_lines)
                    if total_weight > 0:
                        allocated = cost_etb * (p['qty'] / total_weight)
                    else:
                        allocated = 0.0
                else:
                    allocated = 0.0
                product_alloc.append(allocated)
            self.product_allocations.append(product_alloc)

        # Compute total cost and landed units
        self.landed_costs_per_qty = []
        self.landed_costs_per_carton = []
        total_allocations = []
        total_costs = []

        for i, p in enumerate(self.product_lines):
            total_alloc = sum(self.product_allocations[i])
            total_allocations.append(total_alloc)
            total_cost = p['total_fob_etb'] + total_alloc
            total_costs.append(total_cost)
            landed_qty = total_cost / p['qty'] if p['qty'] > 0 else 0
            self.landed_costs_per_qty.append(landed_qty)
            landed_carton = total_cost / p['cartons'] if p['cartons'] > 0 else 0
            self.landed_costs_per_carton.append(landed_carton)

        # Update landed table
        self.landed_table.setRowCount(len(self.product_lines))
        grand_total_etb = 0.0
        for i, p in enumerate(self.product_lines):
            if self.current_basis == "qty":
                landed_unit = self.landed_costs_per_qty[i]
            else:
                landed_unit = self.landed_costs_per_carton[i]

            self.landed_table.setItem(i, 0, QTableWidgetItem(p['name']))
            self.landed_table.setItem(i, 1, QTableWidgetItem(str(p['cartons'])))
            self.landed_table.setItem(i, 2, QTableWidgetItem(str(p['qty'])))
            self.landed_table.setItem(i, 3, QTableWidgetItem(f"{p['total_fob_etb']:,.2f}"))
            self.landed_table.setItem(i, 4, QTableWidgetItem(f"{total_allocations[i]:,.2f}"))
            self.landed_table.setItem(i, 5, QTableWidgetItem(f"{total_costs[i]:,.2f}"))
            self.landed_table.setItem(i, 6, QTableWidgetItem(f"{landed_unit:,.2f}"))
            grand_total_etb += total_costs[i]

        self.grand_total_label.setText(f"Grand Total Landed Cost (ETB): {grand_total_etb:,.2f}")

        # Update header of landed unit column
        if self.current_basis == "qty":
            self.landed_table.setHorizontalHeaderItem(6, QTableWidgetItem("Landed Unit (per Qty)"))
        else:
            self.landed_table.setHorizontalHeaderItem(6, QTableWidgetItem("Landed Unit (per Carton)"))

        # Update allocation matrix
        self._update_allocation_matrix()

        # Update margin
        self.update_margin_product_combo()
        self.update_margin_display()

    # ------------------------------------------------------------------
    # Allocation matrix – products as rows, costs as columns
    # ------------------------------------------------------------------
    def _update_allocation_matrix(self):
        """Display allocation matrix: products as rows, cost items as columns."""
        n_products = len(self.product_lines)
        n_costs = len(self.cost_items)
        
        self.alloc_table.clearContents()
        self.alloc_table.setRowCount(n_products + 1)
        self.alloc_table.setColumnCount(n_costs + 1)
        
        # Headers
        headers = ["Product"] + [item["type"] for item in self.cost_items] + ["Total (per product)"]
        self.alloc_table.setHorizontalHeaderLabels(headers)
        self.alloc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Fill product rows
        for i, p in enumerate(self.product_lines):
            self.alloc_table.setItem(i, 0, QTableWidgetItem(p["name"]))
            row_sum = 0.0
            for j in range(n_costs):
                val = self.product_allocations[i][j]
                item_widget = QTableWidgetItem(f"{val:,.2f}")
                self.alloc_table.setItem(i, j + 1, item_widget)
                row_sum += val
            # Total column (per product) – light green
            total_item = QTableWidgetItem(f"{row_sum:,.2f}")
            total_item.setBackground(QColor("#d4edda"))
            font = total_item.font()
            font.setBold(True)
            total_item.setFont(font)
            self.alloc_table.setItem(i, n_costs, total_item)
        
        # Total row (per cost) – light blue
        total_row = n_products
        total_label_item = QTableWidgetItem("TOTAL")
        total_label_item.setBackground(QColor("#cce5ff"))
        font = total_label_item.font()
        font.setBold(True)
        total_label_item.setFont(font)
        self.alloc_table.setItem(total_row, 0, total_label_item)
        
        grand_total = 0.0
        for j in range(n_costs):
            col_sum = sum(self.product_allocations[i][j] for i in range(n_products))
            item = QTableWidgetItem(f"{col_sum:,.2f}")
            item.setBackground(QColor("#cce5ff"))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.alloc_table.setItem(total_row, j + 1, item)
            grand_total += col_sum
        
        # Grand total cell – darker blue
        grand_item = QTableWidgetItem(f"{grand_total:,.2f}")
        grand_item.setBackground(QColor("#b8daff"))
        font = grand_item.font()
        font.setBold(True)
        grand_item.setFont(font)
        self.alloc_table.setItem(total_row, n_costs, grand_item)

    # ------------------------------------------------------------------
    # Update landed table when basis changes
    # ------------------------------------------------------------------
    def update_landed_table(self):
        if not self.product_lines:
            return
        for i, p in enumerate(self.product_lines):
            if self.current_basis == "qty":
                landed_unit = self.landed_costs_per_qty[i]
            else:
                landed_unit = self.landed_costs_per_carton[i]
            self.landed_table.setItem(i, 6, QTableWidgetItem(f"{landed_unit:,.2f}"))
        if self.current_basis == "qty":
            self.landed_table.setHorizontalHeaderItem(6, QTableWidgetItem("Landed Unit (per Qty)"))
        else:
            self.landed_table.setHorizontalHeaderItem(6, QTableWidgetItem("Landed Unit (per Carton)"))

    # ------------------------------------------------------------------
    # Margin
    # ------------------------------------------------------------------
    def update_margin_product_combo(self):
        self.margin_product_combo.blockSignals(True)
        self.margin_product_combo.clear()
        for p in self.product_lines:
            self.margin_product_combo.addItem(p["name"])
        self.margin_product_combo.blockSignals(False)
        if self.product_lines:
            self.margin_product_combo.setCurrentIndex(0)

    def update_margin_display(self):
        idx = self.margin_product_combo.currentIndex()
        if idx < 0 or not self.product_lines:
            self.margin_landed_cost_label.setText("0.00")
            return
        if self.current_basis == "qty":
            landed_unit = self.landed_costs_per_qty[idx]
            unit_label = "per Qty"
        else:
            landed_unit = self.landed_costs_per_carton[idx]
            unit_label = "per Carton"
        self.margin_landed_cost_label.setText(f"{landed_unit:,.2f} ({unit_label})")
        self.calculate_selling_price()
        self.calculate_margin_from_market()

    def calculate_selling_price(self):
        idx = self.margin_product_combo.currentIndex()
        if idx < 0 or not self.product_lines:
            self.calculated_selling_price_label.setText("0.00")
            return
        if self.current_basis == "qty":
            landed_unit = self.landed_costs_per_qty[idx]
        else:
            landed_unit = self.landed_costs_per_carton[idx]
        margin_pct = self.margin_spin.value() / 100.0
        selling_price = landed_unit * (1 + margin_pct)
        self.calculated_selling_price_label.setText(f"{selling_price:,.2f}")

    def calculate_margin_from_market(self):
        idx = self.margin_product_combo.currentIndex()
        if idx < 0 or not self.product_lines:
            self.implied_margin_label.setText("0.00 %")
            return
        if self.current_basis == "qty":
            landed_unit = self.landed_costs_per_qty[idx]
        else:
            landed_unit = self.landed_costs_per_carton[idx]
        market_price = self.market_price_spin.value()
        if landed_unit == 0:
            self.implied_margin_label.setText("N/A")
            return
        margin_pct = ((market_price - landed_unit) / landed_unit) * 100
        self.implied_margin_label.setText(f"{margin_pct:,.2f} %")

    def on_data_changed(self):
        self.refresh_products_table()
        self.refresh_cost_table()
        self.calculate_landed()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_shipment(self):
        if not self.product_lines:
            QMessageBox.warning(self, "No Products", "Add at least one product.")
            return
        if not self.supplier_combo.currentText().strip():
            QMessageBox.warning(self, "Missing Supplier", "Select a supplier.")
            return
        if not self.bank_combo.currentText().strip():
            QMessageBox.warning(self, "Missing Bank", "Select a bank account.")
            return

        total_fob_rmb = sum(p['qty'] * p['unit_price_rmb'] for p in self.product_lines)
        total_fob_etb = sum(p['total_fob_etb'] for p in self.product_lines)
        total_landed_etb = sum(self.landed_costs_per_qty[i] * self.product_lines[i]['qty'] for i in range(len(self.product_lines)))

        shipment = {
            "id": len(shipments) + 1,
            "supplier": self.supplier_combo.currentText().strip(),
            "bank": self.bank_combo.currentText().strip(),
            "date": self.date_edit.date().toPython(),
            "products": self.product_lines.copy(),
            "exchange_rate": self.rate_spin.value(),
            "cost_items": self.cost_items.copy(),
            "allocation_method": self.allocation_method,
            "status": "Approved",
            "total_fob_rmb": total_fob_rmb,
            "total_fob_etb": total_fob_etb,
            "total_landed_etb": total_landed_etb,
        }
        shipments.append(shipment)
        QMessageBox.information(self, "Saved", f"Proforma #{shipment['id']} saved successfully.")
        self.accept()

# ----------------------------------------------------------------------
# Main Window
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Import Shipment Manager – ETB Landed Cost")
        self.setMinimumSize(1000, 600)
        self.setStyleSheet(STYLE)
        self.init_ui()
        self.refresh_shipment_table()
        self.showMaximized()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_layout = QHBoxLayout()
        create_btn = QPushButton("➕ Create Approved Proforma")
        create_btn.setMinimumHeight(45)
        create_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        create_btn.clicked.connect(self.create_shipment)
        top_layout.addStretch()
        top_layout.addWidget(create_btn)
        layout.addLayout(top_layout)

        self.shipment_table = QTableWidget()
        self.shipment_table.setColumnCount(8)
        self.shipment_table.setHorizontalHeaderLabels([
            "ID", "Supplier", "Bank", "Date", "FOB (RMB)", "FOB (ETB)",
            "Total Landed (ETB)", "Status"
        ])
        self.shipment_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.shipment_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.shipment_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.shipment_table.verticalHeader().setVisible(False)
        self.shipment_table.setAlternatingRowColors(True)
        layout.addWidget(self.shipment_table)

    def refresh_shipment_table(self):
        self.shipment_table.setRowCount(len(shipments))
        for i, s in enumerate(shipments):
            self.shipment_table.setItem(i, 0, QTableWidgetItem(str(s["id"])))
            self.shipment_table.setItem(i, 1, QTableWidgetItem(s["supplier"]))
            self.shipment_table.setItem(i, 2, QTableWidgetItem(s["bank"]))
            self.shipment_table.setItem(i, 3, QTableWidgetItem(s["date"].strftime("%d/%m/%Y")))
            self.shipment_table.setItem(i, 4, QTableWidgetItem(f"¥{s['total_fob_rmb']:,.2f}"))
            self.shipment_table.setItem(i, 5, QTableWidgetItem(f"{s['total_fob_etb']:,.2f}"))
            self.shipment_table.setItem(i, 6, QTableWidgetItem(f"{s['total_landed_etb']:,.2f}"))
            self.shipment_table.setItem(i, 7, QTableWidgetItem(s["status"]))

    def create_shipment(self):
        dialog = ShipmentDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_shipment_table()

# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    if not shipments:
        shipments.append({
            "id": 1,
            "supplier": "Guangzhou Home Co.",
            "bank": "Commercial Bank of Ethiopia",
            "date": date.today(),
            "products": [
                {"name": "Dinner Set", "unit": "set", "cartons": 10, "qty_per_carton": 6, "qty": 60,
                 "unit_price_rmb": 105.0, "cbm_per_carton": 0.05, "total_cbm": 0.5},
                {"name": "Kitchen Mixer", "unit": "pcs", "cartons": 5, "qty_per_carton": 4, "qty": 20,
                 "unit_price_rmb": 315.0, "cbm_per_carton": 0.08, "total_cbm": 0.4},
            ],
            "exchange_rate": 7.85,
            "cost_items": [
                {"type": "Freight", "amount": 100000, "currency": "ETB", "allocation": "By CBM"},
                {"type": "Duty Tax", "amount": 50000, "currency": "ETB", "allocation": "By CBM"},
                {"type": "Inland", "amount": 20000, "currency": "ETB", "allocation": "By CBM"},
            ],
            "status": "Approved",
            "total_fob_rmb": 12600.0,
            "total_fob_etb": 98910.0,
            "total_landed_etb": 101160.0
        })

    window = MainWindow()
    window.show()
    sys.exit(app.exec())