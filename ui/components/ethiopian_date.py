from datetime import date
from ethiopian_date import EthiopianDateConverter as _EthiopianDateConverter
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpinBox
from PySide6.QtCore import QDate, Signal
from typing import Tuple


class EthiopianDateConverter:
    @staticmethod
    def to_gregorian(ethiopian_year: int, ethiopian_month: int, ethiopian_day: int) -> date:
        """Convert Ethiopian date to Gregorian date."""
        converter = _EthiopianDateConverter()
        gregorian = converter.to_gregorian(ethiopian_year, ethiopian_month, ethiopian_day)
        return date(gregorian.year, gregorian.month, gregorian.day)

    @staticmethod
    def to_ethiopian(gregorian_date: date) -> tuple:
        """Convert Gregorian date to (year, month, day) in Ethiopian calendar."""
        converter = _EthiopianDateConverter()
        ethiopian = converter.to_ethiopian(gregorian_date.year, gregorian_date.month, gregorian_date.day)
        return (ethiopian.year, ethiopian.month, ethiopian.day)
    
    @staticmethod
    def get_ethiopian_month_range(eth_year: int, eth_month: int) -> tuple[date, date]:
        """Returns (start_gregorian_date, end_gregorian_date) for the given Ethiopian month."""
        from datetime import timedelta
        start = EthiopianDateConverter.to_gregorian(eth_year, eth_month, 1)
        if eth_month == 13:
            next_year = eth_year + 1
            next_month = 1
        else:
            next_year = eth_year
            next_month = eth_month + 1
        end = EthiopianDateConverter.to_gregorian(next_year, next_month, 1) - timedelta(days=1)
        return start, end



class EthiopianDateEdit(QWidget):
    dateChanged = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gregorian_date = QDate.currentDate()
        self._setup_ui()
        self.setDate(self.gregorian_date)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.year_spin = QSpinBox()
        self.year_spin.setRange(1900, 2100)   # adjust range as needed
        # self.year_spin.setPrefix("ዓ.ም. ")      # Ethiopian year label (optional)

        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 13)
        # self.month_spin.setPrefix("ወር ")

        self.day_spin = QSpinBox()
        self.day_spin.setRange(1, 30)
        # self.day_spin.setPrefix("ቀን ")

      
        layout.addWidget(self.day_spin)
        layout.addWidget(self.month_spin)
        layout.addWidget(self.year_spin)
      

        # Connect signals
        self.year_spin.valueChanged.connect(self._on_ethiopian_changed)
        self.month_spin.valueChanged.connect(self._on_ethiopian_changed)
        self.day_spin.valueChanged.connect(self._on_ethiopian_changed)
    

    def _on_ethiopian_changed(self):
        """When any spinbox changes, convert to Gregorian and emit."""
        try:
            eth_year = self.year_spin.value()
            eth_month = self.month_spin.value()
            eth_day = self.day_spin.value()
            greg_date = EthiopianDateConverter.to_gregorian(eth_year, eth_month, eth_day)
            self.gregorian_date = QDate(greg_date.year, greg_date.month, greg_date.day)
            self.dateChanged.emit(self.gregorian_date)
        except Exception:
            # Invalid date – ignore (or you could show a warning)
            pass
    

    def setDate(self, gregorian_qdate: QDate):
        """Set the date from a Gregorian QDate, updating Ethiopian spinboxes."""
        self.gregorian_date = gregorian_qdate
        greg_pydate = gregorian_qdate.toPython()
        try:
            eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(greg_pydate)
            # Block signals to avoid recursion
            self.year_spin.blockSignals(True)
            self.month_spin.blockSignals(True)
            self.day_spin.blockSignals(True)
            self.day_spin.setValue(eth_day)
            self.month_spin.setValue(eth_month)
            self.year_spin.setValue(eth_year)
            
            
            self.year_spin.blockSignals(False)
            self.month_spin.blockSignals(False)
            self.day_spin.blockSignals(False)
        except Exception:
            # If conversion fails, leave unchanged (or set to a default)
            pass

    def date(self) -> QDate:
        """Return the stored Gregorian QDate."""
        return self.gregorian_date