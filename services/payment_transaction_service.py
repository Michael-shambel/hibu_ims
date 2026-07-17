from datetime import datetime, date
import logging
from models.payment_transaction import PaymentTransaction, PaymentMethodEnum
from models.sale_payment_term import SalePaymentTerm
from models.bank_transactions import BankTransaction, TransactionDirectionEnum
from services.base_service import BaseService, get_session
from services.bank_transaction_service import BankTransactionService

logger = logging.getLogger(__name__)

class PaymentTransactionService(BaseService[PaymentTransaction]):
    def __init__(self):
        super().__init__(PaymentTransaction)
        self.bank_transaction_service = BankTransactionService()

    def record_payment(
        self,
        session,
        sale_payment_term_id: int,
        amount: float,
        bank_account_id: int,
        user_id: int,
        note: str = "",
        payment_date=None
    ):
        if payment_date is None:
            payment_date = date.today()
        
        if isinstance(payment_date, str):
            from datetime import datetime as dt_parser
            payment_date = dt_parser.strptime(payment_date, "%Y-%m-%d").date()
        # Convert to datetime for created_at/last_modified (use start of day)
        now = datetime.now()
        dt = datetime.combine(payment_date, now.time())

        payment_term = session.query(SalePaymentTerm).get(sale_payment_term_id)
        if not payment_term:
            logger.error(f"SalePaymentTerm {sale_payment_term_id} not found")
            raise ValueError(f"SalePaymentTerm {sale_payment_term_id} not found")

        # Create PaymentTransaction with explicit timestamps
        payment_transaction = PaymentTransaction(
            sale_payment_term_id=sale_payment_term_id,
            payment_date=payment_date,
            payment_method=PaymentMethodEnum.TRANSFER,
            amount=amount,
            bank_account_id=bank_account_id,
            user_id=user_id,
            notes=note,
            created_at=dt,
            last_modified=dt
        )
        session.add(payment_transaction)

        # Update the payment term
        payment_term.paid_amount += amount
        payment_term.update_status()
        payment_term.last_modified = dt   # also update term's timestamp
        session.flush()

        # Create BankTransaction using the service method that correctly chains balance_after
        if bank_account_id:
            delivery_name = getattr(payment_term.sale, 'delivery_name', None) or 'unknown'
            description = f"Payment from {delivery_name}"

            tx_data = {
                'bank_account_id': bank_account_id,
                'amount': amount,
                'direction': TransactionDirectionEnum.CREDIT,
                'transaction_date': payment_date,
                'description': description,
                'payment_method': PaymentMethodEnum.TRANSFER,
                'reference_number': None,
                'sale_payment_term_id': sale_payment_term_id,
                'recorded_by_user_id': user_id,
                'created_at': dt,
                'last_modified': dt,
            }
            bank_transaction = self.bank_transaction_service.create_transaction(session, tx_data)
            if not bank_transaction:
                logger.error("Failed to create bank transaction for payment")
                raise Exception("Bank transaction creation failed")

        return payment_transaction