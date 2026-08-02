#!/usr/bin/env python3
import logging
from typing import List, Optional
from sqlalchemy.orm import joinedload
from datetime import date

from models.import_shipments import ImportShipment, ShipmentStatusEnum, PaymentStatusEnum
from models.shipment_products import ShipmentProduct
from models.bank_transactions import BankTransaction, TransactionDirectionEnum
from services.base_service import BaseService, get_session
from models.shipment_costs import ShipmentCost
from services.bank_transaction_service import BankTransactionService

logger = logging.getLogger(__name__)

class ImportShipmentService(BaseService):
    def __init__(self):
        super().__init__(ImportShipment)
        self.bank_tx_service = BankTransactionService()

    # ------------------------------------------------------------------
    # Helper: create bank transaction for a cost item (existing)
    # ------------------------------------------------------------------
    def _create_bank_transaction_for_cost(self, session, shipment_id, cost_data):
        """
        Create a BankTransaction (debit) for a paid cost.
        Returns the transaction ID or None.
        """
        bank_account_id = cost_data.get('bank_account_id')
        payment_date = cost_data.get('payment_date')
        if not bank_account_id or not payment_date:
            return None

        # Balance check
        current_balance = self.bank_tx_service.get_balance(bank_account_id)
        if current_balance < cost_data['amount']:
            raise ValueError(
                f"Insufficient funds in account {bank_account_id}. "
                f"Available: {current_balance:.2f}, Required: {cost_data['amount']:.2f}"
            )

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

        tx = self.bank_tx_service._create_transaction_in_session(session, tx_data)
        if tx:
            session.flush()
            return tx.id
        return None

    # ------------------------------------------------------------------
    # NEW: Helper to create bank transaction for FOB total
    # ------------------------------------------------------------------
    def _create_fob_transaction(self, session, shipment_id, bank_account_id, amount_etb, payment_date):
        """
        Create a DEBIT transaction for the total FOB amount.
        Returns the transaction ID or raises ValueError.
        """
        if amount_etb <= 0:
            return None

        current_balance = self.bank_tx_service.get_balance(bank_account_id)
        if current_balance < amount_etb:
            raise ValueError(
                f"Insufficient funds in account {bank_account_id}. "
                f"Available: {current_balance:.2f}, Required: {amount_etb:.2f}"
            )

        tx_data = {
            'bank_account_id': bank_account_id,
            'amount': amount_etb,
            'direction': TransactionDirectionEnum.DEBIT,
            'transaction_date': payment_date or date.today(),
            'description': f"Shipment #{shipment_id} - FOB Payment",
            'reference_number': f"SHIP-FOB-{shipment_id}"
        }
        tx = self.bank_tx_service._create_transaction_in_session(session, tx_data)
        if tx:
            session.flush()
            return tx.id
        return None

    # ------------------------------------------------------------------
    # Create shipment (updated)
    # ------------------------------------------------------------------
    def create_shipment(self, data: dict):
        with get_session() as session:
            required = ['supplier_id', 'bank_account_id', 'proforma_date',
                        'exchange_rate', 'created_by_user_id', 'products']
            for field in required:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")

            # Extract payment status (default CREDIT)
            payment_status = data.get('payment_status', PaymentStatusEnum.CREDIT.value)
            if payment_status not in [PaymentStatusEnum.PAID.value, PaymentStatusEnum.CREDIT.value]:
                payment_status = PaymentStatusEnum.CREDIT.value

            shipment = ImportShipment(
                supplier_id=data['supplier_id'],
                bank_account_id=data['bank_account_id'],
                proforma_date=data['proforma_date'],
                exchange_rate=float(data['exchange_rate']),
                target_margin=data.get('target_margin', 20.0),
                allocation_mode=data.get('allocation_mode', 'used_cbm'),
                status=ShipmentStatusEnum.DRAFT,
                created_by_user_id=data['created_by_user_id'],
                payment_status=payment_status
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

            # Compute total FOB in ETB
            total_fob_etb = 0.0
            # We need to iterate over products again after they are flushed; they are already added to session
            # but we can compute from the data directly
            for prod in data['products']:
                if prod.get('cartons', 0) <= 0 or prod.get('qty_per_carton', 0) <= 0:
                    continue
                total_qty = prod['cartons'] * prod['qty_per_carton']
                total_fob_etb += total_qty * prod['unit_price_rmb'] * shipment.exchange_rate

            # Handle FOB payment if PAID
            affected_accounts = set()
            if payment_status == PaymentStatusEnum.PAID.value and total_fob_etb > 0:
                fob_tx_id = self._create_fob_transaction(
                    session,
                    shipment.id,
                    shipment.bank_account_id,
                    total_fob_etb,
                    data.get('payment_date', shipment.proforma_date)  # use proforma date if payment_date not provided
                )
                if fob_tx_id:
                    affected_accounts.add(shipment.bank_account_id)

            # Save costs (existing logic)
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
                        # This may raise ValueError if insufficient funds
                        tx_id = self._create_bank_transaction_for_cost(
                            session, shipment.id, cost
                        )
                        if tx_id:
                            shipment_cost.bank_transaction_id = tx_id
                            affected_accounts.add(cost['bank_account_id'])
                    session.add(shipment_cost)

            # Recalculate balances for all affected accounts
            for acc_id in affected_accounts:
                self.bank_tx_service.recalculate_balances_for_account(session, acc_id)

            session.commit()
            logger.info(f"Created shipment #{shipment.id} with FOB ETB {total_fob_etb:.2f}, {len(data['products'])} products and {len(costs)} costs")
            return shipment

    # ------------------------------------------------------------------
    # Update shipment (updated)
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

            # Update payment status
            new_payment_status = data.get('payment_status', PaymentStatusEnum.CREDIT.value)
            if new_payment_status not in [PaymentStatusEnum.PAID.value, PaymentStatusEnum.CREDIT.value]:
                new_payment_status = PaymentStatusEnum.CREDIT.value
            shipment.payment_status = new_payment_status

            # Delete old products (unchanged)
            for prod in shipment.products:
                session.delete(prod)

            # --- Handle FOB transaction ---
            affected_accounts = set()
            # Find old FOB transaction
            old_fob_tx = session.query(BankTransaction).filter(
                BankTransaction.reference_number == f"SHIP-FOB-{shipment_id}",
                BankTransaction.is_deleted == False
            ).first()
            if old_fob_tx:
                old_fob_tx.is_deleted = True
                affected_accounts.add(old_fob_tx.bank_account_id)

            # --- Delete old costs and their transactions ---
            for cost in shipment.costs:
                if cost.bank_transaction_id:
                    tx = session.query(BankTransaction).filter(
                        BankTransaction.id == cost.bank_transaction_id,
                        BankTransaction.is_deleted == False
                    ).first()
                    if tx:
                        tx.is_deleted = True
                        affected_accounts.add(tx.bank_account_id)
                session.delete(cost)

            # Add new products (unchanged)
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

            # Compute new FOB total
            total_fob_etb = 0.0
            for prod in data['products']:
                if prod.get('cartons', 0) <= 0 or prod.get('qty_per_carton', 0) <= 0:
                    continue
                total_qty = prod['cartons'] * prod['qty_per_carton']
                total_fob_etb += total_qty * prod['unit_price_rmb'] * shipment.exchange_rate

            # Create new FOB transaction if PAID
            if new_payment_status == PaymentStatusEnum.PAID.value and total_fob_etb > 0:
                fob_tx_id = self._create_fob_transaction(
                    session,
                    shipment.id,
                    shipment.bank_account_id,
                    total_fob_etb,
                    data.get('payment_date', shipment.proforma_date)
                )
                if fob_tx_id:
                    affected_accounts.add(shipment.bank_account_id)

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
                            affected_accounts.add(cost['bank_account_id'])
                    session.add(shipment_cost)

            # Recalculate balances for all affected accounts
            for acc_id in affected_accounts:
                self.bank_tx_service.recalculate_balances_for_account(session, acc_id)

            session.commit()
            logger.info(f"Updated shipment #{shipment.id}")
            return shipment

    # ------------------------------------------------------------------
    # Get all shipments (unchanged)
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
    # Delete shipment (unchanged)
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
    # Get single shipment with relations (unchanged)
    # ------------------------------------------------------------------
    def get_by_id_with_relations(self, shipment_id: int):
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
    # Approve shipment (unchanged)
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
    # Cancel shipment (unchanged)
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