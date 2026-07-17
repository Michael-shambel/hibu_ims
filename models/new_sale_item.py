from models.engine.database import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, Float, Boolean
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


    sale = relationship("ProfessionalSale", back_populates="items")
    batch = relationship("ProductBatch")

    def __repr__(self):
        return f"<SaleItem(id={self.id}, sale={self.sale_id}, batch={self.batch_id}, inv_qty={self.invoice_quantity}, non_qty={self.non_invoice_quantity})>"