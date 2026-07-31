#!/usr/bin/env python3
import logging
from typing import List, Optional
from sqlalchemy.orm import joinedload

from models.import_shipments import ImportShipment, ShipmentStatusEnum
from models.shipment_products import ShipmentProduct
from models.bank_transactions import BankTransaction
from services.base_service import BaseService, get_session
from models.shipment_costs import ShipmentCost

logger = logging.getLogger(__name__)

class ImportShipmentService(BaseService):
    def __init__(self):
        super().__init__(ImportShipment)

    # ------------------------------------------------------------------
    # Helper: create bank transaction inside an existing session
    # ------------------------------------------------------------------
    def _create_bank_transaction_for_cost(self, session, shipment_id, cost_data):
        """
        Create a BankTransaction (debit) for a paid cost.
        Returns the transaction ID or None.
        Uses the given session (avoid nested transactions).
        """
        from services.bank_transaction_service import BankTransactionService
        from models.bank_transactions import TransactionDirectionEnum

        bank_account_id = cost_data.get('bank_account_id')
        payment_date = cost_data.get('payment_date')
        if not bank_account_id or not payment_date:
            return None

        cost_type_name = cost_data.get('cost_type_name', 'Cost')
        description = f"Shipment #{shipment_id} - {cost_type_name}"

        tx_data = {
            'bank_account_id': bank_account_id,
            'amount': cost_data['amount'],
            'direction': TransactionDirectionEnum.DEBIT,
            'transaction_date': payment_date,
            'description': description,
            'reference_number': f"SHIP-{shipment_id}-{cost_data['cost_type_id']}"
        }

        tx_service = BankTransactionService()
        tx = tx_service._create_transaction_in_session(session, tx_data)
        if tx:
            session.flush()   # to get the ID
            return tx.id
        return None

    # ------------------------------------------------------------------
    # Create shipment
    # ------------------------------------------------------------------
    def create_shipment(self, data: dict):
        with get_session() as session:
            required = ['supplier_id', 'bank_account_id', 'proforma_date',
                        'exchange_rate', 'created_by_user_id', 'products']
            for field in required:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")

            shipment = ImportShipment(
                supplier_id=data['supplier_id'],
                bank_account_id=data['bank_account_id'],
                proforma_date=data['proforma_date'],
                exchange_rate=float(data['exchange_rate']),
                target_margin=data.get('target_margin', 20.0),
                allocation_mode=data.get('allocation_mode', 'used_cbm'),
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

            # Save costs
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
                    if cost.get('paid', False):
                        tx_id = self._create_bank_transaction_for_cost(
                            session, shipment.id, cost
                        )
                        if tx_id:
                            shipment_cost.bank_transaction_id = tx_id
                    session.add(shipment_cost)

            session.commit()
            logger.info(f"Created shipment #{shipment.id} with {len(data['products'])} products and {len(costs)} costs")
            return shipment

    # ------------------------------------------------------------------
    # Get all shipments
    # ------------------------------------------------------------------
    def get_all(self) -> List[ImportShipment]:
        with get_session() as session:
            return session.query(self.model).options(
                joinedload(ImportShipment.supplier),
                joinedload(ImportShipment.bank_account),
                joinedload(ImportShipment.products),
                joinedload(ImportShipment.costs).joinedload(ShipmentCost.cost_type)
            ).filter(
                self.model.is_deleted == False
            ).order_by(self.model.id.desc()).all()

    # ------------------------------------------------------------------
    # Delete shipment (soft-delete)
    # ------------------------------------------------------------------
    def delete_shipment(self, shipment_id: int) -> bool:
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

    # ------------------------------------------------------------------
    # Get single shipment with all relations (including bank transactions)
    # ------------------------------------------------------------------
    def get_by_id_with_relations(self, shipment_id: int):
        """Fetch a shipment with all relationships for editing/viewing."""
        with get_session() as session:
            return session.query(self.model).options(
                joinedload(ImportShipment.supplier),
                joinedload(ImportShipment.bank_account),
                joinedload(ImportShipment.products),
                joinedload(ImportShipment.costs)
                    .joinedload(ShipmentCost.cost_type),
                joinedload(ImportShipment.costs)
                    .joinedload(ShipmentCost.bank_transaction)
                    .joinedload(BankTransaction.bank_account)
            ).filter(
                self.model.id == shipment_id,
                self.model.is_deleted == False
            ).first()

    # ------------------------------------------------------------------
    # Update shipment (replace products and costs)
    # ------------------------------------------------------------------
    def update_shipment(self, shipment_id: int, data: dict):
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
            shipment.allocation_mode = data.get('allocation_mode', 'used_cbm')

            # Delete old products
            for prod in shipment.products:
                session.delete(prod)

            # Delete old costs and soft-delete their bank transactions
            for cost in shipment.costs:
                if cost.bank_transaction_id:
                    tx = session.query(BankTransaction).filter(
                        BankTransaction.id == cost.bank_transaction_id,
                        BankTransaction.is_deleted == False
                    ).first()
                    if tx:
                        tx.is_deleted = True
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
                    if cost.get('paid', False):
                        tx_id = self._create_bank_transaction_for_cost(
                            session, shipment.id, cost
                        )
                        if tx_id:
                            shipment_cost.bank_transaction_id = tx_id
                    session.add(shipment_cost)

            session.commit()
            logger.info(f"Updated shipment #{shipment.id}")
            return shipment

    # ------------------------------------------------------------------
    # Approve shipment
    # ------------------------------------------------------------------
    def approve_shipment(self, shipment_id: int) -> bool:
        with get_session() as session:
            shipment = session.query(self.model).filter(
                self.model.id == shipment_id,
                self.model.is_deleted == False
            ).first()
            if not shipment:
                return False
            if shipment.status != ShipmentStatusEnum.DRAFT:
                raise ValueError("Only DRAFT shipments can be approved")
            shipment.status = ShipmentStatusEnum.APPROVED
            session.commit()
            return True

    # ------------------------------------------------------------------
    # Cancel shipment
    # ------------------------------------------------------------------
    def cancel_shipment(self, shipment_id: int) -> bool:
        with get_session() as session:
            shipment = session.query(self.model).filter(
                self.model.id == shipment_id,
                self.model.is_deleted == False
            ).first()
            if not shipment:
                return False
            if shipment.status != ShipmentStatusEnum.DRAFT:
                raise ValueError("Only DRAFT shipments can be cancelled")
            shipment.status = ShipmentStatusEnum.CANCELLED
            session.commit()
            return True