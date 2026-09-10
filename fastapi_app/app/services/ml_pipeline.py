"""
ml_pipeline.py — Dual XGBoost sub-model training for AirWatch Delhi NCR
SIH PS 26082: Phase 2 Chemistry/ML Model Rebuild

Two sub-models replace the original single flat-AQI regressor:
  1. PM Sub-model  — predicts (PM2.5, PM10) jointly
     Features: pollutant lags + met forcing (PBL, wind, T, RH, inversion_score,
               plume_pm25_contrib) + temporal
     Why separate from O3: PM2.5/PM10 in Delhi are accumulation-mode aerosols
     dominated by transport + trapping (strong PBL dependence). O3 is a secondary
     photochemical pollutant driven by NOx × UV; its physics is orthogonal.

  2. O3 Sub-model  — predicts O3 (µg/m³)
     Features: O3 lags + NOx precursor lags + UV index + temperature + wind + temporal

Model artifacts saved to ml_models/:
  pm_model.joblib   → (xgb_pm25, xgb_pm10, scaler_pm, pm_feature_list)
  o3_model.joblib   → (xgb_o3,              scaler_o3, o3_feature_list)

Callable interface (used by coupling_engine):
  make_pm_model_fn(model_dir)  → Callable[[dict], tuple[float, float]]
  make_o3_model_fn(model_dir)  → Callable[[dict], float]
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import Callable

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from app.services.ml_feature_store import (
    FEATURE_STORE_PATH,
    PM_FEATURE_COLS,
    O3_FEATURE_COLS,
    PM25_TARGET,
    PM10_TARGET,
    O3_TARGET,
    _assert_nox_coverage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MODEL_DIR    = "ml_models"
PM_MODEL_PATH = os.path.join(MODEL_DIR, "pm_model.joblib")
O3_MODEL_PATH = os.path.join(MODEL_DIR, "o3_model.joblib")

# Legacy path (old single-model pipeline) — kept for graceful fallback
LEGACY_MODEL_PATH = os.path.join(MODEL_DIR, "xgb_tuned_aqi_model.joblib")

# ---------------------------------------------------------------------------
# XGBoost hyperparameters
# Deliberately conservative for a dataset of unknown size:
#   - max_depth=6 avoids overfitting on small historical windows
#   - n_estimators=400 + early_stopping gives enough capacity
#   - colsample_bytree=0.8 adds regularisation without reducing feature coverage
# ---------------------------------------------------------------------------
PM_XGB_PARAMS = dict(
    n_estimators=400,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="reg:squarederror",
    n_jobs=-1,
    random_state=42,
    early_stopping_rounds=30,
    eval_metric="mae",
)

O3_XGB_PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=5,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="reg:squarederror",
    n_jobs=-1,
    random_state=42,
    early_stopping_rounds=20,
    eval_metric="mae",
)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_models(df: pd.DataFrame | None = None) -> dict:
    """
    Train both sub-models and persist artifacts.

    Args:
        df: Optional pre-loaded feature DataFrame. If None, loads from
            FEATURE_STORE_PATH (run ml_feature_store.py first).

    Returns:
        Dict with evaluation metrics for both models.
    """
    if df is None:
        if not os.path.exists(FEATURE_STORE_PATH):
            raise FileNotFoundError(
                f"Feature store not found at {FEATURE_STORE_PATH}. "
                "Run: python -m app.services.ml_feature_store"
            )
        df = pd.read_csv(FEATURE_STORE_PATH)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)

    os.makedirs(MODEL_DIR, exist_ok=True)

    metrics = {}
    metrics["pm"] = _train_pm_model(df)
    metrics["o3"] = _train_o3_model(df)

    print("\n=== Phase 2 Training Complete ===")
    for sub, m in metrics.items():
        print(f"  {sub.upper()}: MAE={m.get('mae', 'n/a'):.2f}  R²={m.get('r2', 'n/a'):.4f}")
    return metrics


def _train_pm_model(df: pd.DataFrame) -> dict:
    """Train PM2.5 and PM10 regressors (share scaler, separate estimators)."""
    print("\n--- Training PM2.5 / PM10 sub-model ---")

    # Drop rows missing either target or any required feature
    req = [PM25_TARGET] + [c for c in PM_FEATURE_COLS if c in df.columns]
    pm_df = df.dropna(subset=[PM25_TARGET]).copy()

    # Fill remaining NaN features with column medians (avoids imputer dependency)
    for col in PM_FEATURE_COLS:
        if col in pm_df.columns:
            pm_df[col] = pm_df[col].fillna(pm_df[col].median())
        else:
            pm_df[col] = 0.0
            warnings.warn(f"PM feature '{col}' not found; filled with 0.", stacklevel=2)

    X = pm_df[PM_FEATURE_COLS].values
    y_pm25 = pm_df[PM25_TARGET].values
    y_pm10 = pm_df[PM10_TARGET].fillna(pm_df[PM25_TARGET] * 1.8).values  # heuristic if missing

    # Temporal split (no shuffle — time-series)
    split = int(len(X) * 0.8)
    X_tr, X_te = X[:split], X[split:]
    y25_tr, y25_te = y_pm25[:split], y_pm25[split:]
    y10_tr, y10_te = y_pm10[:split], y_pm10[split:]

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    # PM2.5 model
    xgb_pm25 = xgb.XGBRegressor(**PM_XGB_PARAMS)
    xgb_pm25.fit(
        X_tr_s, y25_tr,
        eval_set=[(X_te_s, y25_te)],
        verbose=False,
    )
    pm25_pred = xgb_pm25.predict(X_te_s)
    pm25_pred = np.clip(pm25_pred, 0, None)

    # PM10 model
    xgb_pm10 = xgb.XGBRegressor(**PM_XGB_PARAMS)
    xgb_pm10.fit(
        X_tr_s, y10_tr,
        eval_set=[(X_te_s, y10_te)],
        verbose=False,
    )
    pm10_pred = xgb_pm10.predict(X_te_s)
    pm10_pred = np.clip(pm10_pred, 0, None)

    mae = mean_absolute_error(y25_te, pm25_pred)
    r2  = r2_score(y25_te, pm25_pred)
    print(f"  PM2.5 MAE={mae:.2f} ug/m3   R2={r2:.4f}")
    print(f"  PM10  MAE={mean_absolute_error(y10_te, pm10_pred):.2f} ug/m3")

    joblib.dump((xgb_pm25, xgb_pm10, scaler, PM_FEATURE_COLS), PM_MODEL_PATH)
    print(f"  Saved -> {PM_MODEL_PATH}")
    return {"mae": mae, "r2": r2, "n_train": split, "n_test": len(X_te)}


def _train_o3_model(df: pd.DataFrame) -> dict:
    """Train O3 regressor using NOx + UV + met features."""
    print("\n--- Training O3 sub-model ---")

    # NOx assertion before training — O3 model is meaningless without NOx signal
    _assert_nox_coverage(df, min_fraction=0.10)

    o3_df = df.dropna(subset=[O3_TARGET]).copy()
    if len(o3_df) < 50:
        warnings.warn(
            f"Only {len(o3_df)} rows with valid O3 target. "
            "O3 model may underfit. Ensure ozone readings are ingested.",
            UserWarning, stacklevel=2,
        )

    for col in O3_FEATURE_COLS:
        if col in o3_df.columns:
            o3_df[col] = o3_df[col].fillna(o3_df[col].median())
        else:
            o3_df[col] = 0.0
            warnings.warn(f"O3 feature '{col}' not found; filled with 0.", stacklevel=2)

    X = o3_df[O3_FEATURE_COLS].values
    y = o3_df[O3_TARGET].values

    split = int(len(X) * 0.8)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    xgb_o3 = xgb.XGBRegressor(**O3_XGB_PARAMS)

    if len(X_te) >= 10:
        xgb_o3.fit(X_tr_s, y_tr, eval_set=[(X_te_s, y_te)], verbose=False)
    else:
        # Too little test data for early stopping — train without eval_set
        params_no_early = {k: v for k, v in O3_XGB_PARAMS.items()
                           if k != "early_stopping_rounds"}
        xgb_o3 = xgb.XGBRegressor(**params_no_early)
        xgb_o3.fit(X_tr_s, y_tr, verbose=False)

    o3_pred = np.clip(xgb_o3.predict(X_te_s), 0, None)
    mae = mean_absolute_error(y_te, o3_pred) if len(y_te) > 0 else float("nan")
    r2  = r2_score(y_te, o3_pred) if len(y_te) > 1 else float("nan")
    print(f"  O3 MAE={mae:.2f} ug/m3   R2={r2:.4f}")

    joblib.dump((xgb_o3, scaler, O3_FEATURE_COLS), O3_MODEL_PATH)
    print(f"  Saved -> {O3_MODEL_PATH}")
    return {"mae": mae, "r2": r2, "n_train": split, "n_test": len(X_te)}


# ---------------------------------------------------------------------------
# Callable interface for coupling_engine
# ---------------------------------------------------------------------------

def make_pm_model_fn(model_dir: str = MODEL_DIR) -> Callable[[dict], tuple[float, float]]:
    """
    Load the trained PM sub-model and return a callable:
      fn(features: dict) -> (pm25_µg/m³, pm10_µg/m³)

    The callable is passed directly to coupling_engine.run_coupled_forecast()
    as pm_model_fn.

    Falls back to a simple persistence model (last-known PM2.5) if no trained
    model file exists, logging a warning.
    """
    path = os.path.join(model_dir, "pm_model.joblib")
    if not os.path.exists(path):
        logger.warning(
            "PM model artifact not found at %s. "
            "Using persistence fallback (pm25_lag_1, pm10_lag_1). "
            "Train first: python -m app.services.ml_pipeline",
            path,
        )
        def _persistence(features: dict) -> tuple[float, float]:
            pm25 = max(float(features.get("pm25_lag_1", 80.0)), 0.0)
            pm10 = max(float(features.get("pm10_lag_1", 150.0)), 0.0)
            return pm25, pm10
        return _persistence

    xgb_pm25, xgb_pm10, scaler, feature_cols = joblib.load(path)
    logger.info("Loaded PM model from %s", path)

    def _pm_fn(features: dict) -> tuple[float, float]:
        row = _dict_to_row(features, feature_cols)
        row_s = scaler.transform(row)
        pm25 = float(np.clip(xgb_pm25.predict(row_s)[0], 0, None))
        pm10 = float(np.clip(xgb_pm10.predict(row_s)[0], 0, None))
        # PM10 must be ≥ PM2.5 (physical constraint)
        pm10 = max(pm10, pm25)
        return pm25, pm10

    return _pm_fn


def make_o3_model_fn(model_dir: str = MODEL_DIR) -> Callable[[dict], float]:
    """
    Load the trained O3 sub-model and return a callable:
      fn(features: dict) -> o3_µg/m³

    Falls back to a simple climatological diurnal O3 estimate if no model
    file exists (UV-driven: O3 ∝ sin(hour_rad) clamped to [20, 80] µg/m³).
    """
    path = os.path.join(model_dir, "o3_model.joblib")
    if not os.path.exists(path):
        logger.warning(
            "O3 model artifact not found at %s. "
            "Using diurnal fallback (UV-proxy). "
            "Train first: python -m app.services.ml_pipeline",
            path,
        )
        def _diurnal_o3(features: dict) -> float:
            hour_sin = float(features.get("hour_sin", 0.0))
            uv       = float(features.get("uv_index", 4.0))
            # O3 peaks ~14:00 local; hour_sin peaks at ~06:00 UTC = ~11:30 IST
            base = 40.0 + 30.0 * max(0.0, hour_sin) * (uv / 5.0)
            return float(np.clip(base, 10.0, 120.0))
        return _diurnal_o3

    xgb_o3, scaler, feature_cols = joblib.load(path)
    logger.info("Loaded O3 model from %s", path)

    def _o3_fn(features: dict) -> float:
        row = _dict_to_row(features, feature_cols)
        row_s = scaler.transform(row)
        return float(np.clip(xgb_o3.predict(row_s)[0], 0, None))

    return _o3_fn


def _dict_to_row(features: dict, feature_cols: list[str]) -> np.ndarray:
    """Convert a feature dict to a (1, n_features) numpy array."""
    row = np.array(
        [float(features.get(col, 0.0)) for col in feature_cols],
        dtype=np.float32,
    ).reshape(1, -1)
    return row


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from app.services.ml_feature_store import prepare_ml_features

    print("Loading feature store...")
    if os.path.exists(FEATURE_STORE_PATH):
        df = pd.read_csv(FEATURE_STORE_PATH)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    else:
        print("Feature store not found — generating now...")
        df = prepare_ml_features()
        if df.empty:
            print("ERROR: Feature store generation failed. Check DB connection.")
            sys.exit(1)

    metrics = train_models(df)
    print("\nTraining complete. Model callables ready via make_pm_model_fn() / make_o3_model_fn()")