#!/usr/bin/env python3
"""
Product Form Dialog for adding/editing products
Modern Professional Design - FIXED VERSION with Accessibility Enhancements
delete_product_line
"""
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QScrollArea,
    QFrame, QFormLayout, QLineEdit, QSpinBox, QComboBox, QTextEdit,
    QDoubleSpinBox, QDateEdit, QLabel, QMessageBox, QGroupBox, QCheckBox,
    QSizePolicy, QTableWidget, QHeaderView, QTableWidgetItem, QApplication
)
from PySide6.QtCore import Qt, QDate, Signal, QTimer, QLocale
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem
from services.supplier_service import SupplierService
from ui.components.universal_crud_dialog import UniversalCRUDDialog
from ui.components.ethiopian_date import EthiopianDateEdit, EthiopianDateConverter
from models.purchase_payment_term import PaymentStatusEnum
from models.purchase_payment_transaction import PaymentMethodEnum
from services.bank_account_service import BankAccountService
from services.purchase_service import PurchaseService
from datetime import datetime
from telegrambot.bot import notify_store_team_sync
from telegrambot.bot import notify_supplier_purchase_sync

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import QCompleter

class ShipmentProductCompleter(QCompleter):
    """
    Completer for shipment contexts: shows supplier_sku if present,
    and includes that in the suggestion text.
    """
    productSelected = Signal(int)

    def __init__(self, product_service, parent=None):
        super().__init__(parent)
        self.product_service = product_service
        self.model = QStandardItemModel()
        self.setModel(self.model)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterMode(Qt.MatchContains)
        self.setCompletionRole(Qt.UserRole)
        self.setMaxVisibleItems(10)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fetch_suggestions)

        self.line_edit = None
        self.suggestion_data = {}

        self.popup().clicked.connect(self.on_item_clicked)

    def setLineEdit(self, line_edit):
        self.line_edit = line_edit
        line_edit.setCompleter(self)

    def update(self, text):
        self.setCompletionPrefix(text)
        self.timer.start(300)

    def fetch_suggestions(self):
        text = self.completionPrefix()
        if len(text) < 2:
            self.model.clear()
            self.popup().hide()
            return

        # Search with supplier_sku included
        suggestions = self.product_service.search_products(
            text, limit=10, include_supplier_sku=True
        )
        self.model.clear()

        for s in suggestions:
            # Build display text: show supplier_sku if present
            if s.get('supplier_sku'):
                display_text = f"{s['supplier_sku']} – {s['name']} ({s['unit']})"
            else:
                display_text = f"{s['name']} ({s['unit']})"

            item = QStandardItem(display_text)
            item.setData(s, Qt.UserRole)
            self.model.appendRow(item)

        if suggestions:
            if self.line_edit:
                self.popup().setModel(self.model)
                rect = self.line_edit.rect()
                bottom_left = self.line_edit.mapToGlobal(rect.bottomLeft())
                popup_height = min(150, len(suggestions) * 25)
                self.popup().setGeometry(bottom_left.x(), bottom_left.y(),
                                          self.line_edit.width(), popup_height)
                self.popup().show()
                self.popup().raise_()
        else:
            self.popup().hide()

    def on_item_clicked(self, index):
        if not index.isValid():
            return
        item_data = index.data(Qt.UserRole)
        if not item_data:
            return

        # Set the line edit text to the product name
        self.line_edit.setText(item_data['name'])
        # Emit signal with product id
        self.productSelected.emit(item_data['id'])

class ProductCompleter(QCompleter):
    productSelected = Signal(int)

    def __init__(self, product_service, parent=None):
        super().__init__(parent)
        self.product_service = product_service
        self.model = QStandardItemModel()
        self.setModel(self.model)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterMode(Qt.MatchContains)
        self.setCompletionRole(Qt.UserRole)
        self.setMaxVisibleItems(10)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fetch_suggestions)

        self.line_edit = None
        self.suggestion_data = {}

        self.popup().clicked.connect(self.on_item_clicked)

    def setLineEdit(self, line_edit):
        self.line_edit = line_edit
        line_edit.setCompleter(self)

    def update(self, text):
        self.setCompletionPrefix(text)
        self.timer.start(300)

    def fetch_suggestions(self):
        text = self.completionPrefix()
        if len(text) < 2:
            self.model.clear()
            self.popup().hide()
            return

        suggestions = self.product_service.search_products(text, limit=10)
        self.model.clear()

        for s in suggestions:
            display_text = f"{s['name']} ({s['unit']})"

            item = QStandardItem(display_text)
            item.setData(s, Qt.UserRole)

            self.model.appendRow(item)

        if suggestions:
            if self.line_edit:
                self.popup().setModel(self.model)
                rect = self.line_edit.rect()
                bottom_left = self.line_edit.mapToGlobal(rect.bottomLeft())
                popup_height = min(150, len(suggestions) * 25)
                self.popup().setGeometry(bottom_left.x(), bottom_left.y(),
                                        self.line_edit.width(), popup_height)
                self.popup().show()
                self.popup().raise_()
        else:
            self.popup().hide()
    
    def on_item_clicked(self, index):
        """Handle selection from popup (SAFE & CORRECT)"""
        if not index.isValid():
            print("❌ Invalid index")
            return

        item_data = index.data(Qt.UserRole)

        if not item_data:
            print("❌ No data found in item")
            return

       
        self.line_edit.setText(item_data['name']) # type: ignore

        self.productSelected.emit(item_data['id'])

        print("✅ Selected:", item_data['name'])
    
    def closeEvent(self, event):
        # Stop the completer's timer if it exists
        if hasattr(self, 'completer'):
            self.completer.timer.stop()
            self.completer.model().clear()
        # Optionally, stop any other timers (none in this dialog except maybe singleShot, which is fine)
        super().closeEvent(event)


