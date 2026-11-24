import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn

from config import settings, PROJECT_ROOT
from models.emergency import EmergencyType, Severity, EmergencyStatus, EmergencyRequest, EmergencyCase
from models.ambulance import Ambulance, AmbulanceStatus
from models.hospital import Hospital
from services.hospital_service import hospital_service
from services.fleet_service import fleet_service
from services.route_service import route_service
from services.rerouting_service import rerouting_service
from ai.model_manager import model_manager
from optimization.optimizer import optimizer
from intelligence.explainability import DecisionEngine
from simulation.traffic_simulator import TrafficSimulator
from providers.weather_provider import weather_provider
from providers.incident_provider import incident_provider
from database.db import db_manager

app = FastAPI(
    title="AERT — AI Emergency Routing & Tracking API",
    version="3.0.0",
    description="AERT Unified Emergency Navigation, Live Mobile Tracking Sync, Weather & Incident Risk Analysis, Hospital Capability Matching, and Multi-Paradigm Route Optimization"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static assets for unified web service (localhost & cloud)
css_dir = PROJECT_ROOT / "css"
js_dir = PROJECT_ROOT / "js"
if css_dir.exists():
    app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
if js_dir.exists():
    app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")

# Active state storage
active_emergencies: Dict[str, EmergencyCase] = {}
pending_sos_calls: List[EmergencyCase] = []
traffic_sim = TrafficSimulator()

def _empty_dispatch_state() -> Dict[str, Any]:
    return {
        "active": False,
        "case_id": None,
        "emergency_type": None,
        "severity": None,
        "phase": "idle",
        "assigned_ambulance": None,
        "assigned_ambulance_name": None,
        "ambulance_capabilities": [],
        "patient_lat": None,
        "patient_lng": None,
        "hospital_id": None,
        "hospital_name": None,
        "hospital_lat": None,
        "hospital_lng": None,
        "phase1_path": [],
        "phase2_path": [],
        "path": [],  # Active leg path for AERT mobile sync
        "phase1_duration_sec": 0.0,
        "phase2_duration_sec": 0.0,
        "eta": 0.0,
        "total_eta_min": 0.0,
        "hosp_name": "AERT Dispatch Base",
        "start_time": 0.0,
        "start_time_ms": 0.0,
        "time_scale": 30,
        "optimization_method": None,
        "improvement_pct": 0.0,
        "reroute_count": 0,
        "last_reroute_reason": None,
        "current_lat": None,
        "current_lng": None,
        "current_speed_kmh": 0.0
    }

active_dispatch_state: Dict[str, Any] = _empty_dispatch_state()

# ----------------- Request Models -----------------
class CoordinateValidationModel(BaseModel):
    @staticmethod
    def check_coords(lat: float, lng: float):
        if not (-90.0 <= lat <= 90.0):
            raise HTTPException(status_code=422, detail=f"Latitude must be between -90 and 90. Received: {lat}")
        if not (-180.0 <= lng <= 180.0):
            raise HTTPException(status_code=422, detail=f"Longitude must be between -180 and 180. Received: {lng}")

class RouteCalcRequest(BaseModel):
    originLat: float
    originLng: float
    destLat: float
    destLng: float
    requestAlternatives: bool = True

class RouteOptimizeRequest(BaseModel):
    candidateRoutes: List[Dict[str, Any]]
    emergencyType: str = "Cardiac Emergency"
    severity: str = "CRITICAL"
    solverMode: str = "topsis"
    weather: Optional[str] = None
    rainfallMm: Optional[float] = None

class RerouteCheckRequest(BaseModel):
    currentLat: float
    currentLng: float
    destLat: float
    destLng: float
    originalEtaSec: float
    emergencyType: Optional[str] = "Cardiac Emergency"
    solverMode: str = "topsis"
    caseId: Optional[str] = None

class AIPredictRequest(BaseModel):
    distanceKm: float
    weather: str = "clear"
    rainfallMm: float = 0.0
    hasEvent: int = 0
    hasAccident: int = 0

class SimulationEventRequest(BaseModel):
    eventType: str = "Traffic Accident"
    severityFactor: float = Field(2.5, gt=1.0, le=10.0)
    locationName: str = "Corridor Junction"
    lat: Optional[float] = None
    lng: Optional[float] = None

class DispatchActionRequest(BaseModel):
    caseId: str
    ambulanceId: str
    hospitalId: str
    routeId: str

class DispatchPhaseUpdateRequest(BaseModel):
    caseId: Optional[str] = None
    ambulanceId: Optional[str] = None
    phase: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    speedKmh: Optional[float] = None

class LegacyEmergencyRequest(BaseModel):
    caseId: Optional[str] = None
    userLat: float
    userLng: float
    hospitalId: Optional[str] = None
    hospitalName: Optional[str] = None
    hospitalLat: Optional[float] = None
    hospitalLng: Optional[float] = None
    emergencyType: Optional[str] = "Cardiac Emergency"
    solverMode: Optional[str] = "topsis"
    weather: Optional[str] = "clear"
    rainfallMm: Optional[float] = 0.0
    accuracy: Optional[float] = None
    source: Optional[str] = "browser-gps"

# ----------------- Frontend Routes (Unified Server) -----------------

@app.get("/")
def serve_dashboard():
    index_path = PROJECT_ROOT / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard index.html not found")
    return FileResponse(str(index_path))

@app.get("/phone.html")
def serve_mobile():
    phone_path = PROJECT_ROOT / "phone.html"
    if not phone_path.exists():
        raise HTTPException(status_code=404, detail="Mobile phone.html not found")
    return FileResponse(str(phone_path))

# ----------------- Endpoints -----------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "AERT — AI Emergency Routing & Live Tracking",
        "version": "3.0.0",
        "simulation_seed": settings.SIMULATION_SEED,
        "qaoa_enabled": settings.ENABLE_QAOA_SIMULATION,
        "weather_provider": weather_provider.name,
        "incident_provider": incident_provider.name,
        "active_emergencies_count": len(active_emergencies),
        "available_ambulances_count": len(fleet_service.get_available_ambulances()),
        "active_dispatch": active_dispatch_state["active"],
        "model_evaluation": model_manager.traffic_predictor.metrics
    }

