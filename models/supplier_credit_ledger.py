from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, ForeignKey, Date, String, Float

from models.engine.database import BaseModel

class SupplierCreditLedger(BaseModel):
    __tablename__ = "supplier_credit_ledger"


    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    purchase_id = Column(Integer, ForeignKey('purchases.id'), nullable=True)
    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=True)
    payment_transaction_id = Column(Integer, ForeignKey('purchase_payment_transaction.id'), nullable=True)
    bank_transaction_id = Column(Integer, ForeignKey('bank_transactions.id'), nullable=True)
    entry_date = Column(Date, nullable=False)
    entry_type = Column(String(20), nullable=False)
    description = Column(String(500), nullable=True)
    debit = Column(Float, default=0.0) 
    credit = Column(Float, default=0.0)


    supplier = relationship("Supplier", backref="credit_ledger_entries")
    purchase = relationship("Purchase", backref="credit_ledger_entries")
    batch = relationship("ProductBatch", backref="credit_ledger_entries")
    payment_transaction = relationship("PurchasePaymentTransaction", backref="credit_ledger_entries")
    bank_transaction = relationship("BankTransaction", backref="credit_ledger_entries")