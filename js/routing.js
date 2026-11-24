// ============================================================
// ROUTING MODULE — OSRM Road Corridors & Two-Phase Emergency Dispatch
// QERI (Quantum Emergency Routing Intelligence)
// ============================================================

let isAmbulanceEnRoute = false;
let currentActiveRoute = null;

async function fetchRouteArray(p1, p2, useAlts) {
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/route/calculate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                originLat: p1.lat,
                originLng: p1.lng,
                destLat: p2.lat,
                destLng: p2.lng,
                requestAlternatives: !!useAlts
            })
        });
        if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data.routes) && data.routes.length > 0) {
                return data.routes;
            }
        }
    } catch (e) {
        console.warn('[BACKEND ROUTE] Falling back to direct browser OSRM:', e.message);
    }

    const alts = useAlts ? 'true' : 'false';
    const url = `https://router.project-osrm.org/route/v1/driving/${p1.lng},${p1.lat};${p2.lng},${p2.lat}?overview=full&geometries=geojson&alternatives=${alts}`;

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error('OSRM HTTP error');
        const data = await res.json();
        if (data.routes && data.routes.length > 0) {
            return data.routes.map((r, i) => ({
                route_id:     `OSRM-R${i + 1}`,
                name:         i === 0 ? 'Primary Road Corridor' : `Alternative Corridor ${i}`,
                path:         r.geometry.coordinates.map(c => [c[1], c[0]]),
                duration_sec: r.duration,
                duration_min: Math.round(r.duration / 60 * 10) / 10,
                distance_m:   r.distance,
                distance_km:  Math.round(r.distance / 1000 * 10) / 10,
                source:       'OSRM Live Road Engine'
            }));
        }
    } catch (e) {
        console.warn('[OSRM] Query failed, using geometric fallback:', e.message);
    }

    const dKm = haversine(p1.lat, p1.lng, p2.lat, p2.lng);
    const durMin = Math.round((dKm / 38.0) * 60 * 10) / 10;
    return [{
        route_id:     'FALLBACK-R1',
        name:         'Direct estimate (road routing unavailable)',
        path:         [[p1.lat, p1.lng], [p2.lat, p2.lng]],
        duration_sec: Math.max(30, durMin * 60),
        duration_min: durMin,
        distance_m:   dKm * 1000,
        distance_km:  Math.round(dKm * 10) / 10,
        source:       'Geometric corridor estimation'
    }];
}

// ── TWO-PHASE AUTO DISPATCH FLOW ─────────────────────────────

