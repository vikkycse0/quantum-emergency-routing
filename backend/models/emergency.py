from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class EmergencyType(str, Enum):
    CARDIAC = "Cardiac Emergency"
    STROKE = "Stroke"
    TRAUMA = "Accident / Trauma"
    BLEEDING = "Severe Bleeding"
    RESPIRATORY = "Respiratory Emergency"
    BURN = "Burn"
    FRACTURE = "Fracture"
    GENERAL = "General Emergency"

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class EmergencyStatus(str, Enum):
    PENDING_DISPATCH = "pending_dispatch"
    DISPATCHED = "dispatched"
    EN_ROUTE_TO_PATIENT = "en_route_to_patient"
    PATIENT_PICKED_UP = "patient_picked_up"
    EN_ROUTE_TO_HOSPITAL = "en_route_to_hospital"
    RESOLVED = "resolved"

class EmergencyRequest(BaseModel):
    userLat: float
    userLng: float
    emergency_type: EmergencyType = EmergencyType.CARDIAC
    severity: Optional[Severity] = None
    patient_count: int = 1
    caller_phone: str = "+91-98765-43210"
    accuracy: Optional[float] = None
    source: Optional[str] = "browser-gps"

class EmergencyCase(BaseModel):
    case_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    source: Optional[str] = "browser-gps"
    emergency_type: EmergencyType
    severity: Severity
    patient_count: int = 1
    status: EmergencyStatus = EmergencyStatus.PENDING_DISPATCH
    caller_phone: str = "+91-98765-43210"
    selected_ambulance_id: Optional[str] = None
    selected_hospital_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
