from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

# This base is used to define all your models
Base = declarative_base()

class Station(Base):
    """Database model for an AQI Monitoring Station (metadata)."""
    __tablename__ = "stations"
    
    # Matches 'location_id' from CSV
    id = Column(Integer, primary_key=True, index=True) 
    name = Column(String, index=True) # Matches 'location' from CSV
    lat = Column(Float)
    lon = Column(Float)
    
    # Relationships for easy querying
    readings = relationship("Reading", back_populates="station")
    predictions = relationship("Prediction", back_populates="station")
    met_readings = relationship("MetReading", back_populates="station")
    inversion_indices = relationship("InversionIndex", back_populates="station")

class Reading(Base):
    """Database model for individual sensor measurements."""
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"))
    datetime = Column(DateTime(timezone=True), default=func.now(), index=True)
    parameter = Column(String)
    unit = Column(String)
    value = Column(Float)

    station = relationship("Station", back_populates="readings")

    # Unique constraint enables INSERT OR IGNORE upserts — no duplicate checks needed
    __table_args__ = (
        UniqueConstraint("station_id", "datetime", "parameter", name="uq_reading"),
    )

class Prediction(Base):
    """
    Database model for forecasted AQI values.

    Phase 2 additions (all nullable — backwards-compatible):
      - predicted_o3:          O3 sub-model output (µg/m³)
      - pm25_lower/upper:      90% confidence interval bounds for PM2.5
      - pm10_lower/upper:      90% confidence interval bounds for PM10
      - inversion_score:       [0.0–1.0] aerosol-trapping severity at this hour
      - inversion_category:    Human-readable category ('None'/'Moderate'/'Strong'/'Severe')
      - iterations_run:        Number of coupling iterations executed (1–3)
      - converged:             Whether the feedback loop converged within max iterations
      - plume_pm25_contrib:    Fire plume contribution to PM2.5 (µg/m³)
      - pbl_height_corrected:  Aerosol-corrected PBL height used in final forecast (m)
    """
    __tablename__ = "predictions"

    id            = Column(Integer, primary_key=True, index=True)
    station_id    = Column(Integer, ForeignKey("stations.id"))

    # When this forecast is valid for
    prediction_time = Column(DateTime(timezone=True), index=True)
    # Offset from the forecast run base (1 = +1h, 72 = +72h)
    hour_offset   = Column(Integer, nullable=True)

    # --- Core pollutant forecasts ---
    predicted_aqi  = Column(Float)
    predicted_pm25 = Column(Float, nullable=True)
    predicted_pm10 = Column(Float, nullable=True)
    predicted_o3   = Column(Float, nullable=True)

    # --- Confidence intervals (90% empirical, scaled by inversion_score) ---
    pm25_lower = Column(Float, nullable=True)
    pm25_upper = Column(Float, nullable=True)
    pm10_lower = Column(Float, nullable=True)
    pm10_upper = Column(Float, nullable=True)

    # --- Coupling diagnostics ---
    inversion_score    = Column(Float,   nullable=True)   # [0.0–1.0]
    inversion_category = Column(String,  nullable=True)   # 'None'/'Moderate'/'Strong'/'Severe'
    iterations_run     = Column(Integer, nullable=True)   # 1–3
    converged          = Column(Integer, nullable=True)   # 0/1 (SQLite has no native bool)
    plume_pm25_contrib = Column(Float,   nullable=True)   # µg/m³ from fire plume
    pbl_height_corrected = Column(Float, nullable=True)   # metres

    # --- MLOps ---
    model_version = Column(String, default="coupled_xgb_v1.0")

    station = relationship("Station", back_populates="predictions")