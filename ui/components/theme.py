#!/usr/bin/env python3
"""Shared visual language for the inventory UI.

Import the tokens and widget builders from here instead of hard-coding hex
values, so every page keeps the same palette, spacing and table styling.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

# ==================== PALETTE ====================
PRIMARY = "#3498db"
PRIMARY_DARK = "#2980b9"

SUCCESS = "#27ae60"
SUCCESS_DARK = "#1e8449"

DANGER = "#e74c3c"
DANGER_DARK = "#c0392b"

WARNING = "#f39c12"
WARNING_DARK = "#c87f0a"

ORANGE = "#e67e22"
ORANGE_DARK = "#ca6f1e"

PURPLE = "#8e44ad"
PURPLE_DARK = "#7d3c98"

SLATE = "#64748b"
SLATE_DARK = "#475569"

TEXT = "#1e293b"
MUTED = "#64748b"
BORDER = "#e2e8f0"
SURFACE = "#ffffff"
CANVAS = "#f8fafc"
ROW_LINE = "#f1f5f9"
SELECTION = "#eff6ff"
DISABLED_BG = "#eef2f7"
DISABLED_TEXT = "#a0aec0"

FONT = "Segoe UI"
ROW_HEIGHT = 54
HEADER_HEIGHT = 44
LOW_STOCK_LIMIT = 10

STOCK_OK = ("#dcfce7", "#15803d")
STOCK_LOW = ("#fef3c7", "#b45309")
STOCK_OUT = ("#fee2e2", "#b91c1c")


# ==================== STOCK HELPERS ====================

def stock_tone(qty):
    """Return the (background, foreground) pill colours for a stock level."""
    try:
        value = int(qty)
    except (TypeError, ValueError):
        value = 0

    if value <= 0:
        return STOCK_OUT
    if value <= LOW_STOCK_LIMIT:
        return STOCK_LOW
    return STOCK_OK


def stock_color(qty):
    """Return just the text colour for a stock level."""
    return stock_tone(qty)[1]


def stock_tooltip(qty):
    try:
        value = int(qty)
    except (TypeError, ValueError):
        value = 0

    if value <= 0:
        return "Out of stock"
    if value <= LOW_STOCK_LIMIT:
        return f"Low stock ({LOW_STOCK_LIMIT} or fewer)"
    return "In stock"


# ==================== SURFACES ====================

CARD_QSS = f"""
    QFrame#card {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}
"""


def card_frame():
    """White rounded panel used for every surface."""
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(CARD_QSS)
    return frame


class StatCard(QFrame):
    """KPI summary card: accent bar, caption, value and an icon."""

    def __init__(self, title, value, color, icon="", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(CARD_QSS)
        self.setFixedHeight(86)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self._accent = QFrame()
        self._accent.setFixedWidth(4)
        self._accent.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)

        self.caption = QLabel(title.upper())
        self.caption.setFont(QFont(FONT, 8, QFont.DemiBold))
        self.caption.setStyleSheet(f"color: {MUTED}; background: transparent;")

        self.value_label = QLabel(str(value))
        self.value_label.setFont(QFont(FONT, 17, QFont.Bold))

        text_box.addWidget(self.caption)
        text_box.addWidget(self.value_label)

        self.icon_label = QLabel(icon)
        self.icon_label.setFont(QFont(FONT, 18))
        self.icon_label.setStyleSheet("background: transparent;")

        layout.addWidget(self._accent)
        layout.addLayout(text_box)
        layout.addStretch()
        layout.addWidget(self.icon_label)

        self.set_color(color)

    def set_color(self, color):
        """Recolour both the accent bar and the value text."""
        self._accent.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        self.value_label.setStyleSheet(f"color: {color}; background: transparent;")

    def set_value(self, text):
        self.value_label.setText(str(text))

    def value(self):
        return self.value_label.text()


INPUT_QSS = f"""
    QLineEdit {{
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
        color: {TEXT};
        background-color: {SURFACE};
    }}
    QLineEdit:focus {{
        border: 1px solid {PRIMARY};
    }}
"""


def style_input(line_edit, min_height=38):
    """Apply the shared form-field look to a QLineEdit."""
    line_edit.setMinimumHeight(min_height)
    line_edit.setStyleSheet(INPUT_QSS)
    return line_edit


def pill_label(text, bg, fg, min_width=52, tooltip=""):
    """Generic colour-coded pill, ready to drop into a table cell."""
    container = QWidget()
    container.setObjectName("cellWidget")
    container.setStyleSheet("#cellWidget { background: transparent; }")

    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignCenter)

    badge = QLabel(str(text))
    badge.setAlignment(Qt.AlignCenter)
    badge.setMinimumWidth(min_width)
    if tooltip:
        badge.setToolTip(tooltip)
    badge.setFont(QFont(FONT, 9, QFont.DemiBold))
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: {bg};
            color: {fg};
            border-radius: 10px;
            padding: 4px 12px;
        }}
    """)

    layout.addWidget(badge)
    return container


# ==================== BUTTONS ====================

