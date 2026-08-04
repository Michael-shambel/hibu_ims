
from enum import Enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from models.engine.database import BaseModel

class ShipmentStatusEnum(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    CANCELLED = "cancelled"

class PaymentStatusEnum(str, Enum):
    PAID = "paid"
    CREDIT = "credit"


class ImportShipment(BaseModel):
    __tablename__ = "import_shipments"

    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)
    proforma_date = Column(Date, nullable=False)
    exchange_rate = Column(Float, nullable=False)
    status = Column(SQLEnum(ShipmentStatusEnum), nullable=False, default=ShipmentStatusEnum.DRAFT)
    created_by_user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=False)
    target_margin = Column(Float, nullable=True, default=20.0)
    allocation_mode = Column(String(20), nullable=True, default="used_cbm")
    payment_status = Column(String(20), nullable=False, default=PaymentStatusEnum.CREDIT.value)
    stocked_in = Column(Boolean, default=False, nullable=False)
    purchase_id = Column(Integer, ForeignKey('purchases.id'), nullable=True)


    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    bank_account = relationship("BankAccount", foreign_keys=[bank_account_id])
    created_by = relationship("AuthUser", foreign_keys=[created_by_user_id])

    products = relationship(
        "ShipmentProduct",
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    costs = relationship(
        "ShipmentCost",
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<ImportShipment(id={self.id}, supplier={self.supplier_id}, status={self.status})>"