
from sqlalchemy import Column, Integer, ForeignKey, String, Float, Index
from models.engine.database import BaseModel
from sqlalchemy.orm import relationship


class ShipmentProduct(BaseModel):
    __tablename__ = "shipment_products"

    shipment_id = Column(Integer, ForeignKey("import_shipments.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("professional_products.id"), nullable=True)
    item_number = Column(String(100), nullable=True, index=True)
    product_name = Column(String(200), nullable=False)
    unit = Column(String(50), nullable=False)

    cartons = Column(Integer, nullable=False)
    qty_per_carton = Column(Integer, nullable=False)
    total_quantity = Column(Integer, nullable=False)

    unit_price_rmb = Column(Float, nullable=False)
    cbm_per_carton = Column(Float, nullable=False)

    total_cbm = Column(Float, nullable=False)

    shipment = relationship("ImportShipment", back_populates="products")
    product = relationship("ProfessionalProduct", foreign_keys=[product_id])

    __table_args__ = (Index("ix_shipment_products_item_number", "item_number"),)