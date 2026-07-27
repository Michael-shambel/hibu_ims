from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

class Tab3SetupMixin:
    def setup_tab3(self):
        """Build Tab 3: Landed Cost & Margin with integrated pricing columns."""
        self.tab3 = QWidget()
        layout = QVBoxLayout(self.tab3)

        # --- Basis & Margin Controls (unchanged) ---
        controls_group = QGroupBox("Landed Unit Basis & Pricing")
        controls_layout = QHBoxLayout(controls_group)

        basis_widget = QWidget()
        basis_layout = QHBoxLayout(basis_widget)
        self.per_qty_radio = QRadioButton("Per Quantity")
        self.per_carton_radio = QRadioButton("Per Carton")
        self.per_qty_radio.setChecked(True)

        self.basis_group = QButtonGroup()
        self.basis_group.addButton(self.per_qty_radio, 1)
        self.basis_group.addButton(self.per_carton_radio, 2)
        self.basis_group.buttonClicked.connect(self.on_basis_changed)

        basis_layout.addWidget(QLabel("Unit Basis:"))
        basis_layout.addWidget(self.per_qty_radio)
        basis_layout.addWidget(self.per_carton_radio)
        basis_layout.addStretch()

        controls_layout.addWidget(basis_widget, 2)

        margin_widget = QWidget()
        margin_layout = QHBoxLayout(margin_widget)
        margin_layout.addWidget(QLabel("Target Margin (%):"))

        self.target_margin_spin = QDoubleSpinBox()
        self.target_margin_spin.setRange(0.0, 1000.0)
        self.target_margin_spin.setDecimals(2)
        self.target_margin_spin.setValue(20.0)
        self.target_margin_spin.setSuffix(" %")
        self.target_margin_spin.valueChanged.connect(self.calculate_selling_prices)
        margin_layout.addWidget(self.target_margin_spin)

        controls_layout.addWidget(margin_widget, 1)
        controls_layout.addStretch()

        layout.addWidget(controls_group)

        # --- Landed Table (with new Qty/Carton column) ---
        landed_group = QGroupBox("Landed Cost & Margin per Product")
        landed_layout = QVBoxLayout(landed_group)

        self.landed_table = QTableWidget()
        self.landed_table.setColumnCount(11)  # <-- UPDATED
        self.landed_table.setHorizontalHeaderLabels([
            "Product", "Cartons", "Qty/Carton", "Total Qty",
            "FOB (ETB)", "Allocation (ETB)", "Total Cost (ETB)",
            "Landed Unit (ETB)", "Selling Price (ETB)",
            "Market Price (ETB)", "Implied Margin (%)"
        ])
        self.landed_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.landed_table.setAlternatingRowColors(True)

        # Make Market Price column editable
        self.landed_table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
        )
        self.landed_table.cellChanged.connect(self.on_market_price_changed)

        landed_layout.addWidget(self.landed_table)

        # --- Grand Total (unchanged) ---
        self.grand_total_label = QLabel("Grand Total Landed Cost (ETB): 0.00")
        self.grand_total_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #1a6b3c;")
        landed_layout.addWidget(self.grand_total_label)

        layout.addWidget(landed_group)

        # --- Profit Analysis (unchanged) ---
        profit_group = QGroupBox("Profit Analysis")
        profit_layout = QVBoxLayout(profit_group)

        profit_row1 = QHBoxLayout()
        self.profit_total_cost_label = QLabel("Total Landed Cost: ETB 0.00")
        self.profit_total_cost_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        profit_row1.addWidget(self.profit_total_cost_label)
        profit_row1.addStretch()

        self.profit_total_selling_label = QLabel("Total Selling (Target Margin): ETB 0.00")
        self.profit_total_selling_label.setStyleSheet("font-weight: bold; color: #2980b9;")
        profit_row1.addWidget(self.profit_total_selling_label)
        profit_row1.addStretch()

        self.profit_total_market_label = QLabel("Total Market Value: ETB 0.00")
        self.profit_total_market_label.setStyleSheet("font-weight: bold; color: #8e44ad;")
        profit_row1.addWidget(self.profit_total_market_label)
        profit_layout.addLayout(profit_row1)

        profit_row2 = QHBoxLayout()
        self.profit_target_label = QLabel("Profit (Target Margin): ETB 0.00  (0.00%)")
        self.profit_target_label.setStyleSheet("font-weight: bold; color: #27ae60;")
        profit_row2.addWidget(self.profit_target_label)
        profit_row2.addStretch()

        self.profit_market_label = QLabel("Profit (Market Price): ETB 0.00  (0.00%)")
        self.profit_market_label.setStyleSheet("font-weight: bold; color: #e67e22;")
        profit_row2.addWidget(self.profit_market_label)
        profit_row2.addStretch()

        self.profit_diff_label = QLabel("Market vs Target Difference: ETB 0.00")
        self.profit_diff_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        profit_row2.addWidget(self.profit_diff_label)

        profit_layout.addLayout(profit_row2)

        layout.addWidget(profit_group)

        self.tabs.addTab(self.tab3, "📊 Landed Cost & Margin")

    # ------------------------------------------------------------------
    # Basis & Margin Methods
    # ------------------------------------------------------------------
    def on_basis_changed(self):
        """Handle basis toggle (Per Quantity / Per Carton)."""
        if self.per_qty_radio.isChecked():
            self.current_basis = "qty"
        else:
            self.current_basis = "carton"
        self.update_landed_table()
        self.calculate_selling_prices()
        self.calculate_implied_margins()
        self.update_profit_summary()
        self.apply_landed_table_styling()

    def update_landed_table(self):
        """Update the landed unit column."""
        if not self.landed_results:
            return

        for i, res in enumerate(self.landed_results):
            landed_unit = res['landed_qty'] if self.current_basis == "qty" else res['landed_carton']
            self.landed_table.setItem(i, 7, QTableWidgetItem(f"{landed_unit:,.2f}"))  # <-- 6 -> 7

        # Update header of landed unit column
        basis_label = "Landed Unit (per Qty)" if self.current_basis == "qty" else "Landed Unit (per Carton)"
        self.landed_table.setHorizontalHeaderItem(7, QTableWidgetItem(basis_label))   # <-- 6 -> 7

        self.calculate_selling_prices()
        self.calculate_implied_margins()
        self.update_profit_summary()

    def calculate_selling_prices(self):
        """Calculate selling prices for all products based on target margin."""
        if not self.landed_results:
            return

        target_margin = self.target_margin_spin.value() / 100.0

        for i, res in enumerate(self.landed_results):
            landed_unit = res['landed_qty'] if self.current_basis == "qty" else res['landed_carton']
            selling_price = landed_unit * (1 + target_margin)
            self.landed_table.setItem(i, 8, QTableWidgetItem(f"{selling_price:,.2f}"))  # <-- 7 -> 8

        self.update_profit_summary()

    def calculate_implied_margins(self):
        """Calculate implied margins for all products based on per-product market price."""
        if not self.landed_results:
            return

        for i, res in enumerate(self.landed_results):
            landed_unit = res['landed_qty'] if self.current_basis == "qty" else res['landed_carton']

            # Get market price from column 9 (was 8)
            market_item = self.landed_table.item(i, 9)
            try:
                market_price = float(market_item.text().replace(',', '')) if market_item else 0.0
            except ValueError:
                market_price = 0.0

            if landed_unit == 0 or market_price == 0:
                margin_pct = 0.0
            else:
                margin_pct = ((market_price - landed_unit) / landed_unit) * 100

            self.landed_table.setItem(i, 10, QTableWidgetItem(f"{margin_pct:,.2f} %"))  # <-- 9 -> 10

        self.update_profit_summary()

    def on_market_price_changed(self, row, col):
        """When Market Price (col 8) is edited, recalculate Implied Margin (col 9)."""
        if col == 9:
            self.calculate_implied_margins()
            self.apply_landed_table_styling()

    def set_market_price_for_all(self, price):
        """Set the same market price for all products (helper method)."""
        if not self.landed_results:
            return

        for i in range(len(self.landed_results)):
            self.landed_table.setItem(i, 9, QTableWidgetItem(f"{price:,.2f}"))  # <-- 8 -> 9
        self.calculate_implied_margins()

    def update_profit_summary(self):
        """
        Update the profit analysis summary based on current landed results,
        selling prices, and market prices.
        """
        if not self.landed_results:
            self.profit_total_cost_label.setText("Total Landed Cost: ETB 0.00")
            self.profit_total_selling_label.setText("Total Selling (Target Margin): ETB 0.00")
            self.profit_total_market_label.setText("Total Market Value: ETB 0.00")
            self.profit_target_label.setText("Profit (Target Margin): ETB 0.00  (0.00%)")
            self.profit_market_label.setText("Profit (Market Price): ETB 0.00  (0.00%)")
            self.profit_diff_label.setText("Market vs Target Difference: ETB 0.00")
            return

        total_cost = 0.0
        total_selling = 0.0
        total_market = 0.0

        for i, res in enumerate(self.landed_results):
            if self.current_basis == "qty":
                qty = res["total_quantity"]
            else:
                qty = res["cartons"]

            cost = res["total_cost"]
            total_cost += cost

            # Selling price – column 8 (was 7)
            sp_item = self.landed_table.item(i, 8)
            try:
                sp = float(sp_item.text().replace(',', '')) if sp_item else 0.0
            except ValueError:
                sp = 0.0
            total_selling += sp * qty

            # Market price – column 9 (was 8)
            mp_item = self.landed_table.item(i, 9)
            try:
                mp = float(mp_item.text().replace(',', '')) if mp_item else 0.0
            except ValueError:
                mp = 0.0
            total_market += mp * qty

        self.profit_total_cost_label.setText(f"Total Landed Cost: ETB {total_cost:,.2f}")
        self.profit_total_selling_label.setText(f"Total Selling (Target Margin): ETB {total_selling:,.2f}")
        self.profit_total_market_label.setText(f"Total Market Value: ETB {total_market:,.2f}")

        profit_target = total_selling - total_cost
        margin_target = (profit_target / total_cost * 100) if total_cost > 0 else 0.0
        self.profit_target_label.setText(
            f"Profit (Target Margin): ETB {profit_target:,.2f}  ({margin_target:,.2f}%)"
        )

        profit_market = total_market - total_cost
        margin_market = (profit_market / total_cost * 100) if total_cost > 0 else 0.0
        self.profit_market_label.setText(
            f"Profit (Market Price): ETB {profit_market:,.2f}  ({margin_market:,.2f}%)"
        )

        diff = profit_market - profit_target
        self.profit_diff_label.setText(f"Market vs Target Difference: ETB {diff:,.2f}")