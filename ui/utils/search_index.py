#!/usr/bin/env python3
"""Shared in-memory search engine for dialogs that hold a snapshot of rows.

The dialog reads its rows once, hands them to a subclass, and from then on
every keystroke filters that snapshot instead of the database:

* the exact stage is a case-insensitive substring test over the fields a
  subclass declares, mirroring the per-field ILIKE the dialogs used to send
  to SQLite;
* when nothing matches, a typo-tolerant fallback runs entirely in memory and
  the caller is told it was used (so the UI can show its 🔍 hint).

The fallback scores every query word against the snapshot's own token
vocabulary once per word (memoised) instead of once per row, which keeps it
at tens of milliseconds for several thousand rows rather than the ~0.5-0.9 s
a row-by-row scan costs.

Pure and UI-free, so the matching rules can be exercised without PySide6 or a
live database.
"""

from ui.utils.credit_search import token_score

__all__ = ["FuzzyFieldIndex"]


class FuzzyFieldIndex:
    """Index a fixed list of dict rows for substring + typo-tolerant search."""

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self._fields = []       # per row: tuple of lower-cased field strings
        self._token_sets = []   # per row: tuple of frozensets, one per field
        self._vocabulary = set()
        self._miss_cache = {}   # query word -> vocabulary tokens it cannot match

        for row in self._rows:
            fields = []
            for raw in self._field_texts(row):
                text = str(raw if raw is not None else "").strip().lower()
                if text:
                    fields.append(text)

            token_sets = tuple(frozenset(field.split()) for field in fields)
            self._fields.append(tuple(fields))
            self._token_sets.append(token_sets)
            for tokens in token_sets:
                self._vocabulary.update(tokens)

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------
    def _field_texts(self, row):
        """The searchable text of one row, as an iterable of strings.

        Each item is one search field: the exact stage matches a query inside
        any single field, and the fuzzy stage requires one field to match
        *every* query word (so words cannot be spread across different fields).
        """
        raise NotImplementedError

    def exact_indices(self, query, indices):
        """Row indices whose text contains ``query`` (already lower-cased)."""
        return [
            i for i in indices if any(query in field for field in self._fields[i])
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def __len__(self):
        return len(self._rows)

    def row(self, index):
        return self._rows[index]

    def fields(self, index):
        return self._fields[index]

    def rows_at(self, indices):
        return [self._rows[i] for i in indices]

    def filter(self, query, indices=None):
        """Return ``(rows, fuzzy_used)`` for a query.

        ``indices`` restricts the search to a subset of the snapshot (for
        example rows on a given date); the default searches every row.
        """
        if indices is None:
            indices = range(len(self._rows))
        q = (query or "").strip().lower()
        if not q:
            return self.rows_at(indices), False

        exact = self.exact_indices(q, indices)
        if exact:
            return self.rows_at(exact), False

        return self.rows_at(self.fuzzy_indices(q, indices)), True

    # ------------------------------------------------------------------
    # Typo-tolerant fallback
    # ------------------------------------------------------------------
    def _unmatched(self, word):
        """Vocabulary tokens that ``word`` cannot match, scored once per word."""
        bad = self._miss_cache.get(word)
        if bad is None:
            bad = frozenset(
                token for token in self._vocabulary if token_score(word, token) == 0.0
            )
            self._miss_cache[word] = bad
        return bad

    def fuzzy_indices(self, query, indices):
        """Row indices with a field whose words all match the query's words."""
        words = query.split()
        if not words:
            return []

        bad_sets = [self._unmatched(word) for word in words]
        return [i for i in indices if self._fuzzy_match(i, bad_sets)]

    def _fuzzy_match(self, index, bad_sets):
        for field_tokens in self._token_sets[index]:
            # field_tokens - bad  ==  this field's tokens that do match
            if all(field_tokens - bad for bad in bad_sets):
                return True
        return False
