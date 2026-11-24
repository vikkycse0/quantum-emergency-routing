import json
import math
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone
from config import settings
from models.ambulance import Ambulance, AmbulanceStatus
from models.emergency import EmergencyType

class FleetService:
    # Strict clinical capability mapping based on emergency profiles
    CAPABILITY_REQUIREMENTS: Dict[EmergencyType, List[str]] = {
        EmergencyType.CARDIAC: ["Cardiac", "ALS"],
        EmergencyType.STROKE: ["ALS"],
        EmergencyType.TRAUMA: ["Trauma", "ALS"],
        EmergencyType.BLEEDING: ["Trauma", "ALS"],
        EmergencyType.RESPIRATORY: ["Ventilator", "Oxygen", "ALS"],
        EmergencyType.BURN: ["Burn", "ALS"],
        EmergencyType.FRACTURE: ["BLS"],
        EmergencyType.GENERAL: ["BLS"]
    }

    # Standard regional base station offsets (within 1.2 - 2.5 km of incident sector)
    BASE_STATION_OFFSETS = [
        (+0.0102, -0.0084),  # AMB-01: North-West Station (~1.4 km)
        (+0.0148, +0.0121),  # AMB-02: North-East Station (~2.1 km)
        (-0.0114, -0.0138),  # AMB-03: South-West Station (~1.9 km)
        (-0.0082, +0.0164),  # AMB-04: South-East Station (~2.0 km)
        (+0.0051, +0.0215),  # AMB-05: East Arterial Station (~2.4 km)
    ]

    def __init__(self):
        self.fleet: Dict[str, Ambulance] = {}
        self._load_fleet()

    def _load_fleet(self):
        if settings.FLEET_DATA_PATH.exists():
            try:
                with open(settings.FLEET_DATA_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        amb = Ambulance(**item)
                        self.fleet[amb.ambulance_id] = amb
            except Exception as e:
                print(f"[FleetService] Error loading fleet: {e}")

    def deploy_fleet_to_region(self, center_lat: float, center_lng: float):
        """
        Deploys available emergency response units to local base stations
        around the active patient / incident geographic sector without moving
        units that are currently dispatched or en route.
        """
        amb_list = list(self.fleet.values())
        for idx, amb in enumerate(amb_list):
            if amb.status != AmbulanceStatus.AVAILABLE:
                continue
            offset_lat, offset_lng = self.BASE_STATION_OFFSETS[idx % len(self.BASE_STATION_OFFSETS)]
            amb.latitude = round(center_lat + offset_lat, 6)
            amb.longitude = round(center_lng + offset_lng, 6)
            amb.last_update = datetime.now(timezone.utc).isoformat()
            self.fleet[amb.ambulance_id] = amb

    def get_all_ambulances(self, user_lat: Optional[float] = None, user_lng: Optional[float] = None) -> List[Ambulance]:
        if user_lat is not None and user_lng is not None:
            self.deploy_fleet_to_region(user_lat, user_lng)
        return list(self.fleet.values())

    def get_available_ambulances(self, user_lat: Optional[float] = None, user_lng: Optional[float] = None) -> List[Ambulance]:
        if user_lat is not None and user_lng is not None:
            self.deploy_fleet_to_region(user_lat, user_lng)
        return [amb for amb in self.fleet.values() if amb.status == AmbulanceStatus.AVAILABLE]

    def get_ambulance_by_id(self, amb_id: str) -> Optional[Ambulance]:
        return self.fleet.get(amb_id)

    def filter_compatible_ambulances(
        self,
        emergency_type: EmergencyType,
        available_only: bool = True,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None
    ) -> Tuple[List[Ambulance], bool, List[str]]:
        """
        Filters the fleet based on required emergency equipment
        and ensures local base station coordinates near user location.
        """
        pool = self.get_available_ambulances(user_lat, user_lng) if available_only else self.get_all_ambulances(user_lat, user_lng)
        if not pool:
            pool = self.get_all_ambulances(user_lat, user_lng)

        required = self.CAPABILITY_REQUIREMENTS.get(emergency_type, ["BLS"])
        
        # Check ambulances having all or key required capabilities
        compatible = []
        for amb in pool:
            has_all = all(req in amb.capabilities for req in required)
            if has_all:
                compatible.append(amb)

        if compatible:
            return compatible, False, required
        else:
            return pool, True, required

    @staticmethod
    def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def update_status(
        self,
        amb_id: str,
        new_status: AmbulanceStatus,
        case_id: Optional[str] = None,
        dest_name: Optional[str] = None,
        eta_sec: Optional[float] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        speed_kmh: Optional[float] = None
    ) -> bool:
        amb = self.fleet.get(amb_id)
        if not amb:
            return False
        amb.status = new_status
        amb.current_case_id = case_id
        if dest_name is not None:
            amb.destination_name = dest_name
        if eta_sec is not None:
            amb.estimated_arrival_sec = eta_sec
        if lat is not None and lng is not None:
            amb.latitude = round(lat, 6)
            amb.longitude = round(lng, 6)
        if speed_kmh is not None:
            amb.current_speed_kmh = round(speed_kmh, 1)
        amb.last_update = datetime.now(timezone.utc).isoformat()
        return True

    def reset_fleet(self):
        self._load_fleet()

fleet_service = FleetService()
