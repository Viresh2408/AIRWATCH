"""
test_met_client.py — Unit tests for the Open-Meteo met client
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import math
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(n_hours: int = 72) -> dict:
    """Build a minimal Open-Meteo-style JSON response."""
    base = datetime(2024, 10, 15, 0, 0, tzinfo=timezone.utc)
    times = [(base.replace(hour=i % 24)).strftime("%Y-%m-%dT%H:%M") for i in range(n_hours)]
    return {
        "hourly": {
            "time": times,
            "boundary_layer_height": [300.0 + i * 2 for i in range(n_hours)],
            "windspeed_10m":         [3.5] * n_hours,
            "winddirection_10m":     [270.0] * n_hours,  # westerly
            "windspeed_80m":         [5.0] * n_hours,
            "winddirection_80m":     [260.0] * n_hours,
            "temperature_2m":        [18.0] * n_hours,
            "relativehumidity_2m":   [70.0] * n_hours,
            "uv_index":              [3.5] * n_hours,
            "surface_pressure":      [1010.0] * n_hours,
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMetClient:

    def test_fetch_returns_correct_count(self):
        """Fetching 72 hours returns exactly 72 records."""
        from app.services.met_client import fetch_met_forecast, clear_cache
        clear_cache()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_mock_response(n_hours=72)
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.met_client.requests.get", return_value=mock_resp):
            records = fetch_met_forecast(28.65, 77.20, hours=72, use_cache=False)

        assert len(records) == 72

    def test_fetch_parses_pbl_height(self):
        """boundary_layer_height is parsed correctly."""
        from app.services.met_client import fetch_met_forecast, clear_cache
        clear_cache()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_mock_response(72)
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.met_client.requests.get", return_value=mock_resp):
            records = fetch_met_forecast(28.65, 77.20, hours=72, use_cache=False)

        assert records[0]["boundary_layer_height"] == pytest.approx(300.0)
        assert all(r["boundary_layer_height"] > 0 for r in records)

    def test_wind_uv_components_westerly(self):
        """
        Wind blowing FROM 270° (westerly) should produce:
          u (eastward) ≈ +speed (wind carries air eastward)
          v (northward) ≈ 0
        Met convention: u = -speed * sin(dir), v = -speed * cos(dir)
        sin(270) = -1, cos(270) = 0 → u = speed, v = 0
        """
        from app.services.met_client import _wind_u, _wind_v
        speed = 3.5
        direction = 270.0
        u = _wind_u(speed, direction)
        v = _wind_v(speed, direction)
        assert u == pytest.approx(speed, abs=1e-6), f"u={u} expected ~{speed}"
        assert v == pytest.approx(0.0, abs=1e-6), f"v={v} expected ~0"

    def test_wind_uv_components_northerly(self):
        """Wind FROM 0° (northerly) → v negative (blowing south), u ≈ 0."""
        from app.services.met_client import _wind_u, _wind_v
        speed = 5.0
        u = _wind_u(speed, 0.0)
        v = _wind_v(speed, 0.0)
        assert u == pytest.approx(0.0, abs=1e-6)
        assert v == pytest.approx(-speed, abs=1e-6)

    def test_api_failure_returns_empty(self):
        """Network failure returns empty list (graceful degradation)."""
        import requests as _req
        from app.services.met_client import fetch_met_forecast, clear_cache
        clear_cache()
        with patch("app.services.met_client.requests.get", side_effect=_req.RequestException("timeout")):
            records = fetch_met_forecast(28.65, 77.20, hours=72, use_cache=False)
        assert records == []

    def test_cache_works(self):
        """Second call to same coordinates returns cached result without HTTP."""
        from app.services.met_client import fetch_met_forecast, clear_cache
        clear_cache()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_mock_response(72)
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.met_client.requests.get", return_value=mock_resp) as mock_get:
            fetch_met_forecast(28.65, 77.20, hours=72, use_cache=True)
            fetch_met_forecast(28.65, 77.20, hours=72, use_cache=True)

        assert mock_get.call_count == 1   # second call hit cache

    def test_datetime_is_utc_aware(self):
        """Returned datetimes must be timezone-aware UTC."""
        from app.services.met_client import fetch_met_forecast, clear_cache
        clear_cache()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_mock_response(3)
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.met_client.requests.get", return_value=mock_resp):
            records = fetch_met_forecast(28.65, 77.20, hours=3, use_cache=False)

        for rec in records:
            assert rec["datetime"].tzinfo is not None
