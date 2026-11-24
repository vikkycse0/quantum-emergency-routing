// ============================================================
// APP — Main Dashboard Controller & Geolocation Engine
// QERI (Quantum Emergency Routing Intelligence)
// ============================================================

let isMapLive = false;

function initApp() {
    updateStatus('weatherDot', 'b', 'weatherText', 'Connecting Weather API...');

    document.getElementById('overlayText').innerHTML =
        'Requesting Browser GPS & Connecting Live Telemetry...<br><br>' +
        '<span style="font-size:12px;color:#94a3b8;">Please allow location access when prompted.</span>';

    logMissionMilestone(getTimestamp(), 'System Initialized', 'Connecting Open-Meteo & OSRM Providers', 'info');

    checkBackendHealth();
    refreshAuditTelemetry();
    acquireBrowserGPS();
    startPhoneListener();
    startIncidentPolling();
}

function getTimestamp() {
    const d = new Date();
    return d.toTimeString().split(' ')[0];
}

function logMissionMilestone(timeLabel, title, detail, type = 'info') {
    const timeline = document.getElementById('missionTimeline');
    if (!timeline) return;

    const node = document.createElement('div');
    node.className = `timeline-node ${type}`;
    node.innerHTML = `
        <div class="timeline-time">${escapeHTML(timeLabel)}</div>
        <div class="timeline-title">${escapeHTML(title)}</div>
        <div class="timeline-desc">${escapeHTML(detail)}</div>
    `;
    timeline.appendChild(node);
    timeline.scrollTop = timeline.scrollHeight;
}

// ── GPS ACQUISITION ──────────────────────────────────────────

