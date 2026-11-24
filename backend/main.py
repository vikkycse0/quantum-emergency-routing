import sys
from pathlib import Path

# Ensure backend directory is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models.emergency import EmergencyType, Severity
from models.ambulance import AmbulanceStatus
from services.hospital_service import hospital_service
from services.fleet_service import fleet_service
from services.route_service import route_service
from ai.model_manager import model_manager
from optimization.optimizer import optimizer
from intelligence.explainability import DecisionEngine

# Legacy simulation components for synthetic grid demo
from environment.graph_model import CityGraph
from simulation.traffic_simulator import TrafficSimulator
from simulation.signal_control import TrafficSignalController

def run_full_simulation():
    print("="*65)
    print("  AERT — AI EMERGENCY ROUTING & TRACKING SYSTEM SIMULATION  ")
    print("="*65)
    
    # 1. Fleet & Station Initialization
    print("\n[1] INITIALIZING FLEET ASSETS & MEDICAL CAPABILITIES...")
    fleet = fleet_service.get_all_ambulances()
    print(f"    -> Fleet Deployed: {len(fleet)} specialized units across base stations.")
    for amb in fleet[:3]:
        print(f"       * {amb.ambulance_id} ({amb.name}): Capabilities={amb.capabilities}")

    # 2. Emergency Event
    user_lat, user_lng = 17.7046, 83.2926
    emergency_type = EmergencyType.CARDIAC
    case_id = "DEMO-701"
    print(f"\n[2] EMERGENCY SOS RECEIVED: Case #{case_id}")
    print(f"    -> Location: ({user_lat}, {user_lng})")
    print(f"    -> Category: {emergency_type.value} [Severity: CRITICAL]")

    # 3. Medical Capability Filtering & Fleet Allocation
    print("\n[3] FILTERING MEDICALLY COMPATIBLE AMBULANCES...")
    compatible_ambs, is_fallback, req_caps = fleet_service.filter_compatible_ambulances(
        emergency_type,
        user_lat=user_lat,
        user_lng=user_lng
    )
    print(f"    -> Required Equipment: {req_caps}")
    print(f"    -> Qualified Units: {[a.ambulance_id for a in compatible_ambs]}")
    
    selected_amb, initial_eta, alloc_method = optimizer.optimize_fleet_dispatch(
        available_ambulances=compatible_ambs,
        emergency_lat=user_lat,
        emergency_lng=user_lng
    )
    print(f"    -> Allocation Method: {alloc_method}")
    print(f"    -> Selected Unit: {selected_amb.ambulance_id} ({selected_amb.name})")
    print(f"    -> Projected Response ETA: {initial_eta:.1f}s ({initial_eta/60.0:.1f} mins)")

    # 4. Hospital Suitability Evaluation
    print("\n[4] EVALUATING NEARBY HEALTHCARE CENTERS...")
    hospitals = hospital_service.get_nearby_hospitals(user_lat, user_lng, emergency_type)
    best_hosp = hospitals[0]
    print(f"    -> Top Evaluated: {best_hosp.name} (Score: {best_hosp.suitability_score})")
    print(f"    -> Clinical Reasons: {best_hosp.suitability_reasons}")

    # 5. Route Discovery & AI Travel Time Prediction
    print("\n[5] FETCHING ROAD NETWORK CORRIDORS & AI TRAFFIC PREDICTION...")
    candidate_routes = route_service.fetch_osrm_routes(
        user_lat, user_lng,
        best_hosp.latitude, best_hosp.longitude,
        request_alternatives=True
    )
    print(f"    -> Discovered {len(candidate_routes)} candidate road corridor(s).")
    
    # 6. Multi-factor route optimization
    print("\n[6] EXECUTING MULTI-CRITERIA ROUTE OPTIMIZATION...")
    opt_result = optimizer.optimize_route_selection(
        candidate_routes=candidate_routes,
        weather="clear",
        rainfall_mm=0.0,
        has_accident=0,
        severity="CRITICAL"
    )
    selected_route = opt_result["selected_route"]
    print(f"    -> Solver Method: {opt_result['optimization_method']}")
    print(f"    -> Selected Corridor: {selected_route['name']} ({selected_route['distance_km']} km)")
    print(f"    -> Objective Improvement: {opt_result['improvement_pct']}% vs baseline")

    # 7. Total Mission ETA Calculation
    amb_to_patient_eta_min = initial_eta / 60.0
    patient_to_hosp_eta_min = selected_route["duration_min"]
    total_mission_eta_min = amb_to_patient_eta_min + patient_to_hosp_eta_min
    
    print("\n[7] TOTAL MISSION TIMELINE METRICS:")
    print(f"    -> Segment 1 (Ambulance -> Patient): {amb_to_patient_eta_min:.1f} mins")
    print(f"    -> Segment 2 (Patient -> Hospital) : {patient_to_hosp_eta_min:.1f} mins")
    print(f"    -> Total Projected Mission ETA     : {total_mission_eta_min:.1f} mins")

    # 8. Simulated Green Corridor Priority
    city = CityGraph(size=8)
    traffic_sim = TrafficSimulator(city)
    signal_controller = TrafficSignalController(city)
    green_corridor_saved = signal_controller.activate_green_corridor([(0,0), (0,1), (0,2), (0,3)])
    print(f"    -> Simulated Signal Priority Time Saved: {green_corridor_saved:.1f}s")

    # 9. Explainable AI Decision Breakdown
    print("\n[8] GENERATING EXPLAINABLE AI REPORT:")
    report = DecisionEngine.generate_report(
        selected_amb=selected_amb,
        emergency={"case_id": case_id, "emergency_type": emergency_type.value, "severity": Severity.CRITICAL.value},
        selected_route=selected_route,
        selected_hospital=best_hosp.model_dump(),
        optimization_result=opt_result,
        ai_prediction=opt_result["selected_ai_breakdown"]["ai_telemetry"]
    )
    print(report)
    
    print("="*65)
    print("  SIMULATION EXECUTED SUCCESSFULLY WITH 0 ERRORS  ")
    print("="*65)

if __name__ == "__main__":
    run_full_simulation()
