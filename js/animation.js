// ============================================================
// ANIMATION MODULE — Two-Phase Live Vehicle Telemetry & Movement
// AERT (AI Emergency Routing & Tracking)
// ============================================================

let ambulanceAnimId = null;
let ambulanceMarker = null;
let trailMarkers = [];
let phaseTransitionTimeout = null;
let currentMissionPhase = 'idle';
let lastPhaseSyncAt = 0;
const SIMULATION_TIME_SCALE = 30;

async function syncMissionPhaseToBackend(phase, lat, lng, speedKmh, force = false) {
    const now = Date.now();
    if (!force && now - lastPhaseSyncAt < 900) return;
    lastPhaseSyncAt = now;
    try {
        await fetch(`${CONFIG.BACKEND_API_BASE}/active_dispatch/phase`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                caseId: typeof activeCaseId !== 'undefined' ? activeCaseId : null,
                ambulanceId: document.getElementById('hudUnitId')?.textContent || null,
                phase: phase,
                lat: lat,
                lng: lng,
                speedKmh: speedKmh
            })
        });
    } catch (e) {}
}

function getPathDistanceKm(path, startIndex = 0) {
    let distanceKm = 0;
    for (let i = Math.max(1, startIndex); i < path.length; i++) {
        distanceKm += haversine(path[i - 1][0], path[i - 1][1], path[i][0], path[i][1]);
    }
    return distanceKm;
}

function getSimulatedTravelDurationMs(path, routeDurationSec, defaultSpeedKmh) {
    let durationSec = Number(routeDurationSec);
    if (!Number.isFinite(durationSec) || durationSec <= 0) {
        const distanceKm = getPathDistanceKm(path);
        durationSec = distanceKm / defaultSpeedKmh * 3600;
    }
    return Math.max(1000, durationSec * 1000 / SIMULATION_TIME_SCALE);
}

function updateVehicleHUD(visible, unitName, unitId, status, speedKmh, distRemKm, lat, lng, trafficTxt) {
    const hud = document.getElementById('vehicleHud');
    if (!hud) return;

    if (!visible) {
        hud.style.display = 'none';
        return;
    }

    hud.style.display = 'flex';
    if (unitName) document.getElementById('hudUnitName').textContent = unitName;
    if (unitId) document.getElementById('hudUnitId').textContent = unitId;
    if (status) document.getElementById('hudMissionStatus').textContent = status;
    if (speedKmh !== undefined) document.getElementById('hudSpeed').textContent = `${Math.round(speedKmh)} km/h`;
    if (distRemKm !== undefined) document.getElementById('hudDistRem').textContent = `${distRemKm.toFixed(2)} km`;
    if (lat !== undefined && lng !== undefined) document.getElementById('hudCoords').textContent = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    if (trafficTxt) document.getElementById('hudTraffic').textContent = trafficTxt;
}

