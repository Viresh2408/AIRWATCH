import numpy as np
from typing import Dict, Any

# Constants for Unit Conversion (ppb to μg/m³)
# MW is used to convert ppb (parts per billion) to μg/m³ 
GAS_MW = {
    'no': 30.01,    # Nitric Oxide
    'no2': 46.01,   # Nitrogen Dioxide
    'so2': 64.06,   # Sulfur Dioxide
    'co': 28.01,    # Carbon Monoxide
    'o3': 48.00     # Ozone
}

# CPCB AQI Sub-Index Breakpoints (Simplified for Core Pollutants, 24hr standard)
# Format: [Lower_AQI, Upper_AQI, Lower_Conc_in_μg/m³, Upper_Conc_in_μg/m³]
# CO concentrations are provided in mg/m³ for CPCB standards.
AQI_BREAKPOINTS = {
    'pm25': [[0, 50, 0, 30], [51, 100, 31, 60], [101, 200, 61, 90], [201, 300, 91, 120], [301, 400, 121, 250], [401, 500, 251, 500]],
    'pm10': [[0, 50, 0, 50], [51, 100, 51, 100], [101, 200, 101, 250], [201, 300, 251, 350], [301, 400, 351, 430], [401, 500, 431, 650]],
    'no2': [[0, 50, 0, 40], [51, 100, 41, 80], [101, 200, 81, 180], [201, 300, 181, 280], [301, 400, 281, 400], [401, 500, 401, 800]],
    'so2': [[0, 50, 0, 40], [51, 100, 41, 80], [101, 200, 81, 180], [201, 300, 181, 280], [301, 400, 281, 400], [401, 500, 401, 800]],
    'o3': [[0, 50, 0, 50], [51, 100, 51, 100], [101, 200, 101, 168], [201, 300, 169, 208], [301, 400, 209, 748], [401, 500, 749, 1000]],
    # CO is often reported in mg/m³ in standards, 1 mg/m³ = 1000 μg/m³
    'co': [[0, 50, 0, 1.0], [51, 100, 1.1, 2.0], [101, 200, 2.1, 10], [201, 300, 10.1, 17], [301, 400, 17.1, 34], [401, 500, 34.1, 50]] 
}

def ppb_to_ugm3(ppb: float, gas_mw: float, temp_c: float = 25.0) -> float:
    """Converts concentration from ppb to µg/m³ (using standard factor)."""
    # Formula: µg/m³ = ppb * MW / 24.45 (at 25°C and 1 atm, standard factor)
    conversion_factor = gas_mw / 24.45
    return ppb * conversion_factor

def calculate_sub_index(conc: float, pollutant: str) -> float:
    """Calculates the CPCB sub-index (I) for a single pollutant."""
    if conc is None or pollutant not in AQI_BREAKPOINTS: return 0
    breakpoints = AQI_BREAKPOINTS[pollutant]
    
    # Find the appropriate concentration (Bp_low, Bp_high) and AQI (Ip_low, Ip_high) range
    for Ip_low, Ip_high, Bp_low, Bp_high in breakpoints:
        if Bp_low <= conc <= Bp_high:
            # CPCB formula: I = [(I_high - I_low) / (B_high - B_low)] * (C - B_low) + I_low
            if Bp_high == Bp_low: return Ip_low 
            
            I = ((Ip_high - Ip_low) / (Bp_high - Bp_low)) * (conc - Bp_low) + Ip_low
            return round(I)
        
        # Handle concentrations above the highest range by extrapolating
        if conc > breakpoints[-1][3]: 
             # Use the highest range's ratio for extrapolation
             return round((breakpoints[-1][1] / breakpoints[-1][3]) * conc) 
             
    return 0 

def get_aqi_category(aqi_value: float) -> Dict[str, str]:
    """Returns the category and color based on the final AQI value."""
    if aqi_value <= 50: return {"category": "Good", "color": "#00A000"} 
    elif aqi_value <= 100: return {"category": "Satisfactory", "color": "#7FC700"} 
    elif aqi_value <= 200: return {"category": "Moderately Polluted", "color": "#FFD700"} 
    elif aqi_value <= 300: return {"category": "Poor", "color": "#FF8C00"} 
    elif aqi_value <= 400: return {"category": "Very Poor", "color": "#DC143C"} 
    else: return {"category": "Severe", "color": "#800000"}


def get_aqi_color(aqi_value: float) -> str:
    """Returns just the hex color string for a given AQI value.

    Convenience wrapper around get_aqi_category() used by tests and
    frontend colour-coding utilities that only need the colour.
    """
    return get_aqi_category(aqi_value)["color"]


def validate_pollutants(data: Dict[str, Any]) -> bool:
    """Validates a pollutant readings dict.

    Returns True if data is non-empty and all values are non-negative
    numbers. Returns False if data is empty or any value is negative.
    """
    if not data:
        return False
    for val in data.values():
        try:
            if float(val) < 0:
                return False
        except (TypeError, ValueError):
            return False
    return True