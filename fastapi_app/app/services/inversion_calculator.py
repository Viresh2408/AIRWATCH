"""
inversion_calculator.py — Atmospheric inversion strength index for AirWatch Delhi NCR
SIH PS 26082: computes a normalized inversion score [0.0–1.0] per forecast hour.

Physics rationale:
  A shallow or collapsing PBL is the primary observational signal of a temperature
  inversion trapping surface pollutants. During Delhi winter severe pollution episodes
  the PBL height regularly drops below 200 m overnight (Srivastava et al. 2021;
  Kumar et al. 2020, ACP). Rather than requiring a vertical radiosonde profile
  (unavailable in real-time without ERA5), we use:

    1. PBL height absolute value  — primary signal
    2. PBL height trend           — a rapidly shrinking PBL implies inversion onset
    3. Time-of-day modifier       — pre-dawn (01:00–06:00 IST) is highest-risk window

  The combined score feeds into the coupling engine to modulate pollutant trapping
  and is exposed via the /api/v1/coupling/inversion/{station} endpoint.

Score definition:
  base_score   = clamp(1 - pbl / THRESHOLD, 0, 1)   [lower PBL → higher score]
  trend_bonus  = clamp(-dpbl / TREND_SCALE, 0, 0.2)  [falling PBL adds up to 0.2]
  tod_bonus    = 0.10 if pre-dawn hours else 0.0
  raw_score    = base_score + trend_bonus + tod_bonus
  final_score  = clamp(raw_score, 0.0, 1.0)

Category thresholds (for API/UI):
  [0.0 – 0.25)  → "None"
  [0.25 – 0.50) → "Weak"
  [0.50 – 0.75) → "Moderate"
  [0.75 – 0.90) → "Strong"
  [0.90 – 1.00] → "Severe"  (Delhi worst-case: PBL <100 m, fast collapse)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import (
    INVERSION_PBL_THRESHOLD,
    INVERSION_PBL_CRITICAL,
)

logger = logging.getLogger(__name__)

# Inversion score category thresholds
INVERSION_CATEGORIES: list[tuple[float, str]] = [
    (0.0,  "None"),
    (0.25, "Weak"),
    (0.50, "Moderate"),
    (0.75, "Strong"),
    (0.90, "Severe"),
]

# How fast a PBL drop (m/h) adds maximum trend bonus (0.2)
# 200 m/h collapse rate → full trend bonus (observed during extreme IGP events)
TREND_SCALE: float = 200.0

# IST = UTC+5:30; pre-dawn risk window (local hours 01–06)
PREDAWN_UTC_HOURS: set[int] = {19, 20, 21, 22, 23, 0}  # 01–06 IST ≈ 19:30–00:30 UTC


def compute_inversion_score(
    pbl_height: float,
    prev_pbl_height: float | None = None,
    forecast_hour_utc: int | None = None,
) -> dict[str, Any]:
    """
    Compute the inversion strength score for a single timestep.

    Args:
        pbl_height:       PBL height in metres from Open-Meteo.
        prev_pbl_height:  PBL height at the previous hour (for trend calc).
                          Pass None if unavailable (first step).
        forecast_hour_utc: UTC hour (0–23) for time-of-day modifier.

    Returns dict with:
        score      (float, 0.0–1.0)
        category   (str)
        pbl_height (float)
        dpbl_dt    (float | None)  — rate of change m/h (negative = falling)
        components (dict)          — breakdown for explainability
    """
    pbl = max(pbl_height, 0.0)

    # 1. Base score: linear from THRESHOLD down to CRITICAL gives 0 → 0.8;
    #    below CRITICAL the score is capped at 1.0.
    if pbl >= INVERSION_PBL_THRESHOLD:
        base_score = 0.0
    elif pbl <= INVERSION_PBL_CRITICAL:
        base_score = 0.8
    else:
        # Linear interpolation between CRITICAL (0.8) and THRESHOLD (0.0)
        frac = (INVERSION_PBL_THRESHOLD - pbl) / (INVERSION_PBL_THRESHOLD - INVERSION_PBL_CRITICAL)
        base_score = frac * 0.8

    # 2. Trend bonus: rapidly collapsing PBL adds up to +0.2
    dpbl = None
    trend_bonus = 0.0
    if prev_pbl_height is not None:
        dpbl = pbl - float(prev_pbl_height)   # negative means PBL is shrinking
        if dpbl < 0:
            trend_bonus = min(0.2, (-dpbl) / TREND_SCALE)

    # 3. Pre-dawn time-of-day bonus (+0.10)
    tod_bonus = 0.0
    if forecast_hour_utc is not None and forecast_hour_utc in PREDAWN_UTC_HOURS:
        tod_bonus = 0.10

    raw_score = base_score + trend_bonus + tod_bonus
    final_score = max(0.0, min(1.0, raw_score))

    category = _score_to_category(final_score)

    logger.debug(
        f"[INV] PBL={pbl:.0f}m dpbl={dpbl} base={base_score:.3f} "
        f"trend={trend_bonus:.3f} tod={tod_bonus:.2f} → score={final_score:.3f} [{category}]"
    )

    return {
        "score": round(final_score, 4),
        "category": category,
        "pbl_height": pbl,
        "dpbl_dt": round(dpbl, 1) if dpbl is not None else None,
        "components": {
            "base_score": round(base_score, 4),
            "trend_bonus": round(trend_bonus, 4),
            "tod_bonus": round(tod_bonus, 4),
        },
    }


def compute_inversion_timeline(met_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Compute the inversion score for a full sequence of hourly met records.

    Args:
        met_records: list of dicts from met_client.fetch_met_forecast(),
                     each with 'boundary_layer_height' and 'datetime'.

    Returns list of dicts with all fields from compute_inversion_score()
    plus 'datetime'.
    """
    results: list[dict[str, Any]] = []
    prev_pbl: float | None = None

    for rec in met_records:
        pbl = rec.get("boundary_layer_height", 0.0)
        dt: datetime = rec.get("datetime")

        hour_utc = dt.hour if isinstance(dt, datetime) else None

        inv = compute_inversion_score(
            pbl_height=pbl,
            prev_pbl_height=prev_pbl,
            forecast_hour_utc=hour_utc,
        )
        inv["datetime"] = dt.isoformat() if dt else None
        results.append(inv)
        prev_pbl = pbl

    logger.info(
        f"[INV] Timeline computed for {len(results)} hours. "
        f"Peak score: {max((r['score'] for r in results), default=0):.3f}"
    )
    return results


def _score_to_category(score: float) -> str:
    """Map inversion score to category string."""
    category = "None"
    for threshold, cat in INVERSION_CATEGORIES:
        if score >= threshold:
            category = cat
    return category