function animateFullEmergencyMission(phase1Path, phase2Path, hospitalName, ambId, phase1DurationSec, phase2DurationSec) {
    clearAnimation();
    if (!phase1Path || phase1Path.length < 2) return;

    // Generate smooth dense sub-waypoints
    const smoothP1 = interpolatePath(phase1Path, 180);
    const smoothP2 = phase2Path && phase2Path.length >= 2 ? interpolatePath(phase2Path, 240) : [];

    const unitDisplayName = ambId === 'AMB-01' ? 'Rapid Response Unit Alpha' : `Emergency Unit ${ambId}`;

    const ambIcon = L.divIcon({
        html: `<div style="font-size:32px;filter:drop-shadow(0 0 10px rgba(56,189,248,0.95))">🚑</div>`,
        className: '',
        iconSize: [36, 36],
        iconAnchor: [18, 18],
    });
    ambulanceMarker = L.marker(smoothP1[0], { icon: ambIcon, zIndexOffset: 5000 }).addTo(leafletMap);

    const p1Total = smoothP1.length;
    const phase1DurationMs = getSimulatedTravelDurationMs(smoothP1, phase1DurationSec, 40);
    const phase1StepMs = Math.max(16, phase1DurationMs / (p1Total - 1));
    const p1DistanceKm = getPathDistanceKm(smoothP1);
    const phase1SpeedKmh = phase1DurationSec > 0 ? p1DistanceKm / (phase1DurationSec / 3600) : 40;
    let idx = 0, lastT = 0, trailCt = 0;

    updateStatus('simDot', 'b', 'simText', `Unit ${ambId} En Route to Patient`);
    currentMissionPhase = 'en_route_to_patient';
    syncMissionPhaseToBackend('en_route_to_patient', smoothP1[0][0], smoothP1[0][1], phase1SpeedKmh, true);
    updateVehicleHUD(true, unitDisplayName, ambId, 'Phase 1: Responding to Patient Location', phase1SpeedKmh, p1DistanceKm, smoothP1[0][0], smoothP1[0][1], `Simulation playback ×${SIMULATION_TIME_SCALE}`);

    function tickPhase1(ts) {
        if (idx >= p1Total) {
            // Reached Patient
            const endPt = smoothP1[p1Total - 1];
            ambulanceMarker.setLatLng(endPt);
            ambulanceMarker.setIcon(L.divIcon({
                html: '<div style="font-size:32px;filter:drop-shadow(0 0 14px #38bdf8)">👨‍⚕️</div>',
                className: '',
                iconSize: [36, 36],
                iconAnchor: [18, 18]
            }));

            currentMissionPhase = 'on_scene';
            syncMissionPhaseToBackend('on_scene', endPt[0], endPt[1], 0, true);
            updateStatus('simDot', 'y', 'simText', 'Paramedics On Scene (Stabilizing)');
            updateVehicleHUD(true, unitDisplayName, ambId, 'Phase 1.5: Paramedics On Scene — Loading Patient', 0, 0.0, endPt[0], endPt[1], 'Stationary / Stabilizing');

            if (typeof logMissionMilestone === 'function') {
                logMissionMilestone(getTimestamp(), `👨‍⚕️ Ambulance On Scene`, `Paramedics stabilizing patient at (${endPt[0].toFixed(4)}, ${endPt[1].toFixed(4)}). Preparing emergency transport.`, 'info');
            }

            // Pause on scene for 1.8s then start transport using latest active Phase 2 route
            phaseTransitionTimeout = setTimeout(() => {
                phaseTransitionTimeout = null;
                const latestP2 = (typeof currentActiveRoute !== 'undefined' && currentActiveRoute && Array.isArray(currentActiveRoute.path) && currentActiveRoute.path.length >= 2)
                    ? interpolatePath(currentActiveRoute.path, 240)
                    : smoothP2;
                const latestDur = (typeof currentActiveRoute !== 'undefined' && currentActiveRoute && currentActiveRoute.duration_sec)
                    ? currentActiveRoute.duration_sec
                    : phase2DurationSec;
                startPhase2(latestP2, hospitalName, ambId, unitDisplayName, latestDur);
            }, 1800);
            return;
        }

        if (ts - lastT < phase1StepMs) {
            ambulanceAnimId = requestAnimationFrame(tickPhase1);
            return;
        }
        lastT = ts;

        const curPt = smoothP1[idx];
        const distRem = getPathDistanceKm(smoothP1, idx);
        const speed = phase1SpeedKmh;

        if (ambulanceMarker) {
            ambulanceMarker.setLatLng(curPt);
        }
        window.ambLat = curPt[0];
        window.ambLng = curPt[1];
        syncMissionPhaseToBackend('en_route_to_patient', curPt[0], curPt[1], speed, false);

        updateVehicleHUD(true, unitDisplayName, ambId, 'Phase 1: Responding to Patient Location', speed, distRem, curPt[0], curPt[1], 'Response Speed: High');

        // Blue Response Trail
        trailCt++;
        if (trailCt % 5 === 0) {
            const dot = L.circleMarker(curPt, {
                radius: 3, fillColor: '#38bdf8', fillOpacity: 0.7,
                stroke: false
            }).addTo(leafletMap);
            trailMarkers.push(dot);
            setTimeout(() => { try { leafletMap.removeLayer(dot); } catch(e){} }, 3000);
        }

        idx += 1;
        ambulanceAnimId = requestAnimationFrame(tickPhase1);
    }

    ambulanceAnimId = requestAnimationFrame(tickPhase1);
}

