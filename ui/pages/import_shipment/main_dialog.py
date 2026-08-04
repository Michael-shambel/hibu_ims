#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QTabWidget,
    QButtonGroup
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from ui.pages.product_dialog import ModernComboBox, ModernDoubleSpinBox, ModernLineEdit, ModernSpinBox, ProductCompleter
from ui.components.ethiopian_date import EthiopianDateEdit
from ui.components.universal_crud_dialog import UniversalCRUDDialog
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService
from services.new_product_service import NewProductService
from services.import_shipment_service import ImportShipmentService, PaymentStatusEnum
from services.cost_type_service import CostTypeService

from .preview_dialog import ExcelPreviewDialog
from .add_product_dialog import AddProductLineDialog
from .cost_item_dialog import AddCostItemDialog

# Import the mixins
from .tab1_setup import Tab1SetupMixin
from .tab2_setup import Tab2SetupMixin
from .tab3_setup import Tab3SetupMixin
from .calculations import CalculationsMixin
from .utils import UtilsMixin

import logging
logger = logging.getLogger(__name__)

class ImportShipmentDialog(
        QDialog,
        Tab1SetupMixin,
        Tab2SetupMixin,
        Tab3SetupMixin,
        CalculationsMixin,
        UtilsMixin
    ):
    def __init__(self, parent=None, current_user=None, mode="create", shipment_id=None):
        super().__init__(parent)
        self.current_user = current_user
        self.mode = mode          # 'create', 'edit', 'view'
        self.shipment_id = shipment_id
        self.product_service = NewProductService()
        self.cost_type_service = CostTypeService()
        self._updating = False
        self.current_basis = "qty"
        self.allocation_mode = "used_cbm"
        self.container_capacity = 68.0
        self.dead_freight = 0.0
        self.products_data = []
        self.landed_results = []
        self.basic_info = None   # <-- NEW: store supplier, bank, date, payment_status

        # self.bank_combo = ModernComboBox("LC Bank", parent=self)
        # self.bank_combo.combo_box.setEditable(True)
        # self.bank_combo.combo_box.lineEdit().setPlaceholderText("Select or type bank...")

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
        # No populate_suppliers / populate_banks calls needed anymore

        if shipment_id:
            self.load_shipment(shipment_id)
        else:
            self.calculate_landed()

    def init_ui(self):
        """Build the UI with three tabs and universal bottom buttons."""
        main_layout = QVBoxLayout(self)

        # ----- Tab Widget -----
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #c0c8d0;
                border-radius: 0px;
                background: white;
            }
            QTabBar::tab {
                background: #e6ecf2;
                padding: 10px 20px;
                margin-right: 2px;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #3498db;
            }
        """)

        # ---------- Tab 1: Shipment Details ----------
        self.setup_tab1()

        # ---------- Tab 2: Costs & Allocation ----------
        self.setup_tab2()

        # ---------- Tab 3: Landed Cost & Margin ----------
        self.setup_tab3()

        # Add the tabs to the main layout
        main_layout.addWidget(self.tabs)

        # ---- Universal Bottom Buttons (always visible) ----
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.setContentsMargins(10, 10, 10, 10)

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

        bottom_btn_layout.addStretch()
        bottom_btn_layout.addWidget(self.save_btn)
        bottom_btn_layout.addSpacing(10)
        bottom_btn_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(bottom_btn_layout)

        # If viewing, disable editing
        if self.mode == "view":
            self.set_read_only(True)

        # # Populate combos with real data from database
        # self.populate_suppliers()
        # self.populate_banks()

        # # Initial calculation
        # self.calculate_landed()

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

    def save_shipment(self):
        """Validate and save the shipment (create or update) including landed costs."""
        # ---- 1. Basic validation ----
        if not self.basic_info:
            QMessageBox.warning(self, "Validation", "Please set supplier and payment details first.")
            return

        supplier_id = self.basic_info.get('supplier_id')
        proforma_date = self.basic_info.get('proforma_date')
        payment_status = self.basic_info.get('payment_status', 'credit')
        bank_id = self.basic_info.get('bank_account_id')   # from dialog

        if not supplier_id:
            QMessageBox.warning(self, "Validation", "Please select a supplier.")
            return
        if not proforma_date:
            QMessageBox.warning(self, "Validation", "Please set a proforma date.")
            return
        if payment_status == "paid" and not bank_id:
            QMessageBox.warning(self, "Validation", "Please select a bank account for paid shipment.")
            return

        exchange_rate = self.rate_spin.spin_box.value()
        if exchange_rate <= 0:
            QMessageBox.warning(self, "Validation", "Exchange rate must be greater than 0.")
            return

        user_id = self.get_user_id()
        if not user_id:
            QMessageBox.warning(self, "Validation", "User not identified. Please log in again.")
            return

        products = self.get_products_from_table()
        if not products:
            QMessageBox.warning(self, "Validation", "Please add at least one product.")
            return

        costs = self.get_costs_from_table()
        target_margin = self.target_margin_spin.value()

        # ---- 2. Prepare shipment data ----
        data = {
            "supplier_id": supplier_id,
            "bank_account_id": bank_id,           # may be None
            "proforma_date": proforma_date,
            "exchange_rate": exchange_rate,
            "created_by_user_id": user_id,
            "products": products,
            "costs": costs,
            "target_margin": target_margin,
            "allocation_mode": self.allocation_mode,
            "payment_status": payment_status,
            "payment_date": proforma_date,
        }

        # ---- 3. Build landed_data from current calculation (Tab 3) ----
        landed_data = {}
        if hasattr(self, 'landed_results') and self.landed_results:
            for idx, res in enumerate(self.landed_results):
                product_name = res['name']
                # Determine landed cost per unit based on current basis
                landed_cost = res['landed_qty'] if self.current_basis == 'qty' else res['landed_carton']
                # Target selling price – if you store it in res, use it; otherwise compute from margin
                target_price_item = self.landed_table.item(idx, 8)
                target_price = float(target_price_item.text().replace(',', '')) if target_price_item else 0.0
                # Market price from table column 9 (index 9)
                market_item = self.landed_table.item(idx, 9)
                market_price = float(market_item.text().replace(',', '')) if market_item else 0.0
                landed_data[product_name] = {
                    'landed_cost': landed_cost,
                    'target_price': target_price,
                    'market_price': market_price
                }

        # ---- 4. Save via service ----
        try:
            service = ImportShipmentService()
            if self.shipment_id:
                shipment = service.update_shipment(self.shipment_id, data, landed_data)
                msg = f"Shipment #{shipment.id} updated."
            else:
                shipment = service.create_shipment(data, landed_data)
                msg = f"Shipment #{shipment.id} saved as DRAFT."

            if shipment:
                QMessageBox.information(self, "Success", msg)
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to save shipment.")
        except Exception as e:
            logger.error(f"Error saving shipment: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

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

        # Disable buttons (except cancel?)
        for widget in self.findChildren(QPushButton):
            # Keep Cancel always enabled, but hide Save in view mode
            if widget is self.cancel_btn:
                continue
            widget.setEnabled(not enabled)

        # Product table: disable editing and cell widgets
        self.product_table.setEditTriggers(
            QTableWidget.NoEditTriggers if enabled else QTableWidget.DoubleClicked
        )
        for row in range(self.product_table.rowCount()):
            # Disable the name line edit (column 1)
            name_widget = self.product_table.cellWidget(row, 1)
            if name_widget and isinstance(name_widget, ModernLineEdit):
                name_widget.setEnabled(not enabled)
            # Disable the unit combo (column 2)
            unit_widget = self.product_table.cellWidget(row, 2)
            if unit_widget and isinstance(unit_widget, QComboBox):
                unit_widget.setEnabled(not enabled)

        # Cost table: disable editing
        self.cost_table.setEditTriggers(
            QTableWidget.NoEditTriggers if enabled else QTableWidget.DoubleClicked
        )

        # Hide Save button in view mode
        self.save_btn.setVisible(not enabled)

    def load_shipment(self, shipment_id):
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import QTableWidgetItem
        from services.import_shipment_service import ImportShipmentService

        service = ImportShipmentService()
        shipment = service.get_by_id_with_relations(shipment_id)
        if not shipment:
            QMessageBox.critical(self, "Error", f"Shipment #{shipment_id} not found.")
            self.reject()
            return

        if self.mode == "view":
            self.setWindowTitle(f"View Shipment #{shipment_id}")
        else:
            self.setWindowTitle(f"Edit Shipment #{shipment_id}")
            self.save_btn.setText("💾 Update Draft")

        # Basic info (now includes bank_account_id)
        self.basic_info = {
            "supplier_id": shipment.supplier_id,
            "payment_status": shipment.payment_status,
            "proforma_date": shipment.proforma_date,
            "bank_account_id": shipment.bank_account_id,   # may be None
        }
        self.update_basic_info_summary()

        # (Bank combo removed – no need to set anything)

        self.rate_spin.spin_box.setValue(shipment.exchange_rate)
        self.target_margin_spin.setValue(shipment.target_margin or 20.0)

        self.allocation_mode = shipment.allocation_mode or "used_cbm"
        if self.allocation_mode == "fixed":
            self.fixed_cbm_radio.setChecked(True)
            self.fixed_cbm_spin.setValue(self.container_capacity)
        else:
            self.used_cbm_radio.setChecked(True)

        # Load products
        self.product_table.setRowCount(0)
        for product in shipment.products:
            if not product.is_deleted:
                data = {
                    "item_number": product.item_number,
                    "product_name": product.product_name,
                    "unit": product.unit,
                    "cartons": product.cartons,
                    "qty_per_carton": product.qty_per_carton,
                    "unit_price_rmb": product.unit_price_rmb,
                    "cbm_per_carton": product.cbm_per_carton,
                }
                self.add_product_row_to_table(data, trigger_calculation=False)

        # Load costs
        self.cost_table.setRowCount(0)
        for cost in shipment.costs:
            if not cost.is_deleted:
                # Determine if this cost was paid
                paid = cost.bank_transaction_id is not None
                payment_date = None
                bank_account_id = None
                bank_account_name = None

                if paid and cost.bank_transaction:
                    payment_date = cost.bank_transaction.transaction_date
                    bank = cost.bank_transaction.bank_account
                    if bank:
                        bank_account_id = bank.id
                        bank_account_name = f"{bank.bank_name} - {bank.account_name}"

                data = {
                    "cost_type_id": cost.cost_type_id,
                    "cost_type_name": cost.cost_type.name if cost.cost_type else "Unknown",
                    "amount": cost.amount,
                    "paid": paid,
                    "payment_date": payment_date,
                    "bank_account_id": bank_account_id,
                    "bank_account_name": bank_account_name,
                }
                self.add_cost_row(data)

        self.calculate_landed()

        # Restore market prices
        if shipment.products:
            market_price_map = {
                p.product_name: p.market_price for p in shipment.products if p.product_name
            }
            for row in range(self.landed_table.rowCount()):
                name_item = self.landed_table.item(row, 0)
                if name_item:
                    product_name = name_item.text().strip()
                    if product_name in market_price_map:
                        price = market_price_map[product_name] or 0.0
                        self.landed_table.setItem(row, 9, QTableWidgetItem(f"{price:,.2f}"))

            self.calculate_implied_margins()
            self.update_profit_summary()
            self.apply_landed_table_styling()

        # Read-only mode
        if shipment.status.value in ("approved", "cancelled"):
            self.mode = "view"
            self.set_read_only(True)
        elif self.mode == "view":
            self.set_read_only(True)
        else:
            self.set_read_only(False)