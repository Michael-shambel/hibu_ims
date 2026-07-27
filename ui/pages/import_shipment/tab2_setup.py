from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QDoubleSpinBox, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QRadioButton,
    QSpinBox, QFormLayout, QGroupBox, QWidget, QApplication, QTabWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from .cost_item_dialog import AddCostItemDialog

class Tab2SetupMixin:
    """Contains setup_tab2 and cost management methods."""

    def setup_tab2(self):
        """Build Tab 2: Costs & Allocation."""
        self.tab2 = QWidget()
        layout = QVBoxLayout(self.tab2)
    
        # --- Cost Table ---
        cost_group = QGroupBox("Additional Costs (Allocated By CBM)")
        cost_layout = QVBoxLayout(cost_group)
    
        self.cost_table = QTableWidget()
        self.cost_table.setColumnCount(2)
        self.cost_table.setHorizontalHeaderLabels(["Cost Type", "Amount (ETB)"])
        self.cost_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cost_table.setColumnWidth(1, 150)
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
    
        # --- Allocation Matrix ---
        matrix_group = QGroupBox("Cost Allocation Breakdown (ETB)")
        matrix_layout = QVBoxLayout(matrix_group)
    
        self.alloc_table = QTableWidget()
        self.alloc_table.setAlternatingRowColors(True)
        matrix_layout.addWidget(self.alloc_table)
    
        layout.addWidget(matrix_group)
    
        # Connect cost table selection
        self.cost_table.itemSelectionChanged.connect(self.on_cost_selection_changed)
    
        self.tabs.addTab(self.tab2, "💰 Costs & Allocation")

    def open_add_cost_dialog(self):
        """Open the add cost item dialog."""
        dialog = AddCostItemDialog(self.cost_type_service, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            self.add_cost_row(data)

    def get_costs_from_table(self):
        """Extract cost data from the cost table."""
        costs = []
        for row in range(self.cost_table.rowCount()):
            cost_type_item = self.cost_table.item(row, 0)
            amount_item = self.cost_table.item(row, 1)
            if not cost_type_item or not amount_item:
                continue
            cost_type_id = cost_type_item.data(Qt.UserRole)
            if not cost_type_id:
                continue
            try:
                amount = float(amount_item.text().replace(',', ''))
            except ValueError:
                continue
            costs.append({
                "cost_type_id": cost_type_id,
                "amount": amount
            })
        return costs

    def add_cost_row(self, data):
        """Add a cost row to the cost table. Prevents duplicate cost types."""
        cost_type_id = data.get("cost_type_id")
        if not cost_type_id:
            return False
            
        # --- Check for duplicate cost type in the current table ---
        for row_idx in range(self.cost_table.rowCount()):
            existing_item = self.cost_table.item(row_idx, 0)
            if existing_item:
                existing_id = existing_item.data(Qt.UserRole)
                if existing_id == cost_type_id:
                    QMessageBox.warning(
                        self,
                        "Duplicate Cost Type",
                        f"Cost type '{data.get('cost_type_name', 'Unknown')}' is already added to this shipment.\nPlease use a different cost type or edit the existing one."
                    )
                    return False

        # --- Proceed with adding the row ---
        row = self.cost_table.rowCount()
        self.cost_table.insertRow(row)

        # Cost Type (store the ID for later)
        cost_type_name = data["cost_type_name"]
        item = QTableWidgetItem(cost_type_name)
        item.setData(Qt.UserRole, cost_type_id)  # store ID
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.cost_table.setItem(row, 0, item)

        # Amount
        amount_item = QTableWidgetItem(f"{data['amount']:,.2f}")
        amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cost_table.setItem(row, 1, amount_item)

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
        Called when a cost table cell is changed.
        If the Amount column (col 1) is edited, update totals and recalculate.
        """
        # Only react to changes in the Amount column (col 1)
        if col != 1:
            return
    
        # Validate that the entered value is a valid number
        amount_item = self.cost_table.item(row, col)
        if not amount_item:
            return
    
        try:
            # Try to parse the amount, removing commas
            amount_text = amount_item.text().replace(',', '')
            amount = float(amount_text)
            if amount < 0:
                raise ValueError
            # Update the display with formatted number
            amount_item.setText(f"{amount:,.2f}")
        except ValueError:
            # If invalid, reset to 0.00 and show a warning
            QMessageBox.warning(self, "Invalid Amount", "Please enter a valid positive number.")
            amount_item.setText("0.00")
            # Don't recalculate if invalid
    
        # Update total costs and recalculate allocation
        self.update_total_costs()
        self.calculate_landed()

    def on_cost_selection_changed(self):
        """Enable/disable remove cost button based on selection."""
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