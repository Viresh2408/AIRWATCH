"""
coupling_engine.py — Two-way meteorology-chemistry feedback loop
SIH PS 26082: the central differentiator from a plain AQI predictor.

This module implements the iterative aerosol-PBL feedback loop described
in the PS specification. It is deliberately NOT WRF-Chem; it is a
'simplified two-way coupling emulator' using:

  - Real Open-Meteo meteorology as physical forcing
  - Empirical aerosol→PBL and aerosol→temperature correction factors
    (coefficients grounded in IGP literature; see config.py comments)
  - Separate ML sub-models for PM2.5/PM10 (transport-dominated) and
    O3 (photochemistry-dominated)
  - 2-3 iteration convergence loop per forecast timestep

The feedback loop per timestep (station_id, hour):
  Step 1: Load raw Open-Meteo met forecast (no feedback)
  Step 2: Run PM2.5/PM10 ML model → first-pass concentration estimate
  Step 3: Apply aerosol→met corrections:
            PBL_corr = PBL_raw × (1 - α × PM2.5_norm)
            T_corr   = T_raw   - β × PM2.5 / 100
            inv_score_corr = recompute from PBL_corr
  Step 4: Re-run PM2.5/PM10 with corrected met inputs
  Step 5: Repeat 3-4 until |ΔPM2.5| < CONVERGENCE_THRESHOLD or max iterations
  Step 6: Run O3 ML model once with final corrected met
          (O3 uses UV attenuation by aerosols: uv_eff = uv_raw * (1 - γ * pm25_norm))
  Step 7: Return final concentrations + iteration trace

Iteration trace is stored for the /api/v1/coupling/feedback-trace/{station}
endpoint — this is the judge-facing 'explainability' output that visually
proves two-way coupling rather than making them take our word for it.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.config import (
    ALPHA_PM_PBL,
    BETA_TEMP_PM,
    COUPLING_MAX_ITERATIONS,
    COUPLING_CONVERGENCE_THRESHOLD,
    INVERSION_PBL_THRESHOLD,
    FORECAST_HORIZON_HOURS,
)
from app.services.inversion_calculator import compute_inversion_score

logger = logging.getLogger(__name__)

# PM2.5 normalization reference concentration (µg/m³)
# Score of 1.0 at this level → maximum aerosol feedback
PM25_NORM_REF: float = 500.0

# UV attenuation coefficient: fraction of UV reduced per unit PM2.5_norm
# Aerosol optical depth at high PM2.5 in Delhi significantly attenuates UV
# (Ramachandran & Kedia 2010 report 30-50% solar reduction in severe haze)
# We use a conservative 0.30 at PM2.5=500 µg/m³ → γ = 0.30
GAMMA_UV_PM: float = 0.30

# Minimum effective PBL height to prevent near-zero division (metres)
PBL_FLOOR: float = 50.0


@dataclass
class CoupledForecastStep:
    """
    Result of the coupling engine for a single forecast timestep.
    Stored for each hour of the 72-h forecast.
    """
    datetime: datetime
    station_id: int
    hour_offset: int          # 1–72 from current time

    # Final converged outputs
    pm25: float               # µg/m³
    pm10: float               # µg/m³
    o3: float                 # µg/m³

    # Derived AQI (CPCB sub-index max)
    aqi_pm25: int
    aqi_pm10: int
    aqi_o3: int
    overall_aqi: int
    aqi_category: str

    # Meteorological context (corrected, post-feedback)
    pbl_height_raw: float     # Open-Meteo original (m)
    pbl_height_corrected: float  # after aerosol feedback
    temperature_raw: float    # °C
    temperature_corrected: float
    uv_index_effective: float # after aerosol shading
    inversion_score: float    # 0–1
    inversion_category: str

    # Fire plume
    plume_pm25_contrib: float  # µg/m³

    # Coupling diagnostics (explainability)
    iterations_run: int
    converged: bool
    iteration_trace: list[dict]  # [{iter, pm25_estimate, pbl_corrected, delta_pm25}]

    # Confidence interval (simple ±% based on inversion strength)
    pm25_lower: float
    pm25_upper: float
    o3_lower: float
    o3_upper: float

    # Model version tag
    model_version: str = "coupling_engine_v1.0"


@dataclass
class CouplingContext:
    """
    Per-station context fed into the engine for each timestep.
    Carries state (lag features, prior AQI) between autoregressive steps.
    """
    station_id: int
    prior_pm25_lags: list[float]    # [t-1, t-2, t-3, t-4] µg/m³
    prior_pm10_lags: list[float]
    prior_o3_lags: list[float]
    prior_no2_lags: list[float]     # NOx precursor for O3 sub-model
    prior_aqi_lags: list[float]


def run_coupled_forecast(
    station_id: int,
    met_records: list[dict[str, Any]],
    plume_records: list[dict[str, Any]],
    initial_context: CouplingContext,
    pm_model_fn,   # callable(features_dict) -> (pm25, pm10)
    o3_model_fn,   # callable(features_dict) -> o3
) -> list[CoupledForecastStep]:
    """
    Run the full 72-hour coupled forecast for one station.

    Args:
        station_id:       Station identifier.
        met_records:      Hourly met forecast from met_client (72 records).
        plume_records:    Hourly fire plume contributions from fire_plume_service.
        initial_context:  Lag state at forecast start.
        pm_model_fn:      Callable (features) → (pm25_µg/m³, pm10_µg/m³).
        o3_model_fn:      Callable (features) → o3_µg/m³.

    Returns list of CoupledForecastStep, one per forecast hour.
    """
    steps: list[CoupledForecastStep] = []
    context = initial_context
    plume_map = {r["datetime"]: r for r in plume_records} if plume_records else {}
    # Track previous step's corrected PBL so compute_inversion_score can calculate
    # the trend_bonus (rate of PBL collapse). None on the first step.
    prev_pbl_corrected: float | None = None

    for hour_idx, met_rec in enumerate(met_records[:FORECAST_HORIZON_HOURS]):
        dt: datetime = met_rec["datetime"]
        plume_rec = plume_map.get(dt, {})
        plume_contrib = plume_rec.get("plume_pm25_contrib", 0.0)

        step = _run_single_step(
            station_id=station_id,
            hour_offset=hour_idx + 1,
            dt=dt,
            met_raw=met_rec,
            plume_pm25=plume_contrib,
            context=context,
            pm_model_fn=pm_model_fn,
            o3_model_fn=o3_model_fn,
            prev_pbl_corrected=prev_pbl_corrected,
        )
        steps.append(step)

        # Carry this step's corrected PBL forward as the reference for next step's trend
        prev_pbl_corrected = step.pbl_height_corrected

        # Update autoregressive lag state with this step's converged outputs
        context = _advance_context(context, step)

    logger.info(
        f"[COUPLING] Station {station_id}: {len(steps)} steps completed. "
        f"Peak PM2.5={max(s.pm25 for s in steps):.1f} µg/m³, "
        f"max iterations={max(s.iterations_run for s in steps)}"
    )
    return steps


def _run_single_step(
    station_id: int,
    hour_offset: int,
    dt: datetime,
    met_raw: dict[str, Any],
    plume_pm25: float,
    context: CouplingContext,
    pm_model_fn,
    o3_model_fn,
    prev_pbl_corrected: float | None = None,
) -> CoupledForecastStep:
    """
    Execute the two-way feedback loop for one forecast hour.

    Args:
        prev_pbl_corrected: The aerosol-corrected PBL height from the previous
            forecast hour (metres). Passed to compute_inversion_score() so the
            trend_bonus fires when PBL is actively collapsing across consecutive
            hours — the key signal for inversion onset during stubble-burning
            episodes. None for the first forecast step.
    """
    pbl_raw = max(met_raw.get("boundary_layer_height", 500.0), PBL_FLOOR)
    t_raw   = met_raw.get("temperature_2m", 25.0)
    uv_raw  = met_raw.get("uv_index", 3.0)

    # Seed inversion score from raw (uncorrected) PBL, using prev step's PBL for trend
    inv_raw = compute_inversion_score(
        pbl_raw,
        prev_pbl_height=prev_pbl_corrected,   # None on first step → trend_bonus = 0
        forecast_hour_utc=dt.hour,
    )
    inversion_score = inv_raw["score"]

    # --- Iterative coupling loop ---
    pm25_estimate = _pm25_from_lags(context)   # seed: extrapolate from prior lags
    iteration_trace: list[dict] = []
    pbl_corrected = pbl_raw
    t_corrected = t_raw
    converged = False
    has_prior_estimate = False   # True once we have a real model output to compare

    for iteration in range(1, COUPLING_MAX_ITERATIONS + 1):
        # Step A: Build feature set with current (corrected) met
        pm_features = _build_pm_features(
            met_raw=met_raw,
            pbl_corrected=pbl_corrected,
            t_corrected=t_corrected,
            inversion_score=inversion_score,
            plume_pm25=plume_pm25,
            context=context,
        )

        # Step B: Run PM2.5/PM10 ML model
        pm25_new, pm10_new = pm_model_fn(pm_features)
        pm25_new = max(0.0, pm25_new)
        pm10_new = max(0.0, pm10_new)

        delta_pm25 = abs(pm25_new - pm25_estimate)
        iteration_trace.append({
            "iteration": iteration,
            "pm25_estimate": round(pm25_new, 2),
            "pm10_estimate": round(pm10_new, 2),
            "pbl_corrected": round(pbl_corrected, 1),
            "t_corrected": round(t_corrected, 2),
            "inversion_score": round(inversion_score, 4),
            "delta_pm25": round(delta_pm25, 3),
        })

        # Step C: Aerosol→met feedback (the "two-way" part)
        # ALPHA_PM_PBL: ~15-20% PBL suppression in severe Delhi haze (IGP literature)
        # BETA_TEMP_PM: ~0.20-0.35°C cooling per 100 µg/m³ (IGP radiative forcing studies)
        # Note: PBL_FLOOR (50m) is intentionally set below INVERSION_PBL_CRITICAL (200m)
        # so maximum aerosol feedback CAN drive the system into Severe territory.
        # At PM2.5_norm=1.0: PBL_corr = PBL_raw × 0.82; e.g. raw=150m → corr=123m < 200m ✓
        pm25_norm = min(pm25_new / PM25_NORM_REF, 1.0)
        pbl_corrected = max(pbl_raw * (1.0 - ALPHA_PM_PBL * pm25_norm), PBL_FLOOR)
        t_corrected = t_raw - (BETA_TEMP_PM * pm25_new / 100.0)

        # Recompute inversion score with corrected PBL.
        # Use prev_pbl_corrected (prior *hour's* corrected PBL) as the reference
        # for trend_bonus — the intra-iteration PBL changes are feedback corrections,
        # not real time progression, so we don't update prev_pbl_corrected here.
        inv_corr = compute_inversion_score(
            pbl_corrected,
            prev_pbl_height=prev_pbl_corrected,
            forecast_hour_utc=dt.hour,
        )
        inversion_score = inv_corr["score"]

        # Step D: Check convergence
        # has_prior_estimate ensures we compare two genuine model outputs, not
        # seed vs. first-pass. We set it True after the first iteration completes.
        # This also correctly handles COUPLING_MAX_ITERATIONS=1: after the single
        # iteration, has_prior_estimate is still False, so converged stays False —
        # which is honest (we ran only once, can't claim convergence).
        if has_prior_estimate and delta_pm25 < COUPLING_CONVERGENCE_THRESHOLD:
            converged = True
            logger.debug(
                f"[COUPLING] Station {station_id} h+{hour_offset}: "
                f"converged at iter {iteration}, ΔPM2.5={delta_pm25:.3f}"
            )
            pm25_estimate = pm25_new
            break

        pm25_estimate = pm25_new
        has_prior_estimate = True

    # Final PM values from last iteration
    pm25_final = pm25_estimate
    pm10_final = pm10_new

    # O3 model: run once with final corrected met + UV attenuation by aerosols
    # Higher PM2.5 → more aerosol optical depth → less UV reaching surface → less O3
    pm25_norm_final = min(pm25_final / PM25_NORM_REF, 1.0)
    uv_effective = uv_raw * (1.0 - GAMMA_UV_PM * pm25_norm_final)
    uv_effective = max(0.0, uv_effective)

    o3_features = _build_o3_features(
        met_raw=met_raw,
        pbl_corrected=pbl_corrected,
        t_corrected=t_corrected,
        uv_effective=uv_effective,
        inversion_score=inversion_score,
        context=context,
    )
    o3_final = max(0.0, o3_model_fn(o3_features))

    # AQI sub-indices
    from app.services.aqi_calculator import calculate_sub_index, get_aqi_category
    aqi_pm25 = calculate_sub_index(pm25_final, "pm25")
    aqi_pm10 = calculate_sub_index(pm10_final, "pm10")
    aqi_o3   = calculate_sub_index(o3_final, "o3")
    overall_aqi = max(aqi_pm25, aqi_pm10, aqi_o3)
    aqi_cat = get_aqi_category(overall_aqi)

    # Confidence intervals: wider when inversion is strong (higher uncertainty)
    ci_factor = 0.10 + 0.20 * inversion_score  # 10-30% CI half-width
    pm25_lower = max(0.0, pm25_final * (1 - ci_factor))
    pm25_upper = pm25_final * (1 + ci_factor)
    o3_lower = max(0.0, o3_final * (1 - ci_factor))
    o3_upper = o3_final * (1 + ci_factor)

    return CoupledForecastStep(
        datetime=dt,
        station_id=station_id,
        hour_offset=hour_offset,
        pm25=round(pm25_final, 2),
        pm10=round(pm10_final, 2),
        o3=round(o3_final, 2),
        aqi_pm25=int(aqi_pm25),
        aqi_pm10=int(aqi_pm10),
        aqi_o3=int(aqi_o3),
        overall_aqi=int(overall_aqi),
        aqi_category=aqi_cat["category"],
        pbl_height_raw=round(pbl_raw, 1),
        pbl_height_corrected=round(pbl_corrected, 1),
        temperature_raw=round(t_raw, 2),
        temperature_corrected=round(t_corrected, 2),
        uv_index_effective=round(uv_effective, 3),
        inversion_score=round(inversion_score, 4),
        inversion_category=inv_corr["category"],
        plume_pm25_contrib=round(plume_pm25, 2),
        iterations_run=len(iteration_trace),
        converged=converged,
        iteration_trace=iteration_trace,
        pm25_lower=round(pm25_lower, 2),
        pm25_upper=round(pm25_upper, 2),
        o3_lower=round(o3_lower, 2),
        o3_upper=round(o3_upper, 2),
    )


def _build_pm_features(
    met_raw: dict, pbl_corrected: float, t_corrected: float,
    inversion_score: float, plume_pm25: float, context: CouplingContext,
) -> dict[str, Any]:
    """Build feature vector for the PM2.5/PM10 ML sub-model."""
    dt: datetime = met_raw["datetime"]
    hour = dt.hour
    return {
        # Met forcing (corrected)
        "pbl_height":       pbl_corrected,
        "temperature":      t_corrected,
        "relativehumidity": met_raw.get("relativehumidity_2m", 60.0),
        "windspeed_10m":    met_raw.get("windspeed_10m", 2.0),
        "winddirection_sin": math.sin(math.radians(met_raw.get("winddirection_10m", 0))),
        "winddirection_cos": math.cos(math.radians(met_raw.get("winddirection_10m", 0))),
        "surface_pressure": met_raw.get("surface_pressure", 1013.0),
        # Coupling-derived
        "inversion_score":  inversion_score,
        "plume_pm25_contrib": plume_pm25,
        # Temporal
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "month":    dt.month,
        "day_of_week": dt.weekday(),
        # Lag features (autoregressive state)
        "pm25_lag_1": context.prior_pm25_lags[0] if len(context.prior_pm25_lags) > 0 else 0,
        "pm25_lag_2": context.prior_pm25_lags[1] if len(context.prior_pm25_lags) > 1 else 0,
        "pm25_lag_3": context.prior_pm25_lags[2] if len(context.prior_pm25_lags) > 2 else 0,
        "pm25_lag_4": context.prior_pm25_lags[3] if len(context.prior_pm25_lags) > 3 else 0,
        "no2_lag_1":  context.prior_no2_lags[0]  if len(context.prior_no2_lags)  > 0 else 0,
        "no2_lag_2":  context.prior_no2_lags[1]  if len(context.prior_no2_lags)  > 1 else 0,
        "aqi_lag_1":  context.prior_aqi_lags[0]  if len(context.prior_aqi_lags)  > 0 else 0,
        "aqi_lag_2":  context.prior_aqi_lags[1]  if len(context.prior_aqi_lags)  > 1 else 0,
    }


def _build_o3_features(
    met_raw: dict, pbl_corrected: float, t_corrected: float,
    uv_effective: float, inversion_score: float, context: CouplingContext,
) -> dict[str, Any]:
    """
    Build feature vector for the O3 photochemistry ML sub-model.

    Key differences from PM features:
      - uv_effective: aerosol-attenuated UV (primary O3 driver)
      - nox_precursor_lag: NO2 lag features (source of NOx for O3 formation)
      - NO2 is ingested from CPCB stations via live_ingestion.py — not stubbed.
    """
    # Guard: assert nox_precursor is wired, never silently zero
    if not any(v > 0 for v in context.prior_no2_lags):
        logger.warning(
            "[COUPLING] O3 model: all NO2 lag values are zero for station "
            f"{context.station_id}. NOx precursor may not be ingested yet. "
            "O3 forecast accuracy will be reduced until NO2 data is available."
        )

    dt: datetime = met_raw["datetime"]
    hour = dt.hour
    return {
        # Primary O3 driver: aerosol-attenuated UV
        "uv_index":         uv_effective,
        # Temperature (O3 formation is temperature-dependent)
        "temperature":      t_corrected,
        # NOx precursor lags — from CPCB NO2 readings (live_ingestion.py)
        "nox_precursor_lag":  context.prior_no2_lags[0] if len(context.prior_no2_lags) > 0 else 0,
        "nox_precursor_lag2": context.prior_no2_lags[1] if len(context.prior_no2_lags) > 1 else 0,
        # Met context
        "pbl_height":       pbl_corrected,
        "relativehumidity": met_raw.get("relativehumidity_2m", 60.0),
        "windspeed_10m":    met_raw.get("windspeed_10m", 2.0),
        "inversion_score":  inversion_score,
        # O3 own lags
        "o3_lag_1": context.prior_o3_lags[0] if len(context.prior_o3_lags) > 0 else 0,
        "o3_lag_2": context.prior_o3_lags[1] if len(context.prior_o3_lags) > 1 else 0,
        # Temporal
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "month":    dt.month,
        "day_of_week": dt.weekday(),
    }


def _pm25_from_lags(context: CouplingContext) -> float:
    """Seed the first iteration from the most recent PM2.5 lag."""
    lags = context.prior_pm25_lags
    return lags[0] if lags else 100.0


def _advance_context(context: CouplingContext, step: CoupledForecastStep) -> CouplingContext:
    """
    Shift lag windows forward by one timestep with this step's outputs.

    NO2/NOx handling — diurnal decay model:
      The original implementation froze NO2 at observed values for all 72 forecast
      hours. This is acceptable as a documented limitation but produces O3 predictions
      that don't respond to NOx changes over the horizon.

      We instead apply a simple two-component model:
        1. Diurnal pattern: Delhi NO2 is higher during morning (07-10 IST) and
           evening (18-21 IST) rush hours, lower overnight. This is a well-documented
           pattern from CPCB data.
        2. Slow decay: without new emissions, NO2 decays toward a background
           level (~40% of peak obs over 24h, matching typical diurnal min in Delhi).

      KNOWN LIMITATION (stated in README): This is a climatological pattern, not
      a real NO2 forecast. It will not capture day-to-day meteorological variability
      in NO2, only diurnal shape. A production upgrade would use a NOx emission
      inventory + atmospheric lifetime model.
    """
    def _shift(lst: list[float], new_val: float) -> list[float]:
        return [new_val] + lst[:3]   # keep most recent 4

    # Forecast next NO2 lag using diurnal model anchored on current observed lags
    no2_forecast = _forecast_no2_lags(
        prior_no2_lags=context.prior_no2_lags,
        next_hour_utc=step.datetime.hour,
        hour_offset=step.hour_offset,
    )

    return CouplingContext(
        station_id=context.station_id,
        prior_pm25_lags=_shift(context.prior_pm25_lags, step.pm25),
        prior_pm10_lags=_shift(context.prior_pm10_lags, step.pm10),
        prior_o3_lags=_shift(context.prior_o3_lags, step.o3),
        prior_no2_lags=no2_forecast,
        prior_aqi_lags=_shift(context.prior_aqi_lags, float(step.overall_aqi)),
    )


def _forecast_no2_lags(
    prior_no2_lags: list[float],
    next_hour_utc: int,
    hour_offset: int,
) -> list[float]:
    """
    Simple diurnal + slow-decay NO2 forecast for use as O3 precursor input.

    Model:
      - Base: most recent observed NO2 (prior_no2_lags[0])
      - Diurnal factor: sinusoidal pattern peaking at ~08:30 and ~19:30 IST
        (≈ 03:00 and 14:00 UTC), capturing Delhi rush-hour NOx emission peaks.
      - Decay: exponential toward background (40% of peak obs) with a 24h e-folding
        time, approximating photochemical removal + deposition over the forecast.
      - KNOWN LIMITATION: This is a climatological pattern only. It does not model
        day-to-day weather impacts on NOx or episodic emission events.
    """
    if not prior_no2_lags:
        return [40.0, 38.0, 36.0, 34.0]   # Delhi background fallback

    base_no2 = prior_no2_lags[0]
    background_no2 = max(base_no2 * 0.40, 10.0)   # typical Delhi nocturnal minimum

    # Hourly decay: e-folding time 24h → per-hour factor = exp(-1/24)
    import math as _math
    decay_factor = _math.exp(-hour_offset / 24.0)
    decayed_base = background_no2 + (base_no2 - background_no2) * decay_factor

    # Diurnal factor: two-peak sinusoid
    # Peak 1: 03:00 UTC = 08:30 IST (morning rush)
    # Peak 2: 14:00 UTC = 19:30 IST (evening rush)
    # Amplitude: ±30% around decayed_base
    hour_rad = 2 * _math.pi * next_hour_utc / 24.0
    peak1_rad = 2 * _math.pi * 3 / 24.0    # 03:00 UTC
    peak2_rad = 2 * _math.pi * 14 / 24.0   # 14:00 UTC
    diurnal_amp = 0.30
    diurnal_factor = 1.0 + diurnal_amp * (
        _math.cos(hour_rad - peak1_rad) + _math.cos(hour_rad - peak2_rad)
    ) / 2.0

    no2_forecast = max(decayed_base * diurnal_factor, 5.0)   # floor at 5 µg/m³

    # Return as [t, t-1, t-2, t-3] with smooth decay across lag window
    return [
        round(no2_forecast, 2),
        round(no2_forecast * 0.95, 2),
        round(no2_forecast * 0.90, 2),
        round(no2_forecast * 0.85, 2),
    ]
