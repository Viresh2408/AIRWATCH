"""
prediction_service.py — 72-hour coupled AQI forecast orchestrator
SIH PS 26082: Phase 2 — routes through coupling_engine instead of
flat XGBoost regressor.

Flow:
  1. Seed CouplingContext from last 4 observed readings per station (DB)
  2. Fetch 72h met forecast from met_client
  3. Fetch fire plume contributions from fire_plume_service
  4. Run coupling_engine.run_coupled_forecast() → list[CoupledForecastStep]
  5. Persist each step as a Prediction row (with coupling diagnostics)

Graceful degradation:
  - If met fetch fails → coupling engine uses met_raw with hardcoded Delhi defaults
  - If FIRMS fetch fails → plume_records = [] (zero-contribution)
  - If no trained model → ml_pipeline fallback callables (persistence / diurnal)
  - If DB has no lag data for a station → CouplingContext defaults (80 µg/m³ PM2.5)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.aqi import Prediction, Station
from app.services.aqi_calculator import calculate_sub_index, AQI_BREAKPOINTS
from app.services.coupling_engine import CouplingContext, run_coupled_forecast
from app.services.met_client import fetch_met_forecast
from app.services.fire_plume_service import estimate_plume_contributions
from app.services.ml_pipeline import make_pm_model_fn, make_o3_model_fn

logger = logging.getLogger(__name__)

MODEL_VERSION = "coupled_xgb_v1.0"
FORECAST_HORIZON_HOURS = 72

# Default lag values when DB has no readings for a station (first-run fallback)
_DEFAULT_PM25 = 80.0
_DEFAULT_PM10 = 160.0
_DEFAULT_O3   = 50.0
_DEFAULT_NO2  = 50.0
_DEFAULT_AQI  = 150.0

# Number of prior hours needed to seed the 4-lag context window
_LAG_WINDOW = 4


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate_and_save_predictions(db: Session) -> int:
    """
    Generate 72-hour coupled forecasts for all known stations and persist to DB.

    Returns:
        Total number of Prediction rows inserted.
    """
    logger.info("=== Starting 72h coupled forecast run ===")

    pm_model_fn = make_pm_model_fn()
    o3_model_fn = make_o3_model_fn()

    stations = db.query(Station).all()
    if not stations:
        logger.warning("No stations in DB — nothing to forecast.")
        return 0

    # Purge stale predictions older than 30 days
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
    deleted = db.query(Prediction).filter(Prediction.prediction_time < cutoff).delete()
    logger.info("Purged %d stale prediction rows.", deleted)

    total_saved = 0

    for station in stations:
        try:
            n = _forecast_station(db, station, pm_model_fn, o3_model_fn)
            total_saved += n
        except Exception as exc:
            logger.error(
                "Forecast failed for station %d (%s): %s",
                station.id, station.name, exc, exc_info=True,
            )
            # Continue with other stations — don't abort the whole run
            continue

    db.commit()
    logger.info(
        "=== Forecast run complete: %d rows saved for %d stations ===",
        total_saved, len(stations),
    )
    return total_saved


# ---------------------------------------------------------------------------
# Per-station forecast
# ---------------------------------------------------------------------------

def _forecast_station(
    db: Session,
    station: Station,
    pm_model_fn,
    o3_model_fn,
) -> int:
    """
    Run the full coupling pipeline for one station and bulk-insert results.
    Returns number of rows inserted.
    """
    logger.info("Forecasting station %d (%s)...", station.id, station.name)

    # 1. Seed context from DB
    context = _build_coupling_context(db, station.id)

    # 2. Met forecast (72h)
    try:
        met_records = fetch_met_forecast(station.id)
    except Exception as exc:
        logger.warning(
            "Met fetch failed for station %d: %s — using safe defaults.", station.id, exc
        )
        met_records = _met_defaults(station.id)

    if not met_records:
        logger.warning("Empty met records for station %d — skipping.", station.id)
        return 0

    # 3. Fire plume contributions
    try:
        plume_records = estimate_plume_contributions(
            station_lat=station.lat,
            station_lon=station.lon,
            met_records=met_records,
        )
    except Exception as exc:
        logger.warning("Plume fetch failed for station %d: %s", station.id, exc)
        plume_records = []

    # 4. Run coupling engine
    steps = run_coupled_forecast(
        station_id=station.id,
        met_records=met_records,
        plume_records=plume_records,
        initial_context=context,
        pm_model_fn=pm_model_fn,
        o3_model_fn=o3_model_fn,
    )

    # 5. Persist
    base_time = met_records[0]["datetime"] - timedelta(hours=1)
    rows = []
    for step in steps:
        aqi = _compute_aqi(step.pm25, step.pm10, step.o3)
        row = Prediction(
            station_id          = station.id,
            prediction_time     = base_time + timedelta(hours=step.hour_offset),
            hour_offset         = step.hour_offset,
            predicted_aqi       = aqi,
            predicted_pm25      = round(step.pm25, 2),
            predicted_pm10      = round(step.pm10, 2),
            predicted_o3        = round(step.o3, 2),
            pm25_lower          = round(step.pm25_lower, 2),
            pm25_upper          = round(step.pm25_upper, 2),
            # PM10 CI derived from PM2.5 CI via the same 1.8× ratio used in training
            pm10_lower          = round(step.pm25_lower * 1.8, 2),
            pm10_upper          = round(step.pm25_upper * 1.8, 2),
            inversion_score     = round(step.inversion_score, 4),
            inversion_category  = step.inversion_category,
            iterations_run      = step.iterations_run,
            converged           = int(step.converged),
            plume_pm25_contrib  = round(step.plume_pm25_contrib, 2),
            pbl_height_corrected= round(step.pbl_height_corrected, 1),
            model_version       = MODEL_VERSION,
        )
        rows.append(row)

    db.bulk_save_objects(rows)
    logger.info("  Inserted %d prediction rows for station %d.", len(rows), station.id)
    return len(rows)


# ---------------------------------------------------------------------------
# Context seeding from DB
# ---------------------------------------------------------------------------

def _build_coupling_context(db: Session, station_id: int) -> CouplingContext:
    """
    Build a CouplingContext from the most recent DB readings for a station.

    Queries the readings table for the last _LAG_WINDOW hourly readings and
    constructs the lag lists for PM2.5, PM10, O3, NO2, and overall AQI.
    Falls back to defaults if no data exists.
    """
    query = text("""
        SELECT datetime, parameter, value
        FROM readings
        WHERE station_id = :sid
          AND datetime >= :cutoff
        ORDER BY datetime DESC
        LIMIT 200
    """)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_LAG_WINDOW + 2)

    try:
        with db.bind.connect() as conn:
            rows = conn.execute(query, {"sid": station_id, "cutoff": cutoff}).fetchall()
    except Exception as exc:
        logger.warning(
            "DB lag query failed for station %d: %s — using defaults.", station_id, exc
        )
        rows = []

    if not rows:
        logger.debug("No recent readings for station %d; using defaults.", station_id)
        return _default_context(station_id)

    # Pivot to {parameter: [value_t, value_t-1, ...]} (most-recent first)
    from collections import defaultdict
    lags: dict[str, list[float]] = defaultdict(list)
    for dt, param, val in rows:
        if param in ("pm25", "pm10", "o3", "no2", "overall_aqi") and val is not None:
            lags[param].append(float(val))

    def _take(key: str, default: float) -> list[float]:
        vals = lags.get(key, [])[:_LAG_WINDOW]
        while len(vals) < _LAG_WINDOW:
            vals.append(default)
        return vals

    return CouplingContext(
        station_id      = station_id,
        prior_pm25_lags = _take("pm25",       _DEFAULT_PM25),
        prior_pm10_lags = _take("pm10",       _DEFAULT_PM10),
        prior_o3_lags   = _take("o3",         _DEFAULT_O3),
        prior_no2_lags  = _take("no2",        _DEFAULT_NO2),
        prior_aqi_lags  = _take("overall_aqi", _DEFAULT_AQI),
    )


def _default_context(station_id: int) -> CouplingContext:
    """Delhi seasonal average defaults when no DB data exists."""
    return CouplingContext(
        station_id      = station_id,
        prior_pm25_lags = [_DEFAULT_PM25] * _LAG_WINDOW,
        prior_pm10_lags = [_DEFAULT_PM10] * _LAG_WINDOW,
        prior_o3_lags   = [_DEFAULT_O3]   * _LAG_WINDOW,
        prior_no2_lags  = [_DEFAULT_NO2]  * _LAG_WINDOW,
        prior_aqi_lags  = [_DEFAULT_AQI]  * _LAG_WINDOW,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_aqi(pm25: float, pm10: float, o3: float) -> int:
    """
    CPCB AQI: maximum sub-index across PM2.5, PM10, O3.
    Mirrors aqi_calculator.get_aqi_category() logic.
    """
    sub_indices = []
    for param, val in [("pm25", pm25), ("pm10", pm10), ("o3", o3)]:
        if val > 0:
            sub_indices.append(calculate_sub_index(val, param))
    return int(max(sub_indices)) if sub_indices else 0


def _met_defaults(station_id: int) -> list[dict]:
    """
    Emergency fallback met records (72h of Delhi winter climatology).
    Used only if Open-Meteo is unreachable.
    """
    from app.services.met_client import DELHI_NCR_STATION_COORDS
    import math

    coords = DELHI_NCR_STATION_COORDS.get(station_id, (28.65, 77.23, "Unknown"))
    lat, lon = coords[0], coords[1]   # tuple: (lat, lon, name)
    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)

    records = []
    for h in range(FORECAST_HORIZON_HOURS):
        dt = now + timedelta(hours=h)
        hour = dt.hour
        # Simple diurnal PBL: low at night (200m), peaks mid-afternoon (800m)
        pbl = 200.0 + 600.0 * max(0.0, math.sin(math.pi * (hour - 6) / 12))
        records.append({
            "datetime":              dt,
            "station_id":            station_id,
            "lat":                   lat,
            "lon":                   lon,
            "boundary_layer_height": pbl,
            "windspeed_10m":         2.5,
            "winddirection_10m":     315.0,    # NW typical Nov–Dec
            "wind_u_10m":            -1.77,
            "wind_v_10m":            1.77,
            "windspeed_80m":         4.0,
            "winddirection_80m":     315.0,
            "wind_u_80m":            -2.83,
            "wind_v_80m":            2.83,
            "temperature_2m":        15.0,
            "relativehumidity_2m":   65.0,
            "uv_index":              max(0.0, 6.0 * math.sin(math.pi * (hour - 6) / 12)),
            "surface_pressure":      1013.0,
        })
    return records