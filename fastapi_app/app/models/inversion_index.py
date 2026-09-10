from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.aqi import Base


class InversionIndex(Base):
    """Database model for atmospheric inversion strength index and category."""
    __tablename__ = "inversion_index"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), index=True)
    datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    score = Column(Float, nullable=True)       # Inversion score [0.0 - 1.0]
    category = Column(String, nullable=True)    # 'None', 'Weak', 'Moderate', 'Strong', 'Severe'

    station = relationship("Station", back_populates="inversion_indices")

    __table_args__ = (
        UniqueConstraint("station_id", "datetime", name="uq_inversion_index"),
    )