@app.get("/api/weather/live")
def get_live_weather(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude")
):
    CoordinateValidationModel.check_coords(lat, lng)
    w_data = weather_provider.get_weather_at_point(lat, lng)
    return {
        "status": "success",
        "weather": w_data
    }

@app.get("/api/traffic/incidents")
def get_live_incidents():
    incidents = incident_provider.get_all_active_incidents()
    return {
        "status": "success",
        "count": len(incidents),
        "incidents": incidents
    }

@app.get("/api/audit/analytics")
def get_audit_analytics():
    return db_manager.get_analytics_summary()

@app.get("/api/audit/cases")
def get_audit_cases(limit: int = Query(15, ge=1, le=50)):
    return {
        "status": "success",
        "analytics": db_manager.get_analytics_summary(),
        "cases": db_manager.get_recent_cases(limit=limit)
    }

@app.get("/api/audit/report/{case_id}")
def get_case_audit_report(case_id: str):
    report = db_manager.generate_case_audit_report(case_id)
    if report:
        return {"status": "success", "report": report}
    raise HTTPException(status_code=404, detail="Audit record for case_id not found")

@app.post("/api/sos_trigger")
def trigger_sos(req: EmergencyRequest):
    CoordinateValidationModel.check_coords(req.userLat, req.userLng)
    case_id = str(uuid.uuid4())[:8]

    severity = req.severity
    if not severity:
        if req.emergency_type in [EmergencyType.CARDIAC, EmergencyType.STROKE, EmergencyType.TRAUMA, EmergencyType.BLEEDING]:
            severity = Severity.CRITICAL
        elif req.emergency_type in [EmergencyType.RESPIRATORY, EmergencyType.BURN]:
            severity = Severity.HIGH
        else:
            severity = Severity.MEDIUM

    emergency = EmergencyCase(
        case_id=case_id,
        latitude=req.userLat,
        longitude=req.userLng,
        accuracy=req.accuracy,
        source=req.source or "browser-gps",
        emergency_type=req.emergency_type,
        severity=severity,
        patient_count=req.patient_count,
        caller_phone=req.caller_phone
    )

    active_emergencies[case_id] = emergency
    pending_sos_calls.append(emergency)

    # Persist in SQLite audit database
    db_manager.record_emergency(emergency.model_dump())

    print(f"\n[SOS TRIGGERED] Case #{case_id} | Coords: ({req.userLat:.6f}, {req.userLng:.6f}) | Accuracy: {req.accuracy}m | Source: {req.source} | Type: {req.emergency_type.value}")

    return {
        "status": "SOS_REGISTERED",
        "case_id": case_id,
        "emergency": emergency
    }

@app.get("/api/poll_sos")
def poll_sos_queue():
    if pending_sos_calls:
        call = pending_sos_calls.pop(0)
        return {"status": "incoming_call", "data": call}
    return {"status": "no_calls"}

@app.get("/api/emergencies")
def list_emergencies():
    return list(active_emergencies.values())

@app.get("/api/emergencies/{case_id}")
def get_emergency(case_id: str):
    if case_id in active_emergencies:
        return active_emergencies[case_id]
    raise HTTPException(status_code=404, detail="Emergency case not found")

@app.get("/api/ambulances")
def list_ambulances(
    lat: Optional[float] = Query(None, description="Patient Latitude for sector positioning"),
    lng: Optional[float] = Query(None, description="Patient Longitude for sector positioning")
):
    if lat is not None and lng is not None:
        CoordinateValidationModel.check_coords(lat, lng)
    return fleet_service.get_all_ambulances(user_lat=lat, user_lng=lng)

@app.get("/api/hospitals/nearby")
def get_nearby_hospitals(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    emergency_type: EmergencyType = Query(EmergencyType.CARDIAC, description="Type of medical emergency")
):
    CoordinateValidationModel.check_coords(lat, lng)
    hospitals = hospital_service.get_nearby_hospitals(lat, lng, emergency_type)
    return {
        "status": "success" if hospitals else "no_hospitals_found",
        "count": len(hospitals),
        "emergency_type": emergency_type,
        "hospitals": hospitals
    }

@app.post("/api/route/calculate")
def calculate_routes(req: RouteCalcRequest):
    CoordinateValidationModel.check_coords(req.originLat, req.originLng)
    CoordinateValidationModel.check_coords(req.destLat, req.destLng)
    routes = route_service.fetch_osrm_routes(
        req.originLat, req.originLng,
        req.destLat, req.destLng,
        request_alternatives=req.requestAlternatives
    )
    return {
        "status": "success",
        "candidate_count": len(routes),
        "routes": routes
    }

@app.post("/api/route/optimize")
def optimize_route(req: RouteOptimizeRequest):
    if not req.candidateRoutes:
        raise HTTPException(status_code=400, detail="candidateRoutes array cannot be empty")
    
    result = optimizer.optimize_route_selection(
        candidate_routes=req.candidateRoutes,
        emergency_type=req.emergencyType,
        severity=req.severity,
        solver_mode=req.solverMode,
        override_weather=req.weather,
        override_rainfall_mm=req.rainfallMm
    )
    return {
        "status": "success",
        "optimization": result
    }

@app.post("/api/route/reroute")
def check_reroute(req: RerouteCheckRequest):
    CoordinateValidationModel.check_coords(req.currentLat, req.currentLng)
    CoordinateValidationModel.check_coords(req.destLat, req.destLng)
    
    reroute_res = rerouting_service.check_and_reroute(
        req.currentLat, req.currentLng,
        req.destLat, req.destLng,
        req.originalEtaSec,
        emergency_type=req.emergencyType or "Cardiac Emergency",
        case_id=req.caseId,
        solver_mode=req.solverMode
    )

    if reroute_res.get("reroute_triggered") and active_dispatch_state.get("active"):
        new_route = reroute_res["selected_route"]
        active_dispatch_state["phase2_path"] = new_route["path"]
        active_dispatch_state["path"] = new_route["path"]
        active_dispatch_state["phase2_duration_sec"] = new_route["duration_sec"]
        active_dispatch_state["reroute_count"] = active_dispatch_state.get("reroute_count", 0) + 1
        active_dispatch_state["last_reroute_reason"] = reroute_res["reason"]

    return {
        "status": "success",
        "result": reroute_res
    }

@app.post("/api/ai/predict")
def predict_ai(req: AIPredictRequest):
    pred = model_manager.eta_predictor.predict_route_eta(
        distance_km=req.distanceKm,
        weather=req.weather,
        rainfall_mm=req.rainfallMm,
        has_event=req.hasEvent,
        has_accident=req.hasAccident
    )
    return {
        "status": "success",
        "prediction": pred
    }

@app.post("/api/dispatch")
def execute_dispatch(req: DispatchActionRequest):
    amb = fleet_service.get_ambulance_by_id(req.ambulanceId)
    if not amb:
        raise HTTPException(status_code=404, detail="Ambulance ID not found")
    
    fleet_service.update_status(
        amb_id=req.ambulanceId,
        new_status=AmbulanceStatus.EN_ROUTE_TO_PATIENT,
        case_id=req.caseId,
        dest_name=f"Patient at Case #{req.caseId}"
    )
    
    if req.caseId in active_emergencies:
        active_emergencies[req.caseId].status = EmergencyStatus.DISPATCHED
        active_emergencies[req.caseId].selected_ambulance_id = req.ambulanceId
        active_emergencies[req.caseId].selected_hospital_id = req.hospitalId

    return {
        "status": "DISPATCH_COMMENCED",
        "case_id": req.caseId,
        "ambulance": fleet_service.get_ambulance_by_id(req.ambulanceId)
    }

@app.get("/api/active_dispatch")
def get_active_dispatch(case_id: Optional[str] = Query(None)):
    """AERT live dispatch bridge for mobile tracking UI."""
    if case_id and active_dispatch_state.get("case_id") and active_dispatch_state["case_id"] != case_id:
        return {"active": False, "case_id": case_id, "phase": "waiting_for_dispatch"}
    return active_dispatch_state

@app.post("/api/active_dispatch/phase")
def update_active_dispatch_phase(req: DispatchPhaseUpdateRequest):
    if req.lat is not None and req.lng is not None:
        CoordinateValidationModel.check_coords(req.lat, req.lng)

    amb_id = req.ambulanceId or active_dispatch_state.get("assigned_ambulance")
    case_id = req.caseId or active_dispatch_state.get("case_id")

    phase_map = {
        "en_route_to_patient": AmbulanceStatus.EN_ROUTE_TO_PATIENT,
        "on_scene": AmbulanceStatus.AT_PATIENT,
        "en_route_to_hospital": AmbulanceStatus.EN_ROUTE_TO_HOSPITAL,
        "arrived": AmbulanceStatus.AVAILABLE,
    }
    if amb_id and req.phase in phase_map:
        fleet_service.update_status(
            amb_id=amb_id,
            new_status=phase_map[req.phase],
            case_id=None if req.phase == "arrived" else case_id,
            lat=req.lat,
            lng=req.lng,
            speed_kmh=req.speedKmh
        )

    if case_id and case_id in active_emergencies:
        if req.phase == "on_scene":
            active_emergencies[case_id].status = EmergencyStatus.PATIENT_PICKED_UP
        elif req.phase == "en_route_to_hospital":
            active_emergencies[case_id].status = EmergencyStatus.EN_ROUTE_TO_HOSPITAL
        elif req.phase == "arrived":
            active_emergencies[case_id].status = EmergencyStatus.RESOLVED
        active_emergencies[case_id].updated_at = datetime.now(timezone.utc).isoformat()
        db_manager.update_emergency_status(case_id, active_emergencies[case_id].status.value)

    if active_dispatch_state.get("active"):
        active_dispatch_state["phase"] = req.phase
        if req.lat is not None:
            active_dispatch_state["current_lat"] = req.lat
        if req.lng is not None:
            active_dispatch_state["current_lng"] = req.lng
        if req.speedKmh is not None:
            active_dispatch_state["current_speed_kmh"] = req.speedKmh
        if req.phase == "en_route_to_hospital" and active_dispatch_state.get("phase2_path"):
            active_dispatch_state["path"] = active_dispatch_state["phase2_path"]
            active_dispatch_state["eta"] = round(active_dispatch_state["phase2_duration_sec"] / 60.0, 1)

    return {"status": "updated", "dispatch": active_dispatch_state}

@app.post("/api/simulation/start")
def start_simulation():
    fleet_service.reset_fleet()
    rerouting_service.clear_disruptions()
    traffic_sim.clear_traffic()
    pending_sos_calls.clear()
    active_dispatch_state.clear()
    active_dispatch_state.update(_empty_dispatch_state())
    return {
        "status": "SIMULATION_READY",
        "message": "Simulation fleet reset, dispatch state cleared, and disruptions cleared."
    }

@app.post("/api/simulation/event")
def trigger_sim_event(req: SimulationEventRequest):
    if (req.lat is None) != (req.lng is None):
        raise HTTPException(status_code=422, detail="lat and lng must be supplied together")
    if req.lat is not None and req.lng is not None:
        CoordinateValidationModel.check_coords(req.lat, req.lng)

    reroute_event = rerouting_service.trigger_disruption(
        disruption_type=req.eventType,
        severity=str(req.severityFactor),
        location_name=req.locationName,
        delay_multiplier=req.severityFactor,
        lat=req.lat,
        lng=req.lng,
        is_simulated=True
    )
    return {
        "status": "EVENT_INJECTED",
        "event": reroute_event
    }

# ----------------- Integrated Simulation & Dispatch Flow with Audit Logging -----------------
@app.post("/api/simulate_dispatch")
def simulate_dispatch_flow(req: LegacyEmergencyRequest):
    CoordinateValidationModel.check_coords(req.userLat, req.userLng)
    if (req.hospitalLat is None) != (req.hospitalLng is None):
        raise HTTPException(status_code=422, detail="hospitalLat and hospitalLng must be supplied together")
    if req.hospitalLat is not None and req.hospitalLng is not None:
        CoordinateValidationModel.check_coords(req.hospitalLat, req.hospitalLng)

    # 1. Match Emergency Category
    e_type = EmergencyType.CARDIAC
    for et in EmergencyType:
        if et.value.lower() in (req.emergencyType or "").lower():
            e_type = et
            break
    severity_by_type = {
        EmergencyType.CARDIAC: Severity.CRITICAL,
        EmergencyType.STROKE: Severity.CRITICAL,
        EmergencyType.TRAUMA: Severity.CRITICAL,
        EmergencyType.BLEEDING: Severity.CRITICAL,
        EmergencyType.RESPIRATORY: Severity.HIGH,
        EmergencyType.BURN: Severity.HIGH,
        EmergencyType.FRACTURE: Severity.MEDIUM,
        EmergencyType.GENERAL: Severity.MEDIUM
    }
    severity = severity_by_type[e_type]

    # 2. Case ID Continuity & Persistent Audit Registration
    case_id = req.caseId
    if not case_id or case_id not in active_emergencies:
        case_id = case_id or str(uuid.uuid4())[:8]
        active_emergencies[case_id] = EmergencyCase(
            case_id=case_id,
            latitude=req.userLat,
            longitude=req.userLng,
            accuracy=req.accuracy,
            source=req.source or "browser-gps",
            emergency_type=e_type,
            severity=severity,
            status=EmergencyStatus.DISPATCHED
        )
    else:
        active_emergencies[case_id].status = EmergencyStatus.DISPATCHED
        active_emergencies[case_id].latitude = req.userLat
        active_emergencies[case_id].longitude = req.userLng
        active_emergencies[case_id].emergency_type = e_type
        active_emergencies[case_id].severity = severity
        active_emergencies[case_id].updated_at = datetime.now(timezone.utc).isoformat()

    db_manager.record_emergency(active_emergencies[case_id].model_dump())

    solver_mode = (req.solverMode or "topsis").lower()

    # 3. Medical Capability Filtering & Local Sector Fleet Deployment
    compatible_ambs, is_fallback, req_caps = fleet_service.filter_compatible_ambulances(
        e_type,
        available_only=True,
        user_lat=req.userLat,
        user_lng=req.userLng
    )

    # 4. Fleet allocation among medically compatible ambulances
    selected_amb, initial_amb_eta_sec, alloc_method = optimizer.optimize_fleet_dispatch(
        available_ambulances=compatible_ambs,
        emergency_lat=req.userLat,
        emergency_lng=req.userLng,
        solver_mode=solver_mode
    )

    # Compute genuine Phase 1 Road Corridor (Ambulance -> Patient)
    phase1_routes = route_service.fetch_osrm_routes(
        selected_amb.latitude, selected_amb.longitude,
        req.userLat, req.userLng,
        request_alternatives=False
    )
    phase1_route = phase1_routes[0]
    amb_to_patient_sec = float(phase1_route.get("duration_sec", initial_amb_eta_sec))

    # Update ambulance state
    fleet_service.update_status(
        amb_id=selected_amb.ambulance_id,
        new_status=AmbulanceStatus.EN_ROUTE_TO_PATIENT,
        case_id=case_id,
        dest_name=f"Patient Case #{case_id}",
        eta_sec=amb_to_patient_sec
    )

    # 5. Healthcare Facility Evaluation
    hospitals = hospital_service.get_nearby_hospitals(req.userLat, req.userLng, emergency_type=e_type)
    best_hosp = hospitals[0] if hospitals else None
    if req.hospitalId:
        matched_hosp = next((h for h in hospitals if h.hospital_id == req.hospitalId), None)
        if matched_hosp is not None:
            best_hosp = matched_hosp
        elif req.hospitalLat is not None and req.hospitalLng is not None:
            best_hosp = Hospital(
                hospital_id=req.hospitalId,
                name=req.hospitalName or "Selected Healthcare Facility",
                latitude=req.hospitalLat,
                longitude=req.hospitalLng,
                source="Dashboard Selected Facility"
            )
        else:
            raise HTTPException(status_code=404, detail="Selected hospital is not in the nearby facility results")
    elif req.hospitalLat is not None and req.hospitalLng is not None:
        best_hosp = Hospital(
            hospital_id="CUSTOM-HOSP",
            name=req.hospitalName or "Selected Healthcare Facility",
            latitude=req.hospitalLat,
            longitude=req.hospitalLng,
            source="Dashboard Selected Facility"
        )

    hosp_dict = best_hosp.model_dump() if best_hosp else {
        "hospital_id": "REGIONAL-FALLBACK",
        "name": "Regional Medical Center",
        "latitude": req.userLat + 0.015,
        "longitude": req.userLng + 0.015,
        "distance_km": 2.1,
        "source": "Fallback Medical Center"
    }

    # 6. Fetch Genuine OSRM Routes to Hospital (Phase 2)
    dest_lat = float(hosp_dict.get("latitude", req.userLat + 0.015))
    dest_lng = float(hosp_dict.get("longitude", req.userLng + 0.015))
    
    candidate_routes = route_service.fetch_osrm_routes(
        req.userLat, req.userLng,
        dest_lat, dest_lng,
        request_alternatives=True
    )

    # 7. Multi-factor risk scoring and route optimization (respecting emergency severity & solverMode)
    opt_res = optimizer.optimize_route_selection(
        candidate_routes=candidate_routes,
        emergency_type=e_type.value,
        severity=severity.value,
        solver_mode=solver_mode,
        override_weather=req.weather if req.weather and req.weather != "clear" else None,
        override_rainfall_mm=req.rainfallMm if req.rainfallMm and req.rainfallMm > 0 else None
    )
    selected_route = opt_res["selected_route"]
    selected_ai = opt_res["selected_ai_breakdown"]["ai_telemetry"]
    selected_weather = opt_res["selected_ai_breakdown"].get("weather_telemetry", {})

    # 8. Journey Segment ETA Accounting
    amb_to_patient_eta_min = round(amb_to_patient_sec / 60.0, 1)
    patient_to_hosp_eta_min = round(selected_route["duration_sec"] / 60.0, 1)
    total_mission_eta_min = round(amb_to_patient_eta_min + patient_to_hosp_eta_min, 1)

    # 9. Generate Explainability Report
    emerg_case = active_emergencies[case_id]
    emerg_case.selected_ambulance_id = selected_amb.ambulance_id
    emerg_case.selected_hospital_id = hosp_dict.get("hospital_id")
    report = DecisionEngine.generate_report(
        selected_amb=selected_amb,
        emergency=emerg_case.model_dump(),
        selected_route=selected_route,
        selected_hospital=hosp_dict,
        optimization_result=opt_res,
        ai_prediction=selected_ai
    )

    # 10. Persist Dispatch & Optimization Run in SQLite Audit DB
    db_manager.record_dispatch({
        "case_id": case_id,
        "ambulance_id": selected_amb.ambulance_id,
        "ambulance_name": selected_amb.name,
        "hospital_id": hosp_dict.get("hospital_id", "HOSP-01"),
        "hospital_name": hosp_dict.get("name", "Medical Center"),
        "route_name": selected_route.get("name", "Optimized Corridor"),
        "ambulance_eta_sec": amb_to_patient_sec,
        "patient_hospital_eta_sec": selected_route["duration_sec"],
        "total_mission_eta_sec": (amb_to_patient_sec + selected_route["duration_sec"]),
        "optimization_method": opt_res["optimization_method"],
        "is_capability_fallback": is_fallback
    })

    db_manager.record_optimization_run({
        "case_id": case_id,
        "qubo_matrix_dim": opt_res.get("qubo_matrix_dimension", f"{len(candidate_routes)}x{len(candidate_routes)}"),
        "solver_method": opt_res["optimization_method"],
        "candidate_routes_count": len(candidate_routes),
        "baseline_cost": opt_res["baseline_cost"],
        "optimized_cost": opt_res["optimized_cost"],
        "improvement_pct": opt_res["improvement_pct"],
        "weather_snapshot": selected_weather,
        "traffic_snapshot": selected_ai,
        "explainability_report": report
    })

    # 11. Update AERT Live Sync State for Mobile Tracking App
    now_ms = round(time.time() * 1000.0, 1)
    active_dispatch_state.update({
        "active": True,
        "case_id": case_id,
        "emergency_type": e_type.value,
        "severity": severity.value,
        "phase": "en_route_to_patient",
        "assigned_ambulance": selected_amb.ambulance_id,
        "assigned_ambulance_name": selected_amb.name,
        "ambulance_capabilities": selected_amb.capabilities,
        "patient_lat": req.userLat,
        "patient_lng": req.userLng,
        "hospital_id": hosp_dict.get("hospital_id"),
        "hospital_name": hosp_dict.get("name", "Healthcare Center"),
        "hospital_lat": dest_lat,
        "hospital_lng": dest_lng,
        "phase1_path": phase1_route["path"],
        "phase2_path": selected_route["path"],
        "path": phase1_route["path"],
        "phase1_duration_sec": amb_to_patient_sec,
        "phase2_duration_sec": float(selected_route["duration_sec"]),
        "eta": amb_to_patient_eta_min,
        "total_eta_min": total_mission_eta_min,
        "hosp_name": hosp_dict.get("name", "Healthcare Center"),
        "start_time": now_ms,
        "start_time_ms": now_ms,
        "time_scale": 30,
        "optimization_method": opt_res["optimization_method"],
        "improvement_pct": opt_res["improvement_pct"],
        "reroute_count": 0,
        "last_reroute_reason": None,
        "current_lat": selected_amb.latitude,
        "current_lng": selected_amb.longitude,
        "current_speed_kmh": 42.0
    })

    return {
        "status": "success",
        "case_id": case_id,
        "severity": severity.value,
        "assigned_ambulance": selected_amb.ambulance_id,
        "assigned_ambulance_name": selected_amb.name,
        "ambulance_capabilities": selected_amb.capabilities,
        "ambulance_coords": [selected_amb.latitude, selected_amb.longitude],
        "is_capability_fallback": is_fallback,
        "required_capabilities": req_caps,
        "selected_hospital": hosp_dict,
        "phase1_route": phase1_route,
        "ambulance_to_patient_eta_sec": round(amb_to_patient_sec, 1),
        "ambulance_to_patient_eta_min": amb_to_patient_eta_min,
        "patient_to_hospital_eta_sec": round(selected_route["duration_sec"], 1),
        "patient_to_hospital_eta_min": patient_to_hosp_eta_min,
        "total_mission_eta_min": total_mission_eta_min,
        "optimization_method": opt_res["optimization_method"],
        "solver_mode": solver_mode,
        "solver_metadata": opt_res.get("solver_metadata", {}),
        "solver_comparison": opt_res.get("solver_comparison", {}),
        "selected_route_index": opt_res["selected_route_index"],
        "selected_route": selected_route,
        "candidate_routes": candidate_routes,
        "candidate_costs": opt_res.get("candidate_costs", []),
        "candidate_breakdowns": opt_res.get("candidate_breakdowns", []),
        "improvement_pct": opt_res["improvement_pct"],
        "selected_ai_breakdown": opt_res["selected_ai_breakdown"],
        "fleet_optimization_method": alloc_method,
        "ai_prediction": selected_ai,
        "weather_telemetry": selected_weather,
        "candidate_count": len(candidate_routes),
        "explainability_report": report
    }

if __name__ == "__main__":
    print(f"[STARTUP] AERT Server starting on http://{settings.HOST}:{settings.PORT}")
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
