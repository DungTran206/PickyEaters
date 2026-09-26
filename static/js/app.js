/**
 * PERSONAL FOOD AGENT - CLIENT APPLICATION v2.1
 * Fixes:
 *  - onclick XSS → event delegation with data-* attrs
 *  - district chip active matching (case-insensitive includes)
 *  - appendWelcomeCard() updates existing DOM refs instead of innerHTML replace
 *  - candidates === 0 → renders empty state
 *  - reasoning split handles both '\n' and ' • ' separators
 *  - drawer animation now works via visibility/opacity (not display)
 *  - skeleton card loading state while agent is thinking
 */

document.addEventListener('DOMContentLoaded', () => {
  // ─── Element References ───────────────────────────────────────────────────
  const messagesContainer = document.getElementById('messagesContainer');
  const chatForm          = document.getElementById('chatForm');
  const chatInput         = document.getElementById('chatInput');
  const sendBtn           = document.getElementById('sendBtn');
  const userSelector      = document.getElementById('userSelector');
  const resetChatBtn      = document.getElementById('resetChatBtn');

  // Location & Identity
  const userNameInput    = document.getElementById('userNameInput');
  const userAddressInput = document.getElementById('userAddressInput');
  const saveLocationBtn  = document.getElementById('saveLocationBtn');
  const districtChips    = document.querySelectorAll('.district-chip');
  const radiusBadge      = document.getElementById('radiusBadge');
  const radiusBadgeText  = document.getElementById('radiusBadgeText');

  // Welcome card dynamic spans (may be replaced on reset, so always query fresh via helper)
  const getWelcomeNameEl    = () => document.getElementById('welcomeUserName');
  const getWelcomeAddressEl = () => document.getElementById('welcomeUserAddress');

  // Preferences Drawer
  const openPrefBtn       = document.getElementById('openPrefBtn');
  const closePrefBtn      = document.getElementById('closePrefBtn');
  const prefDrawerOverlay = document.getElementById('prefDrawerOverlay');
  const prefNameInput     = document.getElementById('prefNameInput');
  const prefAddressInput  = document.getElementById('prefAddressInput');
  const budgetInput       = document.getElementById('budgetInput');
  const budgetValue       = document.getElementById('budgetValue');
  const ratingInput       = document.getElementById('ratingInput');
  const ratingValue       = document.getElementById('ratingValue');
  const cuisinesContainer = document.getElementById('cuisinesContainer');
  const flavorsContainer  = document.getElementById('flavorsContainer');
  const dislikedTags      = document.getElementById('dislikedTags');
  const newIngredientInput = document.getElementById('newIngredientInput');
  const addIngredientBtn  = document.getElementById('addIngredientBtn');
  const savePrefBtn       = document.getElementById('savePrefBtn');
  const toastContainer    = document.getElementById('toastContainer');

  // ─── State ────────────────────────────────────────────────────────────────
  let currentUserId = userSelector.value;
  let isSending     = false;
  // Delivery location: no default. Typed address (lat/lng null) or a map pin (lat/lng set).
  let deliveryLocation = { address: '', lat: null, lng: null };
  const NO_ADDRESS_TEXT = 'chưa có, nhập địa chỉ ở trên hoặc chọn trên bản đồ';
  let currentPreferences = {
    name: '',
    address: '',
    budget: 80000,
    minimum_rating: 4.3,
    preferred_cuisines: [],
    preferred_flavors: [],
    disliked_ingredients: []
  };

  // ─── INIT ─────────────────────────────────────────────────────────────────
  renderWelcomeCard();
  loadUserProfile(currentUserId);

  // User Switcher
  userSelector.addEventListener('change', () => {
    currentUserId = userSelector.value;
    loadUserProfile(currentUserId);
    showToast(`Đã chuyển sang hồ sơ: ${currentUserId}`);
  });

  // Save Location Button
  saveLocationBtn.addEventListener('click', async () => {
    const name = userNameInput.value.trim() || 'Bạn';
    if (!deliveryLocation.address && deliveryLocation.lat === null) {
      showToast('Nhập địa chỉ có quận/huyện, hoặc chọn trên bản đồ.', 'error');
      return;
    }

    try {
      saveLocationBtn.disabled = true;
      saveLocationBtn.textContent = 'Đang lưu…';

      if (await saveLocation(name)) {
        const nameEl = getWelcomeNameEl();
        if (nameEl) nameEl.textContent = name;
        if (prefNameInput) prefNameInput.value = name;
        showToast('Đã lưu địa chỉ.');
      }
    } catch (err) {
      showToast(`Lỗi kết nối: ${err.message}`, 'error');
    } finally {
      saveLocationBtn.disabled = false;
      saveLocationBtn.textContent = 'Lưu địa chỉ';
    }
  });

  // Quick District Chips — FIX: use textContent comparison properly
  districtChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const dist = chip.getAttribute('data-district');
      setDeliveryLocation(dist, null, null);
      showToast(`Giao đến ${dist}. Bấm "Lưu địa chỉ" để giữ cho lần sau.`);
    });
  });

  // FIX: Sync district chip active state by matching data-district attribute
  function syncDistrictChips(address) {
    districtChips.forEach(chip => {
      const chipDistrict = chip.getAttribute('data-district') || '';
      // Check if the address contains the chip's district value
      const isActive = address && chipDistrict && address.toLowerCase().includes(chipDistrict.split(',')[0].trim().toLowerCase());
      chip.classList.toggle('active', isActive);
    });
  }

  // Single place that updates the delivery location everywhere in the UI.
  function setDeliveryLocation(address, lat, lng) {
    deliveryLocation = { address: address || '', lat: lat ?? null, lng: lng ?? null };
    userAddressInput.value = deliveryLocation.address;
    if (prefAddressInput) prefAddressInput.value = deliveryLocation.address;
    const addressEl = getWelcomeAddressEl();
    if (addressEl) addressEl.textContent = deliveryLocation.address || NO_ADDRESS_TEXT;
    syncDistrictChips(deliveryLocation.address);
    openMapBtn.classList.toggle('active', deliveryLocation.lat !== null);
  }

  // Typing an address replaces any map pin.
  userAddressInput.addEventListener('input', () => {
    deliveryLocation = { address: userAddressInput.value.trim(), lat: null, lng: null };
    openMapBtn.classList.remove('active');
    syncDistrictChips(deliveryLocation.address);
  });

  // POST the current delivery location (+ name). Returns true on success.
  async function saveLocation(name) {
    const body = { name, address: deliveryLocation.address };
    if (deliveryLocation.lat !== null) {
      body.latitude = deliveryLocation.lat;
      body.longitude = deliveryLocation.lng;
    }
    const res = await fetch(`/api/user/${currentUserId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || 'Lỗi khi lưu vị trí. Vui lòng thử lại.', 'error');
      return false;
    }
    const pref = await res.json();
    setDeliveryLocation(pref.address, pref.latitude, pref.longitude);
    return true;
  }

  // ─── MAP PICKER (Leaflet + Esri street tiles) ──────────────────────────
  const openMapBtn       = document.getElementById('openMapBtn');
  const mapModal         = document.getElementById('mapModal');
  const closeMapBtn      = document.getElementById('closeMapBtn');
  const confirmMapBtn    = document.getElementById('confirmMapBtn');
  const useMyLocationBtn = document.getElementById('useMyLocationBtn');
  const mapPickInfo      = document.getElementById('mapPickInfo');
  let map = null;
  let pickMarker = null;
  let pendingPick = null;   // { lat, lng, district }

  openMapBtn.addEventListener('click', openMapPicker);
  closeMapBtn.addEventListener('click', closeMapPicker);
  mapModal.addEventListener('click', e => { if (e.target === mapModal) closeMapPicker(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !mapModal.hidden) closeMapPicker(); });

  function openMapPicker() {
    if (typeof L === 'undefined') {
      showToast('Không tải được bản đồ (cần kết nối internet). Bạn hãy nhập địa chỉ nhé.', 'error');
      return;
    }
    mapModal.hidden = false;
    if (!map) {
      map = L.map('mapCanvas');
      // Esri World Street Map: readable Vietnamese street/ward labels, no API key.
      // (tile.openstreetmap.org is not reachable on every network; CARTO now requires a key.)
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> — Source: Esri, HERE, Garmin, USGS, OpenStreetMap contributors'
      }).addTo(map);
      map.on('click', e => pickPoint(e.latlng.lat, e.latlng.lng));
    }
    // Start at the saved pin if any; otherwise show the whole country (a view, not an address).
    if (deliveryLocation.lat !== null) {
      map.setView([deliveryLocation.lat, deliveryLocation.lng], 15);
      pickPoint(deliveryLocation.lat, deliveryLocation.lng);
    } else {
      map.setView([16.0, 106.3], 6);
    }
    setTimeout(() => map.invalidateSize(), 50);   // the map was hidden while initialising
  }

  function closeMapPicker() {
    mapModal.hidden = true;
    openMapBtn.focus();
  }

  async function pickPoint(lat, lng) {
    if (pickMarker) pickMarker.setLatLng([lat, lng]);
    else pickMarker = L.marker([lat, lng]).addTo(map);
    pendingPick = { lat, lng, district: '' };
    confirmMapBtn.disabled = false;
    const coordText = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    mapPickInfo.textContent = `Đã chọn: ${coordText} — đang xác định khu vực...`;
    try {
      const res = await fetch(`/api/locate?lat=${lat}&lng=${lng}`);
      const info = await res.json();
      if (!pendingPick || pendingPick.lat !== lat || pendingPick.lng !== lng) return;  // a newer pick won
      pendingPick.district = info.district;
      mapPickInfo.textContent = info.in_coverage
        ? `Đã chọn: gần ${info.district} (${coordText})`
        : `Đã chọn: ${coordText} — ngoài khu vực có dữ liệu quán (một số quận Hà Nội và TP.HCM), có thể không tìm được món.`;
    } catch {
      mapPickInfo.textContent = `Đã chọn: ${coordText}`;
    }
  }

  useMyLocationBtn.addEventListener('click', () => {
    if (!navigator.geolocation) {
      showToast('Trình duyệt không hỗ trợ lấy vị trí hiện tại.', 'error');
      return;
    }
    mapPickInfo.textContent = 'Đang lấy vị trí hiện tại...';
    navigator.geolocation.getCurrentPosition(
      pos => {
        const { latitude, longitude } = pos.coords;
        map.setView([latitude, longitude], 16);
        pickPoint(latitude, longitude);
      },
      () => {
        mapPickInfo.textContent = 'Không lấy được vị trí hiện tại. Bạn hãy bấm lên bản đồ để chọn.';
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  confirmMapBtn.addEventListener('click', async () => {
    if (!pendingPick) return;
    const label = pendingPick.district
      ? `Vị trí trên bản đồ (gần ${pendingPick.district})`
      : 'Vị trí trên bản đồ';
    setDeliveryLocation(label, pendingPick.lat, pendingPick.lng);
    closeMapPicker();
    const saved = await saveLocation(userNameInput.value.trim() || 'Bạn');
    if (saved) showToast('Đã lưu chỗ giao hàng.');
  });

  // Reset Conversation
  resetChatBtn.addEventListener('click', () => {
    if (confirm('Bạn có muốn đặt lại cuộc trò chuyện về ban đầu không?')) {
      renderWelcomeCard();
      updateRadiusBadge(currentPreferences.preferred_distance || 5, false);
      showToast('Đã bắt đầu cuộc trò chuyện mới.');
    }
  });

  // Quick Prompt Chips (event delegation — works even after DOM changes)
  messagesContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (chip && !isSending) {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) {
        chatInput.value = prompt;
        sendMessage(prompt);
      }
    }
  });

  // FIX: Order button — event delegation with data-* instead of inline onclick
  messagesContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('.order-btn[data-restaurant]');
    if (btn) {
      e.preventDefault();
      const restaurant = btn.getAttribute('data-restaurant');
      const platform   = btn.getAttribute('data-platform');
      // The app cannot place orders itself; say so and tell the user where to go.
      showToast(`Chưa đặt trực tiếp được: mở ${platform} và tìm "${restaurant}".`);
    }
  });

  // Chat Submission
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text || isSending) return;
    sendMessage(text);
  });

  // ─── SEND MESSAGE ─────────────────────────────────────────────────────────
  async function sendMessage(text) {
    chatInput.value = '';
    isSending = true;
    sendBtn.disabled = true;

    const currentName    = userNameInput.value.trim() || 'Bạn';
    const currentAddress = deliveryLocation.address || 'vị trí của bạn';

    // Hide welcome card if still present
    const welcomeCard = document.getElementById('welcomeCard');
    if (welcomeCard) welcomeCard.style.display = 'none';

    appendUserMessage(text);
    scrollToBottom();

    // Show skeleton loading
    const skeletonRow = showSkeletonLoading();
    scrollToBottom();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          user_id: currentUserId,
          user_name: currentName,
          // Only send a location the user actually gave; the backend asks if there is none.
          user_address: deliveryLocation.address || null,
          user_lat: deliveryLocation.lat,
          user_lng: deliveryLocation.lng
        })
      });

      if (!response.ok) {
        throw new Error(`Server trả về lỗi ${response.status}`);
      }

      const data = await response.json();
      skeletonRow.remove();

      const radiusKm   = data.search_radius_km   || 5.0;
      const isExpanded = data.is_radius_expanded  || false;
      updateRadiusBadge(radiusKm, isExpanded);

      appendAgentResponse({
        responseText: data.response,
        toolCalls:    data.tool_calls  || [],
        candidates:   data.candidates  || [],
        radiusKm,
        isExpanded,
        userAddress: currentAddress
      });
      scrollToBottom();

      // If preferences were updated during conversation, sync drawer state
      const hasPrefUpdate = (data.tool_calls || []).some(tc => tc.tool === 'update_user_preference');
      if (hasPrefUpdate) loadUserProfile(currentUserId);

    } catch (err) {
      skeletonRow.remove();
      appendAgentResponse({
        responseText: `Không kết nối được máy chủ (${err.message}). Kiểm tra server đang chạy rồi gửi lại.`,
        toolCalls: [],
        candidates: [],
        radiusKm: 5.0,
        isExpanded: false,
        userAddress: currentAddress
      });
      scrollToBottom();
    } finally {
      isSending    = false;
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  // ─── UI RENDERING HELPERS ─────────────────────────────────────────────────

  const fmtKm  = km => Number(km).toLocaleString('vi-VN');
  const fmtVnd = n => `${Math.round(n || 0).toLocaleString('vi-VN')}đ`;
  const platformClass = pf => (pf || '').toLowerCase().includes('grab') ? 'grabfood' : 'shopeefood';

  function updateRadiusBadge(radiusKm, isExpanded) {
    radiusBadge.className = isExpanded ? 'radius-status expanded' : 'radius-status';
    radiusBadgeText.textContent = isExpanded
      ? `Đã mở rộng tới ${fmtKm(radiusKm)} km`
      : `Tìm trong ${fmtKm(radiusKm)} km`;
  }

  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row user';
    row.innerHTML = `<div class="message-bubble">${escapeHtml(text)}</div>`;
    messagesContainer.appendChild(row);
  }

  function showSkeletonLoading() {
    const row = document.createElement('div');
    row.className = 'message-row agent';
    row.setAttribute('aria-busy', 'true');
    row.innerHTML = `
      <p class="loading-text">Đang tìm quán quanh ${escapeHtml(deliveryLocation.address || 'bạn')}…</p>
      <div class="receipt-skeleton"></div>
      <div class="receipt-skeleton"></div>
    `;
    messagesContainer.appendChild(row);
    return row;
  }

  function appendAgentResponse({ responseText, toolCalls, candidates, radiusKm, isExpanded, userAddress }) {
    const row = document.createElement('div');
    row.className = 'message-row agent';

    let body;
    if (candidates && candidates.length > 0) {
      body = renderStructuredCandidates(candidates, radiusKm, isExpanded, userAddress);
    } else if (!responseText || responseText.trim() === '') {
      body = renderEmptyState('Thử nới ngân sách, đổi món, hoặc chọn địa chỉ khác.');
    } else {
      body = `<div class="agent-note">${formatAgentMarkdown(responseText)}</div>`;
    }

    const trace = toolCalls && toolCalls.length ? `
      <details class="trace">
        <summary>Các bước đã chạy (${toolCalls.length})</summary>
        <ol>
          ${toolCalls.map(tc => `
            <li><code>${escapeHtml(tc.tool)}</code>
              <span class="trace-args">${escapeHtml(JSON.stringify(tc.arguments))}</span></li>`).join('')}
        </ol>
      </details>` : '';

    row.innerHTML = body + trace;
    messagesContainer.appendChild(row);
  }

  function renderEmptyState(message) {
    return `
      <div class="empty-state">
        <p class="empty-state-title">Chưa có món nào hợp</p>
        <p class="empty-state-desc">${escapeHtml(message)}</p>
      </div>
    `;
  }

  // One recommendation = one order receipt. The lines must add up to the total:
  //   dishes (price × portions) + ship − discount = total
  function renderReceipt(cand, idx) {
    const dish    = cand.dish || {};
    const rest    = cand.restaurant || {};
    const pricing = cand.pricing || {};
    const items   = (cand.items && cand.items.length) ? cand.items : [dish];
    const qty     = cand.quantity || 1;
    const rests   = (cand.restaurants && cand.restaurants.length) ? cand.restaurants : [rest];
    const isSplit = rests.length > 1;

    const platformTag = pf => pf ? `<span class="platform ${platformClass(pf)}">${escapeHtml(pf)}</span>` : '';
    const line = (label, amount, cls = '') => `
      <div class="line ${cls}">
        <span class="line-name">${label}</span>
        <span class="line-dots" aria-hidden="true"></span>
        <span class="line-amount">${amount}</span>
      </div>`;
    const itemLine = it => line(
      `${escapeHtml(it.name)}${qty > 1 ? `<small>${qty} phần × ${fmtVnd(it.price)}</small>` : ''}`,
      fmtVnd((it.price || 0) * qty)
    );

    // Header: the shop prints its name at the top of the receipt
    const head = `
      <header class="receipt-head">
        <div class="receipt-no">Số<b>${idx + 1}</b></div>
        <div class="receipt-shop-line">
          <h3 class="receipt-shop">${escapeHtml(isSplit ? `Tách đơn ${rests.length} quán` : (rest.name || 'Quán'))}</h3>
          ${isSplit ? '' : platformTag(rest.platform)}
        </div>
        ${!isSplit && rest.address ? `<p class="receipt-address">${escapeHtml(rest.address)}</p>` : ''}
      </header>
      ${isSplit ? `<p class="receipt-split-note">Chưa quán nào có đủ các món bạn gọi, nên đơn chia cho ${rests.length} quán, mỗi quán giao riêng.</p>` : ''}`;

    // Lines
    let lines = isSplit
      ? rests.map(r => `
          <p class="receipt-group-title">${escapeHtml(r.name)} ${platformTag(r.platform)}</p>
          ${items.filter(i => i.restaurant_id === r.id).map(itemLine).join('')}`).join('')
      : items.map(itemLine).join('');

    const subtotal = pricing.original_price ?? items.reduce((sum, i) => sum + (i.price || 0) * qty, 0);
    const fee      = pricing.delivery_fee || 0;
    const total    = pricing.final_price ?? subtotal + fee;
    const discount = Math.max(0, subtotal + fee - total);                 // taken off the total
    const shipOff  = Math.max(0, (pricing.savings || 0) - discount);      // freeship, already inside `fee`
    const code     = pricing.applied_promotion_code;
    const sticker  = code ? `<span class="promo-code">${escapeHtml(code)}</span>` : '';
    const feeEstimated = rests.some(r => (r.estimated_fields || []).includes('delivery_fee'));

    const shipNotes = [
      isSplit ? `${rests.length} lần giao` : '',
      feeEstimated ? 'ước tính' : '',
      shipOff ? `đã giảm ${fmtVnd(shipOff)}` : '',
    ].filter(Boolean).join(', ');
    lines += line(
      `Phí ship${shipOff && !discount ? sticker : ''}${shipNotes ? `<small>${shipNotes}</small>` : ''}`,
      fmtVnd(fee), 'line-muted'
    );
    if (discount > 0) lines += line(`Giảm giá${sticker}`, `−${fmtVnd(discount)}`, 'line-discount');

    // Facts, each labelled with how reliable it is
    const dist  = rest.distance_km || 0;
    const basis = rest.distance_basis || 'stored';
    const distText = basis === 'unknown'           ? 'Chưa rõ khoảng cách'
                   : basis === 'same_district'     ? `Cùng quận, khoảng ${fmtKm(dist)} km (ước tính)`
                   : basis === 'district_centroid' ? `Khoảng ${fmtKm(dist)} km (ước tính theo quận)`
                   : `${fmtKm(dist)} km`;
    const facts = [
      isSplit ? `Quán xa nhất: ${distText.charAt(0).toLowerCase()}${distText.slice(1)}` : distText,
      !isSplit ? (rest.rating != null ? `★ ${fmtKm(rest.rating)}` : 'Chưa có đánh giá') : '',
      !isSplit && rest.delivery_time_mins && !(rest.estimated_fields || []).includes('delivery_time_mins')
        ? `Giao khoảng ${rest.delivery_time_mins} phút` : '',
    ].filter(Boolean).map(f => `<li>${escapeHtml(f)}</li>`).join('');
    const spicy = items.some(i => i.spicy) ? '<li class="fact-spicy">Có món cay</li>' : '';

    // Why this pick (from the backend's traceable reasoning)
    const raw = cand.reasoning || cand.explanation || '';
    const reasons = raw.includes(' • ') ? raw.split(' • ') : raw.split('\n');
    const why = reasons.filter(r => r.trim()).length ? `
      <details class="receipt-why"${idx === 0 ? ' open' : ''}>
        <summary>Vì sao gợi ý</summary>
        <ul>${reasons.filter(r => r.trim()).map(r => `<li>${escapeHtml(r.trim())}</li>`).join('')}</ul>
      </details>` : '';

    const actions = rests.map(r => {
      const pf = r.platform || 'ShopeeFood';
      return `
        <button type="button" class="btn order-btn" data-restaurant="${escapeHtml(r.name || '')}" data-platform="${escapeHtml(pf)}">
          ${isSplit ? `Đặt ${escapeHtml(r.name || '')} trên ${escapeHtml(pf)}` : `Đặt trên ${escapeHtml(pf)}`}
        </button>`;
    }).join('');

    return `
      <article class="receipt" aria-label="Gợi ý số ${idx + 1}">
        ${head}
        <div class="receipt-lines">
          ${lines}
          <div class="receipt-total"><span>Tổng</span><strong>${fmtVnd(total)}</strong></div>
        </div>
        <ul class="receipt-facts">${facts}${spicy}</ul>
        ${why}
        <div class="receipt-actions">${actions}</div>
      </article>`;
  }

  function renderStructuredCandidates(candidates, radiusKm, isExpanded, userAddress) {
    const where = `<strong>${escapeHtml(userAddress)}</strong>`;
    const context = isExpanded
      ? `Quanh ${where} ít lựa chọn nên đã tìm rộng ra ${fmtKm(radiusKm)} km.`
      : `Tìm trong ${fmtKm(radiusKm)} km quanh ${where}.`;
    return `
      <p class="results-context">${context}</p>
      <div class="receipts">${candidates.map(renderReceipt).join('')}</div>
      <p class="results-followup">Muốn rẻ hơn, gần hơn hay đổi món? Cứ nói tiếp, ví dụ "món số 2 rẻ hơn".</p>
    `;
  }

  function formatAgentMarkdown(text) {
    if (!text) return '';
    return escapeHtml(text)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g,   '<em>$1</em>')
      .replace(/\n\n/g, '<br><br>')
      .replace(/\n/g,  '<br>');
  }

  function renderWelcomeCard() {
    const currentName    = userNameInput.value.trim() || 'bạn';
    const currentAddress = deliveryLocation.address || NO_ADDRESS_TEXT;
    const prompts = [
      'Trưa nay ăn gì dưới 60k?',
      'Phở và bún chả cho 2 người',
      'Món nước gì đó thanh thanh, không cay',
      'Có món nào đang giảm giá không?',
      'Tìm đồ Hàn, ưu tiên gần',
    ];

    messagesContainer.innerHTML = `
      <section class="welcome" id="welcomeCard">
        <p class="welcome-greeting">Chào <span id="welcomeUserName">${escapeHtml(currentName)}</span>,</p>
        <h1 class="welcome-title">Hôm nay ăn gì?</h1>
        <p class="welcome-lede">Nói món bạn thèm, ngân sách, hay thứ muốn tránh. PickyEaters chỉ gợi ý quán có thật quanh chỗ bạn, giá đã tính cả ship.</p>
        <p class="welcome-where">Giao đến: <strong id="welcomeUserAddress">${escapeHtml(currentAddress)}</strong></p>
        <ul class="try-list">
          ${prompts.map(pr => `<li><button type="button" class="chip" data-prompt="${escapeHtml(pr)}">${escapeHtml(pr)}</button></li>`).join('')}
        </ul>
      </section>
    `;
  }

  function scrollToBottom() {
    const workspace = document.querySelector('.chat-workspace');
    if (workspace) workspace.scrollTop = workspace.scrollHeight;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g,  '&amp;')
      .replace(/</g,  '&lt;')
      .replace(/>/g,  '&gt;')
      .replace(/"/g,  '&quot;')
      .replace(/'/g,  '&#039;');
  }

  // ─── PREFERENCES DRAWER ───────────────────────────────────────────────────

  openPrefBtn.addEventListener('click', () => {
    loadUserProfile(currentUserId);
    prefDrawerOverlay.classList.add('active');
  });

  closePrefBtn.addEventListener('click', () => {
    prefDrawerOverlay.classList.remove('active');
  });

  prefDrawerOverlay.addEventListener('click', (e) => {
    if (e.target === prefDrawerOverlay) {
      prefDrawerOverlay.classList.remove('active');
    }
  });

  // ESC key closes drawer
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && prefDrawerOverlay.classList.contains('active')) {
      prefDrawerOverlay.classList.remove('active');
    }
  });

  // Slider live updates
  budgetInput.addEventListener('input', () => {
    budgetValue.textContent = `${parseInt(budgetInput.value).toLocaleString('vi-VN')}đ`;
  });

  ratingInput.addEventListener('input', () => {
    ratingValue.textContent = `${parseFloat(ratingInput.value).toLocaleString('vi-VN', { minimumFractionDigits: 1 })} sao`;
  });

  // Cuisine & flavor toggles
  cuisinesContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.toggle-chip');
    if (chip) setChip(chip, !chip.classList.contains('active'));
  });

  flavorsContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.toggle-chip');
    if (chip) setChip(chip, !chip.classList.contains('active'));
  });

  function setChip(chip, on) {
    chip.classList.toggle('active', on);
    chip.setAttribute('aria-pressed', String(on));
  }

  // Disliked ingredient tags
  addIngredientBtn.addEventListener('click', addDislikedTagFromInput);
  newIngredientInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); addDislikedTagFromInput(); }
  });

  function addDislikedTagFromInput() {
    const val = newIngredientInput.value.trim();
    if (!val) return;
    addDislikedTag(val);
    newIngredientInput.value = '';
  }

  function addDislikedTag(name) {
    const existing = Array.from(dislikedTags.querySelectorAll('.tag-badge .tag-name'))
      .map(s => s.textContent.toLowerCase());
    if (existing.includes(name.toLowerCase())) return;

    const badge = document.createElement('span');
    badge.className = 'tag-badge';
    badge.setAttribute('role', 'listitem');
    badge.innerHTML = `
      <span class="tag-name">${escapeHtml(name)}</span>
      <button type="button" class="tag-remove" aria-label="Bỏ ${escapeHtml(name)}">&times;</button>
    `;
    badge.querySelector('.tag-remove').addEventListener('click', () => badge.remove());
    dislikedTags.appendChild(badge);
  }

  // Save Preferences
  savePrefBtn.addEventListener('click', async () => {
    const selectedCuisines = Array.from(cuisinesContainer.querySelectorAll('.toggle-chip.active'))
      .map(btn => btn.getAttribute('data-val'));

    const selectedFlavors = Array.from(flavorsContainer.querySelectorAll('.toggle-chip.active'))
      .map(btn => btn.getAttribute('data-val'));

    const disliked = Array.from(dislikedTags.querySelectorAll('.tag-badge .tag-name'))
      .map(s => s.textContent.trim());

    const budget    = parseInt(budgetInput.value);
    const minRating = parseFloat(ratingInput.value);
    const name      = prefNameInput.value.trim();
    const address   = prefAddressInput.value.trim();

    try {
      savePrefBtn.disabled = true;
      savePrefBtn.textContent = 'Đang lưu…';

      if (address && address !== deliveryLocation.address) {
        // A newly typed address replaces the map pin.
        deliveryLocation = { address, lat: null, lng: null };
        if (!(await saveLocation(name || userNameInput.value.trim() || 'Bạn'))) return;
      } else if (name) {
        await fetch(`/api/user/${currentUserId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name })
        });
      }
      if (name) { userNameInput.value = name; const el = getWelcomeNameEl(); if (el) el.textContent = name; }

      await Promise.all([
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'budget',             value: budget }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'minimum_rating',      value: minRating }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'preferred_cuisines',  value: selectedCuisines }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'preferred_flavors',   value: selectedFlavors }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'disliked_ingredients', value: disliked }) }),
      ]);

      showToast('Đã lưu khẩu vị.');
      prefDrawerOverlay.classList.remove('active');
    } catch (err) {
      showToast(`Lỗi khi lưu: ${err.message}`, 'error');
    } finally {
      savePrefBtn.disabled = false;
      savePrefBtn.textContent = 'Lưu khẩu vị';
    }
  });

  // Load & sync user profile into all UI elements
  async function loadUserProfile(userId) {
    try {
      const res = await fetch(`/api/user/${userId}`);
      if (!res.ok) return;
      const pref = await res.json();
      currentPreferences = pref;

      const name = pref.name || '';

      userNameInput.value = name;
      if (prefNameInput) prefNameInput.value = name;
      const nameEl = getWelcomeNameEl();
      if (nameEl) nameEl.textContent = name;

      // No default address: show exactly what the profile has (possibly nothing).
      setDeliveryLocation(pref.address || '', pref.latitude, pref.longitude);

      // Preferences UI
      budgetInput.value  = pref.budget || 80000;
      budgetValue.textContent = `${(pref.budget || 80000).toLocaleString('vi-VN')}đ`;

      ratingInput.value  = pref.minimum_rating || 4.3;
      ratingValue.textContent = `${(pref.minimum_rating || 4.3).toLocaleString('vi-VN', { minimumFractionDigits: 1 })} sao`;
      updateRadiusBadge(pref.preferred_distance || 5, false);

      cuisinesContainer.querySelectorAll('.toggle-chip').forEach(chip => {
        setChip(chip, (pref.preferred_cuisines || []).includes(chip.getAttribute('data-val')));
      });

      flavorsContainer.querySelectorAll('.toggle-chip').forEach(chip => {
        setChip(chip, (pref.preferred_flavors || []).includes(chip.getAttribute('data-val')));
      });

      dislikedTags.innerHTML = '';
      (pref.disliked_ingredients || []).forEach(item => addDislikedTag(item));

    } catch (e) {
      console.warn('Could not load user profile:', e);
    }
  }

  // FIX: showToast supports error variant, button uses innerHTML to preserve emoji
  function showToast(msg, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast${type === 'error' ? ' toast-error' : ''}`;
    toast.textContent = msg;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.35s ease';
      setTimeout(() => toast.remove(), 350);
    }, 3200);
  }
});
