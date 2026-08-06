from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QTabWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from .cost_item_dialog import AddCostItemDialog
from ui.pages.product_dialog import ModernLineEdit

class Tab2SetupMixin:
    """Contains setup_tab2 and cost management methods."""

    def setup_tab2(self):
        """Build Tab 2: Costs & Allocation."""
        self.tab2 = QWidget()
        layout = QVBoxLayout(self.tab2)

        # ===== Allocation Mode Selection =====
        mode_group = QGroupBox("Container Allocation Basis")
        mode_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
            }
        """)
        mode_layout = QVBoxLayout(mode_group)

        mode_radio_layout = QHBoxLayout()
        self.fixed_cbm_radio = QRadioButton("Fixed Container Capacity (68 CBM)")
        self.used_cbm_radio = QRadioButton("Total Used CBM")
        self.used_cbm_radio.setChecked(True)

        self.fixed_cbm_radio.toggled.connect(self.on_allocation_mode_changed)
        self.used_cbm_radio.toggled.connect(self.on_allocation_mode_changed)

        self.fixed_cbm_spin = QDoubleSpinBox()
        self.fixed_cbm_spin.setRange(1.0, 1000.0)
        self.fixed_cbm_spin.setDecimals(1)
        self.fixed_cbm_spin.setValue(68.0)
        self.fixed_cbm_spin.setSuffix(" CBM")
        self.fixed_cbm_spin.setEnabled(False)
        self.fixed_cbm_spin.valueChanged.connect(self.on_allocation_mode_changed)

        self.fixed_cbm_radio.toggled.connect(
            lambda checked: self.fixed_cbm_spin.setEnabled(checked)
        )

        mode_radio_layout.addWidget(self.fixed_cbm_radio)
        mode_radio_layout.addWidget(self.fixed_cbm_spin)
        mode_radio_layout.addSpacing(20)
        mode_radio_layout.addWidget(self.used_cbm_radio)
        mode_radio_layout.addStretch()

        mode_layout.addLayout(mode_radio_layout)

        self.dead_freight_label = QLabel("⚠️ Dead Freight (unallocated cost): ETB 0.00")
        self.dead_freight_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 5px;")
        self.dead_freight_label.setVisible(False)
        mode_layout.addWidget(self.dead_freight_label)

        self.container_capacity = 68.0
        layout.addWidget(mode_group)

        # ===== Cost Table (now with 4 columns) =====
        cost_group = QGroupBox("Additional Costs (Allocated By CBM)")
        cost_layout = QVBoxLayout(cost_group)

        self.cost_table = QTableWidget()
        self.cost_table.setColumnCount(4)
        self.cost_table.setHorizontalHeaderLabels([
            "Cost Type", "Amount (ETB)", "Paid Date", "Bank Account"
        ])
        self.cost_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cost_table.setColumnWidth(1, 150)
        self.cost_table.setColumnWidth(2, 120)
        self.cost_table.setColumnWidth(3, 180)
        self.cost_table.setAlternatingRowColors(True)
        self.cost_table.setEditTriggers(QTableWidget.DoubleClicked)
        self.cost_table.cellChanged.connect(self.on_cost_table_cell_changed)
        cost_layout.addWidget(self.cost_table)

        # Cost toolbar
        cost_btn_layout = QHBoxLayout()
        self.add_cost_btn = QPushButton("➕ Add Cost")
        self.add_cost_btn.setMinimumHeight(35)
        self.add_cost_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498db, stop:1 #2980b9);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 15px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2980b9, stop:1 #2471a3);
            }
        """)
        self.add_cost_btn.clicked.connect(self.open_add_cost_dialog)

        self.remove_cost_btn = QPushButton("🗑️ Remove Selected")
        self.remove_cost_btn.setMinimumHeight(35)
        self.remove_cost_btn.setEnabled(False)
        self.remove_cost_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e74c3c, stop:1 #c0392b);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 15px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c0392b, stop:1 #a93226);
            }
            QPushButton:disabled {
                background: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.remove_cost_btn.clicked.connect(self.remove_selected_cost)

        cost_btn_layout.addWidget(self.add_cost_btn)
        cost_btn_layout.addWidget(self.remove_cost_btn)
        cost_btn_layout.addStretch()
        cost_layout.addLayout(cost_btn_layout)

        self.total_costs_label = QLabel("Total Additional Costs: ETB 0.00")
        self.total_costs_label.setStyleSheet("font-weight: bold; color: #2c3e50; padding: 5px;")
        cost_layout.addWidget(self.total_costs_label)

        layout.addWidget(cost_group)

        # ===== Allocation Matrix =====
        matrix_group = QGroupBox("Cost Allocation Breakdown (ETB)")
        matrix_layout = QVBoxLayout(matrix_group)

        self.alloc_table = QTableWidget()
        self.alloc_table.setAlternatingRowColors(True)
        matrix_layout.addWidget(self.alloc_table)

        layout.addWidget(matrix_group)

        self.cost_table.itemSelectionChanged.connect(self.on_cost_selection_changed)

        self.tabs.addTab(self.tab2, "💰 Costs & Allocation")

    # ------------------------------------------------------------------
    # Dialog and data methods
    # ------------------------------------------------------------------
    def open_add_cost_dialog(self):
        """Open the add cost item dialog."""
        # Check if there are any products in the product table
        row_count = self.product_table.rowCount()
        has_products = False
        for row in range(row_count):
            # Skip the summary row (if any)
            if self.product_table.item(row, 0) and self.product_table.item(row, 0).text() == "TOTAL":
                continue
            # Check product name column (column 1)
            name_widget = self.product_table.cellWidget(row, 0)
            if name_widget and isinstance(name_widget, ModernLineEdit):
                if name_widget.text().strip():
                    has_products = True
                    break
            else:
                name_item = self.product_table.item(row, 0)
                if name_item and name_item.text().strip():
                    has_products = True
                    break

        if not has_products:
            QMessageBox.warning(
                self,
                "No Products",
                "Please add at least one product to the shipment before adding costs.\n"
                "Costs are allocated proportionally based on product quantities."
            )
            return

        dialog = AddCostItemDialog(self.cost_type_service, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            self.add_cost_row(data)

    def get_costs_from_table(self):
        """
        Extract full cost data from the cost table.
        Returns a list of dicts with all fields including paid status,
        bank_account_id, and payment_date.
        """
        costs = []
        for row in range(self.cost_table.rowCount()):
            # Retrieve the stored full data dict from the row's first item
            cost_type_item = self.cost_table.item(row, 0)
            if not cost_type_item:
                continue

            # Try to get the full data from UserRole+1
            full_data = cost_type_item.data(Qt.UserRole + 1)
            if full_data and isinstance(full_data, dict):
                # Ensure amount is up-to-date (user might have edited it)
                amount_item = self.cost_table.item(row, 1)
                if amount_item:
                    try:
                        full_data['amount'] = float(amount_item.text().replace(',', ''))
                    except ValueError:
                        full_data['amount'] = 0.0
                costs.append(full_data)
            else:
                # Fallback: build minimal dict from visible data
                cost_type_id = cost_type_item.data(Qt.UserRole)
                cost_type_name = cost_type_item.text()
                amount_item = self.cost_table.item(row, 1)
                amount = float(amount_item.text().replace(',', '')) if amount_item else 0.0
                paid_date_item = self.cost_table.item(row, 2)
                bank_item = self.cost_table.item(row, 3)
                paid = bool(paid_date_item and paid_date_item.text() not in ("", "N/A"))
                costs.append({
                    "cost_type_id": cost_type_id,
                    "cost_type_name": cost_type_name,
                    "amount": amount,
                    "paid": paid,
                    "payment_date": paid_date_item.data(Qt.UserRole) if paid_date_item else None,
                    "bank_account_id": bank_item.data(Qt.UserRole) if bank_item else None,
                    "bank_account_name": bank_item.text() if bank_item else "",
                })
        return costs

    def add_cost_row(self, data):
        """
        Add a cost row to the table.
        data is a dict with keys:
            cost_type_id, cost_type_name, amount,
            paid (bool), payment_date (QDate or datetime.date), bank_account_id, bank_account_name
        """
        cost_type_id = data.get("cost_type_id")
        if not cost_type_id:
            return False

        # Prevent duplicate cost types
        for row_idx in range(self.cost_table.rowCount()):
            existing_item = self.cost_table.item(row_idx, 0)
            if existing_item:
                existing_id = existing_item.data(Qt.UserRole)
                if existing_id == cost_type_id:
                    QMessageBox.warning(
                        self,
                        "Duplicate Cost Type",
                        f"Cost type '{data.get('cost_type_name', 'Unknown')}' is already added."
                    )
                    return False

        row = self.cost_table.rowCount()
        self.cost_table.insertRow(row)

        # ---- Column 0: Cost Type ----
        item = QTableWidgetItem(data["cost_type_name"])
        item.setData(Qt.UserRole, cost_type_id)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        # Store the full data dict for later retrieval
        item.setData(Qt.UserRole + 1, data)
        self.cost_table.setItem(row, 0, item)

        # ---- Column 1: Amount ----
        amount_item = QTableWidgetItem(f"{data['amount']:,.2f}")
        amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cost_table.setItem(row, 1, amount_item)

        # ---- Column 2: Paid Date ----
        paid = data.get("paid", False)
        if paid and data.get("payment_date"):
            from PySide6.QtCore import QDate
            payment_date = data["payment_date"]
            if isinstance(payment_date, QDate):
                date_str = payment_date.toString("dd/MM/yyyy")
            else:
                # assume datetime.date or similar
                date_str = payment_date.strftime("%d/%m/%Y")
            date_item = QTableWidgetItem(date_str)
            date_item.setData(Qt.UserRole, payment_date)
            date_item.setFlags(date_item.flags() & ~Qt.ItemIsEditable)
            self.cost_table.setItem(row, 2, date_item)
        else:
            date_item = QTableWidgetItem("")
            date_item.setFlags(date_item.flags() & ~Qt.ItemIsEditable)
            self.cost_table.setItem(row, 2, date_item)

        # ---- Column 3: Bank Account ----
        if paid and data.get("bank_account_id"):
            bank_name = data.get("bank_account_name", "Unknown")
            bank_item = QTableWidgetItem(bank_name)
            bank_item.setData(Qt.UserRole, data["bank_account_id"])
            bank_item.setFlags(bank_item.flags() & ~Qt.ItemIsEditable)
            self.cost_table.setItem(row, 3, bank_item)
        else:
            bank_item = QTableWidgetItem("")
            bank_item.setFlags(bank_item.flags() & ~Qt.ItemIsEditable)
            self.cost_table.setItem(row, 3, bank_item)

        # Update totals and recalc
        self.update_total_costs()
        self.calculate_landed()
        return True

    def remove_selected_cost(self):
        """Remove the selected cost row."""
        selected = self.cost_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        self.cost_table.removeRow(row)
        self.update_total_costs()
        self.calculate_landed()

    def on_cost_table_cell_changed(self, row, col):
        """
        When Amount (col 1) is edited, update totals and recalc.
        Other columns are read-only and won't trigger this.
        """
        if col != 1:
            return

        amount_item = self.cost_table.item(row, col)
        if not amount_item:
            return

        try:
            amount_text = amount_item.text().replace(',', '')
            amount = float(amount_text)
            if amount < 0:
                raise ValueError
            amount_item.setText(f"{amount:,.2f}")
            # Update stored data dict with new amount
            cost_type_item = self.cost_table.item(row, 0)
            if cost_type_item:
                full_data = cost_type_item.data(Qt.UserRole + 1)
                if full_data:
                    full_data['amount'] = amount
                    cost_type_item.setData(Qt.UserRole + 1, full_data)
        except ValueError:
            QMessageBox.warning(self, "Invalid Amount", "Please enter a valid positive number.")
            amount_item.setText("0.00")

        self.update_total_costs()
        self.calculate_landed()

    def on_cost_selection_changed(self):
        """Enable/disable remove button based on selection."""
        selected = self.cost_table.selectedItems()
        self.remove_cost_btn.setEnabled(len(selected) > 0)

    def update_total_costs(self):
        """Update the total costs label."""
        total = 0.0
        for row in range(self.cost_table.rowCount()):
            amount_item = self.cost_table.item(row, 1)
            if amount_item:
                try:
                    total += float(amount_item.text().replace(',', ''))
                except ValueError:
                    pass
        self.total_costs_label.setText(f"Total Additional Costs: ETB {total:,.2f}")

    def on_allocation_mode_changed(self):
        """Handle changes to allocation mode."""
        if self.fixed_cbm_radio.isChecked():
            self.allocation_mode = "fixed"
            self.container_capacity = self.fixed_cbm_spin.value()
        else:
            self.allocation_mode = "used_cbm"
        self.calculate_landed()