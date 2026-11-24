// ============================================================
// HOSPITALS MODULE — Discovery, Proximity & Clinical Triage
// AERT (AI Emergency Routing & Tracking)
// ============================================================

let currentHospitals = [];
let selectedHosp = null;

async function findHospitals(lat, lng) {
    updateStatus('placesDot', 'b', 'placesText', 'Searching facilities...');
    const listEl = document.getElementById('hospList');
    currentHospitals = [];
    selectedHosp = null;
    const calcBtn = document.getElementById('calcBtn');
    if (calcBtn) calcBtn.disabled = true;
    if (typeof leafletMap !== 'undefined' && leafletMap) placeHospitalMarkers([]);
    if (listEl) {
        listEl.innerHTML = '<p style="font-size:11px;color:var(--text-dim);padding:8px 0">Querying real nearby healthcare centers...</p>';
    }

    try {
        const encType = encodeURIComponent(currentEmergencyType);
        const url = `${CONFIG.BACKEND_API_BASE}/hospitals/nearby?lat=${lat}&lng=${lng}&emergency_type=${encType}`;
        const res = await fetch(url);
        
        if (res.ok) {
            const data = await res.json();
            currentHospitals = (data.hospitals || []).map((h, i) => ({
                id: h.hospital_id || `HOSP-${i+1}`,
                name: h.name,
                lat: h.latitude,
                lng: h.longitude,
                dist: h.distance_km !== undefined ? h.distance_km : haversine(lat, lng, h.latitude, h.longitude),
                vicinity: h.address || 'Verified healthcare location',
                isOpen: h.twenty_four_seven !== null && h.twenty_four_seven !== undefined
                    ? h.twenty_four_seven
                    : null,
                rating: h.rating || 4.2,
                totalRatings: h.total_ratings || 50,
                emergencyDept: h.emergency_dept,
                icu: h.icu,
                cardiac: h.cardiac_care,
                trauma: h.trauma_center,
                burn: h.burn_unit,
                stroke: h.stroke_care,
                suitabilityScore: h.suitability_score,
                suitabilityReasons: h.suitability_reasons || [],
                source: h.source || 'OpenStreetMap Live'
            }));

            if (currentHospitals.length > 0) {
                const isLocal = currentHospitals[0].source.includes('Local');
                const label = isLocal ? 'Structured Registry' : 'OpenStreetMap Live';
                updateStatus('placesDot', 'g', 'placesText', `${currentHospitals.length} Facilities (${label})`);
                const cnt = document.getElementById('hospCount');
                const distances = currentHospitals.map(h => h.dist);
                if (cnt) cnt.textContent = `${currentHospitals.length} Found (${Math.min(...distances).toFixed(1)} - ${Math.max(...distances).toFixed(1)} km)`;

                renderHospitalsList(currentHospitals);
                placeHospitalMarkers(currentHospitals);
                selectHospital(0);
                fitMapBounds(currentHospitals);
            } else {
                updateStatus('placesDot', 'y', 'placesText', '0 Facilities Found');
                if (listEl) {
                    listEl.innerHTML = '<p style="font-size:11px;color:#f87171;padding:8px 0">No healthcare facilities found within the search radius.</p>';
                }
            }
        } else {
            throw new Error(`Hospital API returned HTTP ${res.status}`);
        }
    } catch (e) {
        console.error('[HOSPITALS ERROR]', e);
        updateStatus('placesDot', 'r', 'placesText', 'Healthcare API Offline');
        if (listEl) {
            listEl.textContent = `Healthcare search failed: ${e.message}`;
        }
    }
}

function renderHospitalsList(list) {
    const container = document.getElementById('hospList');
    if (!container) return;
    container.innerHTML = '';

    if (list.length === 0) {
        container.innerHTML = '<p style="font-size:11px;color:var(--text-dim);padding:8px 0">No facilities match the selected filter in this radius.</p>';
        return;
    }

    list.forEach((h, i) => {
        const el = document.createElement('div');
        el.className = 'hosp-item' + (selectedHosp && selectedHosp.id === h.id ? ' selected' : '');
        el.id = 'hosp-list-item-' + i;
        el.dataset.hospitalId = h.id;

        const isTop = i === 0;
        const statusTxt = h.isOpen === true ? '🟢 24×7 Emergency' : (h.isOpen === false ? '⚪ Not 24×7' : '⚪ Hours Unverified');
        const statusColor = h.isOpen === true ? '#86efac' : '#94a3b8';

        // Specialized clinical capability badges
        const caps = [];
        if (h.cardiac === true) caps.push('❤️ Cardiac');
        if (h.trauma === true)  caps.push('💥 Trauma');
        if (h.icu === true)     caps.push('🛏 ICU');
        if (h.burn === true)    caps.push('🔥 Burn Unit');
        if (h.stroke === true)  caps.push('🧠 Stroke');

        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div class="hosp-name" style="color:${isTop ? 'var(--accent)' : 'var(--text)'}">${escapeHTML(h.name)}</div>
                <div class="hosp-dist">${h.dist.toFixed(2)} km</div>
            </div>
            <div class="hosp-meta">
                <span style="color:var(--text-dim);font-size:10px">${escapeHTML(h.vicinity)}</span>
                <span style="font-size:10px;font-weight:700;color:${statusColor}">${statusTxt}</span>
            </div>
            <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:5px">
                ${caps.map(c => `<span class="cap-tag">${c}</span>`).join('')}
                ${caps.length === 0 ? '<span class="cap-tag" style="color:var(--text-dim)">General Medical Center</span>' : ''}
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:9px;color:var(--text-muted);margin-top:5px">
                <span>Source: ${escapeHTML(h.source)}</span>
                ${h.suitabilityReasons && h.suitabilityReasons.length > 0 ? `<span style="color:#c084fc">✓ ${escapeHTML(h.suitabilityReasons[0])}</span>` : ''}
            </div>
        `;

        el.onclick = () => selectHospitalById(h.id);
        container.appendChild(el);
    });
}

function selectHospitalById(hospitalId) {
    const index = currentHospitals.findIndex(h => h.id === hospitalId);
    if (index < 0) return;
    selectHospital(index);
}

function selectHospital(idx) {
    if (!currentHospitals[idx]) return;
    selectedHosp = currentHospitals[idx];

    document.querySelectorAll('.hosp-item').forEach((el, i) => {
        el.classList.toggle('selected', el.dataset.hospitalId === selectedHosp.id);
    });

    const btn = document.getElementById('calcBtn');
    if (btn) {
        btn.disabled = false;
        btn.textContent = `⚡ Calculate Routes to ${selectedHosp.name.substring(0, 24)}...`;
    }

    if (leafletMap) {
        const marker = hospitalMarkers.find(item => item.hospitalId === selectedHosp.id);
        if (marker) marker.openPopup();
    }
}

function filterHospitals(type, btn) {
    document.querySelectorAll('.hosp-filter-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    let filtered = [...currentHospitals];
    if (type === 'suitable') {
        filtered.sort((a, b) => (a.suitabilityScore || 999) - (b.suitabilityScore || 999));
    } else if (type === 'open') {
        filtered = filtered.filter(h => h.isOpen === true);
    } else if (type === 'nearest') {
        filtered.sort((a, b) => a.dist - b.dist);
    }

    renderHospitalsList(filtered);
}
