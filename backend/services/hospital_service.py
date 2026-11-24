import json
import math
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional
from config import settings
from models.hospital import Hospital
from models.emergency import EmergencyType
from providers.cache import data_cache

class HospitalService:
    def __init__(self):
        self.local_hospitals: List[Hospital] = []
        self._load_local_hospitals()

    def _load_local_hospitals(self):
        if settings.LOCAL_HOSPITALS_PATH.exists():
            try:
                with open(settings.LOCAL_HOSPITALS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.local_hospitals = [Hospital(**item) for item in data]
            except Exception as e:
                print(f"[HospitalService] Error loading local hospitals: {e}")

    @staticmethod
    def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def get_nearby_hospitals(
        self,
        user_lat: float,
        user_lng: float,
        emergency_type: EmergencyType = EmergencyType.CARDIAC,
        max_search_radius_km: float = 35.0
    ) -> List[Hospital]:
        """
        Discovers hospitals strictly relevant to the user's real geographic location.
        - Inside local registry coverage (<= 30km of demo base): returns local verified registry.
        - Outside local registry coverage: queries fast OpenStreetMap Photon / Overpass discovery near user coordinates.
        - If live OSM returns no hospitals: returns an empty list. NEVER returns distant Vizag hospitals!
        """
        print(f"\n[HOSPITAL SEARCH] Request for User Location: ({user_lat:.6f}, {user_lng:.6f}) | Emergency: {emergency_type.value}")
        
        # Check cache first for fast response
        cache_key = f"hospitals_{round(user_lat, 3)}_{round(user_lng, 3)}_{emergency_type.value}"
        cached = data_cache.get(cache_key)
        if cached:
            cached_list, prov, _ = cached
            print(f"  -> Returning {len(cached_list)} cached hospitals ({prov}).")
            return [Hospital(**h) if isinstance(h, dict) else h for h in cached_list]

        # Check distance to local registry base center
        dist_to_local_center = self.calculate_distance_km(
            user_lat, user_lng,
            settings.LOCAL_REGISTRY_CENTER_LAT,
            settings.LOCAL_REGISTRY_CENTER_LNG
        )
        print(f"  -> Distance to Local Prototype Registry Center ({settings.LOCAL_REGISTRY_CITY_NAME}): {dist_to_local_center:.2f} km")

        if dist_to_local_center <= settings.LOCAL_REGISTRY_MAX_RADIUS_KM:
            # User is genuinely inside the local prototype registry zone
            print(f"  -> User inside local registry zone (<= {settings.LOCAL_REGISTRY_MAX_RADIUS_KM}km). Evaluating local registry.")
            evaluated = self._evaluate_hospital_list(
                self.local_hospitals,
                user_lat, user_lng,
                emergency_type,
                source_label="Local Structured Registry",
                max_radius_km=max_search_radius_km
            )
            data_cache.set(cache_key, [h.model_dump() for h in evaluated], ttl_sec=600, source_name="Local Registry")
            return evaluated
        
        # User is in another geographic region -> Query fast OpenStreetMap Photon / Overpass discovery
        print("  -> User outside local registry zone. Initiating live OpenStreetMap discovery around user coordinates...")
        osm_hospitals = self._fetch_live_osm_hospitals(user_lat, user_lng, max_radius_km=max_search_radius_km)
        
        if osm_hospitals:
            print(f"  -> Discovered {len(osm_hospitals)} live medical center(s) via OpenStreetMap near ({user_lat:.4f}, {user_lng:.4f}).")
            evaluated = self._evaluate_hospital_list(
                osm_hospitals,
                user_lat, user_lng,
                emergency_type,
                source_label="OpenStreetMap Live Discovery",
                max_radius_km=max_search_radius_km
            )
            data_cache.set(cache_key, [h.model_dump() for h in evaluated], ttl_sec=600, source_name="OpenStreetMap Live")
            return evaluated
        
        # Live OSM discovery returned 0 hospitals
        print("  -> No live hospitals found near user location. Returning empty list (NO distant Vizag fallback).")
        return []

    def _fetch_live_osm_hospitals(self, lat: float, lng: float, max_radius_km: float = 30.0) -> List[Hospital]:
        """
        Multi-tiered live OpenStreetMap hospital discovery:
        Tier 1: Photon Komoot Fast OSM POI search (sub-second response, highly reliable)
        Tier 2: Overpass API with extended 7s timeout
        """
        # Tier 1: Photon OSM POI Search
        try:
            url = f"https://photon.komoot.io/api/?q=hospital&lat={lat}&lon={lng}&limit=12"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AERT/3.0 (PhotonOSM)"}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    features = data.get("features", [])
                    if features:
                        results = []
                        for idx, feat in enumerate(features):
                            coords = feat.get("geometry", {}).get("coordinates", [])
                            if len(coords) < 2:
                                continue
                            h_lng, h_lat = float(coords[0]), float(coords[1])
                            
                            dist = self.calculate_distance_km(lat, lng, h_lat, h_lng)
                            if dist > max_radius_km:
                                continue

                            props = feat.get("properties", {})
                            name = props.get("name")
                            if not name or name.lower() == "hospital":
                                street = props.get("street") or props.get("locality") or f"Hospital #{idx+1}"
                                name = f"Medical Center ({street})"
                                
                            addr_parts = [props.get(k) for k in ["street", "locality", "city", "state"] if props.get(k)]
                            addr = ", ".join(addr_parts) if addr_parts else "Location verified via OpenStreetMap"

                            results.append(Hospital(
                                hospital_id=f"OSM-{props.get('osm_id', idx)}",
                                name=name,
                                latitude=h_lat,
                                longitude=h_lng,
                                address=addr,
                                emergency_dept=None,
                                icu=None,
                                trauma_center=None,
                                cardiac_care=None,
                                stroke_care=None,
                                burn_unit=None,
                                twenty_four_seven=None,
                                source="OpenStreetMap Live Discovery"
                            ))
                        if results:
                            return results
        except Exception as e:
            print(f"[HospitalService] Photon OSM tier encountered error: {e}. Trying Overpass fallback...")

        # Tier 2: Overpass API Fallback
        query = f"""[out:json][timeout:6];
(
  node["amenity"="hospital"](around:{int(max_radius_km*1000)},{lat},{lng});
  way["amenity"="hospital"](around:{int(max_radius_km*1000)},{lat},{lng});
  node["healthcare"="hospital"](around:{int(max_radius_km*1000)},{lat},{lng});
);
out center 12;"""
        
        for mirror in settings.OVERPASS_MIRRORS:
            try:
                req = urllib.request.Request(
                    mirror,
                    data=query.encode('utf-8'),
                    headers={'User-Agent': 'AERT/3.0 (OverpassOSM)'}
                )
                with urllib.request.urlopen(req, timeout=6) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        elements = data.get("elements", [])
                        if elements:
                            results = []
                            for idx, el in enumerate(elements[:12]):
                                h_lat = el.get("lat") or (el.get("center", {}).get("lat"))
                                h_lng = el.get("lon") or (el.get("center", {}).get("lon"))
                                if h_lat is None or h_lng is None:
                                    continue
                                tags = el.get("tags", {})
                                name = tags.get("name") or tags.get("name:en") or f"Hospital / Medical Center {idx+1}"
                                addr = tags.get("addr:street") or tags.get("addr:city") or "OpenStreetMap Node"
                                is_24x7 = tags.get("opening_hours") == "24/7"
                                emergency_dept = True if tags.get("emergency") == "yes" else None
                                
                                results.append(Hospital(
                                    hospital_id=f"OSM-{el.get('id', idx)}",
                                    name=name,
                                    latitude=float(h_lat),
                                    longitude=float(h_lng),
                                    address=addr,
                                    emergency_dept=emergency_dept,
                                    icu=None,
                                    trauma_center=None,
                                    cardiac_care=None,
                                    stroke_care=None,
                                    burn_unit=None,
                                    twenty_four_seven=True if is_24x7 else None,
                                    source="OpenStreetMap Live Discovery"
                                ))
                            return results
            except Exception as e:
                print(f"[HospitalService] Mirror {mirror} failed: {e}")

        return []

    def _evaluate_hospital_list(
        self,
        hospitals: List[Hospital],
        user_lat: float,
        user_lng: float,
        emergency_type: EmergencyType,
        source_label: str,
        max_radius_km: float = 35.0
    ) -> List[Hospital]:
        results = []
        for h in hospitals:
            h_copy = h.model_copy()
            h_copy.source = source_label
            dist = self.calculate_distance_km(user_lat, user_lng, h_copy.latitude, h_copy.longitude)
            
            # Strict distance cutoff
            if dist > max_radius_km:
                continue
                
            h_copy.distance_km = round(dist, 2)
            estimated_eta_min = round((dist / 38.0) * 60, 1)
            h_copy.predicted_eta_min = estimated_eta_min
            
            score, reasons = self.evaluate_suitability(h_copy, emergency_type, dist, estimated_eta_min)
            h_copy.suitability_score = round(score, 2)
            h_copy.suitability_reasons = reasons
            
            print(f"  * Hospital: {h_copy.name} | Coords: ({h_copy.latitude:.4f}, {h_copy.longitude:.4f}) | Distance: {dist:.2f} km | Score: {h_copy.suitability_score}")
            results.append(h_copy)

        results.sort(key=lambda x: (x.suitability_score if x.suitability_score is not None else 999))
        return results

    def evaluate_suitability(
        self,
        hospital: Hospital,
        emergency_type: EmergencyType,
        distance_km: float,
        eta_min: float
    ) -> Tuple[float, List[str]]:
        # Lower score = better clinical suitability + faster arrival (strictly positive without clamping ties)
        score = 30.0 + eta_min * 2.0 + distance_km * 1.2
        reasons = []

        if hospital.emergency_dept is True:
            score -= 4.0
            reasons.append("Emergency Department recorded")
        elif hospital.emergency_dept is False:
            score += 40.0
            reasons.append("No Emergency Department recorded (+40 risk)")
        else:
            reasons.append("Emergency Department capability unverified")

        if hospital.twenty_four_seven is True:
            score -= 2.0

        if emergency_type == EmergencyType.CARDIAC:
            if hospital.cardiac_care is True:
                score -= 12.0
                reasons.append("Cardiac care capability recorded in registry (+12)")
            elif hospital.cardiac_care is False:
                score += 20.0
                reasons.append("No specialized cardiac care (-20)")

        elif emergency_type in [EmergencyType.TRAUMA, EmergencyType.BLEEDING]:
            if hospital.trauma_center is True:
                score -= 12.0
                reasons.append("Trauma center recorded in registry (+12)")

        elif emergency_type == EmergencyType.STROKE:
            if hospital.stroke_care is True:
                score -= 10.0
                reasons.append("Stroke care capability recorded in registry (+10)")

        elif emergency_type == EmergencyType.BURN:
            if hospital.burn_unit is True:
                score -= 15.0
                reasons.append("Burn unit recorded in registry (+15)")

        if hospital.icu is True:
            score -= 5.0
            reasons.append("Intensive Care Unit (ICU) confirmed (+5)")

        return max(1.0, score), reasons

hospital_service = HospitalService()
