from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QLineEdit, QCheckBox, QMessageBox,
    QWidget, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui.pages.product_dialog import ModernLineEdit, ProductCompleter
from services.new_product_service import NewProductService

class StockInMappingDialog(QDialog):
    def __init__(self, shipment, product_service, parent=None):
        super().__init__(parent)
        self.shipment = shipment
        self.product_service = product_service
        self.setWindowTitle(f"Stock In – Shipment #{shipment.id}")
        self.setMinimumSize(1000, 600)
        self.setModal(True)
        self.mapping_result = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        header = QLabel("Map Shipment Products to Local Products")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(header)

        self.table = QTableWidget()
        headers = ["#", "Item #", "Shipment Name", "Local Product Name", "Unit",
                   "Qty (Packs)", "Landed Cost", "Target Price", "Market Price", "Use Market"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 11))
        self.table.verticalHeader().setDefaultSectionSize(55)

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
            # # (col 0)
            self.table.setItem(row, 0, QTableWidgetItem(str(row+1)))
            # Item # (col 1)
            self.table.setItem(row, 1, QTableWidgetItem(sp.item_number or ""))
            # Shipment Name (col 2)
            self.table.setItem(row, 2, QTableWidgetItem(sp.product_name))

            # Local Product Name (col 3) – editable with completer
            name_edit = ModernLineEdit("Local Name", "Type product name...")
            name_edit.setMinimumHeight(40)
            completer = ProductCompleter(self.product_service, parent=self)
            completer.setLineEdit(name_edit.line_edit)
            completer.productSelected.connect(lambda pid, r=row: self.on_product_selected(r, pid))
            name_edit.textChanged.connect(completer.update)
            self.table.setCellWidget(row, 3, name_edit)

            # Unit (col 4) – editable
            unit_edit = QLineEdit()
            unit_edit.setPlaceholderText("Unit")
            unit_edit.setMinimumHeight(40)
            self.table.setCellWidget(row, 4, unit_edit)

            # Qty (col 5) – read‑only
            qty_item = QTableWidgetItem(str(sp.cartons))
            qty_item.setFlags(qty_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 5, qty_item)

            # Landed Cost (col 6) – read‑only
            landed_item = QTableWidgetItem(f"{sp.landed_cost_per_unit:.2f}" if sp.landed_cost_per_unit else "")
            landed_item.setFlags(landed_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 6, landed_item)

            # Target Price (col 7) – read‑only
            target_item = QTableWidgetItem(f"{sp.target_selling_price:.2f}" if sp.target_selling_price else "")
            target_item.setFlags(target_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 7, target_item)

            # Market Price (col 8) – read‑only
            market_item = QTableWidgetItem(f"{sp.market_price:.2f}" if sp.market_price else "")
            market_item.setFlags(market_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 8, market_item)

            # Use Market (col 9) – checkbox
            check = QCheckBox()
            check.setChecked(False)
            self.table.setCellWidget(row, 9, check)

    def on_product_selected(self, row, product_id):
        product = self.product_service.get_by_id(product_id)
        if product:
            unit_edit = self.table.cellWidget(row, 4)
            if unit_edit:
                unit_edit.setText(product.unit or "")

    def get_mapping(self):
        mapping = {}
        for row in range(self.table.rowCount()):
            sp = self.shipment.products[row]
            if sp.is_deleted:
                continue
            name_widget = self.table.cellWidget(row, 3)
            local_name = name_widget.text().strip() if name_widget else ""
            if not local_name:
                raise ValueError(f"Row {row+1}: Local product name is required.")
            unit_widget = self.table.cellWidget(row, 4)
            unit = unit_widget.text().strip() if unit_widget else ""
            if not unit:
                raise ValueError(f"Row {row+1}: Unit is required.")
            use_market = self.table.cellWidget(row, 9).isChecked()

            # Check if product exists; if not, we will rely on NewProductService.create to create it.
            # But we must pass the product name/unit. We don't need to pre‑create because NewProductService will handle it.
            # However, we need to store the name/unit for the service to use.
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