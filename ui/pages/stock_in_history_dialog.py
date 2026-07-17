#!/usr/bin/env python3

from datetime import datetime
from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QApplication, QMessageBox,
    QWidget, QLineEdit
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont, QCursor
from sqlalchemy.orm import joinedload
from services.base_service import get_session
from models.batch_transaction import BatchTransaction, TransactionType
from models.product_batch import ProductBatch
from models.new_product import ProfessionalProduct
from models.purchase import Purchase
from models.supplier import Supplier
from ui.components.ethiopian_date import EthiopianDateConverter
from ui.utils.worker import Worker
import logging

logger = logging.getLogger(__name__)


class StockInHistoryDialog(QDialog):
    """Dialog showing daily summary of received stock (from purchases only)."""

    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Stock In History (Purchases Only)")
        self.setMinimumSize(800, 500)
        self.resize(1000, 600)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.summary_data = []          # list of dicts with date, total_qty, count, etc.
        self.filtered_data = []
        self.suppliers = {}             # id -> name
        self.current_page = 1
        self.page_size = 20
        self.total_pages = 1

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Top filter row
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        filter_label = QLabel("Filter by Supplier:")
        filter_label.setFont(QFont("Segoe UI", 12))
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(250)
        self.supplier_combo.setStyleSheet("font-size: 13px; padding: 5px;")
        self.supplier_combo.currentIndexChanged.connect(self.apply_filter)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.supplier_combo)
        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)

        # Table
        self.table = QTableWidget()
        headers = ["Ethiopian Date", "Total Qty Received", "Items", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(3, 150)

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 12))
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setStyleSheet("""
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
                padding: 8px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(self.table, 1)

        # Loading label
        self.loading_label = QLabel("Loading stock in history...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)

        # Pagination
        pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(pagination_widget)
        pagination_layout.setContentsMargins(0, 10, 0, 0)
        pagination_layout.setSpacing(15)
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.setFixedSize(100, 40)
        self.prev_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.prev_btn.clicked.connect(self.previous_page)
        self.next_btn = QPushButton("Next")
        self.next_btn.setFixedSize(100, 40)
        self.next_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.next_btn.clicked.connect(self.next_page)
        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        main_layout.addWidget(pagination_widget)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def load_data(self):
        self.loading_label.show()
        self.table.hide()
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.supplier_combo.setEnabled(False)

        self.thread = QThread()
        self.worker = Worker(self._fetch_summary)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_summary(self):
        """Fetch all RECEIVED transactions with purchase links, group by Ethiopian date."""
        with get_session() as session:
            # Query only RECEIVED transactions linked to a purchase
            transactions = session.query(BatchTransaction).options(
                joinedload(BatchTransaction.batch).joinedload(ProductBatch.product),
                joinedload(BatchTransaction.batch).joinedload(ProductBatch.purchase).joinedload(Purchase.supplier)
            ).filter(
                BatchTransaction.transaction_type == TransactionType.RECEIVED,
                BatchTransaction.is_deleted == False,
                BatchTransaction.batch.has(ProductBatch.purchase_id.isnot(None))  # Exclude manual stock-in
            ).order_by(BatchTransaction.created_at.desc()).all()

            # Collect unique suppliers for combo box
            supplier_set = {}
            date_groups = {}  # Ethiopian date tuple (year, month, day) -> list of transactions

            for tx in transactions:
                batch = tx.batch
                if not batch or not batch.purchase:
                    continue
                purchase = batch.purchase
                supplier = purchase.supplier
                if supplier:
                    supplier_set[supplier.id] = supplier.supplier_name

                # Convert Gregorian date to Ethiopian
                greg_date = tx.created_at.date()
                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_date)
                key = (eth_year, eth_month, eth_day)

                if key not in date_groups:
                    date_groups[key] = []
                date_groups[key].append(tx)

            # Build summary data
            summary = []
            for (year, month, day), txs in date_groups.items():
                total_qty = sum(tx.quantity for tx in txs)
                # Count distinct products for "Items" count
                distinct_products = set()
                supplier_ids = set()
                for tx in txs:
                    batch = tx.batch
                    if batch and batch.product_id:
                        distinct_products.add(batch.product_id)
                    if batch and batch.purchase and batch.purchase.supplier_id:
                        supplier_ids.add(batch.purchase.supplier_id)
                summary.append({
                    'eth_date': (year, month, day),
                    'total_qty': total_qty,
                    'item_count': len(distinct_products),
                    'transactions': txs,
                    'supplier_ids': supplier_ids
                })

            # Sort by date descending (newest first)
            summary.sort(key=lambda x: (x['eth_date'][0], x['eth_date'][1], x['eth_date'][2]), reverse=True)

            return summary, supplier_set

    def _on_data_loaded(self, result):
        self.summary_data, supplier_dict = result
        self.suppliers = supplier_dict

        # Populate supplier combo
        self.supplier_combo.blockSignals(True)
        self.supplier_combo.clear()
        self.supplier_combo.addItem("All Suppliers", None)
        for sid, name in sorted(supplier_dict.items(), key=lambda x: x[1]):
            self.supplier_combo.addItem(name, sid)
        self.supplier_combo.blockSignals(False)
        self.supplier_combo.setEnabled(True)

        self.apply_filter()
        self.loading_label.hide()
        self.table.show()
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _on_error(self, error):
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load stock in history:\n{error}")
        self.loading_label.hide()
        self.table.show()

    def apply_filter(self):
        """Filter summary data by selected supplier."""
        selected_supplier_id = self.supplier_combo.currentData()
        if selected_supplier_id is None:
            self.filtered_data = self.summary_data
        else:
            self.filtered_data = [
                item for item in self.summary_data
                if selected_supplier_id in item['supplier_ids']
            ]
        self.current_page = 1
        self.update_table()

    def update_table(self):
        total = len(self.filtered_data)
        self.total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        page_items = self.filtered_data[start:end]

        self.table.setRowCount(len(page_items))
        for row, item in enumerate(page_items):
            year, month, day = item['eth_date']
            date_str = f"{day:02d}/{month:02d}/{year:04d}"

            # Date
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            # Total Qty
            qty_item = QTableWidgetItem(str(item['total_qty']))
            qty_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, qty_item)

            # Items count
            count_item = QTableWidgetItem(str(item['item_count']))
            count_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, count_item)

            # Action button
            view_btn = QPushButton("View Details")
            view_btn.setFixedSize(130, 40)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            view_btn.clicked.connect(
                lambda checked, d=item['eth_date'], txs=item['transactions']: self.show_date_details(d, txs)
            )
            self.table.setCellWidget(row, 3, view_btn)

        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_table()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_table()

    def show_date_details(self, eth_date, transactions):
        """Open detail dialog for a specific Ethiopian date."""
        dialog = DateStockInDetailDialog(self, eth_date, transactions, self.suppliers, self.current_user)
        dialog.setModal(False)
        dialog.show()


class DateStockInDetailDialog(QDialog):
    """Show all received items for a specific Ethiopian date."""

    def __init__(self, parent, eth_date, transactions, suppliers_map, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        year, month, day = eth_date
        self.setWindowTitle(f"Stock Received on {day:02d}/{month:02d}/{year:04d}")
        self.setMinimumSize(900, 500)
        self.resize(1100, 600)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.eth_date = eth_date
        self.transactions = transactions
        self.suppliers_map = suppliers_map
        self.current_user = current_user
        self.filtered_transactions = []
        self.current_page = 1
        self.page_size = 20
        self.total_pages = 1

        # Preprocess transaction data for display
        self.detail_rows = []
        for tx in transactions:
            batch = tx.batch
            if not batch:
                continue
            product = batch.product
            purchase = batch.purchase
            supplier = purchase.supplier if purchase else None
            self.detail_rows.append({
                'product_name': product.name if product else "N/A",
                'quantity': tx.quantity,
                'cost_price': batch.cost_price,
                'supplier_name': supplier.supplier_name if supplier else "N/A",
                'supplier_id': supplier.id if supplier else None,
                'purchase_id': purchase.id if purchase else None,
                'time': tx.created_at.strftime("%H:%M") if tx.created_at else "",
                'transaction': tx
            })

        # Sort by time (or product name)
        self.detail_rows.sort(key=lambda x: x['product_name'])

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.apply_filter()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Filter row: supplier combo + search box
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        supplier_label = QLabel("Filter by Supplier:")
        supplier_label.setFont(QFont("Segoe UI", 12))
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.setStyleSheet("font-size: 13px; padding: 5px;")
        self.supplier_combo.currentIndexChanged.connect(self.apply_filter)

        search_label = QLabel("Search Product:")
        search_label.setFont(QFont("Segoe UI", 12))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by product name...")
        self.search_edit.setMinimumWidth(250)
        self.search_edit.setStyleSheet("font-size: 13px; padding: 5px;")
        self.search_edit.textChanged.connect(self.apply_filter)

        filter_layout.addWidget(supplier_label)
        filter_layout.addWidget(self.supplier_combo)
        filter_layout.addSpacing(30)
        filter_layout.addWidget(search_label)
        filter_layout.addWidget(self.search_edit)
        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)

        # Populate supplier combo (only suppliers that appear in these transactions)
        self.supplier_combo.blockSignals(True)
        self.supplier_combo.clear()
        self.supplier_combo.addItem("All Suppliers", None)
        unique_suppliers = {}
        for row in self.detail_rows:
            if row['supplier_id']:
                unique_suppliers[row['supplier_id']] = row['supplier_name']
        for sid, name in sorted(unique_suppliers.items(), key=lambda x: x[1]):
            self.supplier_combo.addItem(name, sid)
        self.supplier_combo.blockSignals(False)

        # Table
        self.table = QTableWidget()
        headers = ["Product Name", "Qty", "Cost Price", "Supplier", "Purchase #", "Time"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 12))
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setStyleSheet("""
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
                padding: 8px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(self.table, 1)

        # Summary totals
        self.total_label = QLabel()
        self.total_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.total_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 6px;")
        main_layout.addWidget(self.total_label)

        # Pagination
        pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(pagination_widget)
        pagination_layout.setContentsMargins(0, 10, 0, 0)
        pagination_layout.setSpacing(15)
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.setFixedSize(100, 40)
        self.prev_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.prev_btn.clicked.connect(self.previous_page)
        self.next_btn = QPushButton("Next")
        self.next_btn.setFixedSize(100, 40)
        self.next_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.next_btn.clicked.connect(self.next_page)
        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        main_layout.addWidget(pagination_widget)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
        """)
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def apply_filter(self):
        selected_supplier_id = self.supplier_combo.currentData()
        search_text = self.search_edit.text().strip().lower()

        filtered = []
        for row in self.detail_rows:
            # Supplier filter
            if selected_supplier_id is not None and row['supplier_id'] != selected_supplier_id:
                continue
            # Search filter
            if search_text and search_text not in row['product_name'].lower():
                continue
            filtered.append(row)

        self.filtered_transactions = filtered
        self.current_page = 1
        self.update_table()

    def update_table(self):
        total = len(self.filtered_transactions)
        self.total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        page_rows = self.filtered_transactions[start:end]

        self.table.setRowCount(len(page_rows))
        total_qty = 0
        total_cost = 0.0

        for row_idx, row_data in enumerate(page_rows):
            # Product Name
            name_item = QTableWidgetItem(row_data['product_name'])
            name_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row_idx, 0, name_item)

            # Quantity
            qty_item = QTableWidgetItem(str(row_data['quantity']))
            qty_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 1, qty_item)

            # Cost Price
            cost_item = QTableWidgetItem(f"${row_data['cost_price']:,.2f}")
            cost_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 2, cost_item)

            # Supplier
            supplier_item = QTableWidgetItem(row_data['supplier_name'])
            supplier_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row_idx, 3, supplier_item)

            # Purchase #
            purchase_str = f"#{row_data['purchase_id']}" if row_data['purchase_id'] else "N/A"
            purchase_item = QTableWidgetItem(purchase_str)
            purchase_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row_idx, 4, purchase_item)

            # Time
            time_item = QTableWidgetItem(row_data['time'])
            time_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row_idx, 5, time_item)

            total_qty += row_data['quantity']
            total_cost += row_data['quantity'] * row_data['cost_price']

        # Update summary label (total of *filtered* rows, not just page)
        filtered_total_qty = sum(r['quantity'] for r in self.filtered_transactions)
        filtered_total_cost = sum(r['quantity'] * r['cost_price'] for r in self.filtered_transactions)
        self.total_label.setText(
            f"Total Quantity (filtered): {filtered_total_qty} units   |   Total Cost: ${filtered_total_cost:,.2f}"
        )

        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_table()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_table()