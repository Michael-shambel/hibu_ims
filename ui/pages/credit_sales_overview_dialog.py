#!/usr/bin/env python3
from datetime import date
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QFrame, QLineEdit, QApplication, QComboBox
)
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QFont, QColor
from services.new_sale_service import NewSaleService
from ui.pages.sales_card_dialog import CustomerSalesListDialog
from ui.pages.credit_payment_dialog import CreditPaymentDialog
from ui.utils.worker import Worker


class CreditSalesOverviewDialog(QDialog):
    def __init__(self, parent, current_user, filter_short_term_only=False):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Credit Sales Overview")
        self.setMinimumSize(1200, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.sale_service = NewSaleService()
        self.filter_short_term_only = filter_short_term_only

        # Pagination state
        self.current_page = 1
        self.page_size = 50
        self.total_pages = 1
        self.total_customers = 0

        self.summary = {}
        self.customer_data = []      # data for current page
        self.filtered_data = []      # filtered subset of current page
        self.search_text = ""

        self.is_loading = False
        self.thread = None
        self.worker = None
        self._closed = False

        self.search_version = 0
        self._load_version = 0
        self.fuzzy_mode = False
        self._fuzzy_attempted = False

        # Debounce timer for search to avoid starting too many threads
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._do_search)

        self.init_ui()
        # Maximise to screen
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ---------- Search bar ----------
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 15, 0, 15)
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFixedSize(120, 35)
        refresh_btn.clicked.connect(self.refresh_data)
        search_layout.addWidget(refresh_btn)
        search_label = QLabel("Search:")
        search_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by customer, status, or amount...")
        self.search_edit.setMinimumHeight(35)
        self.search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.search_edit.textChanged.connect(self.filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()

        self.total_unpaid_label = QLabel("Total Unpaid: $0.00")
        self.total_unpaid_label.setStyleSheet("""
            font-weight: bold;
            font-size: 14px;
            color: #e74c3c;
            padding: 8px 15px;
            background-color: #fdf0f0;
            border-radius: 6px;
            border: 1px solid #f5c6cb;
        """)
        search_layout.addWidget(self.total_unpaid_label)
        main_layout.addLayout(search_layout)

        # ---------- Table ----------
        self.table = QTableWidget()
        headers = ["Customer", "Total", "Paid", "Remaining", "Status", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 140)

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
                border-radius: 4px;
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

        self.fuzzy_status_label = QLabel("")
        self.fuzzy_status_label.setAlignment(Qt.AlignCenter)
        self.fuzzy_status_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.fuzzy_status_label.setStyleSheet("color: #f39c12;")
        self.fuzzy_status_label.hide()
        main_layout.addWidget(self.fuzzy_status_label)

        # ---------- Pagination bar ----------
        pagination_layout = QHBoxLayout()
        pagination_layout.setContentsMargins(0, 10, 0, 10)

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)

        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setStyleSheet("font-weight: bold; font-size: 13px;")

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["20", "50", "100", "200"])
        self.page_size_combo.setCurrentText("50")
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)

        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        pagination_layout.addWidget(QLabel("Rows per page:"))
        pagination_layout.addWidget(self.page_size_combo)

        main_layout.addLayout(pagination_layout)

        # ---------- Loading indicator ----------
        self.loading_label = QLabel("Loading credit sales data, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)

    def refresh_data(self):
        self.fuzzy_mode = False
        self._fuzzy_attempted = False
        self.load_data()

    def load_data(self):
        if self.is_loading:
            return

        # Stop any existing thread
        if self.thread is not None:
            try:
                if self.thread.isRunning():
                    self.thread.quit()
                    self.thread.wait(1000)
            except RuntimeError:
                pass
            self.thread = None
            self.worker = None

        self.is_loading = True

        # # Stop any existing thread before starting a new one
        # try:
        #     if self.thread is not None and self.thread.isRunning():
        #         self.thread.quit()
        #         self.thread.wait(1000)  # Wait up to 1 second for thread to finish
        # except RuntimeError:
        #     self.thread = None
        self.loading_label.show()
        self.table.hide()

        self.thread = QThread()
        self.worker = Worker(self._fetch_data)   # <-- will now use current search_text
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_data_loaded)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_data(self):
        summary = self.sale_service.get_credit_sales_summary()
        customers, total = self.sale_service.get_credit_customers_paginated(
            page=self.current_page,
            page_size=self.page_size,
            short_term_only=self.filter_short_term_only,
            search=self.search_text,
            fuzzy=self.fuzzy_mode
        )
        return summary, customers, total

    def on_data_loaded(self, result):
        if self._closed:
            return

        # Ignore stale results
        if self._load_version != self.search_version:
            self.is_loading = False
            self.loading_label.hide()
            self.table.show()
            return

        summary, customers, total = result

        # --- Auto-fallback fuzzy logic ---
        if total == 0 and self.search_text and not self._fuzzy_attempted:
            self.fuzzy_mode = True
            self._fuzzy_attempted = True
            self.is_loading = False
            QTimer.singleShot(0, self.load_data)  # deferred
            return

        # Normal processing
        self.summary = summary
        self.total_customers = total
        self.total_pages = (total + self.page_size - 1) // self.page_size if total > 0 else 1

        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages} ({total} customers)")

        self.customer_data = customers
        self.filtered_data = customers.copy()

        self.total_unpaid_label.setText(f"Total Unpaid: ${self.summary['total_unpaid']:,.2f}")

        if self.fuzzy_mode and total > 0:
            self.fuzzy_status_label.setText(
                f"🔍 Showing fuzzy matches for '{self.search_text}'"
            )
            self.fuzzy_status_label.show()
        else:
            self.fuzzy_status_label.hide()

        self.populate_table()
        self.loading_label.hide()
        self.table.show()

    def on_error(self, error):
        if self._closed:
            return
        try:
            self.loading_label
        except RuntimeError:
            return
        self.is_loading = False
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load credit sales data:\n{error}")
        self.loading_label.hide()
        self.table.show()

    # ================== Pagination ==================
    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_data()

    def on_page_size_changed(self, new_size):
        self.page_size = int(new_size)
        self.current_page = 1
        self.load_data()

    # ================== Table population ==================
    def populate_table(self, data=None):
        if data is None:
            data = self.filtered_data

        today = date.today()
        self.table.setRowCount(len(data))
        for row, cust in enumerate(data):
            # Customer name
            name_item = QTableWidgetItem(cust['customer_name'])
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, name_item)

            # Total
            total_item = self._amount_item(cust['total_amount'])
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 1, total_item)

            # Paid
            paid_item = self._amount_item(cust['paid_amount'])
            paid_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 2, paid_item)

            # Remaining
            remain_item = self._amount_item(cust['remaining'])
            remain_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 3, remain_item)

            # Status
            status_item = QTableWidgetItem(cust['status'])
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)

            # Determine row colour and tooltip
            due_date = cust.get('earliest_due_date')
            remaining = cust['remaining']
            has_short = cust.get('has_short_term', False)
            row_color = None
            tooltip = ""

            if remaining == 0:
                row_color = QColor(220, 220, 220)   # Light grey
                tooltip = "Fully paid"
            else:
                if due_date and remaining > 0:
                    days = (today - due_date).days
                    if days > 0:                      # Overdue
                        if has_short:
                            row_color = QColor(255, 140, 105)   # #FF8C69
                            tooltip = f"Overdue short‑term by {days} day(s)"
                        else:
                            row_color = QColor(255, 179, 179)   # #FFB3B3
                            tooltip = f"Overdue long‑term by {days} day(s)"
                    elif days == 0:                   # Due today
                        if has_short:
                            row_color = QColor(255, 217, 102)   # #FFD966
                            tooltip = "Due today (short‑term)"
                        else:
                            row_color = QColor(255, 255, 179)   # #FFFFB3
                            tooltip = "Due today (long‑term)"
                    else:                             # Future due (days < 0)
                        if has_short:
                            row_color = QColor(255, 229, 204)   # #FFE5CC
                            tooltip = f"Short‑term credit, due in {abs(days)} day(s)"
                elif has_short and remaining > 0:
                    # Short‑term but no due date (fallback)
                    row_color = QColor(255, 229, 204)
                    tooltip = "Short‑term credit"

            if tooltip:
                status_item.setToolTip(tooltip)

            self.table.setItem(row, 4, status_item)

            # Actions widget
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 2, 5, 2)
            actions_layout.setSpacing(5)

            view_btn = QPushButton("👁️")
            view_btn.setFixedSize(40, 40)
            view_btn.setToolTip("View all credit sales for this customer")
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            view_btn.clicked.connect(lambda checked, c=cust: self.view_customer_sales(c))

            history_btn = QPushButton("🕒")
            history_btn.setFixedSize(40, 40)
            history_btn.setToolTip("View payment history")
            history_btn.setStyleSheet("""
                QPushButton {
                    background-color: #9b59b6;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #8e44ad; }
            """)
            history_btn.clicked.connect(lambda checked, c=cust: self.show_payment_history(c))

            pay_btn = QPushButton("💰")
            pay_btn.setFixedSize(40, 40)
            pay_btn.setToolTip("Record payment against this customer's total")
            pay_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #219a52; }
            """)
            pay_btn.clicked.connect(lambda checked, c=cust: self.pay_customer(c))

            actions_layout.addWidget(view_btn)
            actions_layout.addWidget(history_btn)
            actions_layout.addWidget(pay_btn)
            self.table.setCellWidget(row, 5, actions_widget)

            # Apply row colour to all cells in the row
            if row_color:
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(row_color)
                # Also colour the actions widget background
                actions_widget.setStyleSheet(f"background-color: {row_color.name()};")

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${value:,.2f}")
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        return item

    def filter_table(self, text):
        self.search_text = text.strip()
        self.current_page = 1
        self.fuzzy_mode = False
        self._fuzzy_attempted = False
        self.search_version += 1
        self.search_timer.start(300)

    def _do_search(self):
        """Actually perform the search (called after debounce delay)."""
        # Stop any running thread first
        try:
            if self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(1000)
        except RuntimeError:
            self.thread = None
        # Reset loading state so load_data can proceed
        self.is_loading = False
        self._load_version = self.search_version
        self.load_data()

    def view_customer_sales(self, cust):
        dialog = CustomerSalesListDialog(
            self,
            cust['customer_name'],
            sale_ids=None,          # not needed anymore
            current_user=self.current_user,
            customer_id=cust['customer_id']   # pass customer_id
        )
        dialog.setModal(False)
        dialog.show()

    def pay_customer(self, cust):
        dialog = CreditPaymentDialog(
            self,
            customer_id=cust['customer_id'],
            customer_name=cust['customer_name'],
            total_due=cust['remaining'],
            current_user=self.current_user
        )
        if dialog.exec() == QDialog.Accepted:
            self.load_data()   # refresh current page

    def show_payment_history(self, cust):
        from ui.pages.sales_card_dialog import CreditPaymentHistoryDialog
        dialog = CreditPaymentHistoryDialog(
            self,
            cust['customer_name'],
            cust['customer_id'],
            self.current_user
        )
        dialog.setModal(False)
        dialog.finished.connect(self.load_data)
        dialog.show()

    def closeEvent(self, event):
        self._closed = True

        if self.worker is not None:
            try:
                self.worker.finished.disconnect(self.on_data_loaded)
                self.worker.error.disconnect(self.on_error)
            except (RuntimeError, TypeError):
                pass

        try:
            if hasattr(self, 'thread') and self.thread is not None and self.thread.isRunning():
                self.thread.quit()
        except RuntimeError:
            pass
        event.accept()