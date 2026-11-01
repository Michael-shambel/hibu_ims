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
from ui.components import theme
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
        info_frame.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {theme.CANVAS}; border: 1px solid {theme.BORDER};"
            f"  border-radius: 8px; padding: 10px;"
            f"}}"
        )
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
        theme.style_outline(cancel_btn, theme.SLATE)
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("Report Damage")
        theme.style_filled(save_btn, theme.DANGER, theme.DANGER_DARK)
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
        info.setStyleSheet(
            f"background-color: {theme.SELECTION}; color: {theme.TEXT}; "
            f"padding: 10px; border-radius: 8px;"
        )
        layout.addWidget(info)

        # Batch fields
        batch_frame = QFrame()
        batch_frame.setStyleSheet(
            f"background-color: {theme.CANVAS}; border: 1px solid {theme.BORDER}; "
            f"border-radius: 8px; padding: 10px;"
        )
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
            purchase_frame.setStyleSheet(
                f"background-color: {theme.CANVAS}; border: 1px solid {theme.BORDER}; "
                f"border-radius: 8px; padding: 10px;"
            )
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
        theme.style_outline(cancel_btn, theme.SLATE)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Changes")
        theme.style_filled(save_btn, theme.PRIMARY, theme.PRIMARY_DARK)
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
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(16)

        # ==================== HEADER ====================
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        self.title_label = QLabel(self.product_data["name"])
        self.title_label.setFont(QFont(theme.FONT, 15, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {theme.TEXT};")

        unit = self.product_data.get("unit")
        subtitle_text = "Product details and batch history"
        if unit:
            subtitle_text = f"Unit: {unit}   •   {subtitle_text}"

        subtitle = QLabel(subtitle_text)
        subtitle.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")

        title_box.addWidget(self.title_label)
        title_box.addWidget(subtitle)

        header_layout.addLayout(title_box)
        header_layout.addStretch()
        main_layout.addWidget(header)

        # ==================== KPI CARDS ====================
        main_layout.addLayout(self.create_info_cards())

        # ==================== BATCH CARD ====================
        batch_card = theme.card_frame()
        batch_layout = QVBoxLayout(batch_card)
        batch_layout.setContentsMargins(0, 0, 0, 6)
        batch_layout.setSpacing(0)

        batch_header, self.batch_count_label = theme.card_section_header(
            "Batch Information", "0 batches"
        )

        self.batch_table = self.create_batch_table()
        batch_layout.addWidget(batch_header)
        batch_layout.addWidget(self.batch_table)

        main_layout.addWidget(batch_card, 1)

        # ==================== FOOTER ====================
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.close_button = QPushButton("Close")
        self.close_button.setMinimumWidth(120)
        theme.style_filled(self.close_button, theme.SLATE, theme.SLATE_DARK)
        self.close_button.clicked.connect(self.accept)

        button_layout.addStretch()
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)
    def create_info_cards(self):
        """Four KPI cards mirroring the product list page."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        try:
            price = float(self.product_data.get("price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            stock = int(self.product_data.get("stock") or 0)
        except (TypeError, ValueError):
            stock = 0

        self.card_price = theme.StatCard("Unit Price", f"${price:,.2f}", theme.PRIMARY, "💵")
        self.lbl_price = self.card_price.value_label

        self.card_stock = theme.StatCard("Available Stock", f"{stock:,}", theme.SUCCESS, "📦")
        self.lbl_stock = self.card_stock.value_label

        self.card_total = theme.StatCard(
            "Total Stock",
            theme.format_number(self.product_data.get("total_quantity") or 0),
            theme.PURPLE,
            "🧮",
        )
        self.lbl_total = self.card_total.value_label

        self.card_batches = theme.StatCard(
            "Batches", str(self.product_data.get("total_batches") or 0), theme.SLATE, "🗂️"
        )
        self.lbl_batches = self.card_batches.value_label

        for card in (self.card_price, self.card_stock, self.card_total, self.card_batches):
            row.addWidget(card)

        self.apply_stock_tone(stock)
        return row

    def apply_stock_tone(self, stock):
        """Colour the available-stock card by stock level."""
        self.card_stock.set_color(theme.stock_color(stock))
    def create_batch_table(self):
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "PURCHASE DATE", "SUPPLIER", "QUANTITY", "AVAILABLE", "COST PRICE", "ACTIONS"
        ])

        header = theme.style_table(table)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        table.setColumnWidth(0, 170)
        table.setColumnWidth(2, 110)
        table.setColumnWidth(3, 130)
        table.setColumnWidth(4, 130)
        table.setColumnWidth(5, 322)

        theme.align_header(table, 4, Qt.AlignRight | Qt.AlignVCenter)
        theme.align_header(table, 5, Qt.AlignCenter)

        return table
    def load_batch_details(self):
        try:
            batch_info = self.new_product_service.get_batches_with_product(self.product_id)

            self.batch_table.setRowCount(0)

            if not batch_info:
                self.batch_count_label.setText("0 batches")
                self.show_empty_batches()
                return

            for batch in reversed(list(batch_info)):
                self.add_batch_row(batch)

            self.batch_count_label.setText(f"{self.batch_table.rowCount()} batches")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load batch details:\n{e}")

    def show_empty_batches(self):
        """Placeholder row shown when the product has no batches yet."""
        self.batch_table.setRowCount(1)

        item = QTableWidgetItem("No batches recorded for this product yet")
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor(theme.MUTED))
        item.setFont(QFont(theme.FONT, 10))

        self.batch_table.setItem(0, 0, item)
        self.batch_table.setSpan(0, 0, 1, self.batch_table.columnCount())
        self.batch_table.setRowHeight(0, 60)
    def add_batch_row(self, batch):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)

        purchase_date = batch.purchase.purchase_date if batch.purchase else None
        if purchase_date:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(purchase_date)
            date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
        else:
            date_str = "N/A"

        supplier_name = (
            batch.purchase.supplier.supplier_name
            if batch.purchase and batch.purchase.supplier else "N/A"
        )

        date_item = QTableWidgetItem(date_str)
        date_item.setForeground(QColor(theme.TEXT))
        self.batch_table.setItem(row, 0, date_item)

        supplier_item = QTableWidgetItem(str(supplier_name))
        supplier_item.setFont(QFont(theme.FONT, 10, QFont.DemiBold))
        supplier_item.setForeground(QColor(theme.TEXT))
        supplier_item.setToolTip(str(supplier_name))
        self.batch_table.setItem(row, 1, supplier_item)

        qty_item = QTableWidgetItem(theme.format_number(batch.quantity))
        qty_item.setTextAlignment(Qt.AlignCenter)
        qty_item.setForeground(QColor(theme.MUTED))
        self.batch_table.setItem(row, 2, qty_item)

        self.batch_table.setCellWidget(row, 3, theme.stock_badge(batch.available_quantity))

        try:
            cost_value = float(batch.cost_price or 0)
        except (TypeError, ValueError):
            cost_value = 0.0

        cost_item = QTableWidgetItem(f"${cost_value:,.2f}")
        cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cost_item.setFont(QFont(theme.FONT, 10, QFont.DemiBold))
        cost_item.setForeground(QColor(theme.TEXT))
        self.batch_table.setItem(row, 4, cost_item)

        self.batch_table.setCellWidget(row, 5, self.create_batch_action_buttons(batch.id))

        self.batch_table.setRowHeight(row, theme.ROW_HEIGHT)
    def create_batch_action_buttons(self, batch_id):
        view_btn = theme.action_button("View", "View batch transaction history", theme.PRIMARY, 50)
        view_btn.clicked.connect(lambda checked=False, bid=batch_id: self.view_batch_details(bid))

        edit_btn = theme.action_button("Edit", "Edit batch and purchase", theme.WARNING, 46)

        damage_btn = theme.action_button("Damage", "Report damaged stock", theme.ORANGE, 62)
        damage_btn.clicked.connect(lambda checked=False, bid=batch_id: self.report_damage(bid))

        discount_btn = theme.action_button(
            "Discount", "Apply a discount to the remaining quantity", theme.PURPLE, 68
        )
        discount_btn.clicked.connect(lambda checked=False, bid=batch_id: self.apply_discount(bid))

        delete_btn = theme.action_button("Delete", "Delete batch", theme.DANGER, 56)

        if self.is_user_admin():
            edit_btn.clicked.connect(lambda checked=False, bid=batch_id: self.edit_batch(bid))
            delete_btn.clicked.connect(lambda checked=False, bid=batch_id: self.delete_batch(bid))
        else:
            edit_btn.setEnabled(False)
            edit_btn.setToolTip("Edit batch — admin access required")
            delete_btn.setEnabled(False)
            delete_btn.setToolTip("Delete batch — admin access required")

        return theme.action_cell([view_btn, edit_btn, damage_btn, discount_btn, delete_btn])
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
        """Reload product data and update the KPI cards."""
        product = self.new_product_service.get_by_id(self.product_id)
        if not product:
            return

        batch_count = self.product_batch_service.count_by_product(product.id)
        self.product_data = {
            "id": product.id,
            "name": product.name,
            "stock": product.available_quantity,
            "total_quantity": product.total_quantity,
            "price": product.selling_price,
            "unit": product.unit,
            "total_batches": batch_count,
        }

        try:
            price = float(self.product_data.get("price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0

        try:
            stock = int(self.product_data.get("stock") or 0)
        except (TypeError, ValueError):
            stock = 0

        self.lbl_price.setText(f"${price:,.2f}")
        self.lbl_stock.setText(f"{stock:,}")
        self.lbl_total.setText(theme.format_number(self.product_data.get("total_quantity") or 0))
        self.lbl_batches.setText(str(batch_count))
        self.apply_stock_tone(stock)
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