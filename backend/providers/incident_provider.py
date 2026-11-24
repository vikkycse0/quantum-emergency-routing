import time
import math
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from providers.base import IncidentProvider, DataProvenance
from providers.cache import data_cache

class LiveIncidentProvider(IncidentProvider):
    """
    Manages live and simulated road incidents (accidents, construction, closures, flash floods).
    Provides spatial queries to detect if candidate road corridors intersect known hazards.
    """
    def __init__(self):
        self._active_incidents: Dict[str, Dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "Live Incident Intelligence Engine"

    @property
    def is_live(self) -> bool:
        return True

    def register_incident(
        self,
        incident_type: str,
        lat: float,
        lng: float,
        severity: str = "HIGH",
        delay_sec: float = 180.0,
        description: str = "Traffic incident reported",
        is_simulated: bool = False
    ) -> Dict[str, Any]:
        """
        Registers an incident with spatial attributes.
        """
        incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        incident = {
            "incident_id": incident_id,
            "type": incident_type.upper(),
            "latitude": lat,
            "longitude": lng,
            "severity": severity.upper(),
            "estimated_delay_sec": delay_sec,
            "description": description,
            "is_simulated": is_simulated,
            "provenance": DataProvenance.SIMULATED.value if is_simulated else DataProvenance.LIVE.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"{self.name} ({'Simulated Demo' if is_simulated else 'Live Network'})"
        }
        self._active_incidents[incident_id] = incident
        return incident

    def clear_incidents(self):
        self._active_incidents.clear()

    def get_incidents(self, min_lat: float, min_lng: float, max_lat: float, max_lng: float) -> List[Dict[str, Any]]:
        results = []
        for inc in self._active_incidents.values():
            if min_lat <= inc["latitude"] <= max_lat and min_lng <= inc["longitude"] <= max_lng:
                results.append(inc)
        return results

    def get_all_active_incidents(self) -> List[Dict[str, Any]]:
        return list(self._active_incidents.values())

    def check_corridor_incident_impact(
        self,
        route_coords: List[List[float]],
        impact_radius_km: float = 0.35
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Calculates cumulative delay and returns all incidents intersecting the corridor path.
        """
        total_delay_sec = 0.0
        affected_incidents = []

        if not route_coords:
            return 0.0, []

        for inc in self._active_incidents.values():
            inc_lat = inc["latitude"]
            inc_lng = inc["longitude"]
            
            min_dist_to_route = self._distance_to_route_km(inc_lat, inc_lng, route_coords)

            if min_dist_to_route <= impact_radius_km:
                total_delay_sec += inc["estimated_delay_sec"]
                affected_incidents.append(inc)

        return total_delay_sec, affected_incidents

    @classmethod
    def _distance_to_route_km(cls, lat: float, lng: float, route_coords: List[List[float]]) -> float:
        def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
            radius_km = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlng = math.radians(lng2 - lng1)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
            return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        if not route_coords:
            return float('inf')
        if len(route_coords) == 1:
            return distance_km(lat, lng, route_coords[0][0], route_coords[0][1])

        min_distance = float('inf')
        cos_lat = math.cos(math.radians(lat))
        for start, end in zip(route_coords, route_coords[1:]):
            start_x = math.radians(start[1] - lng) * cos_lat
            start_y = math.radians(start[0] - lat)
            end_x = math.radians(end[1] - lng) * cos_lat
            end_y = math.radians(end[0] - lat)
            dx = end_x - start_x
            dy = end_y - start_y
            segment_length_sq = dx * dx + dy * dy
            fraction = 0.0 if segment_length_sq == 0 else max(
                0.0,
                min(1.0, -(start_x * dx + start_y * dy) / segment_length_sq)
            )
            nearest_lat = start[0] + (end[0] - start[0]) * fraction
            nearest_lng = start[1] + (end[1] - start[1]) * fraction
            min_distance = min(min_distance, distance_km(lat, lng, nearest_lat, nearest_lng))
        return min_distance

incident_provider = LiveIncidentProvider()
