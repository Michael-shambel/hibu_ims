#!/usr/bin/env python3

from datetime import datetime
from typing import List, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QApplication,
    QTableWidgetItem, QHeaderView, QLineEdit, QWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont, QColor, QCursor
from services.new_product_service import NewProductService
from services.new_sale_service import NewSaleService
from services.new_batch_transaction_service import NewBachTransactionService
from services.new_sale_item_service import NewSaleItemService
from models.batch_transaction import BatchTransaction, TransactionType
from models.product_batch import ProductBatch
from models.purchase import Purchase
from models.new_sales import ProfessionalSale
from models.new_sale_item import ProfessionalSaleItem
from models.new_product import ProfessionalProduct
from sqlalchemy.orm import joinedload
from ui.components.ethiopian_date import EthiopianDateConverter
from services.base_service import get_session
from ui.utils.worker import Worker
from ui.pages.purchase_payment_details_dialog import PurchasePaymentDetailsDialog
from ui.pages.stock_in_history_dialog import StockInHistoryDialog
import logging

logger = logging.getLogger(__name__)


class StockValueDialog(QDialog):
    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Stock value overview")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 800)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.product_service = NewProductService()
        self.sale_item_service = NewSaleItemService()

        self.products = []
        self.filtered_products = []
        self.current_page = 1
        self.page_size = 20
        self.total_pages = 1
        self.low_stock_count = 0
        self.filter_low_stock_active = False

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

        # Search bar - enlarged
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 10, 0, 10)
        search_label = QLabel("Search:")
        search_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by product name...")
        self.search_edit.setMinimumHeight(35)
        self.search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.search_edit.textChanged.connect(self.filter_products)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()

        self.low_stock_label = QPushButton("Low Stock: 0")
        self.low_stock_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.low_stock_label.setCursor(QCursor(Qt.PointingHandCursor))
        self.low_stock_label.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 14px;
                color: #e74c3c;
                padding: 8px 15px;
                background-color: #fdf0f0;
                border-radius: 6px;
                border: 1px solid #f5c6cb;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #fadbd8;
                border-color: #e74c3c;
            }
        """)
        self.low_stock_label.clicked.connect(self.toggle_low_stock_filter)
        search_layout.addWidget(self.low_stock_label)

        self.clear_filter_btn = QPushButton("Clear Filter")
        self.clear_filter_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.clear_filter_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.clear_filter_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 14px;
                color: #2c3e50;
                padding: 8px 15px;
                background-color: #f8f9fa;
                border-radius: 6px;
                border: 1px solid #ced4da;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        self.clear_filter_btn.clicked.connect(self.clear_low_stock_filter)
        self.clear_filter_btn.hide()
        search_layout.addWidget(self.clear_filter_btn)
        main_layout.addLayout(search_layout)

        # Table - elderly‑friendly styling
        self.table = QTableWidget()
        headers = ["No.", "Product Name", "Available Stock", "Selling Price", "Unit", "Dozen", "Total Stock", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        # header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 350)
        self.table.setColumnWidth(7, 120)  # wider for larger button

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.table.verticalHeader().setDefaultSectionSize(55)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 15px;
                font-weight: bold;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 12px;
                font-weight: bold;
                font-size: 15px;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        main_layout.addWidget(self.table, 1)

        # Loading indicator
        self.loading_label = QLabel("Loading stock data, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)

        # Pagination - larger buttons
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

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_history = QPushButton("Stock In History")
        self.btn_history.setFixedSize(180, 45)
        self.btn_history.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_history.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        self.btn_history.clicked.connect(self.show_stock_in_history)

        # Close button - larger
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
        btn_layout.addWidget(self.btn_history)
        btn_layout.addWidget(btn_close)
        main_layout.addLayout(btn_layout)
        # main_layout.addWidget(btn_close, alignment=Qt.AlignRight)
    
    def show_stock_in_history(self):
        dialog = StockInHistoryDialog(self, self.current_user)
        dialog.setModal(False)
        dialog.show()
    
    def toggle_low_stock_filter(self):
        if self.filter_low_stock_active:
            self.clear_low_stock_filter()
        else:
            self.filter_low_stock_active = True
            self.low_stock_label.setText(f"Low Stock: {self.low_stock_count} (Filtered)")
            self.low_stock_label.setStyleSheet("""
                QPushButton {
                    font-weight: bold;
                    font-size: 14px;
                    color: #c0392b;
                    padding: 8px 15px;
                    background-color: #fadbd8;
                    border-radius: 6px;
                    border: 2px solid #e74c3c;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #f1948a;
                }
            """)
            self.clear_filter_btn.show()
            self.apply_low_stock_filter()

    def clear_low_stock_filter(self):
        self.filter_low_stock_active = False
        self.low_stock_label.setText(f"Low Stock: {self.low_stock_count}")
        self.low_stock_label.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 14px;
                color: #e74c3c;
                padding: 8px 15px;
                background-color: #fdf0f0;
                border-radius: 6px;
                border: 1px solid #f5c6cb;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #fadbd8;
                border-color: #e74c3c;
            }
        """)
        self.clear_filter_btn.hide()
        self.filter_products(self.search_edit.text())  # Re-apply search filter

    def apply_low_stock_filter(self):
        # Apply both search text and low stock filter
        search_text = self.search_edit.text().strip()
        if search_text:
            search = search_text.lower()
            filtered = [p for p in self.products if search in p.name.lower()]
        else:
            filtered = self.products.copy()
        # Further filter for low stock
        self.filtered_products = [p for p in filtered if getattr(p, '_stock_available', 0) <= 2]
        self.current_page = 1
        self.update_table()

    def load_data(self):
        self.loading_label.show()
        self.table.hide()
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        self.thread = QThread()
        self.worker = Worker(self._fetch_data)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
    
    def _fetch_data(self):
        with get_session() as session:
            products = session.query(ProfessionalProduct).filter(
                ProfessionalProduct.is_deleted == False
            ).all()
            product_ids = [p.id for p in products]
            batches = session.query(ProductBatch).filter(
                ProductBatch.product_id.in_(product_ids),
                ProductBatch.is_deleted == False
            ).all()

            batches_by_product = {}
            for b in batches:
                batches_by_product.setdefault(b.product_id, []).append(b)

            total_valuation = 0.0
            total_capital = 0.0
            low_stock_count = 0

            for product in products:
                product_batches = batches_by_product.get(product.id, [])
                total_available = sum(b.available_quantity for b in product_batches)
                total_stock = sum(b.quantity for b in product_batches)

                product._stock_available = total_available
                product._stock_total = total_stock

                total_valuation += total_available * product.selling_price * product.dozen
                total_capital += sum(b.available_quantity * b.cost_price * b.product.dozen for b in product_batches)
                if total_available <= 2:
                    low_stock_count += 1
            
            products.sort(key=lambda p: getattr(p, '_stock_available', 0), reverse=True)
        return products, total_valuation, total_capital, low_stock_count
    
    def _on_data_loaded(self, result):
        products, total_valuation, total_capital, low_stock_count = result
        self.products = products
        self.low_stock_count = low_stock_count
        self.low_stock_label.setText(f"Low Stock: {low_stock_count}")
        self.filter_products(self.search_edit.text())
        self.loading_label.hide()
        self.table.show()
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)
    
    def _on_error(self, error):
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load stock data:\n{error}")
        self.loading_label.hide()
        self.table.show()

    def filter_products(self, text: str):
        if self.filter_low_stock_active:
            self.apply_low_stock_filter()
        else:
            if not text.strip():
                self.filtered_products = self.products
            else:
                search = text.lower()
                self.filtered_products = [p for p in self.products if search in p.name.lower()]
            self.current_page = 1
            self.update_table()

    def update_table(self):
        total = len(self.filtered_products)
        self.total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        page_products = self.filtered_products[start:end]

        self.table.setRowCount(len(page_products))
        for row, product in enumerate(page_products):
            total_available = getattr(product, '_stock_available', 0)
            total_stock = getattr(product, '_stock_total', 0)

            # No.
            no_item = QTableWidgetItem(str(start + row + 1))
            no_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, no_item)

            # Product Name
            name_item = QTableWidgetItem(product.name)
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 1, name_item)

            # Available Stock
            stock_item = QTableWidgetItem(str(total_available))
            stock_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            stock_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if total_available <= 2:
                stock_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 2, stock_item)

            # Selling Price
            price_item = QTableWidgetItem(f"${product.selling_price:,.2f}")
            price_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, price_item)

            # Unit
            unit_item = QTableWidgetItem(product.unit)
            unit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 4, unit_item)

            # Dozen
            dozen_item = QTableWidgetItem(str(product.dozen))
            dozen_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            dozen_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, dozen_item)

            # Total Stock
            total_stock_item = QTableWidgetItem(str(total_stock))
            total_stock_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_stock_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 6, total_stock_item)

            # Actions - larger button
            view_btn = QPushButton("View Details")
            view_btn.setFixedSize(110, 40)
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
            view_btn.clicked.connect(lambda checked, p=product: self.view_product_details(p))
            self.table.setCellWidget(row, 7, view_btn)

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

    def view_product_details(self, product):
        # Re-fetch the product to get the latest available_quantity from the database
        fresh_product = self.product_service.get_by_id(product.id)
        if not fresh_product:
            QMessageBox.warning(self, "Error", "Product no longer exists.")
            return
        dialog = ProductTransactionDialog(self, fresh_product, self.current_user)
        dialog.setModal(False)
        dialog.show()


