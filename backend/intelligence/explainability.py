
from typing import Dict, Any, List, Optional

class DecisionEngine:
    @staticmethod
    def generate_report(
        selected_amb: Any,
        emergency: Dict[str, Any],
        selected_route: Optional[Dict[str, Any]] = None,
        selected_hospital: Optional[Dict[str, Any]] = None,
        optimization_result: Optional[Dict[str, Any]] = None,
        ai_prediction: Optional[Dict[str, Any]] = None,
        # Backward compatibility keyword/positional parameters
        *args,
        **kwargs
    ) -> str:
        """
        Generates a transparent, honest, data-driven explainability report
        using actual computed parameters. Handles both modern and legacy simulation calls cleanly.
        """
        case_id = emergency.get("case_id") or emergency.get("id", "N/A")
        e_type = emergency.get("emergency_type", "Not available")
        severity = emergency.get("severity", "Not available")
        e_type = getattr(e_type, "value", e_type)
        severity = getattr(severity, "value", severity)

        amb_id = getattr(selected_amb, "ambulance_id", None) or getattr(selected_amb, "id", str(selected_amb))
        amb_name = getattr(selected_amb, "name", "Not available")
        amb_caps = getattr(selected_amb, "capabilities", [])

        hosp_dict = selected_hospital or {}
        hosp_name = hosp_dict.get("name", "Not available")
        hosp_dist = hosp_dict.get("distance_km")
        hosp_reasons = hosp_dict.get("suitability_reasons") or []

        route_dict = selected_route if isinstance(selected_route, dict) else {}
        r_name = route_dict.get("name") or "Not available"
        r_dur_min = route_dict.get("duration_min")
        r_dist_km = route_dict.get("distance_km")

        opt_dict = optimization_result if isinstance(optimization_result, dict) else {}
        opt_method = opt_dict.get("optimization_method", "Not available")
        opt_improvement = opt_dict.get("improvement_pct")

        ai_dict = ai_prediction if isinstance(ai_prediction, dict) else {}
        pred_cong = ai_dict.get("predicted_congestion", "Not available")
        pred_rel = ai_dict.get("reliability_indicator_pct")
        pred_factors = ai_dict.get("influencing_factors") or []
        amb_caps_text = ", ".join(amb_caps) if amb_caps else "Not available"
        hosp_dist_text = f"{hosp_dist:.1f} km" if isinstance(hosp_dist, (int, float)) else "Not available"
        route_duration_text = f"{r_dur_min:.1f} mins" if isinstance(r_dur_min, (int, float)) else "Not available"
        route_distance_text = f"{r_dist_km:.1f} km" if isinstance(r_dist_km, (int, float)) else "Not available"
        reliability_text = f"{pred_rel}%" if isinstance(pred_rel, (int, float)) else "Not available"
        factors_text = ", ".join(pred_factors[:2]) if pred_factors else "Not available"
        improvement_text = (
            f"{opt_improvement}% vs primary route cost"
            if isinstance(opt_improvement, (int, float))
            else "Not available"
        )

        report = f"""====================================================
           DISPATCH DECISION EXPLANATION
====================================================
Incident Case ID   : #{case_id}
Emergency Category : {e_type} [Severity: {severity}]
Optimization Method: {opt_method}

1. WHY THIS AMBULANCE? ({amb_id} - {amb_name})
   - Reported capabilities: {amb_caps_text}.
   - Dispatch status: Selected unit assigned to this case.

2. WHY THIS HOSPITAL? ({hosp_name})
   - Approximate straight-line distance: {hosp_dist_text}.
   - Capability evaluation:
     * {' | '.join(hosp_reasons[:2]) if hosp_reasons else 'Not available'}.
   - Selected destination for {e_type}.

3. WHY THIS ROUTE? ({r_name})
   - Projected traversal: {route_duration_text} ({route_distance_text}).
   - AI traffic prediction: {pred_cong} congestion (Reliability Index: {reliability_text}).
   - Environmental factors: {factors_text}.
   - Estimated optimization improvement: {improvement_text}.
===================================================="""
        return report
