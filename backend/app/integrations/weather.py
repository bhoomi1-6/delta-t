import requests
from datetime import datetime

def get_oxford_weather(target_datetime: datetime) -> dict:
    """
    Fetches hourly weather forecast for Oxford from Open-Meteo.
    Returns precipitation and temperature for the specific hour.
    """
    # Oxford coordinates
    lat = 51.7522
    lon = -1.2560
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation,weathercode"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "hourly" in data:
            times = data["hourly"]["time"]  # List of ISO strings
            precipitation_list = data["hourly"]["precipitation"]
            
            # Format target datetime to match Open-Meteo's hourly format (e.g., "2026-10-25T14:00")
            target_str = target_datetime.strftime("%Y-%m-%dT%H:00")
            
            if target_str in times:
                idx = times.index(target_str)
                return {
                    "precipitation": precipitation_list[idx],  # in mm
                    "raining": precipitation_list[idx] > 0.0
                }
    except Exception as e:
        print(f"Weather API fetch failed: {e}")
        
    # Safe fallback if offline
    return {"precipitation": 0.0, "raining": False}