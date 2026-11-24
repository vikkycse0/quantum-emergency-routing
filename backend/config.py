import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# Load .env file
load_dotenv(BACKEND_DIR / ".env")

class Settings:
    PORT: int = int(os.getenv("PORT", 8001))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    SIMULATION_SEED: int = int(os.getenv("SIMULATION_SEED", 42))
    OSRM_BASE_URL: str = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
    OVERPASS_URL: str = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    OVERPASS_MIRRORS: list = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    
    # Local demo / prototype registry center (Visakhapatnam dataset)
    LOCAL_REGISTRY_CENTER_LAT: float = float(os.getenv("LOCAL_REGISTRY_CENTER_LAT", 17.7046))
    LOCAL_REGISTRY_CENTER_LNG: float = float(os.getenv("LOCAL_REGISTRY_CENTER_LNG", 83.2926))
    LOCAL_REGISTRY_CITY_NAME: str = os.getenv("LOCAL_REGISTRY_CITY_NAME", "Visakhapatnam (Demo Registry)")
    LOCAL_REGISTRY_MAX_RADIUS_KM: float = float(os.getenv("LOCAL_REGISTRY_MAX_RADIUS_KM", 30.0))
    
    # Backward compatibility alias
    DEFAULT_LAT: float = LOCAL_REGISTRY_CENTER_LAT
    DEFAULT_LNG: float = LOCAL_REGISTRY_CENTER_LNG
    DEFAULT_CITY_NAME: str = LOCAL_REGISTRY_CITY_NAME
    
    ENABLE_QAOA_SIMULATION: bool = os.getenv("ENABLE_QAOA_SIMULATION", "true").lower() == "true"
    
    # Path constants
    LOCAL_HOSPITALS_PATH: Path = DATA_DIR / "hospitals" / "local_hospitals.json"
    FLEET_DATA_PATH: Path = DATA_DIR / "fleet" / "ambulances.json"
    TRAFFIC_HISTORY_PATH: Path = DATA_DIR / "traffic" / "traffic_history.csv"

settings = Settings()
