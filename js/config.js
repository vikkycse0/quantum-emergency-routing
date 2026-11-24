// ═══════════════════════════════════════
// AERT (AI EMERGENCY ROUTING & TRACKING) — CONFIG
// Unified Server & Standalone Compatible
// ═══════════════════════════════════════

function resolveBackendApiBase() {
    if (window.location.protocol === 'file:') {
        return 'http://127.0.0.1:8001/api';
    }
    const port = window.location.port;
    if (port === '8001' || port === '' || port === '80' || port === '443') {
        return `${window.location.origin}/api`;
    }
    return `${window.location.protocol}//${window.location.hostname}:8001/api`;
}

const CONFIG = {
    BACKEND_API_BASE: resolveBackendApiBase(),
    SEARCH_RADIUS_M: 25000,
    ANIMATION_DELAY_MS: 90,
    TRAIL_INTERVAL_STEPS: 5,
    MAX_ANIM_STEPS: 350,
    DEFAULT_LOCATION: {
        lat: 17.7046,
        lng: 83.2926,
        name: 'Visakhapatnam (Demo Base Station)'
    },
    OVERPASS_MIRRORS: [
        'https://overpass-api.de/api/interpreter',
        'https://lz4.overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter'
    ]
};