class ModernInput(QWidget):
    """Modern input widget with floating label"""
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.title = title
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # Title label - larger bold font
        self.title_label = QLabel(self.title)
        title_font = QFont("Segoe UI", 13, QFont.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 13px;
                font-weight: bold;
                padding-left: 5px;
            }
        """)
        layout.addWidget(self.title_label)
        
        # Container for input
        self.input_container = QFrame()
        self.input_container.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 2px;
            }
        """)
        
        container_layout = QHBoxLayout(self.input_container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        
        layout.addWidget(self.input_container)


class ModernLineEdit(ModernInput):
    """Modern line edit with floating label"""
    textChanged = Signal(str)
    
    def __init__(self, title="", placeholder="", parent=None):
        super().__init__(title, parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.placeholder = placeholder
        self.create_input_widget()
        self.setup_styles()
        
    def create_input_widget(self):
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(self.placeholder)
        # Larger bold font for input
        input_font = QFont("Segoe UI", 14, QFont.Bold)
        self.line_edit.setFont(input_font)
        self.line_edit.setStyleSheet("""
            QLineEdit {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                selection-background-color: #3498db;
                selection-color: white;
            }
            QLineEdit:focus {
                border: none;
            }
        """)
        self.input_container.layout().addWidget(self.line_edit)
        self.line_edit.textChanged.connect(self._on_text_changed)
        
    def setup_styles(self):
        # Store original methods
        self.line_edit._focusInEvent = self.line_edit.focusInEvent
        self.line_edit._focusOutEvent = self.line_edit.focusOutEvent
        
        # Override focus methods
        self.line_edit.focusInEvent = self._focus_in_event
        self.line_edit.focusOutEvent = self._focus_out_event
        
    def _focus_in_event(self, event):
        self.input_container.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #3498db;
                border-radius: 10px;
                padding: 2px;
            }
        """)
        self.title_label.setStyleSheet("""
            QLabel {
                color: #3498db;
                font-size: 13px;
                font-weight: bold;
                padding-left: 5px;
            }
        """)
        self.line_edit._focusInEvent(event)
        
    def _focus_out_event(self, event):
        if not self.line_edit.text():
            self.input_container.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border: 2px solid #e0e0e0;
                    border-radius: 10px;
                    padding: 2px;
                }
            """)
            self.title_label.setStyleSheet("""
                QLabel {
                    color: #7f8c8d;
                    font-size: 13px;
                    font-weight: bold;
                    padding-left: 5px;
                }
            """)
        self.line_edit._focusOutEvent(event)
        
    def _on_text_changed(self, text):
        self.textChanged.emit(text)
        
    def text(self):
        return self.line_edit.text()
    
    def setText(self, text):
        self.line_edit.setText(text)


class ModernSpinBox(ModernInput):
    """Modern spin box with floating label"""
    valueChanged = Signal(int)
    
    def __init__(self, title="", min_val=0, max_val=1000000, parent=None):
        super().__init__(title, parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.create_input_widget(min_val, max_val)
        
    def create_input_widget(self, min_val, max_val):
        self.spin_box = QSpinBox()
        locale = QLocale(QLocale.English, QLocale.UnitedStates)
        locale.setNumberOptions(QLocale.DefaultNumberOptions)
        self.spin_box.setLocale(locale)
        self.spin_box.setGroupSeparatorShown(True)

        self.spin_box.setRange(min_val, max_val)
        self.spin_box.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_box.setSpecialValueText(" ")
        # Larger bold font
        spin_font = QFont("Segoe UI", 14, QFont.Bold)
        self.spin_box.setFont(spin_font)
        self.spin_box.setStyleSheet("""
            QSpinBox {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 0;
            }
            QSpinBox:focus {
                border: none;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 0;
            }
        """)
        self.input_container.layout().addWidget(self.spin_box)
        
        # Add custom buttons
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(2)
        
        up_btn = QPushButton("▲")
        up_btn.setFixedSize(30, 25)
        up_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                color: #7f8c8d;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3498db;
                color: white;
            }
        """)
        up_btn.clicked.connect(lambda: self.spin_box.setValue(self.spin_box.value() + 1))
        
        down_btn = QPushButton("▼")
        down_btn.setFixedSize(30, 25)
        down_btn.setStyleSheet(up_btn.styleSheet())
        down_btn.clicked.connect(lambda: self.spin_box.setValue(self.spin_box.value() - 1))
        
        button_layout.addWidget(up_btn)
        button_layout.addWidget(down_btn)
        
        self.input_container.layout().addWidget(button_container)
        self.spin_box.valueChanged.connect(self._on_value_changed)
        
    def _on_value_changed(self, value):
        self.valueChanged.emit(value)
        
    def value(self):
        return self.spin_box.value()
    
    def setValue(self, value):
        self.spin_box.setValue(value)

class SelectAllLineEdit(QLineEdit):
    """Line edit that selects all text when clicked."""
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        QTimer.singleShot(0, self.selectAll)
class ModernDoubleSpinBox(ModernInput):
    """Modern double spin box with floating labelc  self.mode """
    valueChanged = Signal(float)
    
    def __init__(self, title="", min_val=0.0, max_val=10000000.0, decimals=2, prefix="", parent=None):
        super().__init__(title, parent)
        self.create_input_widget(min_val, max_val, decimals, prefix)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        
    def create_input_widget(self, min_val, max_val, decimals, prefix):
        self.spin_box = QDoubleSpinBox()
        locale = QLocale(QLocale.English, QLocale.UnitedStates)
        locale.setNumberOptions(QLocale.DefaultNumberOptions)

        self.spin_box.setLocale(locale)
        self.spin_box.setGroupSeparatorShown(True)
        self.spin_box.setRange(min_val, max_val)
        self.spin_box.setDecimals(decimals)
        self.spin_box.setPrefix(prefix + " ")
        self.spin_box.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.spin_box.setSpecialValueText(" ")
        # Larger bold font
        spin_font = QFont("Segoe UI", 14, QFont.Bold)
        self.spin_box.setFont(spin_font)
        self.spin_box.setStyleSheet("""
            QDoubleSpinBox {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 0;
            }
            QDoubleSpinBox:focus {
                border: none;
            }
        """)
        self.input_container.layout().addWidget(self.spin_box)
        self.spin_box.valueChanged.connect(self._on_value_changed)
        
    def _on_value_changed(self, value):
        self.valueChanged.emit(value)
        
    def value(self):
        return self.spin_box.value()
    
    def setValue(self, value):
        self.spin_box.setValue(value)


class ModernComboBox(ModernInput):
    """Modern combo box with floating label  adjust_ui_for_mode $ """
    currentIndexChanged = Signal(int)
    
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.create_input_widget()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        
    def create_input_widget(self):
        self.combo_box = QComboBox()
        self.combo_box.setEditable(True)
        self.combo_box.setLineEdit(SelectAllLineEdit())
        # Larger bold font
        combo_font = QFont("Segoe UI", 14, QFont.Bold)
        self.combo_box.setFont(combo_font)
        self.combo_box.setStyleSheet("""
            QComboBox {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 0;
                padding-right: 85px;    /* make room for the bigger drop‑down button */
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 80px;
                border: none;
                background-color: #3498db;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                margin: 2px;
            }
            QComboBox::drop-down:hover {
                background-color: #2980b9;
            }
            QComboBox::down-arrow {
                image: none;               /* remove the old tiny triangle */
                width: 80px;
                height: 20px;
                background: transparent;
            }
            /* Redraw the arrow as a centred white down‑triangle */
            QComboBox::down-arrow:after {
                content: "";
                width: 0;
                height: 0;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
                border-top: 8px solid white;
                margin: auto;
            }
            QComboBox QAbstractItemView {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
                selection-background-color: #3498db;
                selection-color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
            }
        """)
        self.input_container.layout().addWidget(self.combo_box)
        self.combo_box.currentIndexChanged.connect(self._on_index_changed)
        
    def _on_index_changed(self, index):
        self.currentIndexChanged.emit(index)
        
    def addItem(self, text, data=None):
        if data:
            self.combo_box.addItem(text, data)
        else:
            self.combo_box.addItem(text)
    
    def currentIndex(self):
        return self.combo_box.currentIndex()
    
    def setCurrentIndex(self, index):
        self.combo_box.setCurrentIndex(index)
    
    def currentData(self):
        return self.combo_box.currentData()
    
    def itemData(self, index):
        return self.combo_box.itemData(index)
    
    def findData(self, data):
        return self.combo_box.findData(data)
    
    def clear(self):
        self.combo_box.clear()


class ModernTextEdit(ModernInput):
    """Modern text edit with floating label"""
    textChanged = Signal()
    
    def __init__(self, title="", placeholder="", parent=None):
        super().__init__(title, parent)
        self.placeholder = placeholder
        self.create_input_widget()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
    def create_input_widget(self):
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(self.placeholder)
        self.text_edit.setMaximumHeight(100)
        # Larger bold font
        edit_font = QFont("Segoe UI", 14, QFont.Bold)
        self.text_edit.setFont(edit_font)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
            }
            QTextEdit:focus {
                border: none;
            }
        """)
        self.input_container.layout().addWidget(self.text_edit)
        self.text_edit.textChanged.connect(self._on_text_changed)
        
    def _on_text_changed(self):
        self.textChanged.emit()
        
    def toPlainText(self):
        return self.text_edit.toPlainText()
    
    def setPlainText(self, text):
        self.text_edit.setPlainText(text)


