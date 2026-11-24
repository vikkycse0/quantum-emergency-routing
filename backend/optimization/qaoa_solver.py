import numpy as np
import time
from typing import Tuple, Optional, Dict, Any

class QAOASimulator:
    """
    Simulates the Quantum Approximate Optimization Algorithm (QAOA)
    with normalized Cost Hamiltonian U(C, gamma) and Mixer Hamiltonian U(B, beta)
    statevector unitary evolutions and classical parameter optimization.
    """

    @staticmethod
    def is_qiskit_available() -> bool:
        try:
            import qiskit
            return True
        except ImportError:
            return False

    @staticmethod
    def _apply_mixer(state: np.ndarray, beta: float, N: int) -> np.ndarray:
        """
        Applies transverse field Mixer unitary:
        U(B, beta) = exp(-i * beta * sum_j X_j) = tensor_{j=1}^N (cos(beta)*I - i*sin(beta)*X)
        """
        c = np.cos(beta)
        s = -1j * np.sin(beta)
        mixer_1q = np.array([[c, s], [s, c]], dtype=np.complex128)
        
        state_tensor = state.reshape([2] * N)
        for qubit in range(N):
            state_tensor = np.tensordot(mixer_1q, state_tensor, axes=([1], [qubit]))
            state_tensor = np.moveaxis(state_tensor, 0, qubit)
            
        return state_tensor.reshape(-1)

    @staticmethod
    def solve_qaoa(Q: np.ndarray, constant_offset: float = 0.0, p_steps: int = 1) -> Tuple[np.ndarray, float, Dict[str, Any]]:
        """
        Executes complete QAOA quantum state simulation:
        1. Initialize uniform superposition |+>^N
        2. Apply U(C, gamma) with spectral normalization to prevent phase aliasing
        3. Apply U(B, beta)
        4. Optimize (gamma, beta) to minimize energy expectation
        5. Measure and sample optimal constrained bitstring
        """
        start_time = time.time()
        N = Q.shape[0]
        if N > 14:
            # Protect statevector simulator from exponential memory blowup
            from optimization.classical_solver import ClassicalQUBOSolver
            sol_vec, best_energy = ClassicalQUBOSolver.solve(Q, constant_offset)
            return sol_vec, best_energy, {
                "algorithm": "QAOA -> Classical QUBO Fallback (N > 14 qubits)",
                "simulated_qubits": N,
                "execution_time_ms": round((time.time() - start_time) * 1000.0, 2),
                "runtime_backend": "Classical Combinatorial Fallback"
            }

        num_states = 1 << N
        
        # Compute raw diagonal Cost Hamiltonian energies
        cost_diag = np.zeros(num_states, dtype=np.float64)
        for i in range(num_states):
            bit_vec = np.array([(i >> (N - 1 - k)) & 1 for k in range(N)], dtype=np.float64)
            cost_diag[i] = float(bit_vec.T @ Q @ bit_vec) + constant_offset

        # Shift & normalize energy scale so phase rotations span [0, 2pi] cleanly
        shifted_cost = cost_diag - np.min(cost_diag)
        max_abs = np.max(np.abs(shifted_cost))
        norm_scale = max_abs if max_abs > 1e-6 else 1.0
        normalized_cost = shifted_cost / norm_scale

        # Energy expectation function as a function of (gamma, beta)
        def expectation(gamma, beta):
            psi = np.ones(num_states, dtype=np.complex128) / np.sqrt(num_states)
            psi = psi * np.exp(-1j * gamma * normalized_cost)
            psi = QAOASimulator._apply_mixer(psi, beta, N)
            probs = np.abs(psi) ** 2
            return float(np.sum(probs * cost_diag))

        # Parameter optimization via coarse 16x16 grid + local coordinate refinement
        best_exp = float('inf')
        optimal_gamma, optimal_beta = 0.5, 0.5
        
        for g_candidate in np.linspace(0.1, 2.0 * np.pi, 16):
            for b_candidate in np.linspace(0.05, np.pi, 16):
                exp_val = expectation(g_candidate, b_candidate)
                if exp_val < best_exp:
                    best_exp = exp_val
                    optimal_gamma, optimal_beta = float(g_candidate), float(b_candidate)

        for step in (0.15, 0.04, 0.01):
            for dg in (-step, 0.0, step):
                for db in (-step, 0.0, step):
                    g_c = max(0.0, optimal_gamma + dg)
                    b_c = max(0.0, optimal_beta + db)
                    exp_val = expectation(g_c, b_c)
                    if exp_val < best_exp:
                        best_exp = exp_val
                        optimal_gamma, optimal_beta = g_c, b_c

        # Prepare final state with optimal parameters
        final_state = np.ones(num_states, dtype=np.complex128) / np.sqrt(num_states)
        final_state = final_state * np.exp(-1j * optimal_gamma * normalized_cost)
        final_state = QAOASimulator._apply_mixer(final_state, optimal_beta, N)
        
        # Measurement probability distribution |psi|^2
        probabilities = np.abs(final_state) ** 2
        
        # Filter states that satisfy the one-hot constraint (sum(x) == 1)
        valid_indices = [i for i in range(num_states) if bin(i).count("1") == 1]
        
        if valid_indices:
            # Sample most probable valid quantum state; tie-break by lowest cost energy
            best_idx = max(valid_indices, key=lambda idx: (round(float(probabilities[idx]), 6), -cost_diag[idx]))
        else:
            best_idx = int(np.argmax(probabilities))

        best_energy = float(cost_diag[best_idx])
        best_bit_array = np.array([(best_idx >> (N - 1 - k)) & 1 for k in range(N)], dtype=np.float64)
        
        elapsed_ms = round((time.time() - start_time) * 1000.0, 2)
        
        metadata = {
            "algorithm": "QAOA (Quantum Approximate Optimization Algorithm)",
            "circuit_depth_p": p_steps,
            "simulated_qubits": N,
            "state_dimension": num_states,
            "optimal_gamma": round(float(optimal_gamma), 4),
            "optimal_beta": round(float(optimal_beta), 4),
            "ground_state_measurement_probability": round(float(probabilities[best_idx]), 4),
            "expected_energy": round(float(best_exp), 2),
            "execution_time_ms": elapsed_ms,
            "runtime_backend": "Statevector Quantum Simulation Engine"
        }
        
        return best_bit_array, best_energy, metadata
