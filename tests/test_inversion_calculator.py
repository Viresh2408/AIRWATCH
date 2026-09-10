"""
test_inversion_calculator.py — Unit tests for inversion strength index
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import pytest
from datetime import datetime, timezone


class TestInversionCalculator:

    def test_zero_pbl_gives_high_base_score(self):
        """
        PBL=0 m at CRITICAL → base_score=0.8 (design choice: remaining 0.2
        requires simultaneous rapid PBL collapse + pre-dawn timing).
        With a falling PBL (prev=200m → curr=0m, delta=200m = full trend bonus)
        and pre-dawn UTC hour 20, the combined score hits 1.0.
        """
        from app.services.inversion_calculator import compute_inversion_score
        # Case 1: isolated zero PBL, no trend/tod → base_score = 0.8
        result_base = compute_inversion_score(0.0, forecast_hour_utc=12)
        assert result_base["components"]["base_score"] == pytest.approx(0.8, abs=0.01)
        # Case 2: zero PBL + rapid fall + pre-dawn → combined score = 1.0
        result_max = compute_inversion_score(0.0, prev_pbl_height=200.0, forecast_hour_utc=20)
        assert result_max["score"] == pytest.approx(1.0, abs=0.01)

    def test_high_pbl_gives_zero_score(self):
        """PBL=5000 m (strong mixing, clear day) → score should be 0.0."""
        from app.services.inversion_calculator import compute_inversion_score
        result = compute_inversion_score(5000.0)
        assert result["score"] == pytest.approx(0.0, abs=0.01)

    def test_threshold_pbl_gives_zero_base(self):
        """PBL at INVERSION_PBL_THRESHOLD (500m) → base_score = 0."""
        from app.services.inversion_calculator import compute_inversion_score
        from app.core.config import INVERSION_PBL_THRESHOLD
        result = compute_inversion_score(INVERSION_PBL_THRESHOLD, forecast_hour_utc=12)
        # tod_bonus = 0 at noon UTC (not pre-dawn), trend_bonus = 0 (no prev)
        assert result["components"]["base_score"] == pytest.approx(0.0, abs=0.01)

    def test_falling_pbl_adds_trend_bonus(self):
        """Rapidly falling PBL (−200 m/h) should add trend_bonus = 0.2."""
        from app.services.inversion_calculator import compute_inversion_score
        result = compute_inversion_score(300.0, prev_pbl_height=500.0)
        assert result["components"]["trend_bonus"] == pytest.approx(0.2, abs=0.01)

    def test_rising_pbl_no_trend_penalty(self):
        """Rising PBL should not add trend bonus (but also no penalty)."""
        from app.services.inversion_calculator import compute_inversion_score
        result = compute_inversion_score(500.0, prev_pbl_height=300.0)
        assert result["components"]["trend_bonus"] == pytest.approx(0.0, abs=0.001)

    def test_predawn_hours_add_tod_bonus(self):
        """UTC hour 20 (≈ 01:30 IST) should add tod_bonus = 0.10."""
        from app.services.inversion_calculator import compute_inversion_score
        result_predawn = compute_inversion_score(400.0, forecast_hour_utc=20)
        result_noon    = compute_inversion_score(400.0, forecast_hour_utc=12)
        assert result_predawn["components"]["tod_bonus"] == pytest.approx(0.10, abs=0.001)
        assert result_noon["components"]["tod_bonus"]    == pytest.approx(0.00, abs=0.001)

    def test_score_clamped_to_unit_interval(self):
        """Score is always in [0.0, 1.0] for any input combination."""
        from app.services.inversion_calculator import compute_inversion_score
        for pbl in [0, 50, 100, 200, 500, 1000, 5000]:
            for prev in [None, 0, 100, 600]:
                for hour in [0, 6, 12, 18, 23]:
                    result = compute_inversion_score(pbl, prev_pbl_height=prev, forecast_hour_utc=hour)
                    assert 0.0 <= result["score"] <= 1.0

    def test_category_severe_at_low_pbl(self):
        """PBL=80 m (extreme inversion) → category should be Severe."""
        from app.services.inversion_calculator import compute_inversion_score
        result = compute_inversion_score(80.0, prev_pbl_height=200.0, forecast_hour_utc=21)
        assert result["category"] == "Severe"

    def test_category_none_at_high_pbl(self):
        """PBL=2000 m → category should be None."""
        from app.services.inversion_calculator import compute_inversion_score
        result = compute_inversion_score(2000.0)
        assert result["category"] == "None"

    def test_timeline_length_matches_input(self):
        """compute_inversion_timeline returns one result per met record."""
        from app.services.inversion_calculator import compute_inversion_timeline
        met_records = [
            {"boundary_layer_height": 300.0 + i * 10, "datetime": datetime(2024, 10, 15, i, 0, tzinfo=timezone.utc)}
            for i in range(24)
        ]
        results = compute_inversion_timeline(met_records)
        assert len(results) == 24

    def test_timeline_first_step_no_trend(self):
        """First step in timeline has no prev_pbl, so trend_bonus = 0."""
        from app.services.inversion_calculator import compute_inversion_timeline
        met_records = [
            {"boundary_layer_height": 300.0, "datetime": datetime(2024, 10, 15, 12, 0, tzinfo=timezone.utc)},
            {"boundary_layer_height": 100.0, "datetime": datetime(2024, 10, 15, 13, 0, tzinfo=timezone.utc)},
        ]
        results = compute_inversion_timeline(met_records)
        assert results[0]["components"]["trend_bonus"] == pytest.approx(0.0, abs=0.001)
        assert results[1]["components"]["trend_bonus"] > 0   # PBL dropped 200 m
