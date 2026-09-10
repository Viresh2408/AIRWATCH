"""
met_client.py — Open-Meteo forecast client for AirWatch Delhi NCR
SIH PS 26082: meteorological forcing for the two-way coupling engine.

Fetches per-station 72-hour forecast of:
  - boundary_layer_height   (metres)  — primary PBL input for coupling engine
  - windspeed_10m / winddirection_10m (surface wind)
  - windspeed_80m / winddirection_80m (upper-level; used for fire plume advection)
  - temperature_2m          (°C)
  - relativehumidity_2m     (%)
  - uv_index                (dimensionless) — O3 photochemistry driver
  - surface_pressure        (hPa)

All data is hourly resolution, 72 h ahead, returned as a list of dicts
with a 'datetime' (timezone-aware UTC) key.

API: https://api.open-meteo.com/v1/forecast  (free, no key required)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import requests

from app.core.config import (
    OPEN_METEO_FORECAST_URL,
    FORECAST_HORIZON_HOURS,
    DELHI_LAT_CENTER,
    DELHI_LON_CENTER,
)

logger = logging.getLogger(__name__)

# Hourly variables we request from Open-Meteo
OPEN_METEO_HOURLY_VARS: list[str] = [
    "boundary_layer_height",
    "windspeed_10m",
    "winddirection_10m",
    "windspeed_80m",
    "winddirection_80m",
    "temperature_2m",
    "relativehumidity_2m",
    "uv_index",
    "surface_pressure",
]

# Station lat/lon registry — kept in sync with live_ingestion.STATION_SENSORS
DELHI_NCR_STATION_COORDS: dict[int, tuple[float, float, str]] = {
    3409620: (28.6469, 77.3164, "Anand Vihar"),
    3409621: (28.6310, 77.2433, "ITO"),
    3409622: (28.6683, 77.1333, "Punjabi Bagh"),
    3409623: (28.5644, 77.1895, "RK Puram"),
    3409624: (28.5822, 77.0330, "Dwarka Sector 8"),
    3409625: (28.6270, 77.3640, "Noida Sector 62"),
    3409626: (28.4595, 77.0266, "Gurugram"),
}

_MET_CACHE: dict[str, list[dict[str, Any]]] = {}


def _cache_key(lat: float, lon: float, precision: int = 2) -> str:
    return f"{round(lat, precision)}_{round(lon, precision)}"


def fetch_met_forecast(
    lat: float,
    lon: Optional[float] = None,
    hours: int = FORECAST_HORIZON_HOURS,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """
    Fetch hourly meteorological forecast for a single lat/lon point or station ID.
    If lon is None, lat is treated as a station_id.
    """
    if lon is None:
        return fetch_met_for_station(int(lat), hours=hours)

    key = _cache_key(lat, lon)
    if use_cache and key in _MET_CACHE:
        logger.debug(f"[MET] Cache hit for ({lat:.2f}, {lon:.2f})")
        return _MET_CACHE[key]

    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(OPEN_METEO_HOURLY_VARS),
        "forecast_days": max(1, math.ceil(hours / 24)),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }

    try:
        resp = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"[MET] Open-Meteo fetch failed for ({lat},{lon}): {e}")
        return []

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    if not times:
        logger.warning(f"[MET] No hourly data returned for ({lat},{lon})")
        return []

    records: list[dict[str, Any]] = []
    for i, time_str in enumerate(times[:hours]):
        try:
            dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        ws10 = _safe_float(hourly.get("windspeed_10m", []), i)
        wd10 = _safe_float(hourly.get("winddirection_10m", []), i)
        ws80 = _safe_float(hourly.get("windspeed_80m", []), i)
        wd80 = _safe_float(hourly.get("winddirection_80m", []), i)

        record: dict[str, Any] = {
            "datetime": dt,
            "boundary_layer_height": _safe_float(hourly.get("boundary_layer_height", []), i),
            "windspeed_10m": ws10,
            "winddirection_10m": wd10,
            "windspeed_80m": ws80,
            "winddirection_80m": wd80,
            "temperature_2m": _safe_float(hourly.get("temperature_2m", []), i),
            "relativehumidity_2m": _safe_float(hourly.get("relativehumidity_2m", []), i),
            "uv_index": _safe_float(hourly.get("uv_index", []), i),
            "surface_pressure": _safe_float(hourly.get("surface_pressure", []), i),
            "wind_u_10m": _wind_u(ws10, wd10),
            "wind_v_10m": _wind_v(ws10, wd10),
            "wind_u_80m": _wind_u(ws80, wd80),
            "wind_v_80m": _wind_v(ws80, wd80),
        }
        records.append(record)

    if use_cache:
        _MET_CACHE[key] = records

    logger.info(
        f"[MET] Fetched {len(records)} hourly records for "
        f"({lat:.4f}, {lon:.4f}) — PBL range: {_pbl_range(records)}"
    )
    return records


def fetch_met_for_all_stations(hours: int = FORECAST_HORIZON_HOURS) -> dict[int, list[dict[str, Any]]]:
    """Fetches met forecast for every registered Delhi NCR station."""
    _MET_CACHE.clear()
    result: dict[int, list[dict[str, Any]]] = {}
    for station_id, (lat, lon, name) in DELHI_NCR_STATION_COORDS.items():
        logger.info(f"[MET] Fetching forecast for station {station_id} ({name})")
        result[station_id] = fetch_met_forecast(lat, lon, hours=hours)
    return result


def fetch_met_for_station(station_id: int, hours: int = FORECAST_HORIZON_HOURS) -> list[dict[str, Any]]:
    """Fetch met forecast for a single station by ID."""
    coords = DELHI_NCR_STATION_COORDS.get(station_id)
    if coords is None:
        logger.warning(
            f"[MET] Station {station_id} not in registry; "
            f"using domain centroid ({DELHI_LAT_CENTER}, {DELHI_LON_CENTER})"
        )
        return fetch_met_forecast(DELHI_LAT_CENTER, DELHI_LON_CENTER, hours=hours)
    lat, lon, _ = coords
    return fetch_met_forecast(lat, lon, hours=hours)


def clear_cache() -> None:
    """Clear the in-process met cache."""
    _MET_CACHE.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(lst: list, idx: int, default: float = 0.0) -> float:
    try:
        val = lst[idx]
        return float(val) if val is not None else default
    except (IndexError, TypeError, ValueError):
        return default


def _wind_u(speed: float, direction_deg: float) -> float:
    """Eastward (u) wind component. direction_deg: FROM which wind blows (0=N,90=E)."""
    return -speed * math.sin(math.radians(direction_deg))


def _wind_v(speed: float, direction_deg: float) -> float:
    """Northward (v) wind component."""
    return -speed * math.cos(math.radians(direction_deg))


def _pbl_range(records: list[dict]) -> str:
    pbls = [r["boundary_layer_height"] for r in records if r["boundary_layer_height"] > 0]
    if not pbls:
        return "N/A"
    return f"{min(pbls):.0f}-{max(pbls):.0f} m"
