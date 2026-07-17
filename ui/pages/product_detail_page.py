from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QHBoxLayout, QSpinBox, QTextEdit,
    QFrame, QGridLayout, QTableWidget, QTableWidgetItem, QFormLayout, QComboBox,
    QPushButton, QHeaderView, QMessageBox, QWidget, QMessageBox, QDoubleSpinBox
)
from PySide6.QtCore import QDate
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QIcon, QKeySequence, QAction
from models.sale_payment_term import PaymentStatusEnum
from services.new_product_service import NewProductService
from services.product_batch_service import ProductBatchService
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService
from ui.pages.batch_transaction_history_dialog import BatchTransactionHistoryDialog
from ui.components.ethiopian_date import EthiopianDateEdit, EthiopianDateConverter
import logging
from datetime import date

logger = logging.getLogger(__name__)


class DamageBatchDialog(QDialog):
    def __init__(self, batch, parent=None):
        super().__init__(parent)
        self.batch = batch
        self.setWindowTitle(f"Report Damage - Batch #{batch.id}")
        self.setMinimumWidth(450)
        self.setModal(True)  # Make it modal
        self.init_ui()
        # Remove WA_DeleteOnClose - let caller manage deletion
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Product info with better formatting
        product_name = self.batch.product.name if hasattr(self.batch, 'product') else "Unknown"
        
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        
        info_text = QLabel(f"<b>Product:</b> {product_name}<br>"
                          f"<b>Available:</b> {self.batch.available_quantity} units")
        info_text.setTextFormat(Qt.RichText)
        info_layout.addWidget(info_text)
        layout.addWidget(info_frame)
        
        # Quantity input with better validation
        qty_layout = QHBoxLayout()
        qty_label = QLabel("Damaged Quantity:")
        qty_label.setMinimumWidth(120)
        qty_layout.addWidget(qty_label)
        
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, self.batch.available_quantity)
        self.qty_spin.valueChanged.connect(self.on_quantity_changed)
        qty_layout.addWidget(self.qty_spin)
        
        # Add max label
        self.max_label = QLabel(f"(Max: {self.batch.available_quantity})")
        self.max_label.setStyleSheet("color: #6c757d;")
        qty_layout.addWidget(self.max_label)
        qty_layout.addStretch()
        layout.addLayout(qty_layout)
        
        # Notes
        notes_label = QLabel("Notes (optional):")
        notes_label.setMinimumWidth(120)
        layout.addWidget(notes_label)
        
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlaceholderText("Enter reason for damage or additional notes...")
        layout.addWidget(self.notes_edit)
        
        # Warning label for large quantities
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #e74c3c;")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("Report Damage")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        save_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
    
    def on_quantity_changed(self, value):
        """Show warning if reporting large damage amount"""
        if value > self.batch.available_quantity * 0.5:
            percentage = (value / self.batch.available_quantity * 100)
            self.warning_label.setText(f"⚠️ Warning: You're reporting {value} units damaged "
                                      f"({percentage:.1f}% of available stock)")
        else:
            self.warning_label.clear()
    
    def get_data(self):
        """Return damage data safely"""
        # Store values before returning
        quantity = self.qty_spin.value() if hasattr(self, 'qty_spin') else 0
        notes = self.notes_edit.toPlainText().strip() if hasattr(self, 'notes_edit') else ""
        
        return {
            "quantity": quantity,
            "notes": notes
        }
    
    def accept(self):
        """Validate and accept"""
        # Validate quantity
        if self.qty_spin.value() <= 0:
            QMessageBox.warning(self, "Validation Error", 
                               "Please enter a valid quantity.")
            return
        
        # Confirm if large quantity
        if self.qty_spin.value() > self.batch.available_quantity * 0.5:
            reply = QMessageBox.question(
                self,
                "Confirm Large Damage",
                f"You are reporting {self.qty_spin.value()} units damaged "
                f"({self.qty_spin.value()/self.batch.available_quantity*100:.1f}% of stock).\n\n"
                f"Are you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        super().accept()

class EditBatchDialog(QDialog):
    def __init__(self, batch, parent=None):
        super().__init__(parent)
        self.batch = batch
        self.original_total_qty = batch.quantity
        self.original_available_qty = batch.available_quantity
        # New: the true running balance from transactions, not the stored field
        self.original_running_balance = self._calculate_running_balance(batch.id)

        self.purchase = batch.purchase
        self.payment_term = None
        self.payment_transaction = None
        if self.purchase and self.purchase.payment_terms:
            self.payment_term = self.purchase.payment_terms[0]
            if self.payment_term and self.payment_term.payment_status == PaymentStatusEnum.PAID:
                self.payment_transaction = self.payment_term.purchase_payment_transaction[0] if self.payment_term.purchase_payment_transaction else None

        self.setWindowTitle(f"Edit Batch #{batch.id} and Purchase")
        self.setMinimumWidth(550)
        self.setModal(True)
        self.init_ui()

    def _calculate_running_balance(self, batch_id: int) -> int:
        """Sum the signed quantities of all non‑deleted batch transactions."""
        from services.base_service import get_session
        from models.batch_transaction import BatchTransaction
        with get_session() as session:
            txs = session.query(BatchTransaction).filter(
                BatchTransaction.batch_id == batch_id,
                BatchTransaction.is_deleted == False
            ).all()
            balance = 0
            for tx in txs:
                qty = tx.quantity
                tx_type = tx.transaction_type.value if tx.transaction_type else ""
                # Existing sale transactions are stored positive → treat as negative
                if tx_type.lower() == 'sale' and qty > 0:
                    balance -= qty
                else:
                    balance += qty   # stock_in, received, adjustment (already signed)
            return balance

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Product info
        product_name = self.batch.product.name if hasattr(self.batch, 'product') else "Unknown"
        info = QLabel(f"<b>Product:</b> {product_name}")
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet("background-color: #e8f4fd; padding: 10px; border-radius: 4px;")
        layout.addWidget(info)

        # Batch fields
        batch_frame = QFrame()
        batch_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 10px;")
        batch_layout = QFormLayout(batch_frame)

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(0, 1000000)
        self.qty_spin.setValue(self.original_total_qty)
        self.qty_spin.valueChanged.connect(self.on_total_quantity_changed)
        batch_layout.addRow("Total Quantity:", self.qty_spin)

        self.avail_spin = QSpinBox()
        self.avail_spin.setRange(0, self.qty_spin.value())
        # Pre-fill with the correct running balance, not the possibly drifted available field
        self.avail_spin.setValue(self.original_running_balance)
        self.avail_spin.valueChanged.connect(self.on_available_changed)
        batch_layout.addRow("Available Quantity:", self.avail_spin)

        self.cost_spin = QDoubleSpinBox()
        self.cost_spin.setRange(0.0, 1000000.0)
        self.cost_spin.setDecimals(2)
        self.cost_spin.setValue(self.batch.cost_price)
        self.cost_spin.setPrefix("$ ")
        batch_layout.addRow("Cost Price:", self.cost_spin)

        layout.addWidget(batch_frame)

        # Purchase / payment fields (if the batch belongs to a purchase)
        if self.purchase:
            purchase_frame = QFrame()
            purchase_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 10px;")
            purchase_layout = QFormLayout(purchase_frame)

            # Supplier
            self.supplier_combo = QComboBox()
            self.supplier_combo.setEditable(True)
            self.supplier_combo.setMinimumHeight(35)
            self.load_suppliers()
            if self.purchase.supplier:
                idx = self.supplier_combo.findData(self.purchase.supplier.id)
                if idx >= 0:
                    self.supplier_combo.setCurrentIndex(idx)
            purchase_layout.addRow("Supplier:", self.supplier_combo)

            # Show bank & payment date only if purchase is paid
            if self.payment_term and self.payment_term.payment_status == PaymentStatusEnum.PAID:
                self.bank_combo = QComboBox()
                self.bank_combo.setMinimumHeight(35)
                self.load_bank_accounts()
                if self.payment_transaction and self.payment_transaction.bank_account_id:
                    idx = self.bank_combo.findData(self.payment_transaction.bank_account_id)
                    if idx >= 0:
                        self.bank_combo.setCurrentIndex(idx)
                purchase_layout.addRow("Bank Account:", self.bank_combo)

                self.payment_date = EthiopianDateEdit()
                if self.payment_transaction and self.payment_transaction.payment_date:
                    py_date = self.payment_transaction.payment_date
                    qdate = QDate(py_date.year, py_date.month, py_date.day)
                    self.payment_date.setDate(qdate)
                else:
                    py_date = self.purchase.purchase_date or date.today()
                    qdate = QDate(py_date.year, py_date.month, py_date.day)
                    self.payment_date.setDate(qdate)
                purchase_layout.addRow("Payment Date:", self.payment_date)

            layout.addWidget(purchase_frame)

        # Warning label
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #e74c3c;")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Changes")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        save_btn.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def load_suppliers(self):
        try:
            supplier_service = SupplierService()
            suppliers = supplier_service.get_all()
            self.supplier_combo.clear()
            self.supplier_combo.addItem("Select Supplier", None)
            for supp in suppliers:
                self.supplier_combo.addItem(supp.supplier_name, supp.id)
        except Exception as e:
            logger.error(f"Error loading suppliers: {e}")

    def load_bank_accounts(self):
        try:
            bank_service = BankAccountService()
            accounts = bank_service.get_all()
            self.bank_combo.clear()
            self.bank_combo.addItem("Select Bank Account", None)
            for acc in accounts:
                display = f"{acc.account_name} - {acc.bank_name} ({acc.account_number})"
                self.bank_combo.addItem(display, acc.id)
        except Exception as e:
            logger.error(f"Error loading bank accounts: {e}")

    def on_total_quantity_changed(self, new_total):
        """
        Adjust available quantity based on change from original total.
        The original available used for the UI is the running balance to keep consistency.
        """
        delta_total = new_total - self.original_total_qty
        new_avail = self.original_running_balance + delta_total
        new_avail = max(0, min(new_avail, new_total))

        self.avail_spin.blockSignals(True)
        self.avail_spin.setValue(new_avail)
        self.avail_spin.setMaximum(new_total)
        self.avail_spin.blockSignals(False)

        if new_total < self.original_total_qty and new_avail == new_total:
            self.warning_label.setText("⚠️ Total quantity decreased. Available quantity reduced accordingly.")
        else:
            self.warning_label.clear()

    def on_available_changed(self, value):
        """Ensure available does not exceed total."""
        if value > self.qty_spin.value():
            self.avail_spin.setValue(self.qty_spin.value())

    def get_data(self):
        """Return all data to be updated. Adjustment delta uses running balance as baseline."""
        new_total = self.qty_spin.value()
        new_avail = self.avail_spin.value()
        # Key fix: delta relative to the true running balance, not the potentially wrong field
        delta_avail = new_avail - self.original_running_balance

        data = {
            "batch": {
                "quantity": new_total,
                "available_quantity": new_avail,
                "cost_price": self.cost_spin.value(),
            }
        }

        # Create adjustment transaction if available quantity changed
        if delta_avail != 0:
            data["adjustment"] = {
                "delta": delta_avail,
                "old_quantity": self.original_running_balance,
                "new_quantity": new_avail,
                "notes": f"Manual adjustment: running balance {self.original_running_balance} → {new_avail}"
            }

        if self.purchase:
            data["purchase"] = {
                "supplier_id": self.supplier_combo.currentData()
            }
            if self.payment_term and self.payment_term.payment_status == PaymentStatusEnum.PAID:
                data["payment"] = {
                    "bank_account_id": self.bank_combo.currentData(),
                    "payment_date": self.payment_date.date().toPython()
                }
        return data

    def accept(self):
        """Validate and accept."""
        if self.avail_spin.value() > self.qty_spin.value():
            QMessageBox.warning(self, "Validation Error", "Available quantity cannot exceed total quantity.")
            return
        if self.purchase and not self.supplier_combo.currentData():
            QMessageBox.warning(self, "Validation Error", "Please select a supplier.")
            return
        if self.payment_term and self.payment_term.payment_status == PaymentStatusEnum.PAID:
            if not hasattr(self, 'bank_combo') or not self.bank_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "Please select a bank account.")
                return
        super().accept()

