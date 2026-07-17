#!/usr/bin/env python3
"""
Combined credit reporting for people who exist as both customers and suppliers.
"""

import logging
from typing import Dict, List

from services.new_sale_service import NewSaleService
from services.purchase_service import PurchaseService


logger = logging.getLogger(__name__)


class CombinedCreditService:
    """Build a read-only net credit view from existing customer/supplier ledgers."""

    def __init__(self):
        self.sale_service = NewSaleService()
        self.purchase_service = PurchaseService()

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join((name or "").casefold().split())

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
        if digits.startswith("00251") and len(digits) == 14:
            return "0" + digits[5:]
        if digits.startswith("251") and len(digits) == 12:
            return "0" + digits[3:]
        return digits

    def build_match_key(self, name: str, phone: str) -> str:
        normalized_name = self.normalize_name(name)
        if not normalized_name:
            return ""
        normalized_phone = self.normalize_phone(phone)
        if normalized_phone:
            return f"name-phone:{normalized_name}:{normalized_phone}"
        return f"name-only:{normalized_name}"

    def get_combined_credit_overview(self) -> Dict:
        try:
            sales_rows = self.sale_service.get_credit_sales_by_customer()
            purchase_rows = self.purchase_service.get_credit_purchases_by_supplier()
        except Exception as exc:
            logger.error(f"Error loading combined credit source data: {exc}", exc_info=True)
            return {"summary": self._summary([]), "rows": []}

        grouped: Dict[str, Dict] = {}

        for row in sales_rows:
            remaining = float(row.get("remaining") or 0.0)
            if remaining <= 0:
                continue

            phone = row.get("customer_phone", "")
            key = self.build_match_key(row.get("customer_name", ""), phone)
            if not key:
                continue

            entry = grouped.setdefault(key, self._empty_entry(row.get("customer_name", "")))
            entry["customer_names"].add(row.get("customer_name", ""))
            if phone:
                entry["phones"].add(phone)
            entry["customer_ids"].add(row.get("customer_id"))
            entry["sale_ids"].extend(row.get("sale_ids", []))
            entry["credit_sales_total"] += float(row.get("total_amount") or 0.0)
            entry["credit_sales_paid"] += float(row.get("paid_amount") or 0.0)
            entry["credit_sales_remaining"] += remaining

        for row in purchase_rows:
            remaining = float(row.get("remaining") or 0.0)
            if remaining <= 0:
                continue

            phone = row.get("supplier_phone", "")
            key = self.build_match_key(row.get("supplier_name", ""), phone)
            if not key:
                continue

            entry = grouped.setdefault(key, self._empty_entry(row.get("supplier_name", "")))
            entry["supplier_names"].add(row.get("supplier_name", ""))
            if phone:
                entry["phones"].add(phone)
            entry["supplier_ids"].add(row.get("supplier_id"))
            entry["purchase_ids"].extend(row.get("purchase_ids", []))
            entry["credit_purchases_total"] += float(row.get("total_amount") or 0.0)
            entry["credit_purchases_paid"] += float(row.get("paid_amount") or 0.0)
            entry["credit_purchases_remaining"] += remaining

        rows = []
        for entry in grouped.values():
            has_customer_credit = entry["credit_sales_remaining"] > 0
            has_supplier_credit = entry["credit_purchases_remaining"] > 0
            if not (has_customer_credit and has_supplier_credit):
                continue

            net_balance = entry["credit_sales_remaining"] - entry["credit_purchases_remaining"]
            if net_balance > 0.01:
                direction = "wede egna"
            elif net_balance < -0.01:
                direction = "Wede esu"
            else:
                direction = "Balanced"

            rows.append({
                "name": entry["name"],
                "phone": self._display_phone(entry["phones"]),
                "customer_names": sorted(name for name in entry["customer_names"] if name),
                "supplier_names": sorted(name for name in entry["supplier_names"] if name),
                "customer_ids": sorted(cid for cid in entry["customer_ids"] if cid is not None),
                "supplier_ids": sorted(sid for sid in entry["supplier_ids"] if sid is not None),
                "sale_ids": sorted(set(entry["sale_ids"])),
                "purchase_ids": sorted(set(entry["purchase_ids"])),
                "credit_sales_total": entry["credit_sales_total"],
                "credit_sales_paid": entry["credit_sales_paid"],
                "credit_sales_remaining": entry["credit_sales_remaining"],
                "credit_purchases_total": entry["credit_purchases_total"],
                "credit_purchases_paid": entry["credit_purchases_paid"],
                "credit_purchases_remaining": entry["credit_purchases_remaining"],
                "net_balance": net_balance,
                "abs_net_balance": abs(net_balance),
                "direction": direction,
            })

        rows.sort(key=lambda item: item["abs_net_balance"], reverse=True)
        summary = self._summary(rows)
        return {"summary": summary, "rows": rows}

    def get_combined_credit_summary(self) -> Dict:
        return self.get_combined_credit_overview()["summary"]

    @staticmethod
    def _empty_entry(name: str) -> Dict:
        return {
            "name": name or "N/A",
            "customer_names": set(),
            "supplier_names": set(),
            "phones": set(),
            "customer_ids": set(),
            "supplier_ids": set(),
            "sale_ids": [],
            "purchase_ids": [],
            "credit_sales_total": 0.0,
            "credit_sales_paid": 0.0,
            "credit_sales_remaining": 0.0,
            "credit_purchases_total": 0.0,
            "credit_purchases_paid": 0.0,
            "credit_purchases_remaining": 0.0,
        }

    @staticmethod
    def _display_phone(phones: set) -> str:
        if not phones:
            return ""
        return ", ".join(sorted(phones))

    @staticmethod
    def _summary(rows: List[Dict]) -> Dict:
        total_receivable = sum(row["credit_sales_remaining"] for row in rows)
        total_payable = sum(row["credit_purchases_remaining"] for row in rows)
        net_balance = total_receivable - total_payable

        if net_balance > 0.01:
            net_direction = "Net receivable"
        elif net_balance < -0.01:
            net_direction = "Net payable"
        else:
            net_direction = "Balanced"

        return {
            "matched_count": len(rows),
            "total_receivable": total_receivable,
            "total_payable": total_payable,
            "net_balance": net_balance,
            "abs_net_balance": abs(net_balance),
            "net_direction": net_direction,
        }
