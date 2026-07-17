#!/usr/bin/env python3
"""
Custom UI Components for Sales Management System
"""
from PySide6.QtWidgets import QPushButton, QDoubleSpinBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class ModernButton(QPushButton):
    """Custom modern button with hover effects"""
    def __init__(self, text="", icon=None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(32)
        
    def setPrimary(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
        """)
    
    def setSuccess(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
    
    def setDanger(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
    
    def setSecondary(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)


class EditPriceDialog(QDialog):
    """Professional dialog for editing product price"""
    def __init__(self, product_name, current_price, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Product Price")
        self.setFixedSize(400, 250)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 20)
        main_layout.setSpacing(15)
        
        # Header with icon and title
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        
        # Icon
        icon_label = QLabel("💰")
        icon_label.setStyleSheet("font-size: 20px;")
        
        # Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        
        title_label = QLabel("Edit Product Price")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        
        subtitle_label = QLabel("Applies to all batches of this product")
        subtitle_label.setFont(QFont("Segoe UI", 9))
        subtitle_label.setStyleSheet("color: #64748b;")
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        
        header_layout.addWidget(icon_label)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        main_layout.addWidget(header_widget)
        
        # Price input section
        input_layout = QVBoxLayout()
        input_layout.setSpacing(10)
        
        # Product name display
        product_label = QLabel(f"<b>{product_name}</b>")
        product_label.setFont(QFont("Segoe UI", 12))
        product_label.setStyleSheet("color: #1e293b; background-color: #f8fafc; padding: 10px; border-radius: 6px;")
        product_label.setWordWrap(True)
        
        # Current price display
        current_price_label = QLabel(f"Current Price: <b>ETB {current_price:.2f}</b>")
        current_price_label.setFont(QFont("Segoe UI", 11))
        current_price_label.setStyleSheet("color: #059669;")
        
        # New price input
        new_price_label = QLabel("New Price:")
        new_price_label.setFont(QFont("Segoe UI", 10))
        
        self.price_input = QDoubleSpinBox()
        self.price_input.setDecimals(2)
        self.price_input.setRange(0.01, 999999.99)
        self.price_input.setValue(float(current_price))
        self.price_input.setPrefix("ETB ")
        self.price_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.price_input.setFixedHeight(36)
        self.price_input.setStyleSheet("""
            QDoubleSpinBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 0px 12px;
                font-size: 13px;
                font-weight: 500;
                background-color: white;
                color: #1f2937;
            }
            QDoubleSpinBox:focus {
                border: 1px solid #3b82f6;
                background-color: #f8fafc;
            }
        """)
        
        input_layout.addWidget(product_label)
        input_layout.addWidget(current_price_label)
        input_layout.addWidget(new_price_label)
        input_layout.addWidget(self.price_input)
        
        main_layout.addLayout(input_layout)
        
        # Warning note
        note_label = QLabel("⚠️ This change will affect all batches and future sales of this product.")
        note_label.setFont(QFont("Segoe UI", 9))
        note_label.setStyleSheet("color: #92400e; background-color: #fffbeb; padding: 8px 12px; border-radius: 4px; border: 1px solid #fbbf24;")
        note_label.setWordWrap(True)
        
        main_layout.addWidget(note_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(100, 36)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 500;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Update Price")
        self.save_btn.setFixedSize(120, 36)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.save_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(button_layout)
        
        # Set focus
        self.price_input.setFocus()
        self.price_input.selectAll()
    
    def get_price(self):
        """Get the entered price"""
        return self.price_input.value()