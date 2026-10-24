import requests
from datetime import datetime

def get_oxford_weather_forecast(target_datetime: datetime) -> dict:
    """
    Fetches hourly weather and precipitation probability for Oxford 
    for future dates using Open-Meteo (no API key required).
    """
    lat = 51.7522
    lon = -1.2560
    
    # Request hourly precipitation, rain amounts, and precipitation probability
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&"
        f"hourly=precipitation_probability,precipitation,rain"
    )
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "hourly" in data:
            times = data["hourly"]["time"]
            prob_list = data["hourly"]["precipitation_probability"]
            precip_list = data["hourly"]["precipitation"]
            
            # Format target datetime to match Open-Meteo's hourly format ("YYYY-MM-DDTHH:00")
            target_str = target_datetime.strftime("%Y-%m-%dT%H:00")
            
            if target_str in times:
                idx = times.index(target_str)
                return {
                    "precipitation_probability": prob_list[idx],  # e.g., 70.0 (%)
                    "precipitation_mm": precip_list[idx]          # e.g., 1.2 (mm)
                }
    except Exception as e:
        print(f"Weather API fetch failed: {e}")
        
    # Default fallback if offline or out of bounds
    return {"precipitation_probability": 0.0, "precipitation_mm": 0.0}


def get_oxford_weather(target_datetime: datetime) -> dict:
    """Compatibility alias for the Oxford weather forecast helper."""
    return get_oxford_weather_forecast(target_datetime)