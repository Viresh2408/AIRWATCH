"""
fire_plume_service.py — NASA FIRMS hotspot ingestion + Gaussian plume advection
SIH PS 26082: estimates stubble-burning fire plume arrival over Delhi NCR.

Methodology (judge-defensible, explicitly not HYSPLIT):
  1. Fetch VIIRS/MODIS active fire hotspots from NASA FIRMS API over the
     Punjab/Haryana/UP source region bbox for the last 7 days.
  2. For each hotspot, compute a straight-line advection path using the
     forecast wind vector (see wind-level note below).
  3. A Gaussian spreading cone (half-angle σ_θ ≈ 15°) distributes the
     plume contribution across Delhi NCR grid cells based on angular offset
     from the wind transport vector.
  4. Plume intensity scales with FIRMS Fire Radiative Power (FRP, MW),
     attenuates with distance^1.5 (simplified dry deposition + dilution),
     and is further modulated by the wind speed (slower wind → higher
     concentration per unit area).
  5. Output: per-station relative plume PM2.5 contribution [µg/m³ estimate]
     for each forecast timestep.

Wind-level scope decision (explicitly documented):
  We use the Open-Meteo 80m AGL wind field rather than 850 hPa pressure-level
  wind (~1500 m AGL). The original plan referenced 850 hPa because stubble-
  burning smoke is injected to the lower free troposphere and travels 200+ km
  at that level. However:
    (a) Open-Meteo's free-tier forecast API provides wind at 10m and 80m AGL
        but not 850 hPa pressure-level (that requires the ERA5 reanalysis
        endpoint, which has registration delays incompatible with the build
        window).
    (b) 80m AGL is still above the surface friction sub-layer (~10 m) and
        avoids the worst surface-drag bias, making it a reasonable hackathon-
        scale approximation.
  KNOWN LIMITATION: 80m wind can underestimate transport speed and direction
  aloft, particularly for long-range (>150 km) plumes during strong westerly
  flow aloft. This is explicitly disclosed in README.md ("Known Limitations"
  section) and in the /api/v1/coupling/plume-forecast response metadata.
  A production upgrade path would use ERA5 850 hPa u/v via the CDS API or
  request the `pressure_level` endpoint from Open-Meteo commercial tier.

This is deliberately simplified for a hackathon — we clearly label it
"straight-line advection with Gaussian spreading" in the README and API docs,
not a Lagrangian trajectory model.

FIRMS API key: free registration at https://firms.modaps.eosdis.nasa.gov/api/
If key is absent, falls back to zero-contribution (graceful degradation).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from app.core.config import (
    FIRE_SOURCE_LAT_MIN,
    FIRE_SOURCE_LAT_MAX,
    FIRE_SOURCE_LON_MIN,
    FIRE_SOURCE_LON_MAX,
    NASA_FIRMS_URL,
)
from app.services.met_client import DELHI_NCR_STATION_COORDS

logger = logging.getLogger(__name__)

# Gaussian half-angle spread of the plume cone (degrees)
PLUME_SPREAD_SIGMA_DEG: float = 15.0

# Distance attenuation exponent (1.5 is between 1/r dilution and 1/r^2 deposition)
DISTANCE_ATTENUATION_EXP: float = 1.5

# FRP → PM2.5 emission scaling constant (empirical, tunable in Phase 5)
# Units: µg/m³ per MW of FRP at 1 km distance with 1 m/s wind
FRP_TO_PM25_K: float = 0.5

# Maximum plausible single-source plume contribution (sanity cap)
MAX_PLUME_CONTRIB_UGM3: float = 150.0

# FIRMS data product — VIIRS SNPP (higher resolution than MODIS)
FIRMS_PRODUCT: str = "VIIRS_SNPP_NRT"

# Days of fire data to fetch (7 days catches accumulated burning seasons)
FIRMS_LOOKBACK_DAYS: int = 7


def fetch_fire_hotspots(api_key: str) -> list[dict[str, Any]]:
    """
    Fetch active fire hotspots from NASA FIRMS over the Punjab/Haryana/UP bbox.

    Returns list of dicts with keys:
        lat, lon, frp (Fire Radiative Power, MW), acq_datetime (UTC-aware)

    If api_key is empty or request fails, returns [] gracefully.
    """
    if not api_key:
        logger.warning("[FIRE] FIRMS_API_KEY not set — fire plume contribution will be zero.")
        return []

    # FIRMS CSV endpoint: /api/area/csv/{key}/{product}/{bbox}/{days}
    bbox = f"{FIRE_SOURCE_LON_MIN},{FIRE_SOURCE_LAT_MIN},{FIRE_SOURCE_LON_MAX},{FIRE_SOURCE_LAT_MAX}"
    url = f"{NASA_FIRMS_URL}/{api_key}/{FIRMS_PRODUCT}/{bbox}/{FIRMS_LOOKBACK_DAYS}"

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        text = resp.text
    except requests.RequestException as e:
        logger.error(f"[FIRE] FIRMS request failed: {e}")
        return []

    hotspots = _parse_firms_csv(text)
    logger.info(f"[FIRE] Fetched {len(hotspots)} hotspots from FIRMS (Punjab/Haryana/UP bbox)")
    return hotspots


def estimate_plume_for_station(
    hotspots: list[dict[str, Any]],
    station_lat: float,
    station_lon: float,
    met_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Estimate hourly plume PM2.5 contributions for a single station coordinate."""
    if not hotspots or not met_records:
        return [
            {"datetime": r.get("datetime"), "plume_pm25_contrib": 0.0, "hotspot_count": 0}
            for r in met_records
        ]

    hourly_contribs: list[dict[str, Any]] = []
    for met_rec in met_records:
        dt: datetime = met_rec.get("datetime")
        wind_u = met_rec.get("wind_u_80m", 0.0)
        wind_v = met_rec.get("wind_v_80m", 0.0)
        wind_speed = math.hypot(wind_u, wind_v)
        wind_dir_deg = (math.degrees(math.atan2(-wind_u, -wind_v)) + 360) % 360

        total_contrib = 0.0
        for hs in hotspots:
            contrib = _single_hotspot_contrib(
                hs_lat=hs["lat"],
                hs_lon=hs["lon"],
                hs_frp=hs.get("frp", 10.0),
                st_lat=station_lat,
                st_lon=station_lon,
                wind_dir_deg=wind_dir_deg,
                wind_speed=wind_speed,
            )
            total_contrib += contrib

        total_contrib = min(total_contrib, MAX_PLUME_CONTRIB_UGM3)
        hourly_contribs.append({
            "datetime": dt,
            "plume_pm25_contrib": round(total_contrib, 2),
            "hotspot_count": len(hotspots),
            "wind_dir_80m": round(wind_dir_deg, 1),
            "wind_speed_80m": round(wind_speed, 2),
        })
    return hourly_contribs


def estimate_plume_contributions(
    hotspots: list[dict[str, Any]] | None = None,
    met_records_by_station: dict[int, list[dict[str, Any]]] | None = None,
    *,
    station_lat: float | None = None,
    station_lon: float | None = None,
    met_records: list[dict[str, Any]] | None = None,
) -> Any:
    """
    Estimate plume PM2.5 contribution from fire hotspots.

    Supports two calling conventions:
      1. Single-station:
         estimate_plume_contributions(
             station_lat=..., station_lon=..., met_records=..., hotspots=None
         ) -> list[dict[str, Any]]

      2. Multi-station (dict-based):
         estimate_plume_contributions(
             hotspots, met_records_by_station
         ) -> dict[int, list[dict[str, Any]]]
    """
    # Check if called for a single station via keyword args
    if station_lat is not None and station_lon is not None and met_records is not None:
        if hotspots is None:
            from app.core.config import settings
            hotspots = fetch_fire_hotspots(settings.FIRMS_API_KEY)
        return estimate_plume_for_station(hotspots, station_lat, station_lon, met_records)

    # Multi-station mode
    if met_records_by_station is None:
        met_records_by_station = {}
    if hotspots is None:
        hotspots = []

    if not hotspots:
        result: dict[int, list[dict[str, Any]]] = {}
        for sid, met_recs in met_records_by_station.items():
            result[sid] = [
                {"datetime": r.get("datetime"), "plume_pm25_contrib": 0.0, "hotspot_count": 0}
                for r in met_recs
            ]
        return result

    result = {}
    for station_id, met_recs in met_records_by_station.items():
        coords = DELHI_NCR_STATION_COORDS.get(station_id)
        if coords is None:
            continue
        st_lat, st_lon, st_name = coords
        hourly_contribs = estimate_plume_for_station(hotspots, st_lat, st_lon, met_recs)
        result[station_id] = hourly_contribs
        peak = max((h["plume_pm25_contrib"] for h in hourly_contribs), default=0)
        logger.info(f"[FIRE] {st_name} (ID {station_id}): peak plume contrib = {peak:.1f} µg/m³")

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _single_hotspot_contrib(
    hs_lat: float, hs_lon: float, hs_frp: float,
    st_lat: float, st_lon: float,
    wind_dir_deg: float, wind_speed: float,
) -> float:
    """
    Estimate PM2.5 contribution at a station from a single fire hotspot.

    Gaussian plume cone model (straight-line advection):
      - Only contributes if station is downwind (angular offset < 3σ)
      - Intensity ~ FRP / (distance^1.5 * max(wind_speed, 0.5))
      - Angular attenuation: Gaussian weight exp(-θ²/2σ²)
    """
    if hs_frp <= 0:
        return 0.0

    # Distance from hotspot to station (km)
    dist_km = _haversine_km(hs_lat, hs_lon, st_lat, st_lon)
    if dist_km < 1.0:
        dist_km = 1.0  # avoid divide-by-zero for co-located points

    # Bearing from hotspot → station (degrees)
    bearing_to_station = _bearing_deg(hs_lat, hs_lon, st_lat, st_lon)

    # Angular offset between wind transport direction (downwind) and hotspot→station bearing
    # Wind direction FROM (met convention) → transport direction TO = wind_dir + 180
    transport_dir = (wind_dir_deg + 180) % 360
    angular_offset = _angle_diff(bearing_to_station, transport_dir)

    # Gaussian angular weight
    sigma = PLUME_SPREAD_SIGMA_DEG
    if angular_offset > 3 * sigma:
        return 0.0   # outside plume cone
    angular_weight = math.exp(-(angular_offset ** 2) / (2 * sigma ** 2))

    # Intensity formula
    effective_wind = max(wind_speed, 0.5)   # prevent singularity at calm wind
    raw_contrib = (
        FRP_TO_PM25_K * hs_frp * angular_weight
        / (dist_km ** DISTANCE_ATTENUATION_EXP * effective_wind)
    )
    return raw_contrib


def _parse_firms_csv(text: str) -> list[dict[str, Any]]:
    """Parse FIRMS CSV response into list of hotspot dicts."""
    hotspots: list[dict[str, Any]] = []
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return hotspots

    # FIRMS CSV header (VIIRS_SNPP): latitude,longitude,bright_ti4,...,frp,...
    header = [h.strip().lower() for h in lines[0].split(",")]
    lat_idx = _find_col(header, ["latitude", "lat"])
    lon_idx = _find_col(header, ["longitude", "lon"])
    frp_idx = _find_col(header, ["frp"])
    date_idx = _find_col(header, ["acq_date"])
    time_idx = _find_col(header, ["acq_time"])

    for line in lines[1:]:
        cols = line.split(",")
        try:
            lat = float(cols[lat_idx])
            lon = float(cols[lon_idx])
            frp = float(cols[frp_idx]) if frp_idx is not None else 10.0

            # Parse acquisition datetime (FIRMS format: YYYY-MM-DD, HHMM)
            acq_dt = None
            if date_idx is not None:
                date_str = cols[date_idx].strip()
                time_str = cols[time_idx].strip().zfill(4) if time_idx is not None else "0000"
                acq_dt = datetime.strptime(
                    f"{date_str} {time_str}", "%Y-%m-%d %H%M"
                ).replace(tzinfo=timezone.utc)

            hotspots.append({"lat": lat, "lon": lon, "frp": frp, "acq_datetime": acq_dt})
        except (IndexError, ValueError):
            continue

    return hotspots


def _find_col(header: list[str], names: list[str]) -> int | None:
    for name in names:
        if name in header:
            return header.index(name)
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Forward azimuth (degrees, 0=N) from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _angle_diff(a: float, b: float) -> float:
    """Smallest absolute angular difference between two bearings (degrees)."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff
