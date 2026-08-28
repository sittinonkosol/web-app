(function () {
    const API_BASE = window.location.pathname.replace(/\/admin(\.html)?\/?$/, '').replace(/\/index\.html\/?$/, '').replace(/\/$/, '');

    // Default center: Thailand (or fallback Bangkok / Ubon)
    const DEFAULT_LAT = 15.2293;
    const DEFAULT_LNG = 104.8576; // Ubon Ratchathani center
    const DEFAULT_ZOOM = 13;

    // --- Initialize Leaflet Map ---
    const map = L.map('map', {
        zoomControl: false
    }).setView([DEFAULT_LAT, DEFAULT_LNG], DEFAULT_ZOOM);

    // Add OpenStreetMap Tile Layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);

    // Zoom control on top right
    L.control.zoom({ position: 'topright' }).addTo(map);

    // --- State ---
    let markersLayer = L.layerGroup().addTo(map);
    let tempPinMarker = null;
    let savedMarkersList = [];

    // --- Toast Utility ---
    function showToast(msg) {
        const t = document.createElement('div');
        t.className = 'toast';
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 2600);
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    // --- Custom Category Marker Colors ---
    function getCategoryColor(category) {
        switch (category) {
            case 'จุดบริการ': return '#3b82f6'; // Blue
            case 'จุดนัดพบ': return '#10b981'; // Green
            case 'ร้านค้า': return '#f59e0b'; // Amber
            case 'เหตุด่วน': return '#ef4444'; // Red
            default: return '#8b5cf6'; // Purple
        }
    }

    function createMarkerIcon(category) {
        if (category === 'เหตุด่วน' || (category && category.includes('SOS'))) {
            return L.divIcon({
                className: 'custom-sos-icon',
                html: `<div class="sos-beacon-pulse"><div style="background:#ef4444;width:30px;height:30px;border-radius:50%;border:2.5px solid #fff;box-shadow:0 0 16px rgba(239,68,68,0.9);display:flex;align-items:center;justify-content:center;font-size:14px;color:#fff;">🚨</div></div>`,
                iconSize: [36, 36],
                iconAnchor: [18, 18],
                popupAnchor: [0, -18]
            });
        }
        const color = getCategoryColor(category);
        return L.divIcon({
            className: 'custom-div-icon',
            html: `<div style="background:${color};width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 4px 12px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;"><div style="width:8px;height:8px;background:#fff;border-radius:50%;"></div></div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 28],
            popupAnchor: [0, -28]
        });
    }

    // --- Temporary Pin Icon ---
    const tempIcon = L.divIcon({
        className: 'temp-div-icon',
        html: `<div style="background:#e11d48;width:32px;height:32px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:3px solid #fff;box-shadow:0 6px 16px rgba(225,29,72,0.5);display:flex;align-items:center;justify-content:center;animation:bounce 0.5s;"><div style="width:10px;height:10px;background:#fff;border-radius:50%;"></div></div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 32],
        popupAnchor: [0, -32]
    });

    // --- Reverse Geocoding (OpenStreetMap Nominatim) ---
    async function reverseGeocode(lat, lng) {
        const addrInput = document.getElementById('pin-address');
        addrInput.placeholder = 'กำลังดึงชื่อที่อยู่อัตโนมัติ...';
        try {
            const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`;
            const res = await fetch(url, { headers: { 'Accept-Language': 'th,en' } });
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.display_name) {
                addrInput.value = data.display_name;
            }
        } catch (e) {
            console.warn('Reverse geocode failed', e);
            addrInput.placeholder = 'ระบุที่อยู่หรือบริเวณใกล้เคียง...';
        }
    }

    // --- Handle Map Click to place Temporary Pin ---
    map.on('click', (e) => {
        const { lat, lng } = e.latlng;
        setTemporaryPin(lat, lng);
    });

    function setTemporaryPin(lat, lng) {
        document.getElementById('pin-lat').value = lat;
        document.getElementById('pin-lng').value = lng;
        document.getElementById('display-coords').textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

        if (tempPinMarker) {
            tempPinMarker.setLatLng([lat, lng]);
        } else {
            tempPinMarker = L.marker([lat, lng], { icon: tempIcon, draggable: true }).addTo(map);
            tempPinMarker.on('dragend', (ev) => {
                const pos = ev.target.getLatLng();
                setTemporaryPin(pos.lat, pos.lng);
            });
        }

        // Switch to Add Pin tab, expand sheet, and focus title
        expandSheet();
        activateTab('tab-add-pin');
        reverseGeocode(lat, lng);
    }

    // --- Fetch and Render Saved Markers ---
    async function fetchSavedMarkers() {
        try {
            const res = await fetch(`${API_BASE}/api/locations`);
            if (!res.ok) throw new Error('Fetch failed');
            savedMarkersList = await res.json();
            renderMarkersOnMap(savedMarkersList);
            renderMarkersCards(savedMarkersList);
            const countEl = document.getElementById('pins-count');
            if (countEl) countEl.textContent = savedMarkersList.length;
            const mobileCountEl = document.getElementById('mobile-pins-count');
            if (mobileCountEl) mobileCountEl.textContent = savedMarkersList.length;
        } catch (err) {
            console.error('Failed to load markers', err);
        }
    }

    function renderMarkersOnMap(markers) {
        markersLayer.clearLayers();

        markers.forEach(m => {
            const icon = createMarkerIcon(m.category);
            const marker = L.marker([m.latitude, m.longitude], { icon }).addTo(markersLayer);

            const isEmergency = m.category === 'เหตุด่วน' || m.title.includes('SOS');
            const catBadgeClass = isEmergency ? 'cat-emergency' : 'cat-general';

            const popupHtml = `
                <div style="padding: 6px 4px; min-width: 220px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px;">
                        <strong style="font-size: 15px; color: #fff; font-weight: 700;">${escapeHtml(m.title)}</strong>
                        <span class="cat-badge ${catBadgeClass}">${escapeHtml(m.category)}</span>
                    </div>
                    ${m.address ? `<div style="font-size: 12px; color: #94a3b8; margin-bottom: 6px; line-height: 1.4;">📍 ${escapeHtml(m.address)}</div>` : ''}
                    ${m.description ? `<p style="font-size: 12.5px; color: #e2e8f0; margin-bottom: 8px; line-height: 1.4; background: rgba(255,255,255,0.04); padding: 6px 8px; border-radius: 6px;">${escapeHtml(m.description)}</p>` : ''}
                    
                    <div style="margin: 8px 0 6px;">
                        <a href="https://www.google.com/maps/dir/?api=1&destination=${m.latitude},${m.longitude}" target="_blank" style="display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #38bdf8; text-decoration: none; font-weight: 600;">
                            <span>🧭 นำทางบน Google Maps ↗</span>
                        </a>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #64748b; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;">
                        <span>👤 ${escapeHtml(m.created_by)}</span>
                        <span>${escapeHtml(m.created_at)}</span>
                    </div>
                </div>
            `;
            marker.bindPopup(popupHtml);
        });
    }

    function renderMarkersCards(markers) {
        const container = document.getElementById('markers-cards-container');
        if (markers.length === 0) {
            container.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text-dim);font-size:13.5px;">ยังไม่มีหมุดพิกัด คลิกบนแผนที่เพื่อปักหมุดแรก!</div>`;
            return;
        }

        let html = '';
        markers.forEach(m => {
            html += `
                <div class="marker-card" data-id="${m.id}" data-lat="${m.latitude}" data-lng="${m.longitude}">
                    <div class="marker-card-header">
                        <div class="marker-card-title">📍 ${escapeHtml(m.title)}</div>
                        <span class="cat-badge cat-general">${escapeHtml(m.category)}</span>
                    </div>
                    ${m.address ? `<div class="marker-card-address">${escapeHtml(m.address)}</div>` : ''}
                    <div class="marker-card-footer">
                        <span>👤 ${escapeHtml(m.created_by)}</span>
                        <span style="font-family:var(--font-mono);">${m.latitude.toFixed(4)}, ${m.longitude.toFixed(4)}</span>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;

        // Click card to fly to marker on map
        container.querySelectorAll('.marker-card').forEach(card => {
            card.addEventListener('click', () => {
                const lat = parseFloat(card.dataset.lat);
                const lng = parseFloat(card.dataset.lng);
                map.flyTo([lat, lng], 16, { duration: 1.2 });
            });
        });
    }

    // --- Search Filter in Cards List ---
    const searchInput = document.getElementById('search-markers-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const val = e.target.value.toLowerCase().trim();
            const filtered = savedMarkersList.filter(m => 
                m.title.toLowerCase().includes(val) ||
                (m.address && m.address.toLowerCase().includes(val)) ||
                m.category.toLowerCase().includes(val)
            );
            renderMarkersCards(filtered);
        });
    }

    // --- Save New Pin Form Submit ---
    const newPinForm = document.getElementById('new-pin-form');
    if (newPinForm) {
        newPinForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const lat = parseFloat(document.getElementById('pin-lat').value);
            const lng = parseFloat(document.getElementById('pin-lng').value);

            if (isNaN(lat) || isNaN(lng)) {
                showToast('⚠️ กรุณาคลิกเลือกจุดบนแผนที่ก่อนบันทึก');
                return;
            }

            const title = document.getElementById('pin-title').value.trim();
            const category = document.getElementById('pin-category').value;
            const address = document.getElementById('pin-address').value.trim();
            const description = document.getElementById('pin-desc').value.trim();
            const created_by = document.getElementById('pin-creator').value.trim();

            try {
                const res = await fetch(`${API_BASE}/api/locations`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title, category, address, description, created_by,
                        latitude: lat,
                        longitude: lng
                    })
                });

                if (!res.ok) throw new Error('Save failed');

                showToast('✅ บันทึกพิกัดสถานที่เรียบร้อย!');
                
                // Clear temporary pin & reset form
                if (tempPinMarker) {
                    tempPinMarker.remove();
                    tempPinMarker = null;
                }
                newPinForm.reset();
                document.getElementById('pin-lat').value = '';
                document.getElementById('pin-lng').value = '';
                document.getElementById('display-coords').textContent = 'คลิกเลือกบนแผนที่';

                // Reload markers & switch to list tab
                await fetchSavedMarkers();
                activateTab('tab-list-pins');
                map.flyTo([lat, lng], 15, { duration: 1 });
            } catch (err) {
                console.error(err);
                showToast('บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง');
            }
        });
    }

    // --- Instant SOS Emergency Trigger ---
    async function triggerInstantSOS() {
        if (!navigator.geolocation) {
            showToast('⚠️ เบราว์เซอร์ของคุณไม่รองรับ GPS');
            return;
        }

        showToast('🚨 กำลังดึงพิกัด GPS เพื่อส่งสัญญาณ SOS ทันที...');

        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                const { latitude, longitude, accuracy } = pos.coords;
                const nowStr = new Date().toLocaleTimeString('th-TH');

                // 1. Immediately POST SOS beacon to server
                try {
                    const res = await fetch(`${API_BASE}/api/locations`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            is_sos: true,
                            title: '🚨 สัญญาณ SOS ขอความช่วยเหลือ',
                            category: 'เหตุด่วน',
                            latitude: latitude,
                            longitude: longitude,
                            description: `ความแม่นยำ GPS: ±${accuracy ? accuracy.toFixed(1) : 0} เมตร`,
                            created_by: 'ผู้ส่งสัญญาณฉุกเฉิน (SOS)'
                        })
                    });

                    if (res.ok) {
                        showToast('🚨 ส่งสัญญาณ SOS และบันทึกพิกัดฉุกเฉินเรียบร้อย!');

                        // Update SOS banner
                        const banner = document.getElementById('sos-live-banner');
                        if (banner) {
                            banner.style.display = 'block';
                            document.getElementById('sos-timestamp').textContent = nowStr;
                            document.getElementById('sos-coords-text').textContent = `📍 ${latitude.toFixed(5)}, ${longitude.toFixed(5)} (±${accuracy ? accuracy.toFixed(0) : 0}ม.)`;
                            document.getElementById('sos-address-text').textContent = 'กำลังตรวจสอบชื่อบริเวณใกล้เคียง...';
                        }

                        // Fly map to user's emergency location
                        map.flyTo([latitude, longitude], 17, { duration: 1.2 });

                        // Refresh markers on map
                        await fetchSavedMarkers();

                        // Reverse geocode to show address
                        try {
                            const geoUrl = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`;
                            const geoRes = await fetch(geoUrl, { headers: { 'Accept-Language': 'th,en' } });
                            if (geoRes.ok) {
                                const geoData = await geoRes.json();
                                if (geoData && geoData.display_name) {
                                    document.getElementById('sos-address-text').textContent = `🏢 ${geoData.display_name}`;
                                }
                            }
                        } catch (e) {}
                    }
                } catch (err) {
                    console.error(err);
                    showToast('⚠️ ไม่สามารถส่งสัญญาณ SOS ไปยังเซิร์ฟเวอร์ได้');
                }
            },
            (err) => {
                console.warn('Geolocation denied or failed', err);
                if (err.code === 1) {
                    showToast('⚠️ คุณปฏิเสธการเข้าถึงพิกัด GPS กรุณาอนุญาตตำแหน่งเพื่อส่ง SOS');
                } else {
                    showToast('⚠️ ไม่สามารถระบุพิกัด GPS ได้ในขณะนี้');
                }
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    const sosTriggerBtn = document.getElementById('btn-trigger-sos');
    if (sosTriggerBtn) {
        sosTriggerBtn.addEventListener('click', () => {
            triggerInstantSOS();
        });
    }

    // --- GPS Geolocation "Locate Me" ---
    const locateBtn = document.getElementById('btn-locate-me');
    if (locateBtn) {
        locateBtn.addEventListener('click', () => {
            if (!navigator.geolocation) {
                showToast('⚠️ เบราว์เซอร์ไม่รองรับ GPS');
                return;
            }
            showToast('🔍 กำลังค้นหาพิกัด GPS ของคุณ...');
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const { latitude, longitude } = pos.coords;
                    map.flyTo([latitude, longitude], 16, { duration: 1.5 });
                    setTemporaryPin(latitude, longitude);
                    showToast('🎯 ระบุตำแหน่งของคุณแล้ว!');
                },
                (err) => {
                    console.warn('Geolocation error', err);
                    showToast('⚠️ ไม่สามารถเข้าถึงพิกัด GPS ได้ กรุณาอนุญาตตำแหน่ง');
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        });
    }

    // --- Toggle Side Panel on Mobile ---
    // --- Onboarding / Location Gate Flow ---
    const gateOverlay = document.getElementById('location-gate-overlay');
    const gateStatusText = document.getElementById('gate-status-text');
    const gateSpinner = document.getElementById('gate-spinner');
    const gateActionBtn = document.getElementById('gate-action-btn');
    const gateSkipBtn = document.getElementById('gate-skip-btn');

    // Check existing browser permission state
    if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'geolocation' }).then((result) => {
            if (result.state === 'denied') {
                if (gateStatusText) {
                    gateStatusText.innerHTML = '⚠️ สิทธิ์ถูกบล็อก: กรุณาคลิกไอคอน <strong>🔒 ด้านซ้าย URL</strong> แล้วเลือก Location เป็น <strong>Allow</strong>';
                }
                if (gateSpinner) gateSpinner.style.display = 'none';
            } else if (result.state === 'granted') {
                requestAndRecordLocation(true);
            }
        }).catch(() => {});
    }

    if (gateActionBtn) {
        gateActionBtn.addEventListener('click', () => {
            requestAndRecordLocation(false);
        });
    }

    if (gateSkipBtn) {
        gateSkipBtn.addEventListener('click', () => {
            unlockMap();
        });
    }

    function unlockMap() {
        if (gateOverlay) {
            gateOverlay.classList.add('hidden');
            setTimeout(() => gateOverlay.remove(), 450);
        }
    }

    // Auto-prompt GPS on page load
    requestAndRecordLocation(true);

    function requestAndRecordLocation(isAutoPrompt = false) {
        if (!navigator.geolocation) {
            if (gateStatusText) gateStatusText.textContent = '⚠️ เบราว์เซอร์ไม่รองรับ GPS';
            if (gateSpinner) gateSpinner.style.display = 'none';
            return;
        }

        if (gateStatusText) gateStatusText.textContent = 'กรุณากด "อนุญาต (Allow)" บนหน้าต่างเบราว์เซอร์...';
        if (gateSpinner) gateSpinner.style.display = 'inline-block';

        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                const { latitude, longitude, accuracy } = pos.coords;
                const nowStr = new Date().toLocaleTimeString('th-TH');

                if (gateStatusText) gateStatusText.textContent = '💾 กำลังบันทึกพิกัดตำแหน่งของคุณเข้าสู่ระบบ...';

                // Auto-record location immediately to map_locator.db
                try {
                    const res = await fetch(`${API_BASE}/api/locations`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            is_sos: true,
                            title: '🚨 สัญญาณ SOS (ตรวจจับอัตโนมัติ)',
                            category: 'เหตุด่วน',
                            latitude: latitude,
                            longitude: longitude,
                            description: `ความแม่นยำ GPS: ±${accuracy ? accuracy.toFixed(1) : 0} เมตร (บันทึกอัตโนมัติเมื่อเข้าสู่ระบบ)`,
                            created_by: 'ผู้ใช้เข้าสู่ระบบ (Auto GPS)'
                        })
                    });

                    if (res.ok) {
                        if (gateStatusText) gateStatusText.textContent = '✅ บันทึกพิกัดสำเร็จ! กำลังเข้าสู่แผนที่...';
                        showToast('📍 ตรวจจับและบันทึกพิกัดตำแหน่งของคุณเรียบร้อยแล้ว');

                        // Show SOS banner
                        const banner = document.getElementById('sos-live-banner');
                        if (banner) {
                            banner.style.display = 'block';
                            document.getElementById('sos-timestamp').textContent = nowStr;
                            document.getElementById('sos-coords-text').textContent = `📍 ${latitude.toFixed(5)}, ${longitude.toFixed(5)} (±${accuracy ? accuracy.toFixed(0) : 0}ม.)`;
                            document.getElementById('sos-address-text').textContent = 'กำลังตรวจสอบชื่อบริเวณใกล้เคียง...';
                        }

                        // Unlock map after brief confirmation
                        setTimeout(() => {
                            unlockMap();
                            map.flyTo([latitude, longitude], 16, { duration: 1.2 });
                        }, 400);

                        // Refresh markers on map
                        await fetchSavedMarkers();

                        // Reverse geocode to get human-readable address
                        try {
                            const geoUrl = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`;
                            const geoRes = await fetch(geoUrl, { headers: { 'Accept-Language': 'th,en' } });
                            if (geoRes.ok) {
                                const geoData = await geoRes.json();
                                if (geoData && geoData.display_name) {
                                    document.getElementById('sos-address-text').textContent = `🏢 ${geoData.display_name}`;
                                }
                            }
                        } catch (e) {}
                    } else {
                        unlockMap();
                    }
                } catch (e) {
                    console.warn('Auto record failed', e);
                    unlockMap();
                }
            },
            (err) => {
                console.warn('Geolocation prompt denied or ignored:', err.message);
                if (gateStatusText) {
                    if (err.code === 1) { // PERMISSION_DENIED
                        gateStatusText.innerHTML = '⚠️ สิทธิ์ถูกบล็อก: กรุณาคลิกไอคอน <strong>🔒 ด้านซ้าย URL</strong> แล้วเลือก Location เป็น <strong>Allow</strong>';
                    } else if (err.code === 2) { // POSITION_UNAVAILABLE
                        gateStatusText.textContent = '⚠️ ไม่สามารถระบุสัญญาณ GPS ได้ในขณะนี้';
                    } else if (err.code === 3) { // TIMEOUT
                        gateStatusText.textContent = '⚠️ หมดเวลาการรอสัญญาณ GPS กดปุ่มเพื่อลองใหม่อีกครั้ง';
                    } else {
                        gateStatusText.textContent = '⚠️ กรุณากดปุ่มด้านล่างเพื่ออนุญาตพิกัดตำแหน่ง';
                    }
                }
                if (gateSpinner) gateSpinner.style.display = 'none';
            },
            (err) => {
                console.warn('Geolocation prompt denied or ignored:', err.message);
                if (gateStatusText) {
                    if (err.code === 1) { // PERMISSION_DENIED
                        gateStatusText.innerHTML = '⚠️ สิทธิ์ถูกบล็อก: กรุณาคลิกไอคอน <strong>🔒 ด้านซ้าย URL</strong> แล้วเลือก Location เป็น <strong>Allow</strong>';
                    } else if (err.code === 2) { // POSITION_UNAVAILABLE
                        gateStatusText.textContent = '⚠️ ไม่สามารถระบุสัญญาณ GPS ได้ในขณะนี้';
                    } else if (err.code === 3) { // TIMEOUT
                        gateStatusText.textContent = '⚠️ หมดเวลาการรอสัญญาณ GPS กดปุ่มเพื่อลองใหม่อีกครั้ง';
                    } else {
                        gateStatusText.textContent = '⚠️ กรุณากดปุ่มด้านล่างเพื่ออนุญาตพิกัดตำแหน่ง';
                    }
                }
                if (gateSpinner) gateSpinner.style.display = 'none';
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    // --- Toggle Side Panel / Bottom Sheet ---
    const togglePanelBtn = document.getElementById('btn-toggle-panel');
    const sidePanel = document.getElementById('side-panel');
    const sheetToggleHandle = document.getElementById('sheet-toggle-handle');
    const btnCloseSheet = document.getElementById('btn-close-sheet');

    function toggleSheet() {
        if (sidePanel) {
            sidePanel.classList.toggle('collapsed');
        }
    }

    function expandSheet() {
        if (sidePanel) {
            sidePanel.classList.remove('collapsed');
        }
    }

    function collapseSheet() {
        if (sidePanel) {
            sidePanel.classList.add('collapsed');
        }
    }

    if (togglePanelBtn) {
        togglePanelBtn.addEventListener('click', toggleSheet);
    }
    if (sheetToggleHandle) {
        sheetToggleHandle.addEventListener('click', toggleSheet);
    }
    if (btnCloseSheet) {
        btnCloseSheet.addEventListener('click', collapseSheet);
    }

    // --- Tabs Switching ---
    const tabAddPin = document.getElementById('tab-add-pin');
    const tabListPins = document.getElementById('tab-list-pins');
    const panelAddContent = document.getElementById('panel-add-pin-content');
    const panelListContent = document.getElementById('panel-list-pins-content');

    function activateTab(tabId) {
        if (tabId === 'tab-add-pin') {
            tabAddPin.classList.add('active');
            tabListPins.classList.remove('active');
            panelAddContent.style.display = 'block';
            panelListContent.style.display = 'none';
        } else {
            tabListPins.classList.add('active');
            tabAddPin.classList.remove('active');
            panelListContent.style.display = 'block';
            panelAddContent.style.display = 'none';
        }
    }

    if (tabAddPin && tabListPins) {
        tabAddPin.addEventListener('click', () => activateTab('tab-add-pin'));
        tabListPins.addEventListener('click', () => activateTab('tab-list-pins'));
    }

    // --- Init Load ---
    fetchSavedMarkers();

})();
