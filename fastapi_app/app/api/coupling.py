"""
coupling.py — Two-way meteorology-chemistry coupling API endpoints
SIH PS 26082: Phase 3 Backend/API Extension

Endpoints:
  1. GET /api/v1/coupling/inversion/{station_id}
     Hourly inversion score timeline [0.0–1.0], category ('None'..'Severe'),
     PBL height, collapse rate (dpbl/dt), and component breakdown.

  2. GET /api/v1/coupling/plume-forecast
     NASA FIRMS stubble-burning active fire hotspots + Gaussian plume advection
     contributions (PM2.5 µg/m³) across Delhi NCR monitoring stations.

  3. GET /api/v1/coupling/feedback-trace/{station_id}
     Judge-facing explainability endpoint demonstrating iterative convergence
     of aerosol-PBL two-way feedback loop (uncoupled vs coupled, PBL suppression %).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.config import settings
from app.models.aqi import Station, Prediction
from app.models.inversion_index import InversionIndex
from app.models.fire_hotspot import FireHotspot
from app.models.met_reading import MetReading
from app.services.inversion_calculator import compute_inversion_timeline, compute_inversion_score
from app.services.met_client import fetch_met_forecast, DELHI_NCR_STATION_COORDS
from app.services.fire_plume_service import fetch_fire_hotspots, estimate_plume_for_station
from app.services.coupling_engine import (
    CouplingContext,
    _run_single_step,
    CoupledForecastStep,
)
from app.services.prediction_service import _build_coupling_context, _met_defaults
from app.services.ml_pipeline import make_pm_model_fn, make_o3_model_fn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coupling", tags=["Coupling & Meteorology"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class InversionComponentSchema(BaseModel):
    base_score: float = Field(..., description="Base score from absolute PBL height")
    trend_bonus: float = Field(..., description="Collapse rate bonus for rapidly falling PBL")
    tod_bonus: float = Field(..., description="Time-of-day pre-dawn risk window modifier")


class InversionTimelinePointSchema(BaseModel):
    datetime: str
    score: float = Field(..., ge=0.0, le=1.0, description="Inversion strength index [0.0 - 1.0]")
    category: str = Field(..., description="'None', 'Weak', 'Moderate', 'Strong', or 'Severe'")
    pbl_height: float = Field(..., description="Planetary boundary layer height (m)")
    dpbl_dt: Optional[float] = Field(None, description="PBL change rate (m/h, negative = collapsing)")
    components: Optional[InversionComponentSchema] = None


class InversionResponseSchema(BaseModel):
    station_id: int
    station_name: str
    lat: float
    lon: float
    current_score: float
    current_category: str
    peak_score: float
    peak_category: str
    peak_time: Optional[str] = None
    horizon_hours: int
    timeline: List[InversionTimelinePointSchema]


class FireHotspotSchema(BaseModel):
    lat: float
    lon: float
    frp: Optional[float] = Field(None, description="Fire Radiative Power (MW)")
    detected_at: Optional[str] = None
    source: Optional[str] = "FIRMS_VIIRS"


class PlumeHourlyPointSchema(BaseModel):
    datetime: str
    plume_pm25_contrib: float = Field(..., description="Estimated PM2.5 contribution from fire plume (µg/m³)")
    wind_dir_80m: Optional[float] = Field(None, description="Wind direction at 80m AGL (deg)")
    wind_speed_80m: Optional[float] = Field(None, description="Wind speed at 80m AGL (m/s)")
    hotspot_count: int


class StationPlumeForecastSchema(BaseModel):
    station_id: int
    station_name: str
    lat: float
    lon: float
    peak_plume_contrib_pm25: float
    arrival_time: Optional[str] = Field(None, description="First timestep where plume PM2.5 > 5.0 µg/m³")
    timeline: List[PlumeHourlyPointSchema]


class PlumeForecastResponseSchema(BaseModel):
    active_hotspots_count: int
    source_region: str
    methodology: str
    disclaimer: str
    generated_at: str
    hotspots: List[FireHotspotSchema]
    stations: List[StationPlumeForecastSchema]


class IterationTraceStepSchema(BaseModel):
    iteration: int
    pm25_estimate: float
    pm10_estimate: Optional[float] = None
    pbl_corrected: float
    t_corrected: float
    inversion_score: float
    delta_pm25: float


class FeedbackTraceResponseSchema(BaseModel):
    station_id: int
    station_name: str
    hour_offset: int
    forecast_time: str
    converged: bool
    iterations_run: int
    final_pm25: float
    final_pm10: float
    final_o3: float
    pbl_height_raw: float
    pbl_height_corrected: float
    pbl_suppression_pct: float
    temperature_raw: float
    temperature_corrected: float
    uv_index_effective: float
    inversion_score: float
    inversion_category: str
    iteration_trace: List[IterationTraceStepSchema]
    physics_explanation: str


# ---------------------------------------------------------------------------
# Endpoint 1: Inversion Timeline
# ---------------------------------------------------------------------------

@router.get("/inversion/{station_id}", response_model=InversionResponseSchema)
def get_inversion_timeline(
    station_id: int,
    hours: int = Query(default=72, ge=1, le=168, description="Forecast hours (1-168)"),
    db: Session = Depends(get_db),
):
    """
    Returns atmospheric temperature inversion strength timeline for a station.
    Computes normalized inversion score [0.0–1.0], category ('None' to 'Severe'),
    PBL height, rate of collapse (dpbl/dt), and component breakdown.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station {station_id} not found")

    # Fetch meteorological records (live from Open-Meteo or climatological fallback)
    try:
        met_records = fetch_met_forecast(station_id)
    except Exception as exc:
        logger.warning("Met forecast fetch failed for station %d: %s; using defaults.", station_id, exc)
        met_records = _met_defaults(station_id)

    if not met_records:
        met_records = _met_defaults(station_id)

    met_records = met_records[:hours]

    # Compute timeline using inversion calculator
    timeline_raw = compute_inversion_timeline(met_records)

    timeline_points = []
    peak_score = 0.0
    peak_cat = "None"
    peak_time = None

    for item in timeline_raw:
        score = item["score"]
        if score > peak_score:
            peak_score = score
            peak_cat = item["category"]
            peak_time = item.get("datetime")

        comps = item.get("components")
        comp_schema = (
            InversionComponentSchema(
                base_score=comps.get("base_score", 0.0),
                trend_bonus=comps.get("trend_bonus", 0.0),
                tod_bonus=comps.get("tod_bonus", 0.0),
            )
            if comps
            else None
        )

        timeline_points.append(
            InversionTimelinePointSchema(
                datetime=item.get("datetime") or datetime.utcnow().isoformat(),
                score=score,
                category=item["category"],
                pbl_height=item["pbl_height"],
                dpbl_dt=item.get("dpbl_dt"),
                components=comp_schema,
            )
        )

    current_point = timeline_points[0] if timeline_points else None
    current_score = current_point.score if current_point else 0.0
    current_category = current_point.category if current_point else "None"

    return InversionResponseSchema(
        station_id=station.id,
        station_name=station.name,
        lat=station.lat,
        lon=station.lon,
        current_score=current_score,
        current_category=current_category,
        peak_score=round(peak_score, 4),
        peak_category=peak_cat,
        peak_time=peak_time,
        horizon_hours=len(timeline_points),
        timeline=timeline_points,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: Fire Plume Forecast
# ---------------------------------------------------------------------------

@router.get("/plume-forecast", response_model=PlumeForecastResponseSchema)
def get_plume_forecast(
    station_id: Optional[int] = Query(None, description="Optional station ID to filter"),
    db: Session = Depends(get_db),
):
    """
    Returns NASA FIRMS active fire hotspots and Gaussian plume advection PM2.5
    transport forecast across Delhi NCR monitoring stations.
    """
    # Fetch hotspots from FIRMS API (or DB / fallback)
    hotspots = fetch_fire_hotspots(settings.FIRMS_API_KEY)

    # Convert hotspots to schemas
    hotspot_schemas = [
        FireHotspotSchema(
            lat=hs["lat"],
            lon=hs["lon"],
            frp=hs.get("frp"),
            detected_at=(
                hs["acq_datetime"].isoformat()
                if isinstance(hs.get("acq_datetime"), datetime)
                else None
            ),
            source="FIRMS_VIIRS",
        )
        for hs in hotspots[:200]  # Cap at top 200 for payload efficiency
    ]

    # Stations to calculate
    query = db.query(Station)
    if station_id is not None:
        query = query.filter(Station.id == station_id)
    stations = query.all()

    station_forecasts: List[StationPlumeForecastSchema] = []

    for st in stations:
        try:
            met_records = fetch_met_forecast(st.id)
        except Exception:
            met_records = _met_defaults(st.id)

        if not met_records:
            met_records = _met_defaults(st.id)

        hourly_contribs = estimate_plume_for_station(
            hotspots=hotspots,
            station_lat=st.lat,
            station_lon=st.lon,
            met_records=met_records,
        )

        timeline = []
        peak_contrib = 0.0
        arrival_time = None

        for h in hourly_contribs:
            dt_str = (
                h["datetime"].isoformat()
                if isinstance(h.get("datetime"), datetime)
                else str(h.get("datetime"))
            )
            c = float(h.get("plume_pm25_contrib", 0.0))
            if c > peak_contrib:
                peak_contrib = c
            if arrival_time is None and c >= 5.0:
                arrival_time = dt_str

            timeline.append(
                PlumeHourlyPointSchema(
                    datetime=dt_str,
                    plume_pm25_contrib=c,
                    wind_dir_80m=h.get("wind_dir_80m"),
                    wind_speed_80m=h.get("wind_speed_80m"),
                    hotspot_count=int(h.get("hotspot_count", len(hotspots))),
                )
            )

        station_forecasts.append(
            StationPlumeForecastSchema(
                station_id=st.id,
                station_name=st.name,
                lat=st.lat,
                lon=st.lon,
                peak_plume_contrib_pm25=round(peak_contrib, 2),
                arrival_time=arrival_time,
                timeline=timeline,
            )
        )

    return PlumeForecastResponseSchema(
        active_hotspots_count=len(hotspots),
        source_region="Punjab / Haryana / Western UP (stubble-burning corridor)",
        methodology="Gaussian plume advection cone (spread sigma=15 deg, distance decay r^1.5) driven by 80m AGL wind field",
        disclaimer="Simplified 2-way coupling emulator. 80m AGL wind field used in place of 850 hPa pressure-level wind to operate on Open-Meteo free tier without ERA5 download latency.",
        generated_at=datetime.utcnow().isoformat(),
        hotspots=hotspot_schemas,
        stations=station_forecasts,
    )


# ---------------------------------------------------------------------------
# Endpoint 3: Coupling Feedback Trace (Explainability)
# ---------------------------------------------------------------------------

@router.get("/feedback-trace/{station_id}", response_model=FeedbackTraceResponseSchema)
def get_feedback_trace(
    station_id: int,
    hour_offset: int = Query(default=1, ge=1, le=72, description="Forecast hour offset (1-72)"),
    db: Session = Depends(get_db),
):
    """
    Returns the step-by-step iteration trace of the two-way aerosol-PBL feedback
    loop for a specific station and forecast hour.
    Visualizes raw (uncoupled) meteorology vs aerosol-corrected meteorology,
    demonstrating boundary layer suppression and convergence.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station {station_id} not found")

    # 1. Met forecast
    try:
        met_records = fetch_met_forecast(station_id)
    except Exception:
        met_records = _met_defaults(station_id)

    if not met_records or len(met_records) < hour_offset:
        met_records = _met_defaults(station_id)

    met_rec = met_records[hour_offset - 1]
    dt = met_rec.get("datetime")
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(tz=timezone.utc)

    # 2. Hotspots & plume contribution
    hotspots = fetch_fire_hotspots(settings.FIRMS_API_KEY)
    plume_contribs = estimate_plume_for_station(
        hotspots=hotspots,
        station_lat=station.lat,
        station_lon=station.lon,
        met_records=[met_rec],
    )
    plume_pm25 = plume_contribs[0]["plume_pm25_contrib"] if plume_contribs else 0.0

    # 3. Build context & model callables
    context = _build_coupling_context(db, station_id)
    pm_model_fn = make_pm_model_fn()
    o3_model_fn = make_o3_model_fn()

    # 4. Execute single coupling step with trace
    step: CoupledForecastStep = _run_single_step(
        station_id=station_id,
        hour_offset=hour_offset,
        dt=dt,
        met_raw=met_rec,
        plume_pm25=plume_pm25,
        context=context,
        pm_model_fn=pm_model_fn,
        o3_model_fn=o3_model_fn,
    )

    # PBL suppression percentage
    pbl_suppression_pct = (
        round(((step.pbl_height_raw - step.pbl_height_corrected) / max(step.pbl_height_raw, 1.0)) * 100, 2)
    )

    trace_schemas = [
        IterationTraceStepSchema(
            iteration=t["iteration"],
            pm25_estimate=t["pm25_estimate"],
            pm10_estimate=t.get("pm10_estimate"),
            pbl_corrected=t["pbl_corrected"],
            t_corrected=t["t_corrected"],
            inversion_score=t["inversion_score"],
            delta_pm25=t["delta_pm25"],
        )
        for t in step.iteration_trace
    ]

    physics_text = (
        "Two-way meteorology-chemistry feedback: High near-surface aerosol loading (PM2.5) "
        "scatters incoming shortwave solar radiation, reducing surface heating and temperature. "
        "This thermodynamic stabilization suppresses Planetary Boundary Layer (PBL) development, "
        "lowering the mixing volume. The compressed volume further concentrates trapped aerosols, "
        "producing an amplified pollution peak until the iterative feedback loop achieves convergence."
    )

    return FeedbackTraceResponseSchema(
        station_id=station.id,
        station_name=station.name,
        hour_offset=hour_offset,
        forecast_time=dt.isoformat() if hasattr(dt, "isoformat") else str(dt),
        converged=step.converged,
        iterations_run=step.iterations_run,
        final_pm25=step.pm25,
        final_pm10=step.pm10,
        final_o3=step.o3,
        pbl_height_raw=step.pbl_height_raw,
        pbl_height_corrected=step.pbl_height_corrected,
        pbl_suppression_pct=pbl_suppression_pct,
        temperature_raw=step.temperature_raw,
        temperature_corrected=step.temperature_corrected,
        uv_index_effective=step.uv_index_effective,
        inversion_score=step.inversion_score,
        inversion_category=step.inversion_category,
        iteration_trace=trace_schemas,
        physics_explanation=physics_text,
    )
