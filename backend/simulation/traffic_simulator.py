import random
from enum import Enum
from typing import List, Dict, Any
from config import settings

class TrafficState(str, Enum):
    FREE = "FREE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    BLOCKED = "BLOCKED"

class TrafficSimulator:
    def __init__(self, city_graph=None):
        self.city_graph = city_graph
        self.graph = city_graph.get_live_graph() if city_graph else None
        self.active_events = []
        self.rng = random.Random(settings.SIMULATION_SEED)

    def inject_event(self, event_type: str, severity_factor: float = 3.0, road_name: str = "Main Corridor") -> Dict[str, Any]:
        """
        Injects a deterministic, labeled simulation event.
        """
        event = {
            "event_type": event_type,
            "severity_factor": severity_factor,
            "road_name": road_name,
            "traffic_state": TrafficState.SEVERE.value if severity_factor > 2.0 else TrafficState.HIGH.value
        }
        self.active_events.append(event)
        
        if self.graph:
            edges = list(self.graph.edges())
            if edges:
                sample_edges = self.rng.sample(edges, min(4, len(edges)))
                for u, v in sample_edges:
                    self.graph[u][v]['current_time'] = self.graph[u][v]['base_time'] * severity_factor

        return event

    def simulate_random_spikes(self, num_spikes: int = 5, severity: float = 3.0):
        if not self.graph:
            return []
        edges = list(self.graph.edges())
        spiked_edges = self.rng.sample(edges, min(num_spikes, len(edges)))
        for u, v in spiked_edges:
            self.graph[u][v]['current_time'] = self.graph[u][v]['base_time'] * severity
        return spiked_edges

    def clear_traffic(self):
        self.active_events = []
        if self.graph:
            for u, v in self.graph.edges():
                self.graph[u][v]['current_time'] = self.graph[u][v]['base_time']
