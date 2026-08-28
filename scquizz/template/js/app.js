(function () {
  const API_BASE = window.location.pathname.replace(/\/admin(\.html)?\/?$/, '').replace(/\/index\.html\/?$/, '').replace(/\/$/, '');


  // ---------- ambient particles ----------
  const sky = document.getElementById('sky');
  const sparkCount = window.innerWidth < 600 ? 8 : 14;
  if (sky) {
    for (let i = 0; i < sparkCount; i++) {
      const s = document.createElement('div');
      s.className = 'spark';
      s.style.left = Math.random() * 100 + '%';
      s.style.top = Math.random() * 100 + '%';
      s.style.animationDelay = Math.random() * 8 + 's';
      s.style.animationDuration = 5 + Math.random() * 8 + 's';
      sky.appendChild(s);
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatTime(ts) {
    const d = new Date(ts);
    const months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
    const day = d.getDate();
    const month = months[d.getMonth()];
    const year = d.getFullYear() + 543;
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${day} ${month} ${year} · ${hh}:${mm} น.`;
  }

  let activeAudioCue = null;

  function stopMessageCue() {
    if (activeAudioCue) {
      activeAudioCue.pause();
      activeAudioCue = null;
    }
  }

  function playMessageCue(text, msgId) {
    if (!text || !msgId) return;

    stopMessageCue();

    const audio = new Audio(`${API_BASE}/asset/sfx.mp3`);
    audio.volume = 0.25;
    activeAudioCue = audio;

    function speakText() {
      if (activeAudioCue !== audio) return;

      const ttsAudio = new Audio(`${API_BASE}/api/messages/${msgId}/tts`);
      activeAudioCue = ttsAudio;

      ttsAudio.play().catch(err => {
        console.warn('gTTS play failed', err);
      });
    }

    audio.addEventListener('ended', () => {
      speakText();
    });

    audio.play().catch(err => {
      console.warn('sfx play failed, playing gTTS directly', err);
      speakText();
    });
  }

  // ---------- API Helpers ----------

  // ส่งข้อความผ่าน API
  async function sendMessageToAPI(name, text) {
    const res = await fetch(`${API_BASE}/api/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, text })
    });
    if (!res.ok) throw new Error('Send failed');
  }

  // ลบข้อความผ่าน API
  async function deleteMessageFromAPI(id) {
    const res = await fetch(`${API_BASE}/api/messages/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Delete failed');
  }

  // ทำเครื่องหมายตอบแล้วผ่าน API
  async function answerMessageInAPI(id) {
    const res = await fetch(`${API_BASE}/api/messages/${id}/answer`, { method: 'POST' });
    if (!res.ok) throw new Error('Answer failed');
  }

  // ดึงข้อความทั้งหมด
  let currentList = [];
  async function fetchMessages() {
    try {
      const res = await fetch(`${API_BASE}/api/messages`, { cache: 'no-store' });
      if (!res.ok) throw new Error(res.statusText);
      currentList = await res.json();
      renderAdmin();
    } catch (err) {
      console.error('fetch error', err);
      showToast('โหลดข้อความไม่สำเร็จ');
    }
  }

  // ---------- Poll Client APIs & Logic ----------

  let activePoll = null;
  async function fetchActivePoll() {
    try {
      const res = await fetch(`${API_BASE}/api/polls/active`, { cache: 'no-store' });
      if (!res.ok) throw new Error('Failed to fetch active poll');
      activePoll = await res.json();
      renderActivePoll();
    } catch (err) {
      console.error(err);
    }
  }

  function renderActivePoll() {
    const area = document.getElementById('active-poll-area');
    if (!area) return;

    if (!activePoll) {
      area.innerHTML = `
        <div style="text-align: center; padding: 40px 20px; color: var(--text-dim);">
          <span style="font-size: 40px; display: block; margin-bottom: 10px;">📊</span>
          <p style="font-size: 15px; margin: 0;">ขณะนี้ยังไม่มีโพลที่เปิดใช้งานอยู่</p>
        </div>
      `;
      return;
    }

    const hasVoted = localStorage.getItem(`voted_poll_${activePoll.id}`);
    const isLocation = activePoll.type === 'location';

    if (hasVoted) {
      // Render results view
      let html = `
        <h2 style="font-size: 18px; color: var(--text); font-family: 'Noto Serif Thai', serif; margin: 0 0 20px;">${escapeHtml(activePoll.question)}</h2>
        <div class="poll-results-chart">
      `;

      if (isLocation) {
        const votesDict = activePoll.votes || {};
        const sortedVotes = Object.entries(votesDict).sort((a, b) => b[1] - a[1]);
        const totalVotes = Object.values(votesDict).reduce((a, b) => a + b, 0);

        sortedVotes.forEach(([loc, val]) => {
          const percent = totalVotes > 0 ? Math.round((val / totalVotes) * 100) : 0;
          html += `
            <div class="poll-result-row">
              <div class="poll-result-info">
                <span>${escapeHtml(loc)}</span>
                <span>${percent}% (${val} คน)</span>
              </div>
              <div class="poll-result-bar-bg">
                <div class="poll-result-bar-fill" style="width: ${percent}%;"></div>
              </div>
            </div>
          `;
        });
        if (sortedVotes.length === 0) {
          html += `<p style="text-align: center; color: var(--text-dim);">ยังไม่มีผู้ส่งคำตอบโพล</p>`;
        }
      } else {
        const totalVotes = activePoll.votes.reduce((a, b) => a + b, 0);
        activePoll.options.forEach((opt, idx) => {
          const votes = activePoll.votes[idx];
          const percent = totalVotes > 0 ? Math.round((votes / totalVotes) * 100) : 0;
          html += `
            <div class="poll-result-row">
              <div class="poll-result-info">
                <span>${escapeHtml(opt)}</span>
                <span>${percent}% (${votes} โหวต)</span>
              </div>
              <div class="poll-result-bar-bg">
                <div class="poll-result-bar-fill" style="width: ${percent}%;"></div>
              </div>
            </div>
          `;
        });
      }
      html += `
        </div>
        <p style="font-size: 12px; color: var(--text-dim); text-align: center; margin-top: 20px;">คุณส่งคำตอบโพลนี้แล้ว ขอบคุณครับ</p>
      `;
      area.innerHTML = html;
    } else {
      // Render voting options / input
      let html = `
        <h2 style="font-size: 18px; color: var(--text); font-family: 'Noto Serif Thai', serif; margin: 0 0 20px;">${escapeHtml(activePoll.question)}</h2>
        <form id="vote-form" autocomplete="off" style="position: relative;">
      `;

      if (isLocation) {
        html += `
          <div class="field" style="position: relative; margin-bottom: 20px;">
            <label style="margin-bottom: 8px; display: block; font-weight: 500;">เลือกสถานที่ของคุณ (กดเลือกจากรายการ)</label>
            <input type="text" id="location-search-input" placeholder="🔍 พิมพ์เพื่อค้นหา..." style="width: 100%; margin-bottom: 10px;" autocomplete="off">
            <input type="hidden" id="selected-location-value" value="" required>
            <div id="location-options-list" class="location-options-box"></div>
          </div>
          <button type="submit" class="btn btn-primary" style="margin-top: 10px; width: 100%;">ส่งคะแนนโหวต</button>
        `;
      } else {
        activePoll.options.forEach((opt, idx) => {
          html += `
            <label class="poll-option-card">
              <input type="radio" name="poll-opt" value="${idx}" required>
              <span class="poll-option-text">${escapeHtml(opt)}</span>
            </label>
          `;
        });
        html += `
          <button type="submit" class="btn btn-primary" style="margin-top: 20px; width: 100%;">ส่งคะแนนโหวต</button>
        `;
      }

      html += `</form>`;
      area.innerHTML = html;

      // Location Options List & Search Filter logic
      if (isLocation) {
        const searchInput = document.getElementById('location-search-input');
        const selectedValInput = document.getElementById('selected-location-value');
        const optionsList = document.getElementById('location-options-list');
        const scope = JSON.parse(activePoll.scope || '{}');

        let suggestionsList = [];
        if (scope.level === 'global') {
          suggestionsList = WORLD_COUNTRIES.map(c => c.name);
        } else if (scope.level === 'country') {
          suggestionsList = THAI_PROVINCES.map(p => p.name);
        } else if (scope.level === 'region') {
          suggestionsList = THAI_REGIONS;
        } else if (scope.level === 'province') {
          if (scope.region === 'all') {
            suggestionsList = THAI_PROVINCES.map(p => p.name);
          } else {
            suggestionsList = THAI_PROVINCES.filter(p => p.region === scope.region).map(p => p.name);
          }
        } else if (scope.level === 'district') {
          suggestionsList = THAI_PROVINCES_DISTRICTS[scope.province] || [];
        }

        function renderOptions(filterText = '') {
          optionsList.innerHTML = '';
          const normFilter = filterText.trim().toLowerCase();
          const filtered = suggestionsList.filter(item => {
            if (!normFilter) return true;
            return item.toLowerCase().includes(normFilter);
          });

          if (filtered.length === 0) {
            optionsList.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--text-dim); font-size: 13.5px;">ไม่พบตัวเลือกที่ค้นหา</div>`;
            return;
          }

          filtered.forEach(opt => {
            const card = document.createElement('div');
            card.className = `poll-option-card location-choice-card ${selectedValInput.value === opt ? 'selected' : ''}`;
            card.dataset.value = opt;
            card.innerHTML = `<span>📍</span><span>${escapeHtml(opt)}</span>`;
            card.addEventListener('click', () => {
              optionsList.querySelectorAll('.location-choice-card').forEach(el => el.classList.remove('selected'));
              card.classList.add('selected');
              selectedValInput.value = opt;
              searchInput.value = opt;
            });
            optionsList.appendChild(card);
          });
        }

        renderOptions();

        searchInput.addEventListener('input', () => {
          renderOptions(searchInput.value);
        });
      }

      document.getElementById('vote-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        let body = {};
        if (isLocation) {
          const selectedVal = (document.getElementById('selected-location-value')?.value || '').trim();
          if (!selectedVal) {
            showToast('⚠️ กรุณากดเลือกตัวเลือกจากรายการที่มีให้เท่านั้น');
            return;
          }
          body = { location: selectedVal };
        } else {
          const selectedOpt = document.querySelector('input[name="poll-opt"]:checked');
          if (!selectedOpt) {
            showToast('⚠️ กรุณาเลือกตัวเลือก');
            return;
          }
          body = { option_index: parseInt(selectedOpt.value) };
        }

        try {
          const res = await fetch(`${API_BASE}/api/polls/${activePoll.id}/vote`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
          });
          if (!res.ok) throw new Error('Vote failed');
          localStorage.setItem(`voted_poll_${activePoll.id}`, 'true');
          fetchActivePoll();
        } catch (err) {
          console.error(err);
          showToast('ส่งคะแนนโหวตไม่สำเร็จ ลองใหม่อีกครั้ง');
        }
      });
    }
  }

  // ---------- Admin Poll Manager ----------

  let allPolls = [];
  async function fetchPolls() {
    try {
      const res = await fetch(`${API_BASE}/api/polls`, { cache: 'no-store' });
      if (!res.ok) throw new Error('Failed to fetch polls');
      allPolls = await res.json();
      renderAdminPolls();
    } catch (err) {
      console.error(err);
    }
  }

  function renderAdminPolls() {
    const listContainer = document.getElementById('admin-poll-list');
    if (!listContainer) return;

    if (allPolls.length === 0) {
      listContainer.innerHTML = `
        <div style="text-align: center; padding: 40px; color: #888; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
          <span style="font-size: 32px; display: block; margin-bottom: 10px;">📊</span>
          <p style="margin: 0;">ยังไม่มีโพลในระบบ คลิก "+ สร้างโพล" เพื่อสร้าง</p>
        </div>
      `;
      return;
    }

    let html = '';
    allPolls.forEach(poll => {
      const isLocation = poll.type === 'location';
      const votesDict = isLocation ? (poll.votes || {}) : {};
      const totalVotes = isLocation
        ? Object.values(votesDict).reduce((a, b) => a + b, 0)
        : poll.votes.reduce((a, b) => a + b, 0);
      const isActive = poll.active === 1;

      html += `
        <div class="board-poll-card ${isActive ? 'active-poll' : ''}" data-id="${poll.id}">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 20px;">
            <div>
              <h3 class="board-poll-title">${escapeHtml(poll.question)}</h3>
              <div class="board-poll-status-row" style="margin-top: 6px;">
                <span class="status-badge ${isActive ? 'active' : 'inactive'}">
                  ${isActive ? '● กำลังเปิดโหวต' : '● ปิดโหวต'}
                </span>
                <span style="font-size: 13px; color: #777;">ผู้โหวตรวม: ${totalVotes} คน</span>
              </div>
            </div>
            <button class="btn btn-ghost btn-danger-outline" style="width: auto; padding: 6px 12px; font-size: 13px; border-radius: 6px;" onclick="deletePoll('${poll.id}')">ลบ</button>
          </div>
          
          <div style="margin-top: 10px;">
      `;

      if (isLocation) {
        const scope = JSON.parse(poll.scope || '{}');
        let scopeLabel = '';
        if (scope.level === 'global') scopeLabel = 'ระดับโลก';
        else if (scope.level === 'country') scopeLabel = `ระดับประเทศ (จังหวัดใน ${scope.country})`;
        else if (scope.level === 'region') scopeLabel = `ระดับภูมิภาค (ภูมิภาคใน ${scope.country})`;
        else if (scope.level === 'province') scopeLabel = `ระดับจังหวัด (${scope.region === 'all' ? 'ทุกภูมิภาค' : scope.region})`;
        else if (scope.level === 'district') scopeLabel = `ระดับอำเภอ (อำเภอในจังหวัด ${scope.province})`;

        const topLocations = Object.entries(votesDict).sort((a, b) => b[1] - a[1]).slice(0, 3);

        html += `
          <div style="font-size: 13.5px; color: #555; font-weight: bold; margin-bottom: 6px;">
            ขอบเขต: <span style="color: var(--primary);">${scopeLabel}</span>
          </div>
        `;
        topLocations.forEach(([loc, val]) => {
          const percent = totalVotes > 0 ? Math.round((val / totalVotes) * 100) : 0;
          html += `
            <div class="board-poll-result-row">
              <div class="board-poll-result-info">
                <span>📍 ${escapeHtml(loc)}</span>
                <span>${percent}% (${val} คน)</span>
              </div>
              <div class="board-poll-bar-bg">
                <div class="board-poll-bar-fill" style="width: ${percent}%;"></div>
              </div>
            </div>
          `;
        });
        if (topLocations.length === 0) {
          html += `<p style="font-size: 13px; color: #888; margin: 4px 0;">ยังไม่มีคะแนนโหวต</p>`;
        }
      } else {
        poll.options.forEach((opt, idx) => {
          const votes = poll.votes[idx];
          const percent = totalVotes > 0 ? Math.round((votes / totalVotes) * 100) : 0;
          html += `
            <div class="board-poll-result-row">
              <div class="board-poll-result-info">
                <span>${escapeHtml(opt)}</span>
                <span>${percent}% (${votes})</span>
              </div>
              <div class="board-poll-bar-bg">
                <div class="board-poll-bar-fill" style="width: ${percent}%;"></div>
              </div>
            </div>
          `;
        });
      }

      html += `
          </div>
          <div style="display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid #f0f0f0; padding-top: 12px; margin-top: 12px;">
            ${isActive
          ? `<button class="btn btn-ghost" style="width: auto; padding: 8px 16px; font-size: 13.5px;" onclick="togglePollActive('${poll.id}', false)">ปิดใช้งานโพล</button>`
          : `<button class="btn btn-primary" style="width: auto; padding: 8px 16px; font-size: 13.5px;" onclick="togglePollActive('${poll.id}', true)">เปิดใช้งานโพล</button>`
        }
          </div>
        </div>
      `;
    });

    listContainer.innerHTML = html;

    // Attach click listeners to cards to open presentation modal
    document.querySelectorAll('.board-poll-card').forEach(card => {
      card.addEventListener('click', (e) => {
        // Skip clicks on action buttons
        if (e.target.tagName.toLowerCase() === 'button') return;
        const id = card.getAttribute('data-id');
        const poll = allPolls.find(p => p.id === id);
        if (poll) openPollPresentationModal(poll);
      });
    });
  }

  function openConfirmDeletePollDialog(pollId) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = `
      <div class="modal confirm-body">
        <h2 style="font-family: 'Noto Serif Thai', serif;">ลบโพลสำรวจนี้?</h2>
        <p>เมื่อยืนยัน โพลนี้จะถูกลบออกจากระบบอย่างถาวรและไม่สามารถกู้คืนได้</p>
        <div class="modal-actions">
          <button class="btn btn-ghost" id="cancel-confirm">ยกเลิก</button>
          <button class="btn btn-primary" id="confirm-delete" style="background:linear-gradient(180deg,#E8938A,var(--danger));color:#2a1210;">ยืนยัน ลบโพล</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('#cancel-confirm').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector('#confirm-delete').addEventListener('click', async () => {
      overlay.remove();
      const card = document.querySelector(`.board-poll-card[data-id="${pollId}"]`);
      if (card) {
        card.classList.add('leaving');
        await new Promise(r => setTimeout(r, 500));
      }
      try {
        const res = await fetch(`${API_BASE}/api/polls/${pollId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete poll failed');
        showToast('ลบโพลเรียบร้อย');
      } catch (err) {
        console.error(err);
        showToast('ลบไม่สำเร็จ');
      }
    });
  }

  // Globally bind events for onclick
  window.deletePoll = (id) => {
    openConfirmDeletePollDialog(id);
  };

  window.togglePollActive = async (id, active) => {
    const url = `${API_BASE}/api/polls/${id}/${active ? 'activate' : 'deactivate'}`;
    try {
      const res = await fetch(url, { method: 'POST' });
      if (!res.ok) throw new Error('Toggle active failed');
      showToast(active ? 'เปิดโพลสำรวจแล้ว' : 'ปิดโพลสำรวจแล้ว');
      fetchPolls();
      fetchActivePoll();
    } catch (err) {
      console.error(err);
      showToast('ตั้งค่าไม่สำเร็จ');
    }
  };

  // Live update presentation modal tracks
  let openPollModalId = null;

  // ── Pure-SVG province map (no external libs) ──────────────────────────────
  function _renderProvincesSVG(container, geoData, votesDict) {
    if (!container || !geoData) return;
    window._cachedGeoData = geoData;

    const rect = container.getBoundingClientRect();
    const W = rect.width || container.offsetWidth || 560;
    const H = rect.height || container.offsetHeight || 420;
    const pad = 16;

    // Bounding box in lon/lat
    let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
    geoData.features.forEach(f => {
      const rings = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
      rings.forEach(poly => poly.forEach(ring => ring.forEach(([lon, lat]) => {
        if (lon < minLon) minLon = lon; if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
      })));
    });

    // Equirectangular projection with cos(midLat) aspect correction
    const midLat = (minLat + maxLat) / 2;
    const cosLat = Math.cos(midLat * Math.PI / 180);
    const lonRange = (maxLon - minLon) * cosLat;
    const latRange = maxLat - minLat;

    const availW = W - pad * 2;
    const availH = H - pad * 2;
    const scale = Math.min(availW / lonRange, availH / latRange);

    // Center the map in the container
    const mapW = lonRange * scale;
    const mapH = latRange * scale;
    const offX = pad + (availW - mapW) / 2;
    const offY = pad + (availH - mapH) / 2;

    const project = (lon, lat) => [
      offX + (lon - minLon) * cosLat * scale,
      offY + (maxLat - lat) * scale   // flip Y so north is up
    ];

    const coordsToPath = rings => {
      let d = '';
      rings.forEach(ring => {
        ring.forEach(([lon, lat], i) => {
          const [x, y] = project(lon, lat);
          d += (i === 0 ? `M${x.toFixed(1)},${y.toFixed(1)}` : `L${x.toFixed(1)},${y.toFixed(1)}`);
        });
        d += 'Z';
      });
      return d;
    };

    function normalizeThaiName(str) {
      if (!str) return '';
      return String(str).trim()
        .replace(/^(จังหวัด|จ\.|จ\s+)/, '')
        .replace(/\s+/g, '');
    }

    const aliases = {
      'กรุงเทพมหานคร': ['กรุงเทพ', 'กทม', 'กทม.', 'bangkok'],
      'นครราชสีมา': ['โคราช', 'นม'],
      'อุบลราชธานี': ['อุบล'],
      'อุดรธานี': ['อุดร'],
      'สุราษฎร์ธานี': ['สุราษ', 'สุราษฎร์', 'สุราษฏร์'],
      'นครศรีธรรมราช': ['คอน', 'นครศรี'],
      'พระนครศรีอยุธยา': ['อยุธยา'],
      'ประจวบคีรีขันธ์': ['ประจวบ'],
      'พังงา': ['พังงา'],
      'สงขลา': ['หาดใหญ่', 'สงขลา'],
      'ชลบุรี': ['พัทยา', 'ชลบุรี', 'บางแสน'],
      'เชียงราย': ['ชร'],
      'เชียงใหม่': ['ชม']
    };

    function getVotesForProvince(nameTh) {
      if (!votesDict) return 0;
      if (votesDict[nameTh] !== undefined) return votesDict[nameTh];

      const normFeature = normalizeThaiName(nameTh);
      let total = 0;

      for (const [key, count] of Object.entries(votesDict)) {
        const normKey = normalizeThaiName(key);
        if (!normKey) continue;

        if (normKey === normFeature) {
          total += count;
          continue;
        }

        if (normFeature.startsWith(normKey) || normKey.startsWith(normFeature)) {
          total += count;
          continue;
        }

        if (aliases[nameTh]) {
          if (aliases[nameTh].some(a => normKey === normalizeThaiName(a) || normKey.includes(a))) {
            total += count;
            continue;
          }
        }
      }
      return total;
    }

    // Calculate votes and total votes for each feature
    const featureVotes = new Map();
    let totalVotes = 0;
    geoData.features.forEach(f => {
      const nameTh = f.properties.name_th;
      const count = getVotesForProvince(nameTh);
      featureVotes.set(f, count);
      totalVotes += count;
    });

    // Color scale: 0% = neutral light slate, >0% = dynamic gradient from soft peach to deep ruby based on percent
    const voteColor = (votes) => {
      if (!votes || votes <= 0 || totalVotes <= 0) return '#e2e8f0';
      const pct = (votes / totalVotes) * 100;
      // t varies smoothly from 0.15 (light tint) to 1.0 (deep rich red)
      const t = Math.min(1, Math.max(0.15, Math.pow(pct / 100, 0.45)));
      const hue = Math.round(28 - t * 28);
      const sat = Math.round(80 + t * 18);
      const light = Math.round(80 - t * 48);
      return `hsl(${hue}, ${sat}%, ${light}%)`;
    };

    // Build SVG
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.style.cssText = 'display:block;background:#eef2f9;border-radius:12px;';

    // Tooltip
    const tip = document.createElement('div');
    tip.style.cssText = 'position:fixed;background:rgba(15,15,25,0.88);color:#fff;padding:6px 12px;border-radius:8px;font-size:13px;font-family:\'Noto Sans Thai\',sans-serif;pointer-events:none;display:none;z-index:9999;white-space:nowrap;box-shadow:0 4px 14px rgba(0,0,0,0.25);';
    document.body.appendChild(tip);

    geoData.features.forEach(f => {
      const nameTh = f.properties.name_th;
      const votes = featureVotes.get(f) || 0;
      const fill = voteColor(votes);
      const geom = f.geometry;
      const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
      const pct = totalVotes > 0 ? ((votes / totalVotes) * 100).toFixed(1).replace(/\.0$/, '') : 0;

      polys.forEach(rings => {
        const path = document.createElementNS(ns, 'path');
        path.setAttribute('d', coordsToPath(rings));
        path.setAttribute('fill', fill);
        path.setAttribute('stroke', '#fff');
        path.setAttribute('stroke-width', '0.7');
        path.style.cssText = 'cursor:pointer;transition:fill 0.15s ease, stroke-width 0.15s ease;';

        path.addEventListener('mouseenter', e => {
          path.setAttribute('fill', '#f59e0b');
          path.setAttribute('stroke-width', '1.4');
          tip.innerHTML = votes > 0 
            ? `<strong>${escapeHtml(nameTh)}</strong>: ${votes} คน <span style="color:#fb7185;font-weight:700;">(${pct}%)</span>` 
            : `<strong>${escapeHtml(nameTh)}</strong>: 0 คน`;
          tip.style.display = 'block';
        });
        path.addEventListener('mousemove', e => {
          tip.style.left = (e.clientX + 14) + 'px';
          tip.style.top = (e.clientY - 34) + 'px';
        });
        path.addEventListener('mouseleave', () => {
          path.setAttribute('fill', fill);
          path.setAttribute('stroke-width', '0.7');
          tip.style.display = 'none';
        });

        svg.appendChild(path);
      });
    });

    container.innerHTML = '';
    container.appendChild(svg);

    // Remove tooltip when presentation closes
    container.closest('#poll-presentation-panel')
      ?.querySelector('#close-presentation-btn')
      ?.addEventListener('click', () => tip.remove(), { once: true });
  }
  // ─────────────────────────────────────────────────────────────────────────

  function openPollPresentationModal(poll) {
    openPollModalId = poll.id;
    const boardMain = document.querySelector('.board-main');
    if (!boardMain) return;

    // Hide existing board-main children
    Array.from(boardMain.children).forEach(el => el.style.display = 'none');

    // Create inline presentation panel
    let panel = document.getElementById('poll-presentation-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'poll-presentation-panel';
      boardMain.appendChild(panel);
    }
    panel.style.cssText = 'display:flex;flex-direction:column;padding:20px 0;box-sizing:border-box;';

    updatePollPresentationContent(panel, poll);
  }

  function closePollPresentation() {
    openPollModalId = null;
    const boardMain = document.querySelector('.board-main');
    const panel = document.getElementById('poll-presentation-panel');
    if (panel) panel.remove();
    if (boardMain) Array.from(boardMain.children).forEach(el => el.style.display = '');
  }



  function updatePollPresentationContent(panel, poll) {
    const isLocation = poll.type === 'location';
    const totalVotes = isLocation
      ? Object.values(poll.votes || {}).reduce((a, b) => a + b, 0)
      : poll.votes.reduce((a, b) => a + b, 0);
    const isActive = poll.active === 1;

    if (isLocation) {
      // Live update: just re-render ranking + map
      const rankingList = panel.querySelector('#presentation-ranking-list');
      if (rankingList) {
        panel.querySelector('.total-votes-count').textContent = `ผู้โหวตรวม: ${totalVotes} คน`;
        const sortedVotes = Object.entries(poll.votes || {}).sort((a, b) => b[1] - a[1]);
        rankingList.innerHTML = '';
        sortedVotes.forEach(([loc, val], i) => {
          const percent = totalVotes > 0 ? Math.round((val / totalVotes) * 100) : 0;
          const medals = ['🥇', '🥈', '🥉'];
          const icon = i < 3 ? medals[i] : '📍';
          rankingList.innerHTML += `<div style="display:inline-flex;align-items:center;gap:6px;padding:7px 12px;background:#f5f5f5;border-radius:20px;font-size:14px;"><span style="font-weight:700;color:#1a1a1a;">${icon} ${escapeHtml(loc)}</span><span style="color:#888;">${val} คน</span><strong style="color:#ff1744;">${percent}%</strong></div>`;
        });
        if (sortedVotes.length === 0) rankingList.innerHTML = `<p style="font-size:14px;color:#888;">ยังไม่มีผู้ตอบโพล</p>`;

        // Re-render SVG map
        const mapDiv = panel.querySelector('#presentation-map');
        if (mapDiv && window._cachedGeoData) _renderProvincesSVG(mapDiv, window._cachedGeoData, poll.votes || {});
        return;
      }

      // First render
      panel.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;padding-bottom:12px;border-bottom:1px solid #eee;margin-bottom:14px;">
          <button id="close-presentation-btn" style="background:none;border:1px solid #ddd;border-radius:8px;padding:6px 14px;cursor:pointer;font-size:14px;color:#555;">← กลับ</button>
          <span class="status-badge ${isActive ? 'active' : 'inactive'}" style="font-size:13px;padding:6px 12px;">
            ${isActive ? '● กำลังเปิดโหวต' : '● ปิดโหวต'}
          </span>
          <span class="total-votes-count" style="font-size:14px;color:#666;">ผู้โหวตรวม: ${totalVotes} คน</span>
          <span style="font-size:15px;font-weight:700;color:#1a1a1a;margin-left:8px;font-family:'Noto Serif Thai',serif;">${escapeHtml(poll.question)}</span>
        </div>
        <div id="presentation-map" style="width:100%;flex:1;border-radius:14px;overflow:hidden;background:#eef2f9;min-height:520px;"></div>
        <div style="margin-top:14px;">
          <h3 style="margin:0 0 8px;font-size:14px;color:#555;font-weight:700;">🏆 อันดับที่มา</h3>
          <div id="presentation-ranking-list" style="display:flex;flex-wrap:wrap;gap:8px;"></div>
        </div>
      `;

      panel.querySelector('#close-presentation-btn').addEventListener('click', closePollPresentation);

      // Fill ranking list
      const rl = panel.querySelector('#presentation-ranking-list');
      const sv = Object.entries(poll.votes || {}).sort((a, b) => b[1] - a[1]);
      sv.forEach(([loc, val], i) => {
        const percent = totalVotes > 0 ? Math.round((val / totalVotes) * 100) : 0;
        const medals = ['🥇', '🥈', '🥉'];
        const icon = i < 3 ? medals[i] : '📍';
        rl.innerHTML += `<div style="display:inline-flex;align-items:center;gap:6px;padding:7px 12px;background:#f5f5f5;border-radius:20px;font-size:14px;"><span style="font-weight:700;color:#1a1a1a;">${icon} ${escapeHtml(loc)}</span><span style="color:#888;">${val} คน</span><strong style="color:#ff1744;">${percent}%</strong></div>`;
      });
      if (sv.length === 0) rl.innerHTML = `<p style="font-size:14px;color:#888;">ยังไม่มีผู้ตอบโพล</p>`;

      // Render SVG map
      fetch(`${API_BASE}/asset/provinces.geojson`)
        .then(r => r.json())
        .then(geoData => _renderProvincesSVG(panel.querySelector('#presentation-map'), geoData, poll.votes || {}));

      window._refreshSVGMap = (updatedPoll) => updatePollPresentationContent(panel, updatedPoll);

    } else {
      // Standard poll — also inline, no modal wrapper
      let optionsHtml = '';
      poll.options.forEach((opt, idx) => {
        const votes = poll.votes[idx];
        const percent = totalVotes > 0 ? Math.round((votes / totalVotes) * 100) : 0;
        optionsHtml += `
          <div style="margin-bottom:20px;">
            <div style="display:flex;justify-content:space-between;font-size:18px;font-weight:bold;color:#1a1a1a;margin-bottom:8px;">
              <span>${escapeHtml(opt)}</span>
              <span>${percent}% (${votes} คน)</span>
            </div>
            <div class="board-poll-bar-bg" style="height:26px;border-radius:6px;">
              <div class="board-poll-bar-fill" style="width:${percent}%;height:100%;border-radius:6px 0 0 6px;transition:width 0.5s ease-out;"></div>
            </div>
          </div>`;
      });

      panel.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;padding-bottom:14px;border-bottom:1px solid #eee;margin-bottom:18px;">
          <button id="close-presentation-btn" style="background:none;border:1px solid #ddd;border-radius:8px;padding:6px 14px;cursor:pointer;font-size:14px;color:#555;">← กลับ</button>
          <span class="status-badge ${isActive ? 'active' : 'inactive'}" style="font-size:13px;padding:6px 12px;">
            ${isActive ? '● กำลังเปิดโหวต' : '● ปิดโหวต'}
          </span>
          <span style="font-size:14px;color:#666;">ผู้โหวตรวม: ${totalVotes} คน</span>
        </div>
        <h1 style="font-size:30px;line-height:1.4;color:#1a1a1a;margin:0 0 28px;font-family:'Noto Serif Thai',serif;">${escapeHtml(poll.question)}</h1>
        <div style="display:flex;flex-direction:column;gap:4px;width:100%;">${optionsHtml}</div>
      `;
      panel.querySelector('#close-presentation-btn').addEventListener('click', closePollPresentation);
    }
  }



  // Modal สร้างโพล
  function openCreatePollModal() {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = `
      <div class="modal" style="max-width: 520px; position: relative;">
        <button class="modal-close-btn" id="close-modal-x">✕</button>
        <h2 style="font-size: 22px; color: #1a1a1a; margin-bottom: 20px; font-family: 'Noto Serif Thai', serif;">สร้างโพลสำรวจใหม่</h2>
        
        <div class="field" style="margin-bottom: 16px;">
          <label>ประเภทโพล</label>
          <select id="poll-type-select" style="width: 100%; height: 42px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.15); padding: 0 10px; font-size: 15px; background: white; font-family: inherit;">
            <option value="standard">โพลทั่วไปแบบหลายตัวเลือก</option>
            <option value="location">โพลแผนที่ระบุที่มา/ที่ตั้ง</option>
          </select>
        </div>

        <div class="field" style="margin-bottom: 16px;">
          <label>คำถามโพลล์</label>
          <input type="text" id="poll-q" placeholder="เช่น คุณเดินทางมาจากที่ไหน?" autocomplete="off" style="width: 100%;">
        </div>
        
        <div id="standard-opts-container" class="field" style="margin-bottom: 16px;">
          <label>ตัวเลือกคำตอบ</label>
          <div id="modal-poll-opts-container">
            <div class="poll-input-option-row">
              <input type="text" class="poll-opt-input" placeholder="ตัวเลือกที่ 1" autocomplete="off">
            </div>
            <div class="poll-input-option-row">
              <input type="text" class="poll-opt-input" placeholder="ตัวเลือกที่ 2" autocomplete="off">
            </div>
          </div>
          <button class="btn btn-ghost" id="add-opt-btn" style="width: auto; padding: 6px 12px; font-size: 13px; margin-top: 8px;">+ เพิ่มตัวเลือก</button>
        </div>

        <div id="location-scope-container" style="display: none; flex-direction: column; gap: 16px; margin-bottom: 16px;">
          <div class="field">
            <label>ระดับขอบเขตผลลัพธ์</label>
            <select id="location-level-select" style="width: 100%; height: 42px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.15); padding: 0 10px; font-size: 15px; background: white; font-family: inherit;">
              <option value="global">ระดับโลก (ระบุประเทศ)</option>
              <option value="country">ระดับประเทศ (ระบุจังหวัด)</option>
              <option value="region">ระดับภูมิภาค (ระบุภูมิภาค)</option>
              <option value="province">ระดับจังหวัด (ระบุจังหวัด)</option>
              <option value="district">ระดับอำเภอ (ระบุอำเภอ)</option>
            </select>
          </div>
          
          <div id="scope-cascading-selectors" style="display: flex; flex-direction: column; gap: 12px;">
            <!-- Cascading dropdowns will be rendered here dynamically -->
          </div>
        </div>
        
        <div class="modal-actions" style="margin-top: 24px;">
          <button class="btn btn-ghost" id="cancel-create-poll" style="padding: 12px 24px; font-size: 15px;">ยกเลิก</button>
          <button class="btn btn-primary" id="save-poll-btn" style="padding: 12px 24px; font-size: 15px; background: #208838 !important; color: white !important;">สร้างโพล</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const typeSelect = overlay.querySelector('#poll-type-select');
    const stdContainer = overlay.querySelector('#standard-opts-container');
    const locContainer = overlay.querySelector('#location-scope-container');
    const cascadeArea = overlay.querySelector('#scope-cascading-selectors');
    const levelSelect = overlay.querySelector('#location-level-select');

    typeSelect.addEventListener('change', () => {
      if (typeSelect.value === 'location') {
        stdContainer.style.display = 'none';
        locContainer.style.display = 'flex';
        renderCascadingSelectors();
      } else {
        stdContainer.style.display = 'block';
        locContainer.style.display = 'none';
      }
    });

    levelSelect.addEventListener('change', () => {
      renderCascadingSelectors();
    });

    function renderCascadingSelectors() {
      const level = levelSelect.value;
      cascadeArea.innerHTML = '';

      if (level === 'global') {
        return;
      }

      // Country dropdown
      const countryField = document.createElement('div');
      countryField.className = 'field';
      countryField.innerHTML = `
        <label>ประเทศ</label>
        <select id="scope-country" style="width: 100%; height: 42px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.15); padding: 0 10px; font-size: 15px; background: white; font-family: inherit;">
          <option value="ไทย">ไทย</option>
        </select>
      `;
      cascadeArea.appendChild(countryField);

      if (level === 'region' || level === 'province' || level === 'district') {
        // Region dropdown
        const regionField = document.createElement('div');
        regionField.className = 'field';
        let regionOptions = '';
        if (level === 'province' || level === 'district') {
          regionOptions += `<option value="all">ทั้งหมด (ทุกภูมิภาค)</option>`;
        }
        THAI_REGIONS.forEach(r => {
          regionOptions += `<option value="${r}">${r}</option>`;
        });
        regionField.innerHTML = `
          <label>ภูมิภาค</label>
          <select id="scope-region" style="width: 100%; height: 42px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.15); padding: 0 10px; font-size: 15px; background: white; font-family: inherit;">
            ${regionOptions}
          </select>
        `;
        cascadeArea.appendChild(regionField);

        const regionSelect = regionField.querySelector('#scope-region');

        if (level === 'province' || level === 'district') {
          // Province dropdown
          const provField = document.createElement('div');
          provField.className = 'field';
          provField.innerHTML = `
            <label>จังหวัด</label>
            <select id="scope-province" style="width: 100%; height: 42px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.15); padding: 0 10px; font-size: 15px; background: white; font-family: inherit;"></select>
          `;
          cascadeArea.appendChild(provField);
          const provSelect = provField.querySelector('#scope-province');

          const updateProvinces = () => {
            const selectedReg = regionSelect.value;
            provSelect.innerHTML = '';
            let filteredProvs = THAI_PROVINCES;
            if (selectedReg !== 'all') {
              filteredProvs = THAI_PROVINCES.filter(p => p.region === selectedReg);
            }
            filteredProvs.forEach(p => {
              provSelect.innerHTML += `<option value="${p.name}">${p.name}</option>`;
            });
          };

          regionSelect.addEventListener('change', updateProvinces);
          updateProvinces();
        }
      }
    }

    // Standard options add/remove handlers
    const container = overlay.querySelector('#modal-poll-opts-container');
    const addOptBtn = overlay.querySelector('#add-opt-btn');

    addOptBtn.addEventListener('click', () => {
      const rows = container.querySelectorAll('.poll-input-option-row');
      const nextIdx = rows.length + 1;

      const row = document.createElement('div');
      row.className = 'poll-input-option-row';
      row.innerHTML = `
        <input type="text" class="poll-opt-input" placeholder="ตัวเลือกที่ ${nextIdx}" autocomplete="off">
        <button class="remove-opt-btn">×</button>
      `;

      row.querySelector('.remove-opt-btn').addEventListener('click', () => row.remove());
      container.appendChild(row);
    });

    overlay.querySelector('#close-modal-x').addEventListener('click', () => overlay.remove());
    overlay.querySelector('#cancel-create-poll').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    overlay.querySelector('#save-poll-btn').addEventListener('click', async () => {
      const question = overlay.querySelector('#poll-q').value.trim();
      const pollType = typeSelect.value;

      if (!question) {
        alert('กรุณาป้อนคำถาม');
        return;
      }

      let options = [];
      let scope = null;

      if (pollType === 'standard') {
        const optInputs = overlay.querySelectorAll('.poll-opt-input');
        options = Array.from(optInputs).map(i => i.value.trim()).filter(val => val !== '');
        if (options.length < 2) {
          alert('กรุณาป้อนตัวเลือกอย่างน้อย 2 ตัวเลือก');
          return;
        }
      } else {
        const level = levelSelect.value;
        const countryEl = overlay.querySelector('#scope-country');
        const regionEl = overlay.querySelector('#scope-region');
        const provEl = overlay.querySelector('#scope-province');

        scope = JSON.stringify({
          level,
          country: countryEl ? countryEl.value : null,
          region: regionEl ? regionEl.value : null,
          province: provEl ? provEl.value : null
        });
      }

      try {
        const res = await fetch(`${API_BASE}/api/polls`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, options, type: pollType, scope })
        });
        if (!res.ok) throw new Error('Create poll failed');
        overlay.remove();
        showToast('สร้างโพลสำรวจเรียบร้อย');
        fetchPolls();
        fetchActivePoll();
      } catch (err) {
        console.error(err);
        showToast('สร้างไม่สำเร็จ');
      }
    });
  }

  // ---------- Realtime Listener (Global) ----------

  let wsClient = null;
  let realtimePollTimer = null;

  function refreshRealtimeData(force = false) {
    if (!isAdminAuthed) return;

    const adminVisible = !viewAdmin.classList.contains('hidden');
    if (!adminVisible && !force) return;

    fetchMessages();
    fetchPolls().then(() => {
      if (openPollModalId) {
        const updatedPoll = allPolls.find(p => p.id === openPollModalId);
        const panel = document.getElementById('poll-presentation-panel');
        if (updatedPoll && panel) {
          updatePollPresentationContent(panel, updatedPoll);
        }
      }
    });
    fetchActivePoll();
  }

  function startRealtimeListener() {
    if (wsClient) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${API_BASE}/api/messages/ws`;

    wsClient = new WebSocket(wsUrl);

    wsClient.onmessage = (event) => {
      if (event.data === 'UPDATE') {
        refreshRealtimeData(true);
      } else if (event.data.startsWith('USERS:')) {
        const count = event.data.split(':')[1];
        const numEl = document.getElementById('user-count-num');
        if (numEl) numEl.textContent = count;
      }
    };

    wsClient.onerror = () => {
      if (wsClient) {
        wsClient.close();
      }
    };

    wsClient.onclose = () => {
      wsClient = null;
      setTimeout(() => {
        if (!wsClient) {
          startRealtimeListener();
        }
      }, 3000);
    };
  }

  function startRealtimePolling() {
    if (realtimePollTimer) return;

    realtimePollTimer = setInterval(() => {
      if (isAdminAuthed && !viewAdmin.classList.contains('hidden')) {
        refreshRealtimeData();
      }
    }, 1500);
  }

  function stopRealtimePolling() {
    if (realtimePollTimer) {
      clearInterval(realtimePollTimer);
      realtimePollTimer = null;
    }
  }

  // ---------- router ----------
  const viewSend = document.getElementById('view-send');
  const viewGate = document.getElementById('view-gate');
  const viewAdmin = document.getElementById('view-admin');
  let isAdminAuthed = true; // Handled securely via server-side Django @login_required

  function showOnly(el) {
    [viewSend, viewGate, viewAdmin].forEach(v => {
      if (v) v.classList.add('hidden');
    });
    if (el) el.classList.remove('hidden');
  }

  function route() {
    const hash = window.location.hash;
    const isDocAdmin = window.title?.includes('แอดมิน') || document.title?.includes('แอดมิน') || window.location.pathname.includes('/admin');

    if (hash === '#admin' || isDocAdmin) {
      document.body.classList.add('admin-theme');
      showOnly(viewAdmin);
      startRealtimePolling();
      refreshRealtimeData(true);

      // Update sidebar info
      const host = window.location.host;
      const clientUrl = `${window.location.protocol}//${host}${API_BASE}/`;
      const joinEl = document.getElementById('join-url');
      if (joinEl) joinEl.textContent = `${host}${API_BASE}/`;

      const qrImg = document.getElementById('qr-img');
      if (qrImg) {
        qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(clientUrl)}`;
        qrImg.onclick = () => {
          openExpandedQR(clientUrl);
        };
      }
    } else {
      document.body.classList.remove('admin-theme');
      showOnly(viewSend);
      stopRealtimePolling();
      fetchActivePoll();
    }
  }

  window.addEventListener('hashchange', route);

  // ---------- User/Sender Actions ----------

  const textInput = document.getElementById('f-text');
  const nameInput = document.getElementById('f-name');
  const counter = document.getElementById('f-counter');
  const submitBtn = document.getElementById('f-submit');
  const sendForm = document.getElementById('send-form');
  const sendCard = document.getElementById('send-card');

  function updateFormState() {
    if (!textInput || !counter || !submitBtn) return;
    const len = textInput.value.length;
    counter.textContent = `${len}/1000`;
    if (len > 0) {
      submitBtn.disabled = false;
      counter.classList.remove('danger-text');
    } else {
      submitBtn.disabled = true;
    }
  }

  if (textInput) {
    textInput.addEventListener('input', updateFormState);
  }

  if (sendForm) {
    sendForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      const name = nameInput.value.trim() || 'มังกรผู้เร้าใจ';
      const text = textInput.value.trim();
      if (!text) return;

      submitBtn.disabled = true;
      submitBtn.textContent = 'กำลังปล่อย…';

      try {
        await sendMessageToAPI(name, text);
        if (isAdminAuthed && !viewAdmin.classList.contains('hidden')) {
          refreshRealtimeData(true);
        }
        // Success screen
        sendCard.innerHTML = `
          <div style="text-align:center;padding:20px 0;">
            <span style="font-size:64px;display:block;margin-bottom:20px;animation:float 3s ease-in-out infinite;">🏮</span>
            <h1 style="font-size:24px;margin-bottom:12px;">ปล่อยข้อความเรียบร้อย</h1>
            <p style="color:var(--text-soft);margin-bottom:24px;font-size:15px;">ข้อความของคุณได้ลอยไปต่อหน้าแอดมินแล้ว</p>
            <button class="btn btn-primary" id="btn-reload" style="max-width:180px;margin:0 auto;">เขียนข้อความใหม่</button>
          </div>
        `;
        document.getElementById('btn-reload').addEventListener('click', function () {
          window.location.reload();
        });
      } catch (err) {
        console.error('send error', err);
        submitBtn.disabled = false;
        submitBtn.textContent = 'ปล่อยข้อความ';
        showToast('ส่งไม่สำเร็จ ลองใหม่อีกครั้ง');
      }
    });
  }

  // ---------- admin board ----------
  const noteList = document.getElementById('note-list');
  const emptyState = document.getElementById('admin-empty');

  function renderAdmin() {
    const list = currentList;

    const headerCount = document.getElementById('header-count');
    if (headerCount) headerCount.textContent = `${list.length} 💬`;

    if (list.length === 0) {
      if (emptyState) emptyState.classList.remove('hidden');
      if (noteList) noteList.innerHTML = '';
      return;
    }
    if (emptyState) emptyState.classList.add('hidden');

    const unanswered = list.filter(m => !m.answered);
    const answered = list.filter(m => m.answered);

    let html = '';

    // Render Unanswered messages
    unanswered.forEach((m, i) => {
      if (i === 1) {
        html += '<div style="text-align:center; font-size:13px; color:#777; margin: 10px 0;">Latest question</div>';
      }
      const isHighlight = i === 0 ? 'highlight-card' : '';
      html += `
      <div class="note-card board-card ${isHighlight}" data-id="${m.id}">
        <div class="note-top board-top">
          <span class="board-author">👤 ${escapeHtml(m.name)}</span>
          <span class="board-time mono">${formatTime(m.ts)}</span>
        </div>
        <div class="note-preview board-text">${escapeHtml(m.text)}</div>
      </div>
      `;
    });

    // Render Answered messages section at the bottom
    if (answered.length > 0) {
      html += '<div style="margin: 30px 4px 10px; font-weight: bold; font-size: 15px; color: #555; border-top: 1px solid rgba(0,0,0,0.06); padding-top: 20px;">คำถามที่ตอบแล้ว</div>';
      answered.forEach(m => {
        html += `
        <div class="note-card board-card answered-card" data-id="${m.id}">
          <div class="note-top board-top">
            <span class="board-author">👤 ${escapeHtml(m.name)} (ตอบแล้ว)</span>
            <span class="board-time mono">${formatTime(m.ts)}</span>
          </div>
          <div class="note-preview board-text">${escapeHtml(m.text)}</div>
        </div>
        `;
      });
    }

    if (noteList) noteList.innerHTML = html;

    document.querySelectorAll('.note-card').forEach(card => {
      card.addEventListener('click', () => {
        const id = card.getAttribute('data-id');
        const msg = list.find(m => m.id === id);
        if (msg) openReadModal(msg);
      });
    });
  }

  function openExpandedQR(url) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = `
      <div class="modal" style="position: relative; max-width: 520px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 20px;">
        <button class="modal-close-btn" id="close-modal-x">✕</button>
        <h2 style="font-size: 24px; color: #1a1a1a; margin: 0; font-family: 'Noto Serif Thai', serif;">สแกนเพื่อส่งข้อความ</h2>
        <div style="background: #ffffff; padding: 12px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); display: inline-block;">
          <img src="https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=${encodeURIComponent(url)}" style="display: block; width: 100%; max-width: 360px;" alt="QR Code Large" />
        </div>
        <div style="font-size: 18px; font-weight: bold; color: #555; word-break: break-all;">
          ${window.location.host}
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('#close-modal-x').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  }

  async function deleteMessage(msg) {
    const card = document.querySelector(`.note-card[data-id="${msg.id}"]`);
    if (card) {
      card.classList.add('leaving');
      await new Promise(r => setTimeout(r, 500));
    }
    try {
      await deleteMessageFromAPI(msg.id);
      showToast('ข้อความลอยจากไปแล้ว');
      if (isAdminAuthed) await fetchMessages();
    } catch (err) {
      console.error('delete error', err);
      showToast('ลบไม่สำเร็จ ลองใหม่อีกครั้ง');
    }
  }

  function openReadModal(msg) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';

    const originalRemove = overlay.remove;
    overlay.remove = function () {
      stopMessageCue();
      originalRemove.call(this);
    };

    const answerBtnHtml = !msg.answered
      ? `<button class="btn btn-primary" id="answer-msg">ตอบแล้ว</button>`
      : ``;

    overlay.innerHTML = `
      <div class="modal" style="position: relative;">
        <button class="modal-close-btn" id="close-modal-x">✕</button>
        <div class="modal-top">
          <h2 style="font-family: 'Noto Serif Thai', serif;">ข้อความจาก ${escapeHtml(msg.name)}</h2>
        </div>
        <div class="ts">ส่งเมื่อ ${formatTime(msg.ts)}</div>
        <div class="full-text">${escapeHtml(msg.text)}</div>
        <div class="modal-actions">
          <button class="btn btn-ghost btn-danger-outline" id="close-msg">ลบข้อความ</button>
          ${answerBtnHtml}
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    if (!msg.answered) {
      playMessageCue(msg.text, msg.id);
    }

    overlay.querySelector('#close-modal-x').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    overlay.querySelector('#close-msg').addEventListener('click', () => {
      overlay.remove();
      if (msg.answered) {
        deleteMessage(msg);
      } else {
        openConfirmDialog(msg);
      }
    });

    const answerBtn = overlay.querySelector('#answer-msg');
    if (answerBtn) {
      answerBtn.addEventListener('click', async () => {
        overlay.remove();
        try {
          await answerMessageInAPI(msg.id);
          showToast('ทำเครื่องหมายว่าตอบแล้ว');
          if (isAdminAuthed) await fetchMessages();
        } catch (err) {
          console.error('answer error', err);
          showToast('ตอบไม่สำเร็จ ลองใหม่อีกครั้ง');
        }
      });
    }
  }

  function openConfirmDialog(msg) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = `
      <div class="modal confirm-body">
        <h2 style="font-family: 'Noto Serif Thai', serif;">ปล่อยข้อความนี้ไปหรือยัง?</h2>
        <p>เมื่อยืนยัน ข้อความนี้จะลอยจากไปและไม่สามารถเรียกคืนได้</p>
        <div class="modal-actions">
          <button class="btn btn-ghost" id="cancel-confirm">ยกเลิก</button>
          <button class="btn btn-primary" id="confirm-close" style="background:linear-gradient(180deg,#E8938A,var(--danger));color:#2a1210;">ยืนยัน ปล่อยไป</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('#cancel-confirm').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector('#confirm-close').addEventListener('click', () => {
      overlay.remove();
      deleteMessage(msg);
    });
  }

  function showToast(text) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = text;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
  }

  // ---------- Tab Binding Inits ----------

  // Init sender tabs
  const senderTabQa = document.getElementById('sender-tab-qa');
  const senderTabPoll = document.getElementById('sender-tab-poll');
  const senderQaContent = document.getElementById('sender-qa-content');
  const senderPollContent = document.getElementById('sender-poll-content');

  if (senderTabQa && senderTabPoll) {
    senderTabQa.addEventListener('click', () => {
      senderTabQa.classList.add('active');
      senderTabPoll.classList.remove('active');
      senderQaContent.classList.remove('hidden');
      senderPollContent.classList.add('hidden');
    });
    senderTabPoll.addEventListener('click', () => {
      senderTabPoll.classList.add('active');
      senderTabQa.classList.remove('active');
      senderPollContent.classList.remove('hidden');
      senderQaContent.classList.add('hidden');
      fetchActivePoll();
    });
  }

  // Init admin tabs
  const adminTabQa = document.getElementById('admin-tab-qa');
  const adminTabPoll = document.getElementById('admin-tab-poll');
  const adminQaSection = document.getElementById('admin-qa-section');
  const adminPollSection = document.getElementById('admin-poll-section');

  if (adminTabQa && adminTabPoll) {
    adminTabQa.addEventListener('click', () => {
      adminTabQa.classList.add('active');
      adminTabPoll.classList.remove('active');
      adminQaSection.classList.remove('hidden');
      adminPollSection.classList.add('hidden');
      fetchMessages();
    });
    adminTabPoll.addEventListener('click', () => {
      adminTabPoll.classList.add('active');
      adminTabQa.classList.remove('active');
      adminPollSection.classList.remove('hidden');
      adminQaSection.classList.add('hidden');
      fetchPolls();
    });
  }

  // Bind create poll button
  const createPollBtn = document.getElementById('create-poll-btn');
  if (createPollBtn) {
    createPollBtn.addEventListener('click', openCreatePollModal);
  }

  // ---------- SSE & Real-time Listeners ----------
  let pollEventSource = null;
  function startRealtimeListener() {
    // 1. Server-Sent Events (SSE) stream for Poll & Vote Updates
    try {
      if (pollEventSource) {
        pollEventSource.close();
      }
      const sseUrl = `${API_BASE}/api/polls/events`;
      pollEventSource = new EventSource(sseUrl);

      pollEventSource.onmessage = (event) => {
        if (event.data === 'CONNECTED') {
          console.log('[SSE] Connected to poll real-time stream');
          return;
        }
        console.log('[SSE] Real-time poll update received');
        fetchActivePoll();
        if (isAdminAuthed) {
          fetchPolls();
          fetchMessages();
        }
      };

      pollEventSource.onerror = (err) => {
        console.warn('[SSE] EventSource reconnecting...', err);
      };
    } catch (err) {
      console.warn('[SSE] EventSource init error:', err);
    }

    // 2. WebSocket for Admin Messages
    try {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${proto}//${window.location.host}${API_BASE}/api/messages/ws`;
      const ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        if (event.data === 'UPDATE') {
          fetchMessages();
          fetchPolls();
          fetchActivePoll();
        }
      };
    } catch (e) {
      // WS optional
    }
  }

  // ---------- init ----------
  if ((window.location.pathname.includes('admin.html') || window.location.pathname.endsWith('/admin') || window.location.pathname.endsWith('/admin/')) && window.location.hash !== '#admin') {
    window.location.hash = '#admin';
  }

  startRealtimeListener();
  route();
  updateFormState();

})();