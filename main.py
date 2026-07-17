import os
import sys
import threading
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from models.engine.database import db, Base
from services.auth_service import AuthService
from PySide6.QtWidgets import QApplication, QSplashScreen, QMessageBox, QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer
from ui.main_window import MainWindow
import telegrambot.bot
from telegrambot.bot import start_bot
from utils import resource_path
from security import license_check

def show_error_and_exit(message):
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("License Error")
    dialog.setMinimumWidth(500)
    
    layout = QVBoxLayout(dialog)
    
    # Message label
    msg_label = QLabel("Application cannot start.\n\nPlease copy the machine ID below and send it to your software provider.\n")
    layout.addWidget(msg_label)
    
    # Selectable text area for machine ID
    text_edit = QTextEdit()
    text_edit.setPlainText(message)
    text_edit.setReadOnly(True)
    text_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
    text_edit.setMaximumHeight(100)
    layout.addWidget(text_edit)
    
    # Copy button
    copy_btn = QPushButton("Copy to Clipboard")
    copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(message))
    layout.addWidget(copy_btn)
    
    # Exit button
    exit_btn = QPushButton("Exit")
    exit_btn.clicked.connect(dialog.accept)
    layout.addWidget(exit_btn)
    
    dialog.exec()
    sys.exit(1)

if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

license_path = os.path.join(base_path, "license.key")
is_valid, license_message = license_check.verify_license(license_path)
if not is_valid:
    show_error_and_exit(license_message)

def setup_database():
    Base.metadata.create_all(bind=db.engine)
    auth_service = AuthService()
    auth_service.create_admin_if_not_exists("ADMIN", "ADMIN123")
    print("Tables created successfully.")

def main():
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    app = QApplication(sys.argv)

    import logging
    logging.getLogger('asyncio').setLevel(logging.DEBUG)

    logo_path = resource_path(os.path.join("assets", "logo.ico"))
    if not os.path.exists(logo_path):
        splash_pix = QPixmap(400, 200)
        splash_pix.fill(Qt.white)
    else:
        splash_pix = QPixmap(logo_path)
    
    splash = QSplashScreen(splash_pix)
    splash.showMessage(
        "🚀 Initializing Application...",
        Qt.AlignCenter | Qt.AlignBottom,
        Qt.white
    )
    splash.show()
    app.processEvents()

    print("Starting Telegram bot in background...")
    telegrambot.bot.global_main_window_ref = None
    bot_thread = threading.Thread(
        target=lambda: start_bot(None),  # Pass None initially
        daemon=True,
        name="TelegramBotThread"
    )
    bot_thread.start()

    def load_main_window():
        # Show database setup message
        splash.showMessage("🔄 Setting up database...", Qt.AlignCenter | Qt.AlignBottom, Qt.white)
        app.processEvents()
        
        # This is the KEY - database setup BEFORE UI
        setup_database()
        
        # Now load UI
        splash.showMessage("🎨 Loading interface...", Qt.AlignCenter | Qt.AlignBottom, Qt.white)
        app.processEvents()
        
        main_window = MainWindow()
        main_window.showMaximized()
        # main_window.show()
        # start_bot(main_window)
        telegrambot.bot.global_main_window_ref = main_window
        splash.finish(main_window)

        # start_in_background()

    # Reduced from 2000ms to 500ms for faster startup
    QTimer.singleShot(500, load_main_window)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()