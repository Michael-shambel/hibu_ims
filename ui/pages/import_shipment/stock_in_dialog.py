from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QLineEdit, QCheckBox, QMessageBox,
    QWidget, QApplication, QVBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui.pages.product_dialog import ModernLineEdit, ProductCompleter
from services.new_product_service import NewProductService
from services.import_shipment_service import ImportShipmentService

class StockInMappingDialog(QDialog):
    def __init__(self, shipment, product_service, parent=None):
        super().__init__(parent)
        self.shipment_id = shipment.id
        self.product_service = product_service
        self.setWindowTitle(f"Stock In – Shipment #{self.shipment_id}")
        self.setModal(True)
        self.mapping_result = None

        # Reload shipment fresh from database
        service = ImportShipmentService()
        self.shipment = service.get_by_id_with_relations(self.shipment_id)
        if not self.shipment:
            QMessageBox.critical(self, "Error", "Shipment not found")
            self.reject()
            return

        self.init_ui()

        # Full screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen)
        self.setMinimumSize(0, 0)
        self.setWindowState(Qt.WindowMaximized)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        header = QLabel("Map Shipment Products to Local Products")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(header)

        self.table = QTableWidget()
        headers = ["#", "Item #", "Local Product Name", "Unit",
                   "Qty (Packs)", "Landed Cost", "Target Price", "Market Price", "Use Market"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 11))
        self.table.verticalHeader().setDefaultSectionSize(55)
        # Set a fixed width for the checkbox column so it's visible
        self.table.setColumnWidth(8, 100)

        self.populate_table()
        layout.addWidget(self.table, 1)

        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.stock_btn = QPushButton("✅ Stock In")
        self.stock_btn.setStyleSheet("background-color: #27ae60; color: white;")
        self.stock_btn.clicked.connect(self.confirm_stock_in)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.stock_btn)
        layout.addLayout(btn_layout)

    def populate_table(self):
        self.table.setRowCount(len(self.shipment.products))
        for row, sp in enumerate(self.shipment.products):
            if sp.is_deleted:
                continue

            self.table.setItem(row, 0, QTableWidgetItem(str(row+1)))
            self.table.setItem(row, 1, QTableWidgetItem(sp.item_number or ""))

            # Local Product Name – pre‑filled with shipment product name
            name_edit = ModernLineEdit("Local Name", "Type product name...")
            name_edit.setText(sp.product_name)
            name_edit.setMinimumHeight(40)
            completer = ProductCompleter(self.product_service, parent=self)
            completer.setLineEdit(name_edit.line_edit)
            completer.productSelected.connect(lambda pid, r=row: self.on_product_selected(r, pid))
            name_edit.textChanged.connect(completer.update)
            self.table.setCellWidget(row, 2, name_edit)

            # Unit – pre‑filled
            unit_edit = QLineEdit()
            unit_edit.setText(sp.unit)
            unit_edit.setPlaceholderText("Unit")
            unit_edit.setMinimumHeight(40)
            self.table.setCellWidget(row, 3, unit_edit)

            # Qty (cartons) – read‑only
            qty_item = QTableWidgetItem(str(sp.cartons))
            qty_item.setFlags(qty_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, qty_item)

            # Landed Cost
            landed_val = sp.landed_cost_per_unit if sp.landed_cost_per_unit is not None else 0.0
            landed_item = QTableWidgetItem(f"{landed_val:.2f}")
            landed_item.setFlags(landed_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 5, landed_item)

            # Target Price
            target_val = sp.target_selling_price if sp.target_selling_price is not None else 0.0
            target_item = QTableWidgetItem(f"{target_val:.2f}")
            target_item.setFlags(target_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 6, target_item)

            # Market Price
            market_val = sp.market_price if sp.market_price is not None else 0.0
            market_item = QTableWidgetItem(f"{market_val:.2f}")
            market_item.setFlags(market_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 7, market_item)

            # ---- Use Market checkbox ----
            check_widget = QWidget()
            check_layout = QHBoxLayout(check_widget)
            check_layout.setContentsMargins(0, 0, 0, 0)
            check_layout.setAlignment(Qt.AlignCenter)

            check = QCheckBox()
            check.setChecked(True)   # <-- default checked
            check.setStyleSheet("""
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                }
                QCheckBox::indicator:checked {
                    background-color: #3498db;
                    border: 1px solid #2980b9;
                    border-radius: 3px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: white;
                    border: 1px solid #bdc3c7;
                    border-radius: 3px;
                }
            """)
            check_layout.addWidget(check)
            self.table.setCellWidget(row, 8, check_widget)

    def on_product_selected(self, row, product_id):
        product = self.product_service.get_by_id(product_id)
        if product:
            unit_edit = self.table.cellWidget(row, 3)
            if unit_edit:
                unit_edit.setText(product.unit or "")

    def get_mapping(self):
        mapping = {}
        for row in range(self.table.rowCount()):
            sp = self.shipment.products[row]
            if sp.is_deleted:
                continue
            name_widget = self.table.cellWidget(row, 2)
            local_name = name_widget.text().strip() if name_widget else ""
            if not local_name:
                raise ValueError(f"Row {row+1}: Local product name is required.")
            unit_widget = self.table.cellWidget(row, 3)
            unit = unit_widget.text().strip() if unit_widget else ""
            if not unit:
                raise ValueError(f"Row {row+1}: Unit is required.")

            # Get the checkbox from the container widget
            container = self.table.cellWidget(row, 8)
            if container:
                check = container.findChild(QCheckBox)
                use_market = check.isChecked() if check else False
            else:
                use_market = False

            mapping[sp.id] = {
                'name': local_name,
                'unit': unit,
                'use_market_price': use_market
            }
        return mapping

    def confirm_stock_in(self):
        try:
            self.mapping_result = self.get_mapping()
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))