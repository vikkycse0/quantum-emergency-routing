import time
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from config import settings
from optimization.qubo_builder import QUBOBuilder
from optimization.classical_solver import ClassicalQUBOSolver
from optimization.qaoa_solver import QAOASimulator
from optimization.topsis_solver import topsis_solver
from optimization.ilp_solver import ilp_solver
from optimization.risk_engine import risk_engine
from ai.model_manager import model_manager
from providers.weather_provider import weather_provider
from providers.incident_provider import incident_provider

class OptimizationEngine:
    @staticmethod
    def calculate_route_cost(
        route: Dict[str, Any],
        emergency_type: str = "Cardiac Emergency",
        severity: str = "CRITICAL",
        weather: Optional[str] = None,
        override_weather: Optional[str] = None,
        rainfall_mm: Optional[float] = None,
        override_rainfall_mm: Optional[float] = None,
        has_accident: int = 0,
        *args, **kwargs
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates composite route objective cost driven by AI ETA prediction,
        live Open-Meteo weather sampling, active incidents, and emergency urgency.
        """
        dist_km = float(route.get("distance_km", 3.0))
        path = route.get("path", [])

        # Effective weather parameters
        eff_rain = override_rainfall_mm if override_rainfall_mm is not None else rainfall_mm
        eff_weather = override_weather if override_weather is not None else weather

        # 1. Live Weather along corridor coordinates
        if eff_rain is not None:
            rain_val = float(eff_rain)
            visibility_m = 10000.0
            weather_condition = eff_weather or "Clear"
            weather_telemetry = {"source": "Manual Parameter", "rain_mm": rain_val}
        else:
            w_along = weather_provider.get_weather_along_route(path, sample_points=4)
            rain_val = w_along.get("max_rain_along_corridor_mm", 0.0)
            visibility_m = w_along.get("min_visibility_m", 10000.0)
            weather_condition = w_along.get("worst_condition", "Clear")
            weather_telemetry = w_along

        # 2. Live / Simulated Incident impact along corridor path
        incident_delay_sec, intersecting_incidents = incident_provider.check_corridor_incident_impact(path)
        if has_accident:
            incident_delay_sec += 240.0

        # 3. AI Traffic and Travel Time Prediction
        ai_pred = model_manager.eta_predictor.predict_route_eta(
            distance_km=dist_km,
            weather=weather_condition,
            rainfall_mm=rain_val,
            has_event=0,
            has_accident=1 if (len(intersecting_incidents) > 0 or has_accident) else 0
        )
        
        pred_eta_sec = ai_pred["predicted_eta_sec"]
        cong = ai_pred["predicted_congestion"]

        # 4. Multi-Factor Risk Calculation
        total_cost, breakdown = risk_engine.calculate_corridor_risk(
            predicted_eta_sec=pred_eta_sec,
            congestion_level=cong,
            rainfall_mm=rain_val,
            visibility_m=visibility_m,
            incident_delay_sec=incident_delay_sec,
            emergency_type=emergency_type,
            severity=severity
        )

        breakdown["ai_telemetry"] = ai_pred
        breakdown["weather_telemetry"] = weather_telemetry
        breakdown["incident_count"] = len(intersecting_incidents) + (1 if has_accident else 0)
        breakdown["intersecting_incidents"] = intersecting_incidents
        breakdown["clinical_score"] = max(
            10.0,
            float(ai_pred.get("reliability_indicator_pct", 85.0)) - breakdown["incident_count"] * 18.0
        )

        return total_cost, breakdown

    @staticmethod
    def _run_solver(
        solver_mode: str,
        candidate_costs: List[float],
        candidate_breakdowns: List[Dict[str, Any]]
    ) -> Tuple[int, str, Dict[str, Any]]:
        start_t = time.time()
        mode_lower = (solver_mode or "topsis").lower()
        if mode_lower in ["topsis", "mcdm"]:
            selected_idx, _, solver_meta = topsis_solver.solve_topsis(candidate_breakdowns)
            method_label = "MCDM TOPSIS (Multi-Criteria Ideal Solution)"
        elif mode_lower in ["ilp", "operations_research", "exact"]:
            selected_idx, _, solver_meta = ilp_solver.solve_ilp(candidate_costs)
            method_label = "Operations Research ILP (Exact Integer Programming)"
        elif mode_lower in ["qaoa", "quantum"] and settings.ENABLE_QAOA_SIMULATION:
            Q, offset = QUBOBuilder.build_route_selection_qubo(candidate_costs, penalty_multiplier=2000.0)
            sol_vec, _, solver_meta = QAOASimulator.solve_qaoa(Q, offset)
            selected_idx = int(np.argmax(sol_vec)) if np.sum(sol_vec) > 0 else 0
            method_label = "QAOA Quantum Simulator"
        else:
            Q, offset = QUBOBuilder.build_route_selection_qubo(candidate_costs, penalty_multiplier=2000.0)
            sol_vec, energy = ClassicalQUBOSolver.solve(Q, offset)
            selected_idx = int(np.argmax(sol_vec)) if np.sum(sol_vec) > 0 else 0
            solver_meta = {
                "algorithm": "Quantum-Inspired Classical QUBO Solver",
                "energy": round(float(energy), 2),
                "execution_time_ms": round((time.time() - start_t) * 1000.0, 3)
            }
            method_label = "Quantum-Inspired QUBO Optimization"
        return selected_idx, method_label, solver_meta

    @staticmethod
    def optimize_route_selection(
        candidate_routes: List[Dict[str, Any]],
        emergency_type: str = "Cardiac Emergency",
        severity: str = "CRITICAL",
        solver_mode: str = "topsis",  # Options: 'topsis', 'ilp', 'qubo', 'qaoa'
        weather: Optional[str] = None,
        override_weather: Optional[str] = None,
        rainfall_mm: Optional[float] = None,
        override_rainfall_mm: Optional[float] = None,
        has_accident: int = 0,
        include_comparison: bool = True,
        *args, **kwargs
    ) -> Dict[str, Any]:
        """
        Multi-Paradigm Optimization Dispatcher supporting:
        1. TOPSIS (Multi-Criteria Clinical Decision Making)
        2. Operations Research ILP (Exact Constrained Programming)
        3. QAOA / QUBO (Quantum Combinatorial Benchmark)
        """
        if not candidate_routes:
            raise ValueError("No candidate routes provided for optimization")

        # 1. Compute multi-factor costs and breakdowns
        candidate_costs = []
        candidate_breakdowns = []
        
        for r in candidate_routes:
            cost, breakdown = OptimizationEngine.calculate_route_cost(
                r,
                emergency_type=emergency_type,
                severity=severity,
                weather=weather,
                override_weather=override_weather,
                rainfall_mm=rainfall_mm,
                override_rainfall_mm=override_rainfall_mm,
                has_accident=has_accident
            )
            candidate_costs.append(cost)
            candidate_breakdowns.append(breakdown)

        baseline_cost = candidate_costs[0]

        # 2. Dispatch to requested Optimization Paradigm
        selected_idx, method_label, solver_meta = OptimizationEngine._run_solver(
            solver_mode, candidate_costs, candidate_breakdowns
        )

        # 3. Benchmark all available paradigms side-by-side for transparency
        solver_comparison = {}
        if include_comparison:
            benchmark_modes = ["topsis", "ilp", "qubo"]
            if settings.ENABLE_QAOA_SIMULATION and len(candidate_costs) <= 10:
                benchmark_modes.append("qaoa")
            for mode in benchmark_modes:
                if mode == solver_mode.lower():
                    b_idx, b_label, b_meta = selected_idx, method_label, solver_meta
                else:
                    b_idx, b_label, b_meta = OptimizationEngine._run_solver(
                        mode, candidate_costs, candidate_breakdowns
                    )
                solver_comparison[mode] = {
                    "label": b_label,
                    "selected_route_index": b_idx,
                    "selected_route_name": candidate_routes[b_idx].get("name", f"Route {b_idx + 1}"),
                    "objective_cost": round(candidate_costs[b_idx], 1),
                    "execution_time_ms": b_meta.get("execution_time_ms", 0.0)
                }

        selected_route = candidate_routes[selected_idx]
        selected_cost = candidate_costs[selected_idx]
        improvement_pct = max(0.0, round(((baseline_cost - selected_cost) / max(1.0, baseline_cost)) * 100.0, 1))
        n_routes = len(candidate_routes)

        return {
            "selected_route_index": selected_idx,
            "selected_route": selected_route,
            "optimization_method": method_label,
            "solver_mode": solver_mode,
            "solver_metadata": solver_meta,
            "solver_comparison": solver_comparison,
            "qubo_matrix_dimension": f"{n_routes}x{n_routes}",
            "baseline_cost": round(baseline_cost, 1),
            "optimized_cost": round(selected_cost, 1),
            "improvement_pct": improvement_pct,
            "candidate_costs": [round(c, 1) for c in candidate_costs],
            "candidate_breakdowns": candidate_breakdowns,
            "selected_ai_breakdown": candidate_breakdowns[selected_idx]
        }

    @staticmethod
    def optimize_fleet_dispatch(
        available_ambulances: List[Any],
        emergency_lat: float,
        emergency_lng: float,
        solver_mode: str = "topsis"
    ) -> Tuple[Any, float, str]:
        """
        Multi-paradigm allocation of available ambulances to emergency incident.
        """
        if not available_ambulances:
            raise ValueError("No available ambulances in candidate pool")

        etas = []
        breakdowns = []
        for amb in available_ambulances:
            R = 6371.0
            dlat = (emergency_lat - amb.latitude) * (np.pi / 180)
            dlon = (emergency_lng - amb.longitude) * (np.pi / 180)
            a = np.sin(dlat/2)**2 + np.cos(amb.latitude * np.pi/180) * np.cos(emergency_lat * np.pi/180) * np.sin(dlon/2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            dist_km = R * c
            
            speed_kmh = 45.0 if "ALS" in amb.capabilities else 38.0
            eta_sec = (dist_km / speed_kmh) * 3600.0
            etas.append(eta_sec)

            breakdowns.append({
                "predicted_eta_sec": eta_sec,
                "total_composite_cost": eta_sec,
                "clinical_score": 95.0 if "ALS" in amb.capabilities else 75.0,
                "weather_penalty_sec": 0.0,
                "congestion_penalty_sec": 0.0,
                "incident_delay_sec": 0.0
            })

        if solver_mode.lower() in ["topsis", "mcdm"]:
            selected_idx, _, _ = topsis_solver.solve_topsis(breakdowns)
            method_label = "MCDM TOPSIS Fleet Optimizer"
        elif solver_mode.lower() in ["ilp", "operations_research"]:
            selected_idx, _, _ = ilp_solver.solve_ilp(etas)
            method_label = "Operations Research ILP Dispatcher"
        else:
            Q, offset = QUBOBuilder.build_route_selection_qubo(etas, penalty_multiplier=3000.0)
            sol_vec, energy = ClassicalQUBOSolver.solve(Q, offset)
            selected_idx = int(np.argmax(sol_vec)) if np.sum(sol_vec) > 0 else 0
            method_label = "QUBO Fleet Allocation Optimizer"

        selected_amb = available_ambulances[selected_idx]
        selected_eta = etas[selected_idx]

        return selected_amb, selected_eta, method_label

optimizer = OptimizationEngine()
