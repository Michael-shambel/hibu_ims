from models.engine.database import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, Float, Boolean, DateTime
from sqlalchemy.orm import relationship


class ProfessionalSaleItem(BaseModel):
    __tablename__ = "new_sale_items"

    sale_id = Column(Integer, ForeignKey('professional_sales.id'), nullable=False)

    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=False)



    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    dozen = Column(Integer, nullable=False, default=1)
    total = Column(Float, nullable=False, default=0.0)
    for_despatch = Column(Boolean, default=False)
    despatched_at = Column(DateTime, nullable=True)


    sale = relationship("ProfessionalSale", back_populates="items")
    batch = relationship("ProductBatch")

    def __repr__(self):
        return f"<SaleItem(id={self.id}, sale={self.sale_id}, batch={self.batch_id}, unit_price={self.unit_price}, quantity={self.quantity})>"