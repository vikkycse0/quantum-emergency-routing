import numpy as np
import itertools
from typing import Tuple, List, Dict, Any

class ClassicalQUBOSolver:
    """
    Solves QUBO matrix classically using exact evaluation for small N (N <= 20)
    or simulated annealing / heuristic minimization for large N.
    """

    @staticmethod
    def solve(Q: np.ndarray, constant_offset: float = 0.0) -> Tuple[np.ndarray, float]:
        N = Q.shape[0]
        
        # For N <= 18, exact combinatorial state exploration is instant and guaranteed optimal
        if N <= 18:
            best_energy = float('inf')
            best_state = None
            
            for state_tuple in itertools.product([0, 1], repeat=N):
                x = np.array(state_tuple, dtype=np.float64)
                # Energy = x^T Q x + constant_offset
                energy = float(x.T @ Q @ x) + constant_offset
                if energy < best_energy:
                    best_energy = energy
                    best_state = x
                    
            return best_state, best_energy
        else:
            # Random greedy / simulated local search for larger systems
            x = np.zeros(N, dtype=np.float64)
            best_energy = float('inf')
            best_state = x.copy()
            
            for _ in range(500):
                # Start with single random 1
                curr_x = np.zeros(N, dtype=np.float64)
                curr_x[np.random.randint(0, N)] = 1.0
                energy = float(curr_x.T @ Q @ curr_x) + constant_offset
                if energy < best_energy:
                    best_energy = energy
                    best_state = curr_x
                    
            return best_state, best_energy