function acquireBrowserGPS() {
    if (!('geolocation' in navigator)) {
        handleLocationFailure('Geolocation API is not supported by this browser.');
        return;
    }

    navigator.geolocation.getCurrentPosition(
        onGPSSuccess,
        onGPSError,
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
}

function onGPSSuccess(pos) {
    const lat = pos.coords.latitude;
    const lng = pos.coords.longitude;
    const acc = pos.coords.accuracy;

    console.log(`[REAL GPS] Acquired: (${lat}, ${lng}) accuracy=${acc}m`);
    logMissionMilestone(getTimestamp(), 'GPS Locked', `Coordinates: (${lat.toFixed(4)}, ${lng.toFixed(4)}) ±${Math.round(acc)}m`, 'success');

    // Set authoritative location state
    updateLocationState(lat, lng, acc, 'browser-gps');

    if (!isMapLive) {
        isMapLive = true;
        initMap(lat, lng);
    } else {
        userMarker.setLatLng([lat, lng]);
        leafletMap.setView([lat, lng], 14);
        loadFleetStations(lat, lng);
    }

    findHospitals(lat, lng);
    fetchLiveWeatherTelemetry(lat, lng);
    hideOverlay();
}

function onGPSError(err) {
    let errorMsg = 'Unable to acquire GPS location.';
    switch (err.code) {
        case err.PERMISSION_DENIED:
            errorMsg = 'Location permission denied. Please enable location access in your browser settings.';
            break;
        case err.POSITION_UNAVAILABLE:
            errorMsg = 'GPS unavailable. Device location services may be disabled.';
            break;
        case err.TIMEOUT:
            errorMsg = 'GPS acquisition timed out. Location signal did not respond in time.';
            break;
    }
    console.warn(`[GPS ERROR] ${err.code}: ${err.message}`);
    logMissionMilestone(getTimestamp(), 'GPS Failed', errorMsg, 'danger');
    handleLocationFailure(errorMsg);
}

function handleLocationFailure(reason) {
    const overlayText = document.getElementById('overlayText');
    if (overlayText) {
        overlayText.innerHTML = `
            <div style="color:#f87171;font-weight:700;font-size:14px;margin-bottom:8px">GPS Acquisition Failed</div>
            <div style="color:#cbd5e1;font-size:12px;margin-bottom:16px;line-height:1.4">${reason}</div>
            <button class="btn btn-main" onclick="useDemoLocation()"
                style="background:#f59e0b;border-color:#f59e0b;padding:8px 16px;font-size:12px;width:auto">
                📍 Use Demo Location (Simulation Mode)
            </button>
            <div style="font-size:11px;color:#94a3b8;margin-top:10px">
                Or drag the patient pin manually on the map.
            </div>
        `;
    }

    const gpsDot  = document.getElementById('gpsDot');
    const gpsText = document.getElementById('gpsText');
    const statusEl = document.getElementById('uStatus');
    const accEl    = document.getElementById('uAcc');
    if (gpsDot)  gpsDot.className = 'dot r';
    if (gpsText) gpsText.textContent = 'GPS Offline';
    if (statusEl) statusEl.innerHTML = '<span style="color:#ef4444">GPS Unavailable</span>';
    if (accEl)   accEl.textContent = 'Unavailable';
}

// ── LIVE WEATHER TELEMETRY ─────────────────────────────────────

async function fetchLiveWeatherTelemetry(lat, lng) {
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/weather/live?lat=${lat}&lng=${lng}`);
        if (!res.ok) throw new Error(`Weather API returned HTTP ${res.status}`);
        const data = await res.json();
        const w = data.weather;
        const weatherText = document.getElementById('weatherText');
        const weatherDot = document.getElementById('weatherDot');
        if (weatherText) {
            weatherText.textContent = `Weather: ${w.temperature_c}°C ${w.weather_condition} (${w.provenance})`;
        }
        if (weatherDot) {
            weatherDot.className = w.is_severe ? 'dot y' : 'dot g';
        }
        logMissionMilestone(getTimestamp(), 'Live Weather Sync', `${w.temperature_c}°C · ${w.weather_condition} · Rain: ${w.rain_mm}mm · Source: ${w.source}`, 'info');
    } catch (e) {
        console.warn('[WEATHER ERROR]', e);
        updateStatus('weatherDot', 'y', 'weatherText', 'Weather unavailable');
    }
}

// ── LIVE INCIDENT POLLING ──────────────────────────────────────

function startIncidentPolling() {
    setInterval(async () => {
        try {
            const res = await fetch(`${CONFIG.BACKEND_API_BASE}/traffic/incidents`);
            if (res.ok) {
                const data = await res.json();
                if (typeof renderIncidentMarkers === 'function') {
                    renderIncidentMarkers(data.incidents || []);
                }
            }
        } catch(e) {}
    }, 4000);
}

// ── DEMO MODE — Explicit user action only ─────────────────────

function useDemoLocation() {
    hideOverlay();
    const demo = CONFIG.DEFAULT_LOCATION;
    console.log(`[DEMO MODE] Activated: (${demo.lat}, ${demo.lng})`);

    const modeBadge = document.getElementById('modeBadge');
    if (modeBadge) {
        modeBadge.className = 'badge badge-demo';
        modeBadge.innerHTML = '🟣 SIMULATION MODE';
    }

    updateLocationState(demo.lat, demo.lng, 50, 'demo');
    logMissionMilestone(getTimestamp(), 'Simulation Mode Active', `Demo Location (${demo.lat}, ${demo.lng}) loaded.`, 'quantum');

    if (!isMapLive) {
        isMapLive = true;
        initMap(demo.lat, demo.lng);
    } else {
        userMarker.setLatLng([demo.lat, demo.lng]);
        leafletMap.setView([demo.lat, demo.lng], 14);
        loadFleetStations(demo.lat, demo.lng);
    }

    findHospitals(demo.lat, demo.lng);
    fetchLiveWeatherTelemetry(demo.lat, demo.lng);
}

function hideOverlay() {
    const overlay = document.getElementById('overlay');
    if (overlay) overlay.classList.add('hide');
}

// ── BACKEND HEALTH ────────────────────────────────────────────

async function checkBackendHealth() {
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/health`);
        if (!res.ok) throw new Error(`Health API returned HTTP ${res.status}`);
        await res.json();
        updateStatus('simDot', 'p', 'simText', 'TOPSIS route optimizer ready');
    } catch (e) {
        console.warn('[BACKEND HEALTH ERROR]', e);
        updateStatus('simDot', 'y', 'simText', 'Backend Standby');
    }
}

// ── MOBILE SOS LISTENER ───────────────────────────────────────

