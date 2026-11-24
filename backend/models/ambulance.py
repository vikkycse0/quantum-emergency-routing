from enum import Enum
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class AmbulanceStatus(str, Enum):
    AVAILABLE = "available"
    DISPATCHED = "dispatched"
    EN_ROUTE_TO_PATIENT = "en_route_to_patient"
    AT_PATIENT = "at_patient"
    EN_ROUTE_TO_HOSPITAL = "en_route_to_hospital"
    COMPLETED = "completed"
    OFFLINE = "offline"

class Ambulance(BaseModel):
    ambulance_id: str
    name: str
    latitude: float
    longitude: float
    status: AmbulanceStatus = AmbulanceStatus.AVAILABLE
    capabilities: List[str] = ["BLS", "Oxygen"]
    current_speed_kmh: float = 0.0
    current_case_id: Optional[str] = None
    destination_name: Optional[str] = None
    estimated_arrival_sec: Optional[float] = None
    last_update: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
