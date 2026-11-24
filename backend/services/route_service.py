import urllib.request
import json
import math
from typing import List, Dict, Any, Optional
from config import settings

class RouteService:
    @staticmethod
    def _parse_osrm_route(r: Dict[str, Any], idx: int, label_override: Optional[str] = None) -> Dict[str, Any]:
        coords = [[pt[1], pt[0]] for pt in r["geometry"]["coordinates"]]
        return {
            "route_id": f"OSRM-R{idx + 1}",
            "name": label_override or (f"Road Route {idx + 1}" + (" (Primary)" if idx == 0 else " (Alternative)")),
            "distance_m": r["distance"],
            "distance_km": round(r["distance"] / 1000.0, 2),
            "duration_sec": r["duration"],
            "duration_min": round(r["duration"] / 60.0, 1),
            "path": coords,
            "source": "OSRM Live Road Engine"
        }

    @staticmethod
    def _query_osrm_url(url: str) -> Optional[List[Dict[str, Any]]]:
        req = urllib.request.Request(url, headers={'User-Agent': 'QuantumEmergencyRouter/2.2'})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("code") == "Ok" and data.get("routes"):
                    return data["routes"]
        return None

    @staticmethod
    def fetch_osrm_routes(lat1: float, lon1: float, lat2: float, lon2: float, request_alternatives: bool = True) -> List[Dict[str, Any]]:
        """
        Queries OSRM service for real road routes and geometries.
        If OSRM returns only 1 route when alternatives are requested, queries
        real road corridors via perpendicular mid-corridor waypoints and deduplicates.
        Never manufactures fake road geometries.
        """
        alt_param = "true" if request_alternatives else "false"
        url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson&alternatives={alt_param}"

        try:
            raw_routes = RouteService._query_osrm_url(url)
            if raw_routes:
                parsed_routes = [RouteService._parse_osrm_route(r, idx) for idx, r in enumerate(raw_routes)]

                # If OSRM returned only 1 route and alternatives were requested, probe 2 real waypoint detours
                if request_alternatives and len(parsed_routes) == 1:
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    mid_lat, mid_lon = lat1 + dlat * 0.5, lon1 + dlon * 0.5
                    waypoints = [
                        (mid_lat - dlon * 0.25, mid_lon + dlat * 0.25),
                        (mid_lat + dlon * 0.25, mid_lon - dlat * 0.25),
                    ]
                    seen_sigs = {(round(parsed_routes[0]["distance_m"], -1), round(parsed_routes[0]["duration_sec"], 0))}
                    for wp_lat, wp_lon in waypoints:
                        wp_url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{lon1},{lat1};{wp_lon},{wp_lat};{lon2},{lat2}?overview=full&geometries=geojson"
                        try:
                            wp_routes = RouteService._query_osrm_url(wp_url)
                            if wp_routes:
                                sig = (round(wp_routes[0]["distance"], -1), round(wp_routes[0]["duration"], 0))
                                if sig not in seen_sigs:
                                    seen_sigs.add(sig)
                                    idx = len(parsed_routes)
                                    parsed_routes.append(
                                        RouteService._parse_osrm_route(wp_routes[0], idx, f"Road Route {idx + 1} (Bypass Corridor)")
                                    )
                        except Exception:
                            pass

                return parsed_routes
        except Exception as e:
            print(f"[RouteService] OSRM live routing error/timeout: {e}")

        # Fallback to calculated geometric line if OSRM API is completely unreachable
        dist_km = RouteService.calculate_distance_km(lat1, lon1, lat2, lon2)
        duration_sec = max(30.0, (dist_km / 40.0) * 3600.0)
        return [{
            "route_id": "FALLBACK-DIRECT",
            "name": "Direct Emergency Path (OSRM Offline Fallback)",
            "distance_m": dist_km * 1000.0,
            "distance_km": round(dist_km, 2),
            "duration_sec": duration_sec,
            "duration_min": round(duration_sec / 60.0, 1),
            "path": [[lat1, lon1], [lat2, lon2]],
            "source": "Geometric Fallback (Offline)"
        }]

    @staticmethod
    def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

route_service = RouteService()
