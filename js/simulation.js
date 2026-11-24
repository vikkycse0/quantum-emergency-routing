// ═══════════════════════════════════════
// SIMULATION / DEMO MODULE — Faculty Presentation Control
// ═══════════════════════════════════════

let isDemoModeActive = false;
let simulationEvents = [];

function toggleDemoMode() {
    isDemoModeActive = !isDemoModeActive;
    const panel = document.getElementById('demoControlPanel');
    if (panel) panel.style.display = isDemoModeActive ? 'block' : 'none';

    if (isDemoModeActive) {
        updateStatus('simDot', 'y', 'simText', 'Simulation Stress-Test Panel Open');
    } else {
        onSolverModeChange(typeof currentSolverMode !== 'undefined' ? currentSolverMode : 'topsis');
    }
}

async function triggerSimulationEvent(eventType, factor, locationName) {
    const route = typeof currentActiveRoute !== 'undefined' ? currentActiveRoute : null;
    const routePath = route && Array.isArray(route.path) ? route.path : [];
    let eventLocation = null;
    if (routePath.length > 0) {
        eventLocation = routePath[Math.floor((routePath.length - 1) / 2)];
    } else if (currentLocation.latitude !== null && currentLocation.longitude !== null) {
        eventLocation = [currentLocation.latitude, currentLocation.longitude];
    }

    if (!eventLocation) {
        updateStatus('simDot', 'r', 'simText', 'Set a location before injecting an event');
        return;
    }

    const logBox = document.getElementById('demoEventLog');
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/simulation/event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                eventType: eventType,
                severityFactor: factor,
                locationName: locationName,
                lat: eventLocation[0],
                lng: eventLocation[1]
            })
        });
        if (!res.ok) {
            const error = await res.json().catch(() => null);
            throw new Error(error && error.detail ? error.detail : `Event API returned HTTP ${res.status}`);
        }

        if (logBox) {
            const entry = document.createElement('div');
            entry.style.cssText = 'margin-top:4px;color:#fbbf24';
            entry.textContent = `Event injected: ${eventType} at ${locationName} (${factor}x)`;
            logBox.appendChild(entry);
            logBox.scrollTop = logBox.scrollHeight;
        }
        logMissionMilestone(getTimestamp(), 'Hazard Injected', `${eventType} (${factor}x) near active route`, 'danger');

        if (isAmbulanceEnRoute) setTimeout(checkDynamicReroute, 800);
    } catch (e) {
        console.warn("Simulation API offline:", e);
        updateStatus('simDot', 'r', 'simText', `Simulation event failed: ${e.message}`);
    }
}

async function resetSimulationSession() {
    const logBox = document.getElementById('demoEventLog');
    try {
        const res = await fetch(`${CONFIG.BACKEND_API_BASE}/simulation/start`, { method: 'POST' });
        if (!res.ok) throw new Error(`Simulation reset returned HTTP ${res.status}`);
        if (logBox) logBox.textContent = 'Simulation reset. Ready for events.';
        resetAll();
        if (leafletMap) renderIncidentMarkers([]);
        if (currentLocation.latitude !== null && currentLocation.longitude !== null) {
            await loadFleetStations(currentLocation.latitude, currentLocation.longitude);
        }
        updateStatus('simDot', 'g', 'simText', 'Simulation reset');
    } catch (e) {
        console.error('[SIMULATION RESET ERROR]', e);
        updateStatus('simDot', 'r', 'simText', `Simulation reset failed: ${e.message}`);
    }
}
