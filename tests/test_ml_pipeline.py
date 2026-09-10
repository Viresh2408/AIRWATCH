"""
test_ml_pipeline.py — Unit tests for Phase 2 ML pipeline
Tests the dual sub-model interface, callable factories, and fallback behaviour.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import math
import warnings
import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers — synthetic training data
# ---------------------------------------------------------------------------

def _make_training_df(n: int = 200) -> pd.DataFrame:
    """
    Synthetic feature store with all columns that both sub-models need.
    PM2.5 ~ 80 + 30*sin(hour) + noise  (diurnal + random)
    O3    ~ 50 + 25*max(0, sin(hour))  (daytime peaks only)
    """
    np.random.seed(42)
    hours = np.arange(n)

    pm25  = 80 + 30 * np.sin(2 * np.pi * hours / 24) + np.random.normal(0, 8, n)
    pm10  = pm25 * 1.8 + np.random.normal(0, 10, n)
    o3    = np.clip(50 + 25 * np.maximum(0, np.sin(2 * np.pi * hours / 24 - 0.5)), 0, None) + np.random.normal(0, 5, n)
    no2   = np.clip(60 + 20 * np.cos(2 * np.pi * hours / 24) + np.random.normal(0, 5, n), 10, None)
    pbl   = np.clip(200 + 500 * np.maximum(0, np.sin(2 * np.pi * (hours % 24) / 24 - 0.3)), 50, None)
    aqi   = pm25 * 1.2

    df = pd.DataFrame({
        "station_id":         [1] * n,
        "datetime":           pd.date_range("2023-11-01", periods=n, freq="h", tz="UTC"),
        "pm25":               np.clip(pm25, 0, None),
        "pm10":               np.clip(pm10, 0, None),
        "o3":                 o3,
        "no2":                no2,
        "overall_aqi":        np.clip(aqi, 0, None),
        "pbl_height":         pbl,
        "windspeed_10m":      np.random.uniform(1, 6, n),
        "temperature":        np.random.uniform(12, 28, n),
        "relativehumidity":   np.random.uniform(45, 80, n),
        "uv_index":           np.clip(6 * np.maximum(0, np.sin(2 * np.pi * (hours % 24) / 24 - 0.4)), 0, None),
        "inversion_score":    np.clip((600 - pbl) / 600, 0, 0.8),
        "plume_pm25_contrib": np.random.uniform(0, 5, n),
        "stubble_season":     1,
        "hour_sin":           np.sin(2 * np.pi * (hours % 24) / 24),
        "hour_cos":           np.cos(2 * np.pi * (hours % 24) / 24),
        "day_of_week":        [(i // 24) % 7 for i in range(n)],
        "month":              11,
    })

    # Add lag columns (shifted within station)
    for lag in range(1, 5):
        df[f"pm25_lag_{lag}"] = df["pm25"].shift(lag).fillna(df["pm25"].median())
        df[f"aqi_lag_{lag}"]  = df["overall_aqi"].shift(lag).fillna(df["overall_aqi"].median())
    for lag in range(1, 3):
        df[f"pm10_lag_{lag}"]   = df["pm10"].shift(lag).fillna(df["pm10"].median())
        df[f"o3_lag_{lag}"]     = df["o3"].shift(lag).fillna(df["o3"].median())

    df["nox_precursor_lag"]  = df["no2"].shift(1).fillna(df["no2"].median())
    df["nox_precursor_lag2"] = df["no2"].shift(2).fillna(df["no2"].median())

    # Targets
    df["target_pm25"] = df["pm25"].shift(-1)
    df["target_pm10"] = df["pm10"].shift(-1)
    df["target_o3"]   = df["o3"].shift(-1)

    df = df.dropna(subset=["target_pm25", "target_o3"])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMlPipeline:

    def test_train_pm_model_produces_artifact(self, tmp_path):
        """train_models() saves pm_model.joblib with correct tuple structure."""
        from app.services.ml_pipeline import train_models
        df = _make_training_df()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            metrics = train_models(df)  # uses default MODEL_DIR

        import joblib, os
        from app.services.ml_pipeline import PM_MODEL_PATH
        assert os.path.exists(PM_MODEL_PATH), "pm_model.joblib not created"
        xgb_pm25, xgb_pm10, scaler, cols = joblib.load(PM_MODEL_PATH)
        assert xgb_pm25 is not None
        assert xgb_pm10 is not None
        assert len(cols) > 0
        assert "mae" in metrics["pm"]

    def test_train_o3_model_produces_artifact(self):
        """train_models() saves o3_model.joblib."""
        from app.services.ml_pipeline import train_models, O3_MODEL_PATH
        import os, joblib
        df = _make_training_df()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_models(df)
        assert os.path.exists(O3_MODEL_PATH), "o3_model.joblib not created"
        xgb_o3, scaler, cols = joblib.load(O3_MODEL_PATH)
        assert xgb_o3 is not None

    def test_pm_model_callable_returns_tuple(self):
        """make_pm_model_fn() returns a callable (float, float) from a feature dict."""
        from app.services.ml_pipeline import make_pm_model_fn, train_models, PM_MODEL_PATH
        import os
        df = _make_training_df()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_models(df)
        assert os.path.exists(PM_MODEL_PATH)

        pm_fn = make_pm_model_fn()
        features = {
            "pm25_lag_1": 80.0, "pm25_lag_2": 75.0, "pm25_lag_3": 70.0, "pm25_lag_4": 72.0,
            "pm10_lag_1": 160.0, "pm10_lag_2": 150.0,
            "aqi_lag_1": 150.0, "aqi_lag_2": 140.0, "aqi_lag_3": 145.0, "aqi_lag_4": 148.0,
            "pbl_height": 400.0, "windspeed_10m": 3.0, "temperature": 18.0,
            "relativehumidity": 60.0, "inversion_score": 0.4,
            "plume_pm25_contrib": 0.0,
            "hour_sin": 0.5, "hour_cos": 0.866, "day_of_week": 2,
            "month": 11, "stubble_season": 1,
        }
        pm25, pm10 = pm_fn(features)
        assert pm25 >= 0.0, f"PM2.5 should be non-negative, got {pm25}"
        assert pm10 >= pm25, f"PM10 ({pm10}) should be >= PM2.5 ({pm25})"

    def test_o3_model_callable_returns_float(self):
        """make_o3_model_fn() returns a non-negative float from a feature dict."""
        from app.services.ml_pipeline import make_o3_model_fn, train_models, O3_MODEL_PATH
        import os
        df = _make_training_df()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_models(df)
        assert os.path.exists(O3_MODEL_PATH)

        o3_fn = make_o3_model_fn()
        features = {
            "o3_lag_1": 55.0, "o3_lag_2": 52.0,
            "nox_precursor_lag": 60.0, "nox_precursor_lag2": 58.0,
            "uv_index": 5.0, "temperature": 22.0, "windspeed_10m": 2.5,
            "pbl_height": 500.0, "inversion_score": 0.2,
            "hour_sin": 0.866, "hour_cos": 0.5, "day_of_week": 1, "month": 11,
        }
        o3 = o3_fn(features)
        assert isinstance(o3, float)
        assert o3 >= 0.0, f"O3 should be non-negative, got {o3}"

    def test_pm_model_fallback_when_no_artifact(self, tmp_path, monkeypatch):
        """
        make_pm_model_fn() gracefully falls back to persistence model
        when pm_model.joblib doesn't exist.
        """
        from app.services import ml_pipeline
        monkeypatch.setattr(ml_pipeline, "MODEL_DIR", str(tmp_path))
        pm_fn = ml_pipeline.make_pm_model_fn(model_dir=str(tmp_path))
        # Fallback uses lag_1 values directly
        pm25, pm10 = pm_fn({"pm25_lag_1": 120.0, "pm10_lag_1": 200.0})
        assert pm25 == 120.0
        assert pm10 == 200.0

    def test_o3_model_fallback_is_diurnal(self, tmp_path, monkeypatch):
        """
        make_o3_model_fn() fallback produces higher O3 at midday (hour_sin≈1)
        than at midnight (hour_sin≈0), confirming the diurnal UV proxy works.
        """
        from app.services import ml_pipeline
        monkeypatch.setattr(ml_pipeline, "MODEL_DIR", str(tmp_path))
        o3_fn = ml_pipeline.make_o3_model_fn(model_dir=str(tmp_path))

        o3_midday    = o3_fn({"hour_sin": 1.0, "uv_index": 8.0})
        o3_midnight  = o3_fn({"hour_sin": 0.0, "uv_index": 0.0})
        assert o3_midday > o3_midnight, (
            f"Midday O3 ({o3_midday:.1f}) should exceed midnight O3 ({o3_midnight:.1f})"
        )

    def test_pm10_physical_constraint_pm10_gte_pm25(self):
        """PM10 must always be >= PM2.5 (physical: PM2.5 is a subset of PM10)."""
        from app.services.ml_pipeline import make_pm_model_fn, train_models
        import warnings
        df = _make_training_df()
        # Deliberately make PM10 target lower than PM2.5 in some rows to stress the constraint
        df["target_pm10"] = df["target_pm25"] * 0.5   # impossible physically — model might predict this
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_models(df)
        pm_fn = make_pm_model_fn()
        for pm25_lag in [30.0, 80.0, 250.0, 400.0]:
            features = {
                f"pm25_lag_{i}": pm25_lag for i in range(1, 5)
            }
            features.update({
                f"pm10_lag_{i}": pm25_lag * 0.5 for i in range(1, 3)
            })
            features.update({
                f"aqi_lag_{i}": pm25_lag * 1.2 for i in range(1, 5)
            })
            features.update({
                "pbl_height": 300.0, "windspeed_10m": 2.0,
                "temperature": 18.0, "relativehumidity": 70.0,
                "inversion_score": 0.5, "plume_pm25_contrib": 0.0,
                "hour_sin": 0.0, "hour_cos": 1.0,
                "day_of_week": 3, "month": 11, "stubble_season": 1,
            })
            pm25, pm10 = pm_fn(features)
            assert pm10 >= pm25, (
                f"PM10 ({pm10:.1f}) < PM2.5 ({pm25:.1f}) at lag={pm25_lag} — "
                f"physical constraint violated in make_pm_model_fn"
            )

    def test_nox_assertion_warns_on_zero_no2(self):
        """_assert_nox_coverage emits UserWarning when NO2 is all-zero."""
        from app.services.ml_feature_store import _assert_nox_coverage
        df = _make_training_df()
        df["nox_precursor_lag"] = 0.0   # simulate broken NO2 ingestion
        with pytest.warns(UserWarning, match="nox_precursor_lag"):
            _assert_nox_coverage(df, min_fraction=0.10)

    def test_nox_assertion_passes_with_valid_no2(self):
        """_assert_nox_coverage does NOT warn when NO2 coverage is sufficient."""
        from app.services.ml_feature_store import _assert_nox_coverage
        df = _make_training_df()
        # All non-zero — should not warn
        with warnings.catch_warnings():
            warnings.simplefilter("error")   # treat any warning as error
            _assert_nox_coverage(df, min_fraction=0.10)   # should pass silently

    def test_coupling_engine_integration_with_trained_models(self):
        """
        End-to-end integration: trained callables plugged into coupling_engine
        produce 72 steps with monotonically bounded PM2.5 and non-negative O3.
        """
        from app.services.ml_pipeline import make_pm_model_fn, make_o3_model_fn, train_models
        from app.services.coupling_engine import run_coupled_forecast, CouplingContext
        from datetime import datetime, timezone, timedelta
        import warnings

        df = _make_training_df(n=300)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_models(df)

        pm_fn = make_pm_model_fn()
        o3_fn = make_o3_model_fn()

        ctx = CouplingContext(
            station_id=1,
            prior_pm25_lags=[80.0, 78.0, 82.0, 75.0],
            prior_pm10_lags=[160.0, 155.0, 165.0, 150.0],
            prior_o3_lags=[55.0, 50.0, 52.0, 48.0],
            prior_no2_lags=[60.0, 58.0, 62.0, 57.0],
            prior_aqi_lags=[150.0, 148.0, 155.0, 145.0],
        )

        now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        met = [
            {
                "datetime": now + timedelta(hours=h),
                "station_id": 1,
                "boundary_layer_height": max(50.0, 600.0 - h * 3.0),
                "temperature_2m": 18.0,
                "relativehumidity_2m": 65.0,
                "windspeed_10m": 2.5,
                "winddirection_10m": 315.0,
                "wind_u_10m": -1.77, "wind_v_10m": 1.77,
                "windspeed_80m": 4.0, "winddirection_80m": 315.0,
                "wind_u_80m": -2.83, "wind_v_80m": 2.83,
                "uv_index": max(0.0, 5.0 * math.sin(math.pi * ((now.hour + h) % 24 - 6) / 12)),
                "surface_pressure": 1013.0,
            }
            for h in range(72)
        ]

        steps = run_coupled_forecast(1, met, [], ctx, pm_fn, o3_fn)

        assert len(steps) == 72, f"Expected 72 steps, got {len(steps)}"
        for step in steps:
            assert step.pm25 >= 0.0, f"h+{step.hour_offset}: PM2.5 < 0"
            assert step.pm10 >= step.pm25, f"h+{step.hour_offset}: PM10 < PM2.5"
            assert step.o3 >= 0.0, f"h+{step.hour_offset}: O3 < 0"
            assert 0.0 <= step.inversion_score <= 1.0
