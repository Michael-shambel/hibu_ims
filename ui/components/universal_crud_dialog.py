#!/usr/bin/env python3
"""
Universal CRUD Dialog - Replaces Customer, Supplier, Category, Salesperson dialogs
FIXED VERSION with proper data loading
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QFormLayout, QHeaderView, 
    QMessageBox, QComboBox, QAbstractItemView, QDoubleSpinBox, QCheckBox
)
from PySide6.QtCore import Qt
import re

class UniversalCRUDDialog(QDialog):
    """
    Universal dialog that handles ALL simple CRUD operations
    Replaces: CustomerDialog, SupplierDialog, CategoryDialog, SalespersonDialog
    """
    
    # CONFIGURATION FOR ALL ENTITY TYPES
    CONFIGS = {
        'customer': {
            'title': 'Manage Customers',
            'service_class': None,  # Will be injected
            'columns': ['ID', 'Name', 'TIN', 'Phone', 'Email', 'State'],
            'id_column': 0,
            'fields': [
                {'name': 'name', 'label': 'Customer Name*', 'type': 'text', 'required': True},
                {'name': 'tin_num', 'label': 'TIN Number*', 'type': 'text', 'required': True},
                {'name': 'phone', 'label': 'Phone Number*', 'type': 'text', 'required': True, 'validation': 'phone'},
                {'name': 'email', 'label': 'Email', 'type': 'text'},
                {'name': 'state', 'label': 'State*', 'type': 'combo', 'required': True, 
                 'options': [
                    "Addis Ababa", "Afar Region", "Amhara Region", "Benishangul-Gumuz Region",
                    "Dire Dawa", "Gambela Region", "Harari Region", "Oromia Region", 
                    "Sidama Region", "Somali Region", "SNNPR", "Tigray Region", "South West Ethiopia"
                 ]},
                {'name': 'sub_city', 'label': 'Sub-City', 'type': 'text'},
                {'name': 'wereda', 'label': 'Wereda', 'type': 'text'},
                {'name': 'kebele', 'label': 'Kebele', 'type': 'text'}
            ]
        },
        'supplier': {
            'title': 'Manage Suppliers',
            'service_class': None,  # Will be injected
            'columns': ['ID', 'Name', 'Phone', 'Additional Chat IDs'],
            'id_column': 0,
            'fields': [
                {'name': 'supplier_name', 'label': 'Supplier Name*', 'type': 'text', 'required': True},
                # {'name': 'contact_name', 'label': 'Contact Name', 'type': 'text'},
                {'name': 'contact_phone', 'label': 'Contact Phone', 'type': 'text'},
                {'name': 'additional_chat_ids', 'label': 'Additional Chat IDs (comma sep.)', 'type': 'text'},
                # {'name': 'email', 'label': 'Email', 'type': 'text'},
                # {'name': 'address', 'label': 'Address', 'type': 'textarea'}
            ]
        },
        'category': {
            'title': 'Manage Categories', 
            'service_class': None,  # Will be injected
            'columns': ['ID', 'Name', 'Description'],
            'id_column': 0,
            'fields': [
                {'name': 'name', 'label': 'Category Name*', 'type': 'text', 'required': True},
                {'name': 'description', 'label': 'Description', 'type': 'textarea'}
            ]
        },
        'salesperson': {
            'title': 'Manage Salespersons',
            'service_class': None,  # Will be injected
            'columns': ['ID', 'Name', 'Phone', 'Email', 'Bank', 'Account', 'Commission%', 'Active'],
            'id_column': 0,
            'fields': [
                {'name': 'full_name', 'label': 'Full Name*', 'type': 'text', 'required': True},
                {'name': 'phone', 'label': 'Phone*', 'type': 'text', 'required': True, 'validation': 'phone'},
                {'name': 'email', 'label': 'Email', 'type': 'text'},
                {'name': 'bank', 'label': 'Bank', 'type': 'combo', 
                 'options': [
                    "Abay Bank", "Addis Bank", "Ahadu Bank", "Amhara Bank", "Awash Bank",
                    "Bank of Abyssinia", "Berhan Bank", "Bunna Bank", "CBE", "Cooprative Bank of Oromia",
                    "Dashen Bank", "Enat Bank", "Global Bank", "Gadaa Bank", "Hibret Bank",
                    "Lion Bank", "Hijra Bank", "Oromia Bank", "Nib Bank", "Siinqee Bank",
                    "Shabelle Bank", "Tsehay Bank", "Tsedey Bank", "ZamZam Bank", "Wegagen Bank",
                    "Zemen Bank", "Other"
                 ]},
                {'name': 'account_number', 'label': 'Account Number', 'type': 'text'},
                {'name': 'commission_rate', 'label': 'Commission Rate', 'type': 'double', 'suffix': '%', 'max': 100.0},
                {'name': 'is_active', 'label': 'Active', 'type': 'checkbox', 'default': True}
            ]
        }
    }

    def __init__(self, entity_type, service_class, parent=None):
        super().__init__(parent)
        self.entity_type = entity_type
        self.config = self.CONFIGS[entity_type]
        self.config['service_class'] = service_class
        self.service = service_class()
        self.current_entity = None
        self.field_widgets = {}
        
        self.setWindowTitle(self.config['title'])
        self.setMinimumSize(600, 400)
        self.init_ui()
        self.load_data()

    def init_ui(self):
        """Dynamic UI generation based on config"""
        layout = QVBoxLayout()

        # FORM SECTION
        form_layout = QFormLayout()
        self.create_form_fields(form_layout)
        layout.addLayout(form_layout)

        # BUTTONS
        button_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.update_btn = QPushButton("Update") 
        self.delete_btn = QPushButton("Delete")
        self.clear_btn = QPushButton("Clear")

        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.update_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.clear_btn)
        layout.addLayout(button_layout)

        # TABLE
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.config['columns']))
        self.table.setHorizontalHeaderLabels(self.config['columns'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(QLabel(f"Existing {self.config['title'].split()[-1]}:"))
        layout.addWidget(self.table)

        self.setLayout(layout)

        # CONNECTIONS
        self.add_btn.clicked.connect(self.add_entity)
        self.clear_btn.clicked.connect(self.clear_form)
        self.update_btn.clicked.connect(self.update_entity)
        self.delete_btn.clicked.connect(self.delete_entity)
        self.table.itemSelectionChanged.connect(self.entity_selected)

        self.delete_btn.setEnabled(False)
        self.update_btn.setEnabled(False)

    def create_form_fields(self, form_layout):
        """Create form fields dynamically from config"""
        self.field_widgets = {}
        
        for field_config in self.config['fields']:
            widget = self.create_field_widget(field_config)
            self.field_widgets[field_config['name']] = widget
            form_layout.addRow(field_config['label'] + ":", widget)

    def create_field_widget(self, field_config):
        """Create appropriate widget for field type"""
        field_type = field_config.get('type', 'text')
        
        if field_type == 'text':
            widget = QLineEdit()
        elif field_type == 'textarea':
            widget = QTextEdit()
            widget.setFixedHeight(60)
        elif field_type == 'combo':
            widget = QComboBox()
            widget.addItems(field_config.get('options', []))
            widget.setCurrentIndex(-1)
        elif field_type == 'double':
            widget = QDoubleSpinBox()
            widget.setMaximum(field_config.get('max', 1000000.0))
            widget.setSuffix(field_config.get('suffix', ''))
        elif field_type == 'checkbox':
            widget = QCheckBox()
            widget.setChecked(field_config.get('default', True))
        else:
            widget = QLineEdit()
            
        return widget

    def get_form_data(self):
        """Extract data from form fields"""
        data = {}
        for field_name, widget in self.field_widgets.items():
            if isinstance(widget, QLineEdit):
                data[field_name] = widget.text().strip() or None
            elif isinstance(widget, QTextEdit):
                data[field_name] = widget.toPlainText().strip() or None
            elif isinstance(widget, QComboBox):
                data[field_name] = widget.currentText().strip() or None
            elif isinstance(widget, QDoubleSpinBox):
                data[field_name] = widget.value()
            elif isinstance(widget, QCheckBox):
                data[field_name] = widget.isChecked()
        return data

    def set_form_data(self, data):
        """Populate form fields with data."""
        for field_name, value in data.items():
            if field_name in self.field_widgets:
                widget = self.field_widgets[field_name]
                if isinstance(widget, QLineEdit):
                    # If the value is a list, join it with commas for display
                    if isinstance(value, list):
                        widget.setText(", ".join(str(v) for v in value))
                    else:
                        widget.setText(str(value) if value else "")
                elif isinstance(widget, QTextEdit):
                    widget.setPlainText(str(value) if value else "")
                elif isinstance(widget, QComboBox):
                    index = widget.findText(str(value)) if value else -1
                    widget.setCurrentIndex(index)
                elif isinstance(widget, QDoubleSpinBox) and value is not None:
                    widget.setValue(float(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))

    def validate_form(self):
        """Validate form data"""
        data = self.get_form_data()
        
        # Required field validation
        for field_config in self.config['fields']:
            if field_config.get('required') and not data.get(field_config['name']):
                QMessageBox.warning(self, "Validation Error", 
                                  f"{field_config['label']} is required.")
                return False
        
        # Phone validation
        if self.entity_type in ['customer', 'salesperson']:
            phone = data.get('phone', '')
            if phone:
                phone = phone.replace(" ", "")
                pattern_local = r"^0(9\d{8})$"
                pattern_international = r"^\+2519\d{8}$"
                
                if re.match(pattern_local, phone):
                    # Convert to international format
                    phone = "+251" + phone[1:]
                    self.field_widgets['phone'].setText(phone)
                elif not re.match(pattern_international, phone):
                    QMessageBox.warning(self, "Validation Error",
                                      "Invalid phone number.\nUse format +2519XXXXXXXX or 09XXXXXXXX.")
                    return False
        
        return True

    def load_data(self):
        """Load data into table - FIXED VERSION"""
        try:
            entities = self.service.get_all()
            self.table.setRowCount(len(entities))

            for row, entity in enumerate(entities):
                # Create items for each column based on config
                for col, column_name in enumerate(self.config['columns']):
                    attribute_name = self.get_entity_attribute(column_name)
                    value = self.get_entity_value(entity, attribute_name)
                    
                    # Format special values
                    if column_name == 'Active':
                        value = 'Yes' if value else 'No'
                    elif column_name == 'Commission%' and value is not None:
                        value = f"{value}%"
                    
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    self.table.setItem(row, col, item)
                
            # Hide ID column after populating
            if self.config.get('id_column') is not None:
                self.table.setColumnHidden(self.config['id_column'], True)
                
        except Exception as e:
            print(f"Error loading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data: {str(e)}")

    def get_entity_value(self, entity, attribute_name):
        """Safely get attribute value from entity"""
        try:
            return getattr(entity, attribute_name, None)
        except Exception:
            return None

    def get_entity_attribute(self, column_name):
        """Map column names to entity attributes - FIXED VERSION"""
        mapping = {
            'customer': {
                'ID': 'id',
                'Name': 'name',
                'TIN': 'tin_num', 
                'Phone': 'phone',
                'Email': 'email',
                'State': 'state',
                'Sub-City': 'sub_city',
                'Wereda': 'wereda',
                'Kebele': 'kebele'
            },
            'supplier': {
                'ID': 'id',
                'Name': 'supplier_name',
                'Contact': 'contact_name',
                'Phone': 'contact_phone', 
                'Email': 'email',
                'Address': 'address'
            },
            'category': {
                'ID': 'id',
                'Name': 'name',
                'Description': 'description'
            },
            'salesperson': {
                'ID': 'id',
                'Name': 'full_name',
                'Phone': 'phone',
                'Email': 'email',
                'Bank': 'bank',
                'Account': 'account_number',
                'Commission%': 'commission_rate', 
                'Active': 'is_active'
            }
        }
        
        # Return the mapped attribute or default to lowercase
        return mapping.get(self.entity_type, {}).get(column_name, column_name.lower())

    def entity_selected(self):
        """Handle entity selection from table - FIXED"""
        selected_row = self.table.currentRow()
        if selected_row < 0:
            return
        
        try:
            # Get ID from the hidden ID column
            id_column = self.config.get('id_column', 0)
            entity_id_item = self.table.item(selected_row, id_column)
            
            if not entity_id_item:
                return
                
            entity_id = int(entity_id_item.text())
            self.current_entity = self.service.get_by_id(entity_id)
            
            if self.current_entity:
                # Convert entity to dict for form population
                entity_data = {}
                for field_config in self.config['fields']:
                    field_name = field_config['name']
                    attribute_name = self.get_form_to_entity_mapping(field_name)
                    entity_data[field_name] = self.get_entity_value(self.current_entity, attribute_name)
                
                self.set_form_data(entity_data)
                self.delete_btn.setEnabled(True)
                self.update_btn.setEnabled(True)
                self.add_btn.setEnabled(False)
                
        except Exception as e:
            print(f"Error selecting entity: {e}")

    def get_form_to_entity_mapping(self, form_field_name):
        """Map form field names to entity attribute names"""
        mapping = {
            'customer': {
                'name': 'name',
                'tin_num': 'tin_num',
                'phone': 'phone',
                'email': 'email', 
                'state': 'state',
                'sub_city': 'sub_city',
                'wereda': 'wereda',
                'kebele': 'kebele'
            },
            'supplier': {
                'supplier_name': 'supplier_name',
                'contact_name': 'contact_name',
                'contact_phone': 'contact_phone',
                'email': 'email',
                'address': 'address'
            },
            'category': {
                'name': 'name',
                'description': 'description'
            },
            'salesperson': {
                'full_name': 'full_name',
                'phone': 'phone',
                'email': 'email',
                'bank': 'bank',
                'account_number': 'account_number',
                'commission_rate': 'commission_rate',
                'is_active': 'is_active'
            }
        }
        return mapping.get(self.entity_type, {}).get(form_field_name, form_field_name)

    def clear_form(self):
        """Clear the form"""
        self.current_entity = None
        for widget in self.field_widgets.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QTextEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(-1)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(0.0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(True)
        
        self.table.clearSelection()
        self.delete_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self.add_btn.setEnabled(True)

    def add_entity(self):
        """Add new entity"""
        if not self.validate_form():
            return
        
        data = self.get_form_data()
        try:
            self.service.create(data)
            QMessageBox.information(self, "Success", f"{self.config['title'].split()[-1][:-1]} created successfully!")
            self.clear_form()
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {str(e)}")

    def update_entity(self):
        """Update existing entity"""
        if not self.validate_form():
            return
        
        data = self.get_form_data()
        try:
            self.service.update(self.current_entity.id, data)
            QMessageBox.information(self, "Success", f"{self.config['title'].split()[-1][:-1]} updated successfully!")
            self.clear_form()
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update: {str(e)}")

    def delete_entity(self):
        """Delete entity"""
        if not self.current_entity:
            QMessageBox.warning(self, "Error", "No item selected for deletion.")
            return
        
        entity_name = getattr(self.current_entity, self.get_form_to_entity_mapping(self.config['fields'][0]['name']), "this item")
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete {entity_name}?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                if self.service.delete(self.current_entity.id):
                    QMessageBox.information(self, "Success", f"{self.config['title'].split()[-1][:-1]} deleted successfully!")
                    self.clear_form()
                    self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {str(e)}")