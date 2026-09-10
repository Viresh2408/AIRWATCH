"""
test_prediction_service.py — Unit tests for Phase 2 prediction_service
Tests context seeding, AQI computation, met defaults, and the full
generate_and_save_predictions flow against a real in-memory SQLite DB.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import math
import warnings
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# In-memory SQLite DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_session():
    """Create an in-memory SQLite DB with the full schema."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.aqi import Base, Station, Reading

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed a station
    st = Station(id=3409620, name="Anand Vihar", lat=28.6469, lon=77.3162)
    session.add(st)

    # Seed 6 hours of readings
    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    for h in range(6, 0, -1):
        dt = now - timedelta(hours=h)
        for param, val in [("pm25", 80.0 + h), ("pm10", 160.0 + h),
                            ("o3", 50.0), ("no2", 60.0), ("overall_aqi", 150.0)]:
            session.add(Reading(
                station_id=3409620, datetime=dt,
                parameter=param, unit="µg/m³", value=val,
            ))

    session.commit()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestPredictionService:

    def test_compute_aqi_pm25_dominated(self):
        """AQI with PM2.5=300 should be in 'Poor' to 'Severe' range (CPCB)."""
        from app.services.prediction_service import _compute_aqi
        aqi = _compute_aqi(pm25=300.0, pm10=500.0, o3=40.0)
        assert aqi >= 300, f"PM2.5=300 should give AQI≥300, got {aqi}"

    def test_compute_aqi_zero_pollution(self):
        """All-zero pollutants → AQI = 0."""
        from app.services.prediction_service import _compute_aqi
        aqi = _compute_aqi(pm25=0.0, pm10=0.0, o3=0.0)
        assert aqi == 0

    def test_default_context_has_correct_lag_length(self):
        """_default_context returns 4-element lag lists for all fields."""
        from app.services.prediction_service import _default_context
        ctx = _default_context(station_id=3409620)
        assert ctx.station_id == 3409620
        assert len(ctx.prior_pm25_lags) == 4
        assert len(ctx.prior_no2_lags) == 4
        assert all(v > 0 for v in ctx.prior_pm25_lags)

    def test_build_coupling_context_from_db(self, db_session):
        """_build_coupling_context seeds lags from real DB readings."""
        from app.services.prediction_service import _build_coupling_context
        ctx = _build_coupling_context(db_session, station_id=3409620)
        assert ctx.station_id == 3409620
        assert len(ctx.prior_pm25_lags) == 4
        # Should pick up our seeded values (~80–86 µg/m³)
        assert all(70.0 <= v <= 100.0 for v in ctx.prior_pm25_lags), (
            f"Expected PM2.5 lags near 80, got {ctx.prior_pm25_lags}"
        )

    def test_met_defaults_produces_72_records(self):
        """_met_defaults returns exactly 72 records with required keys."""
        from app.services.prediction_service import _met_defaults
        records = _met_defaults(station_id=3409620)
        assert len(records) == 72
        for rec in records:
            assert "boundary_layer_height" in rec
            assert "uv_index" in rec
            assert rec["boundary_layer_height"] >= 50.0   # ≥ PBL_FLOOR

    def test_met_defaults_pbl_diurnal(self):
        """PBL in default fallback should be higher at midday than midnight."""
        from app.services.prediction_service import _met_defaults
        # Override datetime to get predictable hours
        with patch("app.services.prediction_service.datetime") as mock_dt:
            midnight = datetime(2023, 11, 15, 0, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = midnight
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            records = _met_defaults(station_id=3409620)

        pbl_midnight = records[0]["boundary_layer_height"]   # h=0 = 00:00
        pbl_midday   = records[12]["boundary_layer_height"]  # h=12 = 12:00
        assert pbl_midday > pbl_midnight, (
            f"Midday PBL ({pbl_midday:.0f}m) should exceed midnight ({pbl_midnight:.0f}m)"
        )

    def test_generate_predictions_end_to_end(self, db_session):
        """
        Full end-to-end: generate_and_save_predictions inserts Prediction rows
        for the seeded station without raising exceptions.
        Uses the persistence fallback (no trained model needed).
        """
        from app.services.prediction_service import generate_and_save_predictions
        from app.models.aqi import Prediction

        # Patch met_client and plume_service so no external calls needed
        met_stub = _make_met_stub()
        plume_stub: list = []

        with patch("app.services.prediction_service.fetch_met_forecast", return_value=met_stub), \
             patch("app.services.prediction_service.estimate_plume_contributions", return_value=plume_stub), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            n = generate_and_save_predictions(db_session)

        assert n > 0, "Expected at least some prediction rows to be saved"
        saved = db_session.query(Prediction).filter(Prediction.station_id == 3409620).all()
        assert len(saved) == n, f"Row count mismatch: returned {n} but found {len(saved)}"

    def test_prediction_rows_have_inversion_score(self, db_session):
        """Every saved Prediction row should have inversion_score populated."""
        from app.models.aqi import Prediction
        rows = db_session.query(Prediction).filter(Prediction.station_id == 3409620).all()
        for row in rows:
            assert row.inversion_score is not None, (
                f"h+{row.hour_offset}: inversion_score is None — coupling diagnostics not persisted"
            )
            assert 0.0 <= row.inversion_score <= 1.0

    def test_prediction_rows_have_ci_bounds(self, db_session):
        """Every Prediction row must have pm25_lower ≤ predicted_pm25 ≤ pm25_upper."""
        from app.models.aqi import Prediction
        rows = db_session.query(Prediction).filter(Prediction.station_id == 3409620).all()
        for row in rows:
            if row.predicted_pm25 is not None and row.pm25_lower is not None:
                assert row.pm25_lower <= row.predicted_pm25 <= row.pm25_upper, (
                    f"h+{row.hour_offset}: CI bounds invalid "
                    f"[{row.pm25_lower:.1f}, {row.predicted_pm25:.1f}, {row.pm25_upper:.1f}]"
                )

    def test_pm10_gte_pm25_in_predictions(self, db_session):
        """PM10 must be >= PM2.5 in every saved prediction (physical constraint)."""
        from app.models.aqi import Prediction
        rows = db_session.query(Prediction).filter(Prediction.station_id == 3409620).all()
        for row in rows:
            if row.predicted_pm25 is not None and row.predicted_pm10 is not None:
                assert row.predicted_pm10 >= row.predicted_pm25, (
                    f"h+{row.hour_offset}: PM10 ({row.predicted_pm10:.1f}) < PM2.5 ({row.predicted_pm25:.1f})"
                )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_met_stub(n: int = 72) -> list[dict]:
    """Synthetic met records for the Anand Vihar station."""
    now = datetime(2023, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "datetime": now + timedelta(hours=h),
            "station_id": 3409620,
            "boundary_layer_height": max(50.0, 400.0 + 300.0 * math.sin(math.pi * ((h % 24) - 6) / 12)),
            "temperature_2m": 18.0,
            "relativehumidity_2m": 65.0,
            "windspeed_10m": 2.5,
            "winddirection_10m": 315.0,
            "wind_u_10m": -1.77, "wind_v_10m": 1.77,
            "windspeed_80m": 4.0, "winddirection_80m": 315.0,
            "wind_u_80m": -2.83, "wind_v_80m": 2.83,
            "uv_index": max(0.0, 5.0 * math.sin(math.pi * ((h % 24) - 6) / 12)),
            "surface_pressure": 1013.0,
        }
        for h in range(n)
    ]
