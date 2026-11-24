from ai.traffic_predictor import TrafficPredictor
from ai.eta_predictor import ETAPredictor

class ModelManager:
    _instance = None

    def __init__(self):
        self.traffic_predictor = TrafficPredictor()
        self.eta_predictor = ETAPredictor(self.traffic_predictor)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ModelManager()
        return cls._instance

model_manager = ModelManager.get_instance()
