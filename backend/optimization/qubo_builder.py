import numpy as np
from typing import List, Dict, Any, Tuple

class QUBOBuilder:
    """
    Formulates a Quadratic Unconstrained Binary Optimization (QUBO) problem
    for selecting the globally optimal decision vector x in {0, 1}^N.
    
    Objective Function:
        minimize E(x) = x^T Q x + c^T x + Penalty * (sum(x_i) - 1)^2
    
    Constraint:
        Exactly one candidate item must be selected: sum(x_i) = 1
        Expanded as penalty: P * (sum(x_i) - 1)^2 = P * (sum(x_i^2) + 2*sum_{i<j}(x_i x_j) - 2*sum(x_i) + 1)
        Since x_i in {0,1}, x_i^2 = x_i:
        Penalty = P * (sum(x_i) - 2*sum(x_i) + 2*sum_{i<j}(x_i x_j) + 1)
                = P * ( -sum(x_i) + 2*sum_{i<j}(x_i x_j) + 1 )
    """

    @staticmethod
    def build_route_selection_qubo(candidate_costs: List[float], penalty_multiplier: float = 1000.0) -> Tuple[np.ndarray, float]:
        N = len(candidate_costs)
        Q = np.zeros((N, N), dtype=np.float64)
        
        # Diagonal elements: Linear cost c_i minus Penalty P
        for i in range(N):
            Q[i, i] = candidate_costs[i] - penalty_multiplier
            
        # Off-diagonal elements: Mutual exclusion penalty 2 * P
        for i in range(N):
            for j in range(i + 1, N):
                Q[i, j] = 2.0 * penalty_multiplier

        constant_offset = penalty_multiplier
        return Q, constant_offset

    @staticmethod
    def build_fleet_assignment_qubo(cost_matrix: np.ndarray, penalty: float = 2000.0) -> Tuple[np.ndarray, float]:
        """
        Assigns M ambulances to K emergencies.
        cost_matrix shape: (num_ambulances, num_emergencies)
        """
        num_amb, num_emerg = cost_matrix.shape
        num_vars = num_amb * num_emerg
        Q = np.zeros((num_vars, num_vars), dtype=np.float64)
        
        def var_idx(a, e):
            return a * num_emerg + e

        # Linear costs + constraint 1: Each emergency assigned exactly once
        for e in range(num_emerg):
            for a in range(num_amb):
                idx = var_idx(a, e)
                Q[idx, idx] += cost_matrix[a, e] - penalty
                
            for a1 in range(num_amb):
                for a2 in range(a1 + 1, num_amb):
                    idx1 = var_idx(a1, e)
                    idx2 = var_idx(a2, e)
                    Q[idx1, idx2] += 2.0 * penalty

        # Constraint 2: Each ambulance assigned at most once
        for a in range(num_amb):
            for e1 in range(num_emerg):
                for e2 in range(e1 + 1, num_emerg):
                    idx1 = var_idx(a, e1)
                    idx2 = var_idx(a, e2)
                    Q[idx1, idx2] += 2.0 * penalty

        return Q, penalty * num_emerg
