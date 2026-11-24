// ============================================================
// UTILITIES — Helpers, Distance, Status, and Path Interpolation
// ============================================================

// Haversine distance in kilometers
function haversine(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Calculate bearing / heading in degrees between two points
function calculateBearing(lat1, lng1, lat2, lng2) {
    const dLon = (lng2 - lng1) * Math.PI / 180;
    const y = Math.sin(dLon) * Math.cos(lat2 * Math.PI / 180);
    const x = Math.cos(lat1 * Math.PI / 180) * Math.sin(lat2 * Math.PI / 180) -
              Math.sin(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.cos(dLon);
    const brng = Math.atan2(y, x) * 180 / Math.PI;
    return (brng + 360) % 360;
}

// Generates smooth dense sub-waypoints along any polyline for continuous animation
function interpolatePath(points, totalSteps = 250) {
    if (!points || points.length === 0) return [];
    if (points.length === 1) return [points[0]];

    const interpolated = [];

    // Calculate total polyline length
    let totalDist = 0;
    const segDists = [];
    for (let i = 0; i < points.length - 1; i++) {
        const d = haversine(points[i][0], points[i][1], points[i+1][0], points[i+1][1]);
        segDists.push(d);
        totalDist += d;
    }

    if (totalDist === 0) {
        for (let i = 0; i < totalSteps; i++) interpolated.push(points[0]);
        return interpolated;
    }

    // Distribute steps proportionally
    for (let i = 0; i < points.length - 1; i++) {
        const p1 = points[i];
        const p2 = points[i+1];
        const segSteps = Math.max(2, Math.round((segDists[i] / totalDist) * totalSteps));

        for (let s = 0; s < segSteps; s++) {
            const frac = s / segSteps;
            const lat = p1[0] + (p2[0] - p1[0]) * frac;
            const lng = p1[1] + (p2[1] - p1[1]) * frac;
            interpolated.push([lat, lng]);
        }
    }
    interpolated.push(points[points.length - 1]);
    return interpolated;
}

// Update status pill dot + label
function updateStatus(dotId, dotClass, textId, text) {
    const dotEl = document.getElementById(dotId);
    const txtEl = document.getElementById(textId);
    if (dotEl) dotEl.className = `dot ${dotClass}`;
    if (txtEl) txtEl.textContent = text;
}

function escapeHTML(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[char]);
}
