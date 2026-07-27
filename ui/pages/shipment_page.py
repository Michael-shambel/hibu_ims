from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from services.import_shipment_service import ImportShipmentService
from ui.pages.import_shipment import ImportShipmentDialog


class ImportShipmentPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.service = ImportShipmentService()
        self.init_ui()
        self.refresh()

    def init_ui(self):
        """Initialize the modern UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== TOOLBAR ====================
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 10, 15, 10)
        toolbar_layout.setSpacing(15)

        # New Shipment button
        self.add_btn = QPushButton("➕ New Shipment")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.add_btn.clicked.connect(self.open_new_shipment_dialog)

        # Refresh button
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh)

        # Delete button (enabled only when a row is selected)
        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover:enabled {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.delete_btn.clicked.connect(self.delete_selected_shipment)

        toolbar_layout.addWidget(self.add_btn)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addStretch()

        main_layout.addWidget(toolbar)

        # ==================== TABLE AREA ====================
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(15, 0, 15, 15)
        table_layout.setSpacing(10)

        title = QLabel("🚢 Import Shipments (Proformas)")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        table_layout.addWidget(title)

        self.table = self.create_shipment_table()
        table_layout.addWidget(self.table)

        main_layout.addWidget(table_container, 1)

        # ==================== STATUS BAR ====================
        status_bar = QWidget()
        status_bar.setFixedHeight(30)
        status_bar.setStyleSheet("background-color: #34495e;")

        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 0, 10, 0)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")

        self.stats_label = QLabel("Total: 0 shipments")
        self.stats_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.stats_label)

        main_layout.addWidget(status_bar)

        # Connect selection signal for delete button
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

    def create_shipment_table(self):
        """Create the shipment table."""
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "ID", "Supplier", "Bank", "Date", "Exchange Rate",
            "FOB (ETB)", "Total Landed (ETB)", "Status"
        ])
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        table.setFont(font)

        # Set column widths
        table.setColumnWidth(0, 70)
        table.setColumnWidth(1, 200)
        table.setColumnWidth(2, 200)
        table.setColumnWidth(3, 120)
        table.setColumnWidth(4, 110)
        table.setColumnWidth(5, 150)
        table.setColumnWidth(6, 150)
        table.setColumnWidth(7, 120)

        # Style
        table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d8e0;
            }
            QTableWidget::item {
                padding: 10px;
            }
            QTableWidget::item:selected {
                background-color: #d9e8f7;
            }
            QHeaderView::section {
                background-color: #e6ecf2;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #c0c8d0;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSortingEnabled(True)

        # Double-click to edit/view
        table.doubleClicked.connect(self.on_table_double_clicked)

        return table

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    def refresh(self):
        """Refresh the shipment list from database."""
        self.status_label.setText("Loading...")
        self.status_label.setStyleSheet("color: #f39c12; font-size: 12px;")

        try:
            shipments = self.service.get_all()
            self.table.setRowCount(0)

            if not shipments:
                self.stats_label.setText("Total: 0 shipments")
                self.status_label.setText("Ready")
                self.status_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")
                return

            self.table.setRowCount(len(shipments))
            total_fob = 0.0
            total_landed = 0.0
            draft_count = 0
            approved_count = 0

            for row, shipment in enumerate(shipments):
                # Calculate FOB and Total Landed
                fob_total = 0.0
                for product in shipment.products:
                    if not product.is_deleted:
                        fob_total += product.total_quantity * product.unit_price_rmb * shipment.exchange_rate

                total_costs = sum(c.amount for c in shipment.costs if not c.is_deleted)
                total_landed_shipment = fob_total + total_costs

                # ID
                id_item = QTableWidgetItem(str(shipment.id))
                id_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 0, id_item)

                # Supplier
                supplier_name = shipment.supplier.supplier_name if shipment.supplier else "N/A"
                self.table.setItem(row, 1, QTableWidgetItem(supplier_name))

                # Bank
                bank_name = shipment.bank_account.account_name if shipment.bank_account else "N/A"
                self.table.setItem(row, 2, QTableWidgetItem(bank_name))

                # Date
                date_str = shipment.proforma_date.strftime("%d/%m/%Y") if shipment.proforma_date else "N/A"
                date_item = QTableWidgetItem(date_str)
                date_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 3, date_item)

                # Exchange Rate
                rate_item = QTableWidgetItem(f"{shipment.exchange_rate:.4f}")
                rate_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 4, rate_item)

                # FOB (ETB)
                fob_item = QTableWidgetItem(f"{fob_total:,.2f}")
                fob_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 5, fob_item)

                # Total Landed (ETB)
                landed_item = QTableWidgetItem(f"{total_landed_shipment:,.2f}")
                landed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 6, landed_item)

                # Status
                status_text = shipment.status.value.title() if shipment.status else "Draft"
                status_item = QTableWidgetItem(status_text)
                status_item.setTextAlignment(Qt.AlignCenter)

                if shipment.status and shipment.status.value == "approved":
                    status_item.setBackground(QColor(200, 255, 200))
                    status_item.setForeground(QColor(0, 150, 0))
                    approved_count += 1
                elif shipment.status and shipment.status.value == "cancelled":
                    status_item.setBackground(QColor(255, 200, 200))
                    status_item.setForeground(QColor(200, 0, 0))
                else:
                    status_item.setBackground(QColor(255, 255, 200))
                    status_item.setForeground(QColor(150, 150, 0))
                    draft_count += 1

                status_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
                self.table.setItem(row, 7, status_item)

                # Store shipment ID for later use
                self.table.item(row, 0).setData(Qt.UserRole, shipment.id)

                total_fob += fob_total
                total_landed += total_landed_shipment

            self.stats_label.setText(
                f"Total: {len(shipments)} shipments  |  Draft: {draft_count}  |  Approved: {approved_count}  |  "
                f"Total FOB: {total_fob:,.2f} ETB  |  Total Landed: {total_landed:,.2f} ETB"
            )
            self.status_label.setText("Ready")
            self.status_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")

        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")

    # ------------------------------------------------------------------
    # Selection Handling
    # ------------------------------------------------------------------
    def on_selection_changed(self):
        """Enable/disable delete button based on selection."""
        selected = self.table.selectedItems()
        self.delete_btn.setEnabled(len(selected) > 0)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def open_new_shipment_dialog(self):
        """Open the dialog to create a new shipment."""
        dialog = ImportShipmentDialog(
            parent=self,
            current_user=self.current_user,
            mode="create"
        )
        if dialog.exec():
            self.refresh()

    def on_table_double_clicked(self, index):
        """Open the shipment for editing/viewing when double-clicked."""
        row = index.row()
        # Make sure the row index is valid and the item exists
        id_item = self.table.item(row, 0)
        if not id_item:
            return

        shipment_id = id_item.data(Qt.UserRole)
        if not shipment_id:
            # Fallback: try to parse the ID from text
            try:
                shipment_id = int(id_item.text())
            except ValueError:
                return

        # Check status
        status_item = self.table.item(row, 7)
        if status_item and "Approved" in status_item.text():
            mode = "view"
        else:
            mode = "edit"

        dialog = ImportShipmentDialog(
            parent=self,
            current_user=self.current_user,
            mode=mode,
            shipment_id=shipment_id
        )
        if dialog.exec():
            self.refresh()

    def delete_selected_shipment(self):
        selected = self.table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        id_item = self.table.item(row, 0)
        if not id_item:
            return

        shipment_id = id_item.data(Qt.UserRole)
        if not shipment_id:
            try:
                shipment_id = int(id_item.text())
            except ValueError:
                return

        status_item = self.table.item(row, 7)
        if status_item and "Approved" in status_item.text():
            QMessageBox.warning(self, "Cannot Delete", "Approved shipments cannot be deleted.")
            return