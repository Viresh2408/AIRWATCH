from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
import time
import logging

logger = logging.getLogger(__name__)

from app.core.db import get_db
from app.core.scheduler import scheduler, job_generate_predictions, job_retrain_model, job_live_ingestion
from app.models.aqi import Station, Reading, Prediction
from app.models.user import User
from app.services.aqi_calculator import ppb_to_ugm3, calculate_sub_index, GAS_MW, get_aqi_category, AQI_BREAKPOINTS
from app.services.prediction_service import generate_and_save_predictions
from app.core.auth import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.schemas.auth import UserRegister, UserLogin, LoginResponse, UserResponse
from pydantic import BaseModel, Field

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------

class StationSchema(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    class Config:
        from_attributes = True


class PollutantData(BaseModel):
    parameter: str
    value: float
    unit: str
    ugm3_value: Optional[float] = None
    sub_index: Optional[int] = None


class RealTimeAQISchema(BaseModel):
    station_id: int
    station_name: str
    lat: float
    lon: float
    last_updated: str
    overall_aqi: int
    aqi_category: str
    aqi_color: str
    pollutants: Dict[str, PollutantData]


class PredictionSchema(BaseModel):
    station_id: int
    prediction_time: str
    predicted_aqi: int
    model_version: str
    class Config:
        from_attributes = True


class Forecast72StepSchema(BaseModel):
    """Single timestep in the 72-hour coupled forecast response."""
    hour_offset: int
    prediction_time: str
    predicted_aqi: int
    # Per-pollutant forecasts
    predicted_pm25: Optional[float] = None
    predicted_pm10: Optional[float] = None
    predicted_o3: Optional[float] = None
    # Confidence intervals (90% empirical)
    pm25_lower: Optional[float] = None
    pm25_upper: Optional[float] = None
    pm10_lower: Optional[float] = None
    pm10_upper: Optional[float] = None
    # Coupling diagnostics
    inversion_score: Optional[float] = None
    inversion_category: Optional[str] = None
    plume_pm25_contrib: Optional[float] = None
    pbl_height_corrected: Optional[float] = None
    iterations_run: Optional[int] = None
    converged: Optional[bool] = None
    model_version: Optional[str] = None


class Forecast72Schema(BaseModel):
    station_id: int
    station_name: str
    forecast_generated_at: str
    horizon_hours: int
    steps: List[Forecast72StepSchema]


class HistoryPointSchema(BaseModel):
    datetime: str
    overall_aqi: int
    aqi_category: str
    aqi_color: str
    pollutants: Dict[str, float]


class IngestionSummarySchema(BaseModel):
    total_inserted: int
    per_station: Dict[str, dict]


# ---------------------------------------------------------------------------
# PUBLIC — Stations
# ---------------------------------------------------------------------------

@router.get("/stations/", response_model=List[StationSchema], tags=["Stations"])
def list_stations(db: Session = Depends(get_db)):
    """All monitoring stations — public."""
    return db.query(Station).all()


@router.get("/stations/{station_id}", response_model=StationSchema, tags=["Stations"])
def get_station(station_id: int, db: Session = Depends(get_db)):
    """Single station metadata by ID — public."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station {station_id} not found")
    return station


_last_auto_ingest_time: float = 0.0

def _check_and_refresh_live_telemetry(db: Session) -> None:
    """
    Checks if telemetry is stale (>60m old or missing) and automatically
    fetches live real-time telemetry from Open-Meteo with a 3-minute debounce.
    """
    global _last_auto_ingest_time
    now = time.time()
    if now - _last_auto_ingest_time < 180:  # Debounce: max once per 3 minutes
        return

    from app.services.live_delhi_fetcher import DELHI_STATIONS, ingest_live_delhi_telemetry

    delhi_sids = tuple(s[0] for s in DELHI_STATIONS)
    max_dt = db.execute(
        text("SELECT MAX(datetime) FROM readings WHERE station_id IN :sids"),
        {"sids": delhi_sids}
    ).scalar()

    need_refresh = False
    if not max_dt:
        need_refresh = True
    else:
        if isinstance(max_dt, str):
            max_dt = datetime.fromisoformat(max_dt.replace("Z", "+00:00")[:19]).replace(tzinfo=timezone.utc)
        elif max_dt.tzinfo is None:
            max_dt = max_dt.replace(tzinfo=timezone.utc)

        age_seconds = (datetime.now(timezone.utc) - max_dt).total_seconds()
        if age_seconds > 3600:  # Telemetry older than 1 hour
            need_refresh = True

    if need_refresh:
        _last_auto_ingest_time = now
        try:
            logger.info("[AUTO-INGEST] Telemetry is older than 60m or missing — pulling live Open-Meteo data...")
            ingest_live_delhi_telemetry(db)
        except Exception as e:
            logger.error(f"[AUTO-INGEST] Failed to auto-refresh live telemetry: {e}")

@router.get("/aqi/realtime/", response_model=List[RealTimeAQISchema], tags=["AQI Data"])
def get_realtime_aqi(db: Session = Depends(get_db)):
    """
    Latest AQI for every station. Computes sub-indices and overall AQI
    from the most recent readings in the DB.
    Guarantees real-time freshness by auto-refreshing telemetry if older than 60 minutes.
    """
    _check_and_refresh_live_telemetry(db)

    stations = db.query(Station).all()
    if not stations:
        return []

    results = []
    for station in stations:
        latest_readings = (
            db.query(Reading)
            .filter(Reading.station_id == station.id)
            .order_by(Reading.datetime.desc())
            .limit(100)
            .all()
        )

        if not latest_readings:
            results.append(RealTimeAQISchema(
                station_id=station.id, station_name=station.name,
                lat=station.lat, lon=station.lon,
                last_updated=datetime.utcnow().isoformat(),
                overall_aqi=0, aqi_category="No Data", aqi_color="#cccccc",
                pollutants={},
            ))
            continue

        # Latest reading per parameter
        readings_by_param: dict = {}
        latest_time = None
        for r in latest_readings:
            p = r.parameter.lower()
            if p not in readings_by_param:
                readings_by_param[p] = r
            if latest_time is None or r.datetime > latest_time:
                latest_time = r.datetime

        temp_c = readings_by_param.get("temperature")
        temp_c = temp_c.value if temp_c else 25.0

        sub_indices: dict = {}
        processed: dict = {}

        for param, reading in readings_by_param.items():
            try:
                ugm3 = reading.value
                if reading.unit and reading.unit.lower() == "ppb" and param in GAS_MW:
                    ugm3 = ppb_to_ugm3(reading.value, GAS_MW[param], temp_c)

                sub_idx = None
                if param in AQI_BREAKPOINTS and ugm3 is not None:
                    sub_idx = calculate_sub_index(ugm3, param)
                    if sub_idx and sub_idx > 0:
                        sub_indices[param] = sub_idx

                processed[param] = PollutantData(
                    parameter=param,
                    value=round(reading.value, 2),
                    unit=reading.unit or "µg/m³",
                    ugm3_value=round(ugm3, 2) if ugm3 else None,
                    sub_index=sub_idx,
                )
            except Exception:
                continue

        overall_aqi = max(sub_indices.values()) if sub_indices else 0
        aqi_status = get_aqi_category(overall_aqi)

        results.append(RealTimeAQISchema(
            station_id=station.id, station_name=station.name,
            lat=station.lat, lon=station.lon,
            last_updated=latest_time.isoformat() if latest_time else datetime.utcnow().isoformat(),
            overall_aqi=overall_aqi,
            aqi_category=aqi_status["category"],
            aqi_color=aqi_status["color"],
            pollutants=processed,
        ))

    return results


# ---------------------------------------------------------------------------
# PUBLIC — Historical AQI  (NEW)
# ---------------------------------------------------------------------------

@router.get("/aqi/history/{station_id}", response_model=List[HistoryPointSchema], tags=["AQI Data"])
def get_aqi_history(
    station_id: int,
    hours: int = Query(default=24, ge=1, le=8760, description="Hours of history to return (max 8760 = 1 year)"),
    window: str = Query(default=None, description="Shortcut: 24h, 3d, 7d, 30d (overrides hours)"),
    db: Session = Depends(get_db),
):
    """
    Returns hourly-aggregated AQI history for a station.
    Aggregates raw 15-min readings into hourly means, then computes AQI per hour.
    Default: last 24 hours. Max: 1 year (8760 h).
    Reference is the latest data timestamp in DB so old data still resolves correctly.
    """
    if window:
        window_map = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}
        hours = window_map.get(window.lower(), hours)
    latest_ts = db.execute(
        text("SELECT MAX(datetime) FROM readings WHERE station_id = :sid"),
        {"sid": station_id},
    ).scalar()
    if not latest_ts:
        return []
    if isinstance(latest_ts, str):
        latest_ts = datetime.fromisoformat(latest_ts.replace('Z', '+00:00')[:19])
    since = latest_ts - timedelta(hours=hours)

    rows = db.execute(
        text("""
            SELECT
                datetime,
                parameter,
                unit,
                value
            FROM readings
            WHERE station_id = :sid
              AND datetime >= :since
            ORDER BY datetime
        """),
        {"sid": station_id, "since": since},
    ).fetchall()

    if not rows:
        return []

    # Group by hour in Python to support all SQL dialects (SQLite, PostgreSQL, etc.)
    from collections import defaultdict
    temp_by_hour = defaultdict(lambda: defaultdict(list))
    
    for row in rows:
        dt = row[0]
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00')[:19])
            except ValueError:
                # Fallback purely for safety
                continue
        hour_str = dt.strftime('%Y-%m-%dT%H:00:00')
        param = row[1].lower()
        temp_by_hour[hour_str][param].append((row[2], row[3]))

    by_hour = defaultdict(dict)
    for hour_str, params in temp_by_hour.items():
        for param, values_list in params.items():
            valid_values = [v[1] for v in values_list if v[1] is not None]
            if not valid_values:
                continue
            avg_val = sum(valid_values) / len(valid_values)
            unit = values_list[0][0]
            by_hour[hour_str][param] = {"value": avg_val, "unit": unit}

    history = []
    for hour_str, params in sorted(by_hour.items()):
        temp_c = params.get("temperature", {}).get("value", 25.0)
        sub_indices: dict = {}
        pollutant_values: dict = {}

        for param, data in params.items():
            try:
                ugm3 = data["value"]
                if data["unit"] and data["unit"].lower() == "ppb" and param in GAS_MW:
                    ugm3 = ppb_to_ugm3(data["value"], GAS_MW[param], temp_c)

                pollutant_values[param] = round(ugm3, 2)

                if param in AQI_BREAKPOINTS:
                    si = calculate_sub_index(ugm3, param)
                    if si and si > 0:
                        sub_indices[param] = si
            except Exception:
                continue

        overall_aqi = max(sub_indices.values()) if sub_indices else 0
        aqi_status = get_aqi_category(overall_aqi)

        history.append(HistoryPointSchema(
            datetime=hour_str,
            overall_aqi=overall_aqi,
            aqi_category=aqi_status["category"],
            aqi_color=aqi_status["color"],
            pollutants=pollutant_values,
        ))

    return history


# ---------------------------------------------------------------------------
# PUBLIC — 72-hour coupled forecast (Phase 2)
# ---------------------------------------------------------------------------

@router.get("/aqi/forecast72/{station_id}", response_model=Forecast72Schema, tags=["AQI Data"])
def get_forecast_72(
    station_id: int,
    db: Session = Depends(get_db),
):
    """
    72-hour AQI forecast with per-pollutant breakdowns (PM2.5, PM10, O3),
    90% confidence intervals, and coupling diagnostics (inversion score,
    fire-plume contribution, corrected PBL height, iteration count).

    Data is served from the predictions table (populated by the APScheduler
    job every 6 hours via coupling_engine). Returns the next 72 rows ordered
    by prediction_time.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station {station_id} not found")

    now = datetime.now(tz=None).replace(tzinfo=None)  # naive UTC
    predictions = (
        db.query(Prediction)
        .filter(
            Prediction.station_id == station_id,
            Prediction.prediction_time >= now,
        )
        .order_by(Prediction.prediction_time)
        .limit(72)
        .all()
    )

    steps = [
        Forecast72StepSchema(
            hour_offset=p.hour_offset or i + 1,
            prediction_time=(
                p.prediction_time.isoformat()
                if hasattr(p.prediction_time, "isoformat")
                else str(p.prediction_time)
            ),
            predicted_aqi=int(p.predicted_aqi) if p.predicted_aqi is not None else 0,
            predicted_pm25=p.predicted_pm25,
            predicted_pm10=p.predicted_pm10,
            predicted_o3=p.predicted_o3,
            pm25_lower=p.pm25_lower,
            pm25_upper=p.pm25_upper,
            pm10_lower=p.pm10_lower,
            pm10_upper=p.pm10_upper,
            inversion_score=p.inversion_score,
            inversion_category=p.inversion_category,
            plume_pm25_contrib=p.plume_pm25_contrib,
            pbl_height_corrected=p.pbl_height_corrected,
            iterations_run=p.iterations_run,
            converged=bool(p.converged) if p.converged is not None else None,
            model_version=p.model_version,
        )
        for i, p in enumerate(predictions)
    ]

    return Forecast72Schema(
        station_id=station_id,
        station_name=station.name,
        forecast_generated_at=datetime.utcnow().isoformat(),
        horizon_hours=len(steps),
        steps=steps,
    )


# ---------------------------------------------------------------------------
# PUBLIC — Predictions
# ---------------------------------------------------------------------------

@router.get("/predictions/{station_id}", response_model=List[PredictionSchema], tags=["AQI Data"])
def get_predictions(station_id: int, hours: Optional[int] = None, db: Session = Depends(get_db)):
    """48-hour AQI forecast for a station. Returns cached predictions or fallback data.
    If hours is provided, returns predictions within that past window too."""
    query = db.query(Prediction).filter(Prediction.station_id == station_id)
    if hours is not None:
        query = query.filter(Prediction.prediction_time >= datetime.utcnow() - timedelta(hours=hours))
    else:
        query = query.filter(Prediction.prediction_time >= datetime.utcnow())
    predictions = query.order_by(Prediction.prediction_time).all()

    if predictions:
        return [
            PredictionSchema(
                station_id=p.station_id,
                prediction_time=p.prediction_time.isoformat() if hasattr(p.prediction_time, "isoformat") else str(p.prediction_time),
                predicted_aqi=int(p.predicted_aqi),
                model_version=p.model_version or "xgb_tuned_v2.0",
            )
            for p in predictions
        ]

    # No predictions in DB - generate fallback based on current AQI
    from app.api.endpoints import get_realtime_aqi as get_realtime
    try:
        realtime = get_realtime(db)
        station_data = next((s for s in realtime if s.station_id == station_id), None)
        base_aqi = station_data.overall_aqi if station_data else 100
    except:
        base_aqi = 100

    # Generate 24-hour forecast with realistic variations
    fallback = []
    now = datetime.utcnow()
    for i in range(1, 25):
        pred_time = now + timedelta(hours=i)
        # Add time-of-day variation (higher in morning/evening rush hours)
        hour = pred_time.hour
        time_variation = 0
        if 7 <= hour <= 9 or 17 <= hour <= 19:  # Rush hours
            time_variation = 15
        elif 1 <= hour <= 6:  # Night - lower
            time_variation = -10
        
        variation = int((i % 6) * 5) - 12 + time_variation
        pred_aqi = max(30, min(350, base_aqi + variation))
        fallback.append(PredictionSchema(
            station_id=station_id,
            prediction_time=pred_time.isoformat(),
            predicted_aqi=pred_aqi,
            model_version="forecast_v1.0",
        ))
    return fallback


@router.post("/predictions/generate", status_code=202, tags=["Admin/MLOps"])
def trigger_prediction_job(db: Session = Depends(get_db)):
    generate_and_save_predictions(db)
    return {"message": "Predictions regenerated."}


# ---------------------------------------------------------------------------
# PROTECTED — Authentication
# ---------------------------------------------------------------------------

@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
def register_user(user_data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    db_user = User(
        full_name=user_data.full_name,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        user_type=user_data.user_type,
        location=user_data.location,
        is_active=True,
        is_verified=True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
def login_user(user_credentials: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.get("/auth/me", response_model=UserResponse, tags=["Authentication"])
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user


# ---------------------------------------------------------------------------
# Admin/MLOps — Scheduler
# ---------------------------------------------------------------------------

@router.get("/scheduler/status", tags=["Admin/MLOps"])
def get_scheduler_status():
    if not scheduler.running:
        return {"status": "stopped", "jobs": []}
    return {
        "status": "running",
        "job_count": len(scheduler.get_jobs()),
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
            }
            for j in scheduler.get_jobs()
        ],
    }


@router.post("/scheduler/run/predictions", status_code=202, tags=["Admin/MLOps"])
def trigger_predictions_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_generate_predictions)
    return {"message": "Prediction job triggered."}


@router.post("/scheduler/run/retrain", status_code=202, tags=["Admin/MLOps"])
def trigger_retrain_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_retrain_model)
    return {"message": "Model retraining triggered."}


@router.post("/scheduler/run/ingestion", status_code=202, tags=["Admin/MLOps"])
def trigger_ingestion_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(job_live_ingestion)
    return {"message": "Live ingestion job triggered."}


# ---------------------------------------------------------------------------
# Groq AI Assistant & Health Advisory
# ---------------------------------------------------------------------------

from app.services.groq_ai_service import generate_ai_advisory, chat_with_airwatch

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None
    station_id: Optional[int] = None

@router.get("/ai/advisory", tags=["AI Advisory"])
def get_air_quality_advisory(
    station_id: Optional[int] = Query(None, description="Optional station ID to filter advisory"),
    db: Session = Depends(get_db),
):
    """
    Returns an LLM-generated health advisory & risk assessment powered by Groq,
    grounded in current monitoring station telemetry.
    """
    return generate_ai_advisory(db, station_id=station_id)


@router.post("/ai/chat", tags=["AI Advisory"])
def chat_with_assistant(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Interactive AI assistant for citizens, researchers, and officials to ask
    questions regarding current air quality, health precautions, and trends.
    """
    history_dicts = [h.model_dump() for h in request.history] if request.history else None
    return chat_with_airwatch(
        db,
        message=request.message,
        history=history_dicts,
        station_id=request.station_id,
    )


