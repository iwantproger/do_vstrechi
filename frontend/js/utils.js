/* ═══════════════════════════════════════════
   UTILS
═══════════════════════════════════════════ */

function toggleCollapsible(headerEl) {
  var section = headerEl.closest('.collapsible-section');
  var body = section.querySelector('.collapsible-body');
  var isOpen = section.classList.contains('open');
  if (isOpen) {
    section.classList.remove('open');
    body.style.display = 'none';
  } else {
    section.classList.add('open');
    body.style.display = 'block';
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}
let _toastTimer;
function showToast(msg, type = 'default', duration = 3000) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  var cls = 'toast';
  if (type === 'success') cls += ' success';
  else if (type === 'error') cls += ' error';
  el.className = cls;
  clearTimeout(_toastTimer);
  requestAnimationFrame(() => el.classList.add('show'));
  _toastTimer = setTimeout(() => el.classList.remove('show'), duration);
}

function copyToast(text) {
  if (text) copyText(text);
  showToast('Скопировано');
}

function showSheet(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('show');
}

function hideSheet() {
  document.querySelectorAll('.overlay.show').forEach(o => o.classList.remove('show'));
}

function closeSheet(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('show');
}

function escHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
const esc = escHtml;

function formatDate(d) {
  if (typeof d === 'string') d = new Date(d);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
const fmtDate = formatDate;

function formatDateTime(dateStr) {
  const d = new Date(dateStr);
  return d.getDate() + ' ' + MONTHS_GEN[d.getMonth()].slice(0, 3) + ', ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function getDayName(isoDate) {
  const d = new Date(isoDate);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tmrw = new Date(today); tmrw.setDate(tmrw.getDate() + 1);
  const dayAfter = new Date(tmrw); dayAfter.setDate(dayAfter.getDate() + 1);
  if (d >= today && d < tmrw) return 'Сегодня';
  if (d >= tmrw && d < dayAfter) return 'Завтра';
  return d.getDate() + ' ' + MONTHS_GEN[d.getMonth()].slice(0, 3);
}

function fmtTime(d) {
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function fmtTimeOffset(d, mins) {
  const t = d.getHours() * 60 + d.getMinutes() + mins;
  return String(Math.floor(t / 60) % 24).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0');
}

function fmtDateShort(d) {
  return d.getDate() + ' ' + MONTHS_GEN[d.getMonth()];
}

function fmtDateFull(d) {
  const dayName = DAYS_FULL[d.getDay() === 0 ? 6 : d.getDay() - 1];
  return dayName + ', ' + d.getDate() + ' ' + MONTHS_GEN[d.getMonth()];
}

function dateGroupLabel(dt, now) {
  const todayStr = formatDate(now);
  const tmrw = new Date(now); tmrw.setDate(tmrw.getDate() + 1);
  const ds = formatDate(dt);
  if (ds === todayStr) return 'Сегодня';
  if (ds === formatDate(tmrw)) return 'Завтра';
  if (dt > now) return fmtDateShort(dt);
  return 'Ранее';
}

function getInitials(name) {
  return (name || '').split(' ').slice(0, 2).map(w => w[0] || '').join('').toUpperCase() || '?';
}

function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {});
}

function openLink(url) {
  if (tg) tg.openLink(url); else window.open(url, '_blank');
}

function openTelegramChat(username) {
  if (!username) { showToast('Нет контакта для связи', 'error'); return; }
  var clean = String(username).replace(/^@/, '');
  if (tg?.openTelegramLink) tg.openTelegramLink('https://t.me/' + clean);
  else window.open('https://t.me/' + clean, '_blank');
}

function closeMiniApp() {
  if (tg) tg.close();
  else window.close();
}

function enableBookingNotifications() {
  var bid = state._lastBookingId || '';
  var botUrl = 'https://t.me/' + BOT_USERNAME + '?start=notify' + (bid ? '_' + bid : '');
  if (tg?.openTelegramLink) tg.openTelegramLink(botUrl);
  else window.open(botUrl, '_blank');
}

function renderEmpty(title, desc) {
  return `<div class="empty-state">
    <div class="empty-icon"><svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/></svg></div>
    <div class="empty-title">${title}</div>
    <div class="empty-desc">${desc}</div>
  </div>`;
}

function sliderLabel(v) {
  if (v === 0) return 'Нет';
  if (v < 60) return v + ' мин';
  const h = Math.floor(v / 60), m = v % 60;
  return m ? h + ' ч ' + m + ' мин' : h + ' ч';
}

function updateSlider(inp, valId) {
  const v = parseInt(inp.value);
  const el = document.getElementById(valId);
  if (el) el.textContent = sliderLabel(v);
  const pct = ((v - inp.min) / (inp.max - inp.min)) * 100;
  inp.style.background = 'linear-gradient(to right,var(--a) ' + pct + '%,var(--s3) ' + pct + '%)';
}

