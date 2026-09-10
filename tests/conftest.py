import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient fixture shared across tests in a session.

    Used by test_security.py and any other test that needs to make HTTP
    requests against the app without a running server.
    """
    _fastapi_path = os.path.join(os.path.dirname(__file__), '..', 'fastapi_app')
    if _fastapi_path not in sys.path:
        sys.path.insert(0, _fastapi_path)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_pollutants():
    """Sample pollutant data for testing."""
    return {
        "pm25": 35.5,
        "pm10": 75.0,
        "no2": 45.0,
        "so2": 15.0,
        "o3": 60.0,
        "co": 2.0
    }


@pytest.fixture
def bad_pollutants():
    """Sample pollutant data for poor air quality."""
    return {
        "pm25": 150.0,
        "pm10": 250.0,
        "no2": 150.0,
        "so2": 100.0,
        "o3": 180.0,
        "co": 10.0
    }


@pytest.fixture
def good_pollutants():
    """Sample pollutant data for good air quality."""
    return {
        "pm25": 12.0,
        "pm10": 30.0,
        "no2": 15.0,
        "so2": 5.0,
        "o3": 25.0,
        "co": 0.5
    }
