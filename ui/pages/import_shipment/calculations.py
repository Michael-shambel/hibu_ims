from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QTabWidget,
    QButtonGroup
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from ui.pages.product_dialog import ModernLineEdit

class CalculationsMixin:
    """Contains calculate_landed and related helpers. grand_total_etb"""

    def calculate_landed(self):
        """
        Recalculate landed cost allocation and update:
        - Tab 2: allocation matrix
        - Tab 3: landed table, grand total, and pricing columns
        """
        # --- Step 1: Extract product data from the main table ---
        products = []
        total_cbm_sum = 0.0
        row_count = self.product_table.rowCount()

        for row in range(row_count):
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue

            name_widget = self.product_table.cellWidget(row, 1)
            if isinstance(name_widget, ModernLineEdit):
                product_name = name_widget.text().strip()
            else:
                name_item = self.product_table.item(row, 1)
                product_name = name_item.text().strip() if name_item else ""

            if not product_name:
                item_number_item = self.product_table.item(row, 0)
                if item_number_item:
                    product_name = item_number_item.text().strip()
                else:
                    product_name = f"Item {row+1}"

            if not product_name:
                continue

            try:
                cartons_item = self.product_table.item(row, 3)
                qty_per_item = self.product_table.item(row, 4)
                price_item = self.product_table.item(row, 6)
                cbm_item = self.product_table.item(row, 8)

                cartons = float(cartons_item.text() or 0) if cartons_item else 0
                qty_per = float(qty_per_item.text() or 0) if qty_per_item else 0
                unit_price_rmb = float(price_item.text().replace(',', '') or 0) if price_item else 0
                cbm_per = float(cbm_item.text() or 0) if cbm_item else 0
            except (ValueError, AttributeError):
                continue

            if cartons <= 0 or qty_per <= 0:
                continue

            total_quantity = cartons * qty_per
            total_cbm = cartons * cbm_per
            total_cbm_sum += total_cbm

            products.append({
                "name": product_name,
                "cartons": cartons,
                "qty_per": qty_per,
                "total_quantity": total_quantity,
                "unit_price_rmb": unit_price_rmb,
                "cbm_per": cbm_per,
                "total_cbm": total_cbm,
            })

        # --- Step 2: Extract cost data from the cost table ---
        costs = []
        for row in range(self.cost_table.rowCount()):
            cost_type_item = self.cost_table.item(row, 0)
            amount_item = self.cost_table.item(row, 1)
            if not cost_type_item or not amount_item:
                continue
            cost_type = cost_type_item.text()
            try:
                amount = float(amount_item.text().replace(',', ''))
            except ValueError:
                continue
            costs.append({"type": cost_type, "amount": amount})

        self.products_data = products

        # --- Step 3: If no products or no costs, clear tables ---
        if not products or not costs or total_cbm_sum <= 0:
            self.alloc_table.setRowCount(0)
            self.alloc_table.setColumnCount(0)
            self.landed_table.setRowCount(0)
            self.grand_total_label.setText("Grand Total Landed Cost (ETB): 0.00")
            self.landed_results = []
            return

        # --- Step 4: Determine allocation denominator once ---
        if self.allocation_mode == "fixed":
            allocation_denominator = self.container_capacity
        else:
            allocation_denominator = total_cbm_sum

        # If denominator is zero, we can't allocate
        if allocation_denominator <= 0:
            self.alloc_table.setRowCount(0)
            self.alloc_table.setColumnCount(0)
            self.landed_table.setRowCount(0)
            self.grand_total_label.setText("Grand Total Landed Cost (ETB): 0.00")
            self.landed_results = []
            return

        # --- Step 5: Allocate each cost across products ---
        product_allocations = []
        landed_results = []
        grand_total_etb = 0.0

        for prod in products:
            allocs = []
            for cost in costs:
                # Allocate cost proportionally by product CBM
                allocated = (cost["amount"] / allocation_denominator) * prod["total_cbm"]
                allocs.append(allocated)

            total_alloc = sum(allocs)
            total_cost = (prod["total_quantity"] * prod["unit_price_rmb"] * self.rate_spin.spin_box.value()) + total_alloc
            landed_qty = total_cost / prod["total_quantity"] if prod["total_quantity"] > 0 else 0
            landed_carton = total_cost / prod["cartons"] if prod["cartons"] > 0 else 0

            product_allocations.append({
                "name": prod["name"],
                "allocations": allocs,
                "total_alloc": total_alloc,
            })
            landed_results.append({
                "name": prod["name"],
                "cartons": prod["cartons"],
                "qty_per_carton": prod["qty_per"],
                "total_quantity": prod["total_quantity"],
                "fob_etb": prod["total_quantity"] * prod["unit_price_rmb"] * self.rate_spin.spin_box.value(),
                "allocated": total_alloc,
                "total_cost": total_cost,
                "landed_qty": landed_qty,
                "landed_carton": landed_carton,
            })
            grand_total_etb += total_cost
            
        # --- Compute dead freight (must be done after product loop) ---
        total_cost_sum = sum(c["amount"] for c in costs)
        total_allocated_sum = sum(pa["total_alloc"] for pa in product_allocations)
        if self.allocation_mode == "fixed" and allocation_denominator > total_cbm_sum:
            self.dead_freight = total_cost_sum - total_allocated_sum
        else:
            self.dead_freight = 0.0

        # Update dead freight label
        if hasattr(self, 'dead_freight_label'):
            if self.dead_freight > 0:
                self.dead_freight_label.setText(
                    f"⚠️ Dead Freight (unallocated cost): ETB {self.dead_freight:,.2f}"
                )
                self.dead_freight_label.setVisible(True)
            else:
                self.dead_freight_label.setVisible(False)

        self.landed_results = landed_results

        # --- Step 6: Update allocation matrix (Tab 2) ---
        n_products = len(products)
        n_costs = len(costs)
        self.alloc_table.setRowCount(n_products + 1)
        self.alloc_table.setColumnCount(n_costs + 2)
        headers = ["Product"] + [c["type"] for c in costs] + ["Total (ETB)"]
        self.alloc_table.setHorizontalHeaderLabels(headers)
        self.alloc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        for i, prod_alloc in enumerate(product_allocations):
            self.alloc_table.setItem(i, 0, QTableWidgetItem(prod_alloc["name"]))
            row_total = 0.0
            for j, alloc in enumerate(prod_alloc["allocations"]):
                item = QTableWidgetItem(f"{alloc:,.2f}")
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.alloc_table.setItem(i, j + 1, item)
                row_total += alloc
            total_item = QTableWidgetItem(f"{row_total:,.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_item.setBackground(QColor("#d4edda"))
            font = total_item.font()
            font.setBold(True)
            total_item.setFont(font)
            self.alloc_table.setItem(i, n_costs + 1, total_item)

        total_row = n_products
        label_item = QTableWidgetItem("TOTAL")
        label_item.setBackground(QColor("#cce5ff"))
        font = label_item.font()
        font.setBold(True)
        label_item.setFont(font)
        self.alloc_table.setItem(total_row, 0, label_item)

        grand_total = 0.0
        for j in range(n_costs):
            col_sum = sum(prod_alloc["allocations"][j] for prod_alloc in product_allocations)
            item = QTableWidgetItem(f"{col_sum:,.2f}")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setBackground(QColor("#cce5ff"))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.alloc_table.setItem(total_row, j + 1, item)
            grand_total += col_sum

        grand_item = QTableWidgetItem(f"{grand_total:,.2f}")
        grand_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grand_item.setBackground(QColor("#b8daff"))
        font = grand_item.font()
        font.setBold(True)
        grand_item.setFont(font)
        self.alloc_table.setItem(total_row, n_costs + 1, grand_item)

        self.alloc_table.verticalHeader().setDefaultSectionSize(40)
        self.alloc_table.setAlternatingRowColors(True)

        # --- Step 7: Update landed table (Tab 3) with new Qty/Carton column ---
        self.landed_table.setRowCount(len(landed_results))
        for i, res in enumerate(landed_results):
            self.landed_table.setItem(i, 0, QTableWidgetItem(res["name"]))
            self.landed_table.setItem(i, 1, QTableWidgetItem(str(res["cartons"])))
            self.landed_table.setItem(i, 2, QTableWidgetItem(str(res["qty_per_carton"])))
            self.landed_table.setItem(i, 3, QTableWidgetItem(str(res["total_quantity"])))
            self.landed_table.setItem(i, 4, QTableWidgetItem(f"{res['fob_etb']:,.2f}"))
            self.landed_table.setItem(i, 5, QTableWidgetItem(f"{res['allocated']:,.2f}"))
            self.landed_table.setItem(i, 6, QTableWidgetItem(f"{res['total_cost']:,.2f}"))
            # Col 7: Landed Unit (set by update_landed_table)
            # Col 8: Selling Price (set by calculate_selling_prices)
            self.landed_table.setItem(i, 9, QTableWidgetItem("0.00"))  # Market Price default
            # Col 10: Implied Margin (set by calculate_implied_margins)

        # Update header of landed unit column (col 7)
        basis_label = "Landed Unit (per Qty)" if self.current_basis == "qty" else "Landed Unit (per Carton)"
        self.landed_table.setHorizontalHeaderItem(7, QTableWidgetItem(basis_label))

        # Grand total
        self.grand_total_label.setText(f"Grand Total Landed Cost (ETB): {grand_total_etb:,.2f}")

        # Populate the landed unit column
        self.update_landed_table()

        # --- Step 8: Calculate pricing columns ---
        self.calculate_selling_prices()
        self.calculate_implied_margins()

        self.update_profit_summary()
        self.apply_landed_table_styling()

    def apply_landed_table_styling(self):
        """Apply visual styling to important columns in the landed table."""
        if not self.landed_results:
            return

        # Columns to highlight: Total Cost (6), Landed Unit (7), Selling Price (8), Market Price (9), Implied Margin (10)
        important_cols = [6, 7, 8, 9, 10]

        for row in range(self.landed_table.rowCount()):
            for col in important_cols:
                item = self.landed_table.item(row, col)
                if not item:
                    continue

                # Bold font
                font = item.font()
                font.setBold(True)
                item.setFont(font)

                # Background colours
                if col == 6:          # Total Cost
                    item.setBackground(QColor(240, 240, 240))   # light grey
                elif col == 7:        # Landed Unit
                    item.setBackground(QColor(255, 255, 200))   # light yellow
                elif col == 8:        # Selling Price
                    item.setBackground(QColor(200, 230, 255))   # light blue
                elif col == 9:        # Market Price
                    item.setBackground(QColor(230, 230, 255))   # light purple
                elif col == 10:       # Implied Margin
                    try:
                        # Remove '%' and commas, then convert to float
                        val_str = item.text().replace('%', '').replace(',', '').strip()
                        val = float(val_str) if val_str else 0.0
                    except ValueError:
                        val = 0.0
                    if val < 0:
                        item.setBackground(QColor(255, 200, 200))   # redish
                    elif val > 0:
                        item.setBackground(QColor(200, 255, 200))   # greenish
                    else:
                        item.setBackground(QColor(240, 240, 240))   # neutral

                # Right-align numeric values
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)