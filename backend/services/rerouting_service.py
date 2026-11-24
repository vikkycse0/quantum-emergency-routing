import time
from typing import Dict, Any, List, Optional
from providers.incident_provider import incident_provider
from database.db import db_manager
from services.route_service import route_service
from config import settings

class ReroutingService:
    """
    Real-time dynamic corridor monitor with hysteresis and cooldown logic.
    Continuously checks active road corridors for newly reported accidents,
    floods, or severe congestion slowdowns and calculates optimal alternate corridors.
    """
    def __init__(self):
        self.active_disruptions: List[Dict[str, Any]] = []
        self.last_reroute_time: float = 0.0
        self.cooldown_sec: float = 8.0  # Prevents rapid route oscillation

    def trigger_disruption(
        self,
        disruption_type: str,
        severity: str,
        location_name: str,
        delay_multiplier: float = 2.0,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        is_simulated: bool = True
    ) -> Dict[str, Any]:
        """
        Injects a disruption (real or simulated) into the incident intelligence engine.
        """
        delay_sec = round((delay_multiplier - 1.0) * 240.0, 1)
        inc = incident_provider.register_incident(
            incident_type=disruption_type,
            lat=lat if lat is not None else settings.LOCAL_REGISTRY_CENTER_LAT,
            lng=lng if lng is not None else settings.LOCAL_REGISTRY_CENTER_LNG,
            severity=severity,
            delay_sec=delay_sec,
            description=f"{disruption_type} at {location_name}",
            is_simulated=is_simulated
        )
        self.active_disruptions.append(inc)
        return inc

    def clear_disruptions(self):
        self.active_disruptions.clear()
        incident_provider.clear_incidents()

    def check_and_reroute(
        self,
        current_lat: float,
        current_lng: float,
        dest_lat: float,
        dest_lng: float,
        original_eta_sec: float,
        emergency_type: str = "Cardiac Emergency",
        case_id: Optional[str] = None,
        solver_mode: str = "topsis"
    ) -> Dict[str, Any]:
        """
        Evaluates current corridor conditions against available alternate corridors.
        Enforces cooldown and hysteresis to avoid oscillating detours.
        """
        now = time.time()
        if (now - self.last_reroute_time) < self.cooldown_sec:
            return {
                "reroute_triggered": False,
                "reason": "Reroute evaluation in cooldown buffer"
            }

        # 1. Fetch fresh alternative road corridors
        candidate_routes = route_service.fetch_osrm_routes(
            current_lat, current_lng,
            dest_lat, dest_lng,
            request_alternatives=True
        )

        if not candidate_routes:
            return {
                "reroute_triggered": False,
                "reason": "No alternative road corridors found"
            }

        from optimization.optimizer import optimizer
        opt_res = optimizer.optimize_route_selection(
            candidate_routes=candidate_routes,
            emergency_type=emergency_type,
            severity="CRITICAL",
            solver_mode=solver_mode
        )

        selected_route = opt_res["selected_route"]
        selected_breakdown = opt_res["selected_ai_breakdown"]
        route_breakdowns = opt_res.get("candidate_breakdowns", [])
        selected_idx = opt_res.get("selected_route_index", 0)

        # Effective ETA includes active incident delays on the corridor
        selected_delay = float(selected_breakdown.get("incident_delay_sec", 0.0))
        primary_delay = float(route_breakdowns[0].get("incident_delay_sec", 0.0)) if route_breakdowns else 0.0
        new_eta_sec = float(selected_route["duration_sec"]) + selected_delay
        effective_orig_eta_sec = max(float(original_eta_sec), float(candidate_routes[0]["duration_sec"]) + primary_delay)
        
        original_incidents = (
            route_breakdowns[0].get("intersecting_incidents", [])
            if route_breakdowns
            else []
        )
        selected_incidents = selected_breakdown.get("intersecting_incidents", [])
        avoided_incidents = {
            incident.get("incident_id") for incident in original_incidents
        } - {
            incident.get("incident_id") for incident in selected_incidents
        }
        avoided_incidents.discard(None)

        # Hysteresis comparison: requires meaningful time improvement or active hazard avoidance
        time_saved_sec = effective_orig_eta_sec - new_eta_sec
        should_reroute = (
            time_saved_sec > 30.0
            or (selected_idx != 0 and bool(avoided_incidents))
        )

        if should_reroute and len(candidate_routes) > 1:
            self.last_reroute_time = now
            orig_min = round(effective_orig_eta_sec / 60.0, 1)
            new_min = round(new_eta_sec / 60.0, 1)
            saved_min = round(max(0.0, time_saved_sec / 60.0), 1)

            reason_msg = (
                f"Hazard Avoidance: {len(avoided_incidents)} incident(s) bypassed"
                if avoided_incidents
                else f"Traffic Optimization: {saved_min}m faster corridor discovered"
            )

            # Record in audit DB
            db_manager.record_reroute({
                "case_id": case_id or "CASE-LIVE",
                "trigger_reason": reason_msg,
                "original_eta_min": orig_min,
                "new_eta_min": new_min,
                "time_saved_min": saved_min,
                "disruption_type": next(
                    (incident.get("type", "Traffic Incident") for incident in original_incidents
                     if incident.get("incident_id") in avoided_incidents),
                    "Traffic Congestion"
                )
            })

            return {
                "reroute_triggered": True,
                "reason": reason_msg,
                "original_eta_min": orig_min,
                "new_projected_eta_min": new_min,
                "time_saved_min": saved_min,
                "avoided_incidents_count": len(avoided_incidents),
                "selected_route": selected_route,
                "optimization_result": opt_res
            }

        return {
            "reroute_triggered": False,
            "reason": "Current corridor remains optimal"
        }

rerouting_service = ReroutingService()
