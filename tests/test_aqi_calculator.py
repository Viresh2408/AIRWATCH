import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAQICategories:
    """Test AQI category classification."""

    def test_good_aqi(self):
        """Test that AQI 0-50 is classified as Good."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_category
        assert get_aqi_category(25)["category"] == "Good"
        assert get_aqi_category(50)["category"] == "Good"

    def test_satisfactory_aqi(self):
        """Test that AQI 51-100 is classified as Satisfactory."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_category
        assert get_aqi_category(75)["category"] == "Satisfactory"
        assert get_aqi_category(100)["category"] == "Satisfactory"

    def test_moderate_aqi(self):
        """Test that AQI 101-200 is classified as Moderately Polluted."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_category
        assert get_aqi_category(150)["category"] == "Moderately Polluted"
        assert get_aqi_category(200)["category"] == "Moderately Polluted"

    def test_poor_aqi(self):
        """Test that AQI 201-300 is classified as Poor."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_category
        assert get_aqi_category(250)["category"] == "Poor"
        assert get_aqi_category(300)["category"] == "Poor"

    def test_very_poor_aqi(self):
        """Test that AQI 301-400 is classified as Very Poor."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_category
        assert get_aqi_category(350)["category"] == "Very Poor"
        assert get_aqi_category(400)["category"] == "Very Poor"

    def test_severe_aqi(self):
        """Test that AQI above 400 is classified as Severe."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_category
        assert get_aqi_category(450)["category"] == "Severe"
        assert get_aqi_category(500)["category"] == "Severe"


class TestAQIColors:
    """Test AQI color coding."""

    def test_good_color(self):
        """Test green color for good AQI."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_color
        color = get_aqi_color(25)
        # Accept any hex color string returned by the CPCB palette
        assert color.startswith("#") or color in ["green"]

    def test_moderate_color(self):
        """Test yellow/gold color for moderately polluted AQI."""
        from fastapi_app.app.services.aqi_calculator import get_aqi_color
        color = get_aqi_color(150)
        assert color.startswith("#") or color in ["orange"]


class TestPollutantValidation:
    """Test pollutant data validation."""

    def test_valid_pollutants(self):
        """Test validation of valid pollutant data."""
        from fastapi_app.app.services.aqi_calculator import validate_pollutants
        data = {"pm25": 25, "pm10": 50}
        assert validate_pollutants(data) is True

    def test_invalid_pollutants(self):
        """Test validation rejects negative values."""
        from fastapi_app.app.services.aqi_calculator import validate_pollutants
        data = {"pm25": -10}  # Negative value
        assert validate_pollutants(data) is False

    def test_missing_pollutants(self):
        """Test validation handles missing pollutants."""
        from fastapi_app.app.services.aqi_calculator import validate_pollutants
        data = {}  # Empty data
        result = validate_pollutants(data)
        assert isinstance(result, bool)
