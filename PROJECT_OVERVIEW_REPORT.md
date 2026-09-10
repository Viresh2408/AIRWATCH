# AirWatch Pro: Industrial Air Pollution–Weather Coupled Forecasting Platform
## Complete Project Overview & Technical Architecture Report

> **Prepared for**: AI Assistant / Technical Reviewer / Evaluation Committee  
> **Challenge Domain**: Smart India Hackathon (SIH PS 26082) · Delhi NCR Airshed  
> **Repository**: `AIRWATCH`

---

## 1. Executive Summary

**AirWatch Pro** is an industrial-grade, full-stack air quality intelligence and forecasting platform engineered specifically for the **Delhi National Capital Region (NCR)** and the **Indo-Gangetic Plain (IGP)**.

Unlike conventional air quality monitors and simple machine learning models that treat weather as passive background conditions, AirWatch Pro implements a **dynamic, two-way coupled meteorology–chemistry feedback emulator**. It models the real-world physical mechanisms that cause catastrophic winter smog episodes in Northern India:
- **Aerosol radiative forcing**: High surface concentrations of particulate matter (PM2.5 / PM10) scatter solar radiation.
- **Surface cooling & boundary layer collapse**: Reduced solar heating creates sharp nocturnal and early morning thermal inversion layers, compressing the Planetary Boundary Layer (PBL) down to <200 m (compared to >1,500 m in summer).
- **Aerosol trapping feedback**: The collapsed boundary layer restricts atmospheric ventilation volume, trapping pollutants close to the ground in a positive feedback loop.
- **Transboundary stubble-burning plume advection**: Near-real-time satellite fire hotspots (NASA FIRMS VIIRS/MODIS) over Punjab and Haryana are advected into Delhi via boundary-layer wind vectors.
- **Photochemical ozone synthesis**: Precursor nitrogen oxides ($NO_x$) and volatile compounds drive daytime ozone ($O_3$) production under effective UV radiation.

AirWatch Pro couples these physical equations with **XGBoost machine learning sub-models** to deliver high-resolution **72-hour hourly forecasts** with 90% empirical confidence intervals, real-time CPCB-compliant AQI calculations, satellite plume tracking, and an interactive LLM-powered environmental health advisory.

---

## 2. Real-World Problem & Scientific Motivation

### The Indo-Gangetic Plain Winter Pollution Crisis
During October through January, Delhi NCR experiences hazardous Air Quality Index (AQI > 400, "Severe+") conditions. This crisis is caused by a confluence of three distinct forces:
1. **Local Urban Emissions**: Vehicular traffic, construction dust, and industrial emissions.
2. **Regional Agricultural Stubble Burning**: Massive biomass burning in Punjab, Haryana, and Western UP carried southeastward by prevailing northwesterly winds.
3. **Meteorological Trapping (The Trap Effect)**: As winter sets in, calm surface winds and cold nighttime ground temperatures generate strong temperature inversions. Particulate matter acts as a radiation shield, cooling the ground even further. This shrinks the atmospheric mixing depth (Planetary Boundary Layer height), so identical emission rates lead to 3x–5x higher ground concentrations.

### Why Standard ML Models Fail
Standard ML predictors take meteorological data (temperature, wind speed, humidity) as static inputs to predict PM2.5. They do not feed the predicted PM2.5 back into the atmospheric physics. Consequently, they **systematically underpredict extreme pollution spikes** during severe inversion and stubble burning events.

Numerical chemical transport models like **WRF-Chem** can model these feedbacks, but require supercomputing clusters running 6 to 12 hours per forecast run. **AirWatch Pro solves this by deploying a numerical two-way coupling emulator that converges in $\le 3$ iterations in under 5 seconds**, making real-time, interactive forecasting possible on commodity hardware.

---

## 3. High-Level System Architecture

The platform follows a modern, decoupled client-server architecture:

```
+---------------------------------------------------------------------------------------+
|                                    DATA INGESTION                                     |
|                                                                                       |
|  +------------------------------+             +------------------------------------+  |
|  | Open-Meteo Air Quality & Met |             |      NASA FIRMS Satellite API      |  |
|  | (Hourly real-time PM2.5/PM10/|             | (Near-Real-Time VIIRS/MODIS active |  |
|  | NO2/SO2/CO/O3 + Temp/RH/PBL) |             |  fire hotspots over Punjab/Haryana)|  |
|  +--------------+---------------+             +-----------------+------------------+  |
+-----------------|-----------------------------------------------|---------------------+
                  |                                               |
                  v                                               v
+---------------------------------------------------------------------------------------+
|                               FASTAPI BACKEND & ORCHESTRATION                         |
|                                                                                       |
|  +---------------------------------------------------------------------------------+  |
|  | APScheduler Background Engine                                                   |  |
|  | - Every 15 min: Ingest live telemetry & trigger coupled forecast                |  |
|  | - Every 1 hour: Refresh 72-hour coupled forecast matrix                         |  |
|  | - Every 24 hours (2 AM IST): Retrain XGBoost on updated feature store           |  |
|  +---------------------------------------------------------------------------------+  |
|                                                                                       |
|  +---------------------------+  +--------------------------------------------------+  |
|  | Inversion Index Engine    |  | Two-Way Coupling Engine                          |  |
|  | - Nocturnal cooling calc  |  | - Step 1: Baseline ML forecast                  |  |
|  | - PBL compression score   |  | - Step 2: Aerosol radiative forcing on PBL & Temp|  |
|  | - Multi-tier risk rating  |  | - Step 3: Gaussian plume stubble advection       |  |
|  +---------------------------+  | - Step 4: Iterative convergence loop (<= 3 iter) |  |
|                                 | - Step 5: Photochemical O3 sub-model             |  |
|                                 +--------------------------------------------------+  |
|                                                                                       |
|  +---------------------------+  +--------------------------------------------------+  |
|  | CPCB AQI Engine           |  | Groq LLM Advisory Assistant                      |  |
|  | - 6-pollutant sub-indices |  | - Telemetry-grounded health advice               |  |
|  | - Standard breakpoint map |  | - Sensitive groups alerts & risk mitigations     |  |
|  +---------------------------+  +--------------------------------------------------+  |
+------------------------------------------|--------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                               DATABASE STORAGE (PostgreSQL / SQLite)                  |
|  - stations        : 7 Delhi NCR core CAAQMS stations + coordinates                   |
|  - readings        : Idempotent time-series sensor measurements (past 72h + history)  |
|  - predictions     : 72-hour coupled forecast steps with CI & coupling diagnostics    |
|  - met_readings    : Surface meteorology & boundary layer height                      |
|  - fire_hotspots   : NASA FIRMS fire coordinates, FRP, confidence                     |
|  - inversion_index : Inversion severity scores, PBL height, diurnal metrics           |
|  - users           : JWT auth, hashed passwords, roles (Govt, Industry, Citizen)      |
+------------------------------------------|--------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                             REACT + VITE TAILWIND FRONTEND                            |
|                                                                                       |
|  +---------------------------------------------------------------------------------+  |
|  | Real-Time Dashboard (http://localhost:4028/dashboard)                           |  |
|  | - Delhi NCR Station Cards (Anand Vihar, ITO, Punjabi Bagh, RK Puram, Dwarka,    |  |
|  |   Noida, Gurugram) with live CPCB color-coded badges & sub-index breakdowns      |  |
|  | - 72-Hour Coupled Forecast Visualizer with 90% confidence bands & pollutant mix |  |
|  | - Dynamic Inversion Strength Gauge with timeline slider                          |  |
|  | - NASA FIRMS Stubble-Burning Plume Dispersion Map                               |  |
|  | - Two-Way Coupling Explainability Panel with numerical iteration traces        |  |
|  | - Floating AI Environmental Health Advisory Assistant                           |  |
|  +---------------------------------------------------------------------------------+  |
|  | Historical Analytics (Trends, Heatmaps, Descriptive Statistics, Comparisons)    |  |
|  | Station Detail Pages (Deep-dive parameter graphs, forecast curves)              |  |
|  | Role-Based Auth & Registration (Government Official, Industry Manager, Citizen)|  |
+---------------------------------------------------------------------------------------+
```

---

## 4. Detailed Component Implementation

### 4.1. Live Delhi NCR Telemetry Ingestion (`live_delhi_fetcher.py`)
- **Coverage**: 7 primary CPCB/DPCC continuous ambient air quality stations:
  1. Anand Vihar, East Delhi (Lat: 28.6469, Lon: 77.3164) — Highest PM2.5 receptor
  2. ITO, Central Delhi (Lat: 28.6310, Lon: 77.2433) — Heavy urban traffic
  3. Punjabi Bagh, West Delhi (Lat: 28.6683, Lon: 77.1333) — Residential inversion
  4. RK Puram, South Delhi (Lat: 28.5644, Lon: 77.1895) — DPCC reference station
  5. Dwarka Sector 8, South-West Delhi (Lat: 28.5822, Lon: 77.0330) — Haryana entry corridor
  6. Noida Sector 62, NCR (Lat: 28.6270, Lon: 77.3640) — Eastern transboundary corridor
  7. Gurugram Sector 51, NCR (Lat: 28.4595, Lon: 77.0266) — Southwestern upwind fetch
- **Data Source**: Open-Meteo Air Quality & Weather API (hourly observations and reanalysis).
- **Parameters**: $PM_{2.5}$, $PM_{10}$, $NO_2$, $SO_2$, $CO$, $O_3$, 2m Temperature, Relative Humidity.
- **Idempotent Upserting**: Implemented dialect-native `ON CONFLICT (station_id, datetime, parameter) DO UPDATE SET value = EXCLUDED.value` to ensure incoming real-time telemetry updates current records without wiping historical trends.
- **Self-Healing Freshness**: If any API caller requests `/api/v1/aqi/realtime/` and the database contains telemetry older than 60 minutes, the backend automatically triggers an on-demand live pull (with a 3-minute debounce guard).

### 4.2. Two-Way Atmospheric-Chemical Coupling Engine (`coupling_engine.py`)
At each timestep $t$ in the 72-hour forecast horizon:
1. **PBL Suppression**:
   $$\text{PBL}_{\text{corr}} = \max\left(\text{PBL}_{\text{raw}} \cdot \left[1 - \alpha \cdot \frac{\text{PM}_{2.5}}{\text{PM}_{2.5,\text{ref}}}\right],\, \text{PBL}_{\text{floor}}\right)$$
   Where $\alpha = 0.18$ (calibrated against Indo-Gangetic Plain aerosol studies), $\text{PM}_{2.5,\text{ref}} = 500\,\mu\text{g/m}^3$, $\text{PBL}_{\text{floor}} = 80\,\text{m}$.
2. **Direct Radiative Surface Cooling**:
   $$T_{\text{corr}} = T_{\text{raw}} - \beta \cdot \frac{\text{PM}_{2.5}}{100}$$
   Where $\beta = 0.25^\circ\text{C}$ per $100\,\mu\text{g/m}^3$ PM2.5.
3. **Numerical Convergence Loop**:
   The engine re-evaluates PM2.5 with corrected boundary-layer ventilation depth until $|\text{PM}_{2.5}^{(k)} - \text{PM}_{2.5}^{(k-1)}| < 2.0\,\mu\text{g/m}^3$ or iterations reach $k = 3$.
4. **Photochemical Ozone Sub-Model**:
   Calculates daytime $O_3$ synthesis based on attenuated UV radiation, temperature, and precursor $NO_x$ lag.

### 4.3. NASA FIRMS Fire Plume Dispersion Model (`fire_plume_service.py`)
- **Data Source**: NASA FIRMS Active Fire API (VIIRS S-NPP / NOAA-20 and MODIS).
- **Bounding Box**: Punjab, Haryana, and Western Uttar Pradesh agricultural fire corridor ($29.5^\circ\text{N} - 32.5^\circ\text{N}$, $73.5^\circ\text{E} - 78.5^\circ\text{E}$).
- **Mechanism**: Gaussian plume advection model driven by the 80m Above Ground Level (AGL) boundary layer wind speed and direction vector:
  $$\Delta \text{PM}_{2.5}(x, y) = \frac{Q}{2\pi u \sigma_y \sigma_z} \exp\left(-\frac{y^2}{2\sigma_y^2}\right)$$
  Computes fire plume transit time and surface contribution (in $\mu\text{g/m}^3$) for each Delhi NCR station.

### 4.4. Atmospheric Inversion Index Calculator (`inversion_calculator.py`)
Quantifies the strength of surface-based temperature inversions on a continuous scale $[0.0, 1.0]$:
- Combines normalized boundary layer compression $\frac{500 - \text{PBL}}{300}$, diurnal nocturnal bonus, and rate of change of PBL ($\frac{d\text{PBL}}{dt}$).
- Categorizes risk into 5 clear tiers:
  - **None** ($0.0 - 0.25$): Well-mixed atmosphere, minimal trapping.
  - **Weak** ($0.25 - 0.50$): Standard diurnal boundary layer reduction.
  - **Moderate** ($0.50 - 0.75$): Visible haze formation, reduced dispersion.
  - **Strong** ($0.75 - 0.90$): High pollutant buildup, nocturnal inversion.
  - **Severe** ($0.90 - 1.00$): Extreme trapping, emergency advisory level.

### 4.5. Indian CPCB AQI Calculation Engine (`aqi_calculator.py`)
- Compliant with **Central Pollution Control Board (CPCB)** guidelines.
- Converts gas concentrations from volumetric ($ppb$) to mass concentration ($\mu\text{g/m}^3$) using molecular weights and ambient temperatures.
- Calculates sub-indices for all 6 criteria pollutants across official Indian breakpoints (Good: 0-50, Satisfactory: 51-100, Moderate: 101-200, Poor: 201-300, Very Poor: 301-400, Severe: 401-500).
- Overall AQI is defined as $\max(\text{SubIndex}_i)$ with the driving dominant pollutant explicitly identified.

### 4.6. Groq LLM Environmental Advisory (`groq_ai_service.py`)
- Interfaces with Groq's high-speed Llama-3 inference API.
- Injects live telemetry from all Delhi NCR stations (AQI, PM2.5, dominant pollutants, inversion risk) into the system prompt to generate grounded health recommendations.
- Provides interactive chat for citizens, researchers, and government officials regarding precautions, mask requirements, outdoor exercise advisories, and GRAP (Graded Response Action Plan) alerts.

### 4.7. Frontend React Dashboard & Visualizations
Built with **React 18, Vite, and TailwindCSS**:
- **Monitoring Station Cards**: Color-coded CPCB status, live AQI, pollutant breakdown, last updated time.
- **72-Hour Coupled Forecast Visualizer**: Interactive Recharts graph plotting predicted AQI, PM2.5, PM10, O3, with 90% confidence bands and inversion scores.
- **Atmospheric Inversion Gauge**: Circular SVG gauge and timeline slider showing nocturnal trapping severity.
- **NASA FIRMS Plume Dispersion Map**: Interactive visualization of active fire sources in Punjab/Haryana and estimated plume advection vectors into Delhi.
- **Coupling Explainability Panel**: Step-by-step trace showing numerical convergence from iteration 1 to 3 with physical explanations.
- **Historical Analytics**:
  - *Trend Analysis Chart*: Multi-pollutant time-series with area/line modes.
  - *Spatial Heatmap*: Hour-of-day vs. station pollution heatmaps.
  - *Statistical Summary*: Mean, median, standard deviation, percentile bounds (P25, P75), and CPCB compliance rate.
  - *Comparative Analysis*: Cross-station AQI and radar pollutant profile comparisons.
- **Role-Based Registration & Auth**: Specialized user roles for *Government Official*, *Industrial Manager*, *Environmental Professional*, and *Citizen*, with primary monitoring location selection centered on Delhi NCR.

---

## 5. API Endpoint Catalog

All API routes are prefixed with `/api/v1`:

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/stations/` | `GET` | List all monitoring stations and geocoordinates |
| `/stations/{id}` | `GET` | Retrieve metadata for a single station |
| `/aqi/realtime/` | `GET` | Live AQI, pollutant values, and CPCB category (with auto-freshness trigger) |
| `/aqi/history/{id}` | `GET` | Historical hourly aggregated AQI for a station (`hours=24, 168, 720`) |
| `/aqi/forecast72/{id}` | `GET` | 72-hour coupled forecast with per-pollutant breakdown, CI, & diagnostics |
| `/predictions/{id}` | `GET` | 48-hour standard prediction curve for backward compatibility |
| `/coupling/inversion/{id}` | `GET` | 72-hour inversion severity timeline, PBL heights, and risk categories |
| `/coupling/plume-forecast` | `GET` | Active fire hotspot coordinates, plume PM2.5 contributions, and arrival times |
| `/coupling/feedback-trace/{id}` | `GET` | Numerical iteration-by-iteration coupling convergence trace |
| `/ai/advisory` | `GET` | Real-time grounded health advisory generated by Groq LLM |
| `/ai/chat` | `POST` | Interactive conversational endpoint for air quality inquiries |
| `/auth/register` | `POST` | User registration with hashed credentials and role specification |
| `/auth/login` | `POST` | User login returning a JWT Bearer access token |
| `/auth/me` | `GET` | Profile of currently authenticated user |
| `/scheduler/status` | `GET` | Status of APScheduler background jobs |
| `/scheduler/run/ingestion` | `POST` | Manually trigger live telemetry ingestion |
| `/scheduler/run/predictions` | `POST` | Manually trigger 72h prediction regeneration |

---

## 6. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | FastAPI (Python 3.12) | High-performance asynchronous REST API |
| **Data Engine & ORM** | SQLAlchemy, PostgreSQL (Supabase) / SQLite | Relational storage with unique constraints & upserts |
| **Task Scheduling** | APScheduler | Daemon background thread scheduling (15m, 1h, 24h) |
| **Machine Learning** | XGBoost, scikit-learn, pandas, numpy | Gradient boosted regression sub-models & feature store |
| **Atmospheric Physics** | Custom Coupling Emulator, NumPy | Two-way aerosol-PBL feedback & Gaussian plume model |
| **External APIs** | Open-Meteo, NASA FIRMS, Groq Cloud | Meteorological/AQ observations, satellite fires, LLM |
| **Frontend Framework** | React 18, Vite | Component-driven, fast HMR client application |
| **Styling & Icons** | TailwindCSS, Lucide Icons | Responsive modern industrial dark/light aesthetics |
| **Data Visualization** | Recharts, SVG Canvas | Time-series graphs, gauges, confidence interval bands |
| **Testing** | Pytest, pytest-asyncio | Unit, integration, security, and API test suites |

---

## 7. How to Run the Project

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Valid `.env` configuration (configured with database URL, JWT secret, and optional Groq/FIRMS keys)

### Step 1: Start the FastAPI Backend
```bash
cd AirWatch/fastapi_app
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
- **Backend API**: `http://localhost:8000/`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- On startup, the backend will automatically:
  1. Verify the database tables.
  2. Ensure the 7 Delhi NCR stations exist.
  3. Kick off live telemetry ingestion in a background thread.
  4. Start the APScheduler for 15-minute recurring updates.

### Step 2: Start the React Frontend
```bash
cd AirWatch/frontend
npm run dev
```
- **Dashboard URL**: `http://localhost:4028/dashboard`
- **Register / Login**: `http://localhost:4028/register` and `http://localhost:4028/login`

### Step 3: Run the Test Suite
```bash
cd AirWatch
pytest tests/ -v
```
Runs all 96+ tests covering:
- CPCB AQI Calculator & Breakpoints (`test_aqi_calculator.py`)
- API Endpoints (`test_api.py`)
- Coupling Models & Physics Endpoints (`test_coupling_api.py`)
- Security & Input Validation (`test_security.py`)
- NASA FIRMS Plume Advection (`test_fire_plume_service.py`)
- Inversion Index Calculations (`test_inversion_calculator.py`)

---

## 8. Summary for ChatGPT / AI Reviewers

When analyzing or extending this codebase, keep the following core design principles in mind:
1. **Focus Area**: The project is centered on **Delhi NCR** (SIH PS 26082). Stations and locations should always refer to Delhi NCR CPCB/DPCC monitoring stations (`Anand Vihar`, `ITO`, `Punjabi Bagh`, `RK Puram`, `Dwarka Sector 8`, `Noida Sector 62`, `Gurugram Sector 51`).
2. **Coupled Physics**: Any modification to AQI forecasting should maintain the feedback loop between PM2.5 concentrations, Planetary Boundary Layer height, and surface temperature.
3. **Real-Time Data Flow**: Real-time telemetry is pulled from Open-Meteo and stored with idempotent SQL upserts. Stale data triggers self-healing auto-ingestion.
4. **CPCB Standards**: AQI indices follow official Indian Central Pollution Control Board breakpoints and 6-pollutant maximum-sub-index methodology.
