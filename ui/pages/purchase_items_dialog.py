from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class PurchaseItemsDialog(QDialog):
    def __init__(self, parent, title, purchase, current_user=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 400)
        self.purchase = purchase
        self.current_user = current_user
        self.init_ui()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        headers = ["Product", "Qty (Packs)", "Dozen", "Unit Price (per piece)", "Total"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 8px;
                font-weight: bold;
                border: none;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFont(QFont("Segoe UI", 11))
        self.table.verticalHeader().setDefaultSectionSize(40)

        self.populate_table()
        layout.addWidget(self.table)

        btn_close = QPushButton("Close")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #2c3e50;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        btn_close.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(btn_close)
        layout.addLayout(button_layout)

    def populate_table(self):
        items = []

        if self.purchase.batches:
            for batch in self.purchase.batches:
                if batch.is_deleted:
                    continue
                product = batch.product
                product_name = product.name if product else "Unknown"
                pack_qty = batch.quantity                 # number of packs
                dozen = product.dozen if product and product.dozen else 1
                unit_price = batch.cost_price             # per piece
                total = pack_qty * dozen * unit_price
                items.append({
                    'product_name': product_name,
                    'pack_qty': pack_qty,
                    'dozen': dozen,
                    'unit_price': unit_price,
                    'total': total
                })

        elif self.purchase.items_data:
            # Two possible structures
            if self.purchase.items_data and isinstance(self.purchase.items_data[0], dict) and 'units' in self.purchase.items_data[0]:
                # Legacy: 'units' means total pieces, dozen=1, pack_qty = units
                for raw in self.purchase.items_data:
                    total_pieces = raw.get('units', 0)
                    unit_price = raw.get('unit_price', 0.0)
                    total = raw.get('total', total_pieces * unit_price)
                    items.append({
                        'product_name': raw.get('product_name', ''),
                        'pack_qty': total_pieces,      # treat as packs if dozen=1
                        'dozen': 1,
                        'unit_price': unit_price,
                        'total': total
                    })
            else:
                # Standard: quantity = packs, dozen, cost_price per piece
                # Accept both key conventions: 'pack_qty'/'quantity' and 'unit_price'/'cost_price'
                for raw in self.purchase.items_data:
                    product_name = raw.get('name') or raw.get('product_name', '')
                    pack_qty = raw.get('pack_qty', raw.get('quantity', 0))
                    dozen = raw.get('dozen', 1)
                    unit_price = raw.get('unit_price', raw.get('cost_price', 0.0))
                    total = raw.get('total', pack_qty * dozen * unit_price)
                    items.append({
                        'product_name': product_name,
                        'pack_qty': pack_qty,
                        'dozen': dozen,
                        'unit_price': unit_price,
                        'total': total
                    })

        if not items:
            self.table.setRowCount(0)
            return

        total_packs = 0
        grand_total = 0.0
        for item in items:
            total_packs += item['pack_qty']
            grand_total += item['total']

        self.table.setRowCount(len(items) + 1)

        for row, item in enumerate(items):
            # Product
            self.table.setItem(row, 0, QTableWidgetItem(item['product_name']))
            # Qty (Packs)
            pack_item = QTableWidgetItem(str(item['pack_qty']))
            pack_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, pack_item)
            # Dozen
            dozen_item = QTableWidgetItem(str(item['dozen']))
            dozen_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, dozen_item)
            # Unit Price
            price_item = QTableWidgetItem(f"${item['unit_price']:,.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, price_item)
            # Total
            total_item = QTableWidgetItem(f"${item['total']:,.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, total_item)

        # Footer row
        footer_row = len(items)
        font = QFont("Segoe UI", 11, QFont.Bold)

        product_footer = QTableWidgetItem("TOTAL")
        product_footer.setFont(font)
        self.table.setItem(footer_row, 0, product_footer)

        packs_footer = QTableWidgetItem(str(total_packs))
        packs_footer.setFont(font)
        packs_footer.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(footer_row, 1, packs_footer)

        # Dozen column empty
        self.table.setItem(footer_row, 2, QTableWidgetItem(""))
        # Unit Price column empty
        self.table.setItem(footer_row, 3, QTableWidgetItem(""))
        total_footer = QTableWidgetItem(f"${grand_total:,.2f}")
        total_footer.setFont(font)
        total_footer.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(footer_row, 4, total_footer)