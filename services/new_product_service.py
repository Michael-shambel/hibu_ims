#!/usr/bin/env python3
from typing import List, Optional, Dict, Tuple
import logging
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy import func
from sqlalchemy import or_, select
from models.new_product import ProfessionalProduct
from models.product_batch import ProductBatch
from models.batch_transaction import BatchTransaction, TransactionType
from services.base_service import BaseService, get_session
from models.purchase import Purchase
from services.purchase_service import PurchaseService
from services.untils import normalize_string
from sqlalchemy.orm import Session
from datetime import date, datetime
from models.purchase_payment_term import PaymentStatusEnum
from models.purchase_payment_transaction import PaymentMethodEnum
from models.batch_transaction import TransactionType


logger = logging.getLogger(__name__)

class NewProductService(BaseService[ProfessionalProduct]):

    def __init__(self):
        super().__init__(ProfessionalProduct)
        self.purchase_service = PurchaseService()
    
    def create(self, data):
        total_amount = sum(
            p['quantity'] * p['cost_price'] * p.get('dozen', 1)
            for p in data['products']
        )
        with get_session() as session:
            try:
                purchase_data = {
                    'supplier_id': data['supplier_id'],
                    'total_amount': total_amount,
                    'payment_status': data['payment_status'],
                    'payment_method': data.get('payment_method'),
                    'bank_account_id': data.get('bank_account_id'),
                    'payment_date': data.get('payment_date', date.today()),
                    'user_id': data.get('user_id'),
                    'created_at': data.get('created_at', datetime.now()),
                    'last_modified': data.get('last_modified', datetime.now()),
                }
                from_shipment = data.get('from_shipment', False)

                # Pass the flag to purchase creation
                purchase = self.purchase_service.create_purchase_with_session(
                    session, purchase_data, from_shipment=from_shipment
                )

                for prod_data in data['products']:
                    product = self._get_or_create_product(
                        session=session,
                        name=prod_data['name'],
                        unit=prod_data['unit'],
                        selling_price=prod_data['selling_price'],
                        supplier_id=data['supplier_id'],
                        dozen=prod_data.get('dozen', 1),
                        user_id=data.get('user_id'),
                        created_at=data.get('created_at', datetime.now()),
                        last_modified=data.get('last_modified', datetime.now()),
                        supplier_sku=prod_data.get('supplier_sku')
                    )

                    if not product:
                        raise Exception(f"Failed to create/find product: {prod_data['name']}")

                    batch = ProductBatch(
                        product_id=product.id,
                        purchase_id=purchase.id,
                        quantity=prod_data['quantity'],
                        available_quantity=prod_data['quantity'],
                        cost_price=prod_data['cost_price'],
                        created_at=data.get('created_at', datetime.now()),
                        last_modified=data.get('last_modified', datetime.now())
                    )
                    session.add(batch)
                    session.flush()

                    transaction = BatchTransaction(
                        batch_id=batch.id,
                        quantity=prod_data['quantity'],
                        transaction_type=TransactionType.RECEIVED,
                        reference_number=data.get('invoice_number'),
                        user_id=data.get('user_id'),
                        notes=f"Purchase #{purchase.id}",
                        created_at=data.get('created_at', datetime.now()),
                        last_modified=data.get('last_modified', datetime.now())
                    )
                    session.add(transaction)

                    product.update_totals()

                session.commit()
                logger.info(f"Purchase #{purchase.id} created with {len(data['products'])} products")
                return purchase

            except ValueError as e:
                session.rollback()
                logger.warning(f"ValueError in create: {e}")
                raise   # re-raise so the dialog can catch it
            except Exception as e:
                session.rollback()
                logger.exception("Failed to create product with batch and transaction")
                return None
    

    def _get_or_create_product(
        self,
        session: Session,
        name: str,
        unit: str,
        selling_price: float,
        supplier_id: int,
        dozen: float = 1.0,
        user_id: int = None,
        created_at: date = None,
        last_modified: date = None,
        supplier_sku: str = None
    ) -> ProfessionalProduct:
        norm_name = normalize_string(name)
        norm_unit = normalize_string(unit)
        product = session.query(ProfessionalProduct).filter(
            ProfessionalProduct.normalized_name == norm_name,
            ProfessionalProduct.normalized_unit == norm_unit
        ).first()
        if product:
            if product.is_deleted:
                product.is_deleted = False
            if product.selling_price != selling_price:
                product.selling_price = selling_price
            if product.dozen != dozen:
                product.dozen = dozen
            if product.user_id != user_id:
                product.user_id = user_id
            if product.supplier_sku != supplier_sku:
                product.supplier_sku = supplier_sku
            return product
        
        product = ProfessionalProduct(
            name=name.strip(),
            normalized_name=norm_name,
            unit=unit.strip(),
            normalized_unit=norm_unit,
            selling_price=selling_price,
            dozen=dozen,
            user_id=user_id,
            supplier_sku=supplier_sku,
            created_at=created_at if created_at else datetime.now(),
            last_modified=last_modified if last_modified else datetime.now()
        )
        session.add(product)
        session.flush()
        return product
    
    def add_stock_in(self, product_name, unit, selling_price, dozen, batch_data, user_id=None):
        """Add stock to a product without a purchase (e.g., opening balance)"""
        with get_session() as session:
            try:
                # Get or create product
                product = self._get_or_create_product(
                    session=session,
                    name=product_name,
                    unit=unit,
                    selling_price=selling_price,
                    supplier_id=None,  # no supplier for stock in
                    dozen=dozen,
                    user_id=user_id
                )
                if not product:
                    raise Exception("Failed to create/find product")
                
                # Create batch with purchase_id = NULL
                batch = ProductBatch(
                    product_id=product.id,
                    purchase_id=None,  # important!
                    quantity=batch_data['quantity'],
                    available_quantity=batch_data['quantity'],
                    cost_price=batch_data.get('cost_price')
                )
                session.add(batch)
                session.flush()
                
                # Create transaction with new type STOCK_IN
                transaction = BatchTransaction(
                    batch_id=batch.id,
                    quantity=batch_data['quantity'],
                    transaction_type=TransactionType.STOCK_IN,
                    reference_number=batch_data.get('reference_number'),
                    user_id=user_id,
                    notes=batch_data.get('notes', 'Stock in (no purchase)')
                )
                session.add(transaction)
                
                # Update product totals
                product.update_totals()
                
                session.commit()
                logger.info(f"Stock in for product '{product.name}': {batch_data['quantity']} units")
                return True
            
            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to add stock in: {e}")
                return False
    
    def search_products(self, query: str, limit: int = 10, include_supplier_sku: bool = False) -> List[dict]:
        """
        Search products by name, and optionally by supplier_sku.
        Returns list of dicts with id, name, unit, and supplier_sku (if requested).
        """
        if not query or not query.strip():
            return []

        norm_query = normalize_string(query)

        with get_session() as session:
            # Build filter conditions
            conditions = [ProfessionalProduct.normalized_name.ilike(f"%{norm_query}%")]
            if include_supplier_sku:
                conditions.append(ProfessionalProduct.supplier_sku.ilike(f"%{query}%"))
            
            products = session.query(ProfessionalProduct).filter(
                ProfessionalProduct.is_deleted == False,
                or_(*conditions)
            ).limit(limit).all()

            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "unit": p.unit,
                    "supplier_sku": p.supplier_sku,
                    "dozen": p.dozen,
                    "selling_price": p.selling_price,
                }
                for p in products
            ]                            

    def get_product_by_name(self, name: str, unit: str, session) -> Optional[ProfessionalProduct]:
        try:
            return (
                session.query(ProfessionalProduct)
                .filter(
                    ProfessionalProduct.name == name,
                    # ProfessionalProduct.category_id == category_id,
                    ProfessionalProduct.unit == unit,
                    ProfessionalProduct.is_deleted == False
                )
                .first()
            )
        except Exception as e:
            logger.error(f"Error retrieving product by name: {e}")
            return None
    
    def get_paginated(self, offset=0, limit=20, search=None):
        with get_session() as session:
            try:
                batch_alias = aliased(ProductBatch)

                query = (
                    session.query(
                        ProfessionalProduct.id.label("product_id"),
                        ProfessionalProduct.name.label("product_name"),
                        ProfessionalProduct.available_quantity.label("available_stock"),
                        ProfessionalProduct.total_quantity.label("total_quantity"),
                        ProfessionalProduct.selling_price.label("price"),
                        ProfessionalProduct.unit.label("unit"),
                        ProfessionalProduct.dozen.label("dozen"),
                        func.count(batch_alias.id).label("total_batches")
                    )
                    .outerjoin(batch_alias, (batch_alias.product_id == ProfessionalProduct.id) & (batch_alias.is_deleted == False))
                    .filter(ProfessionalProduct.is_deleted == False)
                    .group_by(ProfessionalProduct.id)
                    .order_by(ProfessionalProduct.available_quantity.desc())
                )

                if search and search.strip():
                    search_term = f"%{search}%"
                    query = query.filter(
                        or_(
                            ProfessionalProduct.name.ilike(search_term),
                            ProfessionalProduct.unit.ilike(search_term)
                        )
                    )
                query = query.offset(offset).limit(limit)
                results = query.all()

                return [
                    {
                        "id": r.product_id,
                        "name": r.product_name,
                        "stock": r.available_stock,
                        "total_quantity": r.total_quantity,
                        "price": r.price,
                        "dozen": r.dozen,
                        "unit": r.unit,
                        "total_batches": r.total_batches
                    }
                    for r in results
                ]
            except Exception as e:
                logger.exception(f"Error retrieving paginated product report: {e}")
                return []
    

    def get_batches_with_product(self, product_id):
        with get_session() as session:
            try:
                query = session.query(ProductBatch).options(
                    joinedload(ProductBatch.purchase).joinedload(Purchase.supplier)
                ).filter(
                    ProductBatch.product_id==product_id,
                    ProductBatch.is_deleted == False,
                ).all()
                return query
            except Exception as e:
                logger.exception(f"Error Getting products with batches: {e}")
                return None
    
    def delete_cascading(self, product_id: int) -> bool:
        from services.product_batch_service import ProductBatchService
        batch_service = ProductBatchService()

        with get_session() as session:
            try:
                product = session.query(ProfessionalProduct).filter(
                    ProfessionalProduct.id == product_id,
                    ProfessionalProduct.is_deleted == False
                ).first()
                if not product:
                    logger.warning(f"Product {product_id} not found or already deleted")
                    return False

                # Get all non-deleted batches for this product
                batches = session.query(ProductBatch).filter(
                    ProductBatch.product_id == product_id,
                    ProductBatch.is_deleted == False
                ).all()

                if not batches:
                    product.is_deleted = True
                    session.commit()
                    return True

                # Delete each batch using the shared session
                for batch in batches:
                    if not batch_service.delete_batch_cascade(batch.id, session=session):
                        raise Exception(f"Failed to delete batch {batch.id}")

                # Mark product as deleted (already done if last batch triggered deletion, but safe)
                product.is_deleted = True

                session.commit()
                logger.info(f"Product {product_id} and all associated records deleted")
                return True

            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to delete product {product_id}: {e}")
                return False
    

    def get_available_products_for_sale(self, search_text=""):
        """Get all available batches for sales - returns ProductBatch objects get_available_batch"""
        with get_session() as session:
            try:
                # Query batches with product relationship loaded
                query = (
                    session.query(ProductBatch)
                    .join(ProfessionalProduct, ProductBatch.product)
                    .options(
                        joinedload(ProductBatch.product)
                    )
                    .filter(
                        ProductBatch.is_deleted == False,
                        ProductBatch.available_quantity > 0,
                        ProfessionalProduct.is_deleted == False
                    )
                    .order_by(ProfessionalProduct.name, ProductBatch.expiry_date)
                )
                
                if search_text:
                    search_term = f"%{search_text}%"
                    query = query.filter(
                        or_(
                            ProfessionalProduct.name.ilike(search_term),
                            ProfessionalProduct.description.ilike(search_term),
                            ProductBatch.batch_number.ilike(search_term)
                        )
                    )
                
                return query.all()
                
            except Exception as e:
                logger.exception(f"Error getting batches for sale: {e}")
                return []

    
    def get_batch_by_id(self, batch_id):
        """Get batch by ID with product relationship loaded"""
        with get_session() as session:
            try:
                return (
                    session.query(ProductBatch)
                    .options(joinedload(ProductBatch.product))  # Eager load the product
                    .filter(
                        ProductBatch.id == batch_id,
                        ProductBatch.is_deleted == False
                    )
                    .first()
                )
            except Exception as e:
                logger.error(f"Error getting batch by ID: {e}")
                return None
    
    def update_product_price(self, product_id: int, new_price: float) -> bool:
        """
        """
        with get_session() as session:
            try:
                product = session.query(ProfessionalProduct).filter(
                    ProfessionalProduct.id == product_id,
                    ProfessionalProduct.is_deleted == False
                ).first()

                if not product:
                    logger.warning(f"Product with ID {product_id} not found")
                    return False
                
                old_price = product.selling_price
                product.selling_price = new_price
                session.commit()

                logger.info(f"Updated price for product '{product.name}' from {old_price} to {new_price}")
                return True
            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to update price for product {product_id}: {e}")
                return False
    
    def get_product_by_id(self, product_id: int) -> Optional[ProfessionalProduct]:
        with get_session() as session:
            try:
                return (
                    session.query(ProfessionalProduct)
                    .options(joinedload(ProfessionalProduct.batches))
                    .filter(
                        ProfessionalProduct.id == product_id,
                        ProfessionalProduct.is_deleted == False
                    )
                    .first()
                )
            except Exception as e:
                logger.error(f"Error getting product by ID: {e}")
                return None
    
    def get_available_products(self, search_text: str = "") -> List[ProfessionalProduct]:
        with get_session() as session:
            query = session.query(ProfessionalProduct).filter(
                ProfessionalProduct.is_deleted == False,
                ProfessionalProduct.available_quantity > 0
            )

            if search_text and search_text.strip():
                norm_query = normalize_string(search_text)
                query = query.filter(
                    ProfessionalProduct.normalized_name.ilike(f"%{norm_query}%")
                )
            
            return query.all()
    
    def get_available_batch(self, product_id: int, required_qty: int = 1) -> Optional[ProductBatch]:
        with get_session() as session:
            batch = session.query(ProductBatch).filter(
                ProductBatch.product_id == product_id,
                ProductBatch.available_quantity >= required_qty,
                ProductBatch.is_deleted == False
            ).order_by(ProductBatch.created_at).first()
            return batch
    

    def get_batch_cost_totals(self, product_ids: List[int]) -> Dict[int, float]:
        """
        Returns a dict mapping product_id to total cost value
        (sum of available_quantity * cost_price over all non-deleted batches).
        """
        with get_session() as session:
            try:
                results = (
                    session.query(
                        ProductBatch.product_id,
                        func.sum(ProductBatch.available_quantity * ProductBatch.cost_price).label('total_cost')
                    )
                    .filter(
                        ProductBatch.product_id.in_(product_ids),
                        ProductBatch.is_deleted == False
                    )
                    .group_by(ProductBatch.product_id)
                    .all()
                )
                return {r.product_id: r.total_cost or 0.0 for r in results}
            except Exception as e:
                logger.exception(f"Error getting batch cost totals: {e}")
                return {}
    
    def allocate_batches(self, product_id: int, required_qty: int,
                        pending_allocations: dict = None) -> List[Tuple[ProductBatch, int]]:
        if pending_allocations is None:
            pending_allocations = {}

        with get_session() as session:
            batches = session.query(ProductBatch).filter(
                ProductBatch.product_id == product_id,
                ProductBatch.available_quantity > 0,
                ProductBatch.is_deleted == False
            ).order_by(ProductBatch.created_at).all()

            allocations = []
            remaining = required_qty
            for batch in batches:
                if remaining <= 0:
                    break
                # Real available = DB available minus already allocated in this sale
                already_allocated = pending_allocations.get(batch.id, 0)
                effective_available = max(0, batch.available_quantity - already_allocated)
                if effective_available <= 0:
                    continue
                take = min(effective_available, remaining)
                allocations.append((batch, take))
                remaining -= take

            if remaining > 0:
                # Not enough stock (including pending allocations)
                return []

            return allocations
    
    def update(self, id: int, data: dict) -> Optional[ProfessionalProduct]:
        with get_session() as session:
            try:
                product = session.query(ProfessionalProduct).filter(
                    ProfessionalProduct.id == id,
                    ProfessionalProduct.is_deleted == False
                ).first()
                if not product:
                    return None

                old_dozen = product.dozen

                if 'name' in data:
                    data['normalized_name'] = normalize_string(data['name'])
                if 'unit' in data:
                    data['normalized_unit'] = normalize_string(data['unit'])
                # Apply updates
                for key, value in data.items():
                    setattr(product, key, value)

                # If dozen changed, recalc product totals and all related purchases
                if 'dozen' in data and data['dozen'] != old_dozen:
                    # 1. Update product totals (total_quantity, available_quantity)
                    product.update_totals()

                    # 2. Find all purchases that have batches of this product
                    from services.purchase_service import PurchaseService
                    purchase_service = PurchaseService()

                    # Get distinct purchase IDs from non‑deleted batches of this product
                    purchase_ids = session.query(ProductBatch.purchase_id).filter(
                        ProductBatch.product_id == id,
                        ProductBatch.is_deleted == False,
                        ProductBatch.purchase_id.isnot(None)
                    ).distinct().all()
                    purchase_ids = [pid for (pid,) in purchase_ids]

                    # Recalc each purchase (this updates purchase.total_amount and term.total_amount)
                    for pid in purchase_ids:
                        purchase_service.recalc_purchase_total(pid, session)

                session.commit()
                return product
            except Exception as e:
                session.rollback()
                logger.error(f"Error updating {self.model.__name__} {id}: {e}")
                return None
    
    def get_total_inventory_value(self) -> float:
        """Sum of (available_quantity × dozen × cost_price) for all non‑deleted batches."""
        from models.product_batch import ProductBatch
        from models.new_product import ProfessionalProduct
        from sqlalchemy import func
        with get_session() as session:
            result = session.query(
                func.sum(ProductBatch.available_quantity * ProfessionalProduct.dozen * ProductBatch.cost_price)
            ).join(
                ProfessionalProduct, ProductBatch.product_id == ProfessionalProduct.id
            ).filter(
                ProductBatch.is_deleted == False,
                ProductBatch.cost_price.isnot(None),
                ProfessionalProduct.is_deleted == False
            ).scalar()
            return float(result) if result else 0.0