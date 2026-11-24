import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from config import DATA_DIR

DB_PATH = DATA_DIR / "quantum_emergency_audit.db"

class DatabaseManager:
    """
    Manages persistent SQLite storage for full emergency case auditability,
    dispatch decisions, quantum optimization runs, and incident telemetry.
    """
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Emergencies Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergencies (
                case_id TEXT PRIMARY KEY,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                accuracy REAL,
                source TEXT,
                emergency_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                patient_count INTEGER DEFAULT 1,
                caller_phone TEXT,
                status TEXT DEFAULT 'pending_dispatch',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            # 2. Dispatches Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                ambulance_id TEXT NOT NULL,
                ambulance_name TEXT,
                hospital_id TEXT NOT NULL,
                hospital_name TEXT,
                route_name TEXT,
                ambulance_eta_sec REAL,
                patient_hospital_eta_sec REAL,
                total_mission_eta_sec REAL,
                optimization_method TEXT,
                is_capability_fallback INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES emergencies(case_id)
            )
            """)

            # 3. Route Optimization Runs & Audit Telemetry
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS optimization_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                qubo_matrix_dim TEXT,
                solver_method TEXT,
                candidate_routes_count INTEGER,
                baseline_cost REAL,
                optimized_cost REAL,
                improvement_pct REAL,
                weather_snapshot_json TEXT,
                traffic_snapshot_json TEXT,
                explainability_report TEXT,
                created_at TEXT NOT NULL
            )
            """)

            # 4. Reroute Events
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reroute_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                trigger_reason TEXT,
                original_eta_min REAL,
                new_eta_min REAL,
                time_saved_min REAL,
                disruption_type TEXT,
                created_at TEXT NOT NULL
            )
            """)

            conn.commit()

    def record_emergency(self, emergency_data: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO emergencies (
                case_id, latitude, longitude, accuracy, source,
                emergency_type, severity, patient_count, caller_phone,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                emergency_data.get("case_id"),
                emergency_data.get("latitude"),
                emergency_data.get("longitude"),
                emergency_data.get("accuracy"),
                emergency_data.get("source", "browser-gps"),
                emergency_data.get("emergency_type"),
                emergency_data.get("severity"),
                emergency_data.get("patient_count", 1),
                emergency_data.get("caller_phone"),
                emergency_data.get("status", "pending_dispatch"),
                emergency_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def record_dispatch(self, dispatch_data: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO dispatches (
                case_id, ambulance_id, ambulance_name, hospital_id, hospital_name,
                route_name, ambulance_eta_sec, patient_hospital_eta_sec,
                total_mission_eta_sec, optimization_method, is_capability_fallback, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dispatch_data.get("case_id"),
                dispatch_data.get("ambulance_id"),
                dispatch_data.get("ambulance_name"),
                dispatch_data.get("hospital_id"),
                dispatch_data.get("hospital_name"),
                dispatch_data.get("route_name"),
                dispatch_data.get("ambulance_eta_sec"),
                dispatch_data.get("patient_hospital_eta_sec"),
                dispatch_data.get("total_mission_eta_sec"),
                dispatch_data.get("optimization_method"),
                1 if dispatch_data.get("is_capability_fallback") else 0,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def record_optimization_run(self, opt_data: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO optimization_runs (
                case_id, qubo_matrix_dim, solver_method, candidate_routes_count,
                baseline_cost, optimized_cost, improvement_pct,
                weather_snapshot_json, traffic_snapshot_json, explainability_report, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                opt_data.get("case_id"),
                opt_data.get("qubo_matrix_dim"),
                opt_data.get("solver_method"),
                opt_data.get("candidate_routes_count", 1),
                opt_data.get("baseline_cost"),
                opt_data.get("optimized_cost"),
                opt_data.get("improvement_pct"),
                json.dumps(opt_data.get("weather_snapshot", {})),
                json.dumps(opt_data.get("traffic_snapshot", {})),
                opt_data.get("explainability_report", ""),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def record_reroute(self, reroute_data: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO reroute_events (
                case_id, trigger_reason, original_eta_min, new_eta_min,
                time_saved_min, disruption_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                reroute_data.get("case_id", "N/A"),
                reroute_data.get("trigger_reason"),
                reroute_data.get("original_eta_min"),
                reroute_data.get("new_eta_min"),
                reroute_data.get("time_saved_min"),
                reroute_data.get("disruption_type"),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def get_analytics_summary(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM emergencies")
            total_cases = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM dispatches")
            total_dispatches = cursor.fetchone()[0]
            
            cursor.execute("SELECT AVG(improvement_pct) FROM optimization_runs")
            avg_improv = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT COUNT(*) FROM reroute_events")
            total_reroutes = cursor.fetchone()[0]

            return {
                "total_emergencies_recorded": total_cases,
                "total_dispatches_completed": total_dispatches,
                "average_qubo_optimization_gain_pct": round(float(avg_improv), 1),
                "total_dynamic_reroutes_executed": total_reroutes,
                "database_engine": "SQLite 3 Persistent Audit Store"
            }

    def update_emergency_status(
        self,
        case_id: str,
        status: str,
        ambulance_id: Optional[str] = None,
        hospital_id: Optional[str] = None
    ):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE emergencies SET status = ?, updated_at = ? WHERE case_id = ?",
                (status, datetime.now(timezone.utc).isoformat(), case_id)
            )
            conn.commit()

    def get_recent_cases(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT e.case_id, e.emergency_type, e.severity, e.status, e.source, e.created_at,
                   d.ambulance_id, d.ambulance_name, d.hospital_name, d.total_mission_eta_sec, d.optimization_method,
                   o.improvement_pct
            FROM emergencies e
            LEFT JOIN dispatches d ON d.dispatch_id = (
                SELECT MAX(d2.dispatch_id) FROM dispatches d2 WHERE d2.case_id = e.case_id
            )
            LEFT JOIN optimization_runs o ON o.run_id = (
                SELECT MAX(o2.run_id) FROM optimization_runs o2 WHERE o2.case_id = e.case_id
            )
            ORDER BY e.created_at DESC
            LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def generate_case_audit_report(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM emergencies WHERE case_id = ?", (case_id,))
            emerg = cursor.fetchone()
            if not emerg:
                return None
                
            cursor.execute("SELECT * FROM dispatches WHERE case_id = ? ORDER BY dispatch_id DESC LIMIT 1", (case_id,))
            disp = cursor.fetchone()
            
            cursor.execute("SELECT * FROM optimization_runs WHERE case_id = ? ORDER BY run_id DESC LIMIT 1", (case_id,))
            opt = cursor.fetchone()
            
            return {
                "emergency": dict(emerg) if emerg else {},
                "dispatch": dict(disp) if disp else {},
                "optimization": dict(opt) if opt else {}
            }

db_manager = DatabaseManager()
