from typing import Optional, List
from pydantic import BaseModel

class HospitalCapability(BaseModel):
    emergency_dept: Optional[bool] = None
    icu: Optional[bool] = None
    trauma_center: Optional[bool] = None
    cardiac_care: Optional[bool] = None
    stroke_care: Optional[bool] = None
    burn_unit: Optional[bool] = None
    ambulance_support: Optional[bool] = None
    twenty_four_seven: Optional[bool] = None

class Hospital(BaseModel):
    hospital_id: str
    name: str
    latitude: float
    longitude: float
    address: str = "Unknown location"
    emergency_dept: Optional[bool] = None
    icu: Optional[bool] = None
    trauma_center: Optional[bool] = None
    cardiac_care: Optional[bool] = None
    stroke_care: Optional[bool] = None
    burn_unit: Optional[bool] = None
    ambulance_support: Optional[bool] = None
    twenty_four_seven: Optional[bool] = None
    rating: Optional[float] = None
    total_ratings: Optional[int] = None
    source: str = "Local Registry"
    last_updated: Optional[str] = None
    distance_km: Optional[float] = None
    predicted_eta_min: Optional[float] = None
    suitability_score: Optional[float] = None
    suitability_reasons: List[str] = []
