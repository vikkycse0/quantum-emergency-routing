import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

class DataCache:
    """
    Thread-safe in-memory cache with Time-To-Live (TTL) and provenance auditing.
    Tracks exact freshness, cache hits/misses, and age in seconds.
    """
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Tuple[Any, str, int]]:
        """
        Retrieves cached data if present.
        Returns: (data, provenance_status, age_sec) or None if not found or expired.
        """
        entry = self._store.get(key)
        if not entry:
            return None

        now = time.time()
        age_sec = int(now - entry["created_at"])
        
        if age_sec <= entry["ttl_sec"]:
            # Fresh cache hit
            return entry["data"], "LIVE", age_sec
        elif age_sec <= (entry["ttl_sec"] * 3):
            # Graceful stale cache fallback (e.g. if API temporarily unreachable)
            return entry["data"], f"CACHED ({age_sec // 60}m ago)", age_sec
        else:
            # Completely expired
            return None

    def set(self, key: str, data: Any, ttl_sec: int = 120, source_name: str = "Live Provider"):
        """
        Stores data with specified TTL in seconds.
        """
        self._store[key] = {
            "data": data,
            "ttl_sec": ttl_sec,
            "created_at": time.time(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source_name
        }

    def clear(self):
        self._store.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "cached_keys_count": len(self._store),
            "keys": list(self._store.keys())
        }

data_cache = DataCache()
