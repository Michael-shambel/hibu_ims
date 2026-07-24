from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox, QDateEdit, QCheckBox
)
from PySide6.QtGui import QFont

class ImportShipmentPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.init_ui()

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
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "ID", "Supplier", "Bank", "Date", "Exchange Rate",
            "FOB (ETB)", "Total Landed (ETB)", "Status"
        ])

        # Set column widths
        table.setColumnWidth(0, 60)   # ID
        table.setColumnWidth(1, 200)  # Supplier
        table.setColumnWidth(2, 200)  # Bank
        table.setColumnWidth(3, 120)  # Date
        table.setColumnWidth(4, 100)  # Exchange Rate
        table.setColumnWidth(5, 150)  # FOB
        table.setColumnWidth(6, 150)  # Total Landed
        table.setColumnWidth(7, 120)  # Status

        # Style
        table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d8e0;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #d9e8f7;
            }
            QHeaderView::section {
                background-color: #e6ecf2;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #c0c8d0;
                font-weight: bold;
                font-size: 13px;
            }
        """)

        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSortingEnabled(True)

        table.doubleClicked.connect(self.on_table_double_clicked)

        return table

    def open_new_shipment_dialog(self):
        pass

    def refresh(self):
        pass

    def delete_shipment(self):
        pass

    def delete_selected_shipment(self):
        pass

    def on_table_double_clicked(self, index):
        pass

    def on_selection_changed(self):
        pass