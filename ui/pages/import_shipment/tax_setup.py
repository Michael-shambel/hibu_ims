#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLabel,
    QDoubleSpinBox, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QComboBox, QCheckBox, QRadioButton,
    QMessageBox
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from ui.pages.product_dialog import ModernLineEdit
from ui.components.ethiopian_date import EthiopianDateEdit

# Customs tax parameters
#   Tax 1 = Qty/doz * USD/doz * DEFAULT_TAX_RATER * USD->ETB   (per line)
#   Tax 2 = Total Freight / (CBM basis / CBM per carton) / Qty/doz
#           CBM basis = fixed container capacity (68) or the shipment's used CBM
DEFAULT_TAX_RATER = 0.73755
FIXED_CONTAINER_CAPACITY = 68.0


class TaxSetupMixin:
    def setup_tax_tab(self):
        self.tax_tab = QWidget()
        layout = QVBoxLayout(self.tax_tab)
        layout.setSpacing(15)

        input_group = QGroupBox("Customs Input Variables")
        input_layout = QFormLayout(input_group)

        # ---- Row 1 ----
        row1_widget = QWidget()
        row1_layout = QHBoxLayout(row1_widget)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(15)

        self.tax_usd_rate = QDoubleSpinBox()
        self.tax_usd_rate.setRange(0.0, 10000.0)
        self.tax_usd_rate.setDecimals(4)
        self.tax_usd_rate.setPrefix("1 USD: ")
        self.tax_usd_rate.setSuffix(" ETB")
        self.tax_usd_rate.setValue(160.0)
        self.tax_usd_rate.valueChanged.connect(self.recalculate_tax)

        self.tax_total_freight = QDoubleSpinBox()
        self.tax_total_freight.setRange(0.0, 1000000000.0)
        self.tax_total_freight.setDecimals(2)
        self.tax_total_freight.setPrefix("ETB ")
        self.tax_total_freight.setValue(0.0)
        self.tax_total_freight.setToolTip(
            "Freight for the whole shipment in ETB. Used by Tax 2."
        )
        self.tax_total_freight.valueChanged.connect(self.recalculate_tax)

        row1_layout.addWidget(QLabel("USD to ETB Rate:"))
        row1_layout.addWidget(self.tax_usd_rate)
        row1_layout.addWidget(QLabel("Total Freight (ETB):"))
        row1_layout.addWidget(self.tax_total_freight)
        row1_layout.addStretch()

        # ---- Row 2 ----
        row2_widget = QWidget()
        row2_layout = QHBoxLayout(row2_widget)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(15)

        self.tax_rater = QDoubleSpinBox()
        self.tax_rater.setRange(0.0, 1.0)
        self.tax_rater.setDecimals(5)
        self.tax_rater.setSingleStep(0.001)
        self.tax_rater.setValue(DEFAULT_TAX_RATER)
        self.tax_rater.setToolTip("Customs tax rater (default 0.73755).")
        self.tax_rater.valueChanged.connect(self.recalculate_tax)

        self.tax_formula_label = QLabel(
            "Tax 1 = Qty/doz × USD/doz × rater × USD→ETB    •    "
            "Tax 2 = Total Freight ÷ (CBM basis ÷ CBM/ctn) ÷ Qty/doz"
        )
        self.tax_formula_label.setStyleSheet("color: #64748b; font-size: 12px;")

        row2_layout.addWidget(QLabel("Tax Rater:"))
        row2_layout.addWidget(self.tax_rater)
        row2_layout.addSpacing(20)
        row2_layout.addWidget(self.tax_formula_label)
        row2_layout.addStretch()

        # ---- Row 3: CBM basis used by the freight tax ----
        row3_widget = QWidget()
        row3_layout = QHBoxLayout(row3_widget)
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(15)

        self.tax_fixed_cbm_radio = QRadioButton("Fixed Container Capacity (68 CBM)")
        self.tax_used_cbm_radio = QRadioButton("Total Used CBM")
        self.tax_used_cbm_radio.setChecked(True)

        self.tax_cbm_spin = QDoubleSpinBox()
        self.tax_cbm_spin.setRange(1.0, 1000.0)
        self.tax_cbm_spin.setDecimals(1)
        self.tax_cbm_spin.setValue(FIXED_CONTAINER_CAPACITY)
        self.tax_cbm_spin.setSuffix(" CBM")
        self.tax_cbm_spin.setEnabled(False)

        self.tax_fixed_cbm_radio.toggled.connect(self.on_tax_basis_changed)
        self.tax_used_cbm_radio.toggled.connect(self.on_tax_basis_changed)
        self.tax_cbm_spin.valueChanged.connect(self.recalculate_tax)

        row3_layout.addWidget(QLabel("Freight CBM Basis:"))
        row3_layout.addWidget(self.tax_fixed_cbm_radio)
        row3_layout.addWidget(self.tax_cbm_spin)
        row3_layout.addSpacing(20)
        row3_layout.addWidget(self.tax_used_cbm_radio)
        row3_layout.addStretch()

        input_layout.addRow(row1_widget)
        input_layout.addRow(row2_widget)
        input_layout.addRow(row3_widget)
        layout.addWidget(input_group)

        # ---- Product Tax Table (EXPANDS to fill remaining space) ----
        table_group = QGroupBox("Product Tax Calculation")
        table_layout = QVBoxLayout(table_group)

        self.tax_table = QTableWidget()
        self.tax_table.setColumnCount(14)
        self.tax_table.setHorizontalHeaderLabels([
            "Item #", "Product Name", "Unit", "Qty/doz", "USD/doz",
            "Total USD", "Total ETB", "Tax 1 /doz", "Tax 2 /doz",
            "Tax 1 (ETB)", "Tax 2 (ETB)", "Total Tax ETB", "Tax/doz", "Tax/pcs"
        ])
        self.tax_table.horizontalHeaderItem(3).setToolTip("Number of dozens for this line")
        self.tax_table.horizontalHeaderItem(4).setToolTip("Price per dozen in USD")
        self.tax_table.horizontalHeaderItem(7).setToolTip(
            "USD/doz × rater × USD→ETB rate"
        )
        self.tax_table.horizontalHeaderItem(8).setToolTip(
            "Total Freight ÷ (CBM basis ÷ CBM/ctn) ÷ Qty/doz"
        )
        self.tax_table.horizontalHeaderItem(13).setToolTip(
            "Tax/doz ÷ Qty/doz"
        )

        # Column widths
        self.tax_table.setColumnWidth(0, 100)
        self.tax_table.setColumnWidth(1, 200)
        self.tax_table.setColumnWidth(2, 80)
        self.tax_table.setColumnWidth(3, 80)   # Qty/doz
        self.tax_table.setColumnWidth(4, 100)  # USD/doz
        self.tax_table.setColumnWidth(5, 100)
        self.tax_table.setColumnWidth(6, 100)
        self.tax_table.setColumnWidth(7, 100)
        self.tax_table.setColumnWidth(8, 100)
        self.tax_table.setColumnWidth(9, 100)
        self.tax_table.setColumnWidth(10, 100)
        self.tax_table.setColumnWidth(11, 120)
        self.tax_table.setColumnWidth(12, 90)
        self.tax_table.setColumnWidth(13, 90)

        header = self.tax_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(self.tax_table.columnCount()):
            if col != 1:
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        # Make Qty/doz (col 3) and USD/doz (col 4) editable
        self.tax_table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
        )
        self.tax_table.cellChanged.connect(self.on_tax_cell_changed)

        self.tax_table.setAlternatingRowColors(True)
        self.tax_table.setFont(QFont("Segoe UI", 11))
        self.tax_table.verticalHeader().setDefaultSectionSize(45)
        self.tax_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.tax_table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 10px;
                font-weight: bold;
                font-size: 13px;
                border: none;
            }
            QTableWidget::item {
                padding: 6px;
            }
        """)

        table_layout.addWidget(self.tax_table, 1)

        self.tax_summary_label = QLabel("Total Tax Payable: ETB 0.00")
        self.tax_summary_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.tax_summary_label.setStyleSheet(
            "color: #e74c3c; padding: 8px; background-color: #fdf0f0; "
            "border-radius: 6px; border: 1px solid #f5c6cb;"
        )
        table_layout.addWidget(self.tax_summary_label)

        layout.addWidget(table_group, 1)

        # ---- Tax Payment Section (similar to Add Cost dialog) ----
        tax_payment_group = QGroupBox("Tax Payment")
        tax_payment_layout = QFormLayout(tax_payment_group)

        self.tax_paid_checkbox = QCheckBox("Paid from Bank Account")
        self.tax_paid_checkbox.toggled.connect(self.on_tax_paid_toggled)

        # Paid details group (initially hidden)
        self.tax_paid_group = QGroupBox()
        tax_paid_layout = QFormLayout(self.tax_paid_group)

        self.tax_bank_combo = QComboBox()
        self.tax_bank_combo.setEditable(True)
        self.tax_bank_combo.lineEdit().setPlaceholderText("Select bank account...")
        tax_paid_layout.addRow("Bank Account:", self.tax_bank_combo)

        self.tax_payment_date = EthiopianDateEdit()
        self.tax_payment_date.setDate(QDate.currentDate())
        tax_paid_layout.addRow("Payment Date:", self.tax_payment_date)

        self.tax_paid_group.setVisible(False)

        tax_payment_layout.addRow(self.tax_paid_checkbox)
        tax_payment_layout.addRow(self.tax_paid_group)

        layout.addWidget(tax_payment_group)

        self.tabs.addTab(self.tax_tab, "💰 Custom Tax")

        # Initialise tax values
        self._tax_ps_values = {}
        self._current_total_freight = 0.0
        self._current_rater = DEFAULT_TAX_RATER
        self._current_usd_rate = 160.0
        self._tax_product_info = {}
        self._tax_used_cbm = 0.0
        self._tax_bank_account_id = None
        self._tax_paid = False
        self._tax_payment_date = None

        # Load bank accounts for tax payment
        self.load_tax_bank_accounts()

    def load_tax_bank_accounts(self):
        from services.bank_account_service import BankAccountService
        service = BankAccountService()
        accounts = service.get_all()
        self.tax_bank_combo.clear()
        self.tax_bank_combo.addItem("Select Bank Account", None)
        for acc in accounts:
            if acc.is_active:
                display = f"{acc.bank_name} - {acc.account_name}"
                self.tax_bank_combo.addItem(display, acc.id)
        if self.tax_bank_combo.count() > 0:
            self.tax_bank_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # All methods below remain exactly as they were (no changes needed)
    # because they already use the correct attribute names.
    # ------------------------------------------------------------------

    def on_tax_basis_changed(self):
        """Enable the capacity box for a fixed basis and recalculate."""
        self.tax_cbm_spin.setEnabled(self.tax_fixed_cbm_radio.isChecked())
        self.recalculate_tax()

    def get_tax_basis(self):
        """Return 'fixed' or 'used_cbm' — which CBM figure Tax 2 divides by."""
        return "fixed" if self.tax_fixed_cbm_radio.isChecked() else "used_cbm"

    def set_tax_basis(self, basis):
        """Select the Tax 2 CBM basis ('fixed' or 'used_cbm')."""
        if basis == "fixed":
            self.tax_fixed_cbm_radio.setChecked(True)
        else:
            self.tax_used_cbm_radio.setChecked(True)

    def _product_info_lookup(self):
        """Map product name -> unit / CBM per carton / total CBM.

        Read from the shipment product table so the tax tab follows whatever is
        entered in the Shipment Details tab (unit and carton volume).
        """
        lookup = {}
        table = getattr(self, 'product_table', None)
        if table is None:
            return lookup

        for row in range(table.rowCount()):
            item_number = table.item(row, 0)
            if item_number and item_number.text() == "TOTAL":
                continue

            name_widget = table.cellWidget(row, 1)
            if isinstance(name_widget, ModernLineEdit):
                name = name_widget.text().strip()
            else:
                name_item = table.item(row, 1)
                name = name_item.text().strip() if name_item else ""
            if not name:
                continue

            unit_widget = table.cellWidget(row, 2)
            if isinstance(unit_widget, ModernLineEdit):
                unit = unit_widget.text().strip()
            else:
                unit_item = table.item(row, 2)
                unit = unit_item.text().strip() if unit_item else ""

            def _num(col):
                cell = table.item(row, col)
                if not cell or not cell.text():
                    return 0.0
                try:
                    return float(cell.text().replace(',', ''))
                except ValueError:
                    return 0.0

            lookup[name] = {
                "unit": unit or "pcs",
                "cbm_per_carton": _num(8),
                "total_cbm": _num(9),
            }

        return lookup

    def _tax_cbm_basis(self):
        """CBM figure Tax 2 divides by: fixed capacity or used CBM."""
        if self.tax_fixed_cbm_radio.isChecked():
            return self.tax_cbm_spin.value()
        return self._tax_used_cbm

    def recalculate_tax(self):
        """Recalculate all tax values when inputs change."""
        if not hasattr(self, 'tax_table') or self.tax_table.rowCount() == 0:
            return

        self._tax_product_info = self._product_info_lookup()
        self._tax_used_cbm = sum(
            info["total_cbm"] for info in self._tax_product_info.values()
        )

        usd_rate = self.tax_usd_rate.value()
        total_freight = self.tax_total_freight.value()
        rater = self.tax_rater.value()

        self._current_total_freight = total_freight
        self._current_rater = rater
        self._current_usd_rate = usd_rate
        self._tax_ps_values = {}

        total_tax = 0.0
        for row in range(self.tax_table.rowCount()):
            self._recalculate_tax_row(row)
            tax_item = self.tax_table.item(row, 11)
            if tax_item:
                try:
                    total_tax += float(tax_item.text().replace(',', ''))
                except ValueError:
                    pass

        self.tax_summary_label.setText(f"Total Tax Payable: ETB {total_tax:,.2f}")
        self.calculate_landed()

    def _recalculate_tax_row(self, row):
        """Recalculate a single tax row.

        Tax 1 (ETB/doz) = USD/doz × rater × USD→ETB rate
        Tax 2 (ETB/doz) = Total Freight ÷ (CBM basis ÷ CBM/ctn) ÷ Qty/doz

        The line's total tax is (Tax 1 + Tax 2) × Qty/doz, i.e. the 1st tax plus
        the 2nd tax for that product.
        """
        # Get Qty/doz from editable column 3
        qty_doz_item = self.tax_table.item(row, 3)
        if not qty_doz_item or not qty_doz_item.text():
            return

        try:
            qty_doz = float(qty_doz_item.text().replace(',', ''))
        except ValueError:
            qty_doz = 0.0

        if qty_doz <= 0:
            return

        # Get USD/doz from editable column 4
        usd_doz_item = self.tax_table.item(row, 4)
        usd_doz = 0.0
        if usd_doz_item:
            try:
                usd_doz = float(usd_doz_item.text().replace(',', ''))
            except ValueError:
                usd_doz = 0.0

        # Get shared values
        usd_rate = self._current_usd_rate
        rater = self._current_rater
        total_freight = self._current_total_freight

        # Goods value
        total_price_usd = qty_doz * usd_doz
        total_price_etb = total_price_usd * usd_rate

        # 1st tax: direct calculation on the goods value
        tax1_doz = usd_doz * rater * usd_rate
        tax1_total = tax1_doz * qty_doz

        # 2nd tax: freight share, spread over the cartons this product fills
        # (CBM basis / CBM per carton), then per dozen.
        name_item = self.tax_table.item(row, 1)
        product_name = name_item.text().strip() if name_item else ""
        cbm_per_carton = self._tax_product_info.get(product_name, {}).get(
            "cbm_per_carton", 0.0
        )
        basis_cbm = self._tax_cbm_basis()
        if cbm_per_carton > 0 and basis_cbm > 0:
            capacity_cartons = basis_cbm / cbm_per_carton
            tax2_doz = total_freight / capacity_cartons / qty_doz
        else:
            tax2_doz = 0.0
        tax2_total = tax2_doz * qty_doz

        total_tax = tax1_total + tax2_total
        tax_doz = total_tax / qty_doz if qty_doz > 0 else 0.0

        # Tax per piece: Tax/doz divided by the row's Qty/doz (not a fixed 12)
        tax_ps = tax_doz / qty_doz if qty_doz > 0 else 0.0

        self.tax_table.blockSignals(True)

        # Set computed columns
        self._set_tax_cell(row, 5, f"{total_price_usd:,.2f}")   # Total USD
        self._set_tax_cell(row, 6, f"{total_price_etb:,.2f}")   # Total ETB
        self._set_tax_cell(row, 7, f"{tax1_doz:,.2f}")          # Tax 1 /doz
        self._set_tax_cell(row, 8, f"{tax2_doz:,.2f}")          # Tax 2 /doz
        self._set_tax_cell(row, 9, f"{tax1_total:,.2f}")        # Tax 1 (ETB)
        self._set_tax_cell(row, 10, f"{tax2_total:,.2f}")       # Tax 2 (ETB)
        self._set_tax_cell(row, 11, f"{total_tax:,.2f}")        # Total Tax ETB
        self._set_tax_cell(row, 12, f"{tax_doz:,.2f}")          # Tax/doz
        self._set_tax_cell(row, 13, f"{tax_ps:,.2f}")           # Tax/pcs

        # Store tax_ps for landed cost
        product_name_item = self.tax_table.item(row, 1)
        if product_name_item:
            self._tax_ps_values[product_name_item.text().strip()] = tax_ps

        self.tax_table.blockSignals(False)

    def on_tax_paid_toggled(self, checked):
        """Show/hide bank account selection for tax payment."""
        self.tax_paid_group.setVisible(checked)
        self.tax_paid = checked
        self._tax_bank_account_id = self.tax_bank_combo.currentData() if checked else None

    def on_tax_cell_changed(self, row, col):
        """Handle changes to editable cells (Qty/doz or USD/doz)."""
        if col in (3, 4):  # Qty/doz or USD/doz
            self._recalculate_tax_row(row)
            # Update totals
            total_tax = 0.0
            for r in range(self.tax_table.rowCount()):
                tax_item = self.tax_table.item(r, 11)  # Total Tax ETB
                if tax_item:
                    try:
                        total_tax += float(tax_item.text().replace(',', ''))
                    except ValueError:
                        pass
            self.tax_summary_label.setText(f"Total Tax Payable: ETB {total_tax:,.2f}")
            self.calculate_landed()

    def get_tax_payment_data(self):
        """Get tax payment data for saving."""
        paid = self.tax_paid_checkbox.isChecked()
        return {
            "tax_paid": paid,
            "bank_account_id": self.tax_bank_combo.currentData() if paid else None,
            "payment_date": self.tax_payment_date.date().toPython() if paid else None,
        }

    def set_tax_payment_data(self, bank_account_id=None, payment_date=None, paid=False):
        """Set tax payment data from loaded shipment."""
        self._tax_bank_account_id = bank_account_id
        self._tax_payment_date = payment_date
        self._tax_paid = paid

        self.tax_paid_checkbox.setChecked(paid)
        if paid and bank_account_id:
            # Find and select the bank account in combo
            idx = self.tax_bank_combo.findData(bank_account_id)
            if idx >= 0:
                self.tax_bank_combo.setCurrentIndex(idx)
            if payment_date:
                # Convert date object to QDate
                if hasattr(payment_date, 'year'):
                    qdate = QDate(payment_date.year, payment_date.month, payment_date.day)
                    self.tax_payment_date.setDate(qdate)

    def populate_tax_table(self):
        """Populate the tax table from the current shipment products."""
        if not hasattr(self, 'tax_table'):
            return

        self.tax_table.blockSignals(True)
        self.tax_table.setRowCount(0)
        self._tax_ps_values = {}
        product_info_lookup = self._product_info_lookup()

        for row in range(self.product_table.rowCount()):
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue

            item_number = self.product_table.item(row, 0).text().strip() if self.product_table.item(row, 0) else ""
            name_widget = self.product_table.cellWidget(row, 1)
            product_name = name_widget.text().strip() if isinstance(name_widget, ModernLineEdit) else ""
            if not product_name:
                continue

            # Get total quantity from column 5
            qty_item = self.product_table.item(row, 5)
            if qty_item:
                try:
                    total_qty = float(qty_item.text().replace(',', ''))
                except ValueError:
                    total_qty = 0.0
            else:
                cartons_item = self.product_table.item(row, 3)
                qty_per_item = self.product_table.item(row, 4)
                try:
                    cartons = float(cartons_item.text() or 0) if cartons_item else 0
                    qty_per = float(qty_per_item.text() or 0) if qty_per_item else 0
                    total_qty = cartons * qty_per
                except ValueError:
                    total_qty = 0.0

            # Default Qty/doz = total_qty / 12
            qty_doz = total_qty / 12 if total_qty > 0 else 0.0

            new_row = self.tax_table.rowCount()
            self.tax_table.insertRow(new_row)

            # Column 0: Item #
            self.tax_table.setItem(new_row, 0, QTableWidgetItem(item_number))
            # Column 1: Product Name
            self.tax_table.setItem(new_row, 1, QTableWidgetItem(product_name))
            # Column 2: Unit — taken from the product row in Shipment Details
            product_info = product_info_lookup.get(product_name, {})
            unit_item = QTableWidgetItem(product_info.get("unit") or "pcs")
            unit_item.setFlags(unit_item.flags() & ~Qt.ItemIsEditable)
            unit_item.setBackground(QColor(240, 240, 240))
            self.tax_table.setItem(new_row, 2, unit_item)
            # Column 3: Qty/doz (editable)
            qty_doz_item = QTableWidgetItem(f"{qty_doz:,.2f}")
            qty_doz_item.setFlags(qty_doz_item.flags() | Qt.ItemIsEditable)
            qty_doz_item.setBackground(QColor(255, 255, 255))
            self.tax_table.setItem(new_row, 3, qty_doz_item)
            # Column 4: USD/doz (editable, empty)
            usd_doz_item = QTableWidgetItem("")
            usd_doz_item.setFlags(usd_doz_item.flags() | Qt.ItemIsEditable)
            usd_doz_item.setBackground(QColor(255, 255, 255))
            self.tax_table.setItem(new_row, 4, usd_doz_item)

        self.tax_table.blockSignals(False)

        if self.tax_table.rowCount() > 0:
            self.recalculate_tax()
        else:
            self.tax_summary_label.setText("Total Tax Payable: ETB 0.00")

    def clear_tax_table(self):
        """Clear the tax table when products change."""
        if not hasattr(self, 'tax_table'):
            return
        self.tax_table.setRowCount(0)
        self._tax_ps_values = {}
        self.tax_summary_label.setText("Total Tax Payable: ETB 0.00")

    def set_tax_read_only(self, enabled):
        """Set tax tab to read-only mode."""
        if not hasattr(self, 'tax_tab'):
            return

        for widget in self.tax_tab.findChildren(QDoubleSpinBox):
            widget.setEnabled(not enabled)

        self.tax_table.setEditTriggers(
            QTableWidget.NoEditTriggers if enabled else QTableWidget.DoubleClicked
        )

        # Lock Qty/doz (col 3) and USD/doz (col 4)
        for row in range(self.tax_table.rowCount()):
            for col in (3, 4):
                item = self.tax_table.item(row, col)
                if item:
                    if enabled:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() | Qt.ItemIsEditable)

        # Also disable tax payment UI when read-only
        self.tax_paid_checkbox.setEnabled(not enabled)
        self.tax_bank_combo.setEnabled(not enabled)

    def _set_tax_cell(self, row, col, text, editable=False):
        """Set a table cell with proper flags."""
        item = self.tax_table.item(row, col)
        if item:
            item.setText(text)
        else:
            item = QTableWidgetItem(text)
            self.tax_table.setItem(row, col, item)

        if col in (3, 4):
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setBackground(QColor(255, 255, 255))
        else:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setBackground(QColor(240, 240, 240))

    def get_total_tax_amount(self):
        """Calculate and return the total tax amount from the tax table."""
        total_tax = 0.0
        for row in range(self.tax_table.rowCount()):
            tax_item = self.tax_table.item(row, 11)  # Total Tax ETB
            if tax_item and tax_item.text():
                try:
                    total_tax += float(tax_item.text().replace(',', ''))
                except ValueError:
                    pass
        return total_tax
