// ============================================================
// MAP MODULE — Leaflet Map Engine & Telemetry Overlays
// ============================================================

let leafletMap, currentTileLayer;
let userMarker;
let hospitalMarkers = [];
let fleetStationMarkers = [];
let fleetMarkersById = {};
let incidentMarkers = [];
let routePolylines = [];

const TILES = {
    dark:      { url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', attr: '© OpenStreetMap contributors', className: 'aert-dark-tiles' },
    satellite: { url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr: '© Esri' },
    street:    { url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', attr: '© OpenStreetMap contributors' }
};

function initMap(lat, lng) {
    console.log(`[MAP INIT] Centering map at (${lat}, ${lng}) — source: ${currentLocation.source}`);

    window.userLat = lat;
    window.userLng = lng;

    leafletMap = L.map('map', {
        center: [lat, lng],
        zoom: 14,
        zoomControl: true,
        attributionControl: true
    });

    currentTileLayer = createTileLayer('dark').addTo(leafletMap);

    // Patient marker — pulsing locator
    const userIcon = L.divIcon({
        html: `<div style="
            width:22px;height:22px;border-radius:50%;
            background:radial-gradient(circle,#38bdf8 30%,#1d4ed8 100%);
            border:3px solid rgba(255,255,255,0.95);
            box-shadow:0 0 14px rgba(56,189,248,0.8),0 0 28px rgba(56,189,248,0.4);
            animation:userPulse 2s ease-in-out infinite;
        "></div>
        <style>@keyframes userPulse{0%,100%{box-shadow:0 0 10px rgba(56,189,248,0.7)}50%{box-shadow:0 0 28px rgba(56,189,248,1)}}</style>`,
        className: '',
        iconSize: [22, 22],
        iconAnchor: [11, 11]
    });

    userMarker = L.marker([lat, lng], { icon: userIcon, draggable: true, zIndexOffset: 2000 }).addTo(leafletMap);
    userMarker.bindPopup('<div style="font-size:12px"><strong>👤 Patient / Incident Location</strong><br><span style="color:#888">Drag to adjust coordinates</span></div>').openPopup();

    userMarker.on('dragend', function () {
        const pos = userMarker.getLatLng();
        console.log(`[MANUAL PIN] User dragged pin to (${pos.lat.toFixed(6)}, ${pos.lng.toFixed(6)})`);
        updateLocationState(pos.lat, pos.lng, null, 'manual');
        findHospitals(pos.lat, pos.lng);
        loadFleetStations(pos.lat, pos.lng);
        if (typeof logMissionMilestone === 'function') {
            logMissionMilestone(getTimestamp(), 'Incident Relocated', `Manual coordinates: (${pos.lat.toFixed(4)}, ${pos.lng.toFixed(4)})`, 'info');
        }
    });

    updateStatus('mapDot', 'g', 'mapText', 'Map Active');
    loadFleetStations(lat, lng);
}

async function loadFleetStations(lat, lng) {
    try {
        const curLat = lat !== undefined ? lat : (currentLocation.latitude !== null ? currentLocation.latitude : window.userLat);
        const curLng = lng !== undefined ? lng : (currentLocation.longitude !== null ? currentLocation.longitude : window.userLng);

        const url = (curLat !== null && curLng !== null)
            ? `${CONFIG.BACKEND_API_BASE}/ambulances?lat=${curLat}&lng=${curLng}`
            : `${CONFIG.BACKEND_API_BASE}/ambulances`;

        const res = await fetch(url);
        if (!res.ok) return;
        const fleet = await res.json();

        fleetStationMarkers.forEach(m => leafletMap.removeLayer(m));
        fleetStationMarkers = [];
        fleetMarkersById = {};

        fleet.forEach(amb => {
            const icon = L.divIcon({
                html: `<div style="padding:2px 5px;background:rgba(15,23,42,0.9);border:1px solid rgba(34,197,94,0.5);border-radius:4px;font-size:9px;color:#4ade80;font-weight:700;white-space:nowrap">${escapeHTML(amb.ambulance_id)}</div>`,
                className: '',
                iconAnchor: [16, 10]
            });
            const m = L.marker([amb.latitude, amb.longitude], { icon, zIndexOffset: 200 }).addTo(leafletMap);
            m.bindPopup(`<strong>${escapeHTML(amb.name)}</strong><br>Equipment: ${escapeHTML(amb.capabilities.join(', '))}<br>Status: <em>${escapeHTML(amb.status)}</em>`);
            fleetStationMarkers.push(m);
            fleetMarkersById[amb.ambulance_id] = m;
        });
    } catch (e) {
        console.warn('[FLEET MAP ERROR]', e);
    }
}

function placeHospitalMarkers(hospitals) {
    hospitalMarkers.forEach(m => leafletMap.removeLayer(m));
    hospitalMarkers = [];

    hospitals.forEach((h, i) => {
        const isTop = i === 0;
        const color = isTop ? '#a855f7' : (h.isOpen === true ? '#22c55e' : '#3b82f6');
        const size  = isTop ? 16 : 12;

        const icon = L.divIcon({
            html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid rgba(255,255,255,0.9);box-shadow:0 0 10px ${color}80;"></div>`,
            className: '',
            iconSize: [size, size],
            iconAnchor: [size/2, size/2]
        });
        const marker = L.marker([h.lat, h.lng], { icon, zIndexOffset: 100 + i }).addTo(leafletMap);
        marker.hospitalId = h.id;

        const openHtml = h.isOpen === true ? '🟢 24×7 Emergency' : (h.isOpen === false ? '⚪ Not 24×7' : '⚪ Hours Unverified');
        marker.bindPopup(`<div style="font-size:12px;max-width:200px">
            <strong>🏥 ${escapeHTML(h.name)}</strong><br>
            <span style="color:#888">${escapeHTML(h.vicinity)}</span><br>
            Distance: <strong>${h.dist.toFixed(1)} km</strong><br>
            ${openHtml}<br>
            Source: <em>${escapeHTML(h.source)}</em>
        </div>`);

        if (i < 6) {
            const label = L.marker([h.lat, h.lng], {
                icon: L.divIcon({
                    html: `<div style="background:rgba(8,12,20,0.85);color:#fff;padding:2px 5px;border-radius:4px;font-size:9px;white-space:nowrap;border:1px solid ${color}80;transform:translateY(-18px)">${escapeHTML(h.name)}</div>`,
                    className: '',
                    iconAnchor: [0, 0]
                }),
                zIndexOffset: 50 + i
            }).addTo(leafletMap);
            hospitalMarkers.push(label);
        }

        marker.on('click', () => selectHospitalById(h.id));
        hospitalMarkers.push(marker);
    });
}

function renderIncidentMarkers(incidents) {
    if (!leafletMap) return;

    incidentMarkers.forEach(m => leafletMap.removeLayer(m));
    incidentMarkers = [];

    const icons = {
        'ACCIDENT': '💥',
        'ROAD_CLOSURE': '⛔',
        'ROAD_WORK': '🚧',
        'FLOOD': '🌊',
        'HAZARD': '⚠'
    };

    incidents.forEach(inc => {
        const iconChar = icons[inc.type] || '⚠';
        const icon = L.divIcon({
            html: `<div style="font-size:22px;filter:drop-shadow(0 0 6px rgba(239,68,68,0.8))">${iconChar}</div>`,
            className: '',
            iconAnchor: [11, 11]
        });

        const marker = L.marker([inc.latitude, inc.longitude], { icon, zIndexOffset: 3000 }).addTo(leafletMap);
        marker.bindPopup(`
            <div style="font-size:11px;max-width:210px">
                <strong style="color:#f87171">⚠ ${escapeHTML(inc.type)}</strong><br>
                <span>${escapeHTML(inc.description)}</span><br>
                Delay Impact: <strong>+${Math.round(inc.estimated_delay_sec/60)} mins</strong><br>
                <div style="font-size:9px;color:#94a3b8;margin-top:3px">Source: ${escapeHTML(inc.source)}</div>
            </div>
        `);
        incidentMarkers.push(marker);
    });
}

function fitMapBounds(points) {
    if (!leafletMap || !points || points.length === 0) return;

    const userLat = currentLocation.latitude !== null ? currentLocation.latitude : window.userLat;
    const userLng = currentLocation.longitude !== null ? currentLocation.longitude : window.userLng;

    if (userLat === null || userLat === undefined) return;

    // Filter points to only those within 25 km of actual user location
    const nearby = points.filter(p => {
        const d = haversine(userLat, userLng, p.lat, p.lng);
        return d <= 25.0;
    });

    if (nearby.length === 0) return;

    const bounds = L.latLngBounds(nearby.map(p => [p.lat, p.lng]));
    leafletMap.fitBounds(bounds, { padding: [60, 60], maxZoom: 15 });
}

function clearRoutePolylines() {
    routePolylines.forEach(p => leafletMap.removeLayer(p));
    routePolylines = [];
}

function drawRoute(path, color, weight, opacity, dashArray) {
    const line = L.polyline(path, {
        color, weight, opacity,
        dashArray: dashArray || null,
        lineCap: 'round',
        lineJoin: 'round'
    }).addTo(leafletMap);
    routePolylines.push(line);
    return path;
}

function switchTile(type, btn) {
    if (!TILES[type] || !leafletMap) return;
    document.querySelectorAll('.map-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    if (currentTileLayer) leafletMap.removeLayer(currentTileLayer);
    currentTileLayer = createTileLayer(type).addTo(leafletMap);
}

function createTileLayer(type) {
    const tile = TILES[type];
    return L.tileLayer(tile.url, {
        maxZoom: 19,
        attribution: tile.attr,
        className: tile.className || ''
    });
}