function startPhase2(smoothP2, hospitalName, ambId, unitDisplayName, routeDurationSec) {
    if (!smoothP2 || smoothP2.length < 2) {
        isAmbulanceEnRoute = false;
        return;
    }
    if (ambulanceAnimId) cancelAnimationFrame(ambulanceAnimId);
    ambulanceAnimId = null;
    if (phaseTransitionTimeout) {
        clearTimeout(phaseTransitionTimeout);
        phaseTransitionTimeout = null;
    }

    const ambIcon = L.divIcon({
        html: `<div style="font-size:34px;filter:drop-shadow(0 0 14px rgba(34,197,94,0.95))">🚑</div>`,
        className: '',
        iconSize: [36, 36],
        iconAnchor: [18, 18]
    });
    if (ambulanceMarker) ambulanceMarker.setIcon(ambIcon);

    const p2Total = smoothP2.length;
    const phase2DurationMs = getSimulatedTravelDurationMs(smoothP2, routeDurationSec, 45);
    const phase2StepMs = Math.max(16, phase2DurationMs / (p2Total - 1));
    const p2DistanceKm = getPathDistanceKm(smoothP2);
    const phase2SpeedKmh = routeDurationSec > 0 ? p2DistanceKm / (routeDurationSec / 3600) : 45;
    let idx = 0, lastT = 0, trailCt = 0;

    currentMissionPhase = 'en_route_to_hospital';
    syncMissionPhaseToBackend('en_route_to_hospital', smoothP2[0][0], smoothP2[0][1], phase2SpeedKmh, true);
    updateStatus('simDot', 'g', 'simText', `Transporting to ${hospitalName}`);
    if (typeof logMissionMilestone === 'function') {
        logMissionMilestone(getTimestamp(), `🚨 Emergency Transport Phase`, `Green Priority Corridor active to ${hospitalName}.`, 'success');
    }

    function tickPhase2(ts) {
        if (idx >= p2Total) {
            // Arrival at Hospital ER
            const endPt = smoothP2[p2Total - 1];
            ambulanceMarker.setLatLng(endPt);
            ambulanceMarker.setIcon(L.divIcon({
                html: '<div style="font-size:36px;filter:drop-shadow(0 0 22px #22c55e)">🏥</div>',
                className: '',
                iconSize: [40, 40],
                iconAnchor: [20, 20]
            }));

            const arrivalCircle = L.circle(endPt, {
                radius: 120, fillColor: '#22c55e', fillOpacity: 0.25,
                color: '#22c55e', weight: 2, opacity: 0.8
            }).addTo(leafletMap);
            trailMarkers.push(arrivalCircle);

            isAmbulanceEnRoute = false;
            currentMissionPhase = 'arrived';
            syncMissionPhaseToBackend('arrived', endPt[0], endPt[1], 0, true);
            updateStatus('simDot', 'g', 'simText', `Patient Admitted: ${hospitalName}`);
            updateVehicleHUD(true, unitDisplayName, ambId, `Phase 2 Complete: Patient Admitted at ${hospitalName}`, 0, 0.0, endPt[0], endPt[1], 'Arrived / ER Handover');

            if (typeof logMissionMilestone === 'function') {
                logMissionMilestone(getTimestamp(), `🏥 Patient Delivered`, `Emergency Handover Complete at ${hospitalName} ER Department.`, 'success');
            }
            if (typeof refreshAuditTelemetry === 'function') {
                refreshAuditTelemetry();
            }
            return;
        }

        if (ts - lastT < phase2StepMs) {
            ambulanceAnimId = requestAnimationFrame(tickPhase2);
            return;
        }
        lastT = ts;

        const curPt = smoothP2[idx];
        const distRem = getPathDistanceKm(smoothP2, idx);
        const speed = phase2SpeedKmh;

        if (ambulanceMarker) {
            ambulanceMarker.setLatLng(curPt);
        }
        window.ambLat = curPt[0];
        window.ambLng = curPt[1];
        syncMissionPhaseToBackend('en_route_to_hospital', curPt[0], curPt[1], speed, false);

        updateVehicleHUD(true, unitDisplayName, ambId, `Phase 2: Transporting Patient to ${hospitalName}`, speed, distRem, curPt[0], curPt[1], `Simulation playback ×${SIMULATION_TIME_SCALE}`);

        // Green Priority Corridor Trail
        trailCt++;
        if (trailCt % 5 === 0) {
            const dot = L.circleMarker(curPt, {
                radius: 3, fillColor: '#22c55e', fillOpacity: 0.85,
                stroke: false
            }).addTo(leafletMap);
            trailMarkers.push(dot);
            setTimeout(() => { try { leafletMap.removeLayer(dot); } catch(e){} }, 4000);
        }

        idx += 1;
        ambulanceAnimId = requestAnimationFrame(tickPhase2);
    }

    ambulanceAnimId = requestAnimationFrame(tickPhase2);
}

// Single path fallback
function animateAmbulance(path) {
    if (!path || path.length < 2) return;
    const smooth = interpolatePath(path, 200);
    startPhase2(smooth, "Healthcare Facility", "AMB-01", "Rapid Response Unit Alpha");
}

function clearAnimation() {
    if (ambulanceAnimId) cancelAnimationFrame(ambulanceAnimId);
    ambulanceAnimId = null;
    if (phaseTransitionTimeout) clearTimeout(phaseTransitionTimeout);
    phaseTransitionTimeout = null;
    currentMissionPhase = 'idle';
    if (ambulanceMarker) {
        try { leafletMap.removeLayer(ambulanceMarker); } catch(e){}
        ambulanceMarker = null;
    }
    trailMarkers.forEach(t => { try { leafletMap.removeLayer(t); } catch(e){} });
    trailMarkers = [];
    updateVehicleHUD(false);
}
