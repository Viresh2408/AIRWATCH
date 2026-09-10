"""
scheduler.py — APScheduler setup for AirWatch Pro

Jobs:
  1. [Every 1 hour]   → generate_and_save_predictions()  (keeps forecast fresh)
  2. [Every day 2 AM] → prepare_ml_features() + train_and_save_model()  (retrains model on latest data)

How APScheduler works here:
  - BackgroundScheduler runs in a daemon thread alongside FastAPI (non-blocking)
  - Jobs are registered with triggers (IntervalTrigger or CronTrigger)
  - Scheduler is started on app startup and shut down cleanly on app exit
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# --- The single scheduler instance shared across the app ---
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


# ---------------------------------------------------------------------------
# JOB DEFINITIONS
# Each job is a plain Python function. APScheduler calls them in a thread.
# ---------------------------------------------------------------------------

def job_live_ingestion():
    """
    Job 0 — Runs every 15 minutes.
    Calls live Delhi telemetry ingestion to pull the latest real-time
    observational air quality and meteorology data from Open-Meteo,
    keeping readings and coupled forecasts fresh for all stations.
    """
    logger.info(f"[SCHEDULER] job_live_ingestion started at {datetime.now()}")
    try:
        from app.core.db import SessionLocal
        from app.services.live_delhi_fetcher import ingest_live_delhi_telemetry

        db = SessionLocal()
        try:
            summary = ingest_live_delhi_telemetry(db)
            logger.info(f"[SCHEDULER] job_live_ingestion done. Summary: {summary}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[SCHEDULER] job_live_ingestion FAILED: {e}", exc_info=True)


def job_generate_predictions():
    """
    Job 1 — Runs every hour.
    Opens a fresh DB session, generates 48-hour AQI predictions for all
    stations using the currently loaded ML model, and saves them to DB.
    """
    logger.info(f"[SCHEDULER] job_generate_predictions started at {datetime.now()}")
    try:
        # Import here to avoid circular imports at module load time
        from app.core.db import SessionLocal
        from app.services.prediction_service import generate_and_save_predictions

        db = SessionLocal()
        try:
            generate_and_save_predictions(db)
            logger.info("[SCHEDULER] job_generate_predictions completed successfully.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[SCHEDULER] job_generate_predictions FAILED: {e}", exc_info=True)


def job_retrain_model():
    """
    Job 2 — Runs every day at 2:00 AM IST.
    Step A: Rebuild the ML feature store CSV from the latest DB readings.
    Step B: Retrain the XGBoost model on the fresh feature store.
    This ensures the model learns from newly ingested sensor data.
    """
    logger.info(f"[SCHEDULER] job_retrain_model started at {datetime.now()}")
    try:
        import os, sys
        # Ensure we run from fastapi_app directory so relative paths resolve
        fastapi_app_dir = os.path.join(os.path.dirname(__file__), '..', '..')
        os.chdir(os.path.abspath(fastapi_app_dir))

        from app.services.ml_feature_store import prepare_ml_features
        from app.services.ml_pipeline import train_and_save_model

        # Step A: Rebuild feature store from DB
        logger.info("[SCHEDULER] Step A — Rebuilding ML feature store...")
        feature_df = prepare_ml_features()

        if feature_df.empty:
            logger.error("[SCHEDULER] Feature store is empty — skipping retraining.")
            return

        # Step B: Retrain model
        logger.info("[SCHEDULER] Step B — Retraining XGBoost model...")
        mae = train_and_save_model(feature_df)
        logger.info(f"[SCHEDULER] job_retrain_model completed. MAE = {mae:.2f}")

    except Exception as e:
        logger.error(f"[SCHEDULER] job_retrain_model FAILED: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# SCHEDULER REGISTRATION
# Called once from main.py lifespan on app startup.
# ---------------------------------------------------------------------------

def start_scheduler():
    """
    Registers all jobs and starts the background scheduler.
    Called during FastAPI app startup.
    """
    # Job 0: Fetch live data from OpenAQ every 15 minutes
    scheduler.add_job(
        func=job_live_ingestion,
        trigger=IntervalTrigger(minutes=15),
        id="live_ingestion",
        name="OpenAQ Live Data Ingestion (15 min)",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Job 1: Generate predictions every hour
    scheduler.add_job(
        func=job_generate_predictions,
        trigger=IntervalTrigger(hours=1),
        id="generate_predictions",
        name="Hourly AQI Prediction Generation",
        replace_existing=True,
        misfire_grace_time=300,   # Allow up to 5 min late if server was busy
    )

    # Job 2: Retrain model every day at 2:00 AM IST
    scheduler.add_job(
        func=job_retrain_model,
        trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Kolkata"),
        id="retrain_model",
        name="Daily Model Retraining",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1 hour late
    )

    scheduler.start()
    logger.info("[SCHEDULER] APScheduler started. Jobs registered:")
    for job in scheduler.get_jobs():
        logger.info(f"  → {job.name} | next run: {job.next_run_time}")


def shutdown_scheduler():
    """Gracefully shuts down the scheduler on app exit."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] APScheduler shut down.")
