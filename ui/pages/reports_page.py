#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QMessageBox, QTableWidget, QTableWidgetItem, QComboBox, QDateEdit,
    QTabWidget, QHeaderView, QAbstractItemView, QFormLayout, QFileDialog,
    QFrame, QSizePolicy, QToolButton, QCheckBox, QLineEdit, QTextEdit
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QDate, QTimer
from services.customer_service import CustomerService
from services.supplier_service import SupplierService
from services.bank_account_service import BankAccountService
from services.bank_transaction_service import BankTransactionService
from services.expense_category_service import ExpenseCategoryService
from services.expense_service import ExpenseService
from datetime import date, datetime, timedelta
from utils import backup_database as create_database_backup
from ui.pages.bank_transaction_dialog import BankTransactionHistoryDialog
from ui.pages.expense_dialog import ExpenseDialog
from ui.pages.manage_categories_dialog import ManageCategoriesDialog
from ui.pages.bank_transfer_dialog import BankTransferDialog
from ui.components.ethiopian_date import EthiopianDateConverter
import logging

logger = logging.getLogger(__name__)



class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.customer_service = CustomerService()
        self.supplier_service = SupplierService()
        self.bank_account_service = BankAccountService()
        self.bank_transaction_service = BankTransactionService()
        self.expense_category_service = ExpenseCategoryService()
        self.expense_service = ExpenseService()

        self.expense_current_offset = 0
        self.expense_batch_size = 50
        self.expense_has_more = True
        self.expense_is_loading = False
        self.expense_search_term = None
        self.expense_search_timer = QTimer()
        self.expense_search_timer.setSingleShot(True)
        self.expense_search_timer.timeout.connect(self.perform_expense_search)

        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Tab widget for different sections
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
       
        #Bank Account Managment
        self.bank_account_tab = QWidget()
        self.tabs.addTab(self.bank_account_tab, "Bank Accounts")
        self.setup_bank_account_tab()

        #Expense Tab
        self.expenses_tab = QWidget()
        self.tabs.addTab(self.expenses_tab, "Expenses")
        self.setup_expenses_tab()

        # Admin Actions Tab
        self.admin_tab = QWidget()
        self.tabs.addTab(self.admin_tab, "Admin Actions")
        self.setup_admin_tab()


        self.tabs.currentChanged.connect(self.on_tab_changed)
    
    def on_tab_changed(self, index):
        """PaymentTransaction Handle tab changes and refresh data when Database Management tab is selected content"""
        tab_name = self.tabs.tabText(index)

        if tab_name == "Generate Reports":
            # Load/refresh customer and product data every time Reports tab is selected showEvent
            self.load_customer_data()
            self.load_product_data()
            logger.info("Reports tab selected - customer and product data refreshed")

        elif tab_name == "Database Management":
            # Refresh the data when Database Management tab is clicked
            self.load_table_data()
            logger.info("Database Management tab selected - data refreshed")
        
        elif tab_name == "Bank Accounts":
            self.load_bank_accounts()
            logger.info("Bank Accounts tab selected - data refreshed")
        
        elif tab_name == "Expenses":
            self.expense_search_field.clear()
            self.expense_search_term = None
            self.refresh_expenses()
            logger.info("Expenses tab selected - data refreshed")
    
    def setup_expenses_tab(self):
        """Modern expenses tab with toolbar, search, filters, table, and status bar add_expense_row"""
        layout = QVBoxLayout(self.expenses_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ==================== TOOLBAR ====================
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 10, 15, 10)
        toolbar_layout.setSpacing(15)

        # Left side buttons
        self.add_expense_btn = QPushButton("➕ Add Expense")
        self.add_expense_btn.setStyleSheet("""
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
        """)
        self.add_expense_btn.clicked.connect(self.add_expense)
        toolbar_layout.addWidget(self.add_expense_btn)
    

        self.manage_cat_btn = QPushButton("📂 Manage Categories")
        self.manage_cat_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 15px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.manage_cat_btn.clicked.connect(self.manage_categories)
        toolbar_layout.addWidget(self.manage_cat_btn)

        toolbar_layout.addStretch()

        # Right side search
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(5)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("color: #7f8c8d; font-size: 16px;")

        self.expense_search_field = QLineEdit()
        self.expense_search_field.setPlaceholderText("Search expenses (description, notes, reference)...")
        self.expense_search_field.setMinimumWidth(300)
        self.expense_search_field.setClearButtonEnabled(True)
        self.expense_search_field.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
            }
        """)
        self.expense_search_field.textChanged.connect(self.on_expense_search_text_changed)

        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.expense_search_field)

        toolbar_layout.addWidget(search_container)

        layout.addWidget(toolbar)

        # ==================== FILTER BAR (Date & Category) ====================
        filter_bar = QWidget()
        filter_bar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #e0e0e0;")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(15, 10, 15, 10)
        filter_layout.setSpacing(15)

        filter_layout.addWidget(QLabel("From:"))
        self.expense_start_date = QDateEdit()
        self.expense_start_date.setDate(QDate.currentDate().addMonths(-1))
        self.expense_start_date.setCalendarPopup(True)
        self.expense_start_date.setStyleSheet("padding: 5px; border: 1px solid #e0e0e0; border-radius: 4px;")
        filter_layout.addWidget(self.expense_start_date)

        filter_layout.addWidget(QLabel("To:"))
        self.expense_end_date = QDateEdit()
        self.expense_end_date.setDate(QDate.currentDate())
        self.expense_end_date.setCalendarPopup(True)
        self.expense_end_date.setStyleSheet("padding: 5px; border: 1px solid #e0e0e0; border-radius: 4px;")
        filter_layout.addWidget(self.expense_end_date)

        filter_layout.addWidget(QLabel("Category:"))
        self.expense_category_filter = QComboBox()
        self.expense_category_filter.addItem("All Categories", None)
        self.expense_category_filter.setStyleSheet("padding: 5px; border: 1px solid #e0e0e0; border-radius: 4px; min-width: 150px;")
        filter_layout.addWidget(self.expense_category_filter)

        self.apply_filter_btn = QPushButton("Apply Filters")
        self.apply_filter_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        self.apply_filter_btn.clicked.connect(self.apply_expense_filter)
        filter_layout.addWidget(self.apply_filter_btn)

        filter_layout.addStretch()
        layout.addWidget(filter_bar)

        filter_layout.addWidget(QLabel("Type:"))
        self.expense_type_filter = QComboBox()
        self.expense_type_filter.addItem("All", None)
        self.expense_type_filter.addItem("Business", False)
        self.expense_type_filter.addItem("Personal", True)
        self.expense_type_filter.setStyleSheet("padding: 5px; border: 1px solid #e0e0e0; border-radius: 4px;")
        filter_layout.addWidget(self.expense_type_filter)
        filter_layout.addStretch()          # ← stretch goes last
        layout.addWidget(filter_bar)

        # ==================== TABLE ====================
        self.expenses_table = QTableWidget()
        self.expenses_table.setColumnCount(7)   # was 6
        self.expenses_table.setHorizontalHeaderLabels([
            "", "Date", "Notes", "Amount", "Category", "Bank Account", "Actions"
        ])
        self.expenses_table.setColumnHidden(0, True)

        # Style table
        self.expenses_table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #e0e0e0;
                font-weight: 600;
                font-size: 13px;
            }
        """)
        self.expenses_table.setAlternatingRowColors(True)
        self.expenses_table.verticalHeader().setVisible(False)
        self.expenses_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.expenses_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.expenses_table.setSelectionMode(QTableWidget.ExtendedSelection)  # Allow multi-select

        # Set column widths
        self.expenses_table.setColumnWidth(1, 100)   # Date
        self.expenses_table.setColumnWidth(2, 250)   # Notes
        self.expenses_table.setColumnWidth(3, 100)   # Amount
        self.expenses_table.setColumnWidth(4, 120)   # Category
        self.expenses_table.setColumnWidth(5, 180)   # Bank Account
        self.expenses_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.expenses_table.horizontalHeader().setStretchLastSection(False)
        self.expenses_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Description stretches

        layout.addWidget(self.expenses_table, 1)  # Give table stretch

        # ==================== PAGINATION & STATUS BAR ====================
        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(15, 10, 15, 10)
        bottom_layout.setSpacing(15)

        # Pagination controls
        self.page_prev_btn = QPushButton("◀ Previous")
        self.page_prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover:enabled {
                background-color: #d0d3d4;
            }
            QPushButton:disabled {
                color: #bdc3c7;
            }
        """)
        self.page_prev_btn.clicked.connect(self.previous_expense_page)

        self.page_next_btn = QPushButton("Next ▶")
        self.page_next_btn.setStyleSheet(self.page_prev_btn.styleSheet())
        self.page_next_btn.clicked.connect(self.next_expense_page)

        self.page_label = QLabel("Page 1")
        self.page_label.setStyleSheet("font-weight: 600; margin: 0 10px;")

        bottom_layout.addWidget(self.page_prev_btn)
        bottom_layout.addWidget(self.page_label)
        bottom_layout.addWidget(self.page_next_btn)
        bottom_layout.addStretch()

        # Status label (total expenses and amount)
        self.expenses_summary_label = QLabel("Total: $0.00")
        self.expenses_summary_label.setStyleSheet("color: #2c3e50; font-weight: 600;")
        bottom_layout.addWidget(self.expenses_summary_label)

        layout.addWidget(bottom_bar)

        # Initial load
        self.load_expenses_categories_filter()
        self.load_expenses()
    
    def on_expense_search_text_changed(self, text):
        """Debounce search input"""
        self.expense_search_timer.stop()
        if text.strip():
            self.expense_search_timer.start(500)
        else:
            self.expense_search_term = None
            self.refresh_expenses()

    def perform_expense_search(self):
        """Execute search with current term"""
        self.expense_search_term = self.expense_search_field.text().strip() or None
        self.refresh_expenses()

    def refresh_expenses(self):
        """Reset pagination and reload expenses"""
        self.expense_current_offset = 0
        self.expense_has_more = True
        self.load_expenses(reset=True)
    
    def load_expenses_categories_filter(self):
        current_cat_id = self.expense_category_filter.currentData()
        categories = self.expense_category_service.get_active()
        self.expense_category_filter.clear()
        self.expense_category_filter.addItem("All Categories", None)
        for cat in categories:
            self.expense_category_filter.addItem(cat.name, cat.id)
        # Restore previous selection if exists
        if current_cat_id is not None:
            index = self.expense_category_filter.findData(current_cat_id)
            if index >= 0:
                self.expense_category_filter.setCurrentIndex(index)

    
    def load_expenses(self, reset=False):
        """Load expenses with pagination, filters, and search"""
        if self.expense_is_loading:
            return
        self.expense_is_loading = True

        try:
            if reset:
                self.expense_current_offset = 0
                self.expense_has_more = True
                self.expenses_table.setRowCount(0)

            start_date = self.expense_start_date.date().toPython()
            end_date = self.expense_end_date.date().toPython()
            category_id = self.expense_category_filter.currentData()
            page_size = self.expense_batch_size
            offset = self.expense_current_offset
            is_personal = self.expense_type_filter.currentData()

            expenses, total = self.expense_service.get_filtered(
                start_date=start_date,
                end_date=end_date,
                category_id=category_id,
                search=self.expense_search_term,
                is_personal=is_personal,
                limit=page_size,
                offset=offset
            )

            if not expenses and offset == 0:
                # No results
                self.expenses_table.setRowCount(0)
                self.expenses_summary_label.setText("Total: $0.00")
                self.page_label.setText("Page 1")
                self.page_prev_btn.setEnabled(False)
                self.page_next_btn.setEnabled(False)
                return

            start_row = self.expenses_table.rowCount()
            self.expenses_table.setRowCount(start_row + len(expenses))

            total_amount = 0.0
            for i, exp in enumerate(expenses):
                row = start_row + i
                self.add_expense_row(row, exp)
                total_amount += exp.amount

            self.expense_current_offset += len(expenses)
            self.expense_has_more = len(expenses) == page_size

            # Update summary and pagination
            total_displayed = self.expenses_table.rowCount()
            start = offset + 1 if total_displayed > 0 else 0
            end = offset + len(expenses)
            self.expenses_summary_label.setText(f"Showing {start}-{end} of {total} | Total: ${total_amount:,.2f}")
            self.page_label.setText(f"Page {offset // page_size + 1}")
            self.page_prev_btn.setEnabled(offset > 0)
            self.page_next_btn.setEnabled(self.expense_has_more)


        except Exception as e:
            logger.error(f"Error loading expenses: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load expenses: {str(e)}")
        finally:
            self.expense_is_loading = False
    
    def add_expense_row(self, row, expense):
        # Hidden ID (col 0)
        id_item = QTableWidgetItem(str(expense.id))
        self.expenses_table.setItem(row, 0, id_item)

        # Date (col 1) – keep Ethiopian conversion
        eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(expense.date)
        date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year}"
        date_item = QTableWidgetItem(date_str)
        date_item.setTextAlignment(Qt.AlignCenter)
        date_item.setToolTip(f"Gregorian: {expense.date.strftime('%Y-%m-%d')}")
        self.expenses_table.setItem(row, 1, date_item)

        # Notes (col 2) – use QTextEdit for multi-line
        notes_widget = QTextEdit()
        notes_widget.setPlainText(expense.notes or "")
        notes_widget.setReadOnly(True)
        notes_widget.setFrameShape(QFrame.NoFrame)
        notes_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        notes_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        notes_widget.setStyleSheet("background-color: transparent;")
        # Adjust height based on content
        font_metrics = notes_widget.fontMetrics()
        col_width = self.expenses_table.columnWidth(2) - 10
        text_rect = font_metrics.boundingRect(
            0, 0, col_width, 0,
            Qt.TextWordWrap | Qt.AlignLeft,
            expense.notes or ""
        )
        height = max(40, text_rect.height() + 15)
        notes_widget.setFixedHeight(height)
        self.expenses_table.setCellWidget(row, 2, notes_widget)

        # Amount (col 3)
        amount_item = QTableWidgetItem(f"${expense.amount:,.2f}")
        amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if expense.amount < 0:
            amount_item.setForeground(QColor("#e74c3c"))
        else:
            amount_item.setForeground(QColor("#27ae60"))
        self.expenses_table.setItem(row, 3, amount_item)

        # Category (col 4)
        category_name = expense.category.name if expense.category else "N/A"
        category_item = QTableWidgetItem(category_name)
        category_item.setTextAlignment(Qt.AlignCenter)
        self.expenses_table.setItem(row, 4, category_item)

        # Bank Account (col 5)
        bank_info = f"{expense.bank_account.bank_name} - {expense.bank_account.account_name}"
        bank_item = QTableWidgetItem(bank_info)
        bank_item.setTextAlignment(Qt.AlignCenter)
        bank_item.setToolTip(bank_info)
        self.expenses_table.setItem(row, 5, bank_item)

        # Actions (col 6)
        actions_widget = self.create_expense_action_buttons(expense)
        self.expenses_table.setCellWidget(row, 6, actions_widget)

        if expense.is_personal:
            for col in range(self.expenses_table.columnCount()):
                item = self.expenses_table.item(row, col)
                if item:
                    item.setBackground(QColor(255, 235, 238))
    
    def manage_categories(self):
        dlg = ManageCategoriesDialog(self)
        if dlg.exec():
            self.load_expenses_categories_filter()
            self.refresh_expenses()

    def delete_expense(self, expense=None):
        """Delete the selected expense(s). If expense provided, delete that one."""
        expenses_to_delete = []
        if expense:
            expenses_to_delete.append(expense)
        else:
            selected_rows = set()
            for item in self.expenses_table.selectedItems():
                selected_rows.add(item.row())
            if not selected_rows:
                QMessageBox.warning(self, "No Selection", "Please select at least one expense to delete.")
                return
            for row in selected_rows:
                expense_id = int(self.expenses_table.item(row, 0).text())
                exp = self.expense_service.get_by_id(expense_id)
                if exp:
                    expenses_to_delete.append(exp)

        if not expenses_to_delete:
            return

        msg = f"Are you sure you want to delete {len(expenses_to_delete)} expense(s)?"
        reply = QMessageBox.question(self, "Confirm Deletion", msg, QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return

        success_count = 0
        for exp in expenses_to_delete:
            try:
                if self.expense_service.delete_with_transaction(exp.id):
                    success_count += 1
            except Exception as e:
                logger.error(f"Error deleting expense {exp.id}: {e}")

        self.refresh_expenses()
        # Optionally, if current page becomes empty and there are previous pages, adjust offset
        if self.expenses_table.rowCount() == 0 and self.expense_current_offset > 0:
            self.expense_current_offset -= self.expense_batch_size
            self.load_expenses()
        QMessageBox.information(self, "Deletion Complete", f"Deleted {success_count} of {len(expenses_to_delete)} expenses.")
    
    def edit_expense(self, expense=None):
        """If expense provided, edit that expense; otherwise use selected row."""
        if expense is None:
            selected = self.expenses_table.selectedItems()
            if not selected:
                QMessageBox.warning(self, "No Selection", "Please select an expense to edit.")
                return
            row = selected[0].row()
            expense_id = int(self.expenses_table.item(row, 0).text())
            expense = self.expense_service.get_by_id(expense_id)
            if not expense:
                QMessageBox.warning(self, "Error", "Selected expense not found.")
                return

        dlg = ExpenseDialog(self, expense=expense, read_only=False)
        if dlg.exec():
            if hasattr(dlg, 'update_data'):
                data = dlg.update_data
            else:
                # fallback for creation (if used)
                common, lines = dlg.get_data()
                data = {'common': common, 'lines': lines}
            try:
                updated = self.expense_service.update(expense.id, data)
                if updated:
                    # self.load_expenses()
                    self.refresh_expenses()
                    QMessageBox.information(self, "Success", "Expense updated successfully.")
                else:
                    QMessageBox.critical(self, "Error", "Failed to update expense.")
            except Exception as e:
                logger.error(f"Error updating expense: {e}")
                QMessageBox.critical(self, "Error", f"Failed to update expense: {str(e)}")
    
    def add_expense(self):
        """Open dialog to create one or more expenses."""
        dlg = ExpenseDialog(self, read_only=False)
        if dlg.exec():
            try:
                self.load_expenses_categories_filter()
                self.refresh_expenses()
                QMessageBox.information(self, "Success", "Expense(s) added successfully.")
            except Exception as e:
                logger.error(f"Error refreshing after add: {e}")
                QMessageBox.warning(self, "Warning", "Expenses saved but failed to refresh the list.")
    
    def create_expense_action_buttons(self, expense):
        """Create modern action buttons for an expense row"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(3)

        # View button
        view_btn = QPushButton("👁️")
        view_btn.setFixedSize(30, 30)
        view_btn.setToolTip("View Details")
        view_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d0d3d4;
            }
        """)
        # view_btn.clicked.connect(lambda checked, e=expense: self.view_expense(e))

        # Edit button
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(30, 30)
        edit_btn.setToolTip("Edit")
        edit_btn.setStyleSheet(view_btn.styleSheet())
        edit_btn.clicked.connect(lambda checked, e=expense: self.edit_expense(e))

        # Delete button
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(30, 30)
        delete_btn.setToolTip("Delete")
        delete_btn.setStyleSheet(view_btn.styleSheet())
        delete_btn.clicked.connect(lambda checked, e=expense: self.delete_expense(e))

        # layout.addWidget(view_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)

        return widget
    
    def previous_expense_page(self):
        if self.expense_current_offset - self.expense_batch_size >= 0:
            self.expense_current_offset -= self.expense_batch_size
            self.load_expenses()

    def next_expense_page(self):
        if self.expense_has_more:
            self.load_expenses()
    
    def apply_expense_filter(self):
        self.expense_search_term = None  # Clear search when applying filters
        self.expense_search_field.clear()
        self.refresh_expenses()
    
    def setup_bank_account_tab(self):
        layout = QVBoxLayout(self.bank_account_tab)
        layout.setContentsMargins(10, 10, 10, 10)

        header_label = QLabel("Bank Account Management")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        button_layout = QHBoxLayout()

        self.create_account_btn = QPushButton("Create New Account")
        self.create_account_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        self.create_account_btn.clicked.connect(self.create_bank_account)
        button_layout.addWidget(self.create_account_btn)

        self.edit_account_btn = QPushButton("Edit Selected Account")
        self.edit_account_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px;")
        self.edit_account_btn.clicked.connect(self.edit_bank_account)
        button_layout.addWidget(self.edit_account_btn)

        self.delete_account_btn = QPushButton("Delete Selected Account")
        self.delete_account_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px;")
        self.delete_account_btn.clicked.connect(self.delete_bank_account)
        button_layout.addWidget(self.delete_account_btn)

        self.transfer_btn = QPushButton("Transfer Funds")
        self.transfer_btn.setStyleSheet("background-color: #9b59b6; color: white; padding: 8px;")
        self.transfer_btn.clicked.connect(self.open_transfer_dialog)
        button_layout.addWidget(self.transfer_btn)

        self.deposit_btn = QPushButton("Record Deposit")
        self.deposit_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 8px;")
        self.deposit_btn.clicked.connect(self.record_deposit)
        button_layout.addWidget(self.deposit_btn)

        self.refresh_accounts_btn = QPushButton("Refresh List")
        self.refresh_accounts_btn.clicked.connect(self.load_bank_accounts)
        button_layout.addWidget(self.refresh_accounts_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.bank_accounts_table = QTableWidget()
        self.bank_accounts_table.setColumnCount(8)
        self.bank_accounts_table.setHorizontalHeaderLabels([
            "ID", "Account Name", "Bank Name", "Account Number",
            "Account Type", "Current Balance", "Status", "Actions"
        ])
        self.bank_accounts_table.setColumnHidden(0, True)
        header = self.bank_accounts_table.horizontalHeader()
        for col in range(7):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.bank_accounts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.bank_accounts_table)

        self.bank_status_label = QLabel("Total: 0 accounts | Active: 0 | Total Balance: $0.00")
        self.bank_status_label.setStyleSheet("margin-top: 10px; font-style: italic;")
        layout.addWidget(self.bank_status_label)

        self.load_bank_accounts()
    
    def record_deposit(self):
        from ui.pages.deposit_dialog import DepositDialog
        from datetime import date

        dlg = DepositDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            tx = self.bank_transaction_service.create_external_deposit(
                to_account_id=data['account_id'],
                amount=data['amount'],
                transaction_date=date.today(),
                source=data['source'],
                description=data['description']
            )
            if tx:
                self.load_bank_accounts()   # Refresh after successful deposit
                QMessageBox.information(self, "Success", "Deposit recorded.")
            else:
                QMessageBox.critical(self, "Error", "Failed to record deposit.")
        # If dialog is cancelled, do nothing
    
    def open_transfer_dialog(self):
        dlg = BankTransferDialog(self)
        if dlg.exec():
            self.load_bank_accounts()
    
    def load_bank_accounts(self):
        try:
            accounts = self.bank_account_service.get_all()
            self.bank_accounts_table.setRowCount(0)

            total_balance = 0
            active_count = 0

            for account in accounts:
                row = self.bank_accounts_table.rowCount()
                self.bank_accounts_table.insertRow(row)
                current_balance = self.bank_transaction_service.get_balance(account.id)

                status = "Active" if account.is_active else "Inactive"

                items = [
                    QTableWidgetItem(str(account.id)),
                    QTableWidgetItem(account.account_name or ""),
                    QTableWidgetItem(account.bank_name or ""),
                    QTableWidgetItem(account.account_number or ""),
                    QTableWidgetItem(account.account_type.value.title() if account.account_type else ""),
                    QTableWidgetItem(f"${current_balance:,.2f}"),
                    QTableWidgetItem(status)
                ]

                if not account.is_active:
                    for item in items:
                        item.setBackground(QColor(240, 240, 240))
                
                elif current_balance < 0:
                    items[5].setBackground(QColor(255, 200, 200))
                
                for col, item in enumerate(items):
                    self.bank_accounts_table.setItem(row, col, item)
                
                btn = QPushButton("Details")
                btn.clicked.connect(lambda checked, acc_id=account.id: self.show_transaction_details(acc_id))
                self.bank_accounts_table.setCellWidget(row, 7, btn)

                total_balance += current_balance
                if account.is_active:
                    active_count += 1
            
            self.bank_status_label.setText(
                f"Total: {len(accounts)} accounts | "
                f"Active: {active_count} | "
                f"Total Balance: ${total_balance:,.2f}"
            )

            logger.info(f"Loaded {len(accounts)} bank accounts")
        except Exception as e:
            logger.error(f"Error loading bank accounts: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load bank accounts: {str(e)}")
    
    def create_bank_account(self):
        try:
            from ui.pages.bank_account_dialog import BankAccountDialog

            dlg = BankAccountDialog(self)
            if dlg.exec():
                account_data = dlg.get_data()
                new_account = self.bank_account_service.create(account_data)
                if new_account:
                    # Reload the accounts list
                    self.load_bank_accounts()
                    QMessageBox.information(self, "Success", 
                                        f"Bank account '{account_data['account_name']}' created successfully!")
        except Exception as e:
            logger.error(f"Error creating bank account: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create bank account: {str(e)}")
    
    def edit_bank_account(self):
        selected_rows = self.bank_accounts_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a bank account to edit.")
            return

        row = selected_rows[0].row()
        account_id = int(self.bank_accounts_table.item(row, 0).text())

        try:
            balance = self.bank_transaction_service.get_balance(account_id)
            account = self.bank_account_service.get_by_id(account_id)
            if not account:
                QMessageBox.warning(self, "Error", "Selected bank account not found.")
                return

            from ui.pages.bank_account_dialog import BankAccountDialog
            dlg = BankAccountDialog(self, account, balance)
            if dlg.exec():
                updated_data = dlg.get_data()
                updated_data.pop('initial_balance', None)   # Remove if present

                # Update account details (name, bank, number, type, active status)
                success = self.bank_account_service.update(account_id, updated_data)
                if not success:
                    QMessageBox.critical(self, "Error", "Failed to update account details.")
                    return

                # Handle balance change if any
                balance_change = dlg.get_balance_change()
                if balance_change:
                    from datetime import date
                    from models.bank_transactions import TransactionDirectionEnum

                    # Get current balance (may have changed while dialog was open)
                    current_balance = self.bank_transaction_service.get_balance(account_id)
                    new_balance = balance_change['new_balance']
                    diff = new_balance - current_balance

                    if abs(diff) > 0.01:   # Only create transaction if significant change
                        direction = 'CREDIT' if diff > 0 else 'DEBIT'
                        tx_data = {
                            'bank_account_id': account_id,
                            'amount': abs(diff),
                            'direction': TransactionDirectionEnum[direction],
                            'transaction_date': date.today(),
                            'description': 'Manual balance adjustment',
                            'balance_after': new_balance,
                            'reference_number': None
                        }
                        adj_tx = self.bank_transaction_service.create(tx_data)
                        if not adj_tx:
                            QMessageBox.warning(
                                self, "Warning",
                                "Account details updated but failed to create adjustment transaction."
                            )
                        else:
                            logger.info(f"Created adjustment transaction for account {account_id}")

                self.load_bank_accounts()
                # Reselect the edited row
                for r in range(self.bank_accounts_table.rowCount()):
                    if int(self.bank_accounts_table.item(r, 0).text()) == account_id:
                        self.bank_accounts_table.selectRow(r)
                        break
                QMessageBox.information(self, "Success", "Bank account updated successfully!")

        except Exception as e:
            logger.error(f"Error editing bank account: {e}")
            QMessageBox.critical(self, "Error", f"Failed to edit bank account: {str(e)}")
    
    def delete_bank_account(self):
        selected_rows = self.bank_accounts_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a bank account to delete.")
            return

        # For simplicity, handle only the first selected account
        row = selected_rows[0].row()
        account_id = int(self.bank_accounts_table.item(row, 0).text())
        account_name = self.bank_accounts_table.item(row, 1).text()

        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete bank account '{account_name}'?\n\n"
            "This will also permanently delete all associated bank transactions. This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        try:
            # Call the service method that soft‑deletes account and its transactions
            success = self.bank_account_service.soft_delete_with_transactions(account_id)
            if success:
                self.load_bank_accounts()   # Refresh the accounts table
                QMessageBox.information(self, "Success", "Bank account and its transactions deleted.")
            else:
                QMessageBox.warning(self, "Error", "Failed to delete bank account.")
        except Exception as e:
            logger.error(f"Error deleting bank account: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete bank account: {str(e)}")
    
    def show_transaction_details(self, account_id):
    
        dlg = BankTransactionHistoryDialog(account_id, self)
        dlg.exec()
    
    def setup_admin_tab(self):
        layout = QVBoxLayout(self.admin_tab)
        
        # Critical actions section
        actions_layout = QVBoxLayout()
        actions_layout.addWidget(QLabel("Critical Operations:"))
        
        # User management
        user_btn = QPushButton("Manage User Accounts")
        user_btn.setStyleSheet("background-color: #9C27B0; color: white;")
        user_btn.clicked.connect(self.manage_users)
        actions_layout.addWidget(user_btn)
        
        # Database maintenance
        db_btn = QPushButton("Database Backup & Restore")
        db_btn.setStyleSheet("background-color: #FF9800; color: white;")
        db_btn.clicked.connect(self.db_maintenance)
        actions_layout.addWidget(db_btn)
        
        # Audit log
        audit_btn = QPushButton("View Audit Logs")
        audit_btn.setStyleSheet("background-color: #607D8B; color: white;")
        audit_btn.clicked.connect(self.view_audit_logs)
        actions_layout.addWidget(audit_btn)
        
        layout.addLayout(actions_layout)
        
        # Status panel
        status_layout = QVBoxLayout()
        status_layout.addWidget(QLabel("System Status:"))
        
        # Status indicators
        status_form = QFormLayout()
        status_form.addRow("Database:", QLabel("Connected (128 tables)"))
        status_form.addRow("Last Backup:", QLabel("2023-11-15 14:30:00"))
        status_form.addRow("Active Users:", QLabel("3 (2 clerks, 1 admin)"))
        status_layout.addLayout(status_form)
        
        layout.addLayout(status_layout)
        
        # Security notice
        notice = QLabel("⚠️ Admin Notice: All actions on this page are logged and audited")
        notice.setStyleSheet("color: #f44336; font-weight: bold;")
        layout.addWidget(notice)
    
    def manage_users(self):
        """Open user management dialog"""
        from ui.pages.user_management_dialog import UserManagementDialog
        dlg = UserManagementDialog(self)
        dlg.exec()
    
    def db_maintenance(self):
        self.backup_database()
    
    def view_audit_logs(self):
        """View audit logs"""
        QMessageBox.information(self, "Audit Logs", 
                               "This would display all administrative actions with timestamps.")
    
    def backup_database(self):
        try:
            backup_file = create_database_backup()
            
            QMessageBox.information(self, "Backup Successful", f"Backup created:\n{backup_file}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", f"Failed to create backup:\n{str(e)}")

    def show_default_tab(self):
        """Reset to the first tab (Generate Reports)"""
        self.tabs.setCurrentIndex(0)