function startPhoneListener() {
    setInterval(async () => {
        try {
            const res = await fetch(`${CONFIG.BACKEND_API_BASE}/poll_sos`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.status !== 'incoming_call') return;

            const call = data.data;
            console.log('[SOS INTERCEPTED]', call);

            const lat = call.latitude !== null && call.latitude !== undefined ? call.latitude : null;
            const lng = call.longitude !== null && call.longitude !== undefined ? call.longitude : null;

            if (lat === null || lng === null) return;

            const acc    = call.accuracy !== null && call.accuracy !== undefined ? call.accuracy : null;
            const source = call.source || 'phone-gps';

            activeCaseId = call.case_id || null;
            const caseDom = document.getElementById('uCaseId');
            if (caseDom && activeCaseId) caseDom.textContent = `#${activeCaseId}`;

            if (call.emergency_type) {
                const sel = document.getElementById('emergencyTypeSelect');
                if (sel) sel.value = call.emergency_type;
                currentEmergencyType = call.emergency_type;
            }

            logMissionMilestone(getTimestamp(), `🚨 SOS Received (Case #${activeCaseId})`, `${currentEmergencyType} at (${lat.toFixed(4)}, ${lng.toFixed(4)})`, 'danger');

            updateLocationState(lat, lng, acc, source);

            if (!isMapLive) {
                isMapLive = true;
                initMap(lat, lng);
                findHospitals(lat, lng);
            } else {
                userMarker.setLatLng([lat, lng]);
                leafletMap.setView([lat, lng], 15);
                findHospitals(lat, lng);
                loadFleetStations(lat, lng);
            }

            setTimeout(() => { callAmbulanceAuto(); }, 1000);
        } catch (e) {}
    }, 2000);
}

// ── HELPER & RESET ────────────────────────────────────────────

async function refreshAuditTelemetry() {
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/audit/cases?limit=5`);
        if (!res.ok) return;
        const data = await res.json();
        const stats = data.analytics || {};
        const cases = data.cases || [];

        const statsEl = document.getElementById('auditStatsGrid');
        if (statsEl) {
            statsEl.innerHTML = `
                <div class="loc-cell"><div class="lbl">Cases</div><div class="val">${stats.total_emergencies_recorded ?? 0}</div></div>
                <div class="loc-cell"><div class="lbl">Dispatches</div><div class="val">${stats.total_dispatches_completed ?? 0}</div></div>
                <div class="loc-cell"><div class="lbl">Avg Gain</div><div class="val">${stats.average_qubo_optimization_gain_pct ?? 0}%</div></div>
                <div class="loc-cell"><div class="lbl">Reroutes</div><div class="val">${stats.total_dynamic_reroutes_executed ?? 0}</div></div>
            `;
        }

        const listEl = document.getElementById('auditRecentList');
        if (listEl) {
            if (cases.length === 0) {
                listEl.innerHTML = '<div style="font-size:10px;color:var(--text-dim)">No dispatches recorded yet.</div>';
            } else {
                listEl.innerHTML = cases.map(c => `
                    <div class="compare-row" style="font-size:10px">
                        <span style="font-family:monospace;color:var(--accent)">#${escapeHTML(c.case_id)}</span>
                        <span style="color:var(--text)">${escapeHTML(c.ambulance_id || 'Pending')}</span>
                        <span style="color:#86efac">${c.total_mission_eta_sec ? (c.total_mission_eta_sec / 60).toFixed(1) + 'm' : escapeHTML(c.status)}</span>
                    </div>
                `).join('');
            }
        }
    } catch (e) {}
}

function resetAll() {
    clearRoutePolylines();
    clearAnimation();
    const routesCard = document.getElementById('routesCard');
    const rightPanel = document.getElementById('rpanel');
    const aiPanel = document.getElementById('aiPanel');
    const benchCard = document.getElementById('solverComparisonCard');
    const calcBtn = document.getElementById('calcBtn');
    const timeline = document.getElementById('missionTimeline');
    if (routesCard) routesCard.style.display = 'none';
    if (rightPanel) rightPanel.style.display = 'none';
    if (aiPanel) aiPanel.style.display = 'none';
    if (benchCard) benchCard.style.display = 'none';
    if (calcBtn) {
        calcBtn.disabled = true;
        calcBtn.textContent = '⚡ Calculate Road Corridors & Optimize';
    }
    if (timeline) {
        timeline.innerHTML = '';
        logMissionMilestone(getTimestamp(), 'Session Reset', 'Ready for next emergency dispatch.', 'info');
    }
    selectedHosp = null;
    isAmbulanceEnRoute = false;
    currentActiveRoute = null;
    activeCaseId = null;
    const caseDom = document.getElementById('uCaseId');
    if (caseDom) caseDom.textContent = '#DEMO-CASE';
    if (typeof currentHospitals !== 'undefined' && currentHospitals.length > 0) {
        selectHospital(0);
    }
    onSolverModeChange(typeof currentSolverMode !== 'undefined' ? currentSolverMode : 'topsis');
}