async function callAmbulanceAuto() {
    const btn = document.getElementById('autoDispatchBtn');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '⏳ Matching available response unit...';

    clearRoutePolylines();
    clearAnimation();
    isAmbulanceEnRoute = false;

    const curLat = currentLocation.latitude !== null ? currentLocation.latitude : null;
    const curLng = currentLocation.longitude !== null ? currentLocation.longitude : null;

    if (curLat === null || curLng === null) {
        btn.disabled = false;
        btn.innerHTML = '🚨 AUTO-DISPATCH (AI-MATCHED UNIT)';
        alert('No valid location. Allow GPS or activate Demo Location first.');
        return;
    }

    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/simulate_dispatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                caseId:        activeCaseId,
                userLat:       curLat,
                userLng:       curLng,
                hospitalId:    selectedHosp ? selectedHosp.id : null,
                hospitalName:  selectedHosp ? selectedHosp.name : null,
                hospitalLat:   selectedHosp ? selectedHosp.lat : null,
                hospitalLng:   selectedHosp ? selectedHosp.lng : null,
                emergencyType: currentEmergencyType,
                solverMode:    typeof currentSolverMode !== 'undefined' ? currentSolverMode : 'topsis'
            })
        });

        if (res.ok) {
            const data = await res.json();

            activeCaseId = data.case_id;
            const caseDom = document.getElementById('uCaseId');
            if (caseDom) caseDom.textContent = `#${activeCaseId}`;

            // 1. Reposition ambulance station to assigned unit real coordinates
            if (data.ambulance_coords) {
                window.ambLat = data.ambulance_coords[0];
                window.ambLng = data.ambulance_coords[1];
            }
            const assignedMarker = fleetMarkersById[data.assigned_ambulance];
            if (assignedMarker) assignedMarker.setLatLng(data.ambulance_coords);

            // 2. Phase 1: Base Station -> Patient (prefer backend-computed corridor)
            let p1 = data.phase1_route;
            if (!p1 || !Array.isArray(p1.path) || p1.path.length < 2) {
                const p1Routes = await fetchRouteArray(
                    { lat: window.ambLat, lng: window.ambLng },
                    { lat: curLat, lng: curLng },
                    false
                );
                p1 = p1Routes[0];
            }
            drawRoute(p1.path, '#38bdf8', 5, 0.9, '12 6');

            // 3. Phase 2: Patient -> Selected Hospital (draw alternatives + highlight optimal corridor)
            const targetHospName = (data.selected_hospital && data.selected_hospital.name)
                ? data.selected_hospital.name
                : (selectedHosp ? selectedHosp.name : "Healthcare Center");

            const p2Routes = data.candidate_routes;
            if (!Array.isArray(p2Routes) || p2Routes.length === 0 || !data.selected_route) {
                throw new Error('Dispatch API did not return an optimized road route.');
            }
            const selectedP2 = data.selected_route;
            currentActiveRoute = selectedP2;
            p2Routes.forEach((r, idx) => {
                if (idx !== data.selected_route_index) {
                    drawRoute(r.path, '#94a3b8', 4, 0.45, '6 6');
                }
            });
            drawRoute(selectedP2.path, '#22c55e', 7, 0.95);

            document.getElementById('aiPanel').style.display = 'block';
            document.getElementById('aiOutput').textContent = data.explainability_report;

            if (typeof logMissionMilestone === 'function') {
                logMissionMilestone(getTimestamp(), `🚨 Unit Dispatched: ${data.assigned_ambulance}`, `Equipment: ${data.ambulance_capabilities.join(', ')} · Projected Response: ${data.ambulance_to_patient_eta_min}m`, 'danger');
            }

            // 4. Render two-phase route comparison & multi-solver benchmark
            renderRouteComparison(p1, p2Routes, {
                selected_route_index: data.selected_route_index,
                optimization_method: data.optimization_method,
                improvement_pct: data.improvement_pct,
                selected_ai_breakdown: data.selected_ai_breakdown,
                solver_comparison: data.solver_comparison
            }, data.ai_prediction);

            if (typeof refreshAuditTelemetry === 'function') {
                refreshAuditTelemetry();
            }

            // 5. Start Two-Phase Live Mission Animation (Base -> Patient -> Hospital)
            isAmbulanceEnRoute = true;
            animateFullEmergencyMission(p1.path, selectedP2.path, targetHospName, data.assigned_ambulance,
                p1.duration_sec, selectedP2.duration_sec);

            const fb = data.is_capability_fallback ? ' (capability fallback)' : '';
            const estimatedRoute = selectedP2.source && selectedP2.source.toLowerCase().includes('fallback');
            updateStatus('simDot', estimatedRoute ? 'y' : 'b', 'simText',
                `Active: ${data.assigned_ambulance}${fb}${estimatedRoute ? ' · estimated route' : ''}`);
        } else {
            const error = await res.json().catch(() => null);
            const detail = error && error.detail ? error.detail : `Dispatch API returned HTTP ${res.status}`;
            throw new Error(detail);
        }
    } catch (e) {
        console.error('[AUTO DISPATCH ERROR]', e);
        alert(`Dispatch could not be completed: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🚨 AUTO-DISPATCH (AI-MATCHED UNIT)';
    }
}

// ── MANUAL ROUTE CALCULATION ─────────────────────────────────

async function calculateRoutes() {
    if (!selectedHosp) return;

    const btn = document.getElementById('calcBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Querying road corridors and risk optimizer...';

    clearRoutePolylines();
    clearAnimation();
    isAmbulanceEnRoute = false;

    try {
        const curLat = currentLocation.latitude !== null ? currentLocation.latitude : null;
        const curLng = currentLocation.longitude !== null ? currentLocation.longitude : null;

        if (curLat === null || curLng === null) {
            alert('No valid location available. Allow GPS or use Demo Location first.');
            return;
        }

        if (typeof logMissionMilestone === 'function') {
            logMissionMilestone(getTimestamp(), 'Generating Road Corridors', `Patient ➔ ${selectedHosp.name}`, 'info');
        }

        const candidateRoutes = await fetchRouteArray({ lat: curLat, lng: curLng }, { lat: selectedHosp.lat, lng: selectedHosp.lng }, true);

        // Backend multi-factor risk scoring and route optimization
        let optData = null;
        let aiPredData = null;
        try {
            const optRes = await fetch(`${CONFIG.BACKEND_API_BASE}/route/optimize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    candidateRoutes: candidateRoutes,
                    emergencyType: currentEmergencyType,
                    severity: currentSeverity,
                    solverMode: typeof currentSolverMode !== 'undefined' ? currentSolverMode : 'topsis'
                })
            });
            if (optRes.ok) {
                const j = await optRes.json();
                optData = j.optimization;
            }

            if (optData && optData.selected_ai_breakdown) {
                aiPredData = optData.selected_ai_breakdown.ai_telemetry || null;
            }
        } catch (e) {
            console.warn('[ROUTE OPTIMIZER] Backend optimizer offline, using baseline calculation.');
        }

        const colors = ['#22c55e', '#fbbf24', '#c084fc'];
        const selIdx = optData ? optData.selected_route_index : 0;
        currentActiveRoute = candidateRoutes[selIdx] || candidateRoutes[0];

        candidateRoutes.forEach((r, i) => {
            const color = colors[i % colors.length];
            const isOpt = i === selIdx;
            drawRoute(r.path, color, isOpt ? 7 : 4, isOpt ? 0.95 : 0.55);
        });

        renderRouteComparison(null, candidateRoutes, optData, aiPredData);

        if (typeof logMissionMilestone === 'function' && optData) {
            logMissionMilestone(getTimestamp(), `Route Selected (${optData.optimization_method})`, `Selected: ${candidateRoutes[selIdx].name} · Cost improvement: ${optData.improvement_pct}%`, 'quantum');
        }
        const aiPanel = document.getElementById('aiPanel');
        const aiOutput = document.getElementById('aiOutput');
        if (aiPanel && aiOutput) {
            aiPanel.style.display = 'block';
            aiOutput.textContent = [
                'ROUTE RECOMMENDATION (not dispatched)',
                `Destination: ${selectedHosp.name}`,
                `Selected corridor: ${currentActiveRoute.name}`,
                `Optimization: ${optData ? optData.optimization_method : 'Baseline route'}`,
                `Predicted travel time: ${currentActiveRoute.duration_min} minutes`,
                `Distance: ${currentActiveRoute.distance_km} km`,
                `Traffic prediction: ${aiPredData ? aiPredData.predicted_congestion : 'Unavailable'}`
            ].join('\n');
        }

    } catch (err) {
        console.error('[ROUTING ERROR]', err);
        alert('Route calculation error: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '⚡ Calculate Road Corridors & Optimize';
    }
}

