#!/usr/bin/env python3
import logging
from functools import partial
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame,
    QLineEdit,
    QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QCheckBox, QSizePolicy,
)
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QFont, QColor
from ui.components import theme
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
        """Build a clean, professional product management interface."""
        self.stat_cards = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # ==================== KPI CARDS ====================
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(14)

        for key, title, value, color, icon in (
            ("products", "Products Listed", "0", theme.PRIMARY, "📦"),
            ("cost", "Cost Value", "$0.00", theme.SUCCESS, "💰"),
            ("low", "Low Stock", "0", theme.WARNING, "⚠️"),
            ("out", "Out of Stock", "0", theme.DANGER, "🚫"),
        ):
            card = theme.StatCard(title, value, color, icon)
            self.stat_cards[key] = card
            stats_row.addWidget(card)

        root.addLayout(stats_row)

        # ==================== TOOLBAR ====================
        toolbar = theme.card_frame()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(10)

        self.add_btn = QPushButton("➕  Add Product")
        self.add_btn.clicked.connect(self.show_add_product_dialog)
        theme.style_filled(self.add_btn, theme.PRIMARY, theme.PRIMARY_DARK)

        self.stock_in_btn = QPushButton("📥  Stock In")
        self.stock_in_btn.clicked.connect(self.open_stock_in_dialog)
        theme.style_filled(self.stock_in_btn, theme.SUCCESS, theme.SUCCESS_DARK)

        self.credit_purchase_btn = QPushButton("🧾  Credit Stock")
        self.credit_purchase_btn.clicked.connect(self.open_credit_purchase_dialog)
        theme.style_filled(self.credit_purchase_btn, theme.PURPLE, theme.PURPLE_DARK)

        self.add_batch_btn = QPushButton("📦  Add Batch")
        self.add_batch_btn.setEnabled(False)
        self.add_batch_btn.setToolTip("Select a single product to add a new batch")
        self.add_batch_btn.clicked.connect(self.open_add_batch_dialog)
        theme.style_filled(self.add_batch_btn, theme.SLATE, theme.SLATE_DARK)

        for button in (self.add_btn, self.stock_in_btn,
                       self.credit_purchase_btn, self.add_batch_btn):
            toolbar_layout.addWidget(button)
        toolbar_layout.addStretch()

        search_container = QFrame()
        search_container.setObjectName("searchBox")
        search_container.setFixedHeight(38)
        search_container.setStyleSheet(f"""
            QFrame#searchBox {{
                background-color: {theme.CANVAS};
                border: 1px solid {theme.BORDER};
                border-radius: 8px;
            }}
        """)
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(12, 0, 8, 0)
        search_layout.setSpacing(8)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 14px; background: transparent;"
        )

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search products by name or unit...")
        self.search_field.setMinimumWidth(280)
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setFrame(False)
        self.search_field.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                background: transparent;
                font-size: 13px;
                color: {theme.TEXT};
                padding: 8px 0;
            }}
        """)
        self.search_field.textChanged.connect(self.on_search_text_changed)

        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_field)
        toolbar_layout.addWidget(search_container)

        root.addWidget(toolbar)

        # ==================== TABLE CARD ====================
        table_card = theme.card_frame()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 6)
        table_layout.setSpacing(0)

        table_header, self.count_label = theme.card_section_header("Product Inventory", "0 items")

        self.table = self.create_product_table()
        table_layout.addWidget(table_header)
        table_layout.addWidget(self.table)

        self.loading_label = QLabel("Loading products...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet(
            f"color: {theme.MUTED}; font-style: italic; padding: 10px; font-size: 12px;"
        )
        self.loading_label.hide()
        table_layout.addWidget(self.loading_label)

        root.addWidget(table_card, 1)

        # ==================== STATUS BAR ====================
        status_bar = theme.card_frame()
        status_bar.setFixedHeight(34)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(14, 0, 14, 0)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 12px; background: transparent;"
        )

        self.stats_label = QLabel("Total: 0 products")
        self.stats_label.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 12px; background: transparent;"
        )

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.stats_label)

        root.addWidget(status_bar)
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
        """Create the products table."""
        table = QTableWidget()
        table.setColumnCount(11)
        table.setHorizontalHeaderLabels([
            "", "PRODUCT", "AVAILABLE STOCK", "PRICE", "UNIT",
            "DOZEN", "TOTAL STOCK", "BATCHES", "TOTAL COST", "ACTIONS", "COST"
        ])

        header = theme.style_table(table)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        table.setColumnWidth(0, 46)
        table.setColumnWidth(2, 150)
        table.setColumnWidth(3, 130)
        table.setColumnWidth(4, 80)
        table.setColumnWidth(5, 80)
        table.setColumnWidth(6, 120)
        table.setColumnWidth(9, 212)

        theme.align_header(table, 1, Qt.AlignLeft | Qt.AlignVCenter)
        theme.align_header(table, 3, Qt.AlignRight | Qt.AlignVCenter)

        table.setColumnHidden(7, True)
        table.setColumnHidden(8, True)
        table.setColumnHidden(10, True)

        table.setSelectionMode(QTableWidget.SingleSelection)

        table.verticalScrollBar().valueChanged.connect(self.on_scroll)

        return table
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
        """Add a styled product row to the table."""
        product_id = product["id"]

        # ---- Selection checkbox ----
        checkbox_widget = QWidget()
        checkbox_widget.setObjectName("cellWidget")
        checkbox_widget.setStyleSheet("#cellWidget { background: transparent; }")
        checkbox_layout = QHBoxLayout(checkbox_widget)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignCenter)

        checkbox = QCheckBox()
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setChecked(product_id in self.selected_product_ids)
        checkbox.setStyleSheet("""
            QCheckBox::indicator {
                width: 17px;
                height: 17px;
                border: 2px solid #cbd5e1;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:hover {
                border-color: #94a3b8;
            }
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border-color: #3498db;
            }
        """)
        self.checkbox_widgets[product_id] = checkbox
        checkbox.stateChanged.connect(partial(self.on_checkbox_changed, product_id=product_id))
        checkbox_layout.addWidget(checkbox)
        self.table.setCellWidget(row, 0, checkbox_widget)

        # ---- Product name ----
        name = product["name"]
        name_item = QTableWidgetItem(name)
        name_item.setToolTip(name)
        name_item.setFont(QFont(theme.FONT, 10, QFont.DemiBold))
        name_item.setForeground(QColor(theme.TEXT))
        if self.current_search_term and self.current_search_term.lower() in name.lower():
            name_item.setForeground(QColor(theme.PRIMARY))
        self.table.setItem(row, 1, name_item)

        # ---- Available stock badge ----
        self.table.setCellWidget(row, 2, theme.stock_badge(product["stock"]))

        # ---- Price ----
        price_item = QTableWidgetItem(f"${product['price']:,.2f}")
        price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        price_item.setFont(QFont(theme.FONT, 10, QFont.DemiBold))
        price_item.setForeground(QColor(theme.TEXT))
        self.table.setItem(row, 3, price_item)

        # ---- Unit ----
        unit_item = QTableWidgetItem(product["unit"] or "—")
        unit_item.setTextAlignment(Qt.AlignCenter)
        unit_item.setForeground(QColor(theme.MUTED))
        self.table.setItem(row, 4, unit_item)

        # ---- Dozen ----
        dozen_item = QTableWidgetItem(theme.format_number(product["dozen"]))
        dozen_item.setTextAlignment(Qt.AlignCenter)
        dozen_item.setForeground(QColor(theme.TEXT))
        self.table.setItem(row, 5, dozen_item)

        # ---- Total stock ----
        total_item = QTableWidgetItem(theme.format_number(product["total_quantity"]))
        total_item.setTextAlignment(Qt.AlignCenter)
        total_item.setForeground(QColor(theme.TEXT))
        self.table.setItem(row, 6, total_item)

        # ---- Hidden batches ----
        batch_item = QTableWidgetItem(str(product["total_batches"]))
        batch_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 7, batch_item)

        # ---- Hidden cost display ----
        cost_display_item = QTableWidgetItem(f"${cost_value * product['dozen']:,.2f}")
        cost_display_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 8, cost_display_item)

        # ---- Action buttons ----
        self.table.setCellWidget(row, 9, self.create_action_buttons(product))

        # ---- Hidden numeric cost + stock (used by update_stats) ----
        cost_item = QTableWidgetItem()
        cost_item.setText(f"{cost_value:.2f}")
        cost_item.setTextAlignment(Qt.AlignCenter)
        cost_item.setData(Qt.UserRole, float(cost_value))
        cost_item.setData(Qt.UserRole + 1, int(product["stock"] or 0))
        self.table.setItem(row, 10, cost_item)

        self.table.setRowHeight(row, theme.ROW_HEIGHT)
    def create_action_buttons(self, product):
        """Create the compact row action buttons."""
        view_btn = theme.action_button("View", "View product details", theme.PRIMARY, 56)
        view_btn.clicked.connect(partial(self.view_product_details, product))

        edit_btn = theme.action_button("Edit", "Edit product", theme.WARNING, 52)
        delete_btn = theme.action_button("Delete", "Delete product", theme.DANGER, 62)

        if self.is_user_admin():
            edit_btn.clicked.connect(partial(self.edit_product, product))
            delete_btn.clicked.connect(partial(self.delete_product, product))
        else:
            edit_btn.setEnabled(False)
            edit_btn.setToolTip("Edit product — admin access required")
            delete_btn.setEnabled(False)
            delete_btn.setToolTip("Delete product — admin access required")

        return theme.action_cell([view_btn, edit_btn, delete_btn])
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
        """Recalculate the KPI cards and the status summary."""
        products_count = 0
        total_value = 0.0
        low_stock = 0
        out_of_stock = 0

        for row in range(self.table.rowCount()):
            cost_item = self.table.item(row, 10)
            if cost_item is None:
                continue

            products_count += 1

            try:
                cost_value = float(cost_item.data(Qt.UserRole) or 0.0)
            except (TypeError, ValueError):
                cost_value = 0.0

            try:
                stock = int(cost_item.data(Qt.UserRole + 1) or 0)
            except (TypeError, ValueError):
                stock = 0

            dozen_item = self.table.item(row, 5)
            try:
                dozen = float(dozen_item.text().replace(",", "")) if dozen_item and dozen_item.text() else 1.0
            except ValueError:
                dozen = 1.0

            total_value += cost_value * dozen

            if stock <= 0:
                out_of_stock += 1
            elif stock <= theme.LOW_STOCK_LIMIT:
                low_stock += 1

        self.stat_cards["products"].set_value(f"{products_count:,}")
        self.stat_cards["cost"].set_value(f"${total_value:,.2f}")
        self.stat_cards["low"].set_value(f"{low_stock:,}")
        self.stat_cards["out"].set_value(f"{out_of_stock:,}")

        prefix = "Found" if self.current_search_term else "Total"
        self.stats_label.setText(
            f"{prefix}: {products_count:,} products   •   "
            f"Cost Value: ${total_value:,.2f}   •   "
            f"Low Stock: {low_stock:,}   •   Out of Stock: {out_of_stock:,}"
        )
        if hasattr(self, "count_label"):
            self.count_label.setText(f"{products_count:,} items")
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