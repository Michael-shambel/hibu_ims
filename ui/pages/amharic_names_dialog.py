#!/usr/bin/env python3
"""
Amharic Names — review and fix the Amharic spelling of product names and
delivery names used in the Telegram notifications.

Three ways to fix a name, none of them needs an Amharic keyboard:

    1. click one of the suggested spellings
    2. type it in the "sounds like" box in latin letters (storaj -> ስቶራጅ)
    3. paste/type the Amharic directly

Every saved fix is remembered and used in every future notification
(database/amharic_overrides.json, next to the database file).
"""

import json
import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from services.amharic_service import AmharicService
from services.new_product_service import NewProductService
from services.new_sale_service import NewSaleService

logger = logging.getLogger(__name__)

# Amharic (Geez) needs an Ethiopic font: the normal UI font ("Segoe UI") has no
# Geez glyphs, so without this list every Amharic name is drawn as empty boxes.
# Same convention as the header date label in main_window.py and the product
# performance dialog.
AMHARIC_FONT_FAMILIES = ("Noto Sans Ethiopic", "Nyala", "Abyssinica SIL", "Ebrima")
AMHARIC_FONT_FAMILY = ", ".join(
    f'"{family}"' for family in AMHARIC_FONT_FAMILIES) + ', "Segoe UI", sans-serif'


def amharic_qfont(size: int = 11, bold: bool = False) -> QFont:
    """The first Ethiopic font this PC actually has (Nyala/Ebrima on Windows)."""
    weight = QFont.Bold if bold else QFont.Normal
    for family in AMHARIC_FONT_FAMILIES:
        if family in QFontDatabase.families():
            return QFont(family, size, weight)
    return QFont("Segoe UI", size, weight)  # stylesheet list still applies

SOURCE_LABELS = {
    "custom": "✍️ custom",
    "seed": "✅ checked",
    "rules": "🤖 automatic",
    "none": "",
}


class AmharicNamesDialog(QDialog):
    """Dialog opened from Reports -> Admin tab -> Amharic Names."""

    COL_NAME = 0
    COL_AMHARIC = 1
    COL_SOURCE = 2
    COL_ACTION = 3

    def __init__(self, parent=None, current_user=None):
        super().__init__(parent)
        self.amharic = AmharicService()
        self.product_service = NewProductService()
        self.sale_service = NewSaleService()

        self._loading = False
        self._rows = {"products": [], "delivery": []}

        self.setWindowTitle("🇪🇹 Amharic Names")
        self.setMinimumSize(1150, 720)
        self._apply_amharic_font()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("<b>Amharic names in the store / admin messages</b>")
        title.setStyleSheet("font-size: 15px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Everything is converted automatically. Fix a name here only if the "
            "Amharic is not what your store team writes — it is remembered forever."
        )
        subtitle.setStyleSheet("color: #607d8b;")
        layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tab("products"), "Products")
        self.tabs.addTab(self._build_tab("delivery"), "Delivery names")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

        layout.addWidget(self._build_fix_panel())

        footer = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #607d8b;")
        footer.addWidget(self.status_label, 1)

        refresh_btn = QPushButton("🔄 Refresh lists")
        refresh_btn.clicked.connect(self.reload_data)
        footer.addWidget(refresh_btn)

        export_btn = QPushButton("⬇️ Export fixes")
        export_btn.clicked.connect(self.export_fixes)
        footer.addWidget(export_btn)

        import_btn = QPushButton("⬆️ Import fixes")
        import_btn.clicked.connect(self.import_fixes)
        footer.addWidget(import_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background-color: #37474f; color: white; padding: 6px 18px;")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

        self.reload_data()

    # ------------------------------------------------------------- building
    def _apply_amharic_font(self):
        """Render Geez characters instead of empty boxes (see AMHARIC_FONT_FAMILY)."""
        self.setFont(amharic_qfont(11))
        self.setStyleSheet(
            f"QDialog, QDialog * {{ font-family: {AMHARIC_FONT_FAMILY}; }}")

    def _build_tab(self, kind: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(8)

        top = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Search…")
        search.textChanged.connect(lambda _text, k=kind: self.populate_table(k))
        top.addWidget(search, 1)

        only_flagged = QCheckBox("Only fixed / needs review")
        only_flagged.stateChanged.connect(lambda _state, k=kind: self.populate_table(k))
        top.addWidget(only_flagged)

        if kind == "delivery":
            top.addWidget(QLabel("How many:"))
            limit_combo = QComboBox()
            limit_combo.addItems(["100", "300", "1000", "all"])
            limit_combo.setCurrentIndex(0)
            limit_combo.currentIndexChanged.connect(
                lambda _index: self.load_delivery_names())
            top.addWidget(limit_combo)
            self.delivery_limit_combo = limit_combo
        layout.addLayout(top)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Name (as typed)", "Amharic", "Source", ""])
        table.horizontalHeader().setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(self.COL_AMHARIC, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(self.COL_SOURCE, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(self.COL_ACTION, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setFont(amharic_qfont(12))
        table.setStyleSheet(f"""
            QTableWidget {{
                font-family: {AMHARIC_FONT_FAMILY};
                font-size: 13px;
            }}
            QHeaderView::section {{
                font-family: "Segoe UI", "Arial", sans-serif;
                font-weight: bold;
            }}
        """)
        table.itemSelectionChanged.connect(lambda k=kind: self._on_row_selected(k))
        table.itemChanged.connect(lambda item, k=kind: self._on_item_changed(k, item))
        layout.addWidget(table, 1)

        if kind == "products":
            self.products_table = table
            self.products_search = search
            self.products_filter = only_flagged
        else:
            self.delivery_table = table
            self.delivery_search = search
            self.delivery_filter = only_flagged
        return page

    def _build_fix_panel(self) -> QWidget:
        panel = QWidget()
        # Styled through its object name: a plain "QWidget" rule would also paint
        # this frame around every label, input and button inside the panel.
        panel.setObjectName("fixPanel")
        panel.setStyleSheet(
            "QWidget#fixPanel { background-color: #f4f6f8; "
            "border: 1px solid #cfd8dc; border-radius: 6px; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.selected_label = QLabel("Select a row above to fix its Amharic spelling.")
        self.selected_label.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(self.selected_label)

        suggestions_row = QHBoxLayout()
        suggestions_row.addWidget(QLabel("Suggestions:"))
        self.suggestions_container = QWidget()
        self.suggestions_container.setStyleSheet("border: none;")
        self.suggestions_layout = QHBoxLayout(self.suggestions_container)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestions_layout.setSpacing(6)
        suggestions_row.addWidget(self.suggestions_container, 1)
        layout.addLayout(suggestions_row)

        sounds_row = QHBoxLayout()
        sounds_row.addWidget(QLabel("Sounds like:"))
        self.sounds_input = QLineEdit()
        self.sounds_input.setPlaceholderText(
            "type it the way it sounds in latin letters, e.g. storaj or tena yistilign")
        self.sounds_input.textChanged.connect(self._preview_sounds)
        sounds_row.addWidget(self.sounds_input, 1)
        self.sounds_preview = QLabel("—")
        self.sounds_preview.setStyleSheet("font-size: 15px; border: none;")
        sounds_row.addWidget(self.sounds_preview)
        use_sounds = QPushButton("Use")
        use_sounds.clicked.connect(self._use_sounds)
        sounds_row.addWidget(use_sounds)
        layout.addLayout(sounds_row)

        fix_row = QHBoxLayout()
        fix_row.addWidget(QLabel("Amharic:"))
        self.fix_input = QLineEdit()
        self.fix_input.setPlaceholderText("the Amharic that should be sent")
        fix_row.addWidget(self.fix_input, 1)
        save_btn = QPushButton("💾 Save for this name")
        save_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        save_btn.clicked.connect(self.save_fix)
        fix_row.addWidget(save_btn)
        reset_btn = QPushButton("↺ Automatic")
        reset_btn.clicked.connect(self.reset_fix)
        fix_row.addWidget(reset_btn)
        layout.addLayout(fix_row)

        self.fix_status = QLabel("")
        self.fix_status.setStyleSheet("color: #607d8b; border: none;")
        layout.addWidget(self.fix_status)
        return panel

    # ---------------------------------------------------------------- data
    def reload_data(self):
        self._load_products()
        self.load_delivery_names()
        self._update_status()

    def _load_products(self):
        try:
            products = self.product_service.get_paginated(offset=0, limit=5000) or []
        except Exception as exc:
            logger.error("Failed to load products for Amharic dialog: %s", exc)
            products = []
        self._rows["products"] = sorted(
            {p.get("name", "").strip() for p in products if p.get("name")},
            key=str.upper)
        self.populate_table("products")

    def load_delivery_names(self):
        try:
            limit_text = self.delivery_limit_combo.currentText()
            limit = 100000 if limit_text == "all" else int(limit_text)
            names = self.sale_service.get_delivery_names_with_frequency("", limit=limit) or []
        except Exception as exc:
            logger.error("Failed to load delivery names for Amharic dialog: %s", exc)
            names = []
        self._rows["delivery"] = [n for n in names if n]
        self.populate_table("delivery")

    def _table_and_filters(self, kind: str):
        if kind == "products":
            return self.products_table, self.products_search, self.products_filter
        return self.delivery_table, self.delivery_search, self.delivery_filter

    def populate_table(self, kind: str, select_name: str = None):
        table, search, only_flagged = self._table_and_filters(kind)
        needle = search.text().strip().upper()
        show_flagged = only_flagged.isChecked()
        keep_selected = select_name if select_name is not None else self._selected_name_for(kind)

        self._loading = True
        try:
            rows = []
            for name in self._rows[kind]:
                if needle and needle not in name.upper():
                    continue
                if show_flagged and not (self.amharic.is_custom(name)
                                         or self.amharic.needs_review(name)):
                    continue
                rows.append(name)

            table.setRowCount(0)
            table.setRowCount(len(rows))
            for row, name in enumerate(rows):
                amharic, source = self.amharic.describe(name)

                name_item = QTableWidgetItem(name)
                name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                table.setItem(row, self.COL_NAME, name_item)

                amharic_item = QTableWidgetItem(amharic or "")
                amharic_item.setToolTip("Edit this text to correct the Amharic")
                table.setItem(row, self.COL_AMHARIC, amharic_item)

                source_text = SOURCE_LABELS.get(source, source)
                if self.amharic.needs_review(name):
                    source_text += "  ⚠️ review"
                source_item = QTableWidgetItem(source_text)
                source_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                table.setItem(row, self.COL_SOURCE, source_item)

                table.setCellWidget(row, self.COL_ACTION, self._reset_button(name))

            if keep_selected and keep_selected in rows:
                table.selectRow(rows.index(keep_selected))
        finally:
            self._loading = False

    def _reset_button(self, name: str) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("↺")
        button.setToolTip("Use the automatic conversion again")
        button.setFixedWidth(34)
        button.clicked.connect(lambda _checked=False, n=name: self._reset_name(n))
        layout.addWidget(button)
        return holder

    # ------------------------------------------------------------- actions
    def _current_kind(self) -> str:
        return "products" if self.tabs.currentIndex() == 0 else "delivery"

    def _current_table(self):
        return self.products_table if self._current_kind() == "products" else self.delivery_table

    def _selected_name(self):
        return self._selected_name_for(self._current_kind())

    def _selected_name_for(self, kind: str):
        table, _search, _filter = self._table_and_filters(kind)
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, self.COL_NAME)
        return item.text() if item else None

    def _on_tab_changed(self, _index):
        self._clear_fix_panel()

    def _on_row_selected(self, kind: str):
        if kind != self._current_kind():
            return
        name = self._selected_name()
        if not name:
            return
        self.selected_label.setText(f"Fixing: {name}")
        self._fill_suggestions(name)

    def _on_item_changed(self, kind: str, item):
        if self._loading or item.column() != self.COL_AMHARIC:
            return
        table, _search, _filter = self._table_and_filters(kind)
        name_item = table.item(item.row(), self.COL_NAME)
        if not name_item:
            return
        name = name_item.text()
        value = item.text().strip()
        auto_value, _source = self.amharic.describe(name)
        if not value:
            return
        if value == (auto_value or "").strip() and not self.amharic.is_custom(name):
            return
        self.amharic.set_override(name, value)
        self.populate_table(kind, select_name=name)
        self._update_status()
        self.fix_status.setText(f"✅ “{name}” will now be sent as: {value}")

    def _fill_suggestions(self, name: str):
        while self.suggestions_layout.count():
            widget = self.suggestions_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        for source, value in self.amharic.suggest(name):
            button = QPushButton(f"{value}   ({SOURCE_LABELS.get(source, source)})")
            button.setStyleSheet("background-color: white; border: 1px solid #90a4ae; padding: 4px 8px;")
            button.clicked.connect(lambda _checked=False, v=value: self.fix_input.setText(v))
            self.suggestions_layout.addWidget(button)
        self.suggestions_layout.addStretch()

        current, source = self.amharic.describe(name)
        self.fix_input.setText(current or "")
        self.sounds_input.clear()
        self.sounds_preview.setText("—")
        self.fix_status.setText(f"Current spelling comes from: {SOURCE_LABELS.get(source, source)}")

    def _clear_fix_panel(self):
        self.selected_label.setText("Select a row above to fix its Amharic spelling.")
        while self.suggestions_layout.count():
            widget = self.suggestions_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.fix_input.clear()
        self.sounds_input.clear()
        self.sounds_preview.setText("—")
        self.fix_status.setText("")

    def _preview_sounds(self, text: str):
        converted = self.amharic.to_amharic_phonetic(text) if text.strip() else ""
        self.sounds_preview.setText(converted or "—")

    def _use_sounds(self):
        converted = self.amharic.to_amharic_phonetic(self.sounds_input.text())
        if converted and converted.strip():
            self.fix_input.setText(converted)

    def save_fix(self):
        kind = self._current_kind()
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Amharic Names", "Select a name in the list first.")
            return
        value = self.fix_input.text().strip()
        if not value:
            QMessageBox.information(self, "Amharic Names", "Enter the Amharic spelling first.")
            return
        self.amharic.set_override(name, value)
        self.populate_table(kind, select_name=name)
        self._update_status()
        self.fix_input.setText(value)
        self.fix_status.setText(f"✅ “{name}” will now be sent as: {value}")

    def reset_fix(self):
        name = self._selected_name()
        if not name:
            return
        self._reset_name(name)

    def _reset_name(self, name: str):
        kind = "products" if any(name == n for n in self._rows["products"]) else "delivery"
        if name not in self._rows[kind]:
            kind = self._current_kind()
        self.amharic.remove_override(name)
        self.populate_table(kind, select_name=name)
        self._update_status()
        self._fill_suggestions(name)
        self.fix_status.setText(f"↺ “{name}” uses the automatic conversion again.")

    def export_fixes(self):
        path, _selected = QFileDialog.getSaveFileName(
            self, "Export Amharic fixes", "amharic_overrides.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "entries": self.amharic.all_overrides()},
                          handle, ensure_ascii=False, indent=2, sort_keys=True)
            QMessageBox.information(self, "Amharic Names", f"Fixes exported to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Amharic Names", f"Export failed: {exc}")

    def import_fixes(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "Import Amharic fixes", "", "JSON (*.json)")
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            entries = data.get("entries") or data
            count = 0
            for key, value in entries.items():
                if isinstance(value, str) and value.strip():
                    self.amharic.set_override(key, value)
                    count += 1
            self.reload_data()
            QMessageBox.information(self, "Amharic Names", f"{count} fixes imported.")
        except Exception as exc:
            QMessageBox.critical(self, "Amharic Names", f"Import failed: {exc}")

    def _update_status(self):
        stats = self.amharic.stats()
        self.status_label.setText(
            f"{stats['corrections']} corrections saved · "
            f"{stats['seed_review']} names flagged for review · "
            f"dictionary: {stats['seed_entries']} entries · "
            f"engine: {'fidel' if stats['fidel_available'] else 'built-in table'}"
        )
