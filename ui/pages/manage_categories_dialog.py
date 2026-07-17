from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QInputDialog
)
from services.expense_category_service import ExpenseCategoryService

class ManageCategoriesDialog(QDialog):
    """
    Dialog to add, edit, and toggle active status of expense categories.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.category_service = ExpenseCategoryService()
        self.setWindowTitle("Manage Expense Categories")
        self.setModal(True)
        self.resize(450, 350)
        self.setup_ui()
        self.load_categories()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Active"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setColumnHidden(0, True)  # Hide ID column
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.add_category)
        btn_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_category)
        btn_layout.addWidget(self.edit_btn)

        self.toggle_btn = QPushButton("Toggle Active")
        self.toggle_btn.clicked.connect(self.toggle_active)
        btn_layout.addWidget(self.toggle_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def load_categories(self):
        """Fetch all categories and populate the table."""
        categories = self.category_service.get_all()
        self.table.setRowCount(0)
        for cat in categories:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(cat.id)))
            self.table.setItem(row, 1, QTableWidgetItem(cat.name))
            self.table.setItem(row, 2, QTableWidgetItem("Yes" if cat.is_active else "No"))

    def get_selected_category_id(self):
        """Return ID of selected category or None."""
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        return int(self.table.item(current_row, 0).text())

    def add_category(self):
        """Prompt for new category name and create if not duplicate."""
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if ok and name.strip():
            existing = self.category_service.get_by_name(name.strip())
            if existing:
                QMessageBox.warning(self, "Duplicate", "A category with that name already exists.")
                return
            data = {'name': name.strip(), 'is_active': True}
            self.category_service.create(data)
            self.load_categories()

    def edit_category(self):
        """Rename selected category."""
        cat_id = self.get_selected_category_id()
        if not cat_id:
            QMessageBox.warning(self, "No Selection", "Please select a category to edit.")
            return
        # Get current name from table
        current_name = self.table.item(self.table.currentRow(), 1).text()
        new_name, ok = QInputDialog.getText(self, "Edit Category", "Category name:", text=current_name)
        if ok and new_name.strip() and new_name != current_name:
            # Check if new name already exists (excluding current)
            existing = self.category_service.get_by_name(new_name.strip())
            if existing and existing.id != cat_id:
                QMessageBox.warning(self, "Duplicate", "Another category with that name already exists.")
                return
            self.category_service.update(cat_id, {'name': new_name.strip()})
            self.load_categories()

    def toggle_active(self):
        """Toggle active status of selected category."""
        cat_id = self.get_selected_category_id()
        if not cat_id:
            QMessageBox.warning(self, "No Selection", "Please select a category to toggle.")
            return
        category = self.category_service.get_by_id(cat_id)
        if category:
            self.category_service.update(cat_id, {'is_active': not category.is_active})
            self.load_categories()