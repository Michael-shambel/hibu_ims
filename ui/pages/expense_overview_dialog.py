#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QWidget, QFrame, QProgressBar,
    QMessageBox, QApplication, QCheckBox
)
from PySide6.QtCore import Qt, QThread, QDate
from PySide6.QtGui import QFont, QColor, QCursor
from services.expense_service import ExpenseService
from ui.components.ethiopian_date import EthiopianDateConverter, EthiopianDateEdit
from ui.utils.worker import Worker
from datetime import date, datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class ExpenseOverviewDialog(QDialog):
    def __init__(self, parent, current_user=None, start_date=None, end_date=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Expense Overview")
        
        screen = QApplication.primaryScreen().availableGeometry()
        desired_height = min(int(screen.height() * 0.8), 700)
        desired_height = max(desired_height, 500)
        self.setMinimumSize(1000, 500)
        self.resize(1200, desired_height)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint
        )
        self.current_user = current_user
        self.expense_service = ExpenseService()
        self.expenses = []
        self._start_date = start_date
        self._end_date = end_date
        self._filter_active = False
        self.init_ui()
        
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        
        if self._start_date is not None and self._end_date is not None:
            self.start_eth_date.setDate(QDate(self._start_date.year, self._start_date.month, self._start_date.day))
            self.end_eth_date.setDate(QDate(self._end_date.year, self._end_date.month, self._end_date.day))
            self._filter_active = True
            self.apply_filter()
        else:
            # self._filter_active = False
            self.load_all_expenses()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Summary cards container
        self.cards_container = QWidget()
        cards_layout = QHBoxLayout(self.cards_container)
        cards_layout.setSpacing(20)
        self.summary_cards = {}
        card_info = [
            ("Total Expenses", "$0.00", "#e74c3c"),
            ("Number of Transactions", "0", "#3498db"),
            ("Average per Day", "$0.00", "#f39c12")
        ]
        for title, value, color in card_info:
            card = self._create_summary_card(title, value, color)
            cards_layout.addWidget(card)
            self.summary_cards[title] = card
        main_layout.addWidget(self.cards_container)

        # Ethiopian date filter row (range)
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 10, 0, 10)

        start_label = QLabel("Start Ethiopian Date:")
        self.start_eth_date = EthiopianDateEdit()
        end_label = QLabel("End Ethiopian Date:")
        self.end_eth_date = EthiopianDateEdit()

        # Set default to current date for both (will show all expenses initially anyway)
        current_qdate = QDate.currentDate()
        self.start_eth_date.setDate(current_qdate)
        self.end_eth_date.setDate(current_qdate)

        self.apply_btn = QPushButton("Apply Filter")
        self.apply_btn.clicked.connect(self.apply_filter)

        filter_layout.addWidget(start_label)
        filter_layout.addWidget(self.start_eth_date)
        filter_layout.addWidget(end_label)
        filter_layout.addWidget(self.end_eth_date)
        filter_layout.addWidget(self.apply_btn)
        filter_layout.addStretch()

        main_layout.addWidget(filter_widget)

        self.business_only_cb = QCheckBox("Show only business expenses")
        self.business_only_cb.setChecked(True)   # default business only
        self.business_only_cb.stateChanged.connect(self.on_business_only_toggled)
        filter_layout.addWidget(self.business_only_cb)
        filter_layout.addStretch()  

        # Loading indicator
        self.loading_label = QLabel("Loading expenses, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.hide()
        main_layout.addWidget(self.loading_label)

        # Tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget, 1)

        # Tab 1: Expense List (table) - with updated styling
        self.expense_tab = QWidget()
        tab1_layout = QVBoxLayout(self.expense_tab)
        self.table = QTableWidget()
        headers = ["ID", "Date (Ethiopian)", "Category", "Amount", "Payment Method", "Bank Account", "Notes", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnHidden(0, True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self.table.setColumnWidth(7, 120) 

        self.table.setAlternatingRowColors(True)
        
        # Updated styling matching AllSalesOverviewDialog
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
        
        tab1_layout.addWidget(self.table)
        self.tab_widget.addTab(self.expense_tab, "Expense List")

        # Tab 2: Category Analysis - with updated styling matching expense table
        self.analysis_tab = QWidget()
        tab2_layout = QVBoxLayout(self.analysis_tab)
        self.category_table = QTableWidget()
        cat_headers = ["Category", "Total Amount", "Percentage", "Visual"]
        self.category_table.setColumnCount(len(cat_headers))
        self.category_table.setHorizontalHeaderLabels(cat_headers)
        cat_header = self.category_table.horizontalHeader()
        cat_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        cat_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        cat_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        cat_header.setSectionResizeMode(3, QHeaderView.Stretch)
        
        self.category_table.setAlternatingRowColors(True)
        
        # Apply same font and row height to category table
        self.category_table.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.category_table.verticalHeader().setDefaultSectionSize(55)
        
        self.category_table.setStyleSheet("""
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
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        tab2_layout.addWidget(self.category_table)
        self.tab_widget.addTab(self.analysis_tab, "Category Analysis")


    def _create_summary_card(self, title, value, color_hex):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 1px solid #E0E0E0;
                min-width: 180px;
                max-width: 220px;
            }}
        """)
        card.setFixedHeight(100)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(title)
        header.setStyleSheet(f"""
            QLabel {{
                background-color: {color_hex};
                color: white;
                font-weight: bold;
                padding: 10px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 12px;
            }}
        """)
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))

        value_label = QLabel(value)
        value_label.setObjectName("value_label")
        value_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #2c3e50;
                padding: 15px 10px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFont(QFont("Segoe UI", 14, QFont.Bold))

        layout.addWidget(header)
        layout.addWidget(value_label)
        return card

    def load_all_expenses(self):
        """Load all non-deleted expenses without date filter."""
        self._filter_active = False
        self.loading_label.show()
        self.table.hide()
        self.category_table.hide()
        self.cards_container.hide()
        self.apply_btn.setEnabled(False)

        self.thread = QThread()
        show_business = self.business_only_cb.isChecked()   # True = business, False = personal
        self.worker = Worker(self._fetch_all_expenses, show_business)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_all_expenses(self, show_business: bool = True):
        """Fetch all non-deleted expenses, filtering by business/personal."""
        from sqlalchemy.orm import joinedload
        from models.expense import Expense
        from services.base_service import get_session

        with get_session() as session:
            query = session.query(Expense).options(
                joinedload(Expense.category),
                joinedload(Expense.bank_account)
            ).filter(
                Expense.is_deleted == False
            )
            # Always apply a filter
            if show_business:
                query = query.filter(Expense.is_personal == False)  # business
            else:
                query = query.filter(Expense.is_personal == True)   # personal
            return query.order_by(Expense.created_at.desc()).all()

    def apply_filter(self):
        """Apply date filter based on Ethiopian date range."""
        self._filter_active = True
        # Get Gregorian dates from EthiopianDateEdit widgets
        start_qdate = self.start_eth_date.date()
        end_qdate = self.end_eth_date.date()
        
        start_g = start_qdate.toPython()
        end_g = end_qdate.toPython()
        
        if start_g > end_g:
            start_g, end_g = end_g, start_g
        
        end_g = end_g + timedelta(days=1)

        # Show loading indicator, hide other widgets
        self.loading_label.show()
        self.table.hide()
        self.category_table.hide()
        self.cards_container.hide()
        self.apply_btn.setEnabled(False)

        # Start background thread
        self.thread = QThread()
        business_only = self.business_only_cb.isChecked() if hasattr(self, 'business_only_cb') else True
        self.worker = Worker(self._fetch_expenses, start_g, end_g, business_only)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _fetch_expenses(self, start_date: date, end_date: date, show_business: bool = True):
        """Fetch expenses within a date range, filtered by business/personal."""
        from sqlalchemy.orm import joinedload
        from models.expense import Expense
        from services.base_service import get_session

        with get_session() as session:
            query = session.query(Expense).options(
                joinedload(Expense.category),
                joinedload(Expense.bank_account)
            ).filter(
                Expense.is_deleted == False,
                Expense.date >= start_date,
                Expense.date < end_date
            )
            if show_business:
                query = query.filter(Expense.is_personal == False)
            else:
                query = query.filter(Expense.is_personal == True)
            return query.order_by(Expense.created_at.asc()).all()

    def _on_data_loaded(self, expenses):
        """Handle loaded expense data (both all expenses and filtered)."""
        self.expenses = expenses

        # Compute totals
        total_amount = sum(e.amount for e in self.expenses)
        count = len(self.expenses)
        
        # Calculate average per day based on actual date range of expenses
        if self.expenses:
            dates = [e.created_at for e in self.expenses]
            min_date = min(dates)
            max_date = max(dates)
            days = (max_date - min_date).days + 1
            avg_per_day = total_amount / days if days > 0 else 0.0
        else:
            avg_per_day = 0.0

        # Update summary cards
        self.summary_cards["Total Expenses"].findChild(QLabel, "value_label").setText(f"${total_amount:,.2f}")
        self.summary_cards["Number of Transactions"].findChild(QLabel, "value_label").setText(str(count))
        self.summary_cards["Average per Day"].findChild(QLabel, "value_label").setText(f"${avg_per_day:,.2f}")

        self.populate_table()
        self.populate_category_analysis()

        # Hide loading, show widgets
        self.loading_label.hide()
        self.table.show()
        self.category_table.show()
        self.cards_container.show()
        self.apply_btn.setEnabled(True)

    def _on_error(self, error):
        """Handle error during data loading."""
        logger.error(f"Error loading expenses: {error}")
        self.loading_label.setText(f"Error loading data: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load expense data:\n{error}")
        self.loading_label.hide()
        self.table.show()
        self.category_table.show()
        self.cards_container.show()
        self.apply_btn.setEnabled(True)

    def populate_table(self):
        """Populate the expense list table with actions column."""
        self.table.setRowCount(len(self.expenses))
        for row, exp in enumerate(self.expenses):
            # Hidden ID (col 0)
            id_item = QTableWidgetItem(str(exp.id))
            self.table.setItem(row, 0, id_item)
            
            # Ethiopian date (col 1)
            exp_date = exp.date if exp.date else exp.created_at   # fallback just in case
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(exp_date)
            date_str = f"{eth_day:02d}/{eth_month:02d}/{eth_year:04d}"
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 1, date_item)

            # Category (col 2)
            category_name = exp.category.name if exp.category else "N/A"
            cat_item = QTableWidgetItem(category_name)
            cat_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 2, cat_item)

            # Amount (col 3)
            amount_item = QTableWidgetItem(f"${exp.amount:,.2f}")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, amount_item)

            # Payment Method (col 4)
            payment_method = exp.payment_method.value.capitalize() if exp.payment_method else "N/A"
            payment_item = QTableWidgetItem(payment_method)
            payment_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 4, payment_item)

            # Bank Account (col 5)
            bank_display = ""
            if exp.bank_account:
                bank_display = f"{exp.bank_account.bank_name} - {exp.bank_account.account_name}"
                if exp.bank_account.account_number:
                    bank_display += f" ({exp.bank_account.account_number[-4:]})"
            bank_item = QTableWidgetItem(bank_display)
            bank_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 5, bank_item)

            # Notes (col 6)
            notes_item = QTableWidgetItem(exp.notes or "")
            notes_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.table.setItem(row, 6, notes_item)

            # Actions (col 7) - Create buttons
            actions_widget = self.create_action_buttons(exp)
            self.table.setCellWidget(row, 7, actions_widget)

        self.table.resizeRowsToContents()
    
    def create_action_buttons(self, expense):
        """Create Edit and Delete buttons for an expense row."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        # Edit button
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(40, 40)
        edit_btn.setToolTip("Edit Expense")
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1e8449; }
        """)
        edit_btn.clicked.connect(lambda checked, e=expense: self.edit_expense(e))

        # Delete button
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(40, 40)
        delete_btn.setToolTip("Delete Expense")
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
        delete_btn.clicked.connect(lambda checked, e=expense: self.delete_expense(e))

        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)

        return widget
    
    def edit_expense(self, expense):
        """Open dialog to edit the selected expense."""
        from ui.pages.expense_dialog import ExpenseDialog
        
        dlg = ExpenseDialog(self, expense=expense, read_only=False)
        if dlg.exec():
            # Apply the changes via the service
            if dlg.update_data:
                try:
                    updated = self.expense_service.update(expense.id, dlg.update_data)
                    if updated:
                        QMessageBox.information(self, "Success", "Expense updated successfully.")
                    else:
                        QMessageBox.critical(self, "Error", "Failed to update expense.")
                        return  # Don't refresh if update failed
                except Exception as e:
                    logger.error(f"Error updating expense: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to update expense: {str(e)}")
                    return
            # Refresh the data
            try:
                if self._start_date is not None and self._end_date is not None:
                    self.apply_filter()
                else:
                    self.load_all_expenses()
            except Exception as e:
                logger.error(f"Error refreshing after edit: {e}")
                QMessageBox.warning(self, "Warning", "Expense saved but failed to refresh the list.")

    def delete_expense(self, expense):
        """Delete the selected expense."""
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion",
            f"Are you sure you want to delete this expense for ${expense.amount:,.2f}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if self.expense_service.delete_with_transaction(expense.id):
                    QMessageBox.information(self, "Success", "Expense deleted successfully.")
                    # Refresh the data
                    if self._start_date is not None and self._end_date is not None:
                        self.apply_filter()
                    else:
                        self.load_all_expenses()
                else:
                    QMessageBox.critical(self, "Error", "Failed to delete expense.")
            except Exception as e:
                logger.error(f"Error deleting expense: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete expense: {str(e)}")

    def populate_category_analysis(self):
        """Group expenses by category, compute totals and percentages, show with visual bar."""
        category_totals = defaultdict(float)
        for exp in self.expenses:
            cat_name = exp.category.name if exp.category else "Uncategorized"
            category_totals[cat_name] += exp.amount

        total = sum(category_totals.values())
        if total == 0:
            self.category_table.setRowCount(1)
            no_data_item = QTableWidgetItem("No expenses in this period")
            no_data_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.category_table.setItem(0, 0, no_data_item)
            
            amount_item = QTableWidgetItem("$0.00")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.category_table.setItem(0, 1, amount_item)
            
            percent_item = QTableWidgetItem("0%")
            percent_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            percent_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.category_table.setItem(0, 2, percent_item)
            return

        # Sort by total descending
        sorted_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        self.category_table.setRowCount(len(sorted_cats))

        for row, (cat_name, amount) in enumerate(sorted_cats):
            percentage = (amount / total) * 100

            # Category name
            cat_item = QTableWidgetItem(cat_name)
            cat_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            self.category_table.setItem(row, 0, cat_item)
            
            # Amount
            amount_item = QTableWidgetItem(f"${amount:,.2f}")
            amount_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.category_table.setItem(row, 1, amount_item)
            
            # Percentage
            percent_item = QTableWidgetItem(f"{percentage:.1f}%")
            percent_item.setFont(QFont("Segoe UI", 13, QFont.Bold))
            percent_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.category_table.setItem(row, 2, percent_item)

            # Visual progress bar
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(int(percentage))
            progress.setFormat(f"{percentage:.1f}%")
            progress.setStyleSheet("""
                QProgressBar {
                    border-radius: 4px;
                    text-align: center;
                    background-color: #ecf0f1;
                }
                QProgressBar::chunk {
                    background-color: #3498db;
                    border-radius: 4px;
                }
            """)
            self.category_table.setCellWidget(row, 3, progress)

        self.category_table.resizeRowsToContents()
        self.category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
    
    def on_business_only_toggled(self):
        """Reload data using the current mode (all or filtered)."""
        if self._filter_active:
            self.apply_filter()
        else:
            self.load_all_expenses()