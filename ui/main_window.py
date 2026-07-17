#!/usr/bin/env python3
"""
"""
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QStackedWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, 
    QMessageBox, QGraphicsDropShadowEffect, QSizePolicy, QProgressBar
)
from PySide6.QtGui import (
    QFont, QPixmap, QIcon, QColor, QPalette, QLinearGradient,
    QPainter, QBrush, QPen, QPainterPath, QCursor
)
from PySide6.QtCore import (
    QSize, Qt, Signal, QTimer, QPropertyAnimation, 
    QEasingCurve, QRect, QPoint, QVariantAnimation, QTimer, QEvent
)
from PySide6.QtSvg import QSvgRenderer
from ui.pages.product_page import ProductManager
# from ui.pages.salesperson_page import SalesPesonManager
from ui.pages.sales_page import SalesManager
from ui.pages.dashboard_page import DashboardManager
from ui.pages.login_dialog import LoginDialog
from ui.pages.reports_page import ReportsPage
from datetime import datetime
from ui.components.ethiopian_date import EthiopianDateConverter
from utils import resource_path

class ModernButton(QPushButton):
    """Custom modern button with hover effects"""
    def __init__(self, text="", icon=None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        self._normal_style = ""
        self._hover_style = ""
        self._checked_style = ""
        
    def setStyles(self, normal, hover, checked):
        self._normal_style = normal
        self._hover_style = hover
        self._checked_style = checked
        self.setStyleSheet(normal)
        
    def enterEvent(self, event):
        if not self.isChecked():
            self.setStyleSheet(self._hover_style)
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        if self.isChecked():
            self.setStyleSheet(self._checked_style)
        else:
            self.setStyleSheet(self._normal_style)
        super().leaveEvent(event)


class ModernLineEdit(QLineEdit):
    """Custom modern line edit with focus effects"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(35)
        self._normal_style = """
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px 12px;
                background-color: white;
                font-size: 14px;
                selection-background-color: #2196F3;
            }
        """
        self._focus_style = """
            QLineEdit {
                border: 2px solid #2196F3;
                border-radius: 8px;
                padding: 8px 12px;
                background-color: white;
                font-size: 14px;
                selection-background-color: #2196F3;
            }
        """
        self.setStyleSheet(self._normal_style)
        
    def focusInEvent(self, event):
        self.setStyleSheet(self._focus_style)
        super().focusInEvent(event)
        
    def focusOutEvent(self, event):
        self.setStyleSheet(self._normal_style)
        super().focusOutEvent(event)




class MainWindow(QMainWindow):
    """Modern Main Window for Inventory Management System"""
    bot_status_changed = Signal(bool)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Megazen IMS - Inventory Management System")
        self.current_user = None

        # Set application palette
        self.set_palette()
        
        # Screen setup
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        window_width = int(screen_width * 0.85)
        window_height = int(screen_height * 0.85)
        
        self.resize(window_width, window_height)
        self.move(
            screen_geometry.x() + (screen_width - window_width) // 2,
            screen_geometry.y() + (screen_height - window_height) // 2
        )
        self.setMinimumSize(1024, 768)

        # Window properties
        self.setWindowIcon(QIcon(resource_path("assets/logo.png")))
        self.bot_status_changed.connect(self._update_bot_status)
        
        # Inactivity timer
        self.inactivity_timer = QTimer()
        self.inactivity_timer.timeout.connect(self.handle_inactivity)
        self.inactivity_timeout = 2 * 60 * 60 * 1000
        self.inactivity_timer.setSingleShot(True)
        
        # Auto‑hide sidebar timer
        self.auto_hide_timer = QTimer()
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.collapse_sidebar)
        
        # Sidebar state
        self.sidebar_visible = False   # False = hidden (only hot edge visible)
        
        # Pages management
        self.pages = {}
        self.page_classes = {
            "Dashboard": DashboardManager,
            "Products": ProductManager,
            "Sales": SalesManager,
            "Reports": ReportsPage
        }
        self.ethiopian_months = [
            "መስከረም", "ጥቅምት", "ኅዳር", "ታኅሣሥ", "ጥር", "የካቲት",
            "መጋቢት", "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜን"
        ]
        
        self.init_ui()
        self.require_login()
    
    def set_palette(self):
        """Set modern color palette for the application"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(248, 249, 250))
        palette.setColor(QPalette.WindowText, QColor(33, 37, 41))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(233, 236, 239))
        palette.setColor(QPalette.ToolTipBase, QColor(33, 37, 41))
        palette.setColor(QPalette.ToolTipText, QColor(248, 249, 250))
        palette.setColor(QPalette.Text, QColor(33, 37, 41))
        palette.setColor(QPalette.Button, QColor(52, 58, 64))
        palette.setColor(QPalette.ButtonText, QColor(248, 249, 250))
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(41, 128, 185))
        palette.setColor(QPalette.Highlight, QColor(41, 128, 185))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)
    
    def init_ui(self):
        """Initialize the modern UI with an auto‑hide overlay sidebar"""
        main_widget = QWidget()
        main_widget.setObjectName("mainWidget")
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ============ HOT EDGE (always visible, 5px wide) ============
        self.hot_edge = QWidget(main_widget)
        self.hot_edge.setObjectName("hotEdge")
        self.hot_edge.setFixedWidth(5)
        self.hot_edge.setStyleSheet("""
            #hotEdge {
                background-color: #2c3e50;
                border-right: 1px solid #1a252f;
            }
        """)
        # Will be positioned in resizeEvent

        # ============ MODERN SIDEBAR (floating overlay) ============
        self.sidebar_widget = QWidget(main_widget)
        self.sidebar_widget.setObjectName("sidebar")
        self.sidebar_widget.setFixedWidth(280)
        self.sidebar_widget.setStyleSheet("""
            #sidebar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-right: 1px solid #1a252f;
            }
        """)
        
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # ============= SIDEBAR HEADER =============
        sidebar_header = QWidget()
        sidebar_header.setFixedHeight(106)
        sidebar_header.setStyleSheet("""
            QWidget {
                background-color: #1a252f;
                border-bottom: 1px solid #34495e;
            }
        """)
        
        header_layout = QVBoxLayout(sidebar_header)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(10)
        
        # Logo and company name
        logo_container = QHBoxLayout()
        self.logo_label = QLabel()
        pixmap = QPixmap(resource_path("assets/logo.png"))
        pixmap.setDevicePixelRatio(self.devicePixelRatio())
        self.logo_label.setPixmap(
            pixmap.scaled(
                48 * self.devicePixelRatio(),
                48 * self.devicePixelRatio(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )
        self.logo_label.setFixedSize(48, 48)
        
        self.company_label = QLabel("MEGAZEN")
        self.company_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.company_label.setStyleSheet("color: #ecf0f1;")
        
        logo_container.addWidget(self.logo_label)
        logo_container.addSpacing(15)
        logo_container.addWidget(self.company_label)
        logo_container.addStretch()
        
        header_layout.addLayout(logo_container)
        
        # Subtitle
        self.subtitle = QLabel("Inventory Management System")
        self.subtitle.setFont(QFont("Segoe UI", 10))
        self.subtitle.setStyleSheet("color: #bdc3c7;")
        header_layout.addSpacing(6)
        header_layout.addWidget(self.subtitle)
        
        sidebar_layout.addWidget(sidebar_header)

        # ================== SIDEBAR MENU BUTTONS ================
        menu_container = QWidget()
        menu_layout = QVBoxLayout(menu_container)
        menu_layout.setContentsMargins(15, 20, 15, 20)
        menu_layout.setSpacing(8)

        button_info = [
            ("Products", resource_path("assets/9025861_package_box_icon.png"), "#3498db"),
            ("Sales", resource_path("assets/326700_cart_shopping_icon.png"), "#3498db"),
            ("Dashboard", resource_path("assets/9055226_bxs_dashboard_icon.png"), "#3498db"),
            ("Reports", resource_path("assets/2124299_app_document_report_essential_icon.png"), "#3498db"),
        ]

        self.buttons = {}
        for name, icon_path, color in button_info:
            btn = ModernButton(name)
            btn.setIcon(QIcon(resource_path(icon_path)))
            btn.setIconSize(QSize(20, 20))
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            
            normal_style = f"""
                QPushButton {{
                    text-align: left;
                    padding: 12px 15px;
                    border: none;
                    border-radius: 8px;
                    font-weight: 500;
                    font-size: 14px;
                    color: #ecf0f1;
                    background-color: transparent;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.1);
                }}
            """
            
            checked_style = f"""
                QPushButton {{
                    text-align: left;
                    padding: 12px 15px;
                    border: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 14px;
                    color: white;
                    background-color: {color};
                }}
            """
            
            btn.setStyles(normal_style, normal_style, checked_style)
            btn.clicked.connect(lambda checked, n=name: self.switch_page(n))
            self.buttons[name] = btn
            
            menu_layout.addWidget(btn)
        
        menu_layout.addStretch()
        sidebar_layout.addWidget(menu_container)

        # ================== USER SECTION ==================
        self.user_section = QWidget()
        self.user_section.setFixedHeight(120)
        self.user_section.setStyleSheet("""
            QWidget {
                background-color: #1a252f;
                border-top: 1px solid #34495e;
            }
        """)
        
        user_layout = QVBoxLayout(self.user_section)
        user_layout.setContentsMargins(20, 15, 20, 15)
        user_layout.setSpacing(10)
        
        user_info_container = QHBoxLayout()
        self.user_avatar = QLabel("👤")
        self.user_avatar.setFixedSize(40, 40)
        self.user_avatar.setStyleSheet("""
            QLabel {
                font-size: 20px;
                background-color: #3498db;
                border-radius: 20px;
                padding: 8px;
                color: white;
            }
        """)
        self.user_avatar.setAlignment(Qt.AlignCenter)
        
        self.user_info_label = QLabel("Not logged in")
        self.user_info_label.setStyleSheet("""
            QLabel {
                color: #ecf0f1;
                font-weight: 600;
                font-size: 14px;
            }
        """)
        
        user_info_container.addWidget(self.user_avatar)
        user_info_container.addSpacing(10)
        user_info_container.addWidget(self.user_info_label)
        user_info_container.addStretch()
        
        user_layout.addLayout(user_info_container)
        
        self.logout_button = ModernButton("Sign Out")
        self.logout_button.setIcon(QIcon(resource_path("assets/logout_icon.png")))
        self.logout_button.setIconSize(QSize(16, 16))
        self.logout_button.setStyles(
            """QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }""",
            """QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-weight: 600;
                font-size: 13px;
            }""",
            """QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-weight: 600;
                font-size: 13px;
            }"""
        )
        self.logout_button.clicked.connect(self.handle_logout)
        
        user_layout.addWidget(self.logout_button)
        sidebar_layout.addWidget(self.user_section)

        # =============== MAIN CONTENT AREA (full width) ================
        main_content = QWidget()
        main_content.setObjectName("mainContent")
        main_content.setStyleSheet("""
            #mainContent {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f0f2f5,
                    stop:1 #d9dee3
                );
            }
        """)
        
        main_content_layout = QVBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(0)

        # ===================== MODERN HEADER (no menu button) =================
        header_widget = QWidget()
        header_widget.setFixedHeight(70)
        header_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 2)
        header_widget.setGraphicsEffect(shadow)
        
        header_layout = QHBoxLayout(header_widget)

        # Page title (left aligned, no hamburger button)
        self.page_title_label = QLabel("Dashboard")
        self.page_title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.page_title_label.setStyleSheet("color: #2c3e50; margin-left: 10px;")
        
        header_layout.addWidget(self.page_title_label)
        header_layout.addSpacing(20)
        header_layout.addStretch()

        # Ethiopian and Gregorian date labels
        datetime_container = QWidget()
        datetime_layout = QHBoxLayout(datetime_container)
        datetime_layout.setContentsMargins(0, 0, 0, 0)
        datetime_layout.setSpacing(5)

        self.ethiopian_label = QLabel()
        self.ethiopian_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-weight: 500;
                font-size: 20px;
                background-color: #f0f0f0;
                padding: 5px 12px;
                border-radius: 15px;
                border: 1px solid #d0d0d0;
                font-family: 'Noto Sans Ethiopic', 'Nyala', 'Abyssinica SIL', 'Ebrima', sans-serif;
            }
        """)
        datetime_layout.addWidget(self.ethiopian_label)

        self.gregorian_label = QLabel()
        self.gregorian_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-weight: 500;
                font-size: 16px;
                background-color: #f8f9fa;
                padding: 5px 12px;
                border-radius: 15px;
                border: 1px solid #d0d0d0;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }
        """)
        datetime_layout.addWidget(self.gregorian_label)

        header_layout.addWidget(datetime_container)
        header_layout.addSpacing(20)

        # Bot status
        bot_container = QWidget()
        bot_layout = QHBoxLayout(bot_container)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(8)
        
        self.bot_indicator = QLabel("●")
        self.bot_indicator.setFixedSize(12, 12)
        self.bot_indicator.setStyleSheet("""
            QLabel {
                color: #e74c3c;
                font-size: 20px;
            }
        """)
        
        self.bot_status_label = QLabel("Bot Offline")
        self.bot_status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-weight: 500;
                font-size: 13px;
            }
        """)
        
        bot_layout.addWidget(self.bot_indicator)
        bot_layout.addWidget(self.bot_status_label)
        header_layout.addWidget(bot_container)

        main_content_layout.addWidget(header_widget)

        # ======================== PAGE CONTENT ===================
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(25, 25, 25, 25)
        content_layout.setSpacing(20)
        
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("""
            QStackedWidget {
                background-color: transparent;
            }
        """)
        
        # Load default page
        self.load_page("Sales")
        content_layout.addWidget(self.stacked_widget)
        main_content_layout.addWidget(content_widget)
        
        # Add main_content to the main layout – it fills the whole window
        main_layout.addWidget(main_content)
        
        self.setCentralWidget(main_widget)
        
        # Initial button state
        self.buttons["Sales"].setChecked(True)
        self.switch_page("Sales")

        # ============ Setup auto‑hide behavior ============
        self.hot_edge.installEventFilter(self)
        self.sidebar_widget.installEventFilter(self)

        self.hot_edge.raise_()
        self.sidebar_widget.raise_()
        
        # Start with sidebar hidden (only hot edge visible)
        self.collapse_sidebar(animate=False)
    
    # ====================== Overlay & Animation Methods ======================
    
    def resizeEvent(self, event):
        """Keep hot edge and sidebar positioned correctly when window is resized."""
        super().resizeEvent(event)
        if hasattr(self, 'hot_edge') and hasattr(self, 'sidebar_widget'):
            wh = self.height()
            # Hot edge: 5px wide, full height, at left edge
            self.hot_edge.setGeometry(0, 0, 5, wh)
            # Sidebar: 280px wide, full height
            self.sidebar_widget.setGeometry(0, 0, 280, wh)
            # Initial position depends on visibility
            if not self.sidebar_visible:
                self.sidebar_widget.move(-280, 0)
            else:
                self.sidebar_widget.move(0, 0)
    
    def eventFilter(self, obj, event):
        # 1. Inactivity monitoring – detect any user activity
        if event.type() in [
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
            QEvent.Type.Enter,
            QEvent.Type.Leave,
            QEvent.Type.Wheel,
        ]:
            self.reset_inactivity_timer()

        # 2. Auto‑hide sidebar logic
        if obj == self.hot_edge or obj == self.sidebar_widget:
            if event.type() == QEvent.Type.Enter:
                self.auto_hide_timer.stop()
                if not self.sidebar_visible:
                    self.expand_sidebar()
            elif event.type() == QEvent.Type.Leave:
                QTimer.singleShot(100, self.check_hide_sidebar)

        return super().eventFilter(obj, event)
    
    def check_hide_sidebar(self):
        """If mouse is outside both the hot edge and the sidebar, start hide timer."""
        pos = self.mapFromGlobal(QCursor.pos())
        hot_geo = self.hot_edge.geometry()
        side_geo = self.sidebar_widget.geometry()
        if not hot_geo.contains(pos) and not side_geo.contains(pos):
            if self.sidebar_visible and not self.auto_hide_timer.isActive():
                self.auto_hide_timer.start(300)
        else:
            self.auto_hide_timer.stop()
    
    def expand_sidebar(self):
        """Animate sidebar sliding in from the left."""
        if hasattr(self, 'sidebar_animation'):
            self.sidebar_animation.stop()
        self.sidebar_animation = QVariantAnimation()
        self.sidebar_animation.setDuration(300)
        self.sidebar_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.sidebar_animation.setStartValue(-280)
        self.sidebar_animation.setEndValue(0)
        self.sidebar_animation.valueChanged.connect(lambda x: self.sidebar_widget.move(x, 0))
        self.sidebar_animation.start()
        self.sidebar_visible = True
        self.hot_edge.hide()
    
    def collapse_sidebar(self, animate=True):
        """Animate sidebar sliding out (or hide instantly)."""
        if animate:
            if hasattr(self, 'sidebar_animation'):
                self.sidebar_animation.stop()
            self.sidebar_animation = QVariantAnimation()
            self.sidebar_animation.setDuration(300)
            self.sidebar_animation.setEasingCurve(QEasingCurve.InOutCubic)
            self.sidebar_animation.setStartValue(0)
            self.sidebar_animation.setEndValue(-280)
            self.sidebar_animation.valueChanged.connect(lambda x: self.sidebar_widget.move(x, 0))
            self.sidebar_animation.start()
        else:
            self.sidebar_widget.move(-280, 0)
        self.sidebar_visible = False
        self.hot_edge.show()   # show the thin handle again
    
    # ====================== Original Methods (unchanged) ======================
    
    def update_datetime_labels(self):
        """Update both Ethiopian and Gregorian date labels."""
        now = datetime.now()
        
        # Ethiopian date
        try:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(now.date())
            eth_weekday_num = now.isoweekday()
            eth_weekdays = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሑድ"]
            eth_weekday = eth_weekdays[eth_weekday_num - 1]
            month_name = self.ethiopian_months[eth_month - 1] if 1 <= eth_month <= 13 else str(eth_month)
            time_str = now.strftime("%I:%M:%S %p")
            eth_date_str = f"{eth_weekday} {eth_day:02d} {month_name}({eth_month:02d}) {eth_year}"
            self.ethiopian_label.setText(eth_date_str)
        except Exception:
            self.ethiopian_label.setText("የኢትዮጵያ ቀን: N/A")
        
        # Gregorian date
        try:
            greg_date_str = now.strftime("%A, %B(%m) %d, %Y")
            self.gregorian_label.setText(greg_date_str)
        except Exception:
            self.gregorian_label.setText("Gregorian: N/A")

    def load_page(self, page_name):
        """Lazy load a page if it hasn't been loaded yet, showEvent"""
        if page_name not in self.pages:
            page_class = self.page_classes[page_name]
            page_instance = page_class()
            
            if self.current_user and hasattr(page_instance, 'set_current_user'):
                page_instance.set_current_user(self.current_user)
            elif self.current_user and hasattr(page_instance, 'current_user'):
                page_instance.current_user = self.current_user
            
            self.pages[page_name] = page_instance
            self.stacked_widget.addWidget(page_instance)
            
            if hasattr(page_instance, 'setGraphicsEffect'):
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(15)
                shadow.setColor(QColor(0, 0, 0, 15))
                shadow.setOffset(0, 0)
                page_instance.setGraphicsEffect(shadow)
            
            print(f"Loaded page: {page_name}")
        
        return self.pages[page_name]

    def switch_page(self, page_name):
        """Switch between pages with animation"""
        self.reset_inactivity_timer()
        
        if page_name in ["Reports", "Dashboard"]:
            if not self.current_user or self.current_user.get("role") != "admin":
                QMessageBox.warning(
                    self, 
                    "Access Denied", 
                    "<b>Administrator Access Required</b><br><br>"
                    "This section requires administrator privileges.<br>"
                    "Please contact your system administrator for access."
                )
                current_widget = self.stacked_widget.currentWidget()
                for name, page in self.pages.items():
                    if page == current_widget:
                        self.buttons[name].setChecked(True)
                        break
                return
        
        self.page_title_label.setText(page_name)
        page = self.load_page(page_name)
        index = self.stacked_widget.indexOf(page)
        
        old_widget = self.stacked_widget.currentWidget()
        if old_widget:
            old_widget.setGraphicsEffect(None)
        
        self.stacked_widget.setCurrentIndex(index)
        
        if hasattr(page, 'setGraphicsEffect'):
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(15)
            shadow.setColor(QColor(0, 0, 0, 15))
            shadow.setOffset(0, 0)
            page.setGraphicsEffect(shadow)

        if page_name == "Reports" and hasattr(page, 'show_default_tab'):
            page.show_default_tab()

        if hasattr(page, 'refresh'):
            page.refresh()

    def update_user_display(self):
        """Update the user display based on login status"""
        if self.current_user:
            username = self.current_user.get('username', 'Unknown')
            role = self.current_user.get('role', 'user').title()
            
            self.user_info_label.setText(f"{username}\n{role}")
            self.user_avatar.setText(username[0].upper())
            
            role_colors = {
                'admin': '#e74c3c',
                'manager': '#3498db',
                'user': '#2ecc71'
            }
            avatar_color = role_colors.get(self.current_user.get('role', 'user'), '#3498db')
            self.user_avatar.setStyleSheet(f"""
                QLabel {{
                    font-size: 16px;
                    background-color: {avatar_color};
                    border-radius: 20px;
                    padding: 8px;
                    color: white;
                    font-weight: bold;
                }}
            """)
            
            self.logout_button.setEnabled(True)
        else:
            self.user_info_label.setText("Not logged in")
            self.user_avatar.setText("?")
            self.user_avatar.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    background-color: #95a5a6;
                    border-radius: 20px;
                    padding: 8px;
                    color: white;
                    font-weight: bold;
                }
            """)
            self.logout_button.setEnabled(False)

    def require_login(self):
        """Require login to access the application normal_style"""
        login_dialog = LoginDialog()
        if login_dialog.exec() == LoginDialog.Accepted:
            self.current_user = login_dialog.logged_in_user
            self.update_user_display()
            self.reset_inactivity_timer()
            self.update_pages_with_user()
        else:
            QMessageBox.information(
                self, 
                "Login Required", 
                "Authentication is required to access the Inventory Management System."
            )
            self.close()
            QApplication.quit()
    
    def update_pages_with_user(self):
        """Update all loaded pages with current user information"""
        for page_name, page in self.pages.items():
            if hasattr(page, 'set_current_user'):
                page.set_current_user(self.current_user)
            elif hasattr(page, 'current_user'):
                page.current_user = self.current_user

    def handle_logout(self):
        """Handle user logout with confirmation"""
        reply = QMessageBox.question(
            self, 
            "Confirm Sign Out", 
            "<html><body style='font-family: Segoe UI; font-size: 14px;'>"
            "<h3 style='color: #2c3e50;'>Confirm Sign Out</h3>"
            "<p>Are you sure you want to sign out?</p>"
            f"<p><small>User: <b>{self.current_user.get('username', 'Unknown')}</b></small></p>"
            "</body></html>",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.perform_logout()
            QMessageBox.information(
                self, 
                "Signed Out", 
                "You have been successfully signed out."
            )
            self.buttons["Dashboard"].setChecked(True)
            self.switch_page("Dashboard")
            self.require_login()

    def set_bot_connected(self):
        """Update bot status to connected"""
        self.bot_status_changed.emit(True)

    def set_bot_disconnected(self):
        """Update bot status to disconnected"""
        self.bot_status_changed.emit(False)

    def _update_bot_status(self, connected):
        """Update bot status UI"""
        if connected:
            self.bot_status_label.setText("Bot Online")
            self.bot_indicator.setStyleSheet("""
                QLabel {
                    color: #2ecc71;
                    font-size: 20px;
                }
            """)
        else:
            self.bot_status_label.setText("Bot Offline")
            self.bot_indicator.setStyleSheet("""
                QLabel {
                    color: #e74c3c;
                    font-size: 20px;
                }
            """)

    def handle_inactivity(self):
        """Handle user inactivity - auto logout"""
        if self.current_user:
            username = self.current_user.get('username', 'User')
            timeout_msg = QMessageBox(self)
            timeout_msg.setIcon(QMessageBox.Warning)
            timeout_msg.setWindowTitle("Session Timeout")
            timeout_msg.setText(f"""
            <html>
            <body style="font-family: Segoe UI; font-size: 14px;">
            <h3 style="color: #e74c3c;">Session Timeout</h3>
            <p>Your session has timed out due to inactivity.</p>
            <p><small>User: <b>{username}</b></small></p>
            <hr>
            <p style="color: #7f8c8d; font-size: 12px;">
            Please log in again to continue.
            </p>
            </body>
            </html>
            """)
            timeout_msg.setStandardButtons(QMessageBox.Ok)
            timeout_msg.exec()
            
            self.perform_logout()
            self.require_login()
    
    def perform_logout(self):
        """Perform Logout without showing login dialog immediately"""
        self.current_user = None
        self.update_user_display()
        
        if "Dashboard" in self.buttons:
            self.buttons["Dashboard"].setChecked(True)
        self.stacked_widget.setCurrentIndex(0)
        
        if hasattr(self, 'inactivity_timer'):
            self.inactivity_timer.stop()

    def reset_inactivity_timer(self):
        """Reset the inactivity timer (call this on any user activity)"""
        if hasattr(self, 'inactivity_timer'):
            if self.inactivity_timer.isActive():
                self.inactivity_timer.stop()
            if self.current_user:
                self.inactivity_timer.start(self.inactivity_timeout)

    def start_inactivity_monitoring(self):
        """Start monitoring user inactivity"""
        self.installEventFilter(self)
        self.reset_inactivity_timer()

    def showEvent(self, event):
        """Handle window show event"""
        super().showEvent(event)
        self.start_inactivity_monitoring()
        self.ethiopian_timer = QTimer(self)
        self.ethiopian_timer.timeout.connect(self.update_datetime_labels)
        self.ethiopian_timer.start(1000)
        self.update_datetime_labels()
        if hasattr(self, 'check_bot_connection'):
            QTimer.singleShot(1000, self.check_bot_connection)
    
    def closeEvent(self, event):
        if hasattr(self, 'ethiopian_timer'):
            self.ethiopian_timer.stop()