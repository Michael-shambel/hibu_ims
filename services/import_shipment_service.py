#!/usr/bin/env python3
import logging
from typing import List, Optional
from sqlalchemy.orm import joinedload

from models.import_shipments import ImportShipment, ShipmentStatusEnum
from models.shipment_products import ShipmentProduct
from services.base_service import BaseService, get_session
from models.shipment_costs import ShipmentCost

logger = logging.getLogger(__name__)

class ImportShipmentService(BaseService):
    def __init__(self):
        super().__init__(ImportShipment)

    def create_shipment(self, data: dict):
        with get_session() as session:
            required = ['supplier_id', 'bank_account_id', 'proforma_date', 'exchange_rate', 'created_by_user_id', 'products']
            for field in required:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")

            shipment = ImportShipment(
                supplier_id=data['supplier_id'],
                bank_account_id=data['bank_account_id'],
                proforma_date=data['proforma_date'],
                exchange_rate=float(data['exchange_rate']),
                target_margin=data.get('target_margin', 20.0),
                status=ShipmentStatusEnum.DRAFT,
                created_by_user_id=data['created_by_user_id']
            )
            session.add(shipment)
            session.flush()

            # Save products
            for prod in data['products']:
                if prod.get('cartons', 0) <= 0 or prod.get('qty_per_carton', 0) <= 0:
                    continue

                total_qty = prod['cartons'] * prod['qty_per_carton']
                total_cbm = prod['cartons'] * prod.get('cbm_per_carton', 0.0)

                product = ShipmentProduct(
                    shipment_id=shipment.id,
                    item_number=prod.get('item_number'),
                    product_name=prod['product_name'],
                    unit=prod['unit'],
                    cartons=prod['cartons'],
                    qty_per_carton=prod['qty_per_carton'],
                    total_quantity=total_qty,
                    unit_price_rmb=prod['unit_price_rmb'],
                    cbm_per_carton=prod.get('cbm_per_carton', 0.0),
                    total_cbm=total_cbm,
                    market_price=prod.get('market_price', 0.0),
                )
                session.add(product)

            # Save costs (NEW)
            costs = data.get('costs', [])
            for cost in costs:
                cost_type_id = cost.get('cost_type_id')
                amount = cost.get('amount')
                if cost_type_id and amount is not None:
                    shipment_cost = ShipmentCost(
                        shipment_id=shipment.id,
                        cost_type_id=cost_type_id,
                        amount=amount
                    )
                    session.add(shipment_cost)

            session.commit()
            logger.info(f"Created shipment #{shipment.id} with {len(data['products'])} products and {len(costs)} costs")
            return shipment

    def get_all(self) -> List[ImportShipment]:
        with get_session() as session:
            return session.query(self.model).options(
                joinedload(ImportShipment.supplier),
                joinedload(ImportShipment.bank_account),
                joinedload(ImportShipment.products),
                joinedload(ImportShipment.costs)
            ).filter(
                self.model.is_deleted == False
            ).order_by(self.model.id.desc()).all()

    def delete_shipment(self, shipment_id: int) -> bool:
        """Soft‑delete a shipment (only if DRAFT)."""
        with get_session() as session:
            shipment = session.query(self.model).filter(
                self.model.id == shipment_id,
                self.model.is_deleted == False
            ).first()
            if not shipment:
                return False
            if shipment.status != ShipmentStatusEnum.DRAFT:
                raise ValueError("Only DRAFT shipments can be deleted")
            shipment.is_deleted = True
            session.commit()
            return True

    def get_by_id_with_relations(self, shipment_id: int):
        """Fetch a shipment with all relationships for editing/viewing."""
        with get_session() as session:
            return session.query(self.model).options(
                joinedload(ImportShipment.supplier),
                joinedload(ImportShipment.bank_account),
                joinedload(ImportShipment.products),
                joinedload(ImportShipment.costs).joinedload(ShipmentCost.cost_type)
            ).filter(
                self.model.id == shipment_id,
                self.model.is_deleted == False
            ).first()

    def update_shipment(self, shipment_id: int, data: dict):
        """Update an existing draft shipment (replace products and costs)."""
        with get_session() as session:
            shipment = session.query(self.model).filter(
                self.model.id == shipment_id,
                self.model.is_deleted == False
            ).first()
            if not shipment:
                raise ValueError("Shipment not found")
            if shipment.status != ShipmentStatusEnum.DRAFT:
                raise ValueError("Only DRAFT shipments can be edited")

            # Update basic fields
            shipment.supplier_id = data['supplier_id']
            shipment.bank_account_id = data['bank_account_id']
            shipment.proforma_date = data['proforma_date']
            shipment.exchange_rate = float(data['exchange_rate'])
            shipment.target_margin = data.get('target_margin', 20.0)

            for prod in shipment.products:
                session.delete(prod)
            for cost in shipment.costs:
                session.delete(cost)

            # Add new products
            for prod in data['products']:
                if prod.get('cartons', 0) <= 0 or prod.get('qty_per_carton', 0) <= 0:
                    continue
                total_qty = prod['cartons'] * prod['qty_per_carton']
                total_cbm = prod['cartons'] * prod.get('cbm_per_carton', 0.0)
                product = ShipmentProduct(
                    shipment_id=shipment.id,
                    item_number=prod.get('item_number'),
                    product_name=prod['product_name'],
                    unit=prod['unit'],
                    cartons=prod['cartons'],
                    qty_per_carton=prod['qty_per_carton'],
                    total_quantity=total_qty,
                    unit_price_rmb=prod['unit_price_rmb'],
                    cbm_per_carton=prod.get('cbm_per_carton', 0.0),
                    total_cbm=total_cbm,
                    market_price=prod.get('market_price', 0.0),
                )
                session.add(product)

            # Add new costs
            for cost in data.get('costs', []):
                cost_type_id = cost.get('cost_type_id')
                amount = cost.get('amount')
                if cost_type_id and amount is not None:
                    shipment_cost = ShipmentCost(
                        shipment_id=shipment.id,
                        cost_type_id=cost_type_id,
                        amount=amount
                    )
                    session.add(shipment_cost)

            session.commit()
            logger.info(f"Updated shipment #{shipment.id}")
            return shipment