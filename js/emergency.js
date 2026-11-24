// ============================================================
// EMERGENCY MODULE — Authoritative Location & Emergency State
// ============================================================

// Single authoritative location state — never silently replaced
let currentLocation = {
    latitude: null,
    longitude: null,
    accuracy: null,
    timestamp: null,
    source: 'uninitialized'
    // source values: 'browser-gps' | 'phone-gps' | 'manual' | 'demo'
};

let currentEmergencyType = 'Cardiac Emergency';
let currentSeverity = 'CRITICAL';
let currentSolverMode = 'topsis';
let activeCaseId = null;

function onSolverModeChange(mode) {
    currentSolverMode = (mode || 'topsis').toLowerCase();
    const labels = {
        topsis: 'TOPSIS route optimizer ready',
        ilp: 'ILP exact solver ready',
        qaoa: 'QAOA quantum simulator ready',
        qubo: 'QUBO solver ready'
    };
    updateStatus('simDot', 'p', 'simText', labels[currentSolverMode] || 'Route optimizer ready');
}

const EMERGENCY_TYPES = {
    'Cardiac Emergency':      { severity: 'CRITICAL', requiredCap: 'ALS + Cardiac Unit' },
    'Stroke':                 { severity: 'CRITICAL', requiredCap: 'ALS Neuro Unit' },
    'Accident / Trauma':      { severity: 'CRITICAL', requiredCap: 'ALS Trauma Unit' },
    'Severe Bleeding':        { severity: 'CRITICAL', requiredCap: 'ALS Trauma Unit' },
    'Respiratory Emergency':  { severity: 'HIGH',     requiredCap: 'ALS + Ventilator' },
    'Burn':                   { severity: 'HIGH',     requiredCap: 'ALS + Burn Unit' },
    'Fracture':               { severity: 'MEDIUM',   requiredCap: 'BLS Response Unit' },
    'General Emergency':      { severity: 'MEDIUM',   requiredCap: 'BLS Unit' }
};

function updateLocationState(lat, lng, accuracy, source) {
    // Strict null check — never fall back silently
    if (lat === null || lat === undefined || lng === null || lng === undefined) {
        console.warn('[LOCATION] updateLocationState called with null coordinates. Ignoring.');
        return;
    }

    currentLocation = {
        latitude: lat,
        longitude: lng,
        accuracy: accuracy !== null && accuracy !== undefined ? accuracy : null,
        timestamp: new Date().toISOString(),
        source: source
    };

    // Mirror to legacy window globals for map/routing modules
    window.userLat = lat;
    window.userLng = lng;

    console.log(`[LOCATION SOURCE] ${currentLocation.source}`);
    console.log(`[USER GPS] ${currentLocation.latitude} , ${currentLocation.longitude}`);
    console.log(`[GPS ACCURACY] ${currentLocation.accuracy !== null ? currentLocation.accuracy + 'm' : 'unknown'}`);

    // Update UI panels
    const latEl  = document.getElementById('uLat');
    const lngEl  = document.getElementById('uLng');
    const accEl  = document.getElementById('uAcc');
    const statusEl = document.getElementById('uStatus');
    const gpsDot   = document.getElementById('gpsDot');
    const gpsText  = document.getElementById('gpsText');
    const modeBadge = document.getElementById('modeBadge');

    if (latEl) latEl.textContent = lat.toFixed(6);
    if (lngEl) lngEl.textContent = lng.toFixed(6);

    if (source === 'browser-gps') {
        const accM = accuracy !== null ? Math.round(accuracy) + 'm' : 'GPS Signal';
        if (accEl) accEl.textContent = `${accM} (Browser Geolocation)`;
        if (statusEl) statusEl.innerHTML = '<span style="color:#22c55e">GPS Locked — Browser Geolocation</span>';
        if (gpsDot) gpsDot.className = 'dot g';
        if (gpsText) gpsText.textContent = 'GPS Active';
        if (modeBadge) {
            modeBadge.className = 'mode-badge-live';
            modeBadge.innerHTML = '<span class="dot g"></span>LIVE GPS MODE';
        }

    } else if (source === 'phone-gps') {
        const accM = accuracy !== null ? Math.round(accuracy) + 'm' : 'SOS Transmitted';
        if (accEl) accEl.textContent = `${accM} (Mobile SOS)`;
        if (statusEl) statusEl.innerHTML = '<span style="color:#38bdf8">SOS Received — Mobile GPS</span>';
        if (gpsDot) gpsDot.className = 'dot b';
        if (gpsText) gpsText.textContent = 'SOS GPS';
        if (modeBadge) {
            modeBadge.className = 'mode-badge-live';
            modeBadge.innerHTML = '<span class="dot r"></span>MOBILE SOS LIVE';
        }

    } else if (source === 'manual') {
        if (accEl) accEl.textContent = 'Manual Pin Drag (User Adjusted)';
        if (statusEl) statusEl.innerHTML = '<span style="color:#38bdf8">Manual Position — Dragged Pin</span>';
        if (gpsDot) gpsDot.className = 'dot b';
        if (gpsText) gpsText.textContent = 'Manual Pin';
        if (modeBadge) {
            modeBadge.className = 'badge badge-medium';
            modeBadge.innerHTML = '📍 MANUAL PIN';
        }

    } else if (source === 'demo') {
        if (accEl) accEl.textContent = 'Demo Simulation Base (Visakhapatnam)';
        if (statusEl) statusEl.innerHTML = '<span style="color:#fbbf24">DEMO LOCATION ACTIVE — Simulation Only</span>';
        if (gpsDot) gpsDot.className = 'dot y';
        if (gpsText) gpsText.textContent = 'Demo Mode';
        if (modeBadge) {
            modeBadge.className = 'badge badge-demo';
            modeBadge.innerHTML = '🟣 SIMULATION MODE';
        }
    }
}

function onEmergencyTypeChange(type) {
    currentEmergencyType = type;
    const info = EMERGENCY_TYPES[type] || { severity: 'MEDIUM' };
    currentSeverity = info.severity;

    const sevBadge = document.getElementById('uSeverity');
    if (sevBadge) {
        sevBadge.textContent = currentSeverity;
        sevBadge.className = `badge badge-${currentSeverity.toLowerCase()}`;
    }

    // Re-evaluate hospitals for new emergency type if location is known
    if (currentLocation.latitude !== null && currentLocation.longitude !== null) {
        findHospitals(currentLocation.latitude, currentLocation.longitude);
    }
}

async function transmitSOSToBackend(lat, lng, accuracy, source, phone) {
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/sos_trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userLat: lat,
                userLng: lng,
                accuracy: accuracy,
                source: source || 'browser-gps',
                emergency_type: currentEmergencyType,
                severity: currentSeverity,
                caller_phone: phone || '+91-98765-43210'
            })
        });

        if (res.ok) {
            const data = await res.json();
            activeCaseId = data.case_id;
            const caseDom = document.getElementById('uCaseId');
            if (caseDom) caseDom.textContent = `#${activeCaseId}`;
            return data;
        }
    } catch (e) {
        console.warn('[SOS] Backend transmission offline:', e);
    }
    return null;
}
