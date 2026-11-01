#!/usr/bin/env python3
"""Pure, UI-free helpers for filtering credit-customer rows by name.

Extracted from the Credit Sales Overview dialog so they can be unit-tested
without importing PySide6 or the database stack.
"""

import difflib

__all__ = ["filter_credit_customers", "token_score"]


def _name_text(cust) -> str:
    return str(cust.get("customer_name") or "").strip().lower()


def _subsequence_match(query: str, text: str) -> bool:
    """True when every character of query appears in text, in order
    (the same matching the old server-side fuzzy LIKE did)."""
    it = iter(text)
    return all(ch in it for ch in query)


def token_score(query_token: str, text_token: str, threshold: float = 0.6) -> float:
    """How well one query word matches one text word, from 0 to 1.

    Shared by the credit-customer filter and the sales-overview search index
    so the typo-tolerance rule is defined exactly once.
    """
    if query_token == text_token:
        return 1.0
    if query_token in text_token or text_token in query_token:
        shorter = min(len(query_token), len(text_token))
        longer = max(len(query_token), len(text_token))
        return 0.9 * (shorter / longer)
    if len(query_token) >= 3 and len(text_token) >= 3:
        ratio = difflib.SequenceMatcher(None, query_token, text_token).ratio()
        return ratio if ratio >= threshold else 0.0
    return 0.0


def _token_match(query: str, text: str) -> bool:
    """Typo-tolerant word matching: every query word must match some word."""
    text_tokens = text.split()
    if not text_tokens:
        return False
    for qt in query.split():
        if max((token_score(qt, tt) for tt in text_tokens), default=0.0) <= 0.0:
            return False
    return True


def filter_credit_customers(rows, query):
    """Filter credit-customer rows by name.

    Returns (rows, fuzzy_used). Substring match first; when it finds nothing,
    falls back to subsequence and typo-tolerant token matching, mirroring the
    fuzzy fallback the dialog used to run as a second database query.
    """
    q = (query or "").strip().lower()
    if not q:
        return list(rows), False

    exact = [r for r in rows if q in _name_text(r)]
    if exact:
        return exact, False

    fuzzy = [r for r in rows if _subsequence_match(q, _name_text(r))]
    if not fuzzy:
        fuzzy = [r for r in rows if _token_match(q, _name_text(r))]
    return fuzzy, True
