from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy, QStackedWidget, QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from services.import_shipment_service import ImportShipmentService
from ui.pages.import_shipment import ImportShipmentDialog


# ======================================================================
# Small reusable widgets
# ======================================================================
class StatCard(QFrame):
    """A compact KPI card used in the dashboard strip at the top of the page."""

    def __init__(self, title, value, color="#3498db", icon="📦", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(86)
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background-color: white;
                border-radius: 10px;
                border: 1px solid #e6ecf2;
                border-left: 4px solid {color};
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        header_row = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18px;")
        header_row.addWidget(icon_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        self.value_label = QLabel(str(value))
        self.value_label.setFont(QFont("Segoe UI", 17, QFont.Bold))
        self.value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(self.value_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: 600;")
        layout.addWidget(title_label)

    def set_value(self, value):
        self.value_label.setText(str(value))


def make_row_action_button(text, tooltip, color, hover_color):
    btn = QPushButton(text)
    btn.setToolTip(tooltip)
    btn.setFixedSize(30, 26)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
    """)
    return btn


# ======================================================================
# Main page
# ======================================================================
class ImportShipmentPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.service = ImportShipmentService()
        self.all_shipments = []  # cached, unfiltered list from the last refresh

        self.init_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def init_ui(self):
        """Initialize the modern UI. status_value"""
        self.setStyleSheet("background-color: #f4f6f9;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== TOOLBAR ====================
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: white; border-bottom: 1px solid #e6ecf2;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 14, 20, 14)
        toolbar_layout.setSpacing(12)

        title = QLabel("🚢 Import Shipments")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color: #2c3e50;")
        toolbar_layout.addWidget(title)

        toolbar_layout.addStretch()

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search by supplier or bank...")
        self.search_input.setFixedWidth(260)
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d9e0;
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 13px;
                background-color: #f8f9fa;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
                background-color: white;
            }
        """)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.apply_filters)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())
        toolbar_layout.addWidget(self.search_input)

        # Status filter
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Statuses", "Draft", "Approved", "Cancelled"])
        self.status_filter.setFixedWidth(150)
        self.status_filter.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d9e0;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                background-color: #f8f9fa;
            }
        """)
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        toolbar_layout.addWidget(self.status_filter)

        # New Shipment button
        self.add_btn = QPushButton("➕  New Shipment")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 9px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:pressed { background-color: #21618c; }
        """)
        self.add_btn.clicked.connect(self.open_new_shipment_dialog)
        toolbar_layout.addWidget(self.add_btn)

        # Refresh button
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setToolTip("Refresh list")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setFixedSize(38, 38)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #dfe6e9; }
        """)
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(toolbar)

        # ==================== KPI DASHBOARD ====================
        dashboard = QWidget()
        dashboard_layout = QHBoxLayout(dashboard)
        dashboard_layout.setContentsMargins(20, 16, 20, 8)
        dashboard_layout.setSpacing(14)

        self.card_total = StatCard("TOTAL SHIPMENTS", "0", "#3498db", "🚢")
        self.card_draft = StatCard("DRAFT", "0", "#f39c12", "📝")
        self.card_approved = StatCard("APPROVED", "0", "#27ae60", "✅")
        self.card_fob = StatCard("TOTAL FOB (ETB)", "0.00", "#8e44ad", "💵")
        self.card_landed = StatCard("TOTAL LANDED (ETB)", "0.00", "#16a085", "📦")

        for card in (self.card_total, self.card_draft, self.card_approved,
                     self.card_fob, self.card_landed):
            dashboard_layout.addWidget(card)

        main_layout.addWidget(dashboard)

        # ==================== CONTENT (TABLE / EMPTY STATE) ====================
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(20, 8, 20, 15)
        table_layout.setSpacing(10)

        self.content_stack = QStackedWidget()

        self.table = self.create_shipment_table()
        self.empty_state = self.create_empty_state()

        self.content_stack.addWidget(self.table)        # index 0
        self.content_stack.addWidget(self.empty_state)   # index 1

        table_layout.addWidget(self.content_stack, 1)
        main_layout.addWidget(table_container, 1)

        # ==================== STATUS BAR ====================
        status_bar = QWidget()
        status_bar.setFixedHeight(30)
        status_bar.setStyleSheet("background-color: #34495e;")

        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(15, 0, 15, 0)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")

        self.stats_label = QLabel("Total: 0 shipments")
        self.stats_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.stats_label)

        main_layout.addWidget(status_bar)

        # Connect selection signal (kept for keyboard users / Delete key)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

    def create_shipment_table(self):
        """Create the shipment table."""
        table = QTableWidget()
        table.setColumnCount(9)
        table.setHorizontalHeaderLabels([
            "ID", "Supplier", "Bank", "Date", "Exchange Rate",
            "FOB (ETB)", "Total Landed (ETB)", "Status", "Actions"
        ])
        font = QFont("Segoe UI", 10)
        table.setFont(font)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        header.setSectionResizeMode(8, QHeaderView.Fixed)

        table.setColumnWidth(0, 60)
        table.setColumnWidth(3, 110)
        table.setColumnWidth(4, 110)
        table.setColumnWidth(5, 150)
        table.setColumnWidth(6, 160)
        table.setColumnWidth(7, 110)
        table.setColumnWidth(8, 160)

        table.setStyleSheet("""
            QTableWidget {
                gridline-color: #edf0f3;
                background-color: white;
                border: 1px solid #e6ecf2;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #d9e8f7;
                color: #2c3e50;
            }
            QHeaderView::section {
                background-color: #f7f9fb;
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid #e6ecf2;
                font-weight: 600;
                font-size: 12px;
                color: #566573;
            }
        """)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(table.styleSheet() + """
            QTableWidget { alternate-background-color: #fafbfc; }
        """)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(48)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSortingEnabled(True)
        table.setToolTip("Double-click a row to view or edit that shipment.")

        table.doubleClicked.connect(self.on_table_double_clicked)

        return table

    def create_empty_state(self):
        """Friendly placeholder shown when there are no shipments to display."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        icon = QLabel("📭")
        icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        self.empty_title = QLabel("No shipments yet")
        self.empty_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.empty_title.setStyleSheet("color: #2c3e50;")
        self.empty_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_title)

        self.empty_subtitle = QLabel("Create your first import shipment to get started.")
        self.empty_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        self.empty_subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_subtitle)

        cta_btn = QPushButton("➕  New Shipment")
        cta_btn.setCursor(Qt.PointingHandCursor)
        cta_btn.setFixedWidth(180)
        cta_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-weight: 600;
                font-size: 13px;
                margin-top: 8px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        cta_btn.clicked.connect(self.open_new_shipment_dialog)
        layout.addWidget(cta_btn, alignment=Qt.AlignCenter)

        return widget

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    def refresh(self):
        """Refresh the shipment list from the database."""
        self.status_label.setText("Loading...")
        self.status_label.setStyleSheet("color: #f39c12; font-size: 12px;")

        try:
            self.all_shipments = self.service.get_all()
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            QMessageBox.critical(self, "Load Failed", f"Could not load shipments:\n{str(e)}")
            return

        self.update_dashboard(self.all_shipments)
        self.apply_filters()

        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #bdc3c7; font-size: 12px;")

    def update_dashboard(self, shipments):
        """Recalculate the KPI cards from the full (unfiltered) shipment list."""
        total_fob = 0.0
        total_landed = 0.0
        draft_count = 0
        approved_count = 0

        for shipment in shipments:
            fob_total = self._shipment_fob(shipment)
            total_costs = sum(c.amount for c in shipment.costs if not c.is_deleted)
            total_landed += fob_total + total_costs
            total_fob += fob_total

            status_value = shipment.status.value if shipment.status else "draft"
            if status_value == "approved":
                approved_count += 1
            elif status_value != "cancelled":
                draft_count += 1

        self.card_total.set_value(str(len(shipments)))
        self.card_draft.set_value(str(draft_count))
        self.card_approved.set_value(str(approved_count))
        self.card_fob.set_value(f"{total_fob:,.2f}")
        self.card_landed.set_value(f"{total_landed:,.2f}")

    def _shipment_fob(self, shipment):
        fob_total = 0.0
        for product in shipment.products:
            if not product.is_deleted:
                fob_total += product.total_quantity * product.unit_price_rmb * shipment.exchange_rate
        return fob_total

    def populate_table(self, shipments):
        """Fill the table with the given (already filtered) list of shipments."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(shipments))

        for row, shipment in enumerate(shipments):
            fob_total = self._shipment_fob(shipment)
            total_costs = sum(c.amount for c in shipment.costs if not c.is_deleted)
            total_landed_shipment = fob_total + total_costs

            # ID
            id_item = QTableWidgetItem()
            id_item.setData(Qt.DisplayRole, shipment.id)
            id_item.setTextAlignment(Qt.AlignCenter)
            id_item.setData(Qt.UserRole, shipment.id)
            id_item.setData(Qt.UserRole + 1, shipment.stocked_in)
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
            if shipment.proforma_date:
                date_item.setData(Qt.UserRole, shipment.proforma_date.toordinal()
                                   if hasattr(shipment.proforma_date, "toordinal") else 0)
            self.table.setItem(row, 3, date_item)

            # Exchange Rate
            rate_item = QTableWidgetItem()
            rate_item.setData(Qt.DisplayRole, f"{shipment.exchange_rate:.4f}")
            rate_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, rate_item)

            # FOB (ETB)
            fob_item = QTableWidgetItem(f"{fob_total:,.2f}")
            fob_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fob_item.setData(Qt.UserRole, fob_total)
            self.table.setItem(row, 5, fob_item)

            # Total Landed (ETB)
            landed_item = QTableWidgetItem(f"{total_landed_shipment:,.2f}")
            landed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            landed_item.setData(Qt.UserRole, total_landed_shipment)
            self.table.setItem(row, 6, landed_item)

            # Status
            status_text = shipment.status.value.title() if shipment.status else "Draft"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)

            is_approved = bool(shipment.status and shipment.status.value == "approved")
            if is_approved:
                status_item.setBackground(QColor(214, 245, 220))
                status_item.setForeground(QColor(0, 128, 0))
            elif shipment.status and shipment.status.value == "cancelled":
                status_item.setBackground(QColor(253, 220, 220))
                status_item.setForeground(QColor(192, 0, 0))
            else:
                status_item.setBackground(QColor(255, 244, 205))
                status_item.setForeground(QColor(150, 110, 0))

            status_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.table.setItem(row, 7, status_item)

            status_value = shipment.status.value if shipment.status else "draft"
            self.table.setCellWidget(row, 8, self.build_action_widget(shipment.id, status_value, shipment.stocked_in))

        self.table.setSortingEnabled(True)

    def build_action_widget(self, shipment_id, status, stocked_in=False):
        """
        Return a widget with action buttons.
        status: "draft", "approved", or "cancelled"
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- Common View/Edit button ----
        if status == "draft":
            # Draft -> Edit (pencil)
            edit_btn = make_row_action_button("✏️", "Edit shipment", "#3498db", "#2980b9")
            edit_btn.clicked.connect(lambda: self.open_shipment_dialog(shipment_id, False))
            layout.addWidget(edit_btn)
        else:
            # Approved or Cancelled -> View (eye)
            view_btn = make_row_action_button("👁", "View shipment", "#3498db", "#2980b9")
            view_btn.clicked.connect(lambda: self.open_shipment_dialog(shipment_id, True))
            layout.addWidget(view_btn)
            if not stocked_in:
                stock_btn = make_row_action_button("📦", "Stock In", "#27ae60", "#219a52")
                stock_btn.clicked.connect(lambda: self.stock_in_shipment(shipment_id))
                layout.addWidget(stock_btn)

        # ---- Approve button (only for draft) ----
        if status == "draft":
            approve_btn = make_row_action_button("✅", "Approve shipment", "#27ae60", "#219a52")
            approve_btn.clicked.connect(lambda: self.approve_shipment(shipment_id))
            layout.addWidget(approve_btn)

        # ---- Cancel button (only for draft) ----
        if status == "draft":
            cancel_btn = make_row_action_button("❌", "Cancel shipment", "#e67e22", "#d35400")
            cancel_btn.clicked.connect(lambda: self.cancel_shipment(shipment_id))
            layout.addWidget(cancel_btn)

        # ---- Delete button (only for draft) ----
        if status == "draft":
            delete_btn = make_row_action_button("🗑️", "Delete shipment", "#e74c3c", "#c0392b")
            delete_btn.clicked.connect(lambda: self.delete_shipment(shipment_id))
            layout.addWidget(delete_btn)

        layout.addStretch()
        return container

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def apply_filters(self):
        """Filter the cached shipment list by search text + status, then repopulate."""
        search_text = self.search_input.text().strip().lower()
        status_choice = self.status_filter.currentText()

        filtered = []
        for shipment in self.all_shipments:
            if search_text:
                supplier_name = (shipment.supplier.supplier_name if shipment.supplier else "").lower()
                bank_name = (shipment.bank_account.account_name if shipment.bank_account else "").lower()
                if search_text not in supplier_name and search_text not in bank_name \
                        and search_text != str(shipment.id):
                    continue

            if status_choice != "All Statuses":
                status_value = shipment.status.value.title() if shipment.status else "Draft"
                if status_value != status_choice:
                    continue

            filtered.append(shipment)

        self.populate_table(filtered)

        if not self.all_shipments:
            self.empty_title.setText("No shipments yet")
            self.empty_subtitle.setText("Create your first import shipment to get started.")
            self.content_stack.setCurrentWidget(self.empty_state)
        elif not filtered:
            self.empty_title.setText("No matching shipments")
            self.empty_subtitle.setText("Try adjusting your search or status filter.")
            self.content_stack.setCurrentWidget(self.empty_state)
        else:
            self.content_stack.setCurrentWidget(self.table)

        self.stats_label.setText(
            f"Showing {len(filtered)} of {len(self.all_shipments)} shipments"
        )

    # ------------------------------------------------------------------
    # Selection Handling
    # ------------------------------------------------------------------
    def on_selection_changed(self):
        pass  # row-level Edit/Delete buttons now handle actions directly

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

    def open_shipment_dialog(self, shipment_id, is_approved):
        mode = "view" if is_approved else "edit"
        dialog = ImportShipmentDialog(
            parent=self,
            current_user=self.current_user,
            mode=mode,
            shipment_id=shipment_id
        )
        if dialog.exec():
            self.refresh()

    def on_table_double_clicked(self, index):
        """Open the shipment for editing/viewing when double-clicked."""
        row = index.row()
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
        is_approved = bool(status_item and "Approved" in status_item.text())
        self.open_shipment_dialog(shipment_id, is_approved)

    def delete_shipment(self, shipment_id):
        """Delete a shipment after explicit confirmation."""
        shipment = next((s for s in self.all_shipments if s.id == shipment_id), None)
        if shipment and shipment.status and shipment.status.value == "approved":
            QMessageBox.warning(self, "Cannot Delete", "Approved shipments cannot be deleted.")
            return

        supplier_name = shipment.supplier.supplier_name if (shipment and shipment.supplier) else "this shipment"

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the shipment from '{supplier_name}' "
            f"(ID: {shipment_id})?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.service.delete(shipment_id)
        except Exception as e:
            QMessageBox.critical(self, "Delete Failed", f"Could not delete shipment:\n{str(e)}")
            return

        self.status_label.setText(f"✅ Shipment #{shipment_id} deleted.")
        self.status_label.setStyleSheet("color: #2ecc71; font-size: 12px;")
        self.refresh()

    def approve_shipment(self, shipment_id):
        """Approve a draft shipment after confirmation."""
        reply = QMessageBox.question(
            self,
            "Approve Shipment",
            f"Are you sure you want to approve shipment #{shipment_id}?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.service.approve_shipment(shipment_id)
            self.status_label.setText(f"✅ Shipment #{shipment_id} approved.")
            self.status_label.setStyleSheet("color: #2ecc71; font-size: 12px;")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Approve Failed", str(e))

    def cancel_shipment(self, shipment_id):
        """Cancel a draft shipment after confirmation."""
        reply = QMessageBox.question(
            self,
            "Cancel Shipment",
            f"Are you sure you want to cancel shipment #{shipment_id}?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.service.cancel_shipment(shipment_id)
            self.status_label.setText(f"❌ Shipment #{shipment_id} cancelled.")
            self.status_label.setStyleSheet("color: #e67e22; font-size: 12px;")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Cancel Failed", str(e))

    def stock_in_shipment(self, shipment_id):
        shipment = self.service.get_by_id_with_relations(shipment_id)
        if not shipment:
            QMessageBox.warning(self, "Error", "Shipment not found.")
            return
        if shipment.stocked_in:
            QMessageBox.information(self, "Already Stocked", "This shipment has already been stocked in.")
            return

        from ui.pages.import_shipment.stock_in_dialog import StockInMappingDialog
        from services.new_product_service import NewProductService

        dialog = StockInMappingDialog(shipment, NewProductService(), self)
        if dialog.exec() == QDialog.Accepted:
            mapping = dialog.mapping_result
            try:
                purchase = self.service.stock_in(shipment_id, mapping)
                QMessageBox.information(self, "Success", f"Stock‑in complete. Purchase #{purchase.id} created.")
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Stock‑in failed: {str(e)}")