function renderRouteComparison(p1, candidateRoutes, optData, aiPredData) {
    document.getElementById('routesCard').style.display = 'block';
    document.getElementById('rpanel').style.display = 'flex';

    const selIdx      = optData ? optData.selected_route_index : 0;
    const optMethod   = optData ? optData.optimization_method : 'Baseline (OSRM)';
    const improvement = optData ? optData.improvement_pct : null;

    let html = '';
    if (p1) {
        html = `<div style="font-size:11px;color:var(--text-dim);padding:6px 10px;background:rgba(56,189,248,0.1);border:1px solid rgba(56,189,248,0.3);border-radius:8px;margin-bottom:8px">
            <strong>Phase 1 (Response):</strong> <strong style="color:#38bdf8">${p1.duration_min} min</strong> · ${p1.distance_km} km
        </div>`;
    }

    candidateRoutes.forEach((r, i) => {
        const isSel       = i === selIdx;
        const totalMission = Math.round(((p1 ? p1.duration_min : 0) + r.duration_min) * 10) / 10;
        const badge       = isSel ? `Selected (${optMethod})` : (i === 0 ? 'Baseline' : 'Alternative');
        html += `<div class="route-card ${isSel ? 'quantum best' : 'normal'}">
            <div class="route-header">
                <div class="route-label" style="color:${isSel ? '#c084fc' : '#f87171'}">
                    ${escapeHTML(r.name)} <span class="route-badge ${isSel ? 'tag-best' : 'tag-slow'}">${escapeHTML(badge)}</span>
                </div>
                <div class="route-time">${totalMission}m</div>
            </div>
            <div class="route-meta">${p1 ? 'Phase 2 (Transport)' : 'Patient to hospital'}: ${r.duration_min} min · ${r.distance_km} km · ${escapeHTML(r.source)}</div>
            <div style="font-size:10px;color:#38bdf8;margin-top:4px">${p1 ? 'Total Projected Mission Time' : 'Projected drive time'}: <strong>${totalMission} mins</strong></div>
        </div>`;
    });

    document.getElementById('routesList').innerHTML = html;
    document.getElementById('savingsVal').textContent = improvement === null ? '—' : `${improvement.toFixed(1)}%`;

    const selRoute = candidateRoutes[selIdx] || candidateRoutes[0];
    const totalMissionMin = selRoute ? Math.round(((p1 ? p1.duration_min : 0) + selRoute.duration_min) * 10) / 10 : null;
    const totalEtaEl = document.getElementById('totalMissionEtaVal');
    if (totalEtaEl) totalEtaEl.textContent = totalMissionMin !== null ? `${totalMissionMin}m` : '—';

    const cong = aiPredData ? aiPredData.predicted_congestion : 'Unavailable';
    const rel = aiPredData && Number.isFinite(aiPredData.reliability_indicator_pct)
        ? `${aiPredData.reliability_indicator_pct}%`
        : 'Unavailable';
    const weatherSnap = optData && optData.selected_ai_breakdown
        ? (optData.selected_ai_breakdown.weather_telemetry || {})
        : {};
    const rainMm = Number.isFinite(weatherSnap.max_rain_along_corridor_mm)
        ? `${weatherSnap.max_rain_along_corridor_mm} mm`
        : 'Unavailable';

    document.getElementById('compareBars').innerHTML = `
        <div class="compare-row"><span>Optimization Engine</span><span style="color:#c084fc;font-weight:700">${escapeHTML(optMethod)}</span></div>
        <div class="compare-row"><span>AI Congestion Index</span><span style="color:#38bdf8;font-weight:700">${cong}</span></div>
        <div class="compare-row"><span>ETA Model Reliability</span><span style="color:var(--text);font-family:monospace">${rel}</span></div>
        <div class="compare-row"><span>Corridor Rain Intensity</span><span style="color:#38bdf8;font-family:monospace">${rainMm}</span></div>
    `;

    const benchCard = document.getElementById('solverComparisonCard');
    const benchBody = document.getElementById('solverComparisonBody');
    const comp = optData && optData.solver_comparison ? optData.solver_comparison : null;
    if (benchCard && benchBody && comp && Object.keys(comp).length > 0) {
        benchCard.style.display = 'block';
        benchBody.innerHTML = Object.entries(comp).map(([key, info]) => {
            const isActive = (typeof currentSolverMode !== 'undefined' && currentSolverMode === key);
            return `<div class="compare-row" style="${isActive ? 'background:rgba(192,132,252,0.1);padding:6px;border-radius:6px' : ''}">
                <span style="font-weight:${isActive ? '800' : '600'};color:${isActive ? '#c084fc' : 'var(--text-dim)'}">${key.toUpperCase()}</span>
                <span style="font-size:10px;color:var(--text)">${escapeHTML(info.selected_route_name)}</span>
                <span style="font-family:monospace;font-size:10px;color:#38bdf8">${info.objective_cost} (${info.execution_time_ms}ms)</span>
            </div>`;
        }).join('');
    }
}

