#!/user/bin/env python3
"""
user managment gialog that manage users of the softwere
        -CRUD userS
        -change all passwords
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QTableWidget, QHBoxLayout, QPushButton,
    QLineEdit, QFormLayout, QComboBox, QWidget, QHeaderView, QTableWidgetItem,
    QMessageBox
)
from PySide6.QtGui import QColor
from services.auth_service import AuthService
from models.auth_user import AuthUser
import logging

logger = logging.getLogger(__name__)


class UserManagementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_service = AuthService()
        self.setWindowTitle("User Management")
        self.setFixedSize(700, 500)
        self.setup_ui()
        self.load_users()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.user_list_tab = QWidget()
        self.tabs.addTab(self.user_list_tab, "User Accounts")
        self.setup_user_list_tab()

        self.add_user_tab = QWidget()
        self.tabs.addTab(self.add_user_tab, "Add New User")
        self.setup_add_user_tab()

        self.change_password_tab = QWidget()
        self.tabs.addTab(self.change_password_tab, "Change Password")
        self.setup_change_password_tab()
    
    def setup_user_list_tab(self):
        """
        """
        layout = QVBoxLayout(self.user_list_tab)

        self.users_table = QTableWidget()
        self.users_table.setColumnCount(4)
        self.users_table.setHorizontalHeaderLabels(["ID", "Username", "Role", "Status"])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.users_table)

        btn_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load_users)
        btn_layout.addWidget(self.refresh_btn)

        self.delete_btn = QPushButton("Delete User")
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.delete_btn.clicked.connect(self.delete_user)
        btn_layout.addWidget(self.delete_btn)

        self.toggle_status_btn = QPushButton("Toggle Status")
        self.toggle_status_btn.clicked.connect(self.toggle_user_status)
        btn_layout.addWidget(self.toggle_status_btn)

        layout.addLayout(btn_layout)

    
    def setup_add_user_tab(self):
        """
        """
        layout = QFormLayout(self.add_user_tab)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Password:", self.password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("Comfirm password")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Comfirm password:", self.confirm_password_input)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["admin", "sales_clerk"])
        layout.addRow("Role:", self.role_combo)

        self.add_user_btn = QPushButton("Create User")
        self.add_user_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.add_user_btn.clicked.connect(self.create_user)
        layout.addRow(self.add_user_btn)


    def setup_change_password_tab(self):
        """
        """
        layout = QFormLayout(self.change_password_tab)

        self.change_pw_username_combo = QComboBox()
        layout.addRow("Username:", self.change_pw_username_combo)

        self.current_password_input = QLineEdit()
        self.current_password_input.setPlaceholderText("Enter your admin password")
        self.current_password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Admin Password:", self.current_password_input)

        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("Enter New Password")
        self.new_password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("New Password:", self.new_password_input)

        self.confirm_new_password_input = QLineEdit()
        self.confirm_new_password_input.setPlaceholderText("Confirm new Password")
        self.confirm_new_password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Confirm Password:", self.confirm_new_password_input)

        self.change_pw_btn = QPushButton("Change Password")
        self.change_pw_btn.setStyleSheet("background-color: #2196F3; color: white;")
        self.change_pw_btn.clicked.connect(self.change_user_password)
        layout.addRow(self.change_pw_btn)


    def load_users(self):
        """
        """
        try:
            users = self.auth_service.get_all()
            self.users_table.setRowCount(0)
            self.change_pw_username_combo.clear()

            for user in users:
                row = self.users_table.rowCount()
                self.users_table.insertRow(row)

                self.users_table.setItem(row, 0, QTableWidgetItem(str(user.id)))
                self.users_table.setItem(row, 1, QTableWidgetItem(user.username))
                self.users_table.setItem(row, 2, QTableWidgetItem(user.role))

                status_item = QTableWidgetItem("Active" if not user.is_deleted else "Inactive")
                if user.is_deleted:
                    status_item.setForeground(QColor("red"))
                self.users_table.setItem(row, 3, status_item)
  
                self.change_pw_username_combo.addItem(user.username, user.id)

        except Exception as e:
            logger.error(f"Error loading users: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load users: {str(e)}")


    def create_user(self):
        """
        """
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        role = self.role_combo.currentText()

        if not username or not password:
            QMessageBox.warning(self, "Validation Error", "Username and password are required")
            return
        
        if password != confirm_password:
            QMessageBox.warning(self, "Validation Error", "Passwords do not match")
            return
        
        if len(password) < 4:
            QMessageBox.warning(self, "Validation Error", "Password must be at least 4 characters")
            return
        
        try:
            existing_user = self.auth_service.get_by_username(username)
            if existing_user:
                QMessageBox.warning(self, "Error", f"Username {username} already exists")
                return
            user = AuthUser(username=username, password=self.auth_service.hash_password(password), role=role)
            result = self.auth_service.create(user)
            
            if result:
                QMessageBox.information(self, "Success", f"User '{username}' created successfully")
                self.clear_add_user_form()
                self.load_users()
                # Switch to user list tab
                self.tabs.setCurrentIndex(0)
            else:
                QMessageBox.critical(self, "Error", "Failed to create user")
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create user: {str(e)}")





    def delete_user(self):
        """Soft delete selected user"""
        selected_items = self.users_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a user to delete")
            return
            
        row = selected_items[0].row()
        user_id = int(self.users_table.item(row, 0).text())
        username = self.users_table.item(row, 1).text()
        
        # Prevent self-deletion (you might want to get current user from session)
        # if user_id == current_user_id:
        #     QMessageBox.warning(self, "Error", "You cannot delete your own account")
        #     return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete user '{username}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            try:
                if self.auth_service.delete(user_id):
                    QMessageBox.information(self, "Success", f"User '{username}' deleted successfully")
                    self.load_users()
                else:
                    QMessageBox.critical(self, "Error", "Failed to delete user")
            except Exception as e:
                logger.error(f"Error deleting user: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete user: {str(e)}")


    def toggle_user_status(self):
        """Toggle user active/inactive status"""
        selected_items = self.users_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a user")
            return
            
        row = selected_items[0].row()
        user_id = int(self.users_table.item(row, 0).text())
        username = self.users_table.item(row, 1).text()
        self.users_table.item(row, 3).text()
        
        try:
            user = self.auth_service.get_by_id(user_id)
            if user:
                # Toggle is_deleted status
                user.is_deleted = not user.is_deleted
                if self.auth_service.update(user_id, {"is_deleted": user.is_deleted}):
                    new_status = "inactive" if user.is_deleted else "active"
                    QMessageBox.information(self, "Success", f"User '{username}' is now {new_status}")
                    self.load_users()
                else:
                    QMessageBox.critical(self, "Error", "Failed to update user status")
                    
        except Exception as e:
            logger.error(f"Error toggling user status: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update user status: {str(e)}")

    def change_user_password(self):
        """Change user password (admin function)"""
        username = self.change_pw_username_combo.currentText()
        user_id = self.change_pw_username_combo.currentData()
        current_password = self.current_password_input.text()
        new_password = self.new_password_input.text()
        confirm_new_password = self.confirm_new_password_input.text()

        # Validation
        if not current_password or not new_password:
            QMessageBox.warning(self, "Validation Error", "All password fields are required")
            return
            
        if new_password != confirm_new_password:
            QMessageBox.warning(self, "Validation Error", "New passwords do not match")
            return
            
        if len(new_password) < 4:
            QMessageBox.warning(self, "Validation Error", "New password must be at least 4 characters")
            return

        try:
            # Verify admin password (you might want to get current admin username from session)
            # For now, we'll authenticate with the first admin user found
            admin_user = self.auth_service.get_admin_user()
            if not admin_user or not self.auth_service.check_password(current_password, admin_user.password):
                QMessageBox.warning(self, "Error", "Invalid admin password")
                return

            # Update user password
            if self.auth_service.update_password(user_id, new_password):
                QMessageBox.information(self, "Success", f"Password for '{username}' changed successfully")
                self.clear_change_password_form()
            else:
                QMessageBox.critical(self, "Error", "Failed to change password")
                
        except Exception as e:
            logger.error(f"Error changing password: {e}")
            QMessageBox.critical(self, "Error", f"Failed to change password: {str(e)}")

    def clear_add_user_form(self):
        """Clear the add user form"""
        self.username_input.clear()
        self.password_input.clear()
        self.confirm_password_input.clear()
        self.role_combo.setCurrentIndex(0)

    def clear_change_password_form(self):
        """Clear the change password form"""
        self.current_password_input.clear()
        self.new_password_input.clear()
        self.confirm_new_password_input.clear()