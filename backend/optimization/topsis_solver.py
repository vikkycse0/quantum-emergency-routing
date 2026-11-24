import math
import time
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

class TOPSSolver:
    """
    Multi-Criteria Decision Making (MCDM) via TOPSIS:
    (Technique for Order of Preference by Similarity to Ideal Solution)
    
    Evaluates candidate emergency corridors and assignments across competing criteria:
    - C1 (Cost): Travel Time / ETA (minimize)
    - C2 (Benefit): Clinical Suitability & Capability Readiness (maximize)
    - C3 (Cost): Environmental & Weather Risk (minimize)
    - C4 (Cost): Traffic Congestion & Incident Delay (minimize)
    """

    @classmethod
    def solve_topsis(
        cls,
        candidate_breakdowns: List[Dict[str, Any]],
        criteria_weights: Optional[Dict[str, float]] = None
    ) -> Tuple[int, List[float], Dict[str, Any]]:
        if not candidate_breakdowns:
            raise ValueError("No candidate alternatives provided to TOPSIS solver")

        start_t = time.time()
        n_alternatives = len(candidate_breakdowns)
        if n_alternatives == 1:
            return 0, [1.0], {
                "algorithm": "MCDM TOPSIS (Multi-Criteria Ideal Solution)",
                "closeness_coefficients": [1.0],
                "best_alternative_score": 1.0,
                "execution_time_ms": round((time.time() - start_t) * 1000.0, 3)
            }

        weights = criteria_weights or {
            "eta": 0.40,
            "clinical_suitability": 0.25,
            "weather_risk": 0.15,
            "incident_congestion": 0.20
        }

        # 1. Build Decision Matrix X [n_alternatives x 4 criteria]
        # Col 0: Predicted ETA (sec) - COST
        # Col 1: Clinical / Corridor Readiness Score - BENEFIT
        # Col 2: Weather Penalty (sec) - COST
        # Col 3: Congestion + Incident Delay (sec) - COST
        matrix = np.zeros((n_alternatives, 4), dtype=np.float64)

        for i, b in enumerate(candidate_breakdowns):
            eta_sec = float(b.get("predicted_eta_sec", 300.0))
            weather_pen = float(b.get("weather_penalty_sec", 0.0))
            cong_pen = float(b.get("congestion_penalty_sec", 0.0)) + float(b.get("incident_delay_sec", 0.0))

            if "clinical_score" in b and b["clinical_score"] is not None:
                clinical_score = float(b["clinical_score"])
            else:
                # Independent reliability/safety readiness score when not explicitly supplied
                ai_rel = float((b.get("ai_telemetry") or {}).get("reliability_indicator_pct", 85.0))
                incident_cnt = float(b.get("incident_count", 0))
                clinical_score = max(10.0, ai_rel - incident_cnt * 15.0)

            matrix[i, 0] = max(1.0, eta_sec)
            matrix[i, 1] = max(1.0, clinical_score)
            matrix[i, 2] = max(0.0, weather_pen)
            matrix[i, 3] = max(0.0, cong_pen)

        # 2. Vector Normalization: r_ij = x_ij / sqrt(sum(x_kj^2))
        norm_matrix = np.zeros_like(matrix)
        for col in range(4):
            denom = np.sqrt(np.sum(matrix[:, col] ** 2))
            norm_matrix[:, col] = matrix[:, col] / denom if denom > 1e-12 else 0.0

        # 3. Weighted Normalized Matrix: v_ij = w_j * r_ij
        w_vec = np.array([
            weights["eta"],
            weights["clinical_suitability"],
            weights["weather_risk"],
            weights["incident_congestion"]
        ], dtype=np.float64)
        weighted_matrix = norm_matrix * w_vec

        # 4. Identify Ideal Solutions:
        # Col 0 (Cost): Min is PIS (+), Max is NIS (-)
        # Col 1 (Benefit): Max is PIS (+), Min is NIS (-)
        # Col 2 (Cost): Min is PIS (+), Max is NIS (-)
        # Col 3 (Cost): Min is PIS (+), Max is NIS (-)
        pis = np.array([
            np.min(weighted_matrix[:, 0]),
            np.max(weighted_matrix[:, 1]),
            np.min(weighted_matrix[:, 2]),
            np.min(weighted_matrix[:, 3])
        ])

        nis = np.array([
            np.max(weighted_matrix[:, 0]),
            np.min(weighted_matrix[:, 1]),
            np.max(weighted_matrix[:, 2]),
            np.max(weighted_matrix[:, 3])
        ])

        # 5. Calculate Euclidean Distances: S_i+ and S_i-
        d_pos = np.sqrt(np.sum((weighted_matrix - pis) ** 2, axis=1))
        d_neg = np.sqrt(np.sum((weighted_matrix - nis) ** 2, axis=1))

        # 6. Relative Closeness to Ideal Solution: C_i* = S_i- / (S_i+ + S_i-)
        denom = d_pos + d_neg
        closeness = np.where(denom > 1e-12, d_neg / denom, 0.5)

        # Tie-break on lowest ETA if closeness scores are effectively equal
        best_score = np.max(closeness)
        tied_indices = [i for i, c in enumerate(closeness) if abs(c - best_score) < 1e-9]
        best_idx = min(tied_indices, key=lambda idx: matrix[idx, 0])
        exec_ms = round((time.time() - start_t) * 1000.0, 3)

        metadata = {
            "algorithm": "MCDM TOPSIS (Multi-Criteria Ideal Solution)",
            "criteria_weights": weights,
            "positive_ideal_vector": [round(float(v), 4) for v in pis],
            "negative_ideal_vector": [round(float(v), 4) for v in nis],
            "closeness_coefficients": [round(float(c), 4) for c in closeness],
            "best_alternative_score": round(float(closeness[best_idx]), 4),
            "execution_time_ms": exec_ms
        }

        return best_idx, [float(c) for c in closeness], metadata

topsis_solver = TOPSSolver()
