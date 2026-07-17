# services/daily_sales_cache_service.py
import json
import os
from datetime import date
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class DailySalesCacheService:
    
    _instance = None
    _cache = {}
    _cache_date = None
    _lock = Lock()
    _file_path = "daily_sales_cache.json"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_from_file()
        return cls._instance
    
    def _load_from_file(self):
        try:
            if os.path.exists(self._file_path):
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cache_date_str = data.get('date', '1900-01-01')
                    self._cache_date = date.fromisoformat(cache_date_str)
                    self._cache = data.get('cache', {})
                    
                    # If file date is not today, clear cache
                    if self._cache_date != date.today():
                        logger.info(f"Cache date ({self._cache_date}) != today ({date.today()}). Clearing cache.")
                        self._cache.clear()
                        self._cache_date = date.today()
                        self._save_to_file()
                    else:
                        logger.info(f"Loaded daily cache from file. Date: {self._cache_date}, Products: {len(self._cache)}")
            else:
                logger.info("No existing cache file found. Starting fresh.")
                self._cache = {}
                self._cache_date = date.today()
                self._save_to_file()
        except Exception as e:
            logger.error(f"Failed to load daily cache: {e}")
            self._cache = {}
            self._cache_date = date.today()
    
    def _save_to_file(self):
        try:
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': self._cache_date.isoformat(),
                    'cache': self._cache
                }, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved daily cache to file. Products: {len(self._cache)}")
        except Exception as e:
            logger.error(f"Failed to save daily cache: {e}")
    
    def get_today_sold(self, product_id: int) -> float:
        with self._lock:
            today = date.today()
            if self._cache_date != today:
                logger.info(f"Date changed from {self._cache_date} to {today}. Clearing cache.")
                self._cache.clear()
                self._cache_date = today
                self._save_to_file()
            return float(self._cache.get(str(product_id), 0.0))
    
    def add_to_daily_cache(self, product_id: int, quantity: float):
        with self._lock:
            today = date.today()
            if self._cache_date != today:
                logger.info(f"Date changed from {self._cache_date} to {today}. Clearing cache.")
                self._cache.clear()
                self._cache_date = today
            
            key = str(product_id)
            old_value = self._cache.get(key, 0.0)
            new_value = old_value + quantity
            self._cache[key] = new_value
            self._save_to_file()
            logger.debug(f"Updated cache: Product {product_id}: {old_value} → {new_value}")
    
    def refresh_from_db(self):
        from services.base_service import get_session
        from models.new_sale_item import ProfessionalSaleItem
        from models.new_sales import ProfessionalSale
        from models.product_batch import ProductBatch
        from sqlalchemy import func
        
        today = date.today()
        
        try:
            with get_session() as session:
                results = session.query(
                    ProductBatch.product_id,
                    func.sum(ProfessionalSaleItem.quantity * ProfessionalSaleItem.dozen).label('total_qty')
                ).join(
                    ProfessionalSaleItem, ProfessionalSaleItem.batch_id == ProductBatch.id
                ).join(
                    ProfessionalSale, ProfessionalSaleItem.sale_id == ProfessionalSale.id
                ).filter(
                    func.date(ProfessionalSale.created_at) == today,
                    ProfessionalSale.is_deleted == False,
                    ProfessionalSaleItem.is_deleted == False
                ).group_by(ProductBatch.product_id).all()
                
                with self._lock:
                    self._cache.clear()
                    for product_id, total_qty in results:
                        if total_qty:
                            self._cache[str(product_id)] = float(total_qty)
                    self._cache_date = today
                    self._save_to_file()
            
            logger.info(f"Cache refreshed from DB after deletion. Products: {len(self._cache)}")
        except Exception as e:
            logger.error(f"Failed to refresh cache from DB: {e}")
    
    def clear_cache(self):
        with self._lock:
            self._cache.clear()
            self._save_to_file()
            logger.info("Cache cleared manually")
    
    def get_all_today_sold(self) -> dict:
        with self._lock:
            return {
                'date': self._cache_date.isoformat(),
                'products': {int(k): v for k, v in self._cache.items()}
            }