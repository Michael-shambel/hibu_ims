from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame, QLineEdit, QApplication
)
from PySide6.QtCore import Qt, QThread
import logging
from PySide6.QtGui import QFont, QColor, QFontMetrics
from services.purchase_service import PurchaseService
from ui.pages.purchase_items_dialog import PurchaseItemsDialog
from ui.pages.credit_payment_dialog import CreditPaymentDialog
from ui.components.ethiopian_date import EthiopianDateConverter
from ui.utils.worker import Worker

logger = logging.getLogger(__name__)

class CreditPurchasesOverviewDialog(QDialog):
    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Credit Purchases Overview")
        self.setMinimumSize(1200, 700)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.purchase_service = PurchaseService()
        self.summary = {}
        self.supplier_data = []
        self.filtered_data = []
        self.search_text = ""
        self._abort = False
        self.is_loading = False
        self._closed = False
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

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 10, 0, 10)
        search_label = QLabel("Search:")
        search_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter by supplier, status, or amount...")
        self.search_edit.setMinimumHeight(35)
        self.search_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        self.search_edit.textChanged.connect(self.filter_table)
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFixedSize(120, 35)
        refresh_btn.clicked.connect(self.refresh_data)
        search_layout.addWidget(refresh_btn)
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
        headers = ["Supplier", "Total", "Paid", "Remaining", "Status", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 200)

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
        self.loading_label = QLabel("Loading credit purchases data, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)

    def refresh_data(self):
        """Reload data manually."""
        self.load_data()

    def load_data(self):
        if self.is_loading:
            return
        self.is_loading = True
        self._abort = False
        self.loading_label.show()
        self.table.hide()

        # NOT parented to the dialog: this lets the background job finish
        # safely and clean itself up on its own, even if the dialog is
        # closed/destroyed before the job completes.
        self.thread = QThread()
        self.worker = Worker(self._fetch_data)
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
        summary = self.purchase_service.get_credit_purchases_summary()
        suppliers = self.purchase_service.get_credit_purchases_by_supplier()
        return summary, suppliers

    def on_data_loaded(self, result):
        if self._closed or self._abort:
            self.is_loading = False
            return
        self.is_loading = False
        summary, suppliers = result
        self.summary = summary
        self.supplier_data = suppliers
        self.supplier_data.sort(key=lambda x: x['remaining'], reverse=True)
        self.filtered_data = self.supplier_data.copy()
        self.total_unpaid_label.setText(f"Total Unpaid: ${self.summary['total_unpaid']:,.2f}")
        self.populate_table()
        self.loading_label.hide()
        self.table.show()

    def on_error(self, error):
        if self._closed or self._abort:
            self.is_loading = False
            return
        self.is_loading = False
        self.loading_label.hide()
        self.table.show()
        QMessageBox.critical(self, "Error", f"Failed to load credit purchases data:\n{error}")

    def populate_table(self, data=None):
        if data is None:
            data = self.filtered_data

        self.table.setRowCount(len(data))
        for row, pur in enumerate(data):
            name_item = QTableWidgetItem(pur['supplier_name'])
            name_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, name_item)

            self.table.setItem(row, 1, self._amount_item(pur['total_amount']))
            self.table.setItem(row, 2, self._amount_item(pur['paid_amount']))
            remaining_item = self._amount_item(pur['remaining'])
            remaining_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 3, remaining_item)

            status_item = QTableWidgetItem(pur['status'])
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            if pur['status'] == 'Paid':
                status_item.setForeground(QColor("#27ae60"))
            elif pur['status'] == 'Partial':
                status_item.setForeground(QColor("#f39c12"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 4, status_item)

            actions_widget = self.create_action_buttons(pur)
            self.table.setCellWidget(row, 5, actions_widget)

    def _amount_item(self, value):
        item = QTableWidgetItem(f"${value:,.2f}")
        item.setFont(QFont("Segoe UI", 13, QFont.Bold))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def create_action_buttons(self, purchase):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        view_btn = QPushButton("👁️")
        view_btn.setFixedSize(40, 40)
        view_btn.setToolTip("View all credit purchases for this supplier")
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
        view_btn.clicked.connect(lambda checked, s=purchase: self.view_supplier_purchases(s))

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
        history_btn.clicked.connect(lambda checked, s=purchase: self.show_payment_history(s))

        pay_btn = QPushButton("💰")
        pay_btn.setFixedSize(40, 40)
        pay_btn.setToolTip("Record payment against this supplier's total")
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
        pay_btn.clicked.connect(lambda checked, s=purchase: self.pay_supplier(s))

        layout.addWidget(view_btn)
        layout.addWidget(history_btn)
        layout.addWidget(pay_btn)
        return widget

    def filter_table(self, text):
        self.search_text = text.lower()
        if not self.search_text:
            self.filtered_data = self.supplier_data.copy()
        else:
            filtered = []
            for supp in self.supplier_data:
                if self.search_text in supp['supplier_name'].lower():
                    filtered.append(supp)
                    continue
                if self.search_text in supp['status'].lower():
                    filtered.append(supp)
                    continue
                amount_str = f"${supp['total_amount']:,.2f}".lower()
                if self.search_text in amount_str:
                    filtered.append(supp)
                    continue
                amount_str = f"${supp['paid_amount']:,.2f}".lower()
                if self.search_text in amount_str:
                    filtered.append(supp)
                    continue
                amount_str = f"${supp['remaining']:,.2f}".lower()
                if self.search_text in amount_str:
                    filtered.append(supp)
                    continue
            self.filtered_data = filtered
        self.populate_table()

    def view_supplier_purchases(self, supp):
        from ui.pages.credit_purchases_overview_dialog import SupplierPurchasesListDialog
        dialog = SupplierPurchasesListDialog(
            self,
            supp['supplier_name'],
            supp['supplier_id'],
            self.current_user
        )
        dialog.setModal(False)
        dialog.show()
        self.load_data()

    def show_payment_history(self, supp):
        from ui.pages.credit_purchases_overview_dialog import PurchasePaymentHistoryDialog
        dialog = PurchasePaymentHistoryDialog(
            self,
            supp['supplier_name'],
            supp['supplier_id'],
            self.current_user
        )
        dialog.setModal(False)
        dialog.show()
        self.load_data()

    def pay_supplier(self, supp):
        dialog = CreditPaymentDialog(
            self,
            customer_id=supp['supplier_id'],
            customer_name=supp['supplier_name'],
            total_due=supp['remaining'],
            current_user=self.current_user,
            transaction_type='purchase'
        )
        if dialog.exec() == QDialog.Accepted:
            self.load_data()

    def closeEvent(self, event):
        self._closed = True
        self._abort = True

        if self.worker is not None:
            try:
                self.worker.finished.disconnect(self.on_data_loaded)
                self.worker.error.disconnect(self.on_error)
            except (RuntimeError, TypeError):
                pass

        self.thread = None
        self.worker = None
        self.is_loading = False
        event.accept()


class SupplierPurchasesListDialog(QDialog):
    """Displays all credit purchases for a single supplier, grouped by date."""
    def __init__(self, parent, supplier_name, supplier_id, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Credit Purchases - {supplier_name}")
        self.setMinimumSize(800, 400)
        self.resize(1000, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.supplier_name = supplier_name
        self.supplier_id = supplier_id
        self.current_user = current_user
        self.purchase_ids = []
        self.grouped_data = []
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

        self.table = QTableWidget()
        headers = ["Purchase Date (Ethiopian)", "Total Amount", "Paid Amount", "Remaining", "Status", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
            self.table.setColumnWidth(col, 140)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(4, 120)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 120)

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

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFixedSize(130, 45)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_data)

        btn_close = QPushButton("Close")
        btn_close.setFixedSize(120, 45)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        btn_close.clicked.connect(self.accept)

        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(btn_close)

        layout.addLayout(button_layout)

    def refresh_data(self):
        self.load_data()

    def _to_ethiopian_date_str(self, dt):
        if not dt:
            return ""
        try:
            from ui.components.ethiopian_date import EthiopianDateConverter
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(dt)
            return f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        except Exception:
            return dt.strftime("%Y-%m-%d")

    def load_data(self):
        from sqlalchemy import func
        from services.base_service import get_session
        from models.supplier_credit_ledger import SupplierCreditLedger
        from models.purchase import Purchase

        with get_session() as session:
            self.purchase_ids = [row.id for row in session.query(Purchase.id).filter(
                Purchase.supplier_id == self.supplier_id,
                Purchase.is_deleted == False
            ).all()]

            rows = session.query(
                SupplierCreditLedger.entry_date,
                SupplierCreditLedger.entry_type,
                func.sum(SupplierCreditLedger.debit).label('total_debit'),
                func.sum(SupplierCreditLedger.credit).label('total_credit')
            ).filter(
                SupplierCreditLedger.supplier_id == self.supplier_id,
                SupplierCreditLedger.is_deleted == False
            ).group_by(
                SupplierCreditLedger.entry_date,
                SupplierCreditLedger.entry_type
            ).order_by(SupplierCreditLedger.entry_date.asc()).all()

        date_totals = {}
        for row in rows:
            d = row.entry_date
            if d not in date_totals:
                date_totals[d] = {'total_amount': 0.0, 'paid_amount': 0.0}

            if row.entry_type == 'purchase':
                date_totals[d]['total_amount'] += row.total_debit
            elif row.entry_type == 'payment':
                date_totals[d]['paid_amount'] += row.total_credit
            else:
                net = row.total_debit - row.total_credit
                date_totals[d]['total_amount'] += net

        with get_session() as session:
            purchases = session.query(Purchase).filter(
                Purchase.supplier_id == self.supplier_id,
                Purchase.is_deleted == False
            ).all()
            pid_to_date = {p.id: p.purchase_date for p in purchases}

            for d in date_totals:
                date_totals[d]['purchase_ids'] = []

            for pid, pdate in pid_to_date.items():
                if pdate in date_totals:
                    date_totals[pdate]['purchase_ids'].append(pid)
                else:
                    if pdate not in date_totals:
                        date_totals[pdate] = {'total_amount': 0.0, 'paid_amount': 0.0, 'purchase_ids': []}
                    date_totals[pdate]['purchase_ids'].append(pid)

        self.grouped_data = []
        for group_date, data in date_totals.items():
            remaining = data['total_amount'] - data['paid_amount']
            if remaining <= 0:
                status = 'Paid'
            elif data['paid_amount'] > 0:
                status = 'Partial'
            else:
                status = 'Unpaid'

            self.grouped_data.append({
                'purchase_date': group_date,
                'total_amount': data['total_amount'],
                'paid_amount': data['paid_amount'],
                'remaining': remaining,
                'status': status,
                'purchase_ids': data.get('purchase_ids', []),
                'payment_term_ids': [],
                'is_unknown': group_date is None
            })

        # Sort newest first
        def sort_key(entry):
            if entry['is_unknown'] or entry['purchase_date'] is None:
                return (1, None)
            return (0, -entry['purchase_date'].toordinal())

        self.grouped_data.sort(key=sort_key)
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.grouped_data))
        for row, group in enumerate(self.grouped_data):
            if group['is_unknown']:
                date_str = "Unknown Date"
            else:
                date_str = self._to_ethiopian_date_str(group['purchase_date'])

            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            total_item = QTableWidgetItem(f"${group['total_amount']:,.2f}")
            total_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, total_item)

            paid_item = QTableWidgetItem(f"${group['paid_amount']:,.2f}")
            paid_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            paid_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, paid_item)

            rem_item = QTableWidgetItem(f"${group['remaining']:,.2f}")
            rem_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            rem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, rem_item)

            status_item = QTableWidgetItem(group['status'])
            status_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            if group['status'] == 'Paid':
                status_item.setForeground(QColor("#27ae60"))
            elif group['status'] == 'Partial':
                status_item.setForeground(QColor("#f39c12"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 4, status_item)

            if group.get('purchase_ids'):
                view_btn = QPushButton("View Items")
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
                view_btn.clicked.connect(lambda checked, ids=group['purchase_ids']: self.view_items(ids))
                self.table.setCellWidget(row, 5, view_btn)
            else:
                empty_item = QTableWidgetItem("—")
                empty_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
                empty_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 5, empty_item)

    def view_items(self, purchase_ids):
        try:
            from services.purchase_service import PurchaseService
            from ui.pages.purchase_items_dialog import PurchaseItemsDialog

            service = PurchaseService()
            all_items = []
            for pid in purchase_ids:
                purchase = service.get_purchase_with_batches(pid)
                if not purchase:
                    continue
                if purchase.batches:
                    for batch in purchase.batches:
                        if batch.is_deleted:
                            continue
                        product = batch.product
                        product_name = product.name if product else "Unknown"
                        pack_qty = batch.quantity
                        dozen = product.dozen if product and hasattr(product, 'dozen') else 1
                        unit_price = batch.cost_price
                        total = pack_qty * dozen * unit_price
                        all_items.append({
                            'product_name': product_name,
                            'pack_qty': pack_qty,
                            'dozen': dozen,
                            'unit_price': unit_price,
                            'total': total
                        })
                elif purchase.items_data:
                    for raw in purchase.items_data:
                        product_name = raw.get('name') or raw.get('product_name', '')
                        pack_qty = raw.get('quantity', 0)
                        dozen = raw.get('dozen', 1)
                        unit_price = raw.get('cost_price', 0.0)
                        total = raw.get('total', pack_qty * dozen * unit_price)
                        all_items.append({
                            'product_name': product_name,
                            'pack_qty': pack_qty,
                            'dozen': dozen,
                            'unit_price': unit_price,
                            'total': total
                        })

            if not all_items:
                QMessageBox.information(self, "No Items", "No items found for these purchases.")
                return

            class DummyPurchase:
                pass
            dummy = DummyPurchase()
            dummy.batches = None
            dummy.items_data = all_items
            group = next((g for g in self.grouped_data if set(g['purchase_ids']) == set(purchase_ids)), None)
            if group and not group['is_unknown']:
                date_str = self._to_ethiopian_date_str(group['purchase_date'])
            else:
                date_str = "Unknown Date"
            dialog = PurchaseItemsDialog(self, f"Items for {self.supplier_name} on {date_str}", dummy, self.current_user)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load items: {str(e)}")
            import logging
            logging.exception("Error in view_items")


