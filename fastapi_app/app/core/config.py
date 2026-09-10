from pathlib import Path
import tempfile
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file's location (fastapi_app/.env)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# ---------------------------------------------------------------------------
# Delhi NCR geographic domain (SIH PS 26082)
# ---------------------------------------------------------------------------
DELHI_LAT_MIN: float = 28.4
DELHI_LAT_MAX: float = 28.9
DELHI_LON_MIN: float = 76.8
DELHI_LON_MAX: float = 77.5
# Representative grid centroid for single-point met queries (central Delhi)
DELHI_LAT_CENTER: float = 28.65
DELHI_LON_CENTER: float = 77.20

# Punjab/Haryana/UP fire-source bbox for FIRMS stubble-burning hotspot fetch
FIRE_SOURCE_LAT_MIN: float = 29.5
FIRE_SOURCE_LAT_MAX: float = 32.5
FIRE_SOURCE_LON_MIN: float = 73.5
FIRE_SOURCE_LON_MAX: float = 78.5

# ---------------------------------------------------------------------------
# Two-way coupling feedback coefficients
# ---------------------------------------------------------------------------
# ALPHA_PM_PBL: fractional PBL suppression per unit normalized PM2.5.
# Derivation: IGP aerosol-PBL studies (e.g. Kumar et al. 2020, ACP;
#   Srivastava et al. 2021, ResearchGate) document ~15-20% boundary layer
#   height reduction during Delhi severe haze (PM2.5 >300 µg/m³), consistent
#   with a linear coefficient of ~0.18 at PM2.5_norm = 1.0 (500 µg/m³).
#   Calibration-tunable against Phase-5 Oct-Nov 2023 backtest.
ALPHA_PM_PBL: float = 0.18

# BETA_TEMP_PM: surface temperature reduction (°C) per 100 µg/m³ PM2.5.
# Derivation: aerosol direct radiative forcing at surface reaches -80 W/m²
#   in severe Delhi winter haze (Ramachandran & Kedia 2010, ACP; Mallet et al.
#   IGP studies). −4.25°C per unit AOD (IAS studies) at AOD~0.8-1.2 for
#   PM2.5~300-500 µg/m³ implies ~0.20-0.35°C per 100 µg/m³. We use 0.25
#   as a central estimate; tunable in Phase-5.
BETA_TEMP_PM: float = 0.25  # °C per 100 µg/m³

# Coupling iteration settings
COUPLING_MAX_ITERATIONS: int = 3
COUPLING_CONVERGENCE_THRESHOLD: float = 2.0  # µg/m³ PM2.5 change to stop early

# PBL height below which inversion is considered "strong" (metres)
INVERSION_PBL_THRESHOLD: float = 500.0  # severe inversion below this
INVERSION_PBL_CRITICAL: float = 200.0   # critical trapping threshold

# ---------------------------------------------------------------------------
# External API URLs
# ---------------------------------------------------------------------------
OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
NASA_FIRMS_URL: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FORECAST_HORIZON_HOURS: int = 72

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"

    # Database Settings
    DATABASE_URL: str

    # JWT Settings
    JWT_SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # OpenAQ (Physical sensor data)
    OPENAQ_API_KEY: str = ""

    # Groq LLM API
    GROQ_API_KEY: str = ""

    # NASA FIRMS active fire API (for stubble-burning plume source)
    FIRMS_API_KEY: str = ""

    # Delhi NCR bounding box (can override defaults via env)
    DELHI_LAT_MIN: float = 28.4
    DELHI_LAT_MAX: float = 28.9
    DELHI_LON_MIN: float = 76.8
    DELHI_LON_MAX: float = 77.5

    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"
    SQLITE_PATH: str = ""
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://localhost:4028,"
        "https://air-watch-theta.vercel.app,"
        "https://airwatch-p0bo.onrender.com"
    )
    ALLOWED_ORIGIN_REGEX: str = (
        r"https://.*\.vercel\.app|https://.*\.onrender\.com|http://localhost(:\d+)?"
    )

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    @computed_field
    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @computed_field
    @property
    def database_url(self) -> str:
        if not self.DATABASE_URL.startswith("sqlite:///"):
            return self.DATABASE_URL

        sqlite_target = self.DATABASE_URL.removeprefix("sqlite:///")

        if sqlite_target.startswith("/"):
            return self.DATABASE_URL

        if self.SQLITE_PATH:
            normalized_path = self.SQLITE_PATH.replace("\\", "/")
            if not normalized_path.startswith("/"):
                normalized_path = f"/{normalized_path}"
            return f"sqlite:///{normalized_path}"

        if self.ENVIRONMENT.lower() in {"production", "staging"}:
            temp_db_path = Path(tempfile.gettempdir()) / "airwatch.db"
            return f"sqlite:///{temp_db_path.as_posix()}"

        return self.DATABASE_URL

settings = Settings()
