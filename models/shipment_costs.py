from models.engine.database import BaseModel
from sqlalchemy import Column, Integer, Float, String, ForeignKey
from sqlalchemy.orm import relationship



class ShipmentCost(BaseModel):
    __tablename__ = "shipment_costs"

    shipment_id = Column(Integer, ForeignKey("import_shipments.id"), nullable=False)
    cost_type_id = Column(Integer, ForeignKey("cost_types.id"), nullable=False)
    amount = Column(Float, nullable=False)

    shipment = relationship("ImportShipment", back_populates="costs")
    cost_type = relationship("CostType")