def style_filled(button, color, hover, min_height=38):
    """Solid button used for page toolbars and dialog actions."""
    button.setCursor(Qt.PointingHandCursor)
    button.setMinimumHeight(min_height)
    button.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover:enabled {{
            background-color: {hover};
        }}
        QPushButton:disabled {{
            background-color: {DISABLED_BG};
            color: {DISABLED_TEXT};
        }}
    """)


def style_outline(button, color, min_height=38):
    """Neutral secondary button: white fill, coloured label, hover fill."""
    button.setCursor(Qt.PointingHandCursor)
    button.setMinimumHeight(min_height)
    button.setStyleSheet(f"""
        QPushButton {{
            background-color: {SURFACE};
            color: {color};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover:enabled {{
            background-color: {CANVAS};
            border-color: {color};
        }}
        QPushButton:disabled {{
            background-color: {CANVAS};
            color: {DISABLED_TEXT};
            border-color: {DISABLED_BG};
        }}
    """)


def action_button(text, tooltip, color, width, height=30):
    """Compact row-level button: outline by default, filled on hover."""
    button = QPushButton(text)
    button.setFixedSize(width, height)
    button.setCursor(Qt.PointingHandCursor)
    button.setFont(QFont(FONT, 9, QFont.DemiBold))
    button.setToolTip(tooltip)
    button.setStyleSheet(f"""
        QPushButton {{
            background-color: {SURFACE};
            color: {color};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-weight: 600;
        }}
        QPushButton:hover:enabled {{
            background-color: {color};
            color: #ffffff;
            border-color: {color};
        }}
        QPushButton:disabled {{
            color: #cbd5e1;
            background-color: {CANVAS};
            border-color: {DISABLED_BG};
        }}
    """)
    return button


def action_cell(buttons, spacing=5):
    """Wrap row action buttons in a transparent table-cell container."""
    widget = QWidget()
    widget.setObjectName("cellWidget")
    widget.setStyleSheet("#cellWidget { background: transparent; }")

    layout = QHBoxLayout(widget)
    layout.setContentsMargins(4, 0, 4, 0)
    layout.setSpacing(spacing)
    layout.setAlignment(Qt.AlignCenter)

    for button in buttons:
        layout.addWidget(button)
    return widget


def action_cell_width(buttons, spacing=5):
    """Minimum column width that fits a set of action buttons."""
    return sum(b.width() for b in buttons) + spacing * (len(buttons) - 1) + 8


# ==================== TABLES ====================

TABLE_QSS = f"""
    QTableWidget {{
        background-color: {SURFACE};
        border: none;
        gridline-color: transparent;
        font-size: 13px;
        color: {TEXT};
        selection-background-color: {SELECTION};
        selection-color: {TEXT};
    }}
    QTableWidget::item {{
        padding-left: 12px;
        padding-right: 12px;
        border-bottom: 1px solid {ROW_LINE};
    }}
    QTableWidget::item:selected {{
        background-color: {SELECTION};
        color: {TEXT};
    }}
    QHeaderView::section {{
        background-color: {CANVAS};
        color: {MUTED};
        font-size: 11px;
        font-weight: 700;
        padding: 12px;
        border: none;
        border-bottom: 1px solid {BORDER};
    }}
    QTableCornerButton::section {{
        background-color: {CANVAS};
        border: none;
    }}
"""


def style_table(table, row_height=ROW_HEIGHT, header_height=HEADER_HEIGHT):
    """Apply the shared data-grid look to a QTableWidget."""
    table.setStyleSheet(TABLE_QSS)
    table.setShowGrid(False)
    table.setAlternatingRowColors(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setFocusPolicy(Qt.NoFocus)
    table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
    table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)

    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setFixedHeight(header_height)
    return header


def align_header(table, column, alignment):
    """Align a single header section (e.g. right for money columns)."""
    item = table.horizontalHeaderItem(column)
    if item is not None:
        item.setTextAlignment(alignment)


def card_section_header(title, trailing_text="", trailing_object_name="sectionCount"):
    """Title row used at the top of a card that contains a table."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(18, 14, 18, 12)
    layout.setSpacing(10)

    title_label = QLabel(title)
    title_label.setFont(QFont(FONT, 13, QFont.Bold))
    title_label.setStyleSheet(f"color: {TEXT}; background: transparent;")

    layout.addWidget(title_label)
    layout.addStretch()

    count_label = QLabel(trailing_text)
    count_label.setObjectName(trailing_object_name)
    count_label.setStyleSheet(f"color: {MUTED}; font-size: 12px; background: transparent;")

    layout.addWidget(count_label)
    return widget, count_label


def stock_badge(qty, min_width=52):
    """Pill label colour coded by stock level, ready for a table cell."""
    bg, fg = stock_tone(qty)
    try:
        value = int(qty)
    except (TypeError, ValueError):
        value = 0

    return pill_label(f"{value:,}", bg, fg, min_width, stock_tooltip(value))


def format_number(value):
    """Render whole numbers without a decimal tail."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"
