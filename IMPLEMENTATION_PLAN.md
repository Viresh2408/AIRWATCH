# Implementation Plan
## Adapting AirWatch → Delhi NCR Coupled Weather-Chemistry AQI Forecasting System
### For SIH PS 26082

---

## 0. Scoping decision (read this first)

Running actual **WRF-Chem** in a hackathon is not feasible — it needs HPC clusters and multi-day runtimes. The realistic, judge-defensible approach is a **simplified two-way coupling emulator**:

- Use real meteorology (forecast + reanalysis) as physical forcing instead of pure historical AQI lags.
- Explicitly compute an **inversion/PBL index** and a **stubble-fire plume contribution**, and feed them into the pollutant model as first-class inputs — not implicit patterns an XGBoost model might stumble on.
- Implement a genuine **feedback loop**: aerosol loading estimate → correction to next-step PBL height / surface temperature → re-run pollutant estimate. Even 2–3 iterations per timestep is enough to legitimately claim "two-way coupling," which is the PS's central ask.
- Be explicit in the README/pitch that this is a **hybrid ML-physics emulator**, not a WRF-Chem replacement. Judges reward honest, well-reasoned scoping over overclaiming.

Assumptions made below (adjust as needed): ~36–48 hour build window, small team (backend/ML + frontend + one person on data/domain), reusing AirWatch's FastAPI + React + SQLite/Postgres stack as plumbing.

---

## Phase 0 — Domain & data pivot (2–4 hrs)

**Goal:** move the whole system's geography and data sources from Navi Mumbai industrial belt → Delhi NCR.

- Swap station list: MPCB Thane-Belapur stations → CPCB/CAQM Delhi NCR stations (via [OpenAQ](https://openaq.org) or [CPCB CCR API](https://airquality.cpcb.gov.in/)).
- Identify and register access to:
  - **Open-Meteo Forecast API** — free, no key, and critically returns **boundary layer height**, wind u/v at multiple pressure levels, temperature, humidity. This is your fastest path to real PBL data without ERA5/CDS registration delays.
  - **NASA FIRMS** (VIIRS/MODIS active fire API) — Punjab/Haryana/UP fire hotspots for stubble-burning source data.
  - (Stretch) **ERA5 reanalysis via Copernicus CDS API** — for historical training data with vertical temperature profiles (better inversion strength calc), but registration/download can be slow — treat as optional.
- Update `.env` / config for Delhi NCR bounding box (lat ~28.4–28.9, lon ~76.8–77.5) instead of Navi Mumbai coordinates.

---

## Phase 1 — Meteorology-coupling core (the critical differentiator — prioritize this)

This is what separates you from a plain AQI predictor. Spend disproportionate time here.

- **`met_client.py`** — pulls PBL height, wind speed/direction at surface and upper levels, temperature, humidity from Open-Meteo for each station/grid cell, for both nowcast and 72h forecast horizon.
- **`inversion_calculator.py`** — computes an inversion-strength index from the vertical temperature gradient (surface vs ~925hPa proxy, or PBL height trend — a shrinking/very low PBL height overnight is your practical inversion signal). Output a normalized 0–1 "inversion strength" score per hour.
- **`fire_plume_service.py`** — fetches FIRMS hotspots over Punjab/Haryana, and for each hotspot does a simple wind-vector advection (a Gaussian-plume style calculation using forecast wind direction/speed at each timestep) to estimate arrival time and relative intensity of the plume over Delhi NCR grid cells. Doesn't need to be HYSPLIT-grade — a straight-line advection with a spreading cone is enough for a hackathon and is easy to explain to judges.
- **`coupling_engine.py`** — the two-way feedback loop, run per forecast timestep (hourly or 3-hourly):
  1. Meteorology forecast (no feedback yet) → forcing for step 2.
  2. Chemistry/ML model estimates PM2.5 and O3 using met forcing + fire-plume contribution + prior AQI.
  3. Aerosol loading estimate feeds back → apply an empirical PBL-suppression correction (higher PM2.5 → shallower next-step PBL, via a simple regression-fit correction factor, not a full radiative transfer solve) and adjust surface temperature slightly downward.
  4. Re-run step 2 with corrected met inputs; iterate 2–3 times or until change is below a threshold.
  5. Output final AQI + inversion index + plume contribution for that timestep.

---

## Phase 2 — Chemistry/ML model rebuild

- Replace the current flat XGBoost lag-feature set with an expanded feature set: PBL height, wind speed/direction, temperature, humidity, inversion index, fire-plume estimated contribution, prior AQI, time-of-day/season features.
- Split into **two sub-models**: PM2.5/PM10 (transport-dominated) and O3 (photochemistry-dominated — weight solar radiation/UV index and NOx availability, since O3 formation behaves very differently from particulate transport; don't reuse the PM2.5 pipeline as-is).
- Extend forecast horizon **48h → 72h**. Use either recursive multi-step XGBoost/LightGBM (predict t+1, feed forward) or direct multi-horizon models. If time allows, an LSTM/Temporal Fusion TFT improves multi-step coherence, but recursive XGBoost is a safe fallback under time pressure.

---

## Phase 3 — Backend/API extension

New/modified endpoints (FastAPI):

- `GET /api/v1/coupling/inversion/{station}` — inversion strength timeline
- `GET /api/v1/coupling/plume-forecast` — fire-plume arrival/intensity grid
- `GET /api/v1/aqi/forecast72/{station}` — 72h AQI forecast with confidence
- `GET /api/v1/coupling/feedback-trace/{station}` — the iteration trace of the feedback loop (met correction magnitude per iteration) — useful for judge-facing "explainability" panel

New DB tables: `met_readings`, `fire_hotspots`, `inversion_index`, and an extended `predictions` table (72h horizon, per-pollutant, confidence interval).

---

## Phase 4 — Frontend dashboard additions

- **Inversion strength gauge/timeline** component.
- **Plume dispersion map overlay**: fire hotspots + wind vector arrows + predicted PM2.5 contribution heatmap (Leaflet with a vector/heatmap layer is enough; deck.gl if you want it slicker).
- **72h forecast chart** (extend the existing Recharts 48h chart).
- **Coupling explainability panel**: shows met forcing input vs. the feedback-loop's correction magnitude at each iteration — this is what visually proves "two-way coupling" to judges rather than making them take your word for it.

---

## Phase 5 — Validation & docs

- Backtest against a known recent stubble-burning spike period if data is available (helps your demo narrative enormously).
- Rewrite README to honestly frame the approach: "hybrid meteorology-chemistry coupling emulator approximating PBL–aerosol feedback, built as a computationally tractable alternative to WRF-Chem for the hackathon timeframe."
- Prepare a short judge-facing explanation of the coupling methodology (this plan's Phase 1 section is your source material).

---

## Concrete file changes/additions (repo-relative paths)

```
fastapi_app/app/services/
    met_client.py               [NEW] Open-Meteo integration (PBL, wind, temp, humidity)
    inversion_calculator.py     [NEW] inversion strength index
    fire_plume_service.py       [NEW] FIRMS ingestion + advection plume estimate
    coupling_engine.py          [NEW] two-way feedback loop orchestrator
    aqi_calculator.py           [MODIFY] Delhi NCR CPCB breakpoints if different from MPCB
    ingestion.py                [MODIFY] swap MPCB → CPCB/OpenAQ Delhi NCR stations
    ml_pipeline.py              [MODIFY] expanded feature set, PM2.5/O3 split, 72h horizon
    prediction_service.py       [MODIFY] call coupling_engine instead of raw ml_pipeline

fastapi_app/app/models/
    met_reading.py               [NEW]
    fire_hotspot.py               [NEW]
    inversion_index.py            [NEW]
    prediction.py                 [MODIFY] extend for 72h + confidence + per-pollutant

fastapi_app/app/api/
    coupling.py                   [NEW] new endpoints (Phase 3)
    predictions.py                 [MODIFY] add /forecast72 route

fastapi_app/app/core/config.py    [MODIFY] Delhi NCR bounding box, new API keys/URLs

frontend/src/components/
    InversionGauge.jsx            [NEW]
    PlumeDispersionMap.jsx        [NEW]
    Forecast72Chart.jsx           [NEW]
    CouplingExplainabilityPanel.jsx [NEW]

frontend/src/pages/Dashboard.jsx  [MODIFY] wire in new components

README.md                          [MODIFY] reframe methodology, Delhi NCR scope
```

---

## Task checklist with rough time budget (48h window example)

| # | Task | Phase | Est. hrs |
|---|------|-------|----------|
| 1 | Delhi NCR station list + OpenAQ/CPCB ingestion swap | 0 | 2 |
| 2 | Open-Meteo met_client.py (PBL, wind, temp) | 1 | 3 |
| 3 | inversion_calculator.py | 1 | 2 |
| 4 | FIRMS fire ingestion + fire_plume_service.py advection | 1 | 4 |
| 5 | coupling_engine.py feedback loop | 1 | 5 |
| 6 | Expanded feature set + PM2.5/O3 split models | 2 | 5 |
| 7 | Extend horizon to 72h (recursive forecasting) | 2 | 3 |
| 8 | New DB tables + migrations | 3 | 2 |
| 9 | New API endpoints | 3 | 3 |
| 10 | InversionGauge + PlumeDispersionMap components | 4 | 4 |
| 11 | Forecast72Chart + CouplingExplainabilityPanel | 4 | 3 |
| 12 | Dashboard wiring | 4 | 2 |
| 13 | Backtest + README rewrite + demo prep | 5 | 3 |

Total: ~41 hrs — front-load Phase 1 (tasks 2–5), since that's the differentiator judges will scrutinize hardest.

---

## Key API references

- Open-Meteo Forecast API (PBL height, wind, temp, free, no key): https://open-meteo.com/en/docs
- NASA FIRMS active fire API: https://firms.modis.gsfc.nasa.gov/api/
- OpenAQ API v3: https://docs.openaq.org/
- CPCB CAAQMS (Delhi NCR real-time stations): https://airquality.cpcb.gov.in/