class PurchasePaymentHistoryDialog(QDialog):
    def __init__(self, parent, supplier_name, supplier_id, current_user):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"Payment History - {supplier_name}")
        self.setMinimumSize(800, 500)
        self.resize(1000, 600)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.supplier_id = supplier_id
        self.current_user = current_user
        self.transactions = []
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

        self.table = QTableWidget()
        headers = ["Date", "Balance", "Credit", "Debit", "Bank Account", "Remaining", "Note", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setWordWrap(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 150)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self.table.setColumnWidth(7, 80)

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

    def _to_ethiopian_date_str(self, dt):
        if not dt:
            return ""
        try:
            from ui.components.ethiopian_date import EthiopianDateConverter
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(dt)
            return f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        except Exception:
            return dt.strftime("%Y-%m-%d")

    def load_data(self):
        from services.purchase_service import PurchaseService
        service = PurchaseService()
        self.transactions = service.get_supplier_combined_history(self.supplier_id)
        self.populate_table()

    def populate_table(self):
        display_transactions = list(reversed(self.transactions))
        self.table.setRowCount(len(display_transactions))

        FIXED_ROW_HEIGHT = 60
        self.table.verticalHeader().setDefaultSectionSize(FIXED_ROW_HEIGHT)

        for row, tx in enumerate(display_transactions):
            date_str = self._to_ethiopian_date_str(tx['date']) if tx['date'] else ""
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 0, date_item)

            balance_item = QTableWidgetItem(f"${tx['balance_before']:,.2f}")
            balance_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, balance_item)

            credit_item = QTableWidgetItem(f"${tx['credit_amount']:,.2f}" if tx['credit_amount'] > 0 else "")
            credit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            credit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if tx['credit_amount'] > 0:
                credit_item.setForeground(QColor("#27ae60"))
            self.table.setItem(row, 2, credit_item)

            debit_item = QTableWidgetItem(f"${tx['debit_amount']:,.2f}" if tx['debit_amount'] > 0 else "")
            debit_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            debit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if tx['debit_amount'] > 0:
                debit_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 3, debit_item)

            bank_item = QTableWidgetItem(tx['bank_account_display'])
            bank_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 4, bank_item)

            remaining_item = QTableWidgetItem(f"${tx['balance_after']:,.2f}")
            remaining_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            remaining_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 5, remaining_item)

            note_text = tx['notes'] if tx['notes'] else " "
            note_item = QTableWidgetItem(note_text)
            note_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            note_item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            note_item.setToolTip(note_text)
            self.table.setItem(row, 6, note_item)

            if tx['type'] == 'payment' and self.is_user_admin():
                delete_btn = QPushButton("🗑️")
                delete_btn.setFixedSize(40, 40)
                delete_btn.setToolTip("Delete this payment")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        font-size: 18px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #c0392b; }
                """)
                delete_btn.clicked.connect(lambda checked, bt_id=tx['bank_transaction_id']: self.delete_payment_group(bt_id))
                self.table.setCellWidget(row, 7, delete_btn)
            else:
                self.table.setItem(row, 7, QTableWidgetItem(""))

            self.table.setRowHeight(row, FIXED_ROW_HEIGHT)

    def is_user_admin(self):
        if not self.current_user:
            return False
        if isinstance(self.current_user, dict):
            return self.current_user.get('is_admin') or self.current_user.get('role') == 'admin'
        return getattr(self.current_user, 'is_admin', False)

    def delete_payment(self, transaction_id):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Delete this payment? This will update the supplier's balance.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        from services.purchase_service import PurchaseService
        service = PurchaseService()
        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        if service.delete_payment_transaction(transaction_id, user_id):
            QMessageBox.information(self, "Success", "Payment deleted.")
            self.load_data()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete payment.")

    def delete_payment_group(self, bank_transaction_id):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Delete this payment? This will remove the bank transaction and all linked allocations.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        from services.purchase_service import PurchaseService
        service = PurchaseService()
        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        if service.delete_bank_transaction_with_payments(bank_transaction_id, user_id):
            QMessageBox.information(self, "Success", "Payment deleted.")
            self.load_data()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete payment.")