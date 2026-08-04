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
from services.new_product_service import NewProductService
from models.purchase_payment_term import PaymentStatusEnum
from models.purchase_payment_transaction import PurchasePaymentTransaction, PaymentMethodEnum
from models.purchase import Purchase
from models.supplier_credit_ledger import SupplierCreditLedger
from datetime import datetime

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
    def create_shipment(self, data: dict, landed_data: dict = None):
        with get_session() as session:
            required = ['supplier_id', 'bank_account_id', 'proforma_date',
                        'exchange_rate', 'created_by_user_id', 'products']
            for field in required:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")

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
            session.flush()   # ensure shipment gets an ID

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
                    landed_cost_per_unit=prod.get('landed_cost_per_unit', 0.0),   # <-- NEW
                    target_selling_price=prod.get('target_selling_price', 0.0),   # <-- NEW
                )
                session.add(product)

            # Compute total FOB in ETB
            total_fob_etb = 0.0
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
                    data.get('payment_date', shipment.proforma_date)
                )
                if fob_tx_id:
                    affected_accounts.add(shipment.bank_account_id)

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
    def update_shipment(self, shipment_id: int, data: dict, landed_data: dict = None):
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

            # Delete old products
            for prod in shipment.products:
                session.delete(prod)

            # Handle FOB transaction
            affected_accounts = set()
            old_fob_tx = session.query(BankTransaction).filter(
                BankTransaction.reference_number == f"SHIP-FOB-{shipment_id}",
                BankTransaction.is_deleted == False
            ).first()
            if old_fob_tx:
                old_fob_tx.is_deleted = True
                affected_accounts.add(old_fob_tx.bank_account_id)

            # Delete old costs and their transactions
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
                    landed_cost_per_unit=prod.get('landed_cost_per_unit', 0.0),   # <-- NEW
                    target_selling_price=prod.get('target_selling_price', 0.0),   # <-- NEW
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


    def stock_in(self, shipment_id: int, mapping: dict) -> Purchase:
        """
        mapping: {shipment_product_id: {'name': str, 'unit': str, 'use_market_price': bool}}
        Returns the created Purchase object.
        """
        with get_session() as session:
            shipment = session.query(ImportShipment).filter(
                ImportShipment.id == shipment_id,
                ImportShipment.is_deleted == False
            ).with_for_update().first()
            if not shipment:
                raise ValueError("Shipment not found")
            if shipment.status.value != "approved":
                raise ValueError("Only approved shipments can be stocked in")
            if shipment.stocked_in:
                raise ValueError("Shipment already stocked in")

            # For credit shipments, all costs must be paid (have bank transaction)
            if shipment.payment_status == "credit":
                unpaid_costs = [c for c in shipment.costs if c.bank_transaction_id is None]
                if unpaid_costs:
                    raise ValueError(f"All shipment costs must be paid. {len(unpaid_costs)} cost(s) are unpaid.")

            # Build product data for NewProductService.create
            products_data = []
            for sp in shipment.products:
                if sp.is_deleted:
                    continue
                map_data = mapping.get(sp.id)
                if not map_data:
                    raise ValueError(f"Product '{sp.product_name}' not mapped.")
                name = map_data['name']
                unit = map_data['unit']
                use_market_price = map_data.get('use_market_price', False)

                # Determine selling price
                if use_market_price and sp.market_price:
                    selling_price = sp.market_price
                else:
                    selling_price = sp.target_selling_price or 0.0

                if sp.landed_cost_per_unit is None:
                    raise ValueError(f"Landed cost missing for '{sp.product_name}'. Re‑approve shipment.")

                products_data.append({
                    'name': name,
                    'unit': unit,
                    'quantity': sp.cartons,                # number of packs (cartons)
                    'dozen': sp.qty_per_carton,            # pieces per pack
                    'cost_price': sp.landed_cost_per_unit, # per piece
                    'selling_price': selling_price,
                })

            if not products_data:
                raise ValueError("No valid products to stock in.")

            # Prepare purchase data – same structure as used in ProductFormDialog
            purchase_data = {
                'supplier_id': shipment.supplier_id,
                'payment_status': shipment.payment_status,  # 'paid' or 'credit'
                'payment_method': None,                     # no new bank transaction
                'bank_account_id': None,                    # no new bank transaction
                'payment_date': shipment.proforma_date,
                'user_id': shipment.created_by_user_id,
                'products': products_data,
                'created_at': datetime.now(),
                'last_modified': datetime.now(),
            }

            # Use existing NewProductService.create – this handles purchase, batches, transactions, ledger
            product_service = NewProductService()
            purchase = product_service.create(purchase_data)
            if not purchase:
                raise ValueError("Failed to create purchase from shipment")

            # Now link bank transactions and adjust payment term
            payment_term = purchase.payment_terms[0]
            total_amount = purchase.total_amount

            if shipment.payment_status == "paid":
                # Link all bank transactions (FOB + costs)
                self._link_shipment_bank_transactions(session, shipment, payment_term)
                payment_term.paid_amount = total_amount
                payment_term.payment_status = PaymentStatusEnum.PAID
            else:  # credit
                # Link only cost transactions (non‑FOB)
                paid_amount = self._link_cost_bank_transactions(session, shipment, payment_term)
                payment_term.paid_amount = paid_amount
                payment_term.update_status()  # sets PARTIAL or CREDIT

            # Mark shipment as stocked in
            shipment.stocked_in = True
            shipment.purchase_id = purchase.id

            session.commit()
            return purchase

    # ========== Helper methods ==========

    def _link_shipment_bank_transactions(self, session, shipment, payment_term):
        """Link FOB and cost transactions for paid shipments."""
        # FOB transaction
        fob_txs = session.query(BankTransaction).filter(
            BankTransaction.reference_number == f"SHIP-FOB-{shipment.id}",
            BankTransaction.is_deleted == False
        ).all()
        for tx in fob_txs:
            tx.purchase_payment_term_id = payment_term.id
            self._create_purchase_payment_from_bank_tx(session, tx, payment_term)

        # Cost transactions
        cost_txs = session.query(BankTransaction).join(ShipmentCost).filter(
            ShipmentCost.shipment_id == shipment.id,
            BankTransaction.is_deleted == False
        ).all()
        for tx in cost_txs:
            tx.purchase_payment_term_id = payment_term.id
            self._create_purchase_payment_from_bank_tx(session, tx, payment_term)

    def _link_cost_bank_transactions(self, session, shipment, payment_term):
        """Link only cost transactions for credit shipments, return total paid amount."""
        paid_amount = 0.0
        cost_txs = session.query(BankTransaction).join(ShipmentCost).filter(
            ShipmentCost.shipment_id == shipment.id,
            BankTransaction.is_deleted == False
        ).all()
        for tx in cost_txs:
            tx.purchase_payment_term_id = payment_term.id
            self._create_purchase_payment_from_bank_tx(session, tx, payment_term)
            paid_amount += tx.amount
        return paid_amount

    def _create_purchase_payment_from_bank_tx(self, session, bank_tx, payment_term):
        """Create a PurchasePaymentTransaction and SupplierCreditLedger entry."""
        payment_tx = PurchasePaymentTransaction(
            purchase_payments_term_id=payment_term.id,
            payment_date=bank_tx.transaction_date,
            payment_method=bank_tx.payment_method or PaymentMethodEnum.TRANSFER,
            amount=bank_tx.amount,
            bank_account_id=bank_tx.bank_account_id,
            user_id=bank_tx.recorded_by_user_id,
            bank_transaction_id=bank_tx.id,
            notes="Auto‑linked from shipment payment"
        )
        session.add(payment_tx)
        session.flush()

        # Add ledger entry (credit to supplier)
        ledger_entry = SupplierCreditLedger(
            supplier_id=payment_term.purchase.supplier_id,
            purchase_id=payment_term.purchase_id,
            payment_transaction_id=payment_tx.id,
            bank_transaction_id=bank_tx.id,
            entry_date=payment_tx.payment_date,
            entry_type='payment',
            description=f"Payment from shipment (purchase #{payment_term.purchase_id})",
            debit=0.0,
            credit=payment_tx.amount,
        )
        session.add(ledger_entry)