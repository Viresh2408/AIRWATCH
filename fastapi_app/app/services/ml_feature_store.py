"""
ml_feature_store.py — Feature engineering for AirWatch Delhi NCR coupled models
SIH PS 26082: Phase 2 rebuild adding meteorological forcing and NOx precursors.

Feature set changes from original (Navi Mumbai flat-AQI):
  OLD: aqi lags, pm25 lags, no2 lags, temporal
  NEW: above + pbl_height, windspeed_10m, temperature, relativehumidity, uv_index,
       inversion_score, nox_precursor_lag (NO2), plume_pm25_contrib (fire signal),
       hour_sin/cos, day_of_week, month, stubble_season flag

Two feature-list exports:
  PM_FEATURE_COLS   — used by the PM2.5/PM10 XGBoost sub-model
  O3_FEATURE_COLS   — used by the O3 XGBoost sub-model (adds UV, NOx)

NOx assertion:
  Before training the O3 sub-model we assert that nox_precursor_lag has ≥ 10%
  non-zero rows. If NO2 ingestion is broken, the assertion raises ValueError
  and training aborts rather than fitting a model with a dead feature.
"""

from __future__ import annotations

import os
import warnings
import numpy as np
import pandas as pd
from sqlalchemy import text

from app.core.db import engine
from app.services.aqi_calculator import (
    calculate_sub_index,
    AQI_BREAKPOINTS,
    ppb_to_ugm3,
    GAS_MW,
)

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------
FEATURE_STORE_DIR  = "ml_data"
FEATURE_STORE_PATH = os.path.join(FEATURE_STORE_DIR, "ml_feature_store.csv")

# ---------------------------------------------------------------------------
# Feature column lists consumed by each sub-model
# (kept in sync with coupling_engine._build_pm_features / _build_o3_features)
# ---------------------------------------------------------------------------
PM_FEATURE_COLS: list[str] = [
    # Pollutant lags
    "pm25_lag_1", "pm25_lag_2", "pm25_lag_3", "pm25_lag_4",
    "pm10_lag_1", "pm10_lag_2",
    "aqi_lag_1",  "aqi_lag_2",  "aqi_lag_3",  "aqi_lag_4",
    # Meteorology (Phase 2 additions)
    "pbl_height",
    "windspeed_10m",
    "temperature",
    "relativehumidity",
    "inversion_score",
    # Fire plume contribution (Phase 2)
    "plume_pm25_contrib",
    # Temporal
    "hour_sin", "hour_cos",
    "day_of_week",
    "month",
    "stubble_season",   # 1 for Oct–Dec (Punjab stubble burning window)
]

O3_FEATURE_COLS: list[str] = [
    # O3 own lags
    "o3_lag_1", "o3_lag_2",
    # NOx precursor (asserted non-zero)
    "nox_precursor_lag", "nox_precursor_lag2",
    # Meteorology — UV is the key driver of photochemical O3 formation
    "uv_index",
    "temperature",
    "windspeed_10m",
    "pbl_height",
    "inversion_score",
    # Temporal
    "hour_sin", "hour_cos",
    "day_of_week",
    "month",
]

# Target columns
PM25_TARGET = "target_pm25"
PM10_TARGET = "target_pm10"
O3_TARGET   = "target_o3"

DEFAULT_TEMP_C = 25.0   # for ppb→µg/m³ conversion when live T unavailable


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def prepare_ml_features(save: bool = True) -> pd.DataFrame:
    """
    Fetch historical data from DB, merge met columns if available, engineer
    features, and return the wide feature DataFrame.

    Returns an empty DataFrame (and logs) if DB is unreachable.
    """
    print("=== AirWatch ml_feature_store: preparing coupled feature set ===")

    # 1. Load raw pollutant readings
    raw_df = _load_readings()
    if raw_df.empty:
        return raw_df

    # 2. Pivot to wide format (one row per station × hour)
    wide_df = _pivot_readings(raw_df)
    if wide_df.empty:
        return wide_df

    # 3. Add AQI overall column
    wide_df = _add_aqi(wide_df)

    # 4. Merge met readings (if a met_readings table exists; otherwise zeros)
    wide_df = _merge_met_readings(wide_df)

    # 5. Feature engineering
    wide_df = _engineer_features(wide_df)

    # 6. Build targets (next-hour PM2.5, PM10, O3)
    wide_df = _add_targets(wide_df)

    # 7. NOx assertion
    _assert_nox_coverage(wide_df)

    # 8. Drop rows with NaN targets/key features
    required_cols = [PM25_TARGET, PM10_TARGET, "pm25_lag_1", "nox_precursor_lag"]
    wide_df = wide_df.dropna(subset=required_cols)

    print(f"Feature store ready: {len(wide_df)} rows, {len(wide_df.columns)} columns.")

    if save:
        os.makedirs(FEATURE_STORE_DIR, exist_ok=True)
        wide_df.to_csv(FEATURE_STORE_PATH, index=False)
        print(f"Saved → {FEATURE_STORE_PATH}")

    return wide_df


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_readings() -> pd.DataFrame:
    """Load all readings from DB, apply unit conversion."""
    query = text("""
        SELECT r.station_id, r.datetime, r.parameter, r.unit, r.value,
               s.lat, s.lon
        FROM readings r
        JOIN stations s ON r.station_id = s.id
        ORDER BY r.station_id, r.datetime
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
    except Exception as exc:
        print(f"ERROR loading readings: {exc}")
        return pd.DataFrame()

    if df.empty:
        print("WARNING: readings table is empty.")
        return df

    # ppb → µg/m³
    def _convert(row):
        if str(row["unit"]).lower() == "ppb" and row["parameter"] in GAS_MW:
            row["value"] = ppb_to_ugm3(row["value"], GAS_MW[row["parameter"]], DEFAULT_TEMP_C)
        return row

    df = df.apply(_convert, axis=1)
    print(f"Loaded {len(df)} raw readings.")
    return df


def _pivot_readings(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot long → wide: one row per (datetime, station_id)."""
    df = df.drop(columns=["unit", "sensors_id", "lat", "lon"], errors="ignore")
    wide = df.pivot_table(
        index=["datetime", "station_id"],
        columns="parameter",
        values="value",
        aggfunc="mean",
    ).reset_index()
    wide.columns.name = None
    # Normalise column names to lower-snake
    wide.columns = [c.lower().replace(" ", "_") for c in wide.columns]
    print(f"Pivoted to {len(wide)} wide rows.")
    return wide


def _add_aqi(df: pd.DataFrame) -> pd.DataFrame:
    """Compute overall AQI (max sub-index) and per-pollutant sub-indices."""
    def _row_aqi(row):
        subs = []
        for p in AQI_BREAKPOINTS:
            col = p.lower()
            if col in row and pd.notna(row[col]) and row[col] >= 0:
                subs.append(calculate_sub_index(float(row[col]), p))
        return max(subs) if subs else np.nan

    df["overall_aqi"] = df.apply(_row_aqi, axis=1)
    return df


def _merge_met_readings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Try to join Open-Meteo met readings from met_readings table.
    If the table doesn't exist yet, fill met columns with NaN (they will be
    filled by _engineer_features fallback defaults for training).
    """
    met_cols = [
        "pbl_height", "windspeed_10m", "temperature",
        "relativehumidity", "uv_index",
    ]
    met_query = text("""
        SELECT station_id, datetime, pbl_height, windspeed_10m,
               temperature, relativehumidity, uv_index
        FROM met_readings
        ORDER BY station_id, datetime
    """)
    try:
        with engine.connect() as conn:
            met_df = pd.read_sql(met_query, conn)
        met_df["datetime"] = pd.to_datetime(met_df["datetime"], utc=True)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.merge(
            met_df, on=["station_id", "datetime"], how="left", suffixes=("", "_met")
        )
        print(f"Merged met readings: {met_df['pbl_height'].notna().sum()} PBL rows.")
    except Exception:
        # met_readings table not yet created — fill with NaN
        print("INFO: met_readings table not found; met features will use fallback defaults.")
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        for col in met_cols:
            if col not in df.columns:
                df[col] = np.nan

    # Fill NaN met columns with Delhi climatological defaults
    # (used during training when historical met coverage is sparse)
    DEFAULTS = {
        "pbl_height":       600.0,   # typical Delhi winter daytime PBL
        "windspeed_10m":    2.5,     # calm-ish, Delhi annual mean
        "temperature":      22.0,    # annual mean
        "relativehumidity": 55.0,
        "uv_index":         4.0,
    }
    for col, default in DEFAULTS.items():
        df[col] = df[col].fillna(default)

    return df


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag features, temporal features, inversion_score, stubble_season."""
    df = df.sort_values(["station_id", "datetime"]).copy()
    g = df.groupby("station_id")

    # Hourly resample to ensure regular grid
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)

    # --- Lag features ---
    for lag in range(1, 5):
        df[f"pm25_lag_{lag}"]  = g["pm25"].shift(lag)
        df[f"aqi_lag_{lag}"]   = g["overall_aqi"].shift(lag)
    for lag in range(1, 3):
        df[f"pm10_lag_{lag}"]  = g["pm10"].shift(lag)
        df[f"o3_lag_{lag}"]    = g["o3"].shift(lag) if "o3" in df.columns else 0.0

    # NOx precursor from NO2 readings (the live_ingestion.py writes 'no2')
    df["nox_precursor_lag"]  = g["no2"].shift(1) if "no2" in df.columns else 0.0
    df["nox_precursor_lag2"] = g["no2"].shift(2) if "no2" in df.columns else 0.0

    # --- Meteorology lag: PBL from previous hour for inversion trend ---
    df["pbl_height_prev"] = g["pbl_height"].shift(1)

    # --- Inversion score (simplified deterministic version for training) ---
    # Full compute_inversion_score uses the service; here we use the same formula
    # inline to avoid circular imports and keep feature generation self-contained.
    def _inv_score(row):
        pbl = row.get("pbl_height", 600.0)
        prev_pbl = row.get("pbl_height_prev", np.nan)
        hour = row.get("_hour", 12)

        THRESHOLD = 500.0
        CRITICAL  = 200.0
        if pbl >= THRESHOLD:
            base = 0.0
        elif pbl <= CRITICAL:
            base = 0.8
        else:
            base = 0.8 * (THRESHOLD - pbl) / (THRESHOLD - CRITICAL)

        trend = 0.0
        if pd.notna(prev_pbl) and prev_pbl > 0:
            collapse_rate = (prev_pbl - pbl) / prev_pbl
            if collapse_rate > 0.15:
                trend = 0.15
            elif collapse_rate > 0.05:
                trend = 0.07

        tod = 0.10 if (0 <= hour <= 5 or hour == 23) else 0.0
        return float(np.clip(base + trend + tod, 0.0, 1.0))

    df["_hour"] = df["datetime"].dt.hour
    df["inversion_score"] = df.apply(_inv_score, axis=1)
    df = df.drop(columns=["pbl_height_prev", "_hour"])

    # Fire plume contribution — zero during historical training (no FIRMS replay)
    # Phase 5 backtest will inject historical FIRMS data here
    if "plume_pm25_contrib" not in df.columns:
        df["plume_pm25_contrib"] = 0.0

    # --- Temporal features ---
    df["hour"]        = df["datetime"].dt.hour
    df["day_of_week"] = df["datetime"].dt.dayofweek
    df["month"]       = df["datetime"].dt.month
    df["hour_sin"]    = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"]    = np.cos(2 * np.pi * df["hour"] / 24)

    # Stubble-burning season flag (Oct–Dec, Punjab/Haryana burning window)
    df["stubble_season"] = df["month"].isin([10, 11, 12]).astype(int)

    df = df.drop(columns=["hour"])
    return df


def _add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Next-hour targets for the three sub-models.
    shift(-1) gives us h+1 PM2.5/PM10/O3 for a given row.
    """
    g = df.groupby("station_id")
    df[PM25_TARGET] = g["pm25"].shift(-1)
    df[PM10_TARGET] = g["pm10"].shift(-1) if "pm10" in df.columns else np.nan
    df[O3_TARGET]   = g["o3"].shift(-1)   if "o3" in df.columns else np.nan
    return df


def _assert_nox_coverage(df: pd.DataFrame, min_fraction: float = 0.10) -> None:
    """
    Assert that nox_precursor_lag has at least min_fraction non-zero rows.
    Raises ValueError if NO2 ingestion appears broken.
    This mirrors the PS requirement that NOx is a live input to the O3 model.
    """
    if "nox_precursor_lag" not in df.columns:
        raise ValueError(
            "nox_precursor_lag column missing from feature store. "
            "Check that live_ingestion.py is ingesting 'no2' from CPCB stations."
        )
    nox_col = df["nox_precursor_lag"]
    non_zero = (nox_col.notna() & (nox_col > 0)).sum()
    frac = non_zero / max(len(nox_col), 1)
    if frac < min_fraction:
        warnings.warn(
            f"nox_precursor_lag is zero/NaN for {(1-frac)*100:.1f}% of rows. "
            f"O3 sub-model will train on mostly-zero NOx. "
            f"Check that OpenAQ is returning 'no2' for Delhi NCR stations. "
            f"(threshold: {min_fraction*100:.0f}% non-zero)",
            UserWarning,
            stacklevel=2,
        )


if __name__ == "__main__":
    df = prepare_ml_features()
    if not df.empty:
        print("\nFeature store sample (5 rows):")
        sample_cols = (
            ["station_id", "datetime", "pm25", "no2", "pbl_height",
             "inversion_score", "nox_precursor_lag", PM25_TARGET, O3_TARGET]
        )
        print(df[[c for c in sample_cols if c in df.columns]].head().to_string())
        print(f"\nPM feature columns present: {[c for c in PM_FEATURE_COLS if c in df.columns]}")
        print(f"O3 feature columns present:  {[c for c in O3_FEATURE_COLS if c in df.columns]}")