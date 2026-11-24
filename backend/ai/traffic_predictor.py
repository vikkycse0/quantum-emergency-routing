import csv
import numpy as np
from typing import Dict, Any, Tuple
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from config import settings
from ai.feature_engineering import FeatureEngineer

class TrafficPredictor:
    def __init__(self):
        self.model = HistGradientBoostingRegressor(max_iter=100, random_state=settings.SIMULATION_SEED)
        self.is_trained = False
        self.metrics: Dict[str, float] = {}
        self._train_from_history()

    def _train_from_history(self):
        csv_path = settings.TRAFFIC_HISTORY_PATH
        if not csv_path.exists():
            print(f"[TrafficPredictor] Dataset not found at {csv_path}. Model uninitialized.")
            return

        X, y = [], []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    hour = int(row['hour'])
                    day = int(row['day_of_week'])
                    weather = row['weather']
                    rainfall_mm = float(row.get('rainfall_mm', 0.0))
                    event = int(row['event'])
                    accident = int(row['accident'])
                    dist_km = float(row['distance_km'])
                    travel_time_sec = float(row['travel_time_sec'])
                    
                    feat = FeatureEngineer.extract_features(hour, day, dist_km, weather, rainfall_mm, event, accident)
                    X.append(feat[0])
                    y.append(travel_time_sec)

            if len(X) > 0:
                X_arr = np.array(X)
                y_arr = np.array(y)
                
                # Split 80% train, 20% test
                X_train, X_test, y_train, y_test = train_test_split(
                    X_arr, y_arr, test_size=0.2, random_state=settings.SIMULATION_SEED
                )
                
                self.model.fit(X_train, y_train)
                y_pred = self.model.predict(X_test)
                
                mae = float(mean_absolute_error(y_test, y_pred))
                rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
                r2 = float(r2_score(y_test, y_pred))
                
                self.metrics = {
                    "mae_sec": round(mae, 2),
                    "rmse_sec": round(rmse, 2),
                    "r2_score": round(r2, 4),
                    "test_samples": len(y_test)
                }
                
                self.is_trained = True
                print(f"[TrafficPredictor] HistGradientBoosting trained on {len(X_train)} samples. Eval metrics: R2={r2:.4f}, MAE={mae:.2f}s, RMSE={rmse:.2f}s.")
        except Exception as e:
            print(f"[TrafficPredictor] Training error: {e}")

    def predict_travel_time(
        self,
        hour: int,
        day_of_week: int,
        distance_km: float,
        weather: str = 'clear',
        rainfall_mm: float = 0.0,
        has_event: int = 0,
        has_accident: int = 0
    ) -> Tuple[float, float, str, Dict[str, Any]]:
        """
        Returns (predicted_travel_time_sec, reliability_pct, congestion_level, model_metrics)
        """
        if not self.is_trained:
            base_speed = 35.0
            fallback_sec = (distance_km / base_speed) * 3600.0
            return fallback_sec, 70.0, "MODERATE (Fallback)", {"status": "untrained_fallback"}

        feat = FeatureEngineer.extract_features(hour, day_of_week, distance_km, weather, rainfall_mm, has_event, has_accident)
        pred_sec = float(self.model.predict(feat)[0])
        # Lower bound sanity speed limit (60 km/h in city)
        min_sec = (distance_km / 60.0) * 3600.0
        pred_sec = max(min_sec, pred_sec)
        
        # Congestion classification based on free-flow comparison (50 km/h baseline)
        free_flow_sec = (distance_km / 50.0) * 3600.0
        ratio = pred_sec / max(1.0, free_flow_sec)

        if ratio < 1.25:
            congestion = "LOW"
        elif ratio < 1.75:
            congestion = "MODERATE"
        elif ratio < 2.3:
            congestion = "HIGH"
        else:
            congestion = "SEVERE"

        # Model-estimated reliability heuristic derived from test R2 score
        reliability = round(min(98.0, max(75.0, (self.metrics.get('r2_score', 0.9) * 100.0) - (ratio * 1.5))), 1)

        return pred_sec, reliability, congestion, self.metrics
