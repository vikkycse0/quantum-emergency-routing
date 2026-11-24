import numpy as np
from typing import Dict, Any, List

class FeatureEngineer:
    WEATHER_MAP = {
        'clear': 0,
        'cloudy': 1,
        'rain': 2,
        'heavy_rain': 3
    }

    @staticmethod
    def extract_features(
        hour: int,
        day_of_week: int,
        distance_km: float,
        weather: str = 'clear',
        rainfall_mm: float = 0.0,
        has_event: int = 0,
        has_accident: int = 0
    ) -> np.ndarray:
        """
        Extracts independent feature vector for travel time regression.
        Features: [hour, day_of_week, distance_km, weather_code, rainfall_mm, is_rush_hour, has_event, has_accident]
        """
        weather_code = FeatureEngineer.WEATHER_MAP.get(weather.lower(), 0)
        
        # Inferred rainfall if not provided explicitly
        if rainfall_mm == 0.0:
            if weather_code == 2:
                rainfall_mm = 8.0
            elif weather_code == 3:
                rainfall_mm = 25.0

        # Rush hour indicator (8-10 AM or 5-8 PM)
        is_rush_hour = 1 if hour in [8, 9, 10, 17, 18, 19, 20] else 0
        
        return np.array([[hour, day_of_week, distance_km, weather_code, rainfall_mm, is_rush_hour, has_event, has_accident]], dtype=np.float32)
