#!/usr/bin/env python3
import logging
from functools import partial
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame,
    QLineEdit,
    QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QCheckBox,
)
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QFont, QColor
from services.new_product_service import NewProductService
from services.supplier_service import SupplierService
from ui.pages.product_dialog import ProductFormDialog
from ui.pages.product_detail_page import ProductDetailsDialog
from functools import partial

logger = logging.getLogger(__name__)

class ProductManager(QWidget):
    """Complete Product Manager"""
    
    def __init__(self, current_user=None):
        super().__init__()
        self.new_product_service = NewProductService()
        self.supplier_service = SupplierService()
        self.current_user = current_user
        
        # Pagination
        self.current_offset = 0
        self.batch_size = 50
        self.is_loading = False
        self.has_more_products = True
        self.current_search_term = None

        self.selected_product_ids = set()
        self.checkbox_widgets = {}
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.load_products)

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)
        


        self.init_ui()
        self.load_products(initial_load=True)
    
    def refresh(self):
        """Refresh product list"""
        self.selected_product_ids.clear()
        self.checkbox_widgets.clear()
        self.current_offset = 0
        self.has_more_products = True
        self.add_batch_btn.setEnabled(False)
        # self.view_batches_btn.setEnabled(False)
        self.status_label.setText("Ready")
        self.load_products(initial_load=True)
    
    def init_ui(self):
        """Initialize the modern UI cost_value"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ==================== TOOLBAR ====================
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 10, 15, 10)
        toolbar_layout.setSpacing(15)
        
        # Left side: Add Product button
        self.add_btn = QPushButton("➕ Add Product")
        # self.add_btn.setIcon(QIcon.fromTheme("list-add"))
        self.add_btn.setStyleSheet("""
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
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)

        # Add Batch Button (enabled only when product selected)
        self.add_batch_btn = QPushButton("📦 Add Batch")
        self.add_batch_btn.setMinimumSize(120, 40)
        self.add_batch_btn.setEnabled(False)
        self.add_batch_btn.clicked.connect(self.open_add_batch_dialog)
        self.add_batch_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
            QPushButton:hover:enabled {
                background-color: #2980b9;
            }
        """)
        self.add_batch_btn.setVisible(False)

        self.stock_in_btn = QPushButton("📦 Stock In")
        self.stock_in_btn.setMinimumSize(120, 40)
        self.stock_in_btn.setEnabled(True)
        # print(f"DEBUG: stock_in_btn enabled at creation = {self.stock_in_btn.isEnabled()}, user = {self.current_user}")
        self.stock_in_btn.clicked.connect(self.open_stock_in_dialog)
        self.stock_in_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
            QPushButton:hover:enabled {
                background-color: #219a52;
            }
        """)
        self.stock_in_btn.setVisible(False)
        self.credit_purchase_btn = QPushButton("📝 Credit Stock")
        self.credit_purchase_btn.setMinimumSize(120, 40)
        self.credit_purchase_btn.setEnabled(True)
        self.credit_purchase_btn.clicked.connect(self.open_credit_purchase_dialog)
        self.credit_purchase_btn.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9b59b6;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.credit_purchase_btn.setVisible(False)

        # Add to toolbar layout (after add_batch_btn)
        toolbar_layout.addWidget(self.stock_in_btn)
        toolbar_layout.addWidget(self.credit_purchase_btn)

        self.add_btn.clicked.connect(self.show_add_product_dialog)
        
        toolbar_layout.addWidget(self.add_btn)
        toolbar_layout.addWidget(self.add_batch_btn)
        # toolbar_layout.addWidget(self.view_batches_btn)
        toolbar_layout.addStretch()
        
        # Right side: Search field
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(5)
        
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("color: #7f8c8d; font-size: 16px; padding-right: 5px;")
        
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search products by name, description, or batch...")
        self.search_field.setMinimumWidth(300)
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setStyleSheet("""
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
        
        self.search_field.textChanged.connect(self.on_search_text_changed)
        
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_field)
        
        toolbar_layout.addWidget(search_container)
        
        main_layout.addWidget(toolbar)
        
        # ==================== TABLE AREA ====================
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(15, 0, 15, 15)
        table_layout.setSpacing(10)
        
        title = QLabel("📦 Product Inventory")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        table_layout.addWidget(title)
        
        self.table = self.create_product_table()
        table_layout.addWidget(self.table)
        
        self.loading_label = QLabel("Loading products...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px; font-size: 13px;")
        self.loading_label.hide()
        table_layout.addWidget(self.loading_label)
        
        main_layout.addWidget(table_container, 1)
        
        # ==================== STATUS BAR ====================
        status_bar = QWidget()
        status_bar.setFixedHeight(30)
        
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 16px;")
        
        self.stats_label = QLabel("Total: 0 products")
        self.stats_label.setStyleSheet("color: #2c3e50; font-size: 16px;")
        
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.stats_label)
        
        main_layout.addWidget(status_bar)
        # print("DEBUG: init_ui completed")
    
    def open_credit_purchase_dialog(self):
        dialog = ProductFormDialog(
            product_service=self.new_product_service,
            supplier_service=self.supplier_service,
            product=None,
            current_user=self.current_user,
            parent=self,
            mode="credit_stock"
        )
        dialog.product_saved.connect(self.on_product_saved)
        dialog.exec()
    
    def open_stock_in_dialog(self):
        """Open the Stock In dialog (admin only)"""

        dialog = ProductFormDialog(
            product_service=self.new_product_service,
            supplier_service=self.supplier_service,
            product=None,
            current_user=self.current_user,
            parent=self,
            mode="stock_in"
        )
        dialog.product_saved.connect(self.on_product_saved)
        dialog.exec()
    
    def create_product_table(self):
        """Create the products table"""
        table = QTableWidget()
        table.setColumnCount(11)
        table.setHorizontalHeaderLabels([
            "", "Product Name", "Available Stock", "Price", "Unit", "Dozen", "Total Stock", "Batches", "Total Cost", "Actions", "CostValue"
        ])

        font = QFont()
        font.setPointSize(16)      # Larger font size
        font.setBold(True)         # Bold text
        table.setFont(font)
        
        table.setStyleSheet("""
            QTableWidget {
                font-size: 16px;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 10px;
            }
            QHeaderView::section {
                font-size: 16px;
                font-weight: bold;
                padding: 8px;
            }
        """)


        # Configure header
        header = table.horizontalHeader()
        table.setColumnWidth(0, 50)
        table.setColumnWidth(1, 400)
        table.setColumnWidth(2, 150)
        table.setColumnWidth(3, 150)
        table.setColumnWidth(4, 65)
        table.setColumnWidth(5, 80)
        table.setColumnWidth(6, 110)  
        table.setColumnWidth(7, 70)
        table.setColumnWidth(8, 100)
        table.setColumnWidth(9, 150)
        table.setColumnWidth(10, 10)

        table.setColumnHidden(7, True)
        table.setColumnHidden(8, True)
        table.setColumnHidden(10, True)
        

        
        # header.setSectionResizeMode(1, QHeaderView.Stretch)
        
        # Table behavior
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        
        # Connect scroll for infinite loading
        table.verticalScrollBar().valueChanged.connect(self.on_scroll)
        
        return table
    
    # ==================== SEARCH METHODS ====================
    
    def on_search_text_changed(self, text):
        """Handle search text changes with debouncing"""
        self.search_timer.stop()
        if text.strip():
            self.search_timer.start(500)  # 500ms delay for debouncing
        else:
            # If search field is cleared, immediately show all products
            self.current_search_term = None
            self.refresh()
    
    def perform_search(self):
        """Perform the search operation"""
        search_text = self.search_field.text().strip()
        if search_text:
            self.current_search_term = search_text
            self.status_label.setText(f"Searching for: '{search_text}'")
        else:
            self.current_search_term = None
            self.status_label.setText("Ready")
        
        self.refresh()
    
    # ==================== DIALOG METHODS ====================
    
    def show_add_product_dialog(self):
        """Show the add product dialog"""
        dialog = ProductFormDialog(
            self.new_product_service,
            self.supplier_service,
            product=None,
            current_user=self.current_user,
            parent=self,
            mode="new_product"
        )
        dialog.product_saved.connect(self.on_product_saved)
        dialog.setModal(False)
        dialog.show()
    
    def edit_product(self, product):
        """Edit a product by showing edit dialog"""
        product_obj = self.new_product_service.get_by_id(product["id"])
        dialog = ProductFormDialog(
            self.new_product_service,
            self.supplier_service,
            product=product_obj,
            current_user=self.current_user,
            parent=self,
            mode="edit_product"
        )
        dialog.product_saved.connect(self.on_product_saved)
        dialog.exec()
    
    def view_product_details(self, product_data):
        self.product_details_dialog = ProductDetailsDialog(product_data, self.current_user, self)
        self.product_details_dialog.setModal(False)
        self.product_details_dialog.show()
    
    def on_product_saved(self, product):
        """Handle product saved/updated signal"""
        self.refresh()
    
    # ==================== TABLE METHODS ====================
    
    def load_products(self, initial_load=False):
        """Load products into the table with infinite scroll"""
        self.remove_loading_row()
        
        if self.is_loading:
            return
        self.is_loading = True
        
        try:
            if initial_load:
                self.current_offset = 0
                self.has_more_products = True
                self.table.setRowCount(0)
                self.checkbox_widgets.clear()
            
            products = self.new_product_service.get_paginated(
                offset=self.current_offset,
                limit=self.batch_size,
                search=self.current_search_term
            )
            
            if not products:
                self.has_more_products = False
                self.is_loading = False

                if self.current_search_term and self.table.rowCount() == 0:
                    self.show_no_results_message()
                return
            
            product_ids = [p["id"] for p in products]
            # print(f"DEBUG - Product IDs: {product_ids}") 
            cost_totals = self.new_product_service.get_batch_cost_totals(product_ids)
            # print(f"DEBUG - Cost totals: {cost_totals}")  # Debug print

            
            start_row = self.table.rowCount()
            self.table.setRowCount(start_row + len(products))
            
            for i, product in enumerate(products):
                row = start_row + i
                cost_value = cost_totals.get(product["id"], 0.0)
                # print(f"DEBUG - Product {product['id']} ({product['name']}): cost_value = {cost_value}")
                self.add_product_row(row, product, cost_value)
            
            self.current_offset += len(products)
            
            if len(products) < self.batch_size:
                self.has_more_products = False
            
            self.update_stats()
            
            if self.has_more_products:
                self.add_loading_row()
                
        except Exception as e:
            logger.error(f"Error loading products: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load products: {str(e)}")
        finally:
            self.is_loading = False
    
    def show_no_results_message(self):
        """Show a message when no search results are found"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        no_results_item = QTableWidgetItem(f"No products found for '{self.current_search_term}'")
        no_results_item.setTextAlignment(Qt.AlignCenter)
        no_results_item.setForeground(QColor(100, 100, 100))
        no_results_item.setFont(QFont("Segoe UI", 11))
        
        self.table.setItem(row, 0, no_results_item)
        self.table.setSpan(row, 0, 1, self.table.columnCount())
        self.table.setRowHeight(row, 60)

    def add_product_row(self, row, product, cost_value=0.0):
        """Add a product row to the table"""
        # Checkbox column
        checkbox_widget = QWidget()
        checkbox_layout = QHBoxLayout(checkbox_widget)
        checkbox_layout.setContentsMargins(10, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignCenter)

        checkbox = QCheckBox()
        product_id = product["id"]
        is_checked = product_id in self.selected_product_ids
        checkbox.setChecked(is_checked)
        self.checkbox_widgets[product_id] = checkbox
        checkbox.stateChanged.connect(
            partial(self.on_checkbox_changed, product_id=product_id)
        )
        checkbox_layout.addWidget(checkbox)
        self.table.setCellWidget(row, 0, checkbox_widget)

        # Product name label – use larger bold font (24pt)
        product_name = product["name"]
        name_label = QLabel(product_name)
        name_font = QFont("Segoe UI", 12, QFont.Bold)
        name_label.setFont(name_font)
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        name_label.setFrameStyle(QFrame.NoFrame)
        
        item_font = QFont("Segoe UI", 12, QFont.Bold)


        # Calculate height based on the larger font
        font_metrics = name_label.fontMetrics()
        col_width = self.table.columnWidth(1) - 10
        text_rect = font_metrics.boundingRect(
            0, 0, col_width, 0,
            Qt.TextWordWrap | Qt.AlignLeft,
            product_name
        )
        # Original minimum was 45, then doubled → minimum now 90
        original_height = max(45, text_rect.height() + 15)
        height = original_height * 2
        name_label.setFixedHeight(height)

        if self.current_search_term and self.current_search_term.lower() in product_name.lower():
            name_label.setStyleSheet("font-weight: bold; background-color: #ffff99;")
        self.table.setCellWidget(row, 1, name_label)

        # Stock Quantity (inherits table font – 24pt bold)
        stock_item = QTableWidgetItem(str(product["stock"]))
        stock_item.setTextAlignment(Qt.AlignCenter)
        stock_item.setFont(item_font)
        if product["stock"] <= 10:
            stock_item.setForeground(QColor("#e74c3c"))
        else:
            stock_item.setForeground(QColor("#27ae60"))
        self.table.setItem(row, 2, stock_item)

        # Price
        price_item = QTableWidgetItem(f"${product['price']:.2f}")
        price_item.setFont(item_font)
        self.table.setItem(row, 3, price_item)

        # Unit
        unit_item = QTableWidgetItem(product["unit"] or "")
        unit_item.setFont(item_font)
        self.table.setItem(row, 4, unit_item)

        # Dozen
        dozen_item = QTableWidgetItem(str(product["dozen"]))
        dozen_item.setTextAlignment(Qt.AlignCenter)
        dozen_item.setFont(item_font)
        self.table.setItem(row, 5, dozen_item)

        # Total Quantity
        total_quantity_item = QTableWidgetItem(str(product["total_quantity"]))
        total_quantity_item.setTextAlignment(Qt.AlignCenter)
        total_quantity_item.setFont(item_font)
        self.table.setItem(row, 6, total_quantity_item)

        batch_item = QTableWidgetItem(str(product["total_batches"]))
        batch_item.setTextAlignment(Qt.AlignCenter)
        batch_item.setFont(item_font)
        self.table.setItem(row, 7, batch_item)

        cost_display_item = QTableWidgetItem(f"${cost_value * product['dozen']:.2f}")
        cost_display_item.setTextAlignment(Qt.AlignCenter)
        cost_display_item.setFont(item_font)
        self.table.setItem(row, 8, cost_display_item)

        # Action Buttons (unchanged size)
        actions_widget = self.create_action_buttons(product)
        self.table.setCellWidget(row, 9, actions_widget)

        cost_item = QTableWidgetItem()
        cost_item.setText(f"{cost_value:.2f}")
        cost_item.setTextAlignment(Qt.AlignCenter)
        cost_item.setData(Qt.UserRole, float(cost_value))
        self.table.setItem(row, 10, cost_item)

        self.table.setRowHeight(row, height)
    
    def create_action_buttons(self, product):
        """Create action buttons for a product row"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(3)

        # View Details button
        view_btn = QPushButton("👁️")
        view_btn.setFixedSize(45, 45)          # 30 → 45
        view_btn.setFont(QFont("Segoe UI", 20))
        view_btn.setToolTip("View Product Details")
        view_btn.clicked.connect(partial(self.view_product_details, product))
        
        # Edit button
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(45, 45)
        edit_btn.setFont(QFont("Segoe UI", 20))
        edit_btn.setToolTip("Edit Product (Admin only)")
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
            edit_btn.setToolTip("Edit Product - Admin access required")
        else:
            edit_btn.clicked.connect(partial(self.edit_product, product))
                
        # Delete button
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(45, 45)
        delete_btn.setEnabled(False)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                color: #bdc3c7;
                border: 1px solid #ecf0f1;
                border-radius: 4px;
                }
        """)
        delete_btn.setFont(QFont("Segoe UI", 20))
        delete_btn.setToolTip("Delete Product (Admin only)")
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
            delete_btn.setToolTip("Delete Product - Admin access required")
        else:
            delete_btn.clicked.connect(partial(self.delete_product, product))
        
        layout.addWidget(view_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        
        return widget
    
    def add_loading_row(self):
        """Add a loading indicator row"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        loading_item = QTableWidgetItem("Loading more products...")
        loading_item.setTextAlignment(Qt.AlignCenter)
        loading_item.setForeground(QColor(100, 100, 100))
        
        self.table.setItem(row, 0, loading_item)
        self.table.setSpan(row, 0, 1, self.table.columnCount())
    
    def on_checkbox_changed(self, state, product_id):
        """Handle checkbox state change"""
        if not isinstance(product_id, int):
            try:
                product_id = int(product_id)
            except ValueError:

                return
        if state == 2:
            self.selected_product_ids.add(product_id)

        else:
            self.selected_product_ids.discard(product_id)

    
        is_single_selection = len(self.selected_product_ids) == 1

        self.add_batch_btn.setEnabled(is_single_selection)
        # self.view_batches_btn.setEnabled(is_single_selection)

        count = len(self.selected_product_ids)
        if count == 0:
            self.status_label.setText("No product selected")
        elif count == 1:
            product_id = next(iter(self.selected_product_ids))
            self.status_label.setText(f"Selected product ID: {product_id}")
        else:
            self.status_label.setText(f"{count} products selected")

    
    def remove_loading_row(self):
        """Remove the loading indicator row"""
        row_count = self.table.rowCount()
        if row_count > 0:
            last_item = self.table.item(row_count - 1, 0)
            if last_item and last_item.text() == "Loading more products...":
                self.table.removeRow(row_count - 1)
    
    def on_scroll(self, value):
        """Handle scroll events for infinite loading - robust solution"""
        if not self.has_more_products or self.is_loading:
            return
        
        scroll_bar = self.table.verticalScrollBar()

        current_pos = scroll_bar.value()
        max_pos = scroll_bar.maximum()
        

        if max_pos == 0 and self.has_more_products:
            if not self.scroll_timer.isActive():
                self.scroll_timer.start(100)
            return
        
        if max_pos > 0:
            scroll_percentage = current_pos / max_pos if max_pos > 0 else 0
            
         
            pixel_threshold = 150  # Pixels from bottom
            percentage_threshold = 0.85  # 85% scrolled
            
           
            near_bottom_by_pixels = current_pos >= max_pos - pixel_threshold
            near_bottom_by_percentage = scroll_percentage >= percentage_threshold
            
            
            if near_bottom_by_pixels or near_bottom_by_percentage:
                if not self.scroll_timer.isActive():
                    self.scroll_timer.start(100)
    
    def delete_product(self, product):
        """Delete a product with confirmation"""
        if not self.is_user_admin():
            QMessageBox.warning(
                self,
                "Permission Denied", 
                "Only administrators can delete products.\n"
                "Please contact your system administrator."
            )
            return

        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            f"Are you sure you want to delete '{product['name']}'?\n\n"
            f"⚠️ This will also delete:\n"
            f"• All batches ({product.get('total_batches', 0)} batches)\n"
            f"• All transaction history\n\n"
            f"This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # Default to "No" for safety
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.status_label.setText(f"Deleting {product['name']}...")

                success = self.new_product_service.delete_cascading(product["id"])

                if success:
                    self.refresh()
                else:
                    QMessageBox.warning(
                        self, 
                        "Error", 
                        f"Failed to delete '{product['name']}'.\n"
                        f"The product may have already been deleted or is in use."
                    )
                
            except Exception as e:
                logger.error(f"Error deleting product: {str(e)}")
                QMessageBox.critical(
                    self, 
                    "Error", 
                    f"An unexpected error occurred while deleting '{product['name']}':\n{str(e)}"
                )
            finally:
                self.status_label.setText("Ready")
    
    def update_stats(self):
        """Update statistics in status bar"""
        total_rows = self.table.rowCount()
        
        if total_rows == 0:
            self.stats_label.setText("Total: 0 products | Cost Value: $0.00 | Low Stock: 0")
            return
            
        total_value = 0.0
        low_stock = 0
        
        for row in range(total_rows):
            # Get items from each column
            quantity_item = self.table.item(row, 2)  # Available Stock
            dozen_item = self.table.item(row, 5)     # Dozen
            cost_item = self.table.item(row, 10)      # Hidden cost column
        
            
            if quantity_item and dozen_item and cost_item:
                
                # Check UserRole data
                user_role_data = cost_item.data(Qt.UserRole)
                
                try:
                    # Parse quantity
                    quantity_text = quantity_item.text()
                    quantity = int(quantity_text) if quantity_text else 0
                    
                    # Parse dozen
                    dozen_text = dozen_item.text()
                    dozen = float(dozen_text) if dozen_text else 1
                    
                    # Get cost value - first try UserRole, then parse text
                    cost_value = cost_item.data(Qt.UserRole)
                    if cost_value is None:
                        cost_text = cost_item.text()
                        cost_value = float(cost_text) if cost_text else 0.0
                    
                    # Add to total value
                    total_value += cost_value * dozen
                    
                    # Check for low stock
                    if quantity <= 10:
                        low_stock += 1
                        
                except (ValueError, AttributeError, TypeError) as e:
                    continue
            else:
                pass
        
        # Format the status text
        if self.current_search_term:
            stats_text = f"Found: {total_rows} products | Cost Value: ${total_value:,.2f} | Low Stock: {low_stock}"
        else:
            stats_text = f"Total: {total_rows} products | Cost Value: ${total_value:,.2f} | Low Stock: {low_stock}"
        
        self.stats_label.setText(stats_text)
    

    def open_add_batch_dialog(self):
        if not self.selected_product_ids:
            QMessageBox.warning(self, "No Selection", "Please select a product first")
            return
        
        if len(self.selected_product_ids) > 1:
            QMessageBox.warning(self, "Multiple selection", "Please select only one product to add a batch")
            return
        
        product_id = next(iter(self.selected_product_ids))

        try:
            product = self.new_product_service.get_by_id(product_id)
            if not product:
                QMessageBox.warning(self, "Error", "Selected product not found.")
                return
            dialog = ProductFormDialog(
                product_service=self.new_product_service,
                supplier_service=self.supplier_service,
                product=product,
                current_user=self.current_user,
                parent=self,
                mode="add_batch"
            )

            dialog.product_saved.connect(self.on_product_saved)
            dialog.setModal(False)
            dialog.show()
            self.refresh()
        except Exception as e:
            logger.error(f"Error opening add batch dialog: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to open dialog: {str(e)}")
    
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
        # print(f"DEBUG: is_user_admin() returning {ret}")
        return ret
    
    def closeEvent(self, event):
        self.scroll_timer.stop()
        self.search_timer.stop()
        super().closeEvent(event)