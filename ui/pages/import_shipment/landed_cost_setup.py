"""
Landed Cost & Margin Tab for Import Shipments
Tab 4 - Final tab with landed cost, pricing, and profit analysis
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor


class LandedCostSetupMixin:
    """Contains setup_landed_tab and landed cost table methods."""

    def setup_landed_tab(self):
        """Build Tab 4: Landed Cost & Margin."""
        self.landed_tab = QWidget()
        layout = QVBoxLayout(self.landed_tab)

        # --- Basis & Margin Controls ---
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

        # --- Landed Table ---
        landed_group = QGroupBox("Landed Cost & Margin per Product")
        landed_layout = QVBoxLayout(landed_group)

        self.landed_table = QTableWidget()
        self.landed_table.setColumnCount(12)
        self.landed_table.setHorizontalHeaderLabels([
            "Product", "Cartons", "Qty/Carton", "Total Qty",
            "FOB (ETB)", "Allocation (ETB)", "Total Tax (ETB)",
            "Total Cost (ETB)", "Landed Unit (ETB)",
            "Selling Price (ETB)", "Market Price (ETB)", "Implied Margin (%)"
        ])
        self.landed_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.landed_table.setAlternatingRowColors(True)

        # Make Market Price column editable
        self.landed_table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
        )
        self.landed_table.cellChanged.connect(self.on_market_price_changed)

        landed_layout.addWidget(self.landed_table)

        # --- Grand Total ---
        self.grand_total_label = QLabel("Grand Total Landed Cost (ETB): 0.00")
        self.grand_total_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #1a6b3c;")
        landed_layout.addWidget(self.grand_total_label)

        layout.addWidget(landed_group)

        # --- Profit Analysis ---
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

        self.tabs.addTab(self.landed_tab, "📊 Landed Cost & Margin")

    # ------------------------------------------------------------------
    # Basis & Margin Methods
    # ------------------------------------------------------------------

    def on_basis_changed(self):
        """Handle basis toggle."""
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
            # Column 8: Landed Unit
            self.landed_table.setItem(i, 8, QTableWidgetItem(f"{landed_unit:,.2f}"))

        # Update header of landed unit column (column 8)
        basis_label = "Landed Unit (per Qty)" if self.current_basis == "qty" else "Landed Unit (per Carton)"
        self.landed_table.setHorizontalHeaderItem(8, QTableWidgetItem(basis_label))

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
            # Column 9: Selling Price
            self.landed_table.setItem(i, 9, QTableWidgetItem(f"{selling_price:,.2f}"))

        self.update_profit_summary()

    def calculate_implied_margins(self):
        """Calculate implied margins based on market price."""
        if not self.landed_results:
            return

        for i, res in enumerate(self.landed_results):
            landed_unit = res['landed_qty'] if self.current_basis == "qty" else res['landed_carton']

            # Column 10: Market Price
            market_item = self.landed_table.item(i, 10)
            try:
                market_price = float(market_item.text().replace(',', '')) if market_item else 0.0
            except ValueError:
                market_price = 0.0

            if landed_unit == 0 or market_price == 0:
                margin_pct = 0.0
            else:
                margin_pct = ((market_price - landed_unit) / landed_unit) * 100

            # Column 11: Implied Margin
            self.landed_table.setItem(i, 11, QTableWidgetItem(f"{margin_pct:,.2f} %"))

        self.update_profit_summary()

    def on_market_price_changed(self, row, col):
        """When Market Price is edited, recalculate Implied Margin."""
        if col == 10:  # Market Price column
            self.calculate_implied_margins()
            self.apply_landed_table_styling()

    def update_profit_summary(self):
        """Update the profit analysis summary."""
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

            # Column 9: Selling Price
            sp_item = self.landed_table.item(i, 9)
            try:
                sp = float(sp_item.text().replace(',', '')) if sp_item else 0.0
            except ValueError:
                sp = 0.0
            total_selling += sp * qty

            # Column 10: Market Price
            mp_item = self.landed_table.item(i, 10)
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

    def apply_landed_table_styling(self):
        """Apply visual styling to important columns."""
        if not self.landed_results:
            return

        important_cols = [6, 7, 8, 9, 10, 11]

        for row in range(self.landed_table.rowCount()):
            for col in important_cols:
                item = self.landed_table.item(row, col)
                if not item:
                    continue

                font = item.font()
                font.setBold(True)
                item.setFont(font)

                if col == 6:          # Total Tax
                    item.setBackground(QColor(200, 240, 255))
                elif col == 7:        # Total Cost
                    item.setBackground(QColor(255, 240, 230))
                elif col == 8:        # Landed Unit
                    item.setBackground(QColor(255, 255, 200))
                elif col == 9:        # Selling Price
                    item.setBackground(QColor(200, 230, 255))
                elif col == 10:       # Market Price
                    item.setBackground(QColor(230, 230, 255))
                elif col == 11:       # Implied Margin
                    try:
                        val_str = item.text().replace('%', '').replace(',', '').strip()
                        val = float(val_str) if val_str else 0.0
                    except ValueError:
                        val = 0.0
                    if val < 0:
                        item.setBackground(QColor(255, 200, 200))
                    elif val > 0:
                        item.setBackground(QColor(200, 255, 200))
                    else:
                        item.setBackground(QColor(240, 240, 240))

                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)