import unittest
import numpy as np
import sys
import time
import random
from pathlib import Path
from types import SimpleNamespace

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.emergency import EmergencyType, Severity, EmergencyCase, EmergencyRequest
from models.hospital import Hospital
from models.ambulance import Ambulance, AmbulanceStatus
from services.hospital_service import hospital_service
from services.fleet_service import fleet_service
from services.route_service import route_service
from services.rerouting_service import rerouting_service
from ai.model_manager import model_manager
from ai.feature_engineering import FeatureEngineer
from optimization.qubo_builder import QUBOBuilder
from optimization.classical_solver import ClassicalQUBOSolver
from optimization.qaoa_solver import QAOASimulator
from optimization.optimizer import optimizer
from optimization.risk_engine import risk_engine
from providers.weather_provider import weather_provider
from providers.incident_provider import incident_provider
from providers.cache import data_cache
from database.db import db_manager
from main import run_full_simulation
from simulation.traffic_simulator import TrafficSimulator
from intelligence.explainability import DecisionEngine
import json
import socket
import threading
import urllib.request
import urllib.error
import uvicorn
from api_server import app
from optimization.topsis_solver import topsis_solver
from optimization.ilp_solver import ilp_solver

class TestQuantumEmergencyIntelligenceSystem(unittest.TestCase):

    def test_01_coordinate_and_emergency_model(self):
        case = EmergencyCase(
            case_id="CASE-AERT-01",
            latitude=28.6139,
            longitude=77.2090,
            accuracy=12.5,
            source="browser-gps",
            emergency_type=EmergencyType.CARDIAC,
            severity=Severity.CRITICAL
        )
        self.assertEqual(case.case_id, "CASE-AERT-01")
        self.assertEqual(case.latitude, 28.6139)
        self.assertEqual(case.longitude, 77.2090)
        self.assertEqual(case.source, "browser-gps")
        self.assertEqual(case.accuracy, 12.5)

    def test_01b_unknown_hospital_capabilities_stay_unknown(self):
        hospital = Hospital(
            hospital_id="OSM-UNKNOWN",
            name="Mapped Hospital",
            latitude=18.0,
            longitude=83.0
        )
        self.assertIsNone(hospital.emergency_dept)
        self.assertIsNone(hospital.twenty_four_seven)

    def test_01c_traffic_simulator_does_not_mutate_global_random_state(self):
        random.seed(1234)
        expected = random.random()
        random.seed(1234)
        TrafficSimulator()
        self.assertEqual(random.random(), expected)

    def test_01d_decision_report_uses_actual_optimization_method_and_metrics(self):
        ambulance = SimpleNamespace(
            ambulance_id="AMB-TEST",
            name="Test Cardiac Unit",
            capabilities=["ALS", "Cardiac"]
        )
        report = DecisionEngine.generate_report(
            selected_amb=ambulance,
            emergency={"case_id": "REPORT-TEST", "emergency_type": "Cardiac Emergency", "severity": "CRITICAL"},
            selected_route={"name": "Primary Road Corridor", "duration_min": 4.5, "distance_km": 2.1},
            selected_hospital={
                "name": "Mapped Hospital",
                "distance_km": 1.2,
                "suitability_reasons": ["Emergency department capability unverified"]
            },
            optimization_result={"optimization_method": "MCDM TOPSIS", "improvement_pct": 0.0},
            ai_prediction={"predicted_congestion": "LOW", "reliability_indicator_pct": 82.0, "influencing_factors": ["Clear weather"]}
        )

        self.assertIn("Optimization Method: MCDM TOPSIS", report)
        self.assertIn("0.0% vs primary route cost", report)
        self.assertIn("Emergency department capability unverified", report)
        self.assertNotIn("QUBO", report)
        self.assertNotIn("Quantum", report)

    def test_01e_decision_report_does_not_invent_missing_metrics(self):
        report = DecisionEngine.generate_report(
            selected_amb=SimpleNamespace(ambulance_id="AMB-TEST", name="Test Unit", capabilities=[]),
            emergency={"case_id": "REPORT-UNKNOWN"},
        )

        self.assertIn("Optimization Method: Not available", report)
        self.assertIn("Reliability Index: Not available", report)
        self.assertIn("Estimated optimization improvement: Not available", report)
        self.assertNotIn("91.0%", report)
        self.assertNotIn("12.0%", report)

    def test_02_weather_provider_and_cache_freshness(self):
        # 1. Test Open-Meteo live point retrieval
        w_point = weather_provider.get_weather_at_point(17.7046, 83.2926)
        self.assertIn("temperature_c", w_point)
        self.assertIn("rain_mm", w_point)
        self.assertIn("provenance", w_point)
        
        # 2. Test corridor sampling along waypoints
        sample_path = [[17.70, 83.29], [17.71, 83.30], [17.72, 83.31]]
        w_route = weather_provider.get_weather_along_route(sample_path, sample_points=3)
        self.assertIn("composite_weather_risk_factor", w_route)
        self.assertGreaterEqual(w_route["composite_weather_risk_factor"], 1.0)

        # 3. Test Cache TTL
        data_cache.set("test_key", {"val": 123}, ttl_sec=2)
        cached = data_cache.get("test_key")
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0]["val"], 123)

    def test_03_incident_provider_and_corridor_intersections(self):
        incident_provider.clear_incidents()
        
        # Register a hazard
        inc = incident_provider.register_incident(
            incident_type="ACCIDENT",
            lat=17.715,
            lng=83.305,
            severity="HIGH",
            delay_sec=300.0,
            description="Multi-car collision on main bypass",
            is_simulated=True
        )
        self.assertEqual(inc["type"], "ACCIDENT")
        self.assertEqual(inc["severity"], "HIGH")

        # Test corridor intersection check
        path_intersecting = [[17.714, 83.304], [17.716, 83.306]]
        delay_sec, affected = incident_provider.check_corridor_incident_impact(path_intersecting, impact_radius_km=0.5)
        self.assertGreater(delay_sec, 0.0)
        self.assertEqual(len(affected), 1)

        incident_provider.clear_incidents()

    def test_03b_incident_detection_checks_route_segments_between_waypoints(self):
        incident_provider.clear_incidents()
        incident_provider.register_incident(
            incident_type="ACCIDENT",
            lat=17.715,
            lng=83.305,
            severity="HIGH",
            delay_sec=180.0,
            is_simulated=True
        )
        # The incident is on the segment, but farther than the impact radius from either endpoint.
        delay_sec, affected = incident_provider.check_corridor_incident_impact(
            [[17.715, 83.300], [17.715, 83.310]],
            impact_radius_km=0.35
        )
        self.assertEqual(delay_sec, 180.0)
        self.assertEqual(len(affected), 1)
        incident_provider.clear_incidents()

    def test_04_emergency_risk_engine_multi_factor_weights(self):
        cost_cardiac, b_cardiac = risk_engine.calculate_corridor_risk(
            predicted_eta_sec=300.0,
            congestion_level="HIGH",
            rainfall_mm=10.0,
            visibility_m=5000.0,
            incident_delay_sec=120.0,
            emergency_type=EmergencyType.CARDIAC.value,
            severity="CRITICAL"
        )
        self.assertGreater(cost_cardiac, 300.0)
        self.assertIn("applied_weights", b_cardiac)
        self.assertEqual(b_cardiac["applied_weights"]["eta_weight"], 1.35)

    def test_05_ambulance_medical_capability_matching_and_sector_deployment(self):
        # 1. Cardiac Emergency requires ALS + Cardiac
        cardiac_ambs, is_fb, req = fleet_service.filter_compatible_ambulances(
            EmergencyType.CARDIAC,
            available_only=True,
            user_lat=18.3018,
            user_lng=83.9003
        )
        self.assertTrue(len(cardiac_ambs) > 0)
        self.assertFalse(is_fb)
        self.assertIn("Cardiac", req)
        self.assertTrue(all({"Cardiac", "ALS"}.issubset(set(amb.capabilities)) for amb in cardiac_ambs))
        self.assertNotIn("AMB-02", [amb.ambulance_id for amb in cardiac_ambs])
        
        # Verify ambulances were stationed around the user's geographic sector
        dist_amb = fleet_service.calculate_distance_km(18.3018, 83.9003, cardiac_ambs[0].latitude, cardiac_ambs[0].longitude)
        self.assertLess(dist_amb, 5.0)

    def test_06_hospital_proximity_and_zero_distant_fallback(self):
        # Test distant location
        delhi_lat, delhi_lng = 28.6139, 77.2090
        dist_to_vizag = hospital_service.calculate_distance_km(delhi_lat, delhi_lng, 17.7046, 83.2926)
        self.assertGreater(dist_to_vizag, 1000.0)

    def test_07_qubo_and_qaoa_solvers(self):
        candidate_costs = [350.0, 200.0, 400.0]
        Q, offset = QUBOBuilder.build_route_selection_qubo(candidate_costs, penalty_multiplier=1500.0)
        
        sol_vec, energy, metadata = QAOASimulator.solve_qaoa(Q, offset)
        self.assertEqual(np.sum(sol_vec), 1.0)
        self.assertEqual(np.argmax(sol_vec), 1) # Index 1 (cost 200) is optimal
        self.assertIn("optimal_gamma", metadata)
        self.assertIn("optimal_beta", metadata)

    def test_08_persistent_sqlite_audit_database(self):
        # Record test emergency and dispatch
        test_case_id = f"TEST-CASE-{int(time.time())}"
        db_manager.record_emergency({
            "case_id": test_case_id,
            "latitude": 17.7046,
            "longitude": 83.2926,
            "accuracy": 15.0,
            "source": "browser-gps",
            "emergency_type": "Cardiac Emergency",
            "severity": "CRITICAL"
        })

        db_manager.record_dispatch({
            "case_id": test_case_id,
            "ambulance_id": "AMB-01",
            "ambulance_name": "Rapid Response Alpha",
            "hospital_id": "HOSP-01",
            "hospital_name": "King George Hospital",
            "route_name": "Primary Road Corridor",
            "ambulance_eta_sec": 95.0,
            "patient_hospital_eta_sec": 240.0,
            "total_mission_eta_sec": 335.0,
            "optimization_method": "QAOA Quantum Simulator",
            "is_capability_fallback": False
        })

        # Retrieve audit report
        audit_rep = db_manager.generate_case_audit_report(test_case_id)
        self.assertIsNotNone(audit_rep)
        self.assertEqual(audit_rep["emergency"]["case_id"], test_case_id)
        self.assertEqual(audit_rep["dispatch"]["ambulance_id"], "AMB-01")

    def test_09_dynamic_rerouting_with_hysteresis(self):
        rerouting_service.clear_disruptions()
        rerouting_service.trigger_disruption(
            disruption_type="Severe Crash",
            severity="Severe",
            location_name="Junction 4",
            delay_multiplier=2.5,
            is_simulated=True
        )
        res = rerouting_service.check_and_reroute(
            current_lat=17.7046, current_lng=83.2926,
            dest_lat=17.7215, dest_lng=83.3150,
            original_eta_sec=500.0,
            case_id="CASE-TEST-REROUTE"
        )
        self.assertIn("reroute_triggered", res)
        rerouting_service.clear_disruptions()

    def test_10_full_simulation_run(self):
        try:
            run_full_simulation()
            success = True
        except Exception as e:
            success = False
            print(f"Simulation failed: {e}")
        self.assertTrue(success)

    def test_11_topsis_benefit_column_and_hospital_score_differentiation(self):
        # Verify TOPSIS prefers higher clinical_score when costs are equal
        breakdowns = [
            {"predicted_eta_sec": 300.0, "weather_penalty_sec": 10.0, "congestion_penalty_sec": 20.0, "incident_delay_sec": 0.0, "clinical_score": 40.0},
            {"predicted_eta_sec": 300.0, "weather_penalty_sec": 10.0, "congestion_penalty_sec": 20.0, "incident_delay_sec": 0.0, "clinical_score": 95.0},
        ]
        best_idx, scores, _ = topsis_solver.solve_topsis(breakdowns)
        self.assertEqual(best_idx, 1)
        self.assertGreater(scores[1], scores[0])

        # Verify hospitals at different distances do not clamp to identical score 1.0
        hospitals = hospital_service.get_nearby_hospitals(17.7046, 83.2926, EmergencyType.CARDIAC)
        capable_scores = [h.suitability_score for h in hospitals if h.cardiac_care]
        self.assertGreater(len(set(capable_scores)), 1)

    def test_12_unified_api_and_live_qaers_sync(self):
        # Spin up real Uvicorn server on an ephemeral local port
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        base = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(40):
            try:
                with opener.open(f"{base}/api/health", timeout=1) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

        def req(path, method="GET", payload=None):
            data = json.dumps(payload).encode("utf-8") if payload is not None else (b"" if method == "POST" else None)
            headers = {"Content-Type": "application/json"} if payload is not None else {"Content-Length": "0"}
            r = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
            with opener.open(r, timeout=5) as resp:
                body = resp.read().decode("utf-8")
                ctype = resp.headers.get("Content-Type", "")
                return resp.status, (json.loads(body) if "application/json" in ctype else body)

        try:
            st, _ = req("/api/simulation/start", method="POST")
            self.assertEqual(st, 200)

            # Unified web & static routes
            st_dash, html_dash = req("/")
            self.assertEqual(st_dash, 200)
            self.assertIn("AERT Command Center", html_dash)

            st_phone, html_phone = req("/phone.html")
            self.assertEqual(st_phone, 200)
            self.assertIn("AERT Patient SOS", html_phone)

            st_cfg, js_cfg = req("/js/config.js")
            self.assertEqual(st_cfg, 200)
            self.assertIn("resolveBackendApiBase", js_cfg)

            # SOS -> Poll -> Dispatch -> Active Dispatch Sync -> Phase Update -> Audit
            st_sos, sos_data = req("/api/sos_trigger", method="POST", payload={
                "userLat": 17.7046,
                "userLng": 83.2926,
                "emergency_type": "Fracture",
                "source": "phone-gps"
            })
            self.assertEqual(st_sos, 200)
            case_id = sos_data["case_id"]

            _, poll_data = req("/api/poll_sos")
            self.assertEqual(poll_data["status"], "incoming_call")

            _, disp_data = req("/api/simulate_dispatch", method="POST", payload={
                "caseId": case_id,
                "userLat": 17.7046,
                "userLng": 83.2926,
                "emergencyType": "Fracture",
                "solverMode": "qaoa"
            })
            self.assertEqual(disp_data["severity"], "MEDIUM")
            self.assertIn("solver_comparison", disp_data)
            self.assertIn("phase1_route", disp_data)

            _, active_data = req(f"/api/active_dispatch?case_id={case_id}")
            self.assertTrue(active_data["active"])
            self.assertEqual(active_data["case_id"], case_id)

            _, phase_data = req("/api/active_dispatch/phase", method="POST", payload={
                "caseId": case_id,
                "ambulanceId": disp_data["assigned_ambulance"],
                "phase": "arrived",
                "lat": 17.7089,
                "lng": 83.3056,
                "speedKmh": 0.0
            })
            self.assertEqual(phase_data["dispatch"]["phase"], "arrived")

            _, audit_data = req("/api/audit/cases?limit=5")
            self.assertTrue(any(c["case_id"] == case_id for c in audit_data["cases"]))

            req("/api/simulation/start", method="POST")
        finally:
            server.should_exit = True
            thread.join(timeout=3)

if __name__ == "__main__":
    unittest.main()