class ProductDetailsDialog(QDialog):
    def __init__(self, product_data, current_user=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.product_data = product_data
        self.product_id = product_data["id"]
        self.current_user = current_user
        self.new_product_service = NewProductService()
        self.product_batch_service = ProductBatchService()

        self.setWindowTitle(f"Product Details - {product_data['name']}")
        self.setMinimumSize(900, 600)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.load_batch_details()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Title with larger bold font
        title_label = QLabel(f"Product Details: {self.product_data['name']}")
        title_font = QFont("Segoe UI", 18, QFont.Bold)  # Increased size
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        self.product_info_widget = self.create_product_info_section()
        main_layout.addWidget(self.product_info_widget, 0)

        # Batch information section label
        batches_label = QLabel("Batch Information")
        batches_font = QFont("Segoe UI", 16, QFont.Bold)  # Increased size
        batches_label.setFont(batches_font)
        batches_label.setStyleSheet("color: #2c3e50; margin-top: 10px;")
        main_layout.addWidget(batches_label)

        # Batch table
        self.batch_table = self.create_batch_table()
        main_layout.addWidget(self.batch_table, 1)

        button_layout = QHBoxLayout()

        self.close_button = QPushButton("Close")
        self.close_button.setMinimumHeight(45)  # Larger button
        close_font = QFont("Segoe UI", 12, QFont.Bold)
        self.close_button.setFont(close_font)
        self.close_button.clicked.connect(self.accept)

        button_layout.addStretch()
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)

    def create_product_info_section(self):
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        layout = QGridLayout(widget)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)

        # Fonts for labels and values
        label_font = QFont("Segoe UI", 13, QFont.Bold)
        value_font = QFont("Segoe UI", 14, QFont.Bold)

        # Price
        price_label = QLabel("Price:")
        price_label.setFont(label_font)
        layout.addWidget(price_label, 1, 0)

        self.lbl_price = QLabel(f"${self.product_data['price']:.2f}")
        self.lbl_price.setFont(value_font)
        layout.addWidget(self.lbl_price, 1, 1)


        # Available Stock
        stock_label = QLabel("Available Stock:")
        stock_label.setFont(label_font)
        layout.addWidget(stock_label, 2, 0)

        self.lbl_stock = QLabel(str(self.product_data["stock"]))
        self.lbl_stock.setFont(value_font)
        if self.product_data["stock"] <= 10:
            self.lbl_stock.setStyleSheet("color: #e74c3c; font-weight: bold;")
        elif self.product_data["stock"] <= 50:
            self.lbl_stock.setStyleSheet("color: #f39c12; font-weight: bold;")
        else:
            self.lbl_stock.setStyleSheet("color: #27ae60; font-weight: bold;")
        layout.addWidget(self.lbl_stock, 2, 1)

        # Number of Batches
        batches_label = QLabel("Number of Batches:")
        batches_label.setFont(label_font)
        layout.addWidget(batches_label, 3, 0)

        self.lbl_batches = QLabel(str(self.product_data["total_batches"]))
        self.lbl_batches.setFont(value_font)
        layout.addWidget(self.lbl_batches, 3, 1)

        return widget

    def create_batch_table(self):
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Purchase Date", "Supplier Name", "Quantity", "Available", "Cost Price", "Actions"
        ])

        # --- Accessibility: larger bold font ---
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        table.setFont(font)

        table.setStyleSheet("""
            QTableWidget {
                font-size: 18px;
                font-weight: bold;
            }
            QHeaderView::section {
                font-size: 18px;
                font-weight: bold;
                padding: 12px;
            }
            QTableWidget::item {
                padding: 15px;
            }
        """)

        header = table.horizontalHeader()
        table.setColumnWidth(0, 180)   # Purchase Date (wider for Ethiopian dd/mm/yyyy)
        table.setColumnWidth(1, 250)   # Supplier Name
        table.setColumnWidth(2, 140)   # Quantity
        table.setColumnWidth(3, 140)   # Available
        table.setColumnWidth(4, 150)   # Cost Price
        table.setColumnWidth(5, 240)   # Actions (wider for larger buttons)


        # header.setSectionResizeMode(0, QHeaderView.Stretch)

        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)

        return table

    def load_batch_details(self):
        try:
            batch_info = self.new_product_service.get_batches_with_product(self.product_id)

            if not batch_info:
                return
            
            batch_info = list(reversed(batch_info))

            self.batch_table.setRowCount(0)

            for batch in batch_info:
                self.add_batch_row(batch)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load batch details:\n{e}")

    def add_batch_row(self, batch):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        self.batch_table.setRowHeight(row, 110)

        purchase_date = batch.purchase.purchase_date if batch.purchase else None
        if purchase_date:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(purchase_date)
            date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        else:
            date_str = "N/A"

        supplier_name = batch.purchase.supplier.supplier_name if batch.purchase and batch.purchase.supplier else "N/A"
        self.batch_table.setItem(row, 0, QTableWidgetItem(date_str))
        self.batch_table.setItem(row, 1, QTableWidgetItem(str(supplier_name)))
        self.batch_table.setItem(row, 2, QTableWidgetItem(str(batch.quantity)))
        self.batch_table.setItem(row, 3, QTableWidgetItem(str(batch.available_quantity)))
        self.batch_table.setItem(row, 4, QTableWidgetItem(str(batch.cost_price)))

        # Action Buttons
        actions_widget = self.create_batch_action_buttons(batch.id)
        self.batch_table.setCellWidget(row, 5, actions_widget)

    def create_batch_action_buttons(self, batch_id):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        button_size = 45
        btn_font = QFont("Segoe UI", 18)

        view_btn = QPushButton("👁️")
        view_btn.setFixedSize(button_size, button_size)
        view_btn.setFont(btn_font)
        view_btn.setToolTip("View Batch Details")
        view_btn.clicked.connect(lambda checked, bid=batch_id: self.view_batch_details(bid))

        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(button_size, button_size)
        edit_btn.setFont(btn_font)
        edit_btn.setToolTip("Edit Batch (Admin only)")
        if not self.is_user_admin():
            edit_btn.setEnabled(False)
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f8f9fa;
                    color: #bdc3c7;
                    border: 1px solid #ecf0f1;
                    border-radius: 4px;
                }
            """)
            edit_btn.setToolTip("Edit Batch - Admin access required")
        else:
            edit_btn.clicked.connect(lambda checked, bid=batch_id: self.edit_batch(bid))

        damage_btn = QPushButton("⚠️")
        damage_btn.setFixedSize(button_size, button_size)
        damage_btn.setFont(btn_font)
        damage_btn.setToolTip("Report Damage")
        damage_btn.clicked.connect(lambda checked, bid=batch_id: self.report_damage(bid))

        discount_btn = QPushButton("💲")
        discount_btn.setFixedSize(button_size, button_size)
        discount_btn.setFont(btn_font)
        discount_btn.setToolTip("Apply discount to remaining quantity")
        discount_btn.clicked.connect(lambda checked, bid=batch_id: self.apply_discount(bid))


        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(button_size, button_size)
        delete_btn.setFont(btn_font)
        delete_btn.setToolTip("Delete Batch (Admin only)")
        if not self.is_user_admin():
            delete_btn.setEnabled(False)
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f8f9fa;
                    color: #bdc3c7;
                    border: 1px solid #ecf0f1;
                    border-radius: 4px;
                }
            """)
            delete_btn.setToolTip("Delete Batch - Admin access required")
        else:
            delete_btn.clicked.connect(lambda checked, bid=batch_id: self.delete_batch(bid))

        layout.addWidget(view_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(damage_btn)
        layout.addWidget(discount_btn)
        layout.addWidget(delete_btn)

        return widget
    
    def apply_discount(self, batch_id):
        try:
            batch = self.new_product_service.get_batch_by_id(batch_id)
            if not batch:
                QMessageBox.warning(self, "Error", "Batch not found.")
                return

            if batch.available_quantity <= 0:
                QMessageBox.information(self, "Cannot Discount", "No remaining quantity to discount.")
                return

            from ui.pages.discount_split_dialog import DiscountSplitDialog
            dlg = DiscountSplitDialog(batch, self)
            if dlg.exec() == QDialog.Accepted:
                user_id = None
                if self.current_user:
                    if isinstance(self.current_user, dict):
                        user_id = self.current_user.get('id')
                    else:
                        user_id = getattr(self.current_user, 'id', None)

                from services.product_batch_service import ProductBatchService
                service = ProductBatchService()
                service.split_batch_for_discount(
                    batch_id=batch_id,
                    new_cost_price=dlg.new_price,
                    note=dlg.note,
                    user_id=user_id
                )

                self.refresh_product_info()
                self.load_batch_details()
        except Exception as e:
            logger.error(f"Error applying discount to batch {batch_id}: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def view_batch_details(self, batch_id):
        """Open dialog showing transaction history for this batch."""
        dialog = BatchTransactionHistoryDialog(batch_id, self)
        dialog.setModal(False)
        dialog.show()
        

    def edit_batch(self, batch_id):
        try:
            from services.product_batch_service import ProductBatchService
            batch_svc = ProductBatchService()
            batch = batch_svc.get_batch_with_purchase(batch_id)
            if not batch:
                QMessageBox.warning(self, "Error", "Batch not found.")
                return

            if not batch.purchase:
                QMessageBox.warning(self, "Error", "This batch has no associated purchase.")
                return

            dialog = EditBatchDialog(batch, self)
            result = dialog.exec()
            if result == QDialog.Accepted:
                data = dialog.get_data()
                updated = batch_svc.update_batch_with_purchase_details(batch_id, data)
                if updated:
                    QMessageBox.information(self, "Success", "Batch and purchase details updated.")
                    self.refresh_product_info()
                    self.load_batch_details()
                else:
                    QMessageBox.critical(self, "Error", "Failed to update batch details.")
            dialog.deleteLater()
        except Exception as e:
            logger.error(f"Error editing batch {batch_id}: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def delete_batch(self, batch_id):
        """Delete a batch and its transactions with confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete this batch?\n\n"
            f"This will also delete all transaction history for this batch.\n"
            f"This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            success = self.product_batch_service.delete_batch_cascade(batch_id)
            if success:
                QMessageBox.information(self, "Success", "Batch deleted successfully.")
                self.refresh_product_info()
                self.load_batch_details()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete batch.")

    def refresh_product_info(self):
        """Reload product data and update info labels."""
        product = self.new_product_service.get_by_id(self.product_id)
        if product:
            batch_count = self.product_batch_service.count_by_product(product.id)
            self.product_data = {
                "id": product.id,
                "name": product.name,
                "stock": product.available_quantity,
                "total_quantity": product.total_quantity,
                "price": product.selling_price,
                "unit": product.unit,
                "total_batches": batch_count
            }
            # Update labels
            # self.lbl_name.setText(self.product_data["name"])
            self.lbl_price.setText(f"${self.product_data['price']:.2f}")
            # self.lbl_unit.setText(self.product_data["unit"])
            self.lbl_stock.setText(str(self.product_data["stock"]))
            # Reapply stock level style
            if self.product_data["stock"] <= 10:
                self.lbl_stock.setStyleSheet("color: #e74c3c; font-weight: bold;")
            elif self.product_data["stock"] <= 50:
                self.lbl_stock.setStyleSheet("color: #f39c12; font-weight: bold;")
            else:
                self.lbl_stock.setStyleSheet("color: #27ae60; font-weight: bold;")
            # self.lbl_total.setText(str(self.product_data["total_quantity"]))
            self.lbl_batches.setText(str(batch_count))

    def report_damage(self, batch_id):
        """Report damage for a batch"""
        try:
            batch = self.new_product_service.get_batch_by_id(batch_id)
            if not batch:
                QMessageBox.warning(self, "Error", "Batch not found.")
                return

            dialog = DamageBatchDialog(batch, self)
            result = dialog.exec()

            if result == QDialog.Accepted:
                data = dialog.get_data()

                if data['quantity'] <= 0:
                    QMessageBox.warning(self, "Error", "Invalid quantity specified.")
                    return

                if data['quantity'] > batch.available_quantity:
                    QMessageBox.warning(self, "Error",
                                        f"Cannot report damage for {data['quantity']} units. "
                                        f"Only {batch.available_quantity} units available.")
                    return

                user_id = None
                if self.current_user:
                    if isinstance(self.current_user, dict):
                        user_id = self.current_user.get('id')
                    else:
                        user_id = getattr(self.current_user, 'id', None)

                success = self.product_batch_service.report_damage(
                    batch_id=batch_id,
                    quantity=data['quantity'],
                    notes=data['notes'],
                    user_id=user_id
                )

                if success:
                    QMessageBox.information(self, "Success",
                                            f"Successfully reported {data['quantity']} units as damaged.")
                    self.refresh_product_info()
                    self.load_batch_details()
                else:
                    QMessageBox.critical(self, "Error", "Failed to report damage.")

            dialog.deleteLater()

        except Exception as e:
            logger.error(f"Error reporting damage for batch {batch_id}: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
    
    def _make_item(self, text, font, alignment=Qt.AlignLeft | Qt.AlignVCenter):
        item = QTableWidgetItem(text)
        item.setFont(font)
        item.setTextAlignment(alignment)
        return item
    
    def is_user_admin(self):
        ret = False
        if not self.current_user:
            ret = False
        elif isinstance(self.current_user, dict):
            ret = self.current_user.get('is_admin', False) or self.current_user.get('role') == 'admin'
        elif hasattr(self.current_user, 'is_admin'):
            ret = self.current_user.is_admin
        elif hasattr(self.current_user, 'role'):
            ret = self.current_user.role == 'admin'
        return ret