class ModernDateEdit(ModernInput):
    """Modern date edit with floating label"""
    dateChanged = Signal(QDate)
    
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.create_input_widget()
        
    def create_input_widget(self):
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate().addDays(30))
        # Larger bold font
        date_font = QFont("Segoe UI", 14, QFont.Bold)
        self.date_edit.setFont(date_font)
        self.date_edit.setStyleSheet("""
            QDateEdit {
                border: none;
                background: transparent;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 0;
            }
            QDateEdit::drop-down {
                border: none;
                width: 30px;
            }
            QDateEdit::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #7f8c8d;
                width: 0;
                height: 0;
                margin-right: 10px;
            }
        """)
        self.input_container.layout().addWidget(self.date_edit)
        self.date_edit.dateChanged.connect(self._on_date_changed)
        
    def _on_date_changed(self, date):
        self.dateChanged.emit(date)
    
    def setDate(self, date):
        self.date_edit.setDate(date)
    
    def date(self):
        """Return Python date object"""
        qdate = self.date_edit.date()
        return qdate.toPython()


class PurchaseDetailsDialog(QDialog):
    """Standalone dialog for supplier, payment status, bank account, and date."""
    def __init__(self, supplier_service, bank_account_service, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Purchase Details")
        self.supplier_service = supplier_service
        self.bank_account_service = bank_account_service
        self.setMinimumWidth(500)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._details = None

        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # --- Supplier section ---
        supplier_group = QGroupBox("Supplier")
        supplier_layout = QHBoxLayout(supplier_group)
        self.supplier_combo = ModernComboBox("Supplier")
        self.add_supplier_btn = QPushButton("+")
        self.add_supplier_btn.setFixedSize(45, 45)
        self.add_supplier_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white;
                border: none; border-radius: 8px; font-weight: bold; font-size: 18px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.add_supplier_btn.clicked.connect(self._open_supplier_dialog)
        supplier_layout.addWidget(self.supplier_combo, 1)
        supplier_layout.addWidget(self.add_supplier_btn)
        layout.addWidget(supplier_group)

        # --- Payment section ---
        payment_group = QGroupBox("Payment")
        payment_form = QFormLayout(payment_group)

        self.payment_status_combo = QComboBox()
        self.payment_status_combo.addItem(PaymentStatusEnum.CREDIT.value.capitalize(), PaymentStatusEnum.CREDIT.value)
        self.payment_status_combo.addItem(PaymentStatusEnum.PAID.value.capitalize(), PaymentStatusEnum.PAID.value)
        self.payment_status_combo.currentIndexChanged.connect(self._on_status_changed)

        self.bank_account_combo = ModernComboBox("Bank Account")
        self.bank_account_combo.setEnabled(True)  # will be hidden/shown instead

        # Container for bank account row (label + combo)
        self.bank_account_widget = QWidget()
        ba_layout = QHBoxLayout(self.bank_account_widget)
        ba_layout.setContentsMargins(0, 0, 0, 0)
        ba_layout.addWidget(QLabel("Bank Account:"))
        ba_layout.addWidget(self.bank_account_combo)

        self.payment_date = EthiopianDateEdit()
        self.payment_date.setDate(QDate.currentDate())

        payment_form.addRow("Status:", self.payment_status_combo)
        payment_form.addRow(self.bank_account_widget)  # add the whole widget (label + combo) in one row
        payment_form.addRow("Date:", self.payment_date)

        layout.addWidget(payment_group)

        # Load data
        self._load_suppliers()
        self._load_bank_accounts()

        # Dialog buttons
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

        # Initial visibility based on default status (CREDIT)
        self._on_status_changed(0)

    def _load_suppliers(self):
        current_id = self.supplier_combo.currentData()

        suppliers = self.supplier_service.get_all()
        self.supplier_combo.clear()
        self.supplier_combo.addItem("Select Supplier", None)
        for s in suppliers:
            self.supplier_combo.addItem(s.supplier_name, s.id)

        if current_id is not None:
            idx = self.supplier_combo.findData(current_id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)
                # Set up completer and return
                line_edit = self.supplier_combo.combo_box.lineEdit()
                if line_edit:
                    completer = QCompleter(self.supplier_combo.combo_box.model())
                    completer.setCaseSensitivity(Qt.CaseInsensitive)
                    completer.setFilterMode(Qt.MatchContains)
                    line_edit.setCompleter(completer)
                return

        if self.supplier_combo.combo_box.count() > 9:   # <--- FIXED
            self.supplier_combo.setCurrentIndex(9)

        # Set up the search completer
        line_edit = self.supplier_combo.combo_box.lineEdit()
        if line_edit:
            completer = QCompleter(self.supplier_combo.combo_box.model())
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            line_edit.setCompleter(completer)

    def _load_bank_accounts(self):
        self.bank_account_combo.clear()
        self.bank_account_combo.addItem("Select Bank Account", None)
        accounts = self.bank_account_service.get_all()
        for acc in accounts:
            display = f"{acc.account_name} - {acc.bank_name} ({acc.account_number})"
            self.bank_account_combo.addItem(display, acc.id)

    def _on_status_changed(self, idx):
        """Show bank account only when PAID, hide when CREDIT."""
        is_paid = self.payment_status_combo.currentData() == PaymentStatusEnum.PAID.value
        self.bank_account_widget.setVisible(is_paid)

    def _open_supplier_dialog(self):
        dialog = UniversalCRUDDialog('supplier', SupplierService, self)
        dialog.exec()
        self._load_suppliers()

    def accept(self):
        if self.supplier_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select a supplier.")
            return
        self._details = {
            "supplier_id": self.supplier_combo.currentData(),
            "payment_status": self.payment_status_combo.currentData(),
            "bank_account_id": self.bank_account_combo.currentData() if self.payment_status_combo.currentData() == PaymentStatusEnum.PAID.value else None,
            "payment_date": self.payment_date.date().toPython(),
        }
        super().accept()

    def get_details(self):
        return self._details


class ProductFormDialog(QDialog):
    product_saved = Signal(object)
    
    def __init__(self, product_service, supplier_service, 
                 product=None, current_user=None, parent=None, mode="new_product"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.product_service = product_service
        self.supplier_service = supplier_service
        self.bank_account_service = BankAccountService()
        self.purchase_service = PurchaseService()
        self.product = product
        self.current_user = current_user
        self.mode = mode

        if mode == "add_batch" and product:
            title = f"Add Batch to: {product.name}"
        elif mode == "edit_product" and product:
            title = f"Edit Product: {product.name}"
        else:
            title = "Add New Product"
        
        self.product_lines = []
        self.purchase_details = None
        self.setWindowTitle(title)
        
        screen = QApplication.primaryScreen().availableGeometry()
        desired_width = min(int(screen.width() * 0.7), 1500)
        desired_width = max(desired_width, 1100)
        desired_height = min(int(screen.height() * 0.8), 800)
        desired_height = max(desired_height, 500)
        self.resize(desired_width, desired_height)

        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self._ignore_text_change = False
        
        self.init_ui()
        self.setMinimumSize(800, 550)
        self.update_button_states()
        self.load_dropdown_data()
        
        if mode == "edit_product" and product:
            QTimer.singleShot(100, self.load_product_data)
        elif mode == "add_batch" and product:
            self.setup_for_batch_mode()
        elif mode == "stock_in":
            self.setup_for_stock_in()
        elif mode == "credit_stock":
            self.setup_for_credit_stock()
        else:
            self.setup_for_purchase_entry()
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            self.setGeometry(screen_geometry)
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== FORM CONTENT ====================
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #f8f9fa;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)

        form_container = QWidget()
        form_container.setStyleSheet("background-color: #f8f9fa;")

        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(30, 30, 30, 30)
        form_layout.setSpacing(25)

        # # ========== PURCHASE DETAILS BUTTON (opens dialog) ==========
        # details_btn_layout = QHBoxLayout()
        # details_btn_layout.setContentsMargins(0, 0, 0, 10)
        # self.purchase_details_btn = QPushButton("📋 Set Purchase Details (Supplier, Payment)")
        # self.purchase_details_btn.setMinimumHeight(45)
        # self.purchase_details_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        # self.purchase_details_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color: #3498db; color: white;
        #         border: none; border-radius: 8px; padding: 10px;
        #     }
        #     QPushButton:hover { background-color: #2980b9; }
        # """)
        # self.purchase_details_btn.clicked.connect(self.open_purchase_details_dialog)
        # details_btn_layout.addWidget(self.purchase_details_btn, 1)
        # form_layout.addLayout(details_btn_layout)

        # ========== TWO-COLUMN ROW CONTAINER ==========
        two_column_widget = QWidget()
        two_column_layout = QHBoxLayout(two_column_widget)
        two_column_layout.setContentsMargins(0, 0, 0, 0)
        two_column_layout.setSpacing(20)

        # LEFT COLUMN – now only the product table + summary
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)  # no extra spacing

        # ========== PURCHASE DETAILS BUTTON (inside left column) ==========
        details_btn_layout = QHBoxLayout()
        details_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.purchase_details_btn = QPushButton("📋 Set Purchase Details (Supplier, Payment)")
        self.purchase_details_btn.setMinimumHeight(20)
        self.purchase_details_btn.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.purchase_details_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white;
                border: none; border-radius: 4px; padding: 10px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.purchase_details_btn.clicked.connect(self.open_purchase_details_dialog)
        details_btn_layout.addWidget(self.purchase_details_btn)
        left_layout.addLayout(details_btn_layout)

        # ========== TABLE SECTION (will stretch vertically) ==========
        self.table_section = QWidget()
        self.table_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # FIX 1: allow vertical stretch
        self.table_section.setStyleSheet("""
            QWidget {
                background-color: #eef2f6;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
            }
        """)

        table_layout = QVBoxLayout(self.table_section)
        table_layout.setContentsMargins(20, 20, 20, 20)
        table_layout.setSpacing(15)

        self.products_table = QTableWidget()
        self.products_table.verticalHeader().setVisible(True)
        self.products_table.setColumnCount(6)
        self.products_table.setHorizontalHeaderLabels([
            "Product", "Qty", "Dozen", "Cost Price", "Total", "Actions"
        ])
        header = self.products_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)   # Product name expands
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)

        # Set reasonable fixed widths for number columns and actions
        self.products_table.setColumnWidth(1, 70)    # Qty
        self.products_table.setColumnWidth(2, 80)    # Dozen
        self.products_table.setColumnWidth(3, 110)   # Cost Price
        self.products_table.setColumnWidth(4, 130)   # Total
        self.products_table.setColumnWidth(5, 60)    # Actions

        table_font = QFont()
        table_font.setPointSize(14)
        table_font.setBold(True)
        self.products_table.setFont(table_font)
        self.products_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QHeaderView::section {
                background-color: #f1f3f4;
                padding: 8px;
                border: none;
                font-weight: bold;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        self.products_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.products_table.setAlternatingRowColors(True)
        # self.products_table.verticalHeader().setVisible(True)
        self.products_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.products_table.setMinimumHeight(200)
        self.products_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.products_table.verticalHeader().setDefaultSectionSize(55)

        table_layout.addWidget(self.products_table, 1)  # give table a stretch factor inside its own layout

        # ========== SUMMARY ROW ==========
        self.summary_row = QWidget()
        self.summary_row.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-top: 1px solid #e0e0e0;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        summary_layout = QHBoxLayout(self.summary_row)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(10)

        summary_font = QFont("Segoe UI", 13, QFont.Bold)

        total_label_col1 = QLabel("Total")
        total_label_col1.setFont(summary_font)
        total_label_col1.setAlignment(Qt.AlignLeft)
        summary_layout.addWidget(total_label_col1, 1)

        self.summary_qty = QLabel("0")
        self.summary_qty.setFont(summary_font)
        self.summary_qty.setAlignment(Qt.AlignRight)
        self.summary_qty.setStyleSheet("color: #27ae60;")
        summary_layout.addWidget(self.summary_qty, 1)

        self.summary_amount = QLabel("$ 0.00")
        self.summary_amount.setFont(summary_font)
        self.summary_amount.setAlignment(Qt.AlignRight)
        self.summary_amount.setStyleSheet("color: #e67e22;")
        summary_layout.addWidget(self.summary_amount, 1)

        empty_widget = QWidget()
        empty_widget.setFixedWidth(50)
        summary_layout.addWidget(empty_widget)

        table_layout.addWidget(self.summary_row)

        # left_layout: add the table section with a stretch factor of 1 (remove extra Stretch)
        left_layout.addWidget(self.table_section, 1)

        # RIGHT COLUMN – unchanged (product input fields)
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(25)

        product_section = QWidget()
        product_section.setStyleSheet("""
            QWidget {
                background-color: #eef2f6;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
            }
        """)

        product_form = QFormLayout(product_section)
        product_form.setContentsMargins(20, 20, 20, 20)
        product_form.setSpacing(20)
        product_form.setLabelAlignment(Qt.AlignRight)

        label_font = QFont("Segoe UI", 14, QFont.Bold)

        name_label = QLabel("Name:")
        name_label.setFont(label_font)
        unit_label = QLabel("Unit:")
        unit_label.setFont(label_font)
        dozen_label = QLabel("Dozen:")
        dozen_label.setFont(label_font)
        qty_label = QLabel("Quantity:")
        qty_label.setFont(label_font)
        cost_label = QLabel("Cost Price:")
        cost_label.setFont(label_font)
        price_label = QLabel("Selling Price:")
        price_label.setFont(label_font)

        self.name_input = ModernLineEdit("Product Name", "Enter product name")
        self.unit_input = ModernLineEdit("Unit", "e.g., pcs, kg, L, box")
        self.dozen_input = ModernDoubleSpinBox("Dozen per Package", 0.01, 1000000.0, 2, "")
        self.quantity_input = ModernSpinBox("Quantity", 0, 1_000_000)
        self.cost_input = ModernDoubleSpinBox("Cost Price", 0.0, 1_000_000_000_000.0, 2, "")
        self.price_input = ModernDoubleSpinBox("Selling Price", 0.0, 1_000_000_000_000.0, 2, "")

        self.name_input.line_edit.installEventFilter(self)
        self.completer = ProductCompleter(self.product_service, parent=self)
        self.completer.setLineEdit(self.name_input.line_edit)
        self.completer.productSelected.connect(self.on_product_selected)
        self.name_input.textChanged.connect(self.completer.update)

        product_form.addRow(name_label, self.name_input)
        product_form.addRow(unit_label, self.unit_input)
        product_form.addRow(dozen_label, self.dozen_input)
        product_form.addRow(qty_label, self.quantity_input)
        product_form.addRow(cost_label, self.cost_input)
        product_form.addRow(price_label, self.price_input)

        right_layout.addWidget(product_section)
        right_layout.addStretch()

        two_column_layout.addWidget(left_column, 3)
        two_column_layout.addWidget(right_column, 2)

        form_layout.addWidget(two_column_widget)
        form_layout.addStretch()
        scroll_area.setWidget(form_container)
        main_layout.addWidget(scroll_area, 1)

        # ========== BOTTOM BUTTONS ==========
        button_widget = QWidget()
        button_widget.setFixedHeight(100)
        button_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #e0e0e0;
            }
        """)

        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(30, 20, 30, 20)
        button_layout.setSpacing(15)

        btn_font = QFont("Segoe UI", 13, QFont.Bold)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumSize(120, 50)
        self.cancel_btn.setFont(btn_font)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0; color: #2c3e50;
                border: none; border-radius: 8px; font-weight: bold;
                font-size: 13px; padding: 12px 24px;
            }
            QPushButton:hover { background-color: #d5d5d5; }
            QPushButton:pressed { background-color: #c8c8c8; }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.add_product_btn = QPushButton("➕ Add Product")
        self.add_product_btn.setMinimumSize(160, 50)
        self.add_product_btn.setFont(btn_font)
        self.add_product_btn.setCursor(Qt.PointingHandCursor)
        self.add_product_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498db, stop:1 #2980b9);
                color: white; border: none; border-radius: 8px;
                font-weight: bold; font-size: 13px; padding: 12px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2980b9, stop:1 #2471a3);
            }
        """)
        self.add_product_btn.clicked.connect(self.add_current_product)

        self.send_notifications_checkbox = QCheckBox("Send Notifications")
        self.send_notifications_checkbox.setChecked(True)
        self.send_notifications_checkbox.setToolTip("Uncheck to prevent sending order notification to supplier and store team")
        self.send_notifications_checkbox.setStyleSheet("""
            QCheckBox {
                padding: 4px 8px;
                border-radius: 4px;
                background-color: #ecf0f1;
                color: #2c3e50;
            }
            QCheckBox:checked {
                background-color: #27ae60;
                color: white;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.finish_btn = QPushButton("💾 Finish Purchase")
        self.finish_btn.setMinimumSize(200, 50)
        self.finish_btn.setFont(btn_font)
        self.finish_btn.setCursor(Qt.PointingHandCursor)
        self.finish_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2ecc71, stop:1 #27ae60);
                color: white; border: none; border-radius: 10px;
                font-weight: bold; font-size: 13px; padding: 14px 28px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #27ae60, stop:1 #219a52);
            }
        """)
        self.finish_btn.clicked.connect(self.finish_purchase)

        button_layout.addStretch()
        button_layout.addWidget(self.send_notifications_checkbox)   # new
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.add_product_btn)
       
        button_layout.addWidget(self.finish_btn)

        main_layout.addWidget(button_widget)

    def open_purchase_details_dialog(self):
        dialog = PurchaseDetailsDialog(self.supplier_service, self.bank_account_service, self)
        if dialog.exec() == QDialog.Accepted:
            self.purchase_details = dialog.get_details()

            # --- fetch supplier name ---
            supplier_id = self.purchase_details["supplier_id"]
            supplier = self.supplier_service.get_by_id(supplier_id)
            supplier_name = supplier.supplier_name if supplier else "???"

            # --- payment status ---
            status = self.purchase_details["payment_status"].capitalize()

            # --- Ethiopian date ---
            greg_date = self.purchase_details["payment_date"]
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_date)
            eth_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"

            # --- update button text ---
            display_text = f"✅ {supplier_name}  |  {status}  |  {eth_date_str}"
            self.purchase_details_btn.setText(display_text)

            # --- keep the same font & center alignment, only change background to green ---
            self.purchase_details_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 10px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
        else:
            pass
    def update_button_states(self):
        has_items = len(self.product_lines) > 0
        self.finish_btn.setEnabled(has_items)
        if has_items:
            self.finish_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2ecc71, stop:1 #27ae60);
                    color: white; border: none; border-radius: 10px;
                    font-weight: 600; font-size: 15px; padding: 14px 28px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #27ae60, stop:1 #219a52);
                }
            """)
        else:
            self.finish_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc; color: #666666;
                    border: none; border-radius: 10px;
                    font-weight: 600; font-size: 15px; padding: 14px 28px;
                }
            """)
    
    def on_product_selected(self, product_id):
        print("🔥 SIGNAL RECEIVED:", product_id)
        product = self.product_service.get_by_id(product_id)
        if not product:
            print("❌ Product not found")
            return
        print("✅ Filling form with:", product.name)

        self.unit_input.setText(product.unit or "")
        self.price_input.setValue(product.selling_price or 0.0)
        self.dozen_input.setValue(product.dozen or 1)
    
    def setup_for_credit_stock(self):
        self.purchase_details_btn.show()  # required for supplier
        self.table_section.show()
        self.summary_row.show()
        self.add_product_btn.show()
        self.finish_btn.setText("💾 Save Stock In")
        self.finish_btn.clicked.disconnect()
        self.finish_btn.clicked.connect(self.save_credit_stock_multiple)
        self.product_lines = []
        self.refresh_product_table()
        self.update_total()
        self.clear_product_fields()
    
    def save_credit_stock_multiple(self):
        if not self.product_lines:
            QMessageBox.warning(self, "Validation", "Add at least one product.")
            return
        # For credit stock we still need supplier; try to get from purchase_details
        supplier_id = self.purchase_details.get("supplier_id") if self.purchase_details else None
        if not supplier_id:
            QMessageBox.warning(self, "Validation", "Supplier is required. Please set purchase details.")
            return

        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        items = []
        for line in self.product_lines:
            items.append({
                "name": line["name"],
                "quantity": line["quantity"],
                "cost_price": line["cost_price"],
                "dozen": line["dozen"]
            })

        credit_stock_data = {
            "supplier_id": supplier_id,
            "purchase_date": None,
            "items": items,
            "user_id": user_id,
        }
        purchase = self.purchase_service.create_credit_purchase(credit_stock_data)
        if purchase:
            QMessageBox.information(self, "Success", "Credit purchase recorded successfully!")
            self.product_saved.emit(None)
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to record credit purchase.")

    # def setup_for_credit_stock(self):
    #     self.purchase_details_btn.show()  # required for supplier
    #     self.table_section.show()
    #     self.summary_row.show()
    #     self.add_product_btn.show()
    #     self.finish_btn.setText("💾 Save Stock In")
    #     self.finish_btn.clicked.disconnect()
    #     self.finish_btn.clicked.connect(self.save_credit_stock_multiple)
    #     self.product_lines = []
    #     self.refresh_product_table()
    #     self.update_total()
    #     self.clear_product_fields()
    

    def save_stock_in_multiple(self):
        """Save all products in the table as stock-in entries validate_current_product"""
        if not self.product_lines:
            QMessageBox.warning(self, "Validation", "Add at least one product.")
            return

        user_id = None
        if self.current_user:
            if isinstance(self.current_user, dict):
                user_id = self.current_user.get('id')
            else:
                user_id = getattr(self.current_user, 'id', None)

        success_count = 0
        failed_lines = []

        for idx, line in enumerate(self.product_lines):
            batch_data = {
                'quantity': line['quantity'],
                'cost_price': line['cost_price'],
            }
            success = self.product_service.add_stock_in(
                product_name=line['name'],
                unit=line['unit'],
                selling_price=line['selling_price'],
                dozen=line.get('dozen', 1),
                batch_data=batch_data,
                user_id=user_id
            )
            if success:
                success_count += 1
            else:
                failed_lines.append(f"Line {idx+1}: {line['name']}")

        if failed_lines:
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Added {success_count} product(s).\nFailed for:\n" + "\n".join(failed_lines)
            )
        else:
            QMessageBox.information(self, "Success", f"Added {success_count} product(s) successfully!")

        self.product_saved.emit(None)
        self.accept()


    def on_payment_status_changed(self, index):
        pass
        # """Show/hide bank account field based on payment status. Payment date always visible.""" load_bank_accounts
        # is_paid = self.payment_status_combo.currentData() == PaymentStatusEnum.PAID.value
        # self.bank_account_container.setVisible(is_paid)

    def setup_for_purchase_entry(self):
        # Show the purchase details button; no need to pre-load banks here because dialog does it. setup_for_batch_mode on_payment_method_changed
        self.purchase_details_btn.show()
    
    def load_bank_accounts(self):
        pass
        # self.bank_account_combo.clear()
        # self.bank_account_combo.addItem("Select Bank Account", None)

        # accounts = self.bank_account_service.get_all()
        
        # priority_ids = [14, 17, 16, 15, 12, 13]
        # account_map = {acc.id: acc for acc in accounts}
        
        # # Priority accounts (in the exact order, only those that exist)
        # for pid in priority_ids:
        #     if pid in account_map:
        #         acc = account_map.pop(pid)
        #         display = f"{acc.account_name} - {acc.bank_name} ({acc.account_number})"
        #         self.bank_account_combo.addItem(display, acc.id)
        
        # # Remaining accounts
        # for acc in account_map.values():
        #     display = f"{acc.account_name} - {acc.bank_name} ({acc.account_number})"
        #     self.bank_account_combo.addItem(display, acc.id)
        
        # if 14 in [a.id for a in accounts]:
        #     idx = self.bank_account_combo.findData(14)
        #     if idx >= 0:
        #         self.bank_account_combo.setCurrentIndex(idx)

    def on_payment_method_changed(self, index):
        pass
        # """Enable bank account only for Transfer or Cheque. validate_form"""
        # # method = self.payment_method_combo.currentData()
        # self.bank_account_combo.setEnabled(True)
    
    def validate_current_product(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation", "Product name is required.")
            return False
        if not self.unit_input.text().strip():
            QMessageBox.warning(self, "Validation", "Unit is required.")
            return False
        if self.quantity_input.value() <= 0:
            QMessageBox.warning(self, "Validation", "Quantity must be greater than 0.")
            return False
        if self.cost_input.value() <= 0:
            QMessageBox.warning(self, "Validation", "Cost price must be greater than 0.")
            return False
        if self.price_input.value() <= 0:
            QMessageBox.warning(self, "Validation", "Selling price must be greater than 0.")
            return False
        return True

    
    def add_current_product(self):
        if not self.validate_current_product():
            return

        product_name = self.name_input.text().strip()
        # Check for duplicate product in the table
        for existing_product in self.product_lines:
            if existing_product["name"].lower() == product_name.lower():
                QMessageBox.warning(
                    self,
                    "Duplicate Product",
                    f"Product '{product_name}' is already added to the list.\n\n"
                    "If you want to add more quantity, please edit the existing entry or remove it first."
                )
                self.products_table.selectRow(self.product_lines.index(existing_product))
                return

        product_data = {
            "name": self.name_input.text().strip(),
            "unit": self.unit_input.text().strip(),
            "dozen": self.dozen_input.value(),
            "quantity": self.quantity_input.value(),
            "cost_price": self.cost_input.value(),
            "selling_price": self.price_input.value() or None,
        }
        self.product_lines.append(product_data)
        self.refresh_product_table()
        self.clear_product_fields()
        self.update_total()
        self.update_button_states()
    
    def clear_product_fields(self):
        self.name_input.setText("")
        self.unit_input.setText("")
        self.dozen_input.setValue(1)
        self.quantity_input.setValue(0)
        self.cost_input.setValue(0.0)
        self.price_input.setValue(0.0)
        self.name_input.line_edit.setFocus()
    

    def refresh_product_table(self):
        self.products_table.setRowCount(len(self.product_lines))
        self.products_table.setVerticalHeaderLabels(
            [str(i + 1) for i in range(len(self.product_lines))]
        )
        for i, line in enumerate(self.product_lines):
            total = line["quantity"] * line.get("dozen", 1) * line["cost_price"]
            self.products_table.setRowHeight(i, 55)
            self.products_table.setItem(i, 0, QTableWidgetItem(line["name"]))
            self.products_table.setItem(i, 1, QTableWidgetItem(str(line["quantity"])))
            self.products_table.setItem(i, 2, QTableWidgetItem(str(line.get("dozen", 1))))   # New Dozen column
            self.products_table.setItem(i, 3, QTableWidgetItem(f"${line['cost_price']:.2f}"))  # Cost (now index 3)
            self.products_table.setItem(i, 4, QTableWidgetItem(f"${total:.2f}"))              # Total (now index 4)

            del_btn = QPushButton("✕")
            del_btn.setFixedSize(40, 40)
            del_font = QFont("Segoe UI", 14, QFont.Bold)
            del_btn.setFont(del_font)
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c; color: white;
                    border: none; border-radius: 4px; font-weight: bold;
                }
                QPushButton:hover { background-color: #c0392b; }
            """)
            del_btn.clicked.connect(lambda checked, idx=i: self.delete_product_line(idx))
            self.products_table.setCellWidget(i, 5, del_btn)

    
    def delete_product_line(self, index):
        if 0 <= index < len(self.product_lines):
            del self.product_lines[index]
            self.refresh_product_table()
            self.update_total()
            self.update_button_states()
    
    def update_total(self):
        total_amount = 0
        total_quantity = 0
        for line in self.product_lines:
            line_total = line["quantity"] * line["cost_price"] * line["dozen"]
            total_amount += line_total
            total_quantity += line["quantity"]
        self.summary_qty.setText(f"{total_quantity:,.0f}")
        self.summary_amount.setText(f"$ {total_amount:,.2f}")
    
    def finish_purchase(self):
        if not self.purchase_details or not self.purchase_details.get("supplier_id"):
            QMessageBox.warning(self, "Validation", "Please set purchase details (supplier & payment) first.")
            return
        if not self.product_lines:
            QMessageBox.warning(self, "Validation", "Add at least one product.")
            return

        details = self.purchase_details
        is_paid = details["payment_status"] == PaymentStatusEnum.PAID.value
        bank_id = details["bank_account_id"]
        if is_paid and bank_id is None:
            QMessageBox.warning(self, "Validation", "Please select a bank account for payment.")
            return

        payment_date = details["payment_date"]
        created_datetime = datetime.combine(payment_date, datetime.now().time())

        purchase_data = {
            "supplier_id": details["supplier_id"],
            "payment_status": details["payment_status"],
            "payment_method": PaymentMethodEnum.TRANSFER,
            "bank_account_id": bank_id,
            "payment_date": payment_date,
            "products": self.product_lines,
            "user_id": self.current_user.id if hasattr(self.current_user, 'id') else None,
            "created_at": created_datetime,
            "last_modified": created_datetime
        }

        try:
            purchase = self.product_service.create(purchase_data)
            if purchase:
                greg_date = payment_date
                eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_date)
                eth_date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
                msg_lines = [f"ቀን፡ {eth_date_str}\n🛒 አዲስ የገባ እቃዎች ዝርዝር፡*\n"]
                num = 1
                for line in self.product_lines:
                    msg_lines.append(f"({num}) {line['name']}  =  {line['quantity']} ካርቶን")
                    num += 1
                message = "\n".join(msg_lines)
                logger.info("About to call notify_store_team_sync, product_lines=%d", len(self.product_lines))
                notify_store_team_sync(
                    message,
                    purchase_id=purchase.id,
                    notification_type='purchase_notification'
                )
                if self.send_notifications_checkbox.isChecked():
                    supplier_id = purchase_data["supplier_id"]
                    notify_supplier_purchase_sync(supplier_id, purchase_id=purchase.id)
                self.product_saved.emit(purchase)
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to record purchase.")
        except ValueError as e:
            QMessageBox.critical(self, "Insufficient Balance", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error: {str(e)}")

    
    def setup_for_batch_mode(self):
        self.table_section.hide()
        self.summary_row.hide()
        self.add_product_btn.hide()

        self.purchase_details_btn.show()  # need supplier & payment

        self.name_input.setEnabled(False)
        self.unit_input.setEnabled(False)
        self.price_input.setEnabled(False)
        self.dozen_input.setEnabled(False)

        if self.product:
            self.name_input.setText(self.product.name)
            self.unit_input.setText(self.product.unit or "")
            self.dozen_input.setValue(self.product.dozen)
            if hasattr(self.product, 'selling_price'):
                self.price_input.setValue(self.product.selling_price)

        self.quantity_input.setValue(0)
        self.cost_input.setValue(0.0)
        self.finish_btn.setText("💾 Save Batch")
        self.finish_btn.clicked.disconnect()
        self.finish_btn.clicked.connect(self.save_batch)

     
    def load_dropdown_data(self):
        """Load categories and suppliers into dropdowns"""
        # self.load_suppliers()
        pass
    
    def load_suppliers(self):
        pass
        # try:
        #     suppliers = self.supplier_service.get_all()
        #     #  print(f"DEBUG: load_suppliers - found {len(suppliers)} suppliers")
        #     self.supplier_combo.combo_box.blockSignals(True)
        #     self.supplier_combo.clear()
        #     self.supplier_combo.addItem("Select Supplier", None)
            
        #     for supplier in suppliers:
        #         self.supplier_combo.addItem(f"{supplier.supplier_name}", int(supplier.id))
            
        #     self.setup_supplier_completer()
        
        #     if self.supplier_combo.combo_box.count() > 9:
        #         self.supplier_combo.setCurrentIndex(9)
        #         logger.info(f"Setting default supplier to index 9")
            
        #     self.supplier_combo.combo_box.blockSignals(False)
        # except Exception as e:
        #     logger.error(f"Error loading suppliers: {str(e)}") get_product_update_data
    
    def load_product_data(self):
        if not self.product:
            return
        self.name_input.setText(self.product.name or "")
        self.unit_input.setText(self.product.unit or "")
        self.price_input.setValue(self.product.selling_price or 0.0)
        if hasattr(self.product, 'supplier_id') and self.product.supplier_id:
            # supplier now lives in the dialog, not editable here; skip
            pass
        self.quantity_input.setValue(0)
        self.cost_input.setValue(0.0)
        if hasattr(self.product, 'dozen'):
            self.dozen_input.setValue(self.product.dozen)
        if self.mode == "edit_product":
            self.purchase_details_btn.hide()
            self.quantity_input.setEnabled(False)
            self.cost_input.setEnabled(False)
            self.send_notifications_checkbox.setVisible(False)
            self.table_section.hide()
            self.summary_row.hide()
            self.add_product_btn.hide()
            self.finish_btn.setText("✏️ Update Product")
            self.finish_btn.clicked.disconnect()
            self.finish_btn.clicked.connect(self.update_product)
            self.finish_btn.setEnabled(True)
            self.finish_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2ecc71, stop:1 #27ae60);
                    color: white; border: none; border-radius: 10px;
                    font-weight: 600; font-size: 15px; padding: 14px 28px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #27ae60, stop:1 #219a52);
                }
            """)
    
    
    def validate_form(self):
        # Your existing validation logic (unchanged)
        errors = []
        if self.mode == "add_batch":
            if self.quantity_input.value() <= 0:
                errors.append("Quantity must be greater than 0.")
            if self.cost_input.value() <= 0:
                errors.append("Cost Price must be greater than 0.")
        elif self.mode == "edit_product":
            if not self.name_input.text().strip():
                errors.append("Product Name is required.")
            if not self.unit_input.text().strip():
                errors.append("Unit is required.")
            if self.price_input.value() <= 0:
                errors.append("Selling Price must be greater than 0.")
            # Supplier no longer validated here because not shown.
        else:  # new_product
            if not self.name_input.text().strip():
                errors.append("Product Name is required.")
            if not self.unit_input.text().strip():
                errors.append("Unit is required.")
            if self.quantity_input.value() < 0:
                errors.append("Quantity cannot be negative.")
            if self.cost_input.value() <= 0:
                errors.append("Cost Price must be greater than 0.")
            if self.price_input.value() <= 0:
                errors.append("Selling Price must be greater than 0.")
            # Supplier validation moved to finish_purchase
        if errors:
            error_msg = "<b>Validation Errors:</b><br><br>" + "<br>".join(f"• {error}" for error in errors)
            QMessageBox.warning(self, "Validation Error", error_msg)
            return False
        return True
    
    def save_batch(self):
        if not self.validate_form():
            return
        if not self.purchase_details or not self.purchase_details.get("supplier_id"):
            QMessageBox.warning(self, "Validation", "Please set purchase details first.")
            return

        details = self.purchase_details
        is_paid = details["payment_status"] == PaymentStatusEnum.PAID.value
        bank_id = details["bank_account_id"]
        if is_paid and bank_id is None:
            QMessageBox.warning(self, "Validation", "Please select a bank account for payment.")
            return

        product_line = {
            "name": self.name_input.text().strip(),
            "unit": self.unit_input.text().strip(),
            "dozen": self.dozen_input.value(),
            "quantity": self.quantity_input.value(),
            "cost_price": self.cost_input.value(),
            "selling_price": self.price_input.value(),
        }

        purchase_data = {
            "supplier_id": details["supplier_id"],
            "payment_status": details["payment_status"],
            "payment_method": PaymentMethodEnum.TRANSFER,
            "bank_account_id": bank_id,
            "payment_date": details["payment_date"],
            "products": [product_line],
            "user_id": self.current_user.id if hasattr(self.current_user, 'id') else None,
            "created_at": details["payment_date"],
            "last_modified": details["payment_date"]
        }

        try:
            purchase = self.product_service.create(purchase_data)
            if purchase:
                self.product_saved.emit(purchase)
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to record purchase.")
        except ValueError as e:
            QMessageBox.critical(self, "Insufficient Balance", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error: {str(e)}")



    def get_product_update_data(self):
        product_data = {
            "name": self.name_input.text().strip(),
            "unit": self.unit_input.text().strip(),
            "selling_price": self.price_input.value(),
            "dozen": self.dozen_input.value(),
        }
        return product_data

    def update_product(self):
        if not self.validate_form():
            return
        product_data = self.get_product_update_data()
        if not product_data["name"]:
            QMessageBox.warning(self, "Validation Error", "Product Name is required.")
            return
        if not product_data["unit"]:
            QMessageBox.warning(self, "Validation Error", "Unit is required.")
            return
        if product_data["selling_price"] <= 0:
            QMessageBox.warning(self, "Validation Error", "Selling Price must be greater than 0.")
            return
        try:
            success = self.product_service.update(self.product.id, product_data)
            if success:
                updated_product = self.product_service.get_by_id(self.product.id)
                self.product_saved.emit(updated_product)
                self.accept()
            else:
                QMessageBox.warning(self, "Error", "Failed to update product. It may have been deleted.")
        except Exception as e:
            logger.error(f"Error updating product: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to update product: {str(e)}")


    def open_supplier_dialog(self):
        pass
        # """Open the supplier management dialog"""
        # dialog = UniversalCRUDDialog('supplier', SupplierService, self)
        # dialog.exec()
        # self.load_suppliers()
    
    def clear_form(self):
        self.name_input.setText("")
        self.unit_input.setText("")
        self.quantity_input.setValue(0)
        self.cost_input.setValue(0.0)
        self.price_input.setValue(0.0)
        self.dozen_input.setValue(1)
        self.name_input.line_edit.setFocus()
    
    def setup_supplier_completer(self):
        """Set up a searchable completer for the supplier combo box."""
        pass
        # line_edit = self.supplier_combo.combo_box.lineEdit()
        # if not line_edit:
        #     return

        # # Use the combo's model for the completer
        # completer = QCompleter(self.supplier_combo.combo_box.model())
        # completer.setCaseSensitivity(Qt.CaseInsensitive)
        # completer.setFilterMode(Qt.MatchContains)          # Match anywhere
        # completer.setCompletionMode(QCompleter.PopupCompletion)
        # line_edit.setCompleter(completer)

        # # When a suggestion is clicked, set the combo's current index
        # completer.activated.connect(self.on_supplier_completer_activated)

    def on_supplier_completer_activated(self, text):
        """Find the supplier with the given text and select it in the combo. setup_for_stock_in on_payment_status_changed"""
        # Find index of the item that matches the text (exact match, case‑insensitive)
        for i in range(self.supplier_combo.combo_box.count()):
            if self.supplier_combo.combo_box.itemText(i).lower() == text.lower():
                self.supplier_combo.combo_box.setCurrentIndex(i)
                break