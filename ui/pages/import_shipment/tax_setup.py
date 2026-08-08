#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLabel,
    QDoubleSpinBox, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from ui.pages.product_dialog import ModernLineEdit


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

        self.tax_total_usd = QDoubleSpinBox()
        self.tax_total_usd.setRange(0.0, 1000000.0)
        self.tax_total_usd.setDecimals(2)
        self.tax_total_usd.setPrefix("$ ")
        self.tax_total_usd.setValue(0.0)
        self.tax_total_usd.valueChanged.connect(self.recalculate_tax)

        self.tax_sample_frt = QDoubleSpinBox()
        self.tax_sample_frt.setRange(0.0, 1000000.0)
        self.tax_sample_frt.setDecimals(2)
        self.tax_sample_frt.setPrefix("ETB ")
        self.tax_sample_frt.setValue(0.0)
        self.tax_sample_frt.valueChanged.connect(self.recalculate_tax)

        row1_layout.addWidget(QLabel("USD to ETB Rate:"))
        row1_layout.addWidget(self.tax_usd_rate)
        row1_layout.addWidget(QLabel("Total USD:"))
        row1_layout.addWidget(self.tax_total_usd)
        row1_layout.addWidget(QLabel("Sample Freight (ETB):"))
        row1_layout.addWidget(self.tax_sample_frt)
        row1_layout.addStretch()

        # ---- Row 2 ----
        row2_widget = QWidget()
        row2_layout = QHBoxLayout(row2_widget)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(15)

        self.tax_rater = QDoubleSpinBox()
        self.tax_rater.setRange(0.0, 1.0)
        self.tax_rater.setDecimals(4)
        self.tax_rater.setSingleStep(0.01)
        self.tax_rater.setValue(0.0)
        self.tax_rater.valueChanged.connect(self.recalculate_tax)

        self.tax_freight_ratio_label = QLabel("0.0000")
        self.tax_freight_ratio_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.tax_freight_ratio_label.setStyleSheet(
            "color: #2c3e50; background-color: #f8f9fa; "
            "padding: 4px 12px; border-radius: 4px; border: 1px solid #d1d5db;"
        )

        row2_layout.addWidget(QLabel("Tax Rater:"))
        row2_layout.addWidget(self.tax_rater)
        row2_layout.addSpacing(30)
        row2_layout.addWidget(QLabel("Tax Freight Ratio:"))
        row2_layout.addWidget(self.tax_freight_ratio_label)
        row2_layout.addStretch()

        input_layout.addRow(row1_widget)
        input_layout.addRow(row2_widget)
        layout.addWidget(input_group)

        # ---- Product Tax Table (EXPANDS to fill remaining space) ----
        table_group = QGroupBox("Product Tax Calculation")
        table_layout = QVBoxLayout(table_group)

        self.tax_table = QTableWidget()
        self.tax_table.setColumnCount(14)
        self.tax_table.setHorizontalHeaderLabels([
            "Item #", "Product Name", "Unit", "Qty/doz", "USD/doz",
            "Total USD", "Total ETB", "FRT Ratio", "FRT/CRT",
            "DPV/CRT", "Rater", "Total Tax ETB", "Tax/doz", "Tax/pcs"
        ])

        # Column widths
        self.tax_table.setColumnWidth(0, 100)
        self.tax_table.setColumnWidth(1, 200)
        self.tax_table.setColumnWidth(2, 80)
        self.tax_table.setColumnWidth(3, 80)   # Qty/doz
        self.tax_table.setColumnWidth(4, 100)  # USD/doz
        self.tax_table.setColumnWidth(5, 100)
        self.tax_table.setColumnWidth(6, 100)
        self.tax_table.setColumnWidth(7, 80)
        self.tax_table.setColumnWidth(8, 100)
        self.tax_table.setColumnWidth(9, 100)
        self.tax_table.setColumnWidth(10, 80)
        self.tax_table.setColumnWidth(11, 120)
        self.tax_table.setColumnWidth(12, 100)
        self.tax_table.setColumnWidth(13, 100)

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

        self.tabs.addTab(self.tax_tab, "💰 Custom Tax")

        # Initialise tax values
        self._tax_ps_values = {}
        self._current_freight_ratio = 0.0
        self._current_rater = 0.15
        self._current_usd_rate = 160.00

    # ------------------------------------------------------------------
    # All methods below remain exactly as they were (no changes needed)
    # because they already use the correct attribute names.
    # ------------------------------------------------------------------

    def recalculate_tax(self):
        """Recalculate all tax values when inputs change."""
        if not hasattr(self, 'tax_table') or self.tax_table.rowCount() == 0:
            return

        usd_rate = self.tax_usd_rate.value()
        total_usd = self.tax_total_usd.value()
        sample_frt = self.tax_sample_frt.value()
        rater = self.tax_rater.value()

        if sample_frt > 0:
            freight_ratio = (total_usd * usd_rate) / sample_frt
        else:
            freight_ratio = 0.0
        self.tax_freight_ratio_label.setText(f"{freight_ratio:.4f}")

        self._current_freight_ratio = freight_ratio
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
        """Recalculate a single tax row."""
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
        freight_ratio = self._current_freight_ratio
        rater = self._current_rater

        # Calculate all columns
        total_price_usd = qty_doz * usd_doz
        total_price_etb = total_price_usd * usd_rate
        frt_ct = total_price_etb / freight_ratio if freight_ratio != 0 else 0.0
        dpv_ct = total_price_etb + frt_ct
        total_tax = rater * dpv_ct
        tax_doz = total_tax / qty_doz if qty_doz > 0 else 0.0
        tax_ps = tax_doz / 12 if tax_doz > 0 else 0.0

        self.tax_table.blockSignals(True)

        # Set computed columns
        self._set_tax_cell(row, 5, f"{total_price_usd:,.2f}", editable=False)   # Total USD
        self._set_tax_cell(row, 6, f"{total_price_etb:,.2f}", editable=False)   # Total ETB
        self._set_tax_cell(row, 7, f"{freight_ratio:.4f}", editable=False)      # FRT Ratio
        self._set_tax_cell(row, 8, f"{frt_ct:,.2f}", editable=False)            # FRT/CT
        self._set_tax_cell(row, 9, f"{dpv_ct:,.2f}", editable=False)            # DPV/CT
        self._set_tax_cell(row, 10, f"{rater:.4f}", editable=False)             # Rater
        self._set_tax_cell(row, 11, f"{total_tax:,.2f}", editable=False)        # Total Tax
        self._set_tax_cell(row, 12, f"{tax_doz:,.2f}", editable=False)          # Tax/doz
        self._set_tax_cell(row, 13, f"{tax_ps:,.2f}", editable=False)           # Tax/pcs

        # Store tax_ps for landed cost
        product_name_item = self.tax_table.item(row, 1)
        if product_name_item:
            self._tax_ps_values[product_name_item.text().strip()] = tax_ps

        self.tax_table.blockSignals(False)

    def _set_tax_cell(self, row, col, text, editable=False):
        """Set a table cell with proper flags."""
        item = self.tax_table.item(row, col)
        if item:
            item.setText(text)
        else:
            item = QTableWidgetItem(text)
            self.tax_table.setItem(row, col, item)

        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setBackground(QColor(240, 240, 240))
        else:
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setBackground(QColor(255, 255, 255))

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

    def populate_tax_table(self):
        """Populate the tax table from the current shipment products."""
        if not hasattr(self, 'tax_table'):
            return

        self.tax_table.blockSignals(True)
        self.tax_table.setRowCount(0)
        self._tax_ps_values = {}

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
            # Column 2: Unit (always "Doz")
            unit_item = QTableWidgetItem("Doz")
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

    # def _update_landed_tax_values(self):
    #     """Update the Tax/Ps values in the landed cost table (Tab 4)."""
    #     if not hasattr(self, '_tax_ps_values') or not hasattr(self, 'landed_table'):
    #         return

    #     for row in range(self.landed_table.rowCount()):
    #         name_item = self.landed_table.item(row, 0)
    #         if name_item:
    #             product_name = name_item.text().strip()
    #             tax_ps = self._tax_ps_values.get(product_name, 0.0)
    #             # Column 7 is now Tax/Ps
    #             if self.landed_table.columnCount() > 7:
    #                 tax_item = self.landed_table.item(row, 7)
    #                 if tax_item:
    #                     tax_item.setText(f"{tax_ps:,.2f}")

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