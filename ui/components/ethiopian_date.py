#!/usr/bin/env python3
from datetime import date, timedelta

from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpinBox
from PySide6.QtCore import QDate, Signal


class EthiopianDateConverter:
    @staticmethod
    def is_leap_year(ethiopian_year: int) -> bool:
        """Ethiopian leap years: year % 4 == 3 (Pagume then has 6 days)."""
        return ethiopian_year % 4 == 3

    @staticmethod
    def days_in_month(ethiopian_year: int, ethiopian_month: int) -> int:
        """Number of days in an Ethiopian month (5/6 for Pagume, 30 otherwise)."""
        if ethiopian_month == 13:
            return 6 if EthiopianDateConverter.is_leap_year(ethiopian_year) else 5
        return 30

    # ------------------------------------------------------------------
    # Ethiopian -> Gregorian
    # ------------------------------------------------------------------
    @staticmethod
    def to_gregorian(ethiopian_year: int, ethiopian_month: int, ethiopian_day: int) -> date:
        # Reject malformed input (0 or non-integer components).
        inputs = (ethiopian_year, ethiopian_month, ethiopian_day)
        if 0 in inputs or [type(data) for data in inputs].count(int) != 3:
            raise ValueError("Malformed input can't be converted.")

        # Ethiopian new year's day in September (11th, or 12th after a leap year).
        new_year_day = (ethiopian_year // 100) - (ethiopian_year // 400) - 4
        if (ethiopian_year - 1) % 4 == 3:
            new_year_day += 1

        # September (Ethiopian) sees a 7-year difference.
        gregorian_year = ethiopian_year + 7

        # Days in Gregorian months, indexed starting from September (index 1).
        # Index 0 is reserved for the leap-year switch below.
        gregorian_months = [0, 30, 31, 30, 31, 31, 28,
                            31, 30, 31, 30, 31, 31, 30]

        # If the next Gregorian year is a leap year, February has 29 days.
        next_year = gregorian_year + 1
        if (next_year % 4 == 0 and next_year % 100 != 0) or next_year % 400 == 0:
            gregorian_months[6] = 29

        # Days elapsed from the start of the Ethiopian year.
        until = ((ethiopian_month - 1) * 30) + ethiopian_day
        if until <= 37 and ethiopian_year <= 1575:  # Julian-era rule
            until += 28
            gregorian_months[0] = 31
        else:
            until += new_year_day - 1

        # Walk the Gregorian months to find month and day.
        m = 0
        gregorian_day = 0
        for i in range(len(gregorian_months)):
            if until <= gregorian_months[i]:
                m = i
                gregorian_day = until
                break
            until -= gregorian_months[i]

        # If m > 4 we have already entered the next Gregorian year.
        if m > 4:
            gregorian_year += 1

        # Gregorian months ordered according to the Ethiopian calendar.
        order = [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        gregorian_month = order[m]
        return date(gregorian_year, gregorian_month, gregorian_day)

    # ------------------------------------------------------------------
    # Gregorian -> Ethiopian
    # ------------------------------------------------------------------
    @staticmethod
    def to_ethiopian(gregorian_date: date) -> tuple:
        year, month, day = gregorian_date.year, gregorian_date.month, gregorian_date.day

        # Dates between 5 and 14 October 1582 do not exist in the Gregorian calendar.
        if month == 10 and day >= 5 and day <= 14 and year == 1582:
            raise ValueError("Invalid Date between 5-14 October 1582.")

        # Days in Gregorian months (January is index 1).
        gregorian_months = [0, 31, 28, 31, 30, 31, 30,
                            31, 31, 30, 31, 30, 31]
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
            gregorian_months[2] = 29

        # September sees an 8-year difference.
        ethiopian_year = year - 8

        # Days elapsed since the first of January.
        until = sum(gregorian_months[1:month]) + day

        # Tahsas (December) length, matching the reference implementation.
        tahissas = 26 if ethiopian_year % 4 == 0 else 25

        # Month lengths; index 1 is Tahsas, index 10 holds Pagume (5/6 days).
        ethiopian_months = [0, 0, 30, 30, 30, 30, 30, 30, 30, 30, 5, 30, 30, 30, 30]

        # Pagume has 6 days in an Ethiopian leap year, 5 otherwise.
        ethiopian_months[10] = 6 if EthiopianDateConverter.is_leap_year(ethiopian_year) else 5

        # Take the 1582 calendar change into account.
        if year < 1582:
            ethiopian_months[1] = 0
            ethiopian_months[2] = tahissas
        elif until <= 277 and year == 1582:
            ethiopian_months[1] = 0
            ethiopian_months[2] = tahissas
        else:
            # Ethiopian new year in the Gregorian calendar.
            new_year_day = (ethiopian_year // 100) - (ethiopian_year // 400) - 4
            if (ethiopian_year - 1) % 4 == 3:
                new_year_day += 1
            tahissas = new_year_day - 3
            ethiopian_months[1] = tahissas

        # Walk the months to find the Ethiopian month and day.
        m = 0
        ethiopian_day = 0
        for m in range(1, len(ethiopian_months)):
            if until <= ethiopian_months[m]:
                if m == 1 or ethiopian_months[m] == 0:
                    ethiopian_day = until + (30 - tahissas)
                else:
                    ethiopian_day = until
                break
            until -= ethiopian_months[m]

        # If m > 10 we have already entered the next Ethiopian year.
        if m > 10:
            ethiopian_year += 1

        # Ethiopian months ordered according to the Gregorian calendar.
        order = [0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 1, 2, 3, 4]
        ethiopian_month = order[m]

        if not (1 <= ethiopian_month <= 13 and 1 <= ethiopian_day <= 30):
            raise ValueError("Unsupported date.")

        return (ethiopian_year, ethiopian_month, ethiopian_day)

    @staticmethod
    def get_ethiopian_month_range(eth_year: int, eth_month: int) -> tuple:
        """Returns (start_gregorian_date, end_gregorian_date) for the given Ethiopian month."""
        start = EthiopianDateConverter.to_gregorian(eth_year, eth_month, 1)
        if eth_month == 13:
            next_year, next_month = eth_year + 1, 1
        else:
            next_year, next_month = eth_year, eth_month + 1
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
        self.year_spin.setRange(1900, 2100)

        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 13)

        self.day_spin = QSpinBox()
        self.day_spin.setRange(1, 30)

        layout.addWidget(self.day_spin)
        layout.addWidget(self.month_spin)
        layout.addWidget(self.year_spin)

        # Connect signals
        self.year_spin.valueChanged.connect(self._on_ethiopian_changed)
        self.month_spin.valueChanged.connect(self._on_ethiopian_changed)
        self.day_spin.valueChanged.connect(self._on_ethiopian_changed)

    def _sync_day_limit(self, eth_year: int, eth_month: int):
        """Limit the day spin-box to the selected month's real length (5-6 for Pagume)."""
        max_day = EthiopianDateConverter.days_in_month(eth_year, eth_month)
        if self.day_spin.maximum() != max_day:
            self.day_spin.blockSignals(True)
            self.day_spin.setMaximum(max_day)
            if self.day_spin.value() > max_day:
                self.day_spin.setValue(max_day)
            self.day_spin.blockSignals(False)

    def _on_ethiopian_changed(self):
        """When any spinbox changes, convert to Gregorian and emit."""
        try:
            eth_year = self.year_spin.value()
            eth_month = self.month_spin.value()
            self._sync_day_limit(eth_year, eth_month)
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
            self._sync_day_limit(eth_year, eth_month)
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