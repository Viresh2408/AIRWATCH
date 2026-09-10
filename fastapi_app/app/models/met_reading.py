from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.aqi import Base


class MetReading(Base):
    """Database model for meteorological readings and forecasts per station."""
    __tablename__ = "met_readings"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), index=True)
    datetime = Column(DateTime(timezone=True), nullable=False, index=True)

    pbl_height = Column(Float, nullable=True)
    windspeed_10m = Column(Float, nullable=True)
    winddirection_10m = Column(Float, nullable=True)
    wind_u_10m = Column(Float, nullable=True)
    wind_v_10m = Column(Float, nullable=True)
    windspeed_80m = Column(Float, nullable=True)
    winddirection_80m = Column(Float, nullable=True)
    wind_u_80m = Column(Float, nullable=True)
    wind_v_80m = Column(Float, nullable=True)
    temperature = Column(Float, nullable=True)
    relativehumidity = Column(Float, nullable=True)
    uv_index = Column(Float, nullable=True)
    surface_pressure = Column(Float, nullable=True)

    station = relationship("Station", back_populates="met_readings")

    __table_args__ = (
        UniqueConstraint("station_id", "datetime", name="uq_met_reading"),
    )
