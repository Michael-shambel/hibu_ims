#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QSizePolicy
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QColor, QFont

from services.combined_credit_service import CombinedCreditService
from ui.utils.worker import Worker


class CombinedCreditOverviewDialog(QDialog):
    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Combined Credit Overview")
        self.setMinimumSize(1200, 700)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.service = CombinedCreditService()
        self.summary = {}
        self.combined_data = []
        self.filtered_data = []
        self.search_text = ""
        self.is_loading = False
        self.thread = None
        self.worker = None

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

            # ---- Search bar ----
            search_layout = QHBoxLayout()
            search_layout.setContentsMargins(0, 5, 0, 5)

            refresh_btn = QPushButton("🔄 Refresh")
            refresh_btn.setFixedSize(130, 44)
            refresh_btn.setCursor(Qt.PointingHandCursor)
            refresh_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
            refresh_btn.setStyleSheet(self._button_style("#3498db", "#2980b9"))
            refresh_btn.clicked.connect(self.load_data)

            search_label = QLabel("🔍 Search:")
            search_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
            search_label.setStyleSheet("color: #2c3e50;")

            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("Filter by name, phone, direction, amount...")
            self.search_edit.setMinimumHeight(42)
            self.search_edit.setFont(QFont("Segoe UI", 14))
            self.search_edit.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #d1d5db;
                    border-radius: 6px;
                    padding: 8px 14px;
                    font-size: 14px;
                    background-color: white;
                }
                QLineEdit:focus {
                    border: 1px solid #3b82f6;
                }
            """)
            self.search_edit.textChanged.connect(self.filter_table)

            search_layout.addWidget(refresh_btn)
            search_layout.addWidget(search_label)
            search_layout.addWidget(self.search_edit, 1)
            main_layout.addLayout(search_layout)

            # ---- Table ----
            self.table = QTableWidget()
            headers = [
                "Name", "Phone", "Credit Sales", "Credit Purchases",
                "Cash Given", "Cash Received", "Direction", "Net Balance", "Actions"
            ]
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)

            # Set minimum widths for all columns
            self.table.setColumnWidth(0, 180)  # Name
            self.table.setColumnWidth(1, 120)  # Phone
            self.table.setColumnWidth(2, 130)  # Credit Sales
            self.table.setColumnWidth(3, 140)  # Credit Purchases
            self.table.setColumnWidth(4, 130)  # Cash Given
            self.table.setColumnWidth(5, 140)  # Cash Received
            self.table.setColumnWidth(6, 130)  # Direction
            self.table.setColumnWidth(7, 130)  # Net Balance
            self.table.setColumnWidth(8, 320)  # Actions – fixed width

            # Resize modes – stretch most columns, keep Actions fixed
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)          # Name
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Phone
            header.setSectionResizeMode(2, QHeaderView.Stretch)          # Credit Sales
            header.setSectionResizeMode(3, QHeaderView.Stretch)          # Credit Purchases
            header.setSectionResizeMode(4, QHeaderView.Stretch)          # Cash Given
            header.setSectionResizeMode(5, QHeaderView.Stretch)          # Cash Received
            header.setSectionResizeMode(6, QHeaderView.ResizeToContents) # Direction
            header.setSectionResizeMode(7, QHeaderView.ResizeToContents) # Net Balance
            header.setSectionResizeMode(8, QHeaderView.Fixed)            # Actions – fixed!

            self.table.setAlternatingRowColors(True)
            self.table.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.verticalHeader().setDefaultSectionSize(60)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)

            self.table.setStyleSheet("""
                QTableWidget {
                    font-size: 14px;
                    font-weight: bold;
                    background-color: white;
                    alternate-background-color: #f8f9fa;
                    gridline-color: #dee2e6;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: white;
                    padding: 12px;
                    font-weight: bold;
                    font-size: 14px;
                    border: none;
                }
                QTableWidget::item {
                    padding: 10px;
                }
            """)
            main_layout.addWidget(self.table, 1)

            self.loading_label = QLabel("Loading combined credit data, please wait...")
            self.loading_label.setAlignment(Qt.AlignCenter)
            self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.loading_label.hide()
            main_layout.addWidget(self.loading_label)

    def create_summary_card(self, title, value, color_hex):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 6px;
                border: 1px solid #E0E0E0;
            }
        """)
        card.setFixedHeight(96)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        title_label.setStyleSheet(f"""
            QLabel {{
                background-color: {color_hex};
                color: white;
                padding: 8px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
        """)

        value_label = QLabel(value)
        value_label.setObjectName("value_label")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        value_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #2c3e50;
                padding: 14px 8px;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)

        layout.addWidget(title_label)
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
        return self.service.get_combined_credit_overview()

    def on_data_loaded(self, result):
        self.is_loading = False
        # self.summary = result["summary"]
        self.combined_data = result["rows"]
        self.filtered_data = self.combined_data.copy()
        # self.update_summary_cards()
        self.populate_table()
        self.loading_label.hide()
        self.table.show()

    def on_error(self, error):
        self.is_loading = False
        self.loading_label.hide()
        self.table.show()
        QMessageBox.critical(self, "Error", f"Failed to load combined credit data:\n{error}")

    # def update_summary_cards(self):
    #     self._set_card_value(self.matched_card, str(self.summary.get("matched_count", 0)))
    #     self._set_card_value(self.receivable_card, f"${self.summary.get('total_receivable', 0.0):,.2f}")
    #     self._set_card_value(self.payable_card, f"${self.summary.get('total_payable', 0.0):,.2f}")
    #     direction = self.summary.get("net_direction", "Balanced")
    #     self._set_card_value(
    #         self.net_card,
    #         f"${self.summary.get('abs_net_balance', 0.0):,.2f} {direction}"
    #     )

    # def _set_card_value(self, card, value):
    #     label = card.findChild(QLabel, "value_label")
    #     if label:
    #         label.setText(value)

    def populate_table(self, data=None):
        if data is None:
            data = self.filtered_data

        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            name_item = QTableWidgetItem(item["name"])
            name_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.table.setItem(row, 0, name_item)

            phone_item = QTableWidgetItem(item.get("phone", ""))
            phone_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            phone_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, phone_item)

            sales_item = self._amount_item(item["credit_sales_remaining"])
            sales_item.setForeground(QColor("#27ae60"))
            self.table.setItem(row, 2, sales_item)

            purchases_item = self._amount_item(item["credit_purchases_remaining"])
            purchases_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 3, purchases_item)

            loan_receivable_item = self._amount_item(item.get("loan_receivable_remaining", 0.0))
            loan_receivable_item.setForeground(QColor("#16a085"))
            self.table.setItem(row, 4, loan_receivable_item)

            loan_payable_item = self._amount_item(item.get("loan_payable_remaining", 0.0))
            loan_payable_item.setForeground(QColor("#8e44ad"))
            self.table.setItem(row, 5, loan_payable_item)

            direction_item = QTableWidgetItem(item["direction"])
            direction_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            direction_item.setTextAlignment(Qt.AlignCenter)
            if item["direction"] == "WEDE EGNA":
                direction_item.setForeground(QColor("#27ae60"))
            elif item["direction"] == "WEDE ESU":
                direction_item.setForeground(QColor("#e74c3c"))
            else:
                direction_item.setForeground(QColor("#7f8c8d"))
            self.table.setItem(row, 6, direction_item)

            net_item = self._amount_item(item["abs_net_balance"])
            if item["net_balance"] > 0.01:
                net_item.setForeground(QColor("#27ae60"))
            elif item["net_balance"] < -0.01:
                net_item.setForeground(QColor("#e74c3c"))
            else:
                net_item.setForeground(QColor("#7f8c8d"))
            self.table.setItem(row, 7, net_item)

            self.table.setCellWidget(row, 8, self.create_action_buttons(item))

    def _amount_item(self, value):
        table_item = QTableWidgetItem(f"${value:,.2f}")
        table_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
        table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return table_item

    def create_action_buttons(self, item):
        widget = QWidget()
        widget.setMinimumWidth(310)  # ensure widget has enough space
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)  # tighter spacing

        sales_btn = QPushButton("Sales")
        sales_btn.setFixedSize(85, 38)
        sales_btn.setCursor(Qt.PointingHandCursor)
        sales_btn.setEnabled(bool(item["sale_ids"]))
        sales_btn.setToolTip("View this person's credit sales")
        sales_btn.setStyleSheet(self._button_style("#27ae60", "#219a52"))
        sales_btn.clicked.connect(lambda checked, row=item: self.view_sales(row))

        purchases_btn = QPushButton("Purchases")
        purchases_btn.setFixedSize(90, 38)
        purchases_btn.setCursor(Qt.PointingHandCursor)
        purchases_btn.setEnabled(bool(item["purchase_ids"]))
        purchases_btn.setToolTip("View this person's credit purchases")
        purchases_btn.setStyleSheet(self._button_style("#e74c3c", "#c0392b"))
        purchases_btn.clicked.connect(lambda checked, row=item: self.view_purchases(row))

        loans_btn = QPushButton("Loans")
        loans_btn.setFixedSize(80, 38)
        loans_btn.setCursor(Qt.PointingHandCursor)
        loans_btn.setEnabled(bool(item.get("loan_ids")))
        loans_btn.setToolTip("View this person's cash loans")
        loans_btn.setStyleSheet(self._button_style("#8e44ad", "#7d3c98"))
        loans_btn.clicked.connect(lambda checked, row=item: self.view_loans(row))

        layout.addWidget(sales_btn)
        layout.addWidget(purchases_btn)
        layout.addWidget(loans_btn)
        return widget

    @staticmethod
    def _button_style(color, hover_color):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {hover_color}; }}
            QPushButton:disabled {{
                background-color: #d1d5db;
                color: #6b7280;
            }}
        """

    def filter_table(self, text):
        self.search_text = text.lower().strip()
        if not self.search_text:
            self.filtered_data = self.combined_data.copy()
        else:
            filtered = []
            for item in self.combined_data:
                searchable = [
                    item["name"],
                    item.get("phone", ""),
                    item["direction"],
                    f"${item['credit_sales_remaining']:,.2f}",
                    f"${item['credit_purchases_remaining']:,.2f}",
                    f"${item.get('loan_receivable_remaining', 0.0):,.2f}",
                    f"${item.get('loan_payable_remaining', 0.0):,.2f}",
                    f"${item['abs_net_balance']:,.2f}",
                ]
                if any(self.search_text in value.lower() for value in searchable):
                    filtered.append(item)
            self.filtered_data = filtered
        self.populate_table()

    def view_sales(self, item):
        if not item["sale_ids"]:
            return
        from ui.pages.sales_card_dialog import CustomerSalesListDialog

        dialog = CustomerSalesListDialog(
            self,
            item["name"],
            item["sale_ids"],
            self.current_user,
        )
        dialog.setModal(False)
        dialog.show()

    def view_purchases(self, item):
        if not item["supplier_ids"]:
            QMessageBox.information(self, "Info", "No supplier IDs found for this entry.")
            return
        supplier_id = item["supplier_ids"][0]
        from ui.pages.credit_purchases_overview_dialog import SupplierPurchasesListDialog
        dialog = SupplierPurchasesListDialog(
            self,
            item["name"],
            supplier_id,
            self.current_user
        )
        dialog.setModal(False)
        dialog.show()
    
    def view_loans(self, item):
        from ui.pages.cash_loans_dialog import CashLoansOverviewDialog

        dialog = CashLoansOverviewDialog(self, self.current_user, initial_search=item["name"])
        dialog.setModal(False)
        dialog.show()

    def closeEvent(self, event):
        try:
            if self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(1000)
        except RuntimeError:
            pass
        event.accept()