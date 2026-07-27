from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QTabWidget
)
from ui.pages.product_dialog import ModernComboBox, ModernDoubleSpinBox, ModernLineEdit, ModernSpinBox, ProductCompleter
from ui.components.universal_crud_dialog import UniversalCRUDDialog
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService

class UtilsMixin:
    """Helper methods that don't fit elsewhere."""

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
        """Extract product data from the product table, including market prices from the landed table."""
        products = []

        # --- Build a map of product name -> market price from the landed table ---
        market_price_map = {}
        for row in range(self.landed_table.rowCount()):
            name_item = self.landed_table.item(row, 0)
            if name_item:
                product_name = name_item.text().strip()
                market_item = self.landed_table.item(row, 9)  # column 9 = Market Price
                if market_item:
                    try:
                        price = float(market_item.text().replace(',', ''))
                        market_price_map[product_name] = price
                    except ValueError:
                        pass

        # --- Iterate over product table rows ---
        for row in range(self.product_table.rowCount()):
            # Skip the summary row (if it exists)
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue

            # Get Item # (column 0)
            item_number = self.product_table.item(row, 0).text().strip() if self.product_table.item(row, 0) else ""

            # Get product name from ModernLineEdit in column 1
            name_widget = self.product_table.cellWidget(row, 1)
            if isinstance(name_widget, ModernLineEdit):
                product_name = name_widget.text().strip()
            else:
                name_item = self.product_table.item(row, 1)
                product_name = name_item.text().strip() if name_item else ""

            # If product name is empty, use item number as fallback
            if not product_name:
                product_name = item_number

            # Skip if still empty
            if not product_name:
                continue

            # Get Unit from combo box in column 2
            unit_combo = self.product_table.cellWidget(row, 2)
            if isinstance(unit_combo, QComboBox):
                unit = unit_combo.currentText().strip()
            else:
                unit = "pcs"

            # Get numeric values
            try:
                cartons = float(self.product_table.item(row, 3).text() or 0)
                qty_per = float(self.product_table.item(row, 4).text() or 0)
                unit_price_rmb = float(self.product_table.item(row, 6).text().replace(',', '') or 0)
                cbm_per_carton = float(self.product_table.item(row, 8).text() or 0)
            except ValueError:
                continue  # skip rows with invalid numbers

            if cartons <= 0 or qty_per <= 0 or unit_price_rmb <= 0:
                continue

            # Look up market price from the landed table
            market_price = market_price_map.get(product_name, 0.0)

            products.append({
                "item_number": item_number if item_number else None,
                "product_name": product_name,
                "unit": unit,
                "cartons": int(cartons),
                "qty_per_carton": int(qty_per),
                "unit_price_rmb": unit_price_rmb,
                "cbm_per_carton": cbm_per_carton,
                "market_price": market_price,   # <-- now saved from landed table
            })
        return products