/* ═══════════════════════════════════════════
   MEETING STATUS BADGES
═══════════════════════════════════════════ */
function getMeetingStatus(b) {
  if (b.status === 'cancelled') return 'cancelled';
  if (b.status === 'completed') return 'completed';
  const now = new Date();
  const start = new Date(b.scheduled_time);
  const dur = b.schedule_duration || b.duration || 60;
  const end = new Date(start.getTime() + dur * 60000);
  if (now >= start && now < end) return 'ongoing';
  if (now >= end) return b.status === 'confirmed' ? 'completed' : 'noans';
  return b.status;
}

function meetingStatusHtml(status) {
  if (status === 'ongoing') {
    return '<div style="display:flex;align-items:center;gap:3px;white-space:nowrap">'
      + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2DD4A0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:block;flex-shrink:0">'
        + '<path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.868v6.264a1 1 0 0 1-1.447.9L15 14"/>'
        + '<rect x="1" y="6" width="14" height="12" rx="2"/>'
      + '</svg>'
      + '<span style="font-size:11px;font-weight:700;color:#2DD4A0;line-height:14px">Идёт</span>'
    + '</div>';
  }
  const map = {
    confirmed: { cls: 'mst-confirmed', icon: '<polyline points="20 6 9 17 4 12"/>', text: 'Всё в силе' },
    pending:   { cls: 'mst-pending',   icon: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>', text: 'Ожидает' },
    noans:     { cls: 'mst-noans',     icon: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>', text: 'Нет ответа' },
    cancelled: { cls: 'mst-cancelled', icon: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>', text: 'Отменено' },
    completed: { cls: 'mst-done',      icon: '<polyline points="20 6 9 17 4 12"/>', text: 'Прошла' },
  };
  const s = map[status] || map.pending;
  return `<div class="mst ${s.cls}"><svg viewBox="0 0 24 24">${s.icon}</svg><span class="mst-label">${s.text}</span></div>`;
}

/* FIX: Bug #11 — статус расписания в едином стиле с meetingStatusHtml (иконка + текст, без подложки) */
function scheduleStatusHtml(isActive) {
  if (isActive) {
    /* зелёная галочка — как "Всё в силе" у встреч */
    return '<div class="mst mst-confirmed"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg><span class="mst-label">Активно</span></div>';
  }
  /* жёлтая пауза — как "Ожидает" у встреч */
  return '<div class="mst mst-pending"><svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1" stroke-linejoin="round"/><rect x="14" y="5" width="4" height="14" rx="1" stroke-linejoin="round"/></svg><span class="mst-label">На паузе</span></div>';
}

function avatarUrl(telegramId) {
  if (!telegramId) return null;
  return '/api/users/' + telegramId + '/avatar';
}

function renderAvatar(telegramId, initials, size) {
  size = size || 44;
  var fontSize = Math.round(size * 0.38);
  var radius = Math.round(size * 0.32);
  var ini = escHtml(initials || '?');
  if (telegramId) {
    return '<div class="avatar-wrap" style="width:' + size + 'px;height:' + size + 'px;border-radius:' + radius + 'px;overflow:hidden;flex-shrink:0;background:var(--a);display:flex;align-items:center;justify-content:center;font-size:' + fontSize + 'px;font-weight:800;color:#07221A">'
      + '<img src="' + avatarUrl(telegramId) + '" '
      + 'style="width:100%;height:100%;object-fit:cover" '
      + 'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'" '
      + 'loading="lazy">'
      + '<span style="display:none;width:100%;height:100%;align-items:center;justify-content:center">' + ini + '</span>'
      + '</div>';
  }
  return '<div style="width:' + size + 'px;height:' + size + 'px;border-radius:' + radius + 'px;background:var(--a);display:flex;align-items:center;justify-content:center;font-size:' + fontSize + 'px;font-weight:800;color:#07221A;flex-shrink:0">' + ini + '</div>';
}

function badgeParticipant() {
  return '<span class="badge-participant">'
    + '<svg viewBox="0 0 24 24" style="width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
    + 'Я участник'
    + '</span>';
}

/* ═══════════════════════════════════════════
   IEO (Inline Edit Overlay)
═══════════════════════════════════════════ */
function showIeo(title, value, suffix) {
  const el = document.getElementById('ieo');
  if (!el) return;
  document.getElementById('ieo-title').textContent = title;
  document.getElementById('ieo-inp').value = value;
  document.getElementById('ieo-suffix').textContent = suffix;
  el.classList.add('show');
}

function closeIeo() {
  const el = document.getElementById('ieo');
  if (el) el.classList.remove('show');
}

function applyIeo() {
  var val = parseInt(document.getElementById('ieo-inp').value);
  if (isNaN(val)) { closeIeo(); return; }
  if (_ieoSliderId) {
    var inp = document.getElementById(_ieoSliderId);
    if (inp) {
      /* clamp to slider range, but allow ieo to exceed max for custom values */
      val = Math.max(parseInt(inp.min), val);
      inp.value = Math.min(parseInt(inp.max), val);
      updateSliderSmart(inp, _ieoLabelId);
      /* label shows custom val even if above max */
      var lbl = document.getElementById(_ieoLabelId);
      if (lbl && val > parseInt(inp.max)) lbl.textContent = sliderLabel(val);
    }
    markScheduleDirty();
  }
  closeIeo();
}

