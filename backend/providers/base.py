from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

class DataProvenance(str, Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    SIMULATED = "SIMULATED"
    UNAVAILABLE = "UNAVAILABLE"

class BaseProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def is_live(self) -> bool:
        pass

class WeatherProvider(BaseProvider):
    @abstractmethod
    def get_weather_at_point(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Retrieves real-time weather metrics at a specific geographic coordinate.
        Returns: {
            "temperature_c": float,
            "precipitation_mm": float,
            "rain_mm": float,
            "precipitation_probability": float,
            "wind_speed_kmh": float,
            "visibility_m": float,
            "weather_code": int,
            "weather_condition": str,
            "is_severe": bool,
            "provenance": DataProvenance,
            "timestamp": str,
            "source": str
        }
        """
        pass

    @abstractmethod
    def get_weather_along_route(self, route_coords: List[List[float]], sample_points: int = 5) -> Dict[str, Any]:
        """
        Samples weather along a multi-kilometer road corridor to detect localized storms or flooding.
        """
        pass

class TrafficProvider(BaseProvider):
    @abstractmethod
    def get_traffic_flow(self, lat: float, lng: float, radius_km: float = 10.0) -> Dict[str, Any]:
        """
        Retrieves live traffic speeds, free flow speeds, and congestion ratios.
        """
        pass

    @abstractmethod
    def get_corridor_speed_factor(self, route_coords: List[List[float]]) -> float:
        """
        Calculates live traffic slowdown multiplier (1.0 = nominal, > 1.0 = delayed).
        """
        pass

class IncidentProvider(BaseProvider):
    @abstractmethod
    def get_incidents(self, min_lat: float, min_lng: float, max_lat: float, max_lng: float) -> List[Dict[str, Any]]:
        """
        Fetches live road incidents (accidents, road closures, hazards, construction).
        """
        pass

class RoutingProvider(BaseProvider):
    @abstractmethod
    def get_routes(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, alternatives: bool = True) -> List[Dict[str, Any]]:
        """
        Fetches genuine road geometry, distance, and baseline duration.
        """
        pass
