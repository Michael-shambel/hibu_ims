# services/unusual_sales_alert_service.py
import statistics
import time
from datetime import date, timedelta
from typing import Dict, Optional, Set
from services.base_service import get_session
from models.product_batch import ProductBatch
from models.new_sale_item import ProfessionalSaleItem
from models.new_sales import ProfessionalSale
from sqlalchemy import func
import threading
import logging

logger = logging.getLogger(__name__)

class UnusualSalesAlertService:
    _instance = None
    _cache: Dict[int, Dict] = {}
    _lock = threading.Lock()
    _cache_ttl_seconds = 3600 * 6          # refresh every 6 hours
    _lookback_days = 30
    _min_historical_days = 15               # at least 15 days of data to compute stats
    _alerted_today: Set[tuple] = set()     # (product_id, today_date) to avoid repeat alerts
    _cooldown_reset_time = None            # time when the cooldown set was last cleared

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def refresh_cache(cls, lookback_days: int = None):
        if lookback_days is None:
            lookback_days = cls._lookback_days
        cutoff = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            rows = session.query(
                ProductBatch.product_id,
                func.date(ProfessionalSale.created_at).label('sale_date'),
                func.sum(ProfessionalSaleItem.quantity).label('daily_qty')
            ).join(
                ProfessionalSaleItem, ProfessionalSaleItem.batch_id == ProductBatch.id
            ).join(
                ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
            ).filter(
                ProfessionalSale.created_at >= cutoff,
                ProfessionalSale.is_deleted == False,
                ProfessionalSaleItem.is_deleted == False,
                ProductBatch.is_deleted == False
            ).group_by(
                ProductBatch.product_id, func.date(ProfessionalSale.created_at)
            ).all()

        product_history = {}
        for product_id, sale_date, qty in rows:
            product_history.setdefault(product_id, []).append(float(qty))

        new_cache = {}
        for product_id, quantities in product_history.items():
            if len(quantities) >= cls._min_historical_days:
                avg = statistics.mean(quantities)
                std = statistics.stdev(quantities) if len(quantities) > 1 else 0.0
                new_cache[product_id] = {
                    'avg': avg,
                    'std': std,
                    'last_updated': time.time()
                }

        with cls._lock:
            cls._cache = new_cache
            # Also clear the cooldown set when cache is refreshed (optional)
            cls._alerted_today.clear()
            cls._cooldown_reset_time = time.time()

        logger.info(f"UnusualSalesAlert cache refreshed: {len(new_cache)} products with sufficient history.")

    @classmethod
    def get_stats(cls, product_id: int) -> Optional[Dict]:
        """Return {'avg': float, 'std': float} for product, or None if not enough data."""
        with cls._lock:
            entry = cls._cache.get(product_id)
            if entry and time.time() - entry['last_updated'] < cls._cache_ttl_seconds:
                return entry
        # Cache expired or missing – refresh and try again
        cls.refresh_cache()
        with cls._lock:
            return cls._cache.get(product_id)

    @classmethod
    def get_daily_threshold(cls, product_id: int) -> Optional[float]:
        stats = cls.get_stats(product_id)
        if not stats:
            return None
        avg = stats['avg']
        std = stats['std']
        threshold = max(avg * 4, avg + 3 * std)
        return max(threshold, 5.0)

    @classmethod
    def should_alert(cls, product_id: int, proposed_total: float) -> bool:
        threshold = cls.get_daily_threshold(product_id)
        if threshold is None:
            return False
        if proposed_total <= threshold:
            return False

        today = date.today()
        key = (product_id, today)
        with cls._lock:
            if key in cls._alerted_today:
                return False
            cls._alerted_today.add(key)
        return True

    @classmethod
    def reset_cooldown(cls):
        """Manually reset the cooldown set (useful for testing or manual override)."""
        with cls._lock:
            cls._alerted_today.clear()
            logger.info("UnusualSalesAlert cooldown set cleared.")