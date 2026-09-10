import math
import requests
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.models.aqi import Station, Reading, Prediction
from app.services.prediction_service import generate_and_save_predictions

logger = logging.getLogger(__name__)

DELHI_STATIONS = [
    (3409620, "Anand Vihar, Delhi", 28.6469, 77.3164),
    (3409621, "ITO, Delhi", 28.6310, 77.2433),
    (3409622, "Punjabi Bagh, Delhi", 28.6683, 77.1333),
    (3409623, "RK Puram, Delhi", 28.5644, 77.1895),
    (3409624, "Dwarka Sector 8, Delhi", 28.5822, 77.0330),
    (3409625, "Noida Sector 62, NCR", 28.6270, 77.3640),
    (3409626, "Gurugram Sector 51, NCR", 28.4595, 77.0266),
]

def ingest_live_delhi_telemetry(db: Session) -> dict:
    """
    Fetches actual real-time observational and hourly air quality + met data
    from Open-Meteo for all 7 Delhi NCR stations and idempotently upserts them
    so the dashboard always reflects live real-world Delhi AQI without wiping history.
    """
    now_utc = datetime.now(timezone.utc)
    current_hour_str = now_utc.strftime("%Y-%m-%dT%H:00")
    logger.info(f"[LIVE INGESTION] Starting live Delhi NCR telemetry pull at {now_utc.isoformat()}...")

    total_inserted = 0

    # Ensure stations exist
    for sid, name, lat, lon in DELHI_STATIONS:
        st = db.query(Station).filter(Station.id == sid).first()
        if not st:
            db.add(Station(id=sid, name=name, lat=lat, lon=lon))
            db.commit()

    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

    for sid, name, lat, lon in DELHI_STATIONS:
        aq_url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"
            f"&past_days=3"
        )
        met_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,relativehumidity_2m"
            f"&past_days=3"
        )

        try:
            r_aq = requests.get(aq_url, timeout=15)
            r_met = requests.get(met_url, timeout=15)
            if r_aq.status_code != 200 or r_met.status_code != 200:
                logger.warning(f"[WARN] Failed to fetch live data for {name}: {r_aq.status_code}, {r_met.status_code}")
                continue

            aq_data = r_aq.json().get("hourly", {})
            met_data = r_met.json().get("hourly", {})

            times = aq_data.get("time", [])
            pm25_list = aq_data.get("pm2_5", [])
            pm10_list = aq_data.get("pm10", [])
            no2_list = aq_data.get("nitrogen_dioxide", [])
            so2_list = aq_data.get("sulphur_dioxide", [])
            co_list = aq_data.get("carbon_monoxide", [])
            o3_list = aq_data.get("ozone", [])

            met_times = met_data.get("time", [])
            temp_list = met_data.get("temperature_2m", [])
            rh_list = met_data.get("relativehumidity_2m", [])

            station_rows = []
            for i, t_str in enumerate(times):
                # Ingest up to current hour
                if t_str > current_hour_str:
                    break
                dt = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)

                pm25_val = pm25_list[i] if i < len(pm25_list) else None
                pm10_val = pm10_list[i] if i < len(pm10_list) else None
                no2_val = no2_list[i] if i < len(no2_list) else None
                so2_val = so2_list[i] if i < len(so2_list) else None
                co_val = (co_list[i] / 1000.0) if (i < len(co_list) and co_list[i] is not None) else None
                o3_val = o3_list[i] if i < len(o3_list) else None

                # Find matching met index
                temp_val = 28.0
                rh_val = 65.0
                if t_str in met_times:
                    m_idx = met_times.index(t_str)
                    temp_val = temp_list[m_idx] if m_idx < len(temp_list) else 28.0
                    rh_val = rh_list[m_idx] if m_idx < len(rh_list) else 65.0

                param_map = [
                    ("pm25", "µg/m³", pm25_val),
                    ("pm10", "µg/m³", pm10_val),
                    ("no2", "µg/m³", no2_val),
                    ("so2", "µg/m³", so2_val),
                    ("co", "mg/m³", co_val),
                    ("o3", "µg/m³", o3_val),
                    ("temperature", "°C", temp_val),
                    ("relativehumidity", "%", rh_val),
                ]

                for p_name, unit, val in param_map:
                    if val is not None:
                        station_rows.append({
                            "station_id": sid,
                            "datetime": dt,
                            "parameter": p_name,
                            "unit": unit,
                            "value": round(float(val), 2),
                        })

            if station_rows:
                # Batch upsert in chunks of 500
                chunk_size = 500
                for start_idx in range(0, len(station_rows), chunk_size):
                    chunk = station_rows[start_idx:start_idx + chunk_size]
                    stmt = dialect_insert(Reading).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["station_id", "datetime", "parameter"],
                        set_={
                            "value": stmt.excluded.value,
                            "unit": stmt.excluded.unit,
                        }
                    )
                    db.execute(stmt)
                db.commit()
                total_inserted += len(station_rows)
                logger.info(f"[LIVE INGESTION] Upserted {len(station_rows)} live records for {name}.")

        except Exception as e:
            logger.error(f"[ERROR] Live ingestion exception for {name}: {e}")
            db.rollback()

    logger.info(f"[LIVE INGESTION] Completed. Total live records upserted: {total_inserted}")

    # Re-generate coupled predictions for Delhi stations based on latest telemetry
    try:
        db.execute(
            text("DELETE FROM predictions WHERE station_id IN :sids"),
            {"sids": tuple(s[0] for s in DELHI_STATIONS)}
        )
        db.commit()
        logger.info("[LIVE INGESTION] Re-running coupled forecasting engine on live telemetry...")
        preds_count = generate_and_save_predictions(db)
        logger.info(f"[LIVE INGESTION] Generated {preds_count} 72-hour coupled predictions.")
    except Exception as e:
        logger.error(f"[LIVE INGESTION] Coupled prediction generation failed: {e}")
        preds_count = 0

    return {"inserted": total_inserted, "predictions": preds_count}

if __name__ == "__main__":
    db = SessionLocal()
    try:
        ingest_live_delhi_telemetry(db)
    finally:
        db.close()
