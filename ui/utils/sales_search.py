#!/usr/bin/env python3
"""Pure, UI-free search index for the All Sales Overview dialog.

Holds one snapshot of every sale (the plain dicts produced by
``NewSaleService.get_all_sales_rows``) and filters it in memory, so typing in
the search box never runs a database query.

The matching rules live in ``ui.utils.search_index``; this module only
declares which sale fields are searchable and how a date filter narrows the
candidate rows.
"""

from ui.utils.search_index import FuzzyFieldIndex

__all__ = ["SalesSearchIndex"]

# Row keys whose text takes part in the search, in table order.
_FIELD_KEYS = (
    "customer_name",
    "delivery_name",
    "delivery_phone",
    "delivery_place",
    "delivery_plate",
)


class SalesSearchIndex(FuzzyFieldIndex):
    """Filter a fixed list of sale rows by query text and optional date.

    Substring matching is case-insensitive and mirrors the per-field ILIKE the
    dialog used to send to SQLite (sale ID, customer, product names, delivery
    fields). When nothing matches, a typo-tolerant fallback runs entirely in
    memory.
    """

    def _field_texts(self, row):
        fields = [row.get(key) for key in _FIELD_KEYS]
        fields.extend(row.get("products") or [])
        return fields

    def exact_indices(self, query, indices):
        """A query made of digits also matches a sale ID exactly."""
        is_digits = query.isdigit()
        return [
            i for i in indices
            if (is_digits and str(self.row(i).get("id")) == query)
            or any(query in field for field in self.fields(i))
        ]

    def filter(self, query, filter_date=None):
        """Return ``(rows, fuzzy_used)`` for a query and optional date.

        ``filter_date`` is a Gregorian ``date``; rows it excludes are dropped
        before matching, exactly like the old SQL ``between`` date filter.
        """
        if filter_date is None:
            return super().filter(query)

        indices = [
            i for i, row in enumerate(self._rows)
            if self._matches_date(row, filter_date)
        ]
        return super().filter(query, indices)

    @staticmethod
    def _matches_date(row, filter_date):
        created = row.get("created_at")
        if created is None:
            return False
        value = created.date() if hasattr(created, "date") else created
        return value == filter_date
