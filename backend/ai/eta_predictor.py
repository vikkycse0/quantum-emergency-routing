from typing import Dict, Any, List
from datetime import datetime
from ai.traffic_predictor import TrafficPredictor

class ETAPredictor:
    def __init__(self, predictor: TrafficPredictor):
        self.predictor = predictor

    def predict_route_eta(
        self,
        distance_km: float,
        weather: str = 'clear',
        rainfall_mm: float = 0.0,
        has_event: int = 0,
        has_accident: int = 0
    ) -> Dict[str, Any]:
        now = datetime.now()
        hour = now.hour
        day_of_week = now.weekday()

        pred_sec, reliability, cong, metrics = self.predictor.predict_travel_time(
            hour=hour,
            day_of_week=day_of_week,
            distance_km=distance_km,
            weather=weather,
            rainfall_mm=rainfall_mm,
            has_event=has_event,
            has_accident=has_accident
        )

        factors = []
        if hour in [8, 9, 10, 17, 18, 19, 20]:
            factors.append(f"Peak Rush Hour Traffic ({hour:02d}:00)")
        if weather in ['rain', 'heavy_rain'] or rainfall_mm > 0:
            factors.append(f"Precipitation: {weather.replace('_', ' ').title()} ({rainfall_mm}mm)")
        if has_event:
            factors.append("Active Public/Festival Event in Corridor")
        if has_accident:
            factors.append("Reported Traffic Incident/Collision")
        if not factors:
            factors.append("Standard Flow & Clear Visibility")

        return {
            "predicted_eta_sec": round(pred_sec, 1),
            "predicted_eta_min": round(pred_sec / 60.0, 1),
            "reliability_indicator_pct": reliability,
            "predicted_congestion": cong,
            "influencing_factors": factors,
            "model_evaluation": metrics
        }
