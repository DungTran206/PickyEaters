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
  let currentPreferences = {
    name: 'Dũng',
    address: 'Cầu Giấy, Hà Nội',
    budget: 80000,
    minimum_rating: 4.3,
    preferred_cuisines: [],
    preferred_flavors: [],
    disliked_ingredients: []
  };

  // ─── INIT ─────────────────────────────────────────────────────────────────
  loadUserProfile(currentUserId);

  // User Switcher
  userSelector.addEventListener('change', () => {
    currentUserId = userSelector.value;
    loadUserProfile(currentUserId);
    showToast(`Đã chuyển sang hồ sơ: ${currentUserId}`);
  });

  // Save Location Button
  saveLocationBtn.addEventListener('click', async () => {
    const name    = userNameInput.value.trim() || 'Bạn';
    const address = userAddressInput.value.trim() || 'Cầu Giấy, Hà Nội';

    try {
      saveLocationBtn.disabled = true;
      saveLocationBtn.innerHTML = '<span>⏳ Đang lưu...</span>';

      const res = await fetch(`/api/user/${currentUserId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, address })
      });

      if (res.ok) {
        // Update welcome card safely via fresh query
        const nameEl    = getWelcomeNameEl();
        const addressEl = getWelcomeAddressEl();
        if (nameEl)    nameEl.textContent = name;
        if (addressEl) addressEl.textContent = address;
        if (prefNameInput)    prefNameInput.value = name;
        if (prefAddressInput) prefAddressInput.value = address;
        syncDistrictChips(address);
        showToast('Đã lưu thông tin vị trí & tên khách hàng thành công! 📍');
      } else {
        showToast('Lỗi khi lưu vị trí. Vui lòng thử lại.', 'error');
      }
    } catch (err) {
      showToast(`Lỗi kết nối: ${err.message}`, 'error');
    } finally {
      saveLocationBtn.disabled = false;
      saveLocationBtn.innerHTML = '<span>💾 Lưu vị trí</span>';
    }
  });

  // Quick District Chips — FIX: use textContent comparison properly
  districtChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const dist = chip.getAttribute('data-district');
      userAddressInput.value = dist;
      if (prefAddressInput)       prefAddressInput.value = dist;
      const addressEl = getWelcomeAddressEl();
      if (addressEl) addressEl.textContent = dist;
      syncDistrictChips(dist);
      showToast(`Đã chọn: ${dist}. Nhấn "Lưu vị trí" để ghi nhớ.`);
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

  // Reset Conversation
  resetChatBtn.addEventListener('click', () => {
    if (confirm('Bạn có muốn đặt lại cuộc trò chuyện về ban đầu không?')) {
      renderWelcomeCard();
      updateRadiusBadge(5.0, false);
      showToast('Đã làm mới cuộc trò chuyện.');
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
      showToast(`🛒 Mở đơn hàng tại ${restaurant} qua ${platform}!`);
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
    const currentAddress = userAddressInput.value.trim() || 'Cầu Giấy, Hà Nội';

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
          user_address: currentAddress
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
        responseText: `⚠️ Có lỗi khi kết nối tới Agent: **${err.message}**. Hãy kiểm tra lại backend nhé!`,
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

  function updateRadiusBadge(radiusKm, isExpanded) {
    if (isExpanded || radiusKm > 5.0) {
      radiusBadge.className = 'radius-status-badge expanded';
      radiusBadgeText.innerHTML = `Bán kính: <strong>${radiusKm} km</strong> <span style="opacity:0.7;font-weight:400;">(Mở rộng)</span>`;
    } else {
      radiusBadge.className = 'radius-status-badge radius-5km';
      radiusBadgeText.innerHTML = `Bán kính: <strong>${radiusKm} km</strong> <span style="opacity:0.7;font-weight:400;">(Chuẩn)</span>`;
    }
  }

  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row user';
    row.innerHTML = `<div class="message-bubble">${escapeHtml(text)}</div>`;
    messagesContainer.appendChild(row);
  }

  // Skeleton loading replaces old typing indicator
  function showSkeletonLoading() {
    const row = document.createElement('div');
    row.className = 'message-row agent';
    row.innerHTML = `
      <div class="message-avatar">🍜</div>
      <div class="message-bubble">
        <div class="skeleton-cards-container">
          ${[1,2].map(() => `
            <div class="skeleton-card">
              <div class="skeleton-line title"></div>
              <div class="skeleton-line sub"></div>
              <div style="margin-top:10px;">
                <div class="skeleton-line tag"></div>
                <div class="skeleton-line tag"></div>
                <div class="skeleton-line tag"></div>
              </div>
              <div style="margin-top:8px;">
                <div class="skeleton-line body"></div>
                <div class="skeleton-line body-short"></div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
    messagesContainer.appendChild(row);
    return row;
  }

  function appendAgentResponse({ responseText, toolCalls, candidates, radiusKm, isExpanded, userAddress }) {
    const row = document.createElement('div');
    row.className = 'message-row agent';

    // 1. Tool Call Trace Accordion
    let toolHtml = '';
    if (toolCalls && toolCalls.length > 0) {
      toolHtml = `
        <div class="tool-trace-card">
          <div class="tool-trace-header" id="traceToggle_${Date.now()}"
               onclick="this.closest('.tool-trace-card').classList.toggle('open')">
            <div class="tool-trace-title">
              <span>🔧</span>
              <span>Đã thực thi ${toolCalls.length} công cụ AI</span>
            </div>
            <span class="tool-trace-icon-toggle">▼</span>
          </div>
          <div class="tool-trace-body">
            ${toolCalls.map(tc => `
              <div class="tool-call-item">
                <div class="tool-call-name">↳ ${escapeHtml(tc.tool)}()</div>
                <div class="tool-call-args">args = ${escapeHtml(JSON.stringify(tc.arguments))}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    // 2. Main body
    let bodyHtml = '';
    if (candidates && candidates.length > 0) {
      bodyHtml = renderStructuredCandidates(candidates, radiusKm, isExpanded, userAddress, responseText);
    } else if (!responseText || responseText.trim() === '') {
      bodyHtml = renderEmptyState('Không tìm thấy món phù hợp trong bán kính 10km. Thử đổi khẩu vị hoặc tăng ngân sách nhé!');
    } else {
      bodyHtml = formatAgentMarkdown(responseText);
    }

    row.innerHTML = `
      <div class="message-avatar">🍜</div>
      <div class="message-bubble">
        ${toolHtml}
        <div class="response-content">${bodyHtml}</div>
      </div>
    `;
    messagesContainer.appendChild(row);
  }

  function renderEmptyState(message) {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">🍽️</div>
        <div class="empty-state-title">Chưa tìm thấy món phù hợp</div>
        <div class="empty-state-desc">${escapeHtml(message)}</div>
      </div>
    `;
  }

  function renderStructuredCandidates(candidates, radiusKm, isExpanded, userAddress, rawText) {
    // Radius Banner
    const radiusBannerHtml = isExpanded
      ? `<div class="radius-alert-banner expanded">
           <span class="radius-alert-icon">🚀</span>
           <div>
             <strong>Khảo sát mở rộng 10.0 km:</strong> Khu vực 5km quanh <em>${escapeHtml(userAddress)}</em> chưa đủ lựa chọn, hệ thống đã tự động mở rộng lên 10km!
           </div>
         </div>`
      : `<div class="radius-alert-banner normal">
           <span class="radius-alert-icon">🎯</span>
           <div>
             <strong>Khảo sát chuẩn 5.0 km:</strong> Đã tìm thấy các lựa chọn ngon trong bán kính 5km quanh <em>${escapeHtml(userAddress)}</em>!
           </div>
         </div>`;

    const cardsHtml = candidates.map((cand, idx) => {
      const dish    = cand.dish     || {};
      const rest    = cand.restaurant || {};
      const pricing = cand.pricing  || {};
      const rank    = idx + 1;

      // Platform
      const platformName  = rest.platform || 'ShopeeFood';
      const platformClass = platformName.toLowerCase().includes('grab') ? 'grabfood' : 'shopeefood';

      // Pricing
      const finalPrice    = pricing.final_price    || dish.price || 0;
      const originalPrice = pricing.original_price || dish.price || 0;
      const savings       = pricing.savings        || 0;

      // Distance
      const dist        = rest.distance_km || 0;
      const isWithin5km = dist <= 5.0;
      const distClass   = isWithin5km ? 'within-5km' : 'expanded-10km';
      const distLabel   = isWithin5km
        ? `📍 ${dist} km (trong 5km)`
        : `🚀 ${dist} km (mở rộng 10km)`;

      const isSpicy = dish.spicy || false;

      // FIX: Reasoning split — handle both ' • ' and '\n' separators, fallback gracefully
      const reasoningRaw = cand.reasoning || cand.explanation || '';
      let reasoningPoints = [];
      if (reasoningRaw) {
        if (reasoningRaw.includes(' • ')) {
          reasoningPoints = reasoningRaw.split(' • ').filter(p => p.trim());
        } else if (reasoningRaw.includes('\n')) {
          reasoningPoints = reasoningRaw.split('\n').filter(p => p.trim());
        } else {
          reasoningPoints = [reasoningRaw];
        }
      }
      if (reasoningPoints.length === 0) {
        reasoningPoints = [
          `🎯 Khớp gu: ${dish.name}`,
          `📍 Khoảng cách: ${dist} km từ vị trí của bạn`,
          `💵 Giá cả hợp lý: ${finalPrice.toLocaleString('vi-VN')}đ`
        ];
      }

      const rankClass = rank === 1 ? 'rank-1' : '';
      const rankEmoji = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : '';

      return `
        <div class="rec-card ${rankClass}">
          <div class="rec-card-header">
            <div class="rec-rank-title">
              <span class="rec-rank-badge" title="Xếp hạng ${rank}">${rankEmoji || '#' + rank}</span>
              <div style="min-width:0;flex:1;">
                <div class="rec-dish-name">${escapeHtml(dish.name || 'Món ăn')}</div>
                <div class="rec-restaurant-info">
                  <span class="rec-restaurant-name">${escapeHtml(rest.name || 'Quán ăn')}</span>
                  <span class="platform-tag ${platformClass}">${escapeHtml(platformName)}</span>
                </div>
                <div class="rec-restaurant-address">
                  <span>📍 ${escapeHtml(rest.address || rest.district || 'Hà Nội')}</span>
                </div>
              </div>
            </div>

            <div class="rec-price-section">
              <div class="rec-final-price">${finalPrice.toLocaleString('vi-VN')}đ</div>
              ${savings > 0 ? `
                <div class="rec-original-price">${originalPrice.toLocaleString('vi-VN')}đ</div>
                <div class="rec-savings-pill">Giảm ${savings.toLocaleString('vi-VN')}đ</div>
              ` : ''}
            </div>
          </div>

          <div class="rec-meta-tags">
            <span class="meta-pill dist ${distClass}">${distLabel}</span>
            <span class="meta-pill rating">⭐ ${rest.rating || 4.5}</span>
            <span class="meta-pill ${isSpicy ? 'spicy' : 'non-spicy'}">${isSpicy ? '🌶️ Có cay' : '🌱 Không cay'}</span>
            ${pricing.applied_promotion_code ? `<span class="meta-pill deal">🔥 Mã: ${escapeHtml(pricing.applied_promotion_code)}</span>` : ''}
            <span class="meta-pill dist">⏱️ ~${rest.delivery_time_mins || 20} phút</span>
          </div>

          <!-- AI Reasoning Box -->
          <div class="rec-reasoning-box">
            <div class="reasoning-header">
              <span>💡</span>
              <span>Lập luận AI (Reasoning)</span>
            </div>
            <div class="reasoning-list">
              ${reasoningPoints.map(point => `
                <div class="reasoning-item">
                  <span class="reasoning-bullet">↳</span>
                  <span class="reasoning-text">${escapeHtml(point.trim())}</span>
                </div>
              `).join('')}
            </div>
          </div>

          <div class="rec-card-footer">
            <button
              class="order-btn"
              data-restaurant="${escapeHtml(rest.name || '')}"
              data-platform="${escapeHtml(platformName)}"
            >
              <span>🛒 Đặt qua ${escapeHtml(platformName)}</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    return `
      ${radiusBannerHtml}
      <div class="rec-section-title">🍜 Gợi ý món ngon phù hợp nhất:</div>
      <div class="rec-cards-grid">${cardsHtml}</div>
      <div class="rec-section-footer">
        💬 Bạn ưng món nào? Muốn điều chỉnh ngân sách, đổi khẩu vị hoặc tìm quán gần hơn không?
      </div>
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

  // FIX: renderWelcomeCard updates existing DOM refs (no innerHTML wipe on messagesContainer)
  function renderWelcomeCard() {
    const currentName    = userNameInput.value.trim()    || 'Dũng';
    const currentAddress = userAddressInput.value.trim() || 'Cầu Giấy, Hà Nội';

    messagesContainer.innerHTML = `
      <div class="welcome-card" id="welcomeCard">
        <div class="welcome-badge">🚀 Trợ lý AI · Bán kính 5km ➔ 10km tự động</div>
        <h1 class="welcome-title">Chào <span id="welcomeUserName">${escapeHtml(currentName)}</span>!<br>Bạn muốn ăn gì hôm nay?</h1>
        <p class="welcome-desc">
          FoodAgent phân tích nhu cầu của bạn và tự động quét trong bán kính <strong>5.0 km</strong> quanh
          <strong id="welcomeUserAddress">${escapeHtml(currentAddress)}</strong>.
          Nếu chưa đủ lựa chọn, hệ thống sẽ tự động <strong>mở rộng lên 10.0 km</strong> và
          giải thích rõ lý do (AI Reasoning) vì sao món đó được chọn!
        </p>
        <div class="quick-chips-title">Thử ngay một trong các gợi ý:</div>
        <div class="quick-chips-container">
          <button class="chip" data-prompt="Tối nay ăn gì quanh 5km?">🍜 Tối nay ăn gì quanh 5km?</button>
          <button class="chip" data-prompt="Tìm gà rán giòn rụm dưới 90k gần đây">🍗 Gà rán giòn rụm &lt;90k</button>
          <button class="chip" data-prompt="Thèm mì cay Hàn Quốc hoặc tokbokki chuẩn vị">🌶️ Mì cay Hàn Quốc / Tokbokki</button>
          <button class="chip" data-prompt="Tìm món chay hoặc bò bít tết thử scale 10km">🚀 Thử món xa (Scale 10km)</button>
          <button class="chip" data-prompt="Tìm cơm suất văn phòng ngon rẻ dưới 60k">🍱 Cơm suất ngon rẻ &lt;60k</button>
          <button class="chip" data-prompt="Tìm món nào không có hành tây">🚫 Món không có hành tây</button>
          <button class="chip" data-prompt="Có món nào đang có mã giảm giá khủng không?">🏷️ Mã giảm giá khủng</button>
        </div>
      </div>
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
    ratingValue.textContent = `${parseFloat(ratingInput.value).toFixed(1)}⭐`;
  });

  // Cuisine & flavor toggles
  cuisinesContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.toggle-chip');
    if (chip) chip.classList.toggle('active');
  });

  flavorsContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.toggle-chip');
    if (chip) chip.classList.toggle('active');
  });

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
    badge.innerHTML = `
      <span class="tag-name">${escapeHtml(name)}</span>
      <span class="tag-remove" title="Xóa">&times;</span>
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
      savePrefBtn.innerHTML = '⏳ Đang lưu...';

      if (name || address) {
        await fetch(`/api/user/${currentUserId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, address })
        });
        if (name)    { userNameInput.value = name; const el = getWelcomeNameEl(); if (el) el.textContent = name; }
        if (address) { userAddressInput.value = address; const el = getWelcomeAddressEl(); if (el) el.textContent = address; syncDistrictChips(address); }
      }

      await Promise.all([
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'budget',             value: budget }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'minimum_rating',      value: minRating }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'preferred_cuisines',  value: selectedCuisines }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'preferred_flavors',   value: selectedFlavors }) }),
        fetch(`/api/preferences/${currentUserId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preference_type: 'disliked_ingredients', value: disliked }) }),
      ]);

      showToast('✨ Đã lưu khẩu vị vào hệ thống thành công!');
      prefDrawerOverlay.classList.remove('active');
    } catch (err) {
      showToast(`Lỗi khi lưu: ${err.message}`, 'error');
    } finally {
      savePrefBtn.disabled = false;
      savePrefBtn.innerHTML = '💾 Lưu thay đổi vào Database';
    }
  });

  // Load & sync user profile into all UI elements
  async function loadUserProfile(userId) {
    try {
      const res = await fetch(`/api/user/${userId}`);
      if (!res.ok) return;
      const pref = await res.json();
      currentPreferences = pref;

      const name    = pref.name    || (userId === 'user_01' ? 'Dũng' : 'Khách mới');
      const address = pref.address || 'Cầu Giấy, Hà Nội';

      userNameInput.value    = name;
      userAddressInput.value = address;
      if (prefNameInput)    prefNameInput.value    = name;
      if (prefAddressInput) prefAddressInput.value = address;

      // FIX: Use fresh query for welcome card elements
      const nameEl    = getWelcomeNameEl();
      const addressEl = getWelcomeAddressEl();
      if (nameEl)    nameEl.textContent    = name;
      if (addressEl) addressEl.textContent = address;

      // FIX: Sync district chips using data-district attribute comparison
      syncDistrictChips(address);

      // Preferences UI
      budgetInput.value  = pref.budget || 80000;
      budgetValue.textContent = `${(pref.budget || 80000).toLocaleString('vi-VN')}đ`;

      ratingInput.value  = pref.minimum_rating || 4.3;
      ratingValue.textContent = `${(pref.minimum_rating || 4.3).toFixed(1)}⭐`;

      cuisinesContainer.querySelectorAll('.toggle-chip').forEach(chip => {
        chip.classList.toggle('active', (pref.preferred_cuisines || []).includes(chip.getAttribute('data-val')));
      });

      flavorsContainer.querySelectorAll('.toggle-chip').forEach(chip => {
        chip.classList.toggle('active', (pref.preferred_flavors || []).includes(chip.getAttribute('data-val')));
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
