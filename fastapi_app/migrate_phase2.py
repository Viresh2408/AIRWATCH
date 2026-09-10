"""
migrate_phase2.py — Idempotent ALTER TABLE migration for Phase 2 Prediction columns.

Run once against the live PostgreSQL DB to add the Phase 2 coupled-forecast columns
to the predictions table.  Safe to re-run: each column is added only if it does
not already exist.

Usage:
    cd AirWatch
    python fastapi_app/migrate_phase2.py

Requires DATABASE_URL in environment (or .env file).
"""

from __future__ import annotations

import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Check fastapi_app/.env")

engine = create_engine(DATABASE_URL)

# ---------------------------------------------------------------------------
# New Phase 2 columns: (column_name, DDL_type, default_expression)
# ---------------------------------------------------------------------------
PHASE2_COLUMNS = [
    # Core per-pollutant forecasts
    ("hour_offset",           "INTEGER",           "NULL"),
    ("predicted_pm25",        "DOUBLE PRECISION",  "NULL"),
    ("predicted_pm10",        "DOUBLE PRECISION",  "NULL"),
    ("predicted_o3",          "DOUBLE PRECISION",  "NULL"),
    # Confidence intervals
    ("pm25_lower",            "DOUBLE PRECISION",  "NULL"),
    ("pm25_upper",            "DOUBLE PRECISION",  "NULL"),
    ("pm10_lower",            "DOUBLE PRECISION",  "NULL"),
    ("pm10_upper",            "DOUBLE PRECISION",  "NULL"),
    # Coupling diagnostics
    ("inversion_score",       "DOUBLE PRECISION",  "NULL"),
    ("inversion_category",    "VARCHAR",           "NULL"),
    ("iterations_run",        "INTEGER",           "NULL"),
    ("converged",             "INTEGER",           "NULL"),
    ("plume_pm25_contrib",    "DOUBLE PRECISION",  "NULL"),
    ("pbl_height_corrected",  "DOUBLE PRECISION",  "NULL"),
    # MLOps
    ("model_version",         "VARCHAR",           "NULL"),
]

# New Phase 2 tables (create if not exist)
CREATE_MET_READINGS = """
CREATE TABLE IF NOT EXISTS met_readings (
    id              SERIAL PRIMARY KEY,
    station_id      INTEGER REFERENCES stations(id),
    datetime        TIMESTAMPTZ NOT NULL,
    pbl_height      DOUBLE PRECISION,
    windspeed_10m   DOUBLE PRECISION,
    winddirection_10m DOUBLE PRECISION,
    wind_u_10m      DOUBLE PRECISION,
    wind_v_10m      DOUBLE PRECISION,
    windspeed_80m   DOUBLE PRECISION,
    winddirection_80m DOUBLE PRECISION,
    wind_u_80m      DOUBLE PRECISION,
    wind_v_80m      DOUBLE PRECISION,
    temperature     DOUBLE PRECISION,
    relativehumidity DOUBLE PRECISION,
    uv_index        DOUBLE PRECISION,
    surface_pressure DOUBLE PRECISION,
    UNIQUE (station_id, datetime)
);
"""

CREATE_FIRE_HOTSPOTS = """
CREATE TABLE IF NOT EXISTS fire_hotspots (
    id          SERIAL PRIMARY KEY,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    frp         DOUBLE PRECISION,
    detected_at TIMESTAMPTZ NOT NULL,
    source      VARCHAR DEFAULT 'FIRMS_VIIRS'
);
"""

CREATE_INVERSION_INDEX = """
CREATE TABLE IF NOT EXISTS inversion_index (
    id          SERIAL PRIMARY KEY,
    station_id  INTEGER REFERENCES stations(id),
    datetime    TIMESTAMPTZ NOT NULL,
    score       DOUBLE PRECISION,
    category    VARCHAR,
    UNIQUE (station_id, datetime)
);
"""


def migrate() -> None:
    with engine.connect() as conn:
        insp = inspect(engine)

        # --- Alter predictions table ---
        existing_cols = {c["name"] for c in insp.get_columns("predictions")}
        added = []
        for col_name, col_type, default in PHASE2_COLUMNS:
            if col_name not in existing_cols:
                ddl = f"ALTER TABLE predictions ADD COLUMN {col_name} {col_type}"
                conn.execute(text(ddl))
                added.append(col_name)
                print(f"  [+] predictions.{col_name} ({col_type})")
            else:
                print(f"  [=] predictions.{col_name} already exists — skipped")

        # --- Create new tables ---
        for name, ddl in [
            ("met_readings",    CREATE_MET_READINGS),
            ("fire_hotspots",   CREATE_FIRE_HOTSPOTS),
            ("inversion_index", CREATE_INVERSION_INDEX),
        ]:
            conn.execute(text(ddl))
            print(f"  [t] {name} — ensured")

        conn.commit()

    print(f"\nMigration complete. {len(added)} column(s) added to predictions.")
    if added:
        print("  Added:", ", ".join(added))


if __name__ == "__main__":
    print("=== AirWatch Phase 2 DB Migration ===")
    migrate()
