# ⚛ AERT — AI Emergency Routing & Tracking System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-1.3+-orange.svg)](https://scikit-learn.org/)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9.4-brightgreen.svg)](https://leafletjs.com/)
[![OSRM](https://img.shields.io/badge/OSRM-Live_Road_Routing-blueviolet.svg)](https://project-osrm.org/)
[![QUBO / QAOA](https://img.shields.io/badge/Optimization-QUBO%20%2F%20QAOA-purple.svg)]()

> **"AI predicts what is likely to happen. Optimization decides what should be done. The map executes and visualizes the decision."**

---

## 📖 1. Project Vision & Architecture

Standard turn-by-turn navigation applications (e.g., Google Maps) solve single-point routing for ordinary driving journeys. During critical medical emergencies, dispatch decisions involve multi-variable constraints:

> *"Given an emergency patient, distributed fleet units with distinct medical equipment, multiple hospitals with differing clinical capabilities, dynamic traffic bottlenecks, and weather delays, **which ambulance + road corridor + hospital combination** minimizes total response time and patient mortality risk?"*

This system provides a full **Emergency Decision Support + Routing Optimization Engine**:

```
                             [ PATIENT ]
                   (Device GPS / Manual Pin / SOS)
                                 │
                                 ▼
                     [ EMERGENCY CLASSIFIER ]
                 (Cardiac, Stroke, Trauma, etc.)
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
   [ MEDICAL FLEET ]    [ HOSPITAL SUITABILITY ] [ OSRM ROAD ENGINE ]
(Equipment Matching:    (24x7 ED, Cath Lab, ICU, (Live Alternatives &
 ALS, Defibrillator,     Trauma Center Scoring)   Geometric Fallback)
 Ventilator, Trauma)             │                    │
            │                    │                    ▼
            │                    │           [ AI TRAFFIC PREDICTOR ]
            │                    │          (HistGradientBoosting:
            │                    │           ETA, Weather, Incidents)
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 │
                                 ▼
                   [ QUBO OPTIMIZATION ENGINE ]
              (QAOA Simulator / Quantum-Inspired)
                                 │
                                 ▼
                      [ OPTIMAL ALLOCATION ]
                  • Medically Qualified Unit
                  • Minimum Risk Road Corridor
                  • Best Clinical Facility
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
   [ LIVE MAP TRACKING ]                    [ EXPLAINABLE AI (XAI) ]
 (Segment 1: Amb -> Patient              (Transparent mathematical
  Segment 2: Patient -> Hosp              and clinical reasoning)
  Dynamic Rerouting on Incidents)
```

---

## 🔬 2. Technical Component Breakdown

### 2.1 Real-Time Geolocation & Location State Model
- **Device GPS**: Utilizes `navigator.geolocation.getCurrentPosition` with high accuracy (`enableHighAccuracy: true`, `timeout: 12000ms`, `maximumAge: 0`).
- **Location State Structure**: Single authoritative frontend state:
  ```javascript
  currentLocation = {
      latitude: float,
      longitude: float,
      accuracy: float,
      timestamp: ISOString,
      source: 'gps' | 'manual' | 'demo'
  }
  ```
- **Error Handling**: Gracefully handles `PERMISSION_DENIED`, `POSITION_UNAVAILABLE`, and `TIMEOUT` without silently substituting coordinates.
- **Simulation / Demo Mode**: Explicitly marked button: `📍 Use Demo Location (Simulation Mode)`.

### 2.2 Medical Capability Filtering (`backend/services/fleet_service.py`)
Ambulance dispatch does not greedily assign the nearest unit. The system maps emergency categories to required life-support equipment:
- **Cardiac Emergency**: Requires `ALS` + `Cardiac` + `Defibrillator`.
- **Stroke / Neuro**: Requires `ALS` + specialized neuro-intake protocol.
- **Trauma / Severe Hemorrhage**: Requires `ALS` + `Trauma` rescue equipment.
- **Respiratory Distress**: Requires `ALS` + `Ventilator` + `Oxygen`.
- **Burn Incident**: Requires `ALS` + `Burn` care equipment.
- **Fracture / General**: Requires standard `BLS` response.

If all specialized units are engaged on active calls, the system assigns the best available unit marked with an explicit fallback indicator.

### 2.3 AI Traffic & Travel Time Regression (`backend/ai/`)
- **Algorithm**: `HistGradientBoostingRegressor` (scikit-learn).
- **Features**: `[hour, day_of_week, distance_km, weather_code, rainfall_mm, is_rush_hour, has_event, has_accident]`.
- **No Target Leakage**: Road `distance_km` and `rainfall_mm` are strictly independent variables.
- **Model Evaluation Metrics** (calculated on 20% test split):
  - $R^2 \approx 0.88$
  - $\text{MAE} \approx 59.7\text{s}$
  - $\text{RMSE} \approx 84.1\text{s}$
- **AI Feeding Route Optimization**: Predicted travel times, congestion risk penalties, and incident delays directly parameterize the QUBO objective cost.

### 2.4 Mathematically Complete QUBO & QAOA Formulation
Ambulance dispatch and candidate corridor selection are formulated as Quadratic Unconstrained Binary Optimization (QUBO) problems:

$$\min_{x \in \{0,1\}^N} \quad E(x) = x^T Q x + P \left(\sum_{i=1}^N x_i - 1\right)^2$$

Where:
- $x_i = 1$ indicates selection of candidate option $i$.
- $P$ is the mutual exclusion penalty enforcing that **exactly one** valid choice is selected.

#### QAOA Simulator (`backend/optimization/qaoa_solver.py`):
1. Initializes uniform superposition $|\psi_0\rangle = |+\rangle^{\otimes N}$.
2. Applies normalized Cost Hamiltonian unitary: $U(C, \gamma) = \exp(-i \gamma H_C)$.
3. Applies transverse field Mixer unitary: $U(B, \beta) = \exp(-i \beta \sum_j X_j) = \bigotimes_{j=1}^N (\cos\beta I - i\sin\beta X_j)$.
4. Optimizes $(\gamma, \beta)$ to minimize expected energy $\langle \psi | H_C | \psi \rangle$.
5. Samples measurement probability distribution $|\psi(\gamma^*, \beta^*)|^2$ to select the optimal ground state.

### 2.5 Total Mission ETA Semantics
The mission timeline is decomposed into distinct journey segments:
- **Segment 1**: Ambulance Station $\rightarrow$ Patient Location ($\text{ETA}_1$)
- **Segment 2**: Patient Location $\rightarrow$ Destination Hospital ($\text{ETA}_2$)
- **Total Mission ETA**: $\text{ETA}_{\text{total}} = \text{ETA}_1 + \text{ETA}_2$

### 2.6 Dynamic Real-Time Rerouting
During ambulance transit, the corridor monitor can receive simulated road disruptions (Accident $+200\%$ delay, Heavy Monsoon Rain $+80\%$ delay, Road Closure). When triggered:
1. Recalculates candidate road corridors from current vehicle coordinates.
2. Compares projected delays.
3. Automatically triggers an in-flight reroute and visualizes the updated green corridor trail and time saved.

---

## 🚀 3. Quickstart & Installation Guide

### Prerequisites
- Python 3.10+
- Modern Web Browser (Chrome, Firefox, Edge, Safari)

### Step 1: Install Backend Dependencies
```powershell
cd d:\qunatum1\quantum\backend
pip install -r requirements.txt
```

### Step 2: Run the Verification Test Suite
```powershell
python -m unittest tests/test_all_components.py
```
*(All 11 unit and integration tests will execute and pass)*

### Step 3: Run Full CLI Simulation
```powershell
python main.py
```

### Step 4: Launch FastAPI API Gateway
```powershell
python api_server.py
```
*Server runs at `http://127.0.0.1:8001`.*

### Step 5: Launch Frontend Dashboard
Open `d:\qunatum1\quantum\index.html` directly in your browser.

---

## 🎓 4. Faculty Demonstration Guide

1. **Live GPS Position**:
   - Open `index.html`. Allow location access. The map immediately centers on your actual device coordinates.
2. **Emergency SOS Transmission**:
   - Open `phone.html`, select **Cardiac Emergency (Critical)**, and press **SEND SOS**.
   - Your device coordinates are transmitted to `POST /api/sos_trigger`.
3. **Dispatcher Interception**:
   - The central dashboard detects the emergency with continuous Case ID (`#CASE-XXXX`).
4. **Medical Capability Matching & QUBO Dispatch**:
   - The system queries fleet assets and selects `AMB-01` (equipped with ALS & Cardiac Defibrillator).
5. **Hospital Suitability & Corridor Optimization**:
   - The QAOA simulator evaluates candidate routes and ranks healthcare facilities by clinical compatibility.
6. **Dynamic Reroute Demonstration**:
   - Click **🎛 Faculty Demo Panel** in the top bar.
   - Click **💥 Inject Accident (+200% Delay)**.
   - The dynamic reroute engine updates the ambulance trajectory live on the map.
7. **Explainable AI (XAI)**:
   - Review the detailed text breakdown explaining the clinical, optimization, and environmental reasons behind the decision.
