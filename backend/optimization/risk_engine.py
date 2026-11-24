from typing import Dict, Any, Tuple
from models.emergency import EmergencyType, Severity

class EmergencyRiskEngine:
    """
    Transparent, configurable multi-variable emergency route risk engine.
    Formulates composite objective costs factoring in:
    - AI-predicted road travel times
    - Live Open-Meteo precipitation and visibility risks along the corridor
    - Active traffic congestion levels
    - Live road incidents, closures, and construction delays
    - Clinical category urgency weights
    """

    # Urgency weights tailored to clinical profiles
    EMERGENCY_WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
        EmergencyType.CARDIAC.value: {
            "eta_weight": 1.35,
            "congestion_weight": 1.20,
            "weather_weight": 0.85,
            "incident_weight": 1.30
        },
        EmergencyType.STROKE.value: {
            "eta_weight": 1.30,
            "congestion_weight": 1.15,
            "weather_weight": 0.85,
            "incident_weight": 1.25
        },
        EmergencyType.TRAUMA.value: {
            "eta_weight": 1.25,
            "congestion_weight": 1.10,
            "weather_weight": 0.90,
            "incident_weight": 1.40
        },
        EmergencyType.BLEEDING.value: {
            "eta_weight": 1.25,
            "congestion_weight": 1.10,
            "weather_weight": 0.90,
            "incident_weight": 1.40
        },
        EmergencyType.RESPIRATORY.value: {
            "eta_weight": 1.20,
            "congestion_weight": 1.05,
            "weather_weight": 1.25,
            "incident_weight": 1.15
        },
        EmergencyType.BURN.value: {
            "eta_weight": 1.15,
            "congestion_weight": 1.05,
            "weather_weight": 1.10,
            "incident_weight": 1.15
        },
        EmergencyType.GENERAL.value: {
            "eta_weight": 1.00,
            "congestion_weight": 1.00,
            "weather_weight": 1.00,
            "incident_weight": 1.00
        }
    }

    @classmethod
    def calculate_corridor_risk(
        cls,
        predicted_eta_sec: float,
        congestion_level: str,
        rainfall_mm: float,
        visibility_m: float,
        incident_delay_sec: float,
        emergency_type: str = "Cardiac Emergency",
        severity: str = "CRITICAL"
    ) -> Tuple[float, Dict[str, Any]]:
        
        weights = cls.EMERGENCY_WEIGHT_PROFILES.get(
            emergency_type,
            cls.EMERGENCY_WEIGHT_PROFILES[EmergencyType.GENERAL.value]
        )

        # 1. Congestion penalty term
        congestion_penalties = {
            "LOW": 0.0,
            "MODERATE": 40.0,
            "HIGH": 120.0,
            "SEVERE": 300.0
        }
        cong_penalty = congestion_penalties.get(congestion_level.upper(), 40.0) * weights["congestion_weight"]

        # 2. Weather & Environmental penalty
        weather_penalty = (rainfall_mm * 5.0) * weights["weather_weight"]
        if visibility_m < 3000.0:
            weather_penalty += 35.0

        # 3. Incident delay term
        inc_penalty = incident_delay_sec * weights["incident_weight"]

        # 4. Total weighted composite cost
        eta_term = predicted_eta_sec * weights["eta_weight"]
        total_cost = eta_term + cong_penalty + weather_penalty + inc_penalty

        breakdown = {
            "predicted_eta_sec": round(predicted_eta_sec, 1),
            "eta_weighted_term": round(eta_term, 1),
            "congestion_penalty_sec": round(cong_penalty, 1),
            "weather_penalty_sec": round(weather_penalty, 1),
            "incident_delay_sec": round(inc_penalty, 1),
            "total_composite_cost": round(total_cost, 1),
            "applied_weights": weights
        }

        return total_cost, breakdown

risk_engine = EmergencyRiskEngine()
