"""
test_fire_plume_service.py — Unit tests for NASA FIRMS fire plume dispersion service.
Tests CSV parsing, Haversine/bearing geometry, Gaussian spreading cone math,
and graceful degradation under missing API keys or zero-fire conditions.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import pytest
from app.services.fire_plume_service import (
    _haversine_km,
    _bearing_deg,
    _angle_diff,
    _parse_firms_csv,
    _single_hotspot_contrib,
    fetch_fire_hotspots,
    estimate_plume_contributions,
    estimate_plume_for_station,
)


class TestFirePlumeMath:
    """Test geometric and physical formulas."""

    def test_haversine_known_distance(self):
        """Delhi (28.65, 77.20) to Amritsar (31.63, 74.87) is approx 400-420 km."""
        dist = _haversine_km(28.65, 77.20, 31.63, 74.87)
        assert 390.0 < dist < 430.0

    def test_haversine_same_point(self):
        """Distance between identical coordinates is 0.0."""
        dist = _haversine_km(28.65, 77.20, 28.65, 77.20)
        assert dist == 0.0

    def test_bearing_cardinal_directions(self):
        """North is 0 deg, East is 90 deg, South is 180 deg, West is 270 deg."""
        # Due north
        b_north = _bearing_deg(28.0, 77.0, 29.0, 77.0)
        assert abs(b_north - 0.0) < 1.0 or abs(b_north - 360.0) < 1.0
        # Due east
        b_east = _bearing_deg(28.0, 77.0, 28.0, 78.0)
        assert abs(b_east - 90.0) < 1.0

    def test_angle_diff_wrap_around(self):
        """Test minimal angular difference across 0/360 boundary."""
        assert _angle_diff(10, 350) == 20
        assert _angle_diff(350, 10) == 20
        assert _angle_diff(90, 180) == 90
        assert _angle_diff(0, 180) == 180

    def test_single_hotspot_zero_frp(self):
        """Zero or negative FRP produces 0.0 contribution."""
        contrib = _single_hotspot_contrib(
            hs_lat=30.0, hs_lon=75.0, hs_frp=0.0,
            st_lat=28.6, st_lon=77.2,
            wind_dir_deg=315.0, wind_speed=3.0,
        )
        assert contrib == 0.0

    def test_single_hotspot_upwind_versus_downwind(self):
        """
        Hotspot in Punjab (31.0 N, 75.0 E) Northwest of Delhi (28.6 N, 77.2 E).
        Bearing from hotspot to Delhi is ~135 deg (SE).
        If wind is from NW (315 deg), transport is to SE (135 deg) -> Delhi is directly DOWNWIND.
        If wind is from SE (135 deg), transport is to NW (315 deg) -> Delhi is UPWIND -> 0 contribution.
        """
        # Downwind: wind from NW (315 deg) -> transport to 135 deg
        contrib_downwind = _single_hotspot_contrib(
            hs_lat=31.0, hs_lon=75.0, hs_frp=50.0,
            st_lat=28.6, st_lon=77.2,
            wind_dir_deg=315.0, wind_speed=3.0,
        )
        assert contrib_downwind > 0.0

        # Upwind: wind from SE (135 deg) -> transport to 315 deg (away from Delhi)
        contrib_upwind = _single_hotspot_contrib(
            hs_lat=31.0, hs_lon=75.0, hs_frp=50.0,
            st_lat=28.6, st_lon=77.2,
            wind_dir_deg=135.0, wind_speed=3.0,
        )
        assert contrib_upwind == 0.0


class TestFIRMSCSVParser:
    """Test parsing of NASA FIRMS CSV output."""

    def test_parse_valid_csv(self):
        sample_csv = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "30.5123,75.4321,340.2,0.4,0.4,2023-11-05,0815,N,VIIRS,nominal,2.0NRT,295.1,42.5,D\n"
            "31.1111,74.9999,355.0,0.5,0.4,2023-11-05,0815,N,VIIRS,high,2.0NRT,300.0,78.2,D\n"
        )
        hotspots = _parse_firms_csv(sample_csv)
        assert len(hotspots) == 2
        assert hotspots[0]["lat"] == 30.5123
        assert hotspots[0]["lon"] == 75.4321
        assert hotspots[0]["frp"] == 42.5
        assert isinstance(hotspots[0]["acq_datetime"], datetime)

    def test_parse_empty_or_header_only_csv(self):
        assert _parse_firms_csv("") == []
        assert _parse_firms_csv("latitude,longitude,frp\n") == []

    def test_fetch_fire_hotspots_no_key_returns_empty(self):
        """Without API key, returns [] without raising exceptions."""
        result = fetch_fire_hotspots("")
        assert result == []


class TestEstimatePlumeContributions:
    """Test hourly plume contribution calculations across stations."""

    def test_zero_hotspots_returns_zero_contrib(self):
        met_recs = [
            {"datetime": datetime(2023, 11, 5, h, 0, tzinfo=timezone.utc),
             "wind_u_80m": -2.0, "wind_v_80m": 2.0}
            for h in range(24)
        ]
        res = estimate_plume_contributions(
            hotspots=[],
            met_records_by_station={3409620: met_recs},
        )
        assert 3409620 in res
        assert len(res[3409620]) == 24
        assert all(r["plume_pm25_contrib"] == 0.0 for r in res[3409620])

    def test_single_station_kwargs_convention(self):
        """Verify calling with station_lat, station_lon, met_records returns list."""
        hotspots = [
            {"lat": 31.0, "lon": 75.0, "frp": 60.0, "acq_datetime": datetime.now(tz=timezone.utc)}
        ]
        met_recs = [
            {"datetime": datetime(2023, 11, 5, 12, 0, tzinfo=timezone.utc),
             "wind_u_80m": -2.0, "wind_v_80m": 2.0}
        ]
        contribs = estimate_plume_contributions(
            hotspots=hotspots,
            station_lat=28.6469,
            station_lon=77.3162,
            met_records=met_recs,
        )
        assert isinstance(contribs, list)
        assert len(contribs) == 1
        assert "plume_pm25_contrib" in contribs[0]
        assert contribs[0]["hotspot_count"] == 1
