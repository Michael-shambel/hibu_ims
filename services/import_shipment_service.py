#!/usr/bin/env python3
import logging
from typing import List, Optional

from models.import_shipments import ImportShipment, ShipmentStatusEnum
from models.shipment_products import ShipmentProduct
from services.base_service import BaseService, get_session

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
                status=ShipmentStatusEnum.DRAFT,
                created_by_user_id=data['created_by_user_id']
            )
            session.add(shipment)
            session.flush()

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
                    total_cbm=total_cbm
                )
                session.add(product)
            session.commit()
            logger.info(f"Created shipment #{shipment.id} with {len(data['products'])} products")
            return shipment