from sqlalchemy import Column, Integer, Float, String, DateTime
from app.models.aqi import Base


class FireHotspot(Base):
    """Database model for active fire hotspots detected by NASA FIRMS (VIIRS/MODIS)."""
    __tablename__ = "fire_hotspots"

    id = Column(Integer, primary_key=True, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    frp = Column(Float, nullable=True)  # Fire Radiative Power (MW)
    detected_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source = Column(String, default="FIRMS_VIIRS")
