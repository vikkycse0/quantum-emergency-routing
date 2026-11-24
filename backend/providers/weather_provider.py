import json
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from providers.base import WeatherProvider, DataProvenance
from providers.cache import data_cache

class OpenMeteoWeatherProvider(WeatherProvider):
    """
    Real-time weather provider consuming Open-Meteo API.
    Provides temperature, precipitation, rainfall rate, wind speeds, visibility, and storm risk.
    """
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    # WMO Weather interpretation codes
    WMO_CODE_MAP = {
        0: ("Clear sky", False),
        1: ("Mainly clear", False),
        2: ("Partly cloudy", False),
        3: ("Overcast", False),
        45: ("Fog", True),
        48: ("Depositing rime fog", True),
        51: ("Light drizzle", False),
        53: ("Moderate drizzle", False),
        55: ("Dense drizzle", True),
        61: ("Slight rain", False),
        63: ("Moderate rain", True),
        65: ("Heavy rain", True),
        80: ("Slight rain showers", False),
        81: ("Moderate rain showers", True),
        82: ("Violent rain showers", True),
        95: ("Thunderstorm", True),
        96: ("Thunderstorm with slight hail", True),
        99: ("Thunderstorm with heavy hail", True),
    }

    @property
    def name(self) -> str:
        return "Open-Meteo Real-Time Weather API"

    @property
    def is_live(self) -> bool:
        return True

    def get_weather_at_point(self, lat: float, lng: float) -> Dict[str, Any]:
        cache_key = f"weather_{round(lat, 2)}_{round(lng, 2)}"
        cached = data_cache.get(cache_key)
        if cached:
            data, prov_status, age = cached
            data["provenance"] = prov_status
            data["age_seconds"] = age
            return data

        params = {
            "latitude": round(lat, 4),
            "longitude": round(lng, 4),
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m,visibility",
            "timezone": "auto"
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "QuantumEmergencyRouting/2.0 (OpenMeteoProvider)"}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    raw = json.loads(response.read().decode('utf-8'))
                    current = raw.get("current", {})
                    
                    code = int(current.get("weather_code", 0))
                    condition_text, is_severe = self.WMO_CODE_MAP.get(code, ("Variable Conditions", False))
                    
                    rain_mm = float(current.get("rain", 0.0) or current.get("precipitation", 0.0))
                    temp_c = float(current.get("temperature_2m", 28.0))
                    wind_kmh = float(current.get("wind_speed_10m", 12.0))
                    visibility_m = float(current.get("visibility", 10000.0))
                    
                    # Risk score based on environmental factors
                    risk_multiplier = 1.0
                    if rain_mm > 15.0 or is_severe:
                        risk_multiplier += 0.35
                    if visibility_m < 3000.0:
                        risk_multiplier += 0.20
                    if wind_kmh > 45.0:
                        risk_multiplier += 0.15

                    result = {
                        "temperature_c": temp_c,
                        "precipitation_mm": rain_mm,
                        "rain_mm": rain_mm,
                        "wind_speed_kmh": wind_kmh,
                        "visibility_m": visibility_m,
                        "weather_code": code,
                        "weather_condition": condition_text,
                        "is_severe": is_severe or (rain_mm > 10.0),
                        "environmental_risk_multiplier": round(risk_multiplier, 2),
                        "provenance": DataProvenance.LIVE.value,
                        "age_seconds": 0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": self.name
                    }
                    
                    # Cache for 5 minutes (300 sec)
                    data_cache.set(cache_key, result, ttl_sec=300, source_name=self.name)
                    return result
        except Exception as e:
            print(f"[OpenMeteoWeatherProvider] Live query failed ({e}). Returning degraded weather status.")

        # Graceful fallback state with explicit UNKNOWN provenance
        return {
            "temperature_c": 26.0,
            "precipitation_mm": 0.0,
            "rain_mm": 0.0,
            "wind_speed_kmh": 10.0,
            "visibility_m": 10000.0,
            "weather_code": 0,
            "weather_condition": "Nominal Conditions (Provider Standby)",
            "is_severe": False,
            "environmental_risk_multiplier": 1.0,
            "provenance": DataProvenance.UNAVAILABLE.value,
            "age_seconds": -1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"{self.name} [Offline Mode]"
        }

    def get_weather_along_route(self, route_coords: List[List[float]], sample_points: int = 4) -> Dict[str, Any]:
        """
        Samples weather across points along the route corridor to detect localized downpours.
        """
        if not route_coords:
            return self.get_weather_at_point(17.70, 83.29)
            
        total_points = len(route_coords)
        indices = [int(i * (total_points - 1) / max(1, sample_points - 1)) for i in range(sample_points)]
        
        max_rain = 0.0
        min_vis = 10000.0
        worst_condition = "Clear"
        any_severe = False
        max_risk = 1.0
        
        for idx in indices:
            pt = route_coords[idx]
            w = self.get_weather_at_point(pt[0], pt[1])
            if w["rain_mm"] > max_rain:
                max_rain = w["rain_mm"]
                worst_condition = w["weather_condition"]
            if w["visibility_m"] < min_vis:
                min_vis = w["visibility_m"]
            if w["is_severe"]:
                any_severe = True
            if w.get("environmental_risk_multiplier", 1.0) > max_risk:
                max_risk = w["environmental_risk_multiplier"]

        return {
            "max_rain_along_corridor_mm": max_rain,
            "min_visibility_m": min_vis,
            "worst_condition": worst_condition,
            "has_severe_weather_hazard": any_severe,
            "composite_weather_risk_factor": round(max_risk, 2),
            "sampled_waypoints_count": len(indices),
            "source": self.name
        }

weather_provider = OpenMeteoWeatherProvider()
