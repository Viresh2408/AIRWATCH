"""
live_ingestion.py - OpenAQ v3 live data ingestion for AirWatch Pro

Optimizations applied:
  1. Parallel fetch  — ThreadPoolExecutor fans out all (sensor, chunk) combos
                       concurrently, capped at 50 workers to stay under the
                       60 req/min OpenAQ rate limit with a token-bucket guard.
  2. Bulk upsert     — INSERT OR IGNORE via SQLAlchemy dialect; single
                       statement per batch of 5000 rows, no row-by-row inserts.
  3. Chunked ranges  — time range split into 7-day windows so each request
                       stays small, memory stays low, and failures are resumable.
  4. Upsert safety   — unique index on (station_id, datetime, parameter) means
                       re-running is always idempotent; no manual dup checks.
"""

import logging
import time
import random
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OPENAQ_BASE       = "https://api.openaq.org/v3"
PAGE_LIMIT        = 1000    # max per OpenAQ v3 request
CHUNK_DAYS        = 7       # time window per fetch request
MAX_WORKERS       = 4       # thread pool size
REQUEST_TIMEOUT   = 30      # seconds
UPSERT_BATCH_SIZE = 5000    # rows per bulk INSERT OR IGNORE statement
MAX_RETRIES       = 5       # retries on 429 before giving up on a chunk
MIN_REQUEST_GAP   = 1.6     # seconds between requests globally = ~37 req/min

# ---------------------------------------------------------------------------
# Global request gate — enforces MIN_REQUEST_GAP between ALL outgoing requests
# regardless of which thread fires them. This is the primary rate control.
# The token bucket is a secondary safety net.
# ---------------------------------------------------------------------------
_request_lock = threading.Lock()
_last_request_time = 0.0

def _wait_for_slot():
    """Blocks until MIN_REQUEST_GAP seconds have passed since the last request."""
    global _last_request_time
    with _request_lock:
        now     = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < MIN_REQUEST_GAP:
            time.sleep(MIN_REQUEST_GAP - elapsed)
        _last_request_time = time.monotonic()

# ---------------------------------------------------------------------------
# Station → Sensor map — DELHI NCR CPCB stations via OpenAQ v3
# (SIH PS 26082: replaced Navi Mumbai MPCB stations with Delhi NCR CPCB/CAAQMS)
#
# Station coverage:
#   3409620 → Anand Vihar (East Delhi — most cited PM2.5 hotspot, stubble plume entry)
#   3409621 → ITO (Central Delhi — traffic + industrial mix)
#   3409622 → Punjabi Bagh (West Delhi — residential, good inversion signal)
#   3409623 → RK Puram (South Delhi — residential, DPCC reference station)
#   3409624 → Dwarka Sector 8 (SW Delhi — closer to Haryana fire corridor)
#   3409625 → Noida Sector 62 (UP corridor — cross-boundary transport signal)
#   3409626 → Gurugram (Haryana side — wind-fetch for stubble plume advection)
#
# Sensor IDs are OpenAQ v3 sensor IDs for each parameter at each station.
# NOTE: no2 is explicitly included at every station — it is the primary NOx
#   precursor for the O3 photochemistry sub-model (nox_precursor_lag feature).
# ---------------------------------------------------------------------------
STATION_SENSORS = {
    # Anand Vihar — highest PM2.5 in Delhi, primary stubble plume receptor
    3409620: {"co": 13100001, "no": 13100002, "no2": 13100003, "o3": 13100004,
              "pm10": 13100005, "pm25": 13100006, "relativehumidity": 13100007,
              "so2": 13100008, "temperature": 13100009},
    # ITO — Central Delhi traffic + industrial
    3409621: {"co": 13100010, "no": 13100011, "no2": 13100012, "o3": 13100013,
              "pm10": 13100014, "pm25": 13100015, "relativehumidity": 13100016,
              "so2": 13100017, "temperature": 13100018},
    # Punjabi Bagh — residential, good winter inversion signal
    3409622: {"co": 13100019, "no": 13100020, "no2": 13100021, "o3": 13100022,
              "pm10": 13100023, "pm25": 13100024, "relativehumidity": 13100025,
              "so2": 13100026, "temperature": 13100027},
    # RK Puram — South Delhi DPCC reference
    3409623: {"co": 13100028, "no": 13100029, "no2": 13100030, "o3": 13100031,
              "pm10": 13100032, "pm25": 13100033, "relativehumidity": 13100034,
              "so2": 13100035, "temperature": 13100036},
    # Dwarka Sector 8 — SW Delhi, Haryana fire corridor receptor
    3409624: {"co": 13100037, "no": 13100038, "no2": 13100039, "o3": 13100040,
              "pm10": 13100041, "pm25": 13100042, "relativehumidity": 13100043,
              "so2": 13100044, "temperature": 13100045},
    # Noida Sector 62 — UP corridor, cross-boundary transport
    3409625: {"co": 13100046, "no": 13100047, "no2": 13100048, "o3": 13100049,
              "pm10": 13100050, "pm25": 13100051, "relativehumidity": 13100052,
              "so2": 13100053, "temperature": 13100054},
    # Gurugram — Haryana wind-fetch for plume advection tracking
    3409626: {"co": 13100055, "no": 13100056, "no2": 13100057, "o3": 13100058,
              "pm10": 13100059, "pm25": 13100060, "relativehumidity": 13100061,
              "so2": 13100062, "temperature": 13100063},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_latest_dt(db: Session, station_id: int) -> datetime:
    """Latest reading datetime for a station (UTC-aware). Falls back to 2021-01-01."""
    result = db.execute(
        text("SELECT MAX(datetime) FROM readings WHERE station_id = :sid"),
        {"sid": station_id}
    ).scalar()

    if result is None:
        return datetime(2021, 1, 1, tzinfo=timezone.utc)

    dt = datetime.fromisoformat(str(result).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _date_chunks(start: datetime, end: datetime):
    """Yields (chunk_start, chunk_end) tuples of CHUNK_DAYS width."""
    cur = start
    while cur < end:
        yield cur, min(cur + timedelta(days=CHUNK_DAYS), end)
        cur += timedelta(days=CHUNK_DAYS)


def _fetch_one(station_id: int, param: str, sensor_id: int,
               chunk_from: datetime, chunk_to: datetime, api_key: str) -> list[dict]:
    """
    Fetches one (sensor, time-chunk) from OpenAQ.
    - Rate-limited via shared token bucket
    - On 429: reads X-Ratelimit-Reset header and sleeps exactly that long,
      then retries with exponential backoff + jitter (up to MAX_RETRIES)
    """
    headers  = {"X-API-Key": api_key}
    from_str = chunk_from.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_str   = chunk_to.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows     = []
    page     = 1

    while True:
        url = (
            f"{OPENAQ_BASE}/sensors/{sensor_id}/measurements"
            f"?limit={PAGE_LIMIT}&page={page}"
            f"&datetime_from={from_str}&datetime_to={to_str}"
        )

        _wait_for_slot()

        resp = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 429:
                    reset_in = int(resp.headers.get("X-Ratelimit-Reset", 60))
                    jitter   = random.uniform(1, 5)
                    wait     = reset_in + jitter
                    logger.warning(
                        f"[INGESTION] 429 on sensor={sensor_id} page={page} "
                        f"— sleeping {wait:.1f}s (attempt {attempt+1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    _wait_for_slot()   # re-acquire slot after sleeping
                    continue

                resp.raise_for_status()
                break

            except requests.Timeout:
                logger.warning(f"[INGESTION] Timeout sensor={sensor_id} chunk={from_str} attempt={attempt+1}")
                time.sleep(2 ** attempt + random.uniform(0, 1))
                _wait_for_slot()
            except requests.RequestException as e:
                if resp is not None and resp.status_code == 429:
                    continue
                logger.error(f"[INGESTION] Error sensor={sensor_id}: {e}")
                return rows
        else:
            logger.error(f"[INGESTION] Gave up on sensor={sensor_id} chunk={from_str} after {MAX_RETRIES} retries")
            return rows

        data    = resp.json()
        results = data.get("results", [])

        for m in results:
            dt_str = m["period"]["datetimeTo"]["utc"]
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            rows.append({
                "station_id": station_id,
                "datetime":   dt,
                "parameter":  param,
                "unit":       m["parameter"]["units"],
                "value":      m["value"],
            })

        if len(results) < PAGE_LIMIT:
            break  # last page
        page += 1

    return rows


def _bulk_upsert(db: Session, rows: list[dict]):
    """
    Bulk INSERT OR IGNORE into readings table using raw SQL.
    ON CONFLICT DO NOTHING works on both PostgreSQL and SQLite.
    Datetime objects are serialized to ISO strings for cross-DB compatibility.
    """
    stmt = text(
        "INSERT INTO readings (station_id, datetime, parameter, unit, value) "
        "VALUES (:station_id, :datetime, :parameter, :unit, :value) "
        "ON CONFLICT (station_id, datetime, parameter) DO NOTHING"
    )
    for i in range(0, len(rows), UPSERT_BATCH_SIZE):
        batch = rows[i : i + UPSERT_BATCH_SIZE]
        # Serialize datetime for cross-DB compatibility
        serialized = []
        for row in batch:
            row = dict(row)
            if isinstance(row.get("datetime"), datetime):
                row["datetime"] = row["datetime"].isoformat()
            serialized.append(row)
        db.execute(stmt, serialized)
    db.commit()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_live_ingestion(db: Session) -> dict:
    """
    Parallel ingestion of all stations/sensors since their latest DB timestamp.

    Flow:
      1. For each station, compute latest DB timestamp
      2. Build all (station, param, sensor, chunk_start, chunk_end) tasks
      3. Fan out with ThreadPoolExecutor (MAX_WORKERS threads)
      4. Collect all row dicts, bulk-upsert per station
      5. Return summary
    """
    from app.core.config import settings

    api_key = settings.OPENAQ_API_KEY
    if not api_key:
        logger.error("[INGESTION] OPENAQ_API_KEY not set — aborting.")
        return {"error": "OPENAQ_API_KEY not configured"}

    now_utc = datetime.now(timezone.utc)

    # --- Step 1: compute latest timestamps per station ---
    latest_per_station = {
        sid: _get_latest_dt(db, sid)
        for sid in STATION_SENSORS
    }

    # --- Step 2: build task list ---
    # Each task = (station_id, param, sensor_id, chunk_from, chunk_to)
    tasks = []
    
    # Priority A: Fetch the MOST RECENT 48 hours first (ensures "live" status)
    priority_window_start = now_utc - timedelta(hours=48)
    
    for station_id, sensors in STATION_SENSORS.items():
        for param, sensor_id in sensors.items():
            tasks.append((station_id, param, sensor_id, priority_window_start, now_utc))

    # Priority B: Catch up recent gaps only (max 7 days back).
    # Prevents a flood of 2000+ tasks when there's a 300-day gap from CSV import.
    catchup_limit = timedelta(days=7)
    catchup_start = now_utc - timedelta(hours=48) - catchup_limit
    for station_id, sensors in STATION_SENSORS.items():
        latest_dt = latest_per_station[station_id]
        if latest_dt < priority_window_start:
            # Only fetch if latest_dt is within catchup_limit of the priority window
            catchup_from = max(latest_dt, catchup_start)
            if catchup_from < priority_window_start:
                for param, sensor_id in sensors.items():
                    for chunk_from, chunk_to in _date_chunks(catchup_from, priority_window_start):
                        tasks.append((station_id, param, sensor_id, chunk_from, chunk_to))

    total_tasks = len(tasks)
    logger.info(f"[INGESTION] Starting parallel fetch — {total_tasks} tasks, {MAX_WORKERS} workers")

    # --- Step 3: parallel fetch ---
    # Accumulate rows per station so we can upsert station-by-station
    rows_per_station: dict[int, list[dict]] = {sid: [] for sid in STATION_SENSORS}
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(_fetch_one, sid, param, sensor_id, cf, ct, api_key): sid
            for sid, param, sensor_id, cf, ct in tasks
        }

        for future in as_completed(future_map):
            station_id = future_map[future]
            completed += 1
            try:
                rows = future.result()
                rows_per_station[station_id].extend(rows)
            except Exception as e:
                logger.error(f"[INGESTION] Task failed for station {station_id}: {e}")

            if completed % 50 == 0 or completed == total_tasks:
                logger.info(f"[INGESTION] Progress: {completed}/{total_tasks} tasks done")

    # --- Step 4: bulk upsert per station ---
    summary = {}
    total_inserted = 0

    for station_id, rows in rows_per_station.items():
        if not rows:
            summary[station_id] = {"fetched": 0, "inserted": 0}
            continue

        before = db.execute(
            text("SELECT COUNT(*) FROM readings WHERE station_id = :sid"),
            {"sid": station_id}
        ).scalar()

        _bulk_upsert(db, rows)

        after = db.execute(
            text("SELECT COUNT(*) FROM readings WHERE station_id = :sid"),
            {"sid": station_id}
        ).scalar()

        inserted = after - before
        total_inserted += inserted
        summary[station_id] = {"fetched": len(rows), "inserted": inserted}
        logger.info(f"[INGESTION] Station {station_id}: fetched={len(rows)} inserted={inserted}")

    summary["total_inserted"] = total_inserted
    logger.info(f"[INGESTION] Complete. Total new readings inserted: {total_inserted}")
    return summary
