#!/usr/bin/env python3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QWidget, QApplication,
    QLabel, QPushButton, QMessageBox, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtGui import (
    QFont, QPixmap, QIcon, QColor, QPalette, QPainter, 
    QLinearGradient, QCursor, QBrush, QPainterPath
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStyle
from services.auth_service import AuthService
from utils import resource_path

class ModernLoginButton(QPushButton):
    """Custom modern button for login dialog"""
    def __init__(self, text="", icon=None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(45)
        self.setFont(QFont("Segoe UI", 12, QFont.Medium))
        
    def setPrimaryStyle(self):
        """Set primary button style (blue gradient)"""
        primary_normal = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2980b9);
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: 600;
                padding: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2980b9, stop:1 #2573a7);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2573a7, stop:1 #1c5d87);
            }
            QPushButton:disabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #bdc3c7, stop:1 #95a5a6);
                color: #7f8c8d;
            }
        """
        self.setStyleSheet(primary_normal)
    
    def setSecondaryStyle(self):
        """Set secondary button style (gray)"""
        secondary_normal = """
            QPushButton {
                background-color: transparent;
                border: 2px solid #3498db;
                border-radius: 8px;
                color: #3498db;
                font-weight: 600;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(52, 152, 219, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(52, 152, 219, 0.2);
            }
        """
        self.setStyleSheet(secondary_normal)


class ModernLoginLineEdit(QLineEdit):
    """Custom modern line edit for login dialog"""
    def __init__(self, placeholder="", is_password=False, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(50)
        self.setFont(QFont("Segoe UI", 12))
        
        if is_password:
            self.setEchoMode(QLineEdit.Password)
            
        # Add eye icon for password visibility toggle
        if is_password:
            self.toggle_password_btn = QPushButton(self)
            self.toggle_password_btn.setCursor(Qt.PointingHandCursor)
            self.toggle_password_btn.setIcon(QIcon(resource_path("assets/eye_icon.png")))
            self.toggle_password_btn.setIconSize(QSize(20, 20))
            self.toggle_password_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    padding: 0px 8px;
                }
                QPushButton:hover {
                    background: rgba(0, 0, 0, 0.05);
                    border-radius: 4px;
                }
            """)
            self.toggle_password_btn.clicked.connect(self.toggle_password_visibility)
            self.update_button_icon()
            
        self.set_normal_style()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'toggle_password_btn'):
            frame_width = self.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth)  # QStyle.PM_DefaultFrameWidth
            button_size = self.toggle_password_btn.sizeHint()
            self.toggle_password_btn.move(
                self.rect().right() - frame_width - button_size.width() - 10,
                (self.rect().bottom() - button_size.height() + 1) // 2
            )
            
    def set_normal_style(self):
        normal_style = """
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px 15px;
                background-color: white;
                font-size: 14px;
                selection-background-color: #2196F3;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
                background-color: #f8f9fa;
            }
            QLineEdit:disabled {
                background-color: #f5f5f5;
                color: #95a5a6;
                border: 2px solid #e0e0e0;
            }
        """
        self.setStyleSheet(normal_style)
        
    def set_error_style(self):
        error_style = """
            QLineEdit {
                border: 2px solid #e74c3c;
                border-radius: 8px;
                padding: 12px 15px;
                background-color: #fff5f5;
                font-size: 14px;
                selection-background-color: #2196F3;
            }
            QLineEdit:focus {
                border: 2px solid #e74c3c;
                background-color: #fff5f5;
            }
        """
        self.setStyleSheet(error_style)
        
    def toggle_password_visibility(self):
        if self.echoMode() == QLineEdit.Password:
            self.setEchoMode(QLineEdit.Normal)
            self.toggle_password_btn.setIcon(QIcon(resource_path("assets/eye_slash_icon.png")))
        else:
            self.setEchoMode(QLineEdit.Password)
            self.toggle_password_btn.setIcon(QIcon(resource_path("assets/eye_icon.png")))
        self.update_button_icon()
        
    def update_button_icon(self):
        if hasattr(self, 'toggle_password_btn'):
            if self.echoMode() == QLineEdit.Password:
                self.toggle_password_btn.setToolTip("Show password")
            else:
                self.toggle_password_btn.setToolTip("Hide password")