class ProductTransactionDialog(QDialog):
    def __init__(self, parent, product, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Transaction History - {product.name}")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.product = product
        self.current_user = current_user
        self.transaction_service = NewBachTransactionService()
        self.sale_service = NewSaleService()
        self.sale_item_service = NewSaleItemService()

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_label = QLabel(f"<b>{self.product.name}</b> - {self.product.unit}")
        header_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(header_label)

        # Loading indicator
        self.loading_label = QLabel("Loading transaction history, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        layout.addWidget(self.loading_label)

        # Table - elderly-friendly styling
        self.table = QTableWidget()
        headers = ["Date", "Type", "Quantity", "Balance", "Details", "Action"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        # header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 350)
        self.table.setColumnWidth(5, 110)  # wider for larger button

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.table.verticalHeader().setDefaultSectionSize(55)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 15px;
                font-weight: bold;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 12px;
                font-weight: bold;
                font-size: 15px;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.table, 1)

        # Close button - larger
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
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def load_data(self):
        self.loading_label.show()
        self.table.hide()
        self.thread = QThread()
        self.worker = Worker(self._fetch_transactions)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
    
    def _fetch_transactions(self):
        with get_session() as session:
            batches = session.query(ProductBatch).filter(
                ProductBatch.product_id == self.product.id,
                ProductBatch.is_deleted == False
            ).all()
            batch_ids = [b.id for b in batches]

            if not batch_ids:
                return []

            transactions = session.query(BatchTransaction).options(
                joinedload(BatchTransaction.batch)
            ).filter(
                BatchTransaction.batch_id.in_(batch_ids),
                BatchTransaction.is_deleted == False
            ).order_by(BatchTransaction.created_at.asc()).all()

            sale_events = {}
            other_events = []

            for tx in transactions:
                if tx.transaction_type in [TransactionType.RECEIVED, TransactionType.STOCK_IN]:
                    purchase_id = None
                    payment_term_id = None
                    if tx.batch and tx.batch.purchase_id:
                        purchase_id = tx.batch.purchase_id
                        purchase = session.query(Purchase).get(purchase_id)
                        if purchase and purchase.payment_terms:
                            payment_term_id = purchase.payment_terms[0].id
                    other_events.append({
                        'date': tx.created_at.date(),
                        'type': 'received',
                        'quantity': tx.quantity,
                        'details': self._get_received_details(tx, session),
                        'purchase_id': purchase_id,
                        'payment_term_id': payment_term_id,
                    })
                elif tx.transaction_type == TransactionType.DAMAGE:
                    other_events.append({
                        'date': tx.created_at.date(),
                        'type': 'damage',
                        'quantity': -tx.quantity,
                        'details': tx.notes or 'Damage reported',
                    })
                elif tx.transaction_type == TransactionType.ADJUSTMENT:
                    qty = tx.quantity
                    other_events.append({
                        'date': tx.created_at.date(),
                        'type': 'adjustment',
                        'quantity': qty,
                        'details': tx.notes or f'Manual adjustment: {qty:+d} units',
                    })
                elif tx.transaction_type == TransactionType.SALE and tx.reference_number:
                    sale_id = int(tx.reference_number)
                    date_key = tx.created_at.date()
                    if date_key not in sale_events:
                        sale_events[date_key] = {
                            'total_quantity': 0,
                            'sale_ids': set(),
                            'sale_objects': {},
                        }
                    sale_events[date_key]['total_quantity'] += tx.quantity
                    sale_events[date_key]['sale_ids'].add(sale_id)

            all_sale_ids = set()
            for data in sale_events.values():
                all_sale_ids.update(data['sale_ids'])
            if all_sale_ids:
                sales = session.query(ProfessionalSale).filter(ProfessionalSale.id.in_(all_sale_ids)).all()
                sale_dict = {s.id: s for s in sales}
                for data in sale_events.values():
                    for sid in data['sale_ids']:
                        if sid in sale_dict:
                            data['sale_objects'][sid] = sale_dict[sid]

            all_events = other_events.copy()
            for date_key, data in sale_events.items():
                if data['total_quantity'] > 0:
                    num_sales = len(data['sale_ids'])
                    summary = f"{num_sales} sale(s), total quantity {data['total_quantity']}"
                    tooltip_parts = []
                    for sale_id, sale in data['sale_objects'].items():
                        cust = sale.customer.name if sale.customer else "N/A"
                        tooltip_parts.append(f"Sale #{sale_id}: {cust}")
                    tooltip = "\n".join(tooltip_parts) if tooltip_parts else summary

                    all_events.append({
                        'date': date_key,
                        'type': 'sale',
                        'quantity': -data['total_quantity'],
                        'details': summary,
                        'tooltip': tooltip,
                        'sale_data': data,
                    })

            all_events.sort(key=lambda e: e['date'])
            return all_events
    
    def _on_data_loaded(self, events):
        self.populate_table(events)
        self.loading_label.hide()
        self.table.show()
    
    def _on_error(self, error):
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load transaction data:\n{error}")
        self.loading_label.hide()
        self.table.show()
    
    def populate_table(self, events):
        reversed_events = list(reversed(events))
        
        balances = []
        running_balance = 0
        for event in events:  # original order (oldest first)
            running_balance += event['quantity']
            balances.append(running_balance)
        balances.reverse()
        
        self.table.setRowCount(len(reversed_events))
        for row, event in enumerate(reversed_events):
            eth_date = EthiopianDateConverter.to_ethiopian(event['date'])
            date_str = f"{eth_date[2]:02d}/{eth_date[1]:02d}/{eth_date[0]:04d}"
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            # Type
            type_display = event['type'].capitalize()
            type_item = QTableWidgetItem(type_display)
            type_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            if event['type'] == 'sale':
                type_item.setForeground(QColor("#e74c3c"))
            elif event['type'] == 'received':
                type_item.setForeground(QColor("#27ae60"))
            elif event['type'] == 'damage':
                type_item.setForeground(QColor("#f39c12"))
            elif event['type'] == 'adjustment':
                type_item.setForeground(QColor("#f39c12"))
            self.table.setItem(row, 1, type_item)

            # Quantity
            qty = event['quantity']
            qty_item = QTableWidgetItem(f"{qty:+d}")
            qty_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if qty < 0:
                qty_item.setForeground(QColor("#e74c3c"))
            else:
                qty_item.setForeground(QColor("#27ae60"))
            self.table.setItem(row, 2, qty_item)

            balance_item = QTableWidgetItem(str(balances[row]))
            balance_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, balance_item)

            # Details
            details_item = QTableWidgetItem(event['details'])
            details_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            details_item.setToolTip(event.get('tooltip', event['details']))
            self.table.setItem(row, 4, details_item)

            # Action button - larger
            if event['type'] == 'sale':
                view_btn = QPushButton("View Sales")
                view_btn.setFixedSize(110, 40)
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
                sale_data = event['sale_data']
                view_btn.clicked.connect(lambda checked, sd=sale_data: self.view_daily_sales(sd))
                self.table.setCellWidget(row, 5, view_btn)
            elif event['type'] == 'received':
                if event.get('purchase_id') and event.get('payment_term_id'):
                    view_btn = QPushButton("View Payment")
                    view_btn.setFixedSize(110, 40)
                    view_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #27ae60;
                            color: white;
                            border: none;
                            border-radius: 6px;
                            font-weight: bold;
                            font-size: 13px;
                        }
                        QPushButton:hover { background-color: #2ecc71; }
                    """)
                    purchase_id = event['purchase_id']
                    payment_term_id = event['payment_term_id']
                    view_btn.clicked.connect(lambda checked, pid=purchase_id, ptid=payment_term_id: self.view_purchase_payment(pid, ptid))
                    self.table.setCellWidget(row, 5, view_btn)
                else:
                    self.table.setItem(row, 5, QTableWidgetItem(""))
            else:
                self.table.setItem(row, 5, QTableWidgetItem(""))

    def _get_received_details(self, tx, session):
        batch = tx.batch
        if batch and batch.purchase_id:
            purchase = session.query(Purchase).get(batch.purchase_id)
            if purchase and purchase.supplier:
                return f"Supplier: {purchase.supplier.supplier_name}"
            return f"Purchase #{batch.purchase_id}"
        return "Stock in"

    def view_daily_sales(self, sale_data):
        sales_list = []
        for sale_id in sale_data['sale_ids']:
            sale = sale_data['sale_objects'].get(sale_id)
            if not sale:
                continue

            with get_session() as session:
                items = session.query(ProfessionalSaleItem).options(
                    joinedload(ProfessionalSaleItem.batch)
                ).filter(
                    ProfessionalSaleItem.sale_id == sale_id,
                    ProfessionalSaleItem.is_deleted == False,
                    ProfessionalSaleItem.batch.has(ProductBatch.product_id == self.product.id)
                ).all()

                total_qty = sum(i.quantity for i in items)
                if total_qty == 0:
                    total_qty = sale_data['total_quantity']

                if items:
                    avg_price = sum(i.total for i in items) / total_qty if total_qty else 0
                    total_amount = sum(i.total for i in items)
                else:
                    avg_price = self.product.selling_price
                    total_amount = total_qty * avg_price

            sales_list.append({
                'customer_name': sale.customer.name if sale.customer else "N/A",
                'delivery_name': sale.delivery_name,
                'delivery_phone': sale.delivery_phone,
                'delivery_place': sale.delivery_place,
                'delivery_plate': sale.delivery_Plate,
                'quantity': total_qty,
                'unit_price': avg_price,
                'total_amount': total_amount,
            })

        if not sales_list:
            QMessageBox.information(self, "No Data", "No sales found for this date.")
            return

        date_key = list(sale_data['sale_objects'].values())[0].created_at.date() if sale_data['sale_objects'] else datetime.now().date()
        dialog = DailySalesListDialog(self, self.product, date_key.strftime("%Y-%m-%d"), sales_list, self.current_user)
        dialog.exec()

    def view_purchase_payment(self, purchase_id: int, payment_term_id: int):
        dialog = PurchasePaymentDetailsDialog(self, purchase_id, payment_term_id, self.current_user)
        dialog.setModal(False)
        dialog.show()


class DailySalesListDialog(QDialog):
    """Display all sales for a product on a specific date."""

    def __init__(self, parent, product, date_str, sales_data, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Sales of {product.name} on {date_str}")
        self.setMinimumSize(800, 400)
        self.resize(1000, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.product = product
        self.date_str = date_str
        self.sales_data = sales_data
        self.current_user = current_user
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        greg_date = datetime.strptime(self.date_str, "%Y-%m-%d").date()
        eth_date = EthiopianDateConverter.to_ethiopian(greg_date)
        eth_date_str = f"{eth_date[2]:02d}/{eth_date[1]:02d}/{eth_date[0]:04d}"
        self.setWindowTitle(f"Sales of {self.product.name} on {eth_date_str}")

        # Summary - larger font
        total_qty = sum(s['quantity'] for s in self.sales_data)
        total_amount = sum(s['total_amount'] for s in self.sales_data)
        summary = QLabel(
            f"Total quantity sold: {total_qty}  |  Total amount: ${total_amount:,.2f} | {eth_date_str}"
        )
        summary.setFont(QFont("Segoe UI", 13, QFont.Bold))
        summary.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 6px;")
        layout.addWidget(summary)

        # Table - elderly-friendly styling
        self.table = QTableWidget()
        headers = ["Customer", "Delivery Info", "Quantity", "Unit Price", "Total"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        # header.setSectionResizeMode(0, QHeaderView.Stretch)
        # header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 250)
        self.table.setColumnWidth(1, 250)

        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.table.verticalHeader().setDefaultSectionSize(55)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 15px;
                font-weight: bold;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 12px;
                font-weight: bold;
                font-size: 15px;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.populate_table()
        layout.addWidget(self.table, 1)

        # Close button - larger
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
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def populate_table(self):
        self.table.setRowCount(len(self.sales_data))
        for row, sale in enumerate(self.sales_data):
            # Customer
            cust_item = QTableWidgetItem(sale['customer_name'])
            cust_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, cust_item)

            # Delivery info
            delivery_parts = []
            if sale['delivery_name']:
                delivery_parts.append(sale['delivery_name'])
            if sale['delivery_phone']:
                delivery_parts.append(sale['delivery_phone'])
            if sale['delivery_place']:
                delivery_parts.append(sale['delivery_place'])
            if sale['delivery_plate']:
                delivery_parts.append(sale['delivery_plate'])
            delivery_str = ", ".join(delivery_parts) if delivery_parts else "No delivery info"
            delivery_item = QTableWidgetItem(delivery_str)
            delivery_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            delivery_item.setToolTip("\n".join(delivery_parts) if delivery_parts else "No delivery info")
            self.table.setItem(row, 1, delivery_item)

            # Quantity
            qty_item = QTableWidgetItem(str(sale['quantity']))
            qty_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, qty_item)

            # Unit Price
            price_item = QTableWidgetItem(f"${sale['unit_price']:,.2f}")
            price_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, price_item)

            # Total
            total_item = QTableWidgetItem(f"${sale['total_amount']:,.2f}")
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, total_item)