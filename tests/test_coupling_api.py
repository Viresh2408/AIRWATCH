"""
test_coupling_api.py — Unit tests for Phase 3 Coupling API router and new models.
Tests inversion timeline, fire plume forecast, feedback trace explainability endpoints,
and database model operations.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.aqi import Base, Station, Reading, Prediction
from app.models.met_reading import MetReading
from app.models.fire_hotspot import FireHotspot
from app.models.inversion_index import InversionIndex

client = TestClient(app)


class TestCouplingModels:
    """Test SQLAlchemy DB models for Phase 3."""

    def test_met_reading_model_instantiation(self):
        dt = datetime.now(tz=timezone.utc)
        mr = MetReading(
            station_id=1,
            datetime=dt,
            pbl_height=450.0,
            windspeed_10m=3.2,
            winddirection_10m=310.0,
            windspeed_80m=4.8,
            temperature=22.5,
            relativehumidity=55.0,
            uv_index=4.1,
            surface_pressure=1012.0,
        )
        assert mr.station_id == 1
        assert mr.pbl_height == 450.0
        assert mr.temperature == 22.5

    def test_fire_hotspot_model_instantiation(self):
        dt = datetime.now(tz=timezone.utc)
        fh = FireHotspot(
            lat=30.85,
            lon=75.45,
            frp=65.2,
            detected_at=dt,
            source="FIRMS_VIIRS",
        )
        assert fh.lat == 30.85
        assert fh.frp == 65.2
        assert fh.source == "FIRMS_VIIRS"

    def test_inversion_index_model_instantiation(self):
        dt = datetime.now(tz=timezone.utc)
        inv = InversionIndex(
            station_id=1,
            datetime=dt,
            score=0.82,
            category="Strong",
        )
        assert inv.station_id == 1
        assert inv.score == 0.82
        assert inv.category == "Strong"


class TestCouplingEndpoints:
    """Test FastAPI endpoints under /api/v1/coupling."""

    def test_inversion_endpoint_nonexistent_station_returns_404(self):
        resp = client.get("/api/v1/coupling/inversion/99999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_inversion_endpoint_existing_station(self):
        # Station 6943 exists in DB
        resp = client.get("/api/v1/coupling/inversion/6943?hours=24")
        assert resp.status_code == 200
        data = resp.json()
        assert data["station_id"] == 6943
        assert "station_name" in data
        assert "current_score" in data
        assert "current_category" in data
        assert "peak_score" in data
        assert "timeline" in data
        assert len(data["timeline"]) > 0

        first_pt = data["timeline"][0]
        assert "score" in first_pt
        assert "category" in first_pt
        assert "pbl_height" in first_pt
        assert "components" in first_pt
        assert 0.0 <= first_pt["score"] <= 1.0

    def test_plume_forecast_endpoint(self):
        resp = client.get("/api/v1/coupling/plume-forecast")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_hotspots_count" in data
        assert "source_region" in data
        assert "methodology" in data
        assert "disclaimer" in data
        assert "stations" in data
        assert isinstance(data["stations"], list)

        if data["stations"]:
            st = data["stations"][0]
            assert "station_id" in st
            assert "peak_plume_contrib_pm25" in st
            assert "timeline" in st

    def test_plume_forecast_with_station_filter(self):
        resp = client.get("/api/v1/coupling/plume-forecast?station_id=6943")
        assert resp.status_code == 200
        data = resp.json()
        assert "stations" in data
        for st in data["stations"]:
            assert st["station_id"] == 6943

    def test_feedback_trace_nonexistent_station_returns_404(self):
        resp = client.get("/api/v1/coupling/feedback-trace/99999999")
        assert resp.status_code == 404

    def test_feedback_trace_endpoint(self):
        resp = client.get("/api/v1/coupling/feedback-trace/6943?hour_offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["station_id"] == 6943
        assert data["hour_offset"] == 1
        assert "converged" in data
        assert "iterations_run" in data
        assert "pbl_height_raw" in data
        assert "pbl_height_corrected" in data
        assert "pbl_suppression_pct" in data
        assert "iteration_trace" in data
        assert len(data["iteration_trace"]) >= 1
        assert "physics_explanation" in data

        # Check trace structure
        first_step = data["iteration_trace"][0]
        assert "iteration" in first_step
        assert "pm25_estimate" in first_step
        assert "pbl_corrected" in first_step
        assert "delta_pm25" in first_step
