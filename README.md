# AirWatch Pro: Coupled Meteorology-Chemistry AQI Prediction System

[![Smart India Hackathon 2024](https://img.shields.io/badge/SIH%202024-PS%2026082-blueviolet?style=for-the-badge)](https://www.sih.gov.in/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%200.104-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB?style=for-the-badge&logo=react)](https://reactjs.org/)
[![XGBoost](https://img.shields.io/badge/ML-Coupled%20XGBoost-FF6600?style=for-the-badge&logo=xgboost)](https://xgboost.readthedocs.io/)
[![Tests](https://img.shields.io/badge/Tests-96%20Passing-success?style=for-the-badge&logo=pytest)](https://docs.pytest.org/)

An industrial-grade, real-time air quality forecasting and explainability platform specifically engineered for the **Delhi NCR Indo-Gangetic Plain (IGP)** airshed. AirWatch Pro implements a **two-way meteorology-chemistry feedback emulator** coupling boundary-layer dynamics, NASA FIRMS active fire plumes, and photochemical ozone synthesis.

---

## 1. Problem Statement & Scientific Motivation

### The Indo-Gangetic Plain Reality
Standard machine learning AQI predictors treat meteorology (temperature, wind, boundary layer height) as static, exogenous inputs. In reality, during the post-monsoon and winter seasons in Delhi NCR:

1. **Aerosol-PBL Feedback Loop**: Massive particulate loading from regional stubble-burning and urban emissions attenuates incoming shortwave solar radiation.
2. **Surface Cooling & Boundary Layer Collapse**: The ground cools, creating a thermal inversion where the daytime Planetary Boundary Layer (PBL) fails to lift, collapsing below 200 m AGL overnight (versus >1,500 m in summer).
3. **Severe Trapping**: The compressed boundary layer restricts the ventilation volume, further concentrating pollutants near the surface and amplifying the crisis.

Conventional uncoupled ML models severely underpredict pollution spikes because they fail to account for this positive feedback. **AirWatch Pro bridges this gap by iteratively coupling meteorological forcing with chemical concentrations.**

---

## 2. Core Architecture & Coupling Engine

Rather than deploying computationally prohibitive numerical chemical transport models (e.g., WRF-Chem, requiring 6–12 hours of multi-node HPC per forecast cycle), AirWatch Pro uses an **iterative two-way coupling emulator** that converges in $\le 3$ iterations per forecast hour:

```mermaid
flowchart TD
    subgraph Forcing ["Step 1: Meteorological & Fire Forcing"]
        OM[Open-Meteo 72h Forecast] -->|Raw PBL, Temp, Wind, UV| CE
        FIRMS[NASA FIRMS Active Fires] -->|FRP & Hotspots| PLUME[Gaussian Plume Transport]
        PLUME -->|Plume PM2.5 Contrib| CE[Coupling Engine Loop]
    end

    subgraph FeedbackLoop ["Iterative Coupling Loop (1-3 Iterations)"]
        CE -->|Met + Plume + Lags| PM_MODEL[XGBoost PM2.5/PM10 Sub-Model]
        PM_MODEL -->|PM2.5 Estimate| AEROSOL_FEEDBACK[Aerosol-PBL Feedback Step]
        AEROSOL_FEEDBACK -->|Correct PBL: -18%| INV[Inversion Index Calc]
        AEROSOL_FEEDBACK -->|Correct Temp: -0.25°C/100ug| CE
        AEROSOL_FEEDBACK -->|Delta PM2.5 < 2.0 ug/m3?| CONV{Converged?}
        CONV -- No --> CE
        CONV -- Yes --> O3_MODEL[XGBoost O3 Photochemistry Model]
    end

    subgraph Outputs ["Step 3: Downstream Deliverables"]
        O3_MODEL --> FORECAST72[72h Forecast API & DB]
        AEROSOL_FEEDBACK --> TRACE[Feedback Trace Explainability API]
        INV --> GAUGE[Inversion Strength Timeline]
    end
```

### Numerical Coupling Equations

For each forecast timestep $(t)$:

1. **Planetary Boundary Layer (PBL) Suppression**:
   $$\text{PBL}_{\text{corr}} = \max\left(\text{PBL}_{\text{raw}} \cdot \left[1 - \alpha \cdot \frac{\text{PM}_{2.5}}{\text{PM}_{2.5,\text{ref}}}\right],\, \text{PBL}_{\text{floor}}\right)$$
   Where $\alpha = 0.18$, $\text{PM}_{2.5,\text{ref}} = 500\ \mu\text{g/m}^3$, $\text{PBL}_{\text{floor}} = 50\ \text{m}$.

2. **Surface Radiative Cooling**:
   $$T_{\text{corr}} = T_{\text{raw}} - \beta \cdot \frac{\text{PM}_{2.5}}{100}$$
   Where $\beta = 0.25^\circ\text{C}$ per $100\ \mu\text{g/m}^3$.

3. **Photochemical UV Optical Attenuation (Ozone Sub-Model)**:
   $$\text{UV}_{\text{eff}} = \text{UV}_{\text{raw}} \cdot \left[1 - \gamma \cdot \frac{\text{PM}_{2.5}}{\text{PM}_{2.5,\text{ref}}}\right]$$
   Where $\gamma = 0.30$. High particulate optical depth attenuates actinic solar flux, curbing daytime secondary ozone synthesis.

4. **Atmospheric Inversion Severity Score**:
   $$\text{Score} = \text{clamp}\left(\left[1 - \frac{\text{PBL}}{500}\right] + \text{Bonus}_{\text{trend}} + \text{Bonus}_{\text{pre-dawn}},\, 0.0,\, 1.0\right)$$
   Categorized into `None` ($<0.25$), `Weak` ($0.25–0.50$), `Moderate` ($0.50–0.75$), `Strong` ($0.75–0.90$), and `Severe` ($\ge 0.90$).

---

## 3. Grounding & Literature Citations

All empirical coefficients used in the feedback loop are directly grounded in peer-reviewed atmospheric studies of the Indo-Gangetic Plain:

| Parameter | Value | Phenomenon | Scientific Citation |
|---|---|---|---|
| **$\alpha$** | `0.18` | Fractional PBL suppression during extreme haze | **Kumar et al. (2020), ACP**; **Srivastava et al. (2021)**: Document ~15–20% boundary layer height reduction in Delhi winter haze ($PM_{2.5} > 300\ \mu\text{g/m}^3$). |
| **$\beta$** | `0.25°C` | Direct aerosol radiative cooling per $100\ \mu\text{g/m}^3$ | **Ramachandran & Kedia (2010), ACP**: Observed $-80\ \text{W/m}^2$ surface radiative forcing in Delhi during severe post-monsoon haze. |
| **$\gamma$** | `0.30` | Actinic solar UV flux attenuation | **IAS Indo-Gangetic Atmospheric Studies**: 30–50% decrease in ground UV-A/UV-B during winter high-AOD episodes. |
| **$\sigma_\theta$** | `15.0°` | Plume dispersion half-angle spread | Standard industrial Gaussian plume cone formulation for regional transport. |

---

## 4. Transparent Methodology & Known Limitations

To maintain scientific integrity for judges and researchers, AirWatch Pro explicitly states the following operational trade-offs:

1. **80m AGL Wind Transport Field**:
   Open-Meteo's free-tier operational API provides wind speed and direction at 10m and 80m AGL, but not 850 hPa pressure levels (which requires ECMWF ERA5 reanalysis with multi-hour retrieval delays). 80m AGL sits above the surface drag sublayer (~10m) and serves as an effective operational proxy for regional transport across Haryana/Punjab into Delhi NCR.
2. **Straight-Line Gaussian Cone Dispersion**:
   Fire smoke transport is modeled using straight-line advection with Gaussian angular spreading ($\sigma = 15^\circ$) and distance attenuation ($r^{-1.5}$), rather than full Lagrangian particle dispersion (e.g. NOAA HYSPLIT). This ensures sub-second API responses suitable for real-time edge deployment.
3. **NOx Precursor Diurnal Evolution**:
   Ozone formation uses an empirical diurnal decay model anchored on observed CPCB NO2 concentrations to capture Delhi's dual rush-hour NOx emission peaks (08:30 and 19:30 IST).

---

## 5. System Features & Visualizations

- **72-Hour Multi-Pollutant Forecast**: Dedicated XGBoost sub-models forecasting $PM_{2.5}$, $PM_{10}$, and $O_3$ with 90% confidence bands that dynamically widen during strong inversion conditions.
- **Atmospheric Inversion Gauge**: Radial SVG visualization tracking real-time inversion score, boundary layer height (m AGL), collapse rate ($dpbl/dt$), and pre-dawn risk window bonuses.
- **Stubble-Burning Plume Map**: Interactive regional map rendering NASA FIRMS VIIRS active fire hotspots, 80m AGL wind vectors, downwind Gaussian dispersion cones, and station arrival rankings.
- **Judge-Facing Explainability Panel**: Step-by-step iteration convergence breakdown proving numerical convergence ($\Delta PM_{2.5} < 2.0\ \mu\text{g/m}^3$) and PBL compression metrics.
- **AI Environmental Health Advisory**: Real-time LLM health precautions and citizen advisory grounded in live station sensor telemetry.

---

## 6. API Reference

All endpoints are hosted under `/api/v1` and fully documented via interactive Swagger UI at `http://localhost:8000/docs`:

### Coupling & Meteorology
- `GET /api/v1/coupling/inversion/{station_id}?hours=72`: Hourly inversion index $[0.0, 1.0]$, category, PBL height, and collapse rate.
- `GET /api/v1/coupling/plume-forecast`: NASA FIRMS active fires, Gaussian plume PM2.5 transport contributions, and arrival times.
- `GET /api/v1/coupling/feedback-trace/{station_id}?hour_offset=1`: Explainability iteration trace, PBL suppression percentage, and thermodynamic adjustments.

### Monitoring & Predictions
- `GET /api/v1/aqi/realtime/`: Real-time CPCB sub-index computations across all monitoring stations.
- `GET /api/v1/aqi/history/{station_id}?hours=24`: Hourly-aggregated historical air quality readings.
- `GET /api/v1/aqi/forecast72/{station_id}`: 72-hour coupled forecast with per-pollutant trajectories and confidence intervals.
- `GET /api/v1/stations/`: Monitoring station directory and coordinates.

### AI & Operations
- `GET /api/v1/ai/advisory`: Telemetry-grounded citizen and industrial health advisory.
- `POST /api/v1/ai/chat`: Interactive conversational air quality assistant.
- `GET /api/v1/scheduler/status`: APScheduler background job statuses (predictions, ingestion, retraining).

---

## 7. Installation & Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- PostgreSQL (or local SQLite)

### 1. Backend Setup
```powershell
# Clone repository
git clone https://github.com/your-org/AirWatch.git
cd AirWatch

# Install Python dependencies
pip install -r fastapi_app/requirements.txt

# Configure environment
cp fastapi_app/.env.example fastapi_app/.env

# Run database migration for coupling columns and tables
python fastapi_app/migrate_phase2.py

# Launch FastAPI backend
uvicorn fastapi_app.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```powershell
cd frontend

# Install Node dependencies
npm install

# Start Vite dev server
npm run dev
```
Open `http://localhost:5173` to explore the dashboard.

---

## 8. Automated Testing & Verification

The codebase includes an automated test suite with **96 tests passing (0 failures, 0 errors)**:

```powershell
# Run entire test suite
python -m pytest tests/ -v --tb=short
```

### Test Coverage Breakdown
- `tests/test_coupling_api.py`: Inversion timeline, plume forecast, feedback trace explainability, and database models.
- `tests/test_fire_plume_service.py`: Haversine distance, azimuth geometry, FIRMS CSV parsing, and Gaussian cone dispersion.
- `tests/test_coupling_engine.py`: Numerical convergence loop, PBL feedback suppression, UV attenuation, and trend bonus.
- `tests/test_prediction_service.py`: 72h forecast persistence, context lag seeding, confidence intervals, and physical constraints ($PM_{10} \ge PM_{2.5}$).
- `tests/test_ml_pipeline.py`: PM & O3 XGBoost sub-models, diurnal fallbacks, and NOx assertions.
- `tests/test_met_client.py`: Open-Meteo forecast retrieval, caching, and wind vector decomposition.
- `tests/test_inversion_calculator.py`: Atmospheric inversion boundary conditions and collapse rates.
- `tests/test_aqi_calculator.py`: CPCB sub-index math, pollutant validation, and color palettes.
- `tests/test_security.py`: SQL injection, XSS sanitization, rate limiting, and token verification.

### Empirical Backtest
To execute the historical episode backtest comparing uncoupled baseline vs. coupled model:
```powershell
python fastapi_app/backtest_coupled_model.py
```
Evaluation metrics and structured results are output to `fastapi_app/backtest_results.json`.

---

## 9. License & Acknowledgments

- **License**: MIT License.
- **Data Providers**: Open-Meteo API (Meteorology & Boundary Layer Height), NASA FIRMS (VIIRS Active Fire Hotspots), Central Pollution Control Board (CPCB) / OpenAQ (Station Telemetry).
