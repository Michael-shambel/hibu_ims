#!/usr/bin/env python3
from datetime import date
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QLineEdit, QApplication
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont, QColor
from services.new_sale_service import NewSaleService
from ui.pages.sales_card_dialog import SaleItemsDialog, CustomerSalesListDialog
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
        self.summary = {}
        self.customer_data = []
        self.filtered_data = []
        self.search_text = ""
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.is_loading = False
        self.thread = None
        self.worker = None
        self._closed = False
        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 15, 0, 15)
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

        # Table
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

        # Loading indicator
        self.loading_label = QLabel("Loading credit sales data, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)


    def create_summary_card(self, title, value, color_hex):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 1px solid #E0E0E0;
                min-width: 200px;
                max-width: 240px;
            }}
        """)
        card.setFixedHeight(120)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background-color: {color_hex};
                color: white;
                font-weight: bold;
                padding: 14px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 14px;
            }}
        """)
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Segoe UI", 12, QFont.Bold))

        value_label = QLabel(value)
        value_label.setObjectName("value_label")
        value_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #2c3e50;
                padding: 18px 10px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFont(QFont("Segoe UI", 16, QFont.Bold))

        layout.addWidget(header)
        layout.addWidget(value_label)
        return card

    def load_data(self):
        if self.is_loading:
            return
        self.is_loading = True
        self.loading_label.show()
        self.table.hide()
        self.thread = QThread()
        self.worker = Worker(self._fetch_data)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_data_loaded)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_data(self):
        summary = self.sale_service.get_credit_sales_summary()
        customers = self.sale_service.get_credit_sales_by_customer()
        return summary, customers

    def on_data_loaded(self, result):
        if self._closed:
            return
        self.is_loading = False
        summary, customers = result
        for cust in customers:
            if 'sale_ids' in cust and cust['sale_ids']:
                all_sales = self.sale_service.get_credit_sales_by_ids(cust['sale_ids'])
                # keep only sales that still have a remaining balance
                outstanding = [s for s in all_sales if s.get('remaining', 0) > 0]
                if outstanding:
                    cust['total_amount'] = sum(s['total_amount'] for s in outstanding)
                    cust['paid_amount'] = sum(s['paid_amount'] for s in outstanding)
                    cust['remaining'] = cust['total_amount'] - cust['paid_amount']
                else:
                    # This customer no longer has any outstanding – will be removed later
                    cust['remaining'] = 0
            else:
                cust['remaining'] = 0
        self.summary = summary
        self.customer_data = customers

        # 1. Remove fully paid customers
        self.customer_data = [c for c in self.customer_data if c['remaining'] > 0]

        # 2. Apply short‑term filter if requested (modify the master list)
        if self.filter_short_term_only:
            self.customer_data = [c for c in self.customer_data if c.get('has_short_term', False)]

        # 3. Sort by remaining amount (descending)
        self.customer_data.sort(key=lambda x: x['remaining'], reverse=True)

        # 4. Initialise filtered_data with the (possibly filtered) master list
        self.filtered_data = self.customer_data.copy()

        # 5. Update total unpaid label (using the original summary, which is fine)
        self.total_unpaid_label.setText(f"Total Unpaid: ${self.summary['total_unpaid']:,.2f}")

        # 6. Populate table (no search text change that would trigger filter_table)
        self.populate_table()
        self.loading_label.hide()
        self.table.show()

    def on_error(self, error):
        if self._closed:
            return
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load credit sales data:\n{error}")
        self.loading_label.hide()
        self.table.show()

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

        # total = len(self.customer_data)
        # visible = len(data)
        # filter_text = f" (Filter: '{self.search_edit.text()}')" if self.search_edit.text() else ""
        # self.status_label.setText(f"Showing {visible} of {total} customers{filter_text}")

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${value:,.2f}")
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        return item

    def filter_table(self, text):
        self.search_text = text.lower()
        if not self.search_text:
            self.filtered_data = self.customer_data.copy()
        else:
            filtered = []
            for cust in self.customer_data:
                if self.search_text in cust['customer_name'].lower():
                    filtered.append(cust)
                    continue
                if self.search_text in cust['status'].lower():
                    filtered.append(cust)
                    continue
                amount_str = f"${cust['total_amount']:,.2f}".lower()
                if self.search_text in amount_str:
                    filtered.append(cust)
                    continue
                amount_str = f"${cust['paid_amount']:,.2f}".lower()
                if self.search_text in amount_str:
                    filtered.append(cust)
                    continue
                amount_str = f"${cust['remaining']:,.2f}".lower()
                if self.search_text in amount_str:
                    filtered.append(cust)
                    continue
            filtered.sort(key=lambda x: x['remaining'], reverse=True)
            self.filtered_data = filtered
        self.populate_table()

    def view_customer_sales(self, cust):
        dialog = CustomerSalesListDialog(
            self,
            cust['customer_name'],
            cust['sale_ids'],
            self.current_user
        )
        dialog.setModal(False)
        dialog.show()
        # self.load_data()

    def pay_customer(self, cust):
        dialog = CreditPaymentDialog(
            self,
            customer_id=cust['customer_id'],
            customer_name=cust['customer_name'],
            total_due=cust['remaining'],
            current_user=self.current_user
        )
        if dialog.exec() == QDialog.Accepted:
            self.load_data()

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
        # self.load_data()
    
    def closeEvent(self, event):
        """Stop background thread before closing to avoid accessing deleted widgets."""
        self._closed = True
        try:
            if hasattr(self, 'thread') and self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(2000)
        except RuntimeError:
            # Underlying C++ object already deleted – nothing to do
            pass
        event.accept()