async function checkDynamicReroute() {
    if (!isAmbulanceEnRoute || !selectedHosp) return;
    const inPhase2 = (typeof currentMissionPhase !== 'undefined' && currentMissionPhase === 'en_route_to_hospital');
    const originLat = inPhase2 ? window.ambLat : currentLocation.latitude;
    const originLng = inPhase2 ? window.ambLng : currentLocation.longitude;
    if (originLat === null || originLat === undefined) return;

    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/route/reroute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                currentLat:     originLat,
                currentLng:     originLng,
                destLat:        selectedHosp.lat,
                destLng:        selectedHosp.lng,
                originalEtaSec: currentActiveRoute && currentActiveRoute.duration_sec
                    ? currentActiveRoute.duration_sec
                    : 600.0,
                emergencyType:  currentEmergencyType,
                solverMode:     typeof currentSolverMode !== 'undefined' ? currentSolverMode : 'topsis',
                caseId:         activeCaseId
            })
        });
        if (!res.ok) return;
        const json = await res.json();
        const result = json.result;
        if (result.reroute_triggered) {
            showRerouteAlert(result.reason, result.new_projected_eta_min, result.time_saved_min);
            if (typeof logMissionMilestone === 'function') {
                logMissionMilestone(getTimestamp(), '🔄 Dynamic Rerouting Executed', `${result.reason} · New ETA: ${result.new_projected_eta_min}m (Saved: ${result.time_saved_min}m)`, 'danger');
            }
            clearRoutePolylines();
            currentActiveRoute = result.selected_route;
            drawRoute(result.selected_route.path, '#22c55e', 7, 0.95);
            if (inPhase2) {
                const newPath = interpolatePath(result.selected_route.path, 240);
                startPhase2(newPath, selectedHosp.name, document.getElementById('hudUnitId').textContent,
                    document.getElementById('hudUnitName').textContent, result.selected_route.duration_sec);
            }
            if (typeof refreshAuditTelemetry === 'function') refreshAuditTelemetry();
        }
    } catch (e) {}
}

function showRerouteAlert(reason, newEta, saved) {
    const toast = document.createElement('div');
    toast.className = 'reroute-toast';
    toast.innerHTML = `
        <div style="font-weight:800;color:#f59e0b;font-size:13px">⚠ DYNAMIC REROUTING TRIGGERED</div>
        <div style="font-size:11px;margin:3px 0">${escapeHTML(reason)}</div>
        <div style="font-size:11px;color:#22c55e;font-weight:700">✓ Recalculated Optimal Corridor: ${newEta} min (Saved ${saved}m)</div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 6000);
}
