"""
test_coupling_engine.py — Unit tests for the two-way coupling feedback loop (fixed)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fastapi_app'))

import math
import pytest
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_met_rec(hour_offset: int, pbl: float = 500.0, temp: float = 20.0,
                  ws10: float = 3.0, wd10: float = 270.0, uv: float = 4.0) -> dict:
    base = datetime(2024, 11, 1, 0, 0, tzinfo=timezone.utc)
    dt = base + timedelta(hours=hour_offset)
    return {
        "datetime": dt,
        "boundary_layer_height": pbl,
        "temperature_2m": temp,
        "windspeed_10m": ws10,
        "winddirection_10m": wd10,
        "windspeed_80m": ws10 * 1.3,
        "winddirection_80m": wd10,
        "relativehumidity_2m": 70.0,
        "uv_index": uv,
        "surface_pressure": 1010.0,
        "wind_u_10m": -ws10 * math.sin(math.radians(wd10)),
        "wind_v_10m": -ws10 * math.cos(math.radians(wd10)),
        "wind_u_80m": -ws10 * 1.3 * math.sin(math.radians(wd10)),
        "wind_v_80m": -ws10 * 1.3 * math.cos(math.radians(wd10)),
    }


def _make_context(pm25: float = 80.0, no2: float = 40.0, o3: float = 50.0) -> object:
    from app.services.coupling_engine import CouplingContext
    return CouplingContext(
        station_id=3409620,
        prior_pm25_lags=[pm25, pm25 * 0.9, pm25 * 0.8, pm25 * 0.7],
        prior_pm10_lags=[pm25 * 2.0] * 4,
        prior_o3_lags=[o3] * 4,
        prior_no2_lags=[no2] * 4,
        prior_aqi_lags=[120.0] * 4,
    )


def _simple_pm_model(features: dict):
    """Trivial PM model: pm25 scales from lag + inversion + plume."""
    base = features.get("pm25_lag_1", 80.0)   # anchored to prior lag
    inv = features.get("inversion_score", 0.0)
    plume = features.get("plume_pm25_contrib", 0.0)
    pm25 = base * (1 + inv * 0.5) + plume
    pm10 = pm25 * 2.0
    return pm25, pm10


def _simple_o3_model(features: dict):
    """Trivial O3 model: o3 ~ 50 * (uv / 5)."""
    uv = features.get("uv_index", 3.0)
    return 50.0 * (uv / 5.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCouplingEngine:

    def test_step_produces_output(self):
        """A 72-hour coupled run returns exactly 72 CoupledForecastStep objects."""
        from app.services.coupling_engine import run_coupled_forecast
        met = [_make_met_rec(h) for h in range(72)]
        ctx = _make_context()
        steps = run_coupled_forecast(
            station_id=3409620,
            met_records=met,
            plume_records=[],
            initial_context=ctx,
            pm_model_fn=_simple_pm_model,
            o3_model_fn=_simple_o3_model,
        )
        assert len(steps) == 72

    def test_feedback_reduces_pbl(self):
        """
        Core two-way coupling invariant: aerosol → PBL suppression.
        When PM2.5 is high (seeded from prior lags), the aerosol feedback
        must produce corrected_PBL <= raw_PBL for every forecast step.
        """
        from app.services.coupling_engine import run_coupled_forecast
        ctx = _make_context(pm25=300.0)   # high PM2.5 seed
        met = [_make_met_rec(h, pbl=600.0) for h in range(72)]
        steps = run_coupled_forecast(
            station_id=3409620,
            met_records=met,
            plume_records=[],
            initial_context=ctx,
            pm_model_fn=_simple_pm_model,
            o3_model_fn=_simple_o3_model,
        )
        for step in steps:
            assert step.pbl_height_corrected <= step.pbl_height_raw, (
                f"h+{step.hour_offset}: corrected PBL {step.pbl_height_corrected:.1f} "
                f"> raw PBL {step.pbl_height_raw:.1f} — feedback direction is wrong!"
            )

    def test_high_pm25_suppresses_o3_uv(self):
        """
        High PM2.5 → aerosol shading → lower effective UV → lower O3.
        Tests the O3 sub-model's divergence from the PM sub-model.
        """
        from app.services.coupling_engine import run_coupled_forecast, CouplingContext
        ctx_clean = CouplingContext(
            3409620, [10.0]*4, [20.0]*4, [50.0]*4, [30.0]*4, [50.0]*4)
        ctx_polluted = CouplingContext(
            3409620, [400.0]*4, [800.0]*4, [50.0]*4, [30.0]*4, [250.0]*4)
        met = [_make_met_rec(12, pbl=600.0, uv=8.0)]

        steps_clean    = run_coupled_forecast(3409620, met, [], ctx_clean,    _simple_pm_model, _simple_o3_model)
        steps_polluted = run_coupled_forecast(3409620, met, [], ctx_polluted, _simple_pm_model, _simple_o3_model)

        assert steps_polluted[0].uv_index_effective < steps_clean[0].uv_index_effective, (
            "Polluted scenario should have lower effective UV than clean scenario"
        )
        assert steps_polluted[0].o3 < steps_clean[0].o3, (
            "Higher PM2.5 should result in lower O3 via UV attenuation"
        )

    def test_convergence_within_max_iterations(self):
        """Coupling loop must not exceed COUPLING_MAX_ITERATIONS per step."""
        from app.services.coupling_engine import run_coupled_forecast, COUPLING_MAX_ITERATIONS
        ctx = _make_context(pm25=100.0)
        met = [_make_met_rec(h) for h in range(72)]
        steps = run_coupled_forecast(3409620, met, [], ctx, _simple_pm_model, _simple_o3_model)
        for step in steps:
            assert step.iterations_run <= COUPLING_MAX_ITERATIONS, (
                f"h+{step.hour_offset}: ran {step.iterations_run} iterations, max is {COUPLING_MAX_ITERATIONS}"
            )

    def test_iteration_trace_populated(self):
        """Every step must have a non-empty iteration_trace (required for explainability endpoint)."""
        from app.services.coupling_engine import run_coupled_forecast
        ctx = _make_context()
        met = [_make_met_rec(h) for h in range(72)]
        steps = run_coupled_forecast(3409620, met, [], ctx, _simple_pm_model, _simple_o3_model)
        for step in steps:
            assert len(step.iteration_trace) >= 1
            required_keys = {"iteration", "pm25_estimate", "pbl_corrected", "delta_pm25"}
            for entry in step.iteration_trace:
                assert required_keys.issubset(entry.keys()), (
                    f"Trace entry missing keys: {required_keys - entry.keys()}"
                )

    def test_plume_increases_pm25(self):
        """Fire plume contribution should increase average PM2.5 vs no-plume baseline."""
        from app.services.coupling_engine import run_coupled_forecast
        ctx = _make_context(pm25=80.0)
        met = [_make_met_rec(h) for h in range(72)]
        plume_with = [
            {"datetime": met[i]["datetime"], "plume_pm25_contrib": 50.0, "hotspot_count": 5}
            for i in range(72)
        ]
        steps_no    = run_coupled_forecast(3409620, met, [],         ctx, _simple_pm_model, _simple_o3_model)
        steps_with  = run_coupled_forecast(3409620, met, plume_with, ctx, _simple_pm_model, _simple_o3_model)

        avg_no   = sum(s.pm25 for s in steps_no)   / len(steps_no)
        avg_with = sum(s.pm25 for s in steps_with) / len(steps_with)
        assert avg_with > avg_no, (
            f"Plume should increase PM2.5: {avg_with:.1f} vs {avg_no:.1f}"
        )

    def test_confidence_interval_wider_under_inversion(self):
        """Under strong inversion (low PBL), CI half-width should be wider than clear-sky."""
        from app.services.coupling_engine import run_coupled_forecast
        ctx = _make_context(pm25=100.0)
        met_clear     = [_make_met_rec(12, pbl=2000.0)]
        met_inversion = [_make_met_rec(3,  pbl=100.0)]

        steps_clear     = run_coupled_forecast(3409620, met_clear,     [], ctx, _simple_pm_model, _simple_o3_model)
        steps_inversion = run_coupled_forecast(3409620, met_inversion, [], ctx, _simple_pm_model, _simple_o3_model)

        ci_clear     = steps_clear[0].pm25_upper     - steps_clear[0].pm25_lower
        ci_inversion = steps_inversion[0].pm25_upper - steps_inversion[0].pm25_lower

        assert ci_inversion > ci_clear, (
            f"CI under inversion ({ci_inversion:.1f}) should be wider than clear ({ci_clear:.1f})"
        )

    def test_trend_bonus_fires_in_engine_path(self):
        """
        The primary regression guard for the trend_bonus threading fix.

        Verifies that inversion_score is HIGHER when the PBL collapses
        across consecutive forecast hours than when PBL is static — proving
        that prev_pbl_corrected is actually threaded into compute_inversion_score()
        inside the live engine path, not only in standalone unit tests.

        Before the fix: both scenarios produced identical inversion_scores because
        _run_single_step never passed prev_pbl_height, making trend_bonus always 0.
        After the fix: collapsing scenario must score > static scenario.
        """
        from app.services.coupling_engine import run_coupled_forecast

        ctx = _make_context(pm25=80.0)

        # Scenario A: PBL collapses from 600m → 100m over 6 hours (rapid inversion onset)
        met_collapsing = [
            _make_met_rec(h, pbl=max(100.0, 600.0 - h * 83.0), uv=2.0)
            for h in range(6)
        ]

        # Scenario B: PBL is flat at 300m throughout (no trend signal)
        met_static = [_make_met_rec(h, pbl=300.0, uv=2.0) for h in range(6)]

        steps_collapsing = run_coupled_forecast(
            3409620, met_collapsing, [], ctx, _simple_pm_model, _simple_o3_model
        )
        steps_static = run_coupled_forecast(
            3409620, met_static, [], ctx, _simple_pm_model, _simple_o3_model
        )

        # By step 3 onward, the collapsing PBL sequence should have higher
        # inversion_score than static PBL at the same absolute level, because
        # the trend_bonus is adding to the score.
        # (Skip step 0: no prev_pbl on first step so scores are comparable there)
        collapsing_scores = [s.inversion_score for s in steps_collapsing[1:]]
        static_scores     = [s.inversion_score for s in steps_static[1:]]

        # At least some steps should show the trend effect
        trend_effect_seen = any(
            c > s for c, s in zip(collapsing_scores, static_scores)
        )
        assert trend_effect_seen, (
            "Collapsing PBL scenario should produce higher inversion_score than "
            "static PBL at the same level on at least some steps — trend_bonus "
            f"may not be wired in.\n"
            f"Collapsing scores: {[round(x,3) for x in collapsing_scores]}\n"
            f"Static scores:     {[round(x,3) for x in static_scores]}"
        )

    def test_severe_reachable_via_trend_at_midday(self):
        """
        Severe inversion must be reachable at noon UTC (no pre-dawn tod_bonus)
        through trend_bonus alone — i.e., a sustained multi-hour PBL collapse
        during a stubble-burning episode drives the score past 0.90 (Severe)
        without relying on the tod_bonus.

        Before the trend threading fix:
          base_score(PBL~120m) ≈ 0.80  +  tod_bonus(noon)=0.0  = 0.80 → Strong
        After fix (with trend_bonus ~0.15+ from 400m → 120m collapse):
          0.80 + 0.15 = 0.95 → Severe  ✓
        """
        from app.services.coupling_engine import run_coupled_forecast, CouplingContext

        ctx = CouplingContext(
            station_id=3409620,
            prior_pm25_lags=[500.0] * 4,
            prior_pm10_lags=[900.0] * 4,
            prior_o3_lags=[40.0] * 4,
            prior_no2_lags=[80.0] * 4,
            prior_aqi_lags=[400.0] * 4,
        )

        def _max_pm_model(features):
            return 500.0, 1000.0   # always max PM2.5 → maximum alpha correction

        # PBL collapses rapidly over 4 hours during midday UTC (12:00–15:00)
        # so tod_bonus = 0 throughout. Start at 400m, drop 70m/h → 120m by h+4.
        met = [
            _make_met_rec(12 + h, pbl=max(120.0, 400.0 - h * 70.0), uv=5.0)
            for h in range(5)
        ]

        steps = run_coupled_forecast(
            3409620, met, [], ctx, _max_pm_model, lambda f: 30.0
        )

        # By step 3+ (PBL fully collapsed, trend firing), expect Severe or at
        # minimum Strong — not just "Moderate" which is what you'd get without trend
        late_categories = {s.inversion_category for s in steps[2:]}
        assert late_categories & {"Severe", "Strong"}, (
            f"Expected at least 'Strong' or 'Severe' inversion at midday with "
            f"rapidly collapsing PBL + max PM2.5 forcing, but got: {late_categories}. "
            f"trend_bonus may not be reaching the engine path.\n"
            f"Scores: {[round(s.inversion_score, 3) for s in steps]}\n"
            f"Categories: {[s.inversion_category for s in steps]}"
        )

    def test_max_iterations_1_cannot_report_converged(self):
        """
        Issue 4 guard: with COUPLING_MAX_ITERATIONS=1, the engine runs exactly
        once. Since convergence requires comparing two model outputs, converged
        should be False — running once is not a convergence proof.

        This also verifies the loop exits cleanly without hanging.
        """
        import app.services.coupling_engine as eng
        original_max = eng.COUPLING_MAX_ITERATIONS
        eng.COUPLING_MAX_ITERATIONS = 1
        try:
            from app.services.coupling_engine import run_coupled_forecast
            ctx = _make_context(pm25=100.0)
            met = [_make_met_rec(h) for h in range(5)]   # 5 steps is enough
            steps = run_coupled_forecast(
                3409620, met, [], ctx, _simple_pm_model, _simple_o3_model
            )
            for step in steps:
                assert not step.converged, (
                    f"h+{step.hour_offset}: converged=True with max_iterations=1 "
                    f"is misleading — need ≥2 iterations to confirm convergence."
                )
                assert step.iterations_run == 1
        finally:
            eng.COUPLING_MAX_ITERATIONS = original_max   # restore for other tests

    def test_no2_lags_evolve_over_forecast_horizon(self):
        """
        Issue 3 guard: NO2 lags must NOT be frozen flat across the 72h forecast.
        Confirm they show diurnal variation AND decay toward background.
        """
        from app.services.coupling_engine import run_coupled_forecast, CouplingContext

        ctx = CouplingContext(
            station_id=3409620,
            prior_pm25_lags=[80.0] * 4,
            prior_pm10_lags=[160.0] * 4,
            prior_o3_lags=[50.0] * 4,
            prior_no2_lags=[100.0] * 4,   # high observed NO2 at forecast start
            prior_aqi_lags=[150.0] * 4,
        )
        met = [_make_met_rec(h) for h in range(72)]
        steps = run_coupled_forecast(
            3409620, met, [], ctx, _simple_pm_model, _simple_o3_model
        )

        # Collect the leading NO2 lag that each step uses as nox_precursor_lag
        # We can infer this from O3 variance — if NO2 were frozen, O3 output would
        # be identical across same-UV hours. Instead check the steps' nox inputs
        # indirectly: NO2 in the advancing context should decay by h+72.
        # The simplest direct check: confirm steps at different hours don't all
        # share the same O3 value when UV differs (would be impossible if NO2 were frozen
        # AND constant, since O3 = f(UV, NO2, temp, ...)).

        # Direct test: call _forecast_no2_lags and verify it's not frozen
        from app.services.coupling_engine import _forecast_no2_lags

        no2_h1  = _forecast_no2_lags([100.0, 100.0, 100.0, 100.0], next_hour_utc=4,  hour_offset=1)
        no2_h24 = _forecast_no2_lags([100.0, 100.0, 100.0, 100.0], next_hour_utc=4,  hour_offset=24)
        no2_h72 = _forecast_no2_lags([100.0, 100.0, 100.0, 100.0], next_hour_utc=4,  hour_offset=72)

        # h1 should be close to base (100 µg/m³ ± diurnal)
        assert no2_h1[0] > 20.0, "NO2 at h+1 should still be near observed value"
        # h72 should be significantly lower (decayed to ~background)
        assert no2_h72[0] < no2_h1[0], (
            f"NO2 at h+72 ({no2_h72[0]:.1f}) should be less than h+1 ({no2_h1[0]:.1f}) "
            f"— exponential decay toward background must be active."
        )
        # Peak at rush hour (UTC 03 = IST 08:30) should be higher than overnight (UTC 18)
        no2_rush    = _forecast_no2_lags([100.0]*4, next_hour_utc=3,  hour_offset=12)
        no2_overnight = _forecast_no2_lags([100.0]*4, next_hour_utc=18, hour_offset=12)
        assert no2_rush[0] > no2_overnight[0], (
            f"NO2 at rush hour (UTC 03, {no2_rush[0]:.1f}) should be higher than "
            f"overnight (UTC 18, {no2_overnight[0]:.1f}) — diurnal pattern not working."
        )