class LoginDialog(QDialog):
    """Modern login dialog matching main window design"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login - Megazen IMS")
        self.setFixedSize(450, 450)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self.logged_in_user = None
        
        # Set window icon
        self.setWindowIcon(QIcon(resource_path("assets/logo.png")))
        
        # Apply modern palette
        self.set_palette()
        
        # Create layout
        self.init_ui()
        
        # Center on screen
        self.center_on_screen()
        
    def set_palette(self):
        """Set modern color palette for the dialog"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(248, 249, 250))
        palette.setColor(QPalette.WindowText, QColor(33, 37, 41))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(233, 236, 239))
        palette.setColor(QPalette.Text, QColor(33, 37, 41))
        palette.setColor(QPalette.Button, QColor(52, 58, 64))
        palette.setColor(QPalette.ButtonText, QColor(248, 249, 250))
        palette.setColor(QPalette.Highlight, QColor(41, 128, 185))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)
        
    def center_on_screen(self):
        """Center the dialog on the screen"""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        
    def init_ui(self):
        """Initialize the modern UI for login dialog"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(0)
        
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)
        
        # Username field
        username_label = QLabel("Username")
        username_label.setFont(QFont("Segoe UI", 11, QFont.Medium))
        username_label.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        
        self.username_input = ModernLoginLineEdit("Enter your username")
        self.username_input.setToolTip("Enter your username")
        
        # Password field
        password_label = QLabel("Password")
        password_label.setFont(QFont("Segoe UI", 11, QFont.Medium))
        password_label.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        
        self.password_input = ModernLoginLineEdit("Enter your password", is_password=True)
        self.password_input.setToolTip("Enter your password")
        
        # Login button
        self.login_button = ModernLoginButton("Sign In")
        self.login_button.setPrimaryStyle()
        self.login_button.clicked.connect(self.handle_login)
        
        # Change password button
        self.change_password_button = ModernLoginButton("Change Password")
        self.change_password_button.setSecondaryStyle()
        self.change_password_button.clicked.connect(self.open_change_password)
        
        # Enable/disable password change button dynamically
        self.change_password_button.setEnabled(False)
        self.username_input.textChanged.connect(
            lambda: self.change_password_button.setEnabled(bool(self.username_input.text().strip()))
        )
        
        # Add widgets to form
        form_layout.addWidget(username_label)
        form_layout.addWidget(self.username_input)
        form_layout.addWidget(password_label)
        form_layout.addWidget(self.password_input)
        form_layout.addSpacing(10)
        form_layout.addWidget(self.login_button)
        form_layout.addSpacing(15)
        form_layout.addWidget(self.change_password_button)
        
        # ============= FOOTER =============
        footer_widget = QWidget()
        footer_layout = QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        
        # Copyright
        copyright_label = QLabel("© 2026 Megazen Inventory Management System")
        copyright_label.setFont(QFont("Segoe UI", 9))
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet("color: #95a5a6;")
        
        # Version info (optional)
        version_label = QLabel("Version 1.0")
        version_label.setFont(QFont("Segoe UI", 8))
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: #bdc3c7;")
        
        footer_layout.addWidget(copyright_label)
        footer_layout.addWidget(version_label)
        
        # Add all sections to main layout
        # main_layout.addWidget(header_widget)
        main_layout.addWidget(form_widget)
        main_layout.addStretch()
        main_layout.addWidget(footer_widget)
        
        self.setLayout(main_layout)
        
        # Add shadow effect to the dialog
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)
        
        # Set enter key to trigger login
        self.password_input.returnPressed.connect(self.handle_login)
        
    def handle_login(self):
        """Handle login attempt with modern feedback"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            self.show_error_message("Please enter both username and password")
            return

        try:
            # Disable inputs while processing
            self.set_inputs_enabled(False)
            self.login_button.setText("Signing in...")
            
            auth_service = AuthService()
            user = auth_service.get_by_username(username)
            
            if user and auth_service.authenticate_user(username, password):
                self.logged_in_user = {
                    "id": user.id,
                    "username": username,
                    "role": user.role
                }
                
                # Success animation/feedback
                self.show_success_message()
                self.accept()
            else:
                self.show_error_message("Invalid username or password")
                self.password_input.clear()
                self.password_input.setFocus()
                
        except Exception as e:
            self.show_error_message(f"Login failed: {str(e)}")
        finally:
            self.set_inputs_enabled(True)
            self.login_button.setText("Sign In")
    
    def set_inputs_enabled(self, enabled):
        """Enable or disable all input fields"""
        self.username_input.setEnabled(enabled)
        self.password_input.setEnabled(enabled)
        self.login_button.setEnabled(enabled)
        self.change_password_button.setEnabled(enabled and bool(self.username_input.text().strip()))
    
    def show_error_message(self, message):
        """Show styled error message"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Login Failed")
        msg_box.setText(f"""
        <html>
        <body style="font-family: Segoe UI; font-size: 13px;">
        <h3 style="color: #e74c3c; margin-bottom: 10px;">Login Failed</h3>
        <p>{message}</p>
        </body>
        </html>
        """)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        
        # Highlight problematic fields
        self.username_input.set_error_style()
        self.password_input.set_error_style()
        QTimer.singleShot(2000, lambda: [
            self.username_input.set_normal_style(),
            self.password_input.set_normal_style()
        ])
    
    def show_success_message(self):
        """Show success message (briefly)"""
        # Flash success color on inputs
        self.username_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #2ecc71;
                border-radius: 8px;
                padding: 12px 15px;
                background-color: #f0fff4;
                font-size: 14px;
            }
        """)
        self.password_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #2ecc71;
                border-radius: 8px;
                padding: 12px 15px;
                background-color: #f0fff4;
                font-size: 14px;
            }
        """)
    
    def open_change_password(self):
        """Open change password dialog"""
        username = self.username_input.text().strip()
        if not username:
            self.show_error_message("Please enter username first to change password")
            return

        dialog = ChangePasswordDialog(username, self)
        dialog.exec()


class ChangePasswordDialog(QDialog):
    """Modern change password dialog"""
    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Password - Megazen IMS")
        self.setFixedSize(450, 650)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self.username = username
        self.auth_service = AuthService()
        
        # Set window icon
        self.setWindowIcon(QIcon(resource_path("assets/logo.png")))
        
        # Apply modern palette
        self.set_palette()
        
        # Create layout
        self.init_ui()
        
        # Center on screen
        self.center_on_screen()
        
    def set_palette(self):
        """Set modern color palette"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(248, 249, 250))
        self.setPalette(palette)
        
    def center_on_screen(self):
        """Center the dialog on the screen"""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        
    def init_ui(self):
        """Initialize the modern UI for change password dialog"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 0, 40, 10)
        main_layout.setSpacing(0)
        
        # ============= HEADER =============
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        # Title
        title_label = QLabel("Change Password")
        title_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50;")
        
        # Subtitle
        subtitle_label = QLabel(f"Change password for user: <b>{self.username}</b>")
        subtitle_label.setFont(QFont("Segoe UI", 11))
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #7f8c8d;")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        
        # ============= FORM =============
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)
        
        # Current password
        current_label = QLabel("Current Password")
        current_label.setFont(QFont("Segoe UI", 11, QFont.Medium))
        current_label.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        
        self.current_password = ModernLoginLineEdit("Enter current password", is_password=True)
        
        # New password
        new_label = QLabel("New Password")
        new_label.setFont(QFont("Segoe UI", 11, QFont.Medium))
        new_label.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        
        self.new_password = ModernLoginLineEdit("Enter new password", is_password=True)
        
        # Confirm password
        confirm_label = QLabel("Confirm New Password")
        confirm_label.setFont(QFont("Segoe UI", 11, QFont.Medium))
        confirm_label.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        
        self.confirm_password = ModernLoginLineEdit("Confirm new password", is_password=True)
        
        # Password requirements
        requirements_label = QLabel(
            "<small>Password requirements: At least 8 characters, including uppercase, lowercase, and numbers</small>"
        )
        requirements_label.setFont(QFont("Segoe UI", 9))
        requirements_label.setStyleSheet("color: #95a5a6; margin-top: 10px;")
        
        # Change button
        self.change_button = ModernLoginButton("Change Password")
        self.change_button.setPrimaryStyle()
        self.change_button.clicked.connect(self.handle_change)
        
        # Add widgets to form
        form_layout.addWidget(current_label)
        form_layout.addWidget(self.current_password)
        form_layout.addWidget(new_label)
        form_layout.addWidget(self.new_password)
        form_layout.addWidget(confirm_label)
        form_layout.addWidget(self.confirm_password)
        form_layout.addWidget(requirements_label)
        form_layout.addSpacing(00)
        form_layout.addWidget(self.change_button)
        
        # ============= FOOTER =============
        footer_widget = QWidget()
        footer_layout = QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        
        cancel_button = ModernLoginButton("Cancel")
        cancel_button.setSecondaryStyle()
        cancel_button.clicked.connect(self.reject)
        
        footer_layout.addWidget(cancel_button)
        
        # Add all sections
        main_layout.addWidget(header_widget)
        main_layout.addWidget(form_widget)
        # main_layout.addStretch()
        main_layout.addWidget(footer_widget)
        
        self.setLayout(main_layout)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)
        
        # Set enter key to trigger change
        self.confirm_password.returnPressed.connect(self.handle_change)
        
    def handle_change(self):
        """Handle password change"""
        current_pw = self.current_password.text().strip()
        new_pw = self.new_password.text().strip()
        confirm_pw = self.confirm_password.text().strip()

        if not current_pw or not new_pw or not confirm_pw:
            self.show_error("Please fill out all fields")
            return

        if new_pw != confirm_pw:
            self.show_error("New passwords do not match")
            self.new_password.set_error_style()
            self.confirm_password.set_error_style()
            return

        # Simple password validation
        if len(new_pw) < 8:
            self.show_error("Password must be at least 8 characters long")
            return

        # Disable button while processing
        self.change_button.setEnabled(False)
        self.change_button.setText("Changing...")

        try:
            if self.auth_service.change_password(self.username, current_pw, new_pw):
                self.show_success()
            else:
                self.show_error("Incorrect current password")
                self.current_password.set_error_style()
        except Exception as e:
            self.show_error(f"Failed to change password: {str(e)}")
        finally:
            self.change_button.setEnabled(True)
            self.change_button.setText("Change Password")
    
    def show_error(self, message):
        """Show error message"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Error")
        msg_box.setText(f"""
        <html>
        <body style="font-family: Segoe UI; font-size: 13px;">
        <h3 style="color: #e74c3c;">Password Change Failed</h3>
        <p>{message}</p>
        </body>
        </html>
        """)
        msg_box.exec()
    
    def show_success(self):
        """Show success message and close"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Success")
        msg_box.setText(f"""
        <html>
        <body style="font-family: Segoe UI; font-size: 13px;">
        <h3 style="color: #2ecc71;">Password Changed Successfully</h3>
        <p>Your password has been updated.</p>
        <p><small>Please log in again with your new password.</small></p>
        </body>
        </html>
        """)
        msg_box.exec()
        self.accept()