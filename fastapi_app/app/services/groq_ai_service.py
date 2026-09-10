"""
groq_ai_service.py - Groq-powered AI air quality advisory and chat assistant for AirWatch
"""

import logging
import requests
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.models.aqi import Station, Reading, Prediction
from app.services.aqi_calculator import get_aqi_category

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODELS = ["qwen/qwen3.6-27b", "openai/gpt-oss-120b"]


def _call_groq(messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 1000) -> Optional[str]:
    """Helper to send chat completion requests to Groq with fallback models."""
    api_key = settings.GROQ_API_KEY
    if not api_key:
        logger.warning("[GROQ_AI] GROQ_API_KEY is not configured in settings.")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    candidate_models = [DEFAULT_MODEL] + FALLBACK_MODELS

    for model in candidate_models:
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.warning(f"[GROQ_AI] Model {model} failed with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"[GROQ_AI] Error invoking Groq model {model}: {e}")

    return None


def get_current_station_context(db: Session, station_id: Optional[int] = None) -> Dict[str, Any]:
    """Gathers recent pollutant data and predictions for context."""
    if station_id:
        stations = db.query(Station).filter(Station.id == station_id).all()
    else:
        stations = db.query(Station).all()

    if not stations:
        return {"stations": []}

    station_data = []
    for st in stations:
        # Get latest reading for each parameter
        latest_readings = (
            db.query(Reading)
            .filter(Reading.station_id == st.id)
            .order_by(Reading.datetime.desc())
            .limit(15)
            .all()
        )
        pollutants = {}
        for r in latest_readings:
            if r.parameter not in pollutants:
                pollutants[r.parameter] = {
                    "value": round(r.value, 2) if r.value is not None else 0,
                    "unit": r.unit,
                }

        # Get latest prediction
        latest_pred = (
            db.query(Prediction)
            .filter(Prediction.station_id == st.id)
            .order_by(Prediction.prediction_time.desc())
            .first()
        )

        station_data.append({
            "station_id": st.id,
            "station_name": st.name,
            "lat": st.lat,
            "lon": st.lon,
            "pollutants": pollutants,
            "predicted_aqi": round(latest_pred.predicted_aqi) if latest_pred else None,
        })

    return {"stations": station_data}


def generate_ai_advisory(db: Session, station_id: Optional[int] = None) -> Dict[str, Any]:
    """Generates an intelligent LLM health advisory based on live monitoring station data."""
    context = get_current_station_context(db, station_id)

    if not context["stations"]:
        return {
            "summary": "No active monitoring stations found in the database.",
            "health_advisory": [],
            "source": "fallback",
        }

    target = context["stations"][0]
    pol_summary = ", ".join([f"{k}: {v['value']} {v['unit']}" for k, v in target["pollutants"].items()]) or "Normal"

    system_prompt = (
        "You are AirWatch AI, an expert environmental scientist and public health consultant. "
        "Analyze the provided air quality data and provide clear, empathetic, and actionable guidance. "
        "Format your response as a valid JSON object with the following keys:\n"
        "- summary: 2 sentences explaining current air status and primary concern.\n"
        "- health_risk_level: Low, Moderate, High, or Severe.\n"
        "- vulnerable_groups: Guidance for children, pregnant women, and elderly or asthmatics.\n"
        "- outdoor_activities: Specific advice for exercise, jogging, and commuting.\n"
        "- protective_measures: Mask suggestions (N95/None), indoor air filters, windows open/closed.\n"
        "- forecast_insight: Brief remark on whether air quality is predicted to improve or worsen."
    )

    user_prompt = (
        f"Station: {target['station_name']}\n"
        f"Pollutants: {pol_summary}\n"
        f"Predicted Next AQI: {target['predicted_aqi'] or 'N/A'}\n"
        "Generate the JSON health advisory now. Output ONLY valid JSON."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    llm_output = _call_groq(messages, temperature=0.3)

    if llm_output:
        try:
            cleaned = llm_output.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned.removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            parsed["station_name"] = target["station_name"]
            parsed["station_id"] = target["station_id"]
            parsed["pollutants"] = target["pollutants"]
            parsed["source"] = "groq"
            return parsed
        except Exception as e:
            logger.warning(f"[GROQ_AI] Failed to parse JSON response: {e}")

    # Fallback advisory if Groq is offline
    return {
        "station_name": target["station_name"],
        "station_id": target["station_id"],
        "summary": f"Air quality at {target['station_name']} is currently being tracked. Primary readings: {pol_summary}.",
        "health_risk_level": "Moderate",
        "vulnerable_groups": "Sensitive individuals should limit prolonged outdoor exertion.",
        "outdoor_activities": "Outdoor activities are acceptable, take breaks if experiencing symptoms.",
        "protective_measures": "Consider wearing a mask during peak traffic hours.",
        "forecast_insight": f"Predicted AQI is around {target['predicted_aqi'] or 'standard levels'}.",
        "source": "rule-based fallback",
    }


def chat_with_airwatch(db: Session, message: str, history: Optional[List[Dict[str, str]]] = None, station_id: Optional[int] = None) -> Dict[str, Any]:
    """Conversational assistant for users to ask questions about air quality and safety."""
    context = get_current_station_context(db, station_id)

    stations_summary = []
    for s in context["stations"][:4]:
        pol_str = ", ".join([f"{k}={v['value']}" for k, v in s["pollutants"].items()])
        stations_summary.append(f"- {s['station_name']}: {pol_str or 'Data updating'}")

    context_str = "\n".join(stations_summary) if stations_summary else "Live stations active."

    system_prompt = (
        "You are AirWatch Assistant, an intelligent, helpful environmental advisor. "
        "You have direct access to real-time air quality monitors and ML forecasting models in the region.\n\n"
        f"CURRENT LIVE STATION DATA:\n{context_str}\n\n"
        "Guidelines:\n"
        "1. Give direct, factual, and helpful responses to user queries about pollution, safety, masks, travel, and symptoms.\n"
        "2. Ground your answers in the station data above when relevant.\n"
        "3. Keep answers concise (2-4 paragraphs max), professional, and encouraging."
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for turn in history[-6:]:  # Keep last 3 turns
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    reply = _call_groq(messages, temperature=0.5)

    if not reply:
        reply = (
            "I am currently operating with local sensor telemetry. "
            "Our monitoring stations indicate active data collection. "
            "Please check the live dashboard map for precise pollutant levels."
        )

    return {
        "reply": reply,
        "station_context_count": len(context["stations"]),
        "model": DEFAULT_MODEL,
    }
