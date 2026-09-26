#!/usr/bin/env python3
"""
Report Subscriptions dialog.

Three tabs:
  1. Product Groups  – build the reusable product sets (e.g. "Group A" = 20 of
     the 40 products) that scope a report.
  2. Subscribers     – who receives what: an admin account or an external
     Telegram recipient, full report or specific groups, per report type.
  3. Expense Tags    – tag expenses to a product group, singly in bulk, so a
     scoped report carries that group's expenses (and thus its net profit).
"""
import logging
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from services.auth_service import AuthService
from services.expense_category_service import ExpenseCategoryService
from services.expense_service import ExpenseService
from services.product_group_service import ProductGroupService
from services.report_subscription_service import (
    REPORT_TYPE_LABELS, ReportSubscriptionService,
)

logger = logging.getLogger(__name__)

NO_GROUP = '— none (untagged) —'
ALL_GROUPS = '— all —'


class ReportSubscriptionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.group_service = ProductGroupService()
        self.subscription_service = ReportSubscriptionService()
        self.expense_service = ExpenseService()
        self.category_service = ExpenseCategoryService()
        self.auth_service = AuthService()

        self.selected_group_id = None
        self.selected_subscriber_id = None
        self._saved_member_count = 0
        # Source of truth for the group-member checklist (see load_product_choices).
        self.selected_product_ids = set()

        self.setWindowTitle("Report Subscriptions")
        self.setMinimumSize(1100, 720)
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.groups_tab = QWidget()
        self.tabs.addTab(self.groups_tab, "Product Groups")
        self.setup_groups_tab()

        self.subscribers_tab = QWidget()
        self.tabs.addTab(self.subscribers_tab, "Subscribers")
        self.setup_subscribers_tab()

        self.expenses_tab = QWidget()
        self.tabs.addTab(self.expenses_tab, "Expense Tags")
        self.setup_expenses_tab()

        close_btn = QPushButton("Close")
        close_btn.setMinimumSize(110, 36)
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.reload_all()

    # ==================================================================
    # Shared helpers
    # ==================================================================
    def reload_all(self):
        self.load_groups()
        self.load_product_choices(preselect=set())
        self.load_subscribers()
        self.load_expense_filters()
        self.load_expenses()

    def _make_table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    # ==================================================================
    # Tab 1 — Product Groups
    # ==================================================================
    def setup_groups_tab(self):
        layout = QHBoxLayout(self.groups_tab)

        # --- left: group list ---
        left = QVBoxLayout()
        left.addWidget(QLabel("Product groups"))
        self.groups_table = self._make_table(["ID", "Name", "Products", "Active"])
        self.groups_table.itemSelectionChanged.connect(self.on_group_selected)
        left.addWidget(self.groups_table)

        group_btns = QHBoxLayout()
        new_btn = QPushButton("New Group")
        new_btn.clicked.connect(self.clear_group_form)
        group_btns.addWidget(new_btn)
        del_btn = QPushButton("Delete Group")
        del_btn.setStyleSheet("background-color: #f44336; color: white;")
        del_btn.clicked.connect(self.delete_group)
        group_btns.addWidget(del_btn)
        left.addLayout(group_btns)

        left_box = QWidget()
        left_box.setLayout(left)
        layout.addWidget(left_box, 1)

        # --- right: form + members ---
        right = QVBoxLayout()

        form_box = QGroupBox("Group details")
        form = QFormLayout(form_box)
        self.group_name_input = QLineEdit()
        self.group_name_input.setPlaceholderText("e.g. Group A")
        form.addRow("Name:", self.group_name_input)
        self.group_desc_input = QLineEdit()
        self.group_desc_input.setPlaceholderText("Optional description")
        form.addRow("Description:", self.group_desc_input)
        self.group_active_check = QCheckBox("Active (usable in subscriptions)")
        self.group_active_check.setChecked(True)
        form.addRow("", self.group_active_check)

        save_group_btn = QPushButton("Save Group")
        save_group_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        save_group_btn.clicked.connect(self.save_group)
        form.addRow(save_group_btn)
        right.addWidget(form_box)

        members_box = QGroupBox("Products in this group")
        members_layout = QVBoxLayout(members_box)
        search_row = QHBoxLayout()
        self.product_search_input = QLineEdit()
        self.product_search_input.setPlaceholderText("Search products…")
        # textChanged hands the new text to the slot, which is not what we want.
        self.product_search_input.textChanged.connect(lambda *_: self.load_product_choices())
        search_row.addWidget(self.product_search_input)
        right.addWidget(members_box)

        members_layout.addLayout(search_row)
        self.product_list = QListWidget()
        self.product_list.setSelectionMode(QAbstractItemView.NoSelection)
        members_layout.addWidget(self.product_list)

        member_btns = QHBoxLayout()
        self.member_count_label = QLabel("0 selected")
        member_btns.addWidget(self.member_count_label)
        member_btns.addStretch()
        select_all_btn = QPushButton("Select All Shown")
        select_all_btn.clicked.connect(lambda: self.toggle_all_products(True))
        member_btns.addWidget(select_all_btn)
        clear_all_btn = QPushButton("Clear Selection")
        clear_all_btn.clicked.connect(lambda: self.toggle_all_products(False))
        member_btns.addWidget(clear_all_btn)
        save_members_btn = QPushButton("Save Members")
        save_members_btn.setStyleSheet("background-color: #2196F3; color: white;")
        save_members_btn.clicked.connect(self.save_group_members)
        member_btns.addWidget(save_members_btn)
        members_layout.addLayout(member_btns)

        right_box = QWidget()
        right_box.setLayout(right)
        layout.addWidget(right_box, 1)

        self.product_list.itemChanged.connect(self.on_product_item_changed)

    def load_groups(self):
        self.groups_table.setRowCount(0)
        try:
            for group in self.group_service.list_with_counts():
                row = self.groups_table.rowCount()
                self.groups_table.insertRow(row)
                self.groups_table.setItem(row, 0, QTableWidgetItem(str(group['id'])))
                self.groups_table.setItem(row, 1, QTableWidgetItem(group['name']))
                self.groups_table.setItem(row, 2, QTableWidgetItem(str(group['product_count'])))
                active_item = QTableWidgetItem("Yes" if group['is_active'] else "No")
                if not group['is_active']:
                    active_item.setForeground(QColor("#999999"))
                self.groups_table.setItem(row, 3, active_item)
        except Exception as e:
            logger.error("Failed to load product groups: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to load product groups: {e}")

    def on_group_selected(self):
        items = self.groups_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        group_id = int(self.groups_table.item(row, 0).text())
        self.load_group_form(group_id)

    def load_group_form(self, group_id):
        self.selected_group_id = group_id
        groups = {g['id']: g for g in self.group_service.list_with_counts()}
        group = groups.get(group_id)
        if not group:
            return

        self.group_name_input.setText(group['name'])
        self.group_desc_input.setText(group['description'] or '')
        self.group_active_check.setChecked(group['is_active'])

        # Show the group's members pre-checked, then the rest of the catalogue.
        # Selection is set first so the search-clear re-render shows the right ticks.
        member_ids = {m['id'] for m in self.group_service.get_members(group_id)}
        self._saved_member_count = len(member_ids)
        self.selected_product_ids = {int(m) for m in member_ids}
        self.product_search_input.clear()
        self.load_product_choices()

    def clear_group_form(self):
        self.selected_group_id = None
        self._saved_member_count = 0
        self.selected_product_ids = set()
        self.group_name_input.clear()
        self.group_desc_input.clear()
        self.group_active_check.setChecked(True)
        self.groups_table.clearSelection()
        self.product_search_input.clear()
        self.load_product_choices()

    def load_product_choices(self, preselect=None):
        """
        Render the checklist.

        The selection itself lives in `self.selected_product_ids`, NOT in the
        list widget, so searching (which filters which products are shown) never
        drops ticks on hidden products — otherwise typing in the search box could
        silently wipe a group's membership on the next "Save Members".

        `preselect` replaces the selection; None keeps it.
        """
        if preselect is not None:
            self.selected_product_ids = {int(p) for p in preselect}

        search = self.product_search_input.text().strip()
        try:
            products = self.group_service.get_products_for_picker(search)
        except Exception as e:
            logger.error("Failed to load product choices: %s", e)
            products = []

        self.product_list.blockSignals(True)
        self.product_list.clear()
        for product in products:
            label = f"{product['name']}  ({product['unit']})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, product['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if product['id'] in self.selected_product_ids else Qt.Unchecked)
            self.product_list.addItem(item)
        self.product_list.blockSignals(False)
        self.update_member_count()

    def on_product_item_changed(self, item):
        """Keep the tracked selection in step with the visible checkboxes."""
        product_id = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.selected_product_ids.add(product_id)
        else:
            self.selected_product_ids.discard(product_id)
        self.update_member_count()

    def _checked_product_ids(self):
        return set(self.selected_product_ids)

    def toggle_all_products(self, checked):
        """Tick/untick the products currently shown (the search filter applies)."""
        shown_ids = set()
        self.product_list.blockSignals(True)
        for i in range(self.product_list.count()):
            item = self.product_list.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            shown_ids.add(item.data(Qt.UserRole))
        self.product_list.blockSignals(False)

        if checked:
            self.selected_product_ids.update(shown_ids)
        else:
            self.selected_product_ids.difference_update(shown_ids)
        self.update_member_count()

    def update_member_count(self, *_):
        shown = self.product_list.count()
        checked = len(self._checked_product_ids())
        if self.selected_group_id is not None:
            self.member_count_label.setText(
                f"{checked} selected · {self._saved_member_count} saved in group · {shown} shown"
            )
        else:
            self.member_count_label.setText(f"{checked} selected · {shown} shown")

    def save_group(self):
        name = self.group_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "A group name is required.")
            return

        data = {
            'name': name,
            'description': self.group_desc_input.text().strip() or None,
            'is_active': self.group_active_check.isChecked(),
        }

        if self.selected_group_id:
            ok = self.group_service.update_group(self.selected_group_id, data)
        else:
            created = self.group_service.create_group(name, data['description'])
            ok = created is not None
            if created:
                self.selected_group_id = created.id

        if not ok:
            QMessageBox.critical(self, "Error", "Could not save the group (name may be taken).")
            return

        self.load_groups()
        QMessageBox.information(self, "Saved", f"Group '{name}' saved.")
        if self.selected_group_id:
            self.load_group_form(self.selected_group_id)

    def save_group_members(self):
        if self.selected_group_id is None:
            QMessageBox.warning(self, "No group", "Create or select a group first.")
            return
        product_ids = self._checked_product_ids()
        if self.group_service.set_members(self.selected_group_id, product_ids):
            self._saved_member_count = len(product_ids)
            self.load_groups()
            self.update_member_count()
            QMessageBox.information(
                self, "Saved", f"Group now contains {len(product_ids)} product(s)."
            )
        else:
            QMessageBox.critical(self, "Error", "Failed to save group members.")

    def delete_group(self):
        if not self.selected_group_id:
            QMessageBox.warning(self, "No group", "Select a group to delete.")
            return
        if QMessageBox.question(
            self, "Confirm", "Delete this group? Products, expenses and subscribers keep existing."
        ) != QMessageBox.Yes:
            return
        if self.group_service.delete_group(self.selected_group_id):
            self.clear_group_form()
            self.load_groups()
            self.load_subscribers()
            self.load_expense_filters()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete the group.")

    # ==================================================================
    # Tab 2 — Subscribers
    # ==================================================================
    def setup_subscribers_tab(self):
        layout = QVBoxLayout(self.subscribers_tab)

        self.subscribers_table = self._make_table(
            ["ID", "Name", "Chat ID", "Admin user", "Scope", "Groups", "Reports", "Active"]
        )
        self.subscribers_table.itemSelectionChanged.connect(self.on_subscriber_selected)
        layout.addWidget(self.subscribers_table)

        form_box = QGroupBox("Subscriber")
        form = QHBoxLayout(form_box)

        left_form = QFormLayout()
        self.sub_name_input = QLineEdit()
        self.sub_name_input.setPlaceholderText("e.g. Group A distributor")
        left_form.addRow("Name:", self.sub_name_input)

        self.sub_chat_input = QLineEdit()
        self.sub_chat_input.setPlaceholderText("Telegram chat id (send /getid to the bot)")
        left_form.addRow("Chat ID:", self.sub_chat_input)

        self.sub_admin_combo = QComboBox()
        left_form.addRow("Linked admin:", self.sub_admin_combo)

        self.sub_full_check = QCheckBox("Full report (ignore product groups)")
        self.sub_full_check.setChecked(True)
        self.sub_full_check.stateChanged.connect(self.on_full_report_toggled)
        left_form.addRow("", self.sub_full_check)

        self.sub_active_check = QCheckBox("Active")
        self.sub_active_check.setChecked(True)
        left_form.addRow("", self.sub_active_check)

        self.sub_notes_input = QLineEdit()
        left_form.addRow("Notes:", self.sub_notes_input)

        form.addLayout(left_form, 1)

        mid_form = QVBoxLayout()
        mid_form.addWidget(QLabel("Product groups — tick the ones this subscriber gets"))
        self.sub_groups_list = QListWidget()
        self.sub_groups_list.setSelectionMode(QAbstractItemView.NoSelection)
        mid_form.addWidget(self.sub_groups_list)
        self.sub_scope_hint = QLabel()
        self.sub_scope_hint.setWordWrap(True)
        self.sub_scope_hint.setMinimumWidth(280)
        mid_form.addWidget(self.sub_scope_hint)
        form.addLayout(mid_form, 1)

        right_form = QVBoxLayout()
        right_form.addWidget(QLabel("Report types"))
        self.sub_type_checks = {}
        for key, label in REPORT_TYPE_LABELS.items():
            check = QCheckBox(label)
            check.setChecked(True)
            self.sub_type_checks[key] = check
            right_form.addWidget(check)
        right_form.addStretch()
        form.addLayout(right_form)

        layout.addWidget(form_box)

        btns = QHBoxLayout()
        new_btn = QPushButton("New Subscriber")
        new_btn.clicked.connect(self.clear_subscriber_form)
        btns.addWidget(new_btn)
        save_btn = QPushButton("Save Subscriber")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        save_btn.clicked.connect(self.save_subscriber)
        btns.addWidget(save_btn)
        del_btn = QPushButton("Delete Subscriber")
        del_btn.setStyleSheet("background-color: #f44336; color: white;")
        del_btn.clicked.connect(self.delete_subscriber)
        btns.addWidget(del_btn)
        btns.addStretch()
        layout.addLayout(btns)
        # setChecked() doesn't emit when the value is already True, so seed the
        # scope hint explicitly instead of relying on the signal.
        self.on_full_report_toggled()

    def load_subscribers(self):
        try:
            subscribers = self.subscription_service.list_subscribers()
        except Exception as e:
            logger.error("Failed to load subscribers: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to load subscribers: {e}")
            return

        self.subscribers_table.setRowCount(0)
        for sub in subscribers:
            row = self.subscribers_table.rowCount()
            self.subscribers_table.insertRow(row)
            scope = "Full report" if sub['full_report'] else "Product scoped"
            reports = [
                REPORT_TYPE_LABELS[key]
                for key, flag in (
                    ('daily', 'receive_daily'), ('monthly', 'receive_monthly'),
                    ('quarterly', 'receive_quarterly'), ('semiannual', 'receive_semiannual'),
                    ('annual', 'receive_annual'),
                ) if sub[flag]
            ]
            self.subscribers_table.setItem(row, 0, QTableWidgetItem(str(sub['id'])))
            self.subscribers_table.setItem(row, 1, QTableWidgetItem(sub['display_name']))
            self.subscribers_table.setItem(row, 2, QTableWidgetItem(str(sub['chat_id'])))
            self.subscribers_table.setItem(row, 3, QTableWidgetItem(sub['auth_username'] or '—'))
            self.subscribers_table.setItem(row, 4, QTableWidgetItem(scope))
            self.subscribers_table.setItem(row, 5, QTableWidgetItem(', '.join(sub['group_names']) or '—'))
            self.subscribers_table.setItem(row, 6, QTableWidgetItem(', '.join(reports)))
            status = QTableWidgetItem("Yes" if sub['is_active'] else "No")
            if not sub['is_active']:
                status.setForeground(QColor("#999999"))
            self.subscribers_table.setItem(row, 7, status)

        self.load_admin_choices()
        self.load_subscriber_group_choices()

    def load_admin_choices(self):
        current = self.sub_admin_combo.currentData()
        self.sub_admin_combo.clear()
        self.sub_admin_combo.addItem("— none (external subscriber) —", None)
        try:
            for user in self.auth_service.get_all():
                self.sub_admin_combo.addItem(
                    f"{user.username} ({user.role})", user.id
                )
        except Exception as e:
            logger.error("Failed to load users: %s", e)
        if current is not None:
            idx = self.sub_admin_combo.findData(current)
            if idx >= 0:
                self.sub_admin_combo.setCurrentIndex(idx)

    def load_subscriber_group_choices(self, preselect=None):
        if preselect is None:
            preselect = self._checked_subscriber_group_ids()

        self.sub_groups_list.blockSignals(True)
        self.sub_groups_list.clear()
        for group in self.group_service.list_with_counts():
            item = QListWidgetItem(f"{group['name']}  ({group['product_count']} products)")
            item.setData(Qt.UserRole, group['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if group['id'] in preselect else Qt.Unchecked)
            self.sub_groups_list.addItem(item)
        self.sub_groups_list.blockSignals(False)

    def _checked_subscriber_group_ids(self):
        ids = set()
        for i in range(self.sub_groups_list.count()):
            item = self.sub_groups_list.item(i)
            if item.checkState() == Qt.Checked:
                ids.add(item.data(Qt.UserRole))
        return ids

    def on_full_report_toggled(self, *args):
        full = self.sub_full_check.isChecked()
        self.sub_groups_list.setEnabled(not full)
        # The group list is disabled while "full report" is on, which is easy to
        # read as "ticking is broken". Say plainly what will happen instead.
        if full:
            self.sub_scope_hint.setText(
                "⛔ Full report is ON — this subscriber receives EVERY product, "
                "and any groups ticked below are ignored.\n"
                "Untick \"Full report\" to scope them to specific groups."
            )
            self.sub_scope_hint.setStyleSheet("color: #b58900; font-weight: bold;")
        else:
            self.sub_scope_hint.setText(
                "✅ Scoped report — tick the groups below, then press "
                "Save Subscriber. They receive only those products, and only "
                "expenses tagged to those groups. No group ticked = full report."
            )
            self.sub_scope_hint.setStyleSheet("color: #2e7d32; font-weight: bold;")

    def on_subscriber_selected(self):
        items = self.subscribers_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        subscriber_id = int(self.subscribers_table.item(row, 0).text())
        self.load_subscriber_form(subscriber_id)

    def load_subscriber_form(self, subscriber_id):
        sub = self.subscription_service.get_subscriber(subscriber_id)
        if not sub:
            return
        self.selected_subscriber_id = subscriber_id
        self.sub_name_input.setText(sub['display_name'])
        self.sub_chat_input.setText(str(sub['chat_id']))
        idx = self.sub_admin_combo.findData(sub['auth_user_id'])
        self.sub_admin_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.sub_full_check.setChecked(sub['full_report'])
        self.sub_active_check.setChecked(sub['is_active'])
        self.sub_notes_input.setText(sub['notes'] or '')
        self.load_subscriber_group_choices(set(sub['group_ids']))
        self.on_full_report_toggled()
        for key, check in self.sub_type_checks.items():
            check.setChecked(bool(sub[f'receive_{key}']))

    def clear_subscriber_form(self):
        self.selected_subscriber_id = None
        self.sub_name_input.clear()
        self.sub_chat_input.clear()
        self.sub_admin_combo.setCurrentIndex(0)
        self.sub_full_check.setChecked(True)
        self.sub_active_check.setChecked(True)
        self.sub_notes_input.clear()
        self.load_subscriber_group_choices(set())
        self.on_full_report_toggled()
        for check in self.sub_type_checks.values():
            check.setChecked(True)
        self.subscribers_table.clearSelection()

    def save_subscriber(self):
        name = self.sub_name_input.text().strip()
        chat_text = self.sub_chat_input.text().strip()
        if not name or not chat_text:
            QMessageBox.warning(self, "Validation", "Name and chat ID are required.")
            return
        try:
            chat_id = int(chat_text)
        except ValueError:
            QMessageBox.warning(self, "Validation", "Chat ID must be a number (send /getid to the bot).")
            return

        data = {
            'display_name': name,
            'chat_id': chat_id,
            'auth_user_id': self.sub_admin_combo.currentData(),
            'full_report': self.sub_full_check.isChecked(),
            'is_active': self.sub_active_check.isChecked(),
            'notes': self.sub_notes_input.text().strip() or None,
            'group_ids': sorted(self._checked_subscriber_group_ids()),
            'report_types': [k for k, c in self.sub_type_checks.items() if c.isChecked()],
        }

        if self.selected_subscriber_id:
            ok = self.subscription_service.update_subscriber(self.selected_subscriber_id, data)
        else:
            created = self.subscription_service.create_subscriber(
                display_name=name,
                chat_id=chat_id,
                auth_user_id=data['auth_user_id'],
                full_report=data['full_report'],
                report_types=data['report_types'],
                group_ids=data['group_ids'],
                notes=data['notes'],
            )
            ok = created is not None
            if created:
                self.selected_subscriber_id = created.id

        if not ok:
            QMessageBox.critical(self, "Error", "Could not save the subscriber (that chat ID may already exist).")
            return

        self.load_subscribers()
        QMessageBox.information(self, "Saved", f"Subscriber '{name}' saved.")

    def delete_subscriber(self):
        if not self.selected_subscriber_id:
            QMessageBox.warning(self, "No subscriber", "Select a subscriber first.")
            return
        if QMessageBox.question(self, "Confirm", "Remove this subscriber?") != QMessageBox.Yes:
            return
        if self.subscription_service.delete_subscriber(self.selected_subscriber_id):
            self.clear_subscriber_form()
            self.load_subscribers()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete the subscriber.")

    # ==================================================================
    # Tab 3 — Expense Tags
    # ==================================================================
    def setup_expenses_tab(self):
        layout = QVBoxLayout(self.expenses_tab)

        filters_box = QGroupBox("Filter")
        filters = QHBoxLayout(filters_box)

        filters.addWidget(QLabel("Group:"))
        self.exp_group_combo = QComboBox()
        self.exp_group_combo.currentIndexChanged.connect(self.load_expenses)
        filters.addWidget(self.exp_group_combo)

        filters.addWidget(QLabel("Category:"))
        self.exp_category_combo = QComboBox()
        self.exp_category_combo.currentIndexChanged.connect(self.load_expenses)
        filters.addWidget(self.exp_category_combo)

        filters.addWidget(QLabel("From:"))
        self.exp_from_date = QDateEdit()
        self.exp_from_date.setCalendarPopup(True)
        self.exp_from_date.setDate(QDate(QDate.currentDate().year(), QDate.currentDate().month(), 1))
        self.exp_from_date.dateChanged.connect(self.load_expenses)
        filters.addWidget(self.exp_from_date)

        filters.addWidget(QLabel("To:"))
        self.exp_to_date = QDateEdit()
        self.exp_to_date.setCalendarPopup(True)
        self.exp_to_date.setDate(QDate.currentDate())
        self.exp_to_date.dateChanged.connect(self.load_expenses)
        filters.addWidget(self.exp_to_date)

        self.exp_untagged_only = QCheckBox("Only untagged")
        self.exp_untagged_only.stateChanged.connect(self.load_expenses)
        filters.addWidget(self.exp_untagged_only)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_expenses)
        filters.addWidget(load_btn)
        filters.addStretch()
        layout.addWidget(filters_box)

        self.expenses_table = self._make_table(["Date", "Category", "Notes", "Amount", "Group"])
        layout.addWidget(self.expenses_table)

        self.exp_total_label = QLabel("")
        layout.addWidget(self.exp_total_label)

        action_box = QGroupBox("Tagging")
        actions = QHBoxLayout(action_box)
        actions.addWidget(QLabel("Assign selected filters to:"))
        self.tag_group_combo = QComboBox()
        actions.addWidget(self.tag_group_combo)
        apply_btn = QPushButton("Apply Tag")
        apply_btn.setStyleSheet("background-color: #2196F3; color: white;")
        apply_btn.clicked.connect(self.apply_tag)
        actions.addWidget(apply_btn)
        clear_btn = QPushButton("Clear Tag")
        clear_btn.clicked.connect(self.clear_tag)
        actions.addWidget(clear_btn)
        actions.addStretch()
        hint = QLabel("Bulk tagging uses the filters above (category + date range).")
        hint.setStyleSheet("color: #666666;")
        actions.addWidget(hint)
        layout.addWidget(action_box)

    def load_expense_filters(self):
        self.exp_group_combo.blockSignals(True)
        self.exp_group_combo.clear()
        self.exp_group_combo.addItem(ALL_GROUPS, 'ALL')
        self.exp_group_combo.addItem(NO_GROUP, None)
        for group in self.group_service.list_with_counts():
            self.exp_group_combo.addItem(group['name'], group['id'])
        self.exp_group_combo.blockSignals(False)

        self.exp_category_combo.blockSignals(True)
        self.exp_category_combo.clear()
        self.exp_category_combo.addItem("— all categories —", None)
        try:
            for category in self.category_service.get_active():
                self.exp_category_combo.addItem(category.name, category.id)
        except Exception as e:
            logger.error("Failed to load expense categories: %s", e)
        self.exp_category_combo.blockSignals(False)

        self.tag_group_combo.clear()
        for group in self.group_service.list_with_counts():
            self.tag_group_combo.addItem(group['name'], group['id'])

        self.load_expenses()

    def _filters(self):
        return {
            'group_choice': self.exp_group_combo.currentData(),
            'category_id': self.exp_category_combo.currentData(),
            'start': self.exp_from_date.date().toPython(),
            'end': self.exp_to_date.date().toPython(),
            'untagged_only': self.exp_untagged_only.isChecked(),
        }

    def load_expenses(self, *_):
        if self.exp_group_combo.count() == 0:
            return

        f = self._filters()
        try:
            if f['group_choice'] == 'ALL':
                rows, _total = self.expense_service.get_filtered(
                    start_date=f['start'], end_date=f['end'],
                    category_id=f['category_id'], is_personal=False, limit=500,
                )
            else:
                rows = self.expense_service.get_expenses_by_group(
                    f['group_choice'], start_date=f['start'], end_date=f['end'], limit=500
                )
                if f['category_id'] is not None:
                    rows = [r for r in rows if r.category_id == f['category_id']]
                if f['untagged_only'] and f['group_choice'] is not None:
                    rows = [r for r in rows if r.product_group_id is None]
        except Exception as e:
            logger.error("Failed to load expenses: %s", e)
            rows = []

        groups = {g['id']: g['name'] for g in self.group_service.list_with_counts()}
        self.expenses_table.setRowCount(0)
        total = 0.0
        for exp in rows:
            row = self.expenses_table.rowCount()
            self.expenses_table.insertRow(row)
            self.expenses_table.setItem(row, 0, QTableWidgetItem(str(exp.date)))
            self.expenses_table.setItem(
                row, 1, QTableWidgetItem(exp.category.name if exp.category else '—')
            )
            self.expenses_table.setItem(row, 2, QTableWidgetItem(exp.notes or ''))
            amount_item = QTableWidgetItem(f"{exp.amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.expenses_table.setItem(row, 3, amount_item)
            group_item = QTableWidgetItem(groups.get(exp.product_group_id, '—'))
            if exp.product_group_id is None:
                group_item.setForeground(QColor("#999999"))
            self.expenses_table.setItem(row, 4, group_item)
            total += exp.amount

        self.exp_total_label.setText(
            f"{len(rows)} expense(s) · Total ETB {total:,.2f}"
        )

    def apply_tag(self):
        group_id = self.tag_group_combo.currentData()
        if group_id is None:
            QMessageBox.warning(self, "No group", "Create a product group first.")
            return
        f = self._filters()
        # A specific group row also means untagged-only is off: we are moving
        # expenses into the chosen group regardless of their current tag.
        only_untagged = f['untagged_only'] and f['group_choice'] == 'ALL'
        changed = self.expense_service.assign_group_to_expenses(
            group_id=group_id,
            category_id=f['category_id'],
            date_from=f['start'],
            date_to=f['end'],
            only_untagged=only_untagged,
            is_personal=False,
        )
        QMessageBox.information(self, "Tagged", f"{changed} expense(s) tagged.")
        self.load_expenses()

    def clear_tag(self):
        f = self._filters()
        if QMessageBox.question(
            self, "Confirm",
            "Remove the product-group tag from the expenses matching the filters?",
        ) != QMessageBox.Yes:
            return
        changed = self.expense_service.assign_group_to_expenses(
            group_id=None,
            category_id=f['category_id'],
            date_from=f['start'],
            date_to=f['end'],
            only_untagged=False,
            is_personal=False,
        )
        QMessageBox.information(self, "Cleared", f"{changed} expense(s) untagged.")
        self.load_expenses()
