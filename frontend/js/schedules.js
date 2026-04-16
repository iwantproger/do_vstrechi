/* ═══════════════════════════════════════════
   SCHEDULES LIST (s-schedules)
═══════════════════════════════════════════ */
/* FIX: localStorage хранит ID удалённых расписаний (DELETE ≠ пауза) */
function _getDeletedIds() {
  try { return JSON.parse(localStorage.getItem('deleted_schedules') || '[]'); } catch(e) { return []; }
}
function _markDeleted(id) {
  var ids = _getDeletedIds();
  if (ids.indexOf(id) === -1) ids.push(id);
  try { localStorage.setItem('deleted_schedules', JSON.stringify(ids)); } catch(e) {}
}
function _unmarkDeleted(id) {
  var ids = _getDeletedIds().filter(function(x) { return x !== id; });
  try { localStorage.setItem('deleted_schedules', JSON.stringify(ids)); } catch(e) {}
}

async function loadSchedules() {
  var list = document.getElementById('schedules-list');
  if (!list) return;
  var { data, error } = await apiFetch('GET', '/api/schedules');
  if (error) { showToast('Ошибка загрузки расписаний', 'error'); return; }
  if (data) state.schedules = data.schedules || data;
  if (!state.schedules || !state.schedules.length) {
    list.innerHTML = renderEmpty('Нет расписаний', 'Создайте первое расписание, чтобы клиенты могли записываться');
    return;
  }

  var deletedIds = _getDeletedIds();
  var visible = [];
  var archived = [];
  state.schedules.forEach(function(s) {
    if (deletedIds.indexOf(s.id) !== -1) archived.push(s);
    else visible.push(s);
  });

  var html = '';
  if (!visible.length && !archived.length) {
    list.innerHTML = renderEmpty('Нет расписаний', 'Создайте первое расписание, чтобы клиенты могли записываться');
    return;
  }
  visible.forEach(function(s) { html += renderLinkCard(s); });
  if (archived.length) {
    html += '<div style="margin:24px 16px 0"><button onclick="toggleScheduleArchive()" style="display:flex;align-items:center;gap:6px;width:100%;background:none;border:1px solid var(--b1);border-radius:12px;padding:10px 16px;font-family:var(--font);font-size:13px;font-weight:600;color:var(--t2);cursor:pointer">'
      + '<svg viewBox="0 0 24 24" style="width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:2"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg>'
      + 'Архив (' + archived.length + ')</button></div>';
    html += '<div id="schedule-archive" style="display:none;margin-top:8px">';
    archived.forEach(function(s) { html += renderLinkCard(s, true); });
    html += '</div>';
  }
  list.innerHTML = html;
}

function toggleScheduleArchive() {
  var el = document.getElementById('schedule-archive');
  if (!el) return;
  el.style.display = el.style.display === 'none' ? '' : 'none';
}

function formatWorkDays(days) {
  if (!days || !days.length) return '';
  var sorted = days.slice().sort(function(a, b) { return a - b; });
  /* check if consecutive */
  var isConsec = true;
  for (var i = 1; i < sorted.length; i++) {
    if (sorted[i] !== sorted[i - 1] + 1) { isConsec = false; break; }
  }
  if (isConsec && sorted.length > 2) {
    return DAYS[sorted[0]] + '–' + DAYS[sorted[sorted.length - 1]];
  }
  return sorted.map(function(d) { return DAYS[d] || ''; }).join(', ');
}

function fmtTimeStr(t) {
  if (!t) return '';
  if (typeof t === 'string') return t.slice(0, 5);
  return '';
}

function getScheduleUrl(id) {
  return location.origin + location.pathname + '?schedule_id=' + id;
}

function getScheduleTelegramUrl(id) {
  return 'https://t.me/' + BOT_USERNAME + '/app?startapp=' + id;
}

function renderLinkCard(s, isArchived) {
  var title = escHtml(s.title || '');
  var desc = s.description ? escHtml(s.description) : '';
  var dur = sliderLabel(s.duration || 60);
  var daysStr = formatWorkDays(s.work_days || []);
  var timeStr = fmtTimeStr(s.start_time) + '–' + fmtTimeStr(s.end_time);
  var platName = PLAT_NAMES[s.platform] || s.platform || '';
  var isActive = s.is_active !== false;
  var opacity = (isArchived || !isActive) ? ';opacity:.55' : '';

  var html = '<div class="link-card" onclick="openScheduleView(\'' + s.id + '\')" style="padding:14px 16px' + opacity + '">';
  /* row 1: title + статус */
  html += '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:' + (desc ? '6' : '10') + 'px">'
    + '<div class="lc-name" style="font-size:15px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + title + '</div>'
    + '<span style="flex-shrink:0">' + (isArchived ? scheduleArchivedHtml() : scheduleStatusHtml(isActive)) + '</span>'
  + '</div>';
  /* row 2: description (if any) */
  if (desc) html += '<div style="font-size:12px;color:var(--t2);margin-bottom:10px">' + desc + '</div>';
  /* row 3: pills + buttons */
  html += '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">'
    + '<div style="display:flex;gap:5px;flex-wrap:wrap;flex:1;min-width:0">'
      + '<span class="lc-pill">' + escHtml(dur) + '</span>'
      + (daysStr ? '<span class="lc-pill">' + escHtml(daysStr) + '</span>' : '')
      + '<span class="lc-pill">' + escHtml(timeStr) + '</span>'
      + (platName ? '<span class="lc-pill">' + escHtml(platName) + '</span>' : '')
    + '</div>'
    + (isArchived
      ? '<button class="lc-btn" onclick="event.stopPropagation();restoreSchedule(\'' + s.id + '\')" style="height:32px;padding:0 12px;font-size:12px;font-weight:700;color:var(--green);background:var(--gs)">Восстановить</button>'
      : '<div style="flex-shrink:0">'
        + '<button class="lc-btn lc-share" onclick="event.stopPropagation();openShareSheet(\'' + s.id + '\')" style="height:32px;padding:0 12px;display:flex;align-items:center;gap:6px;font-size:12px;font-weight:700"><svg viewBox="0 0 24 24" style="width:14px;height:14px"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>Поделиться</button>'
      + '</div>')
  + '</div>';
  html += '</div>';
  return html;
}

/* Бейдж «Удалено» для архивных карточек */
function scheduleArchivedHtml() {
  return '<div class="mst mst-cancelled"><svg viewBox="0 0 24 24"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg><span class="mst-label">Удалено</span></div>';
}

/* Восстановить расписание из архива */
async function restoreSchedule(id) {
  var { error } = await apiFetch('PATCH', '/api/schedules/' + id, { is_active: true });
  if (error) { showToast('Не удалось восстановить', 'error'); return; }
  _unmarkDeleted(id);
  var s = (state.schedules || []).find(function(x) { return x.id === id; });
  if (s) s.is_active = true;
  loadSchedules();
  showToast('Расписание восстановлено', 'success');
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
}

/* ═══════════════════════════════════════════
   SCHEDULE DETAIL (s-link-detail)
═══════════════════════════════════════════ */
var _schedDirty = false;
var _editScheduleId = null;

function openScheduleDetail(id) {
  var s = (state.schedules || []).find(function(x) { return x.id === id; });
  if (!s) return;
  _editScheduleId = id;
  _schedDirty = false;

  /* title in header */
  var titleEl = document.getElementById('link-detail-title');
  if (titleEl) titleEl.textContent = escHtml(s.title || 'Расписание');

  /* name + desc */
  var nameInp = document.getElementById('sl-name-inp');
  if (nameInp) nameInp.value = s.title || '';
  var descInp = document.getElementById('sl-desc-inp');
  if (descInp) descInp.value = s.description || '';

  /* duration slider */
  var durInp = document.getElementById('sl-dur');
  if (durInp) {
    durInp.value = s.duration || 60;
    updateSliderSmart(durInp, 'sl-dur-val');
  }

  /* buffer slider */
  var bufInp = document.getElementById('sl-buf');
  if (bufInp) {
    bufInp.value = s.buffer_time || 0;
    updateSliderSmart(bufInp, 'sl-buf-val');
  }

  /* advance slider */
  var advInp = document.getElementById('sl-advance');
  if (advInp) {
    advInp.value = s.min_booking_advance || 0;
    updateAdvanceLabel('sl-advance', 'sl-advance-val');
  }

  /* work days */
  var daysEl = document.getElementById('sl-days');
  if (daysEl) {
    var chips = daysEl.querySelectorAll('.chip-day');
    var wd = s.work_days || [];
    chips.forEach(function(c, i) {
      if (wd.indexOf(i) >= 0) c.classList.add('on');
      else c.classList.remove('on');
    });
  }

  /* start/end time */
  var startInp = document.getElementById('sl-start');
  if (startInp) startInp.value = fmtTimeStr(s.start_time) || '09:00';
  var endInp = document.getElementById('sl-end');
  if (endInp) endInp.value = fmtTimeStr(s.end_time) || '18:00';

  /* platform chips */
  var platCont = document.getElementById('sl-platforms');
  if (platCont) {
    platCont.querySelectorAll('.chip').forEach(function(c) {
      var plat = c.getAttribute('data-plat');
      if (plat === s.platform) c.classList.add('on');
      else c.classList.remove('on');
    });
  }
  var linkWrap = document.getElementById('sl-link-wrap');
  var addrWrap = document.getElementById('sl-addr-wrap');
  var addrInp = document.getElementById('sl-addr-inp');
  if (s.platform === 'offline') {
    if (linkWrap) linkWrap.style.display = 'none';
    if (addrWrap) addrWrap.style.display = '';
    if (addrInp) addrInp.value = s.location_address || '';
  } else {
    if (linkWrap) linkWrap.style.display = (s.platform === 'other' || s.platform === 'zoom' || s.platform === 'google_meet') ? '' : 'none';
    if (addrWrap) addrWrap.style.display = 'none';
    if (addrInp) addrInp.value = '';
  }
  var linkInp = document.getElementById('sl-link-inp');
  if (linkInp) linkInp.value = s.custom_link || '';

  /* manual confirm toggle — backed by requires_confirmation field */
  var togEl = document.getElementById('sl-manual-tog');
  if (togEl) {
    if (s.requires_confirmation !== false) togEl.classList.add('on');
    else togEl.classList.remove('on');
  }

  /* pause button label */
  updatePauseBtn(s.is_active !== false);

  /* reset save button */
  resetSaveBtn();

  showScreen('s-link-detail');
}

function updatePauseBtn(isActive) {
  var btn = document.getElementById('sl-pause-btn');
  var lbl = document.getElementById('sl-pause-label');
  /* also update sheet-link-menu pause row */
  var sheetLbl = document.getElementById('sheet-pause-label');
  if (sheetLbl) sheetLbl.textContent = isActive ? 'Поставить на паузу' : 'Включить';
  if (!btn) return;
  if (isActive) {
    lbl.textContent = 'Поставить на паузу';
    btn.style.background = 'var(--ams)';
    btn.style.color = 'var(--amber)';
    btn.style.borderColor = 'rgba(245,166,35,.2)';
  } else {
    lbl.textContent = 'Включить';
    btn.style.background = 'var(--gs)';
    btn.style.color = 'var(--green)';
    btn.style.borderColor = 'rgba(45,212,160,.2)';
  }
}

function markScheduleDirty() {
  if (_schedDirty) return;
  _schedDirty = true;
  var btn = document.getElementById('sl-save-btn');
  if (btn) { btn.className = 'btn btn-primary'; }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function resetSaveBtn() {
  _schedDirty = false;
  var btn = document.getElementById('sl-save-btn');
  if (btn) { btn.className = 'btn btn-disabled'; }
}

function collectScheduleForm() {
  var nameVal = (document.getElementById('sl-name-inp') || {}).value || '';
  var descVal = (document.getElementById('sl-desc-inp') || {}).value || '';
  var dur = parseInt((document.getElementById('sl-dur') || {}).value) || 60;
  var buf = parseInt((document.getElementById('sl-buf') || {}).value) || 0;
  var startVal = (document.getElementById('sl-start') || {}).value || '09:00';
  var endVal = (document.getElementById('sl-end') || {}).value || '18:00';

  /* work days */
  var days = [];
  var daysEl = document.getElementById('sl-days');
  if (daysEl) {
    daysEl.querySelectorAll('.chip-day').forEach(function(c, i) {
      if (c.classList.contains('on')) days.push(i);
    });
  }

  /* platform */
  var plat = 'jitsi';
  var platCont = document.getElementById('sl-platforms');
  if (platCont) {
    var sel = platCont.querySelector('.chip.on');
    if (sel) plat = sel.getAttribute('data-plat') || 'jitsi';
  }

  var advance = parseInt((document.getElementById('sl-advance') || {}).value) || 0;
  var manualTog = document.getElementById('sl-manual-tog');
  var addrVal = (document.getElementById('sl-addr-inp') || {}).value || '';

  return {
    title: nameVal,
    description: descVal || null,
    duration: dur,
    buffer_time: buf,
    work_days: days,
    start_time: startVal,
    end_time: endVal,
    platform: plat,
    location_address: addrVal || null,
    min_booking_advance: advance,
    requires_confirmation: !!(manualTog && manualTog.classList.contains('on')),
    custom_link: (document.getElementById('sl-link-inp') || {}).value || null,
  };
}

async function saveScheduleChanges() {
  if (!_schedDirty || !_editScheduleId) return;
  var form = collectScheduleForm();
  if (!form.title || form.title.length < 1) {
    showToast('Введите название');
    return;
  }

  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
  var { data, error } = await apiFetch('PATCH', '/api/schedules/' + _editScheduleId, form);
  if (error) {
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast('Не удалось сохранить');
    return;
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast('Сохранено');
  resetSaveBtn();

  /* update local state */
  var idx = state.schedules.findIndex(function(x) { return x.id === _editScheduleId; });
  if (idx >= 0) {
    Object.assign(state.schedules[idx], form);
    if (data) Object.assign(state.schedules[idx], data);
  }
}

async function toggleSchedulePause() {
  if (!_editScheduleId) return;
  var s = (state.schedules || []).find(function(x) { return x.id === _editScheduleId; });
  if (!s) return;
  var currentlyActive = s.is_active !== false;
  var newActive = !currentlyActive;

  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  var { data, error } = await apiFetch('PATCH', '/api/schedules/' + _editScheduleId, {
    is_active: newActive
  });
  if (error) {
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast('Не удалось ' + (newActive ? 'активировать' : 'приостановить'), 'error');
    return;
  }

  s.is_active = newActive;
  updatePauseBtn(newActive);

  /* update s-schedule-view статус и кнопка паузы */
  var svBadge = document.getElementById('sv-status-badge');
  if (svBadge) svBadge.innerHTML = scheduleStatusHtml(newActive);
  var svPauseLabel = document.getElementById('sv-pause-label');
  var svPauseBtn = document.getElementById('sv-pause-btn');
  if (svPauseLabel && svPauseBtn) {
    if (newActive) {
      svPauseLabel.textContent = 'Приостановить';
      svPauseBtn.style.background = 'var(--ams)';
      svPauseBtn.style.color = 'var(--amber)';
    } else {
      svPauseLabel.textContent = 'Включить';
      svPauseBtn.style.background = 'var(--gs)';
      svPauseBtn.style.color = 'var(--green)';
    }
  }

  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast(newActive ? 'Расписание активировано' : 'Расписание на паузе', 'success');
}

function scheduleBack() {
  if (_schedDirty) {
    /* just go back — user chose not to save */
    _schedDirty = false;
  }
  goBack();
}

/* ═══════════════════════════════════════════
   SCHEDULE VIEW (read-only, s-schedule-view)
═══════════════════════════════════════════ */
function openScheduleView(id) {
  var s = (state.schedules || []).find(function(x) { return x.id === id; });
  if (!s) return;
  _editScheduleId = id;

  var el;
  el = document.getElementById('sv-title'); if (el) el.textContent = s.title || 'Расписание';
  el = document.getElementById('sv-name'); if (el) el.textContent = s.title || '';
  el = document.getElementById('sv-desc'); if (el) el.textContent = s.description || '—';
  el = document.getElementById('sv-desc-row'); if (el) el.style.display = s.description ? '' : 'none';
  el = document.getElementById('sv-duration'); if (el) el.textContent = sliderLabel(s.duration || 60);
  el = document.getElementById('sv-buffer'); if (el) el.textContent = s.buffer_time ? sliderLabel(s.buffer_time) : 'Нет';
  el = document.getElementById('sv-days'); if (el) el.textContent = formatWorkDays(s.work_days || []);
  el = document.getElementById('sv-time'); if (el) el.textContent = fmtTimeStr(s.start_time) + ' – ' + fmtTimeStr(s.end_time);
  el = document.getElementById('sv-platform'); if (el) el.textContent = PLAT_NAMES[s.platform] || s.platform || '';

  /* advance row */
  var advRow = document.getElementById('sv-advance-row');
  var advVal = document.getElementById('sv-advance');
  if (advRow && advVal) {
    var adv = s.min_booking_advance || 0;
    if (adv > 0) {
      advRow.style.display = '';
      advVal.textContent = advanceLabel(adv);
    } else {
      advRow.style.display = 'none';
    }
  }

  var isActive = s.is_active !== false;
  var badgeEl = document.getElementById('sv-status-badge');
  if (badgeEl) badgeEl.innerHTML = scheduleStatusHtml(isActive);
  var svPauseLabel = document.getElementById('sv-pause-label');
  var svPauseBtn = document.getElementById('sv-pause-btn');
  if (svPauseLabel && svPauseBtn) {
    if (isActive) {
      svPauseLabel.textContent = 'Приостановить';
      svPauseBtn.style.background = 'var(--ams)';
      svPauseBtn.style.color = 'var(--amber)';
    } else {
      svPauseLabel.textContent = 'Включить';
      svPauseBtn.style.background = 'var(--gs)';
      svPauseBtn.style.color = 'var(--green)';
    }
  }

  showScreen('s-schedule-view');
  loadScheduleCalConfig(id);
}

function editCurrentSchedule() {
  if (_editScheduleId) openScheduleDetail(_editScheduleId);
}

function previewAsGuest() {
  var scheduleId = _editScheduleId;
  if (!scheduleId) return;
  state._previewMode = true;
  state._previewReturnScreen = 's-schedule-view';
  showScreen('s-calendar');
  loadCalendar(scheduleId);
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

/* ═══════════════════════════════════════════
   ADVANCE LABEL HELPER
═══════════════════════════════════════════ */
function advanceLabel(mins) {
  mins = parseInt(mins);
  if (!mins || mins <= 0) return 'Нет';
  if (mins < 60) return mins + ' мин';
  if (mins === 60) return '1 ч';
  if (mins < 1440) {
    var h = Math.floor(mins / 60), m = mins % 60;
    return h + ' ч' + (m ? ' ' + m + ' мин' : '');
  }
  if (mins === 1440) return '1 дн';
  var d = Math.floor(mins / 1440);
  return d + ' дн';
}

function updateAdvanceLabel(inputId, labelId) {
  var val = parseInt((document.getElementById(inputId) || {}).value) || 0;
  var labelEl = document.getElementById(labelId);
  if (!labelEl) return;
  labelEl.textContent = advanceLabel(val);
  var inp = document.getElementById(inputId);
  if (inp) {
    var pct = ((val - inp.min) / (inp.max - inp.min)) * 100;
    inp.style.background = 'linear-gradient(to right,var(--a) ' + pct + '%,var(--s3) ' + pct + '%)';
  }
}

function pickPlatEdit(el) {
  var cont = el.parentElement;
  if (!cont) return;
  cont.querySelectorAll('.chip').forEach(function(c) { c.classList.remove('on'); });
  el.classList.add('on');
  var plat = el.getAttribute('data-plat');
  var linkWrap = document.getElementById('sl-link-wrap');
  var addrWrap = document.getElementById('sl-addr-wrap');
  if (plat === 'offline') {
    if (linkWrap) linkWrap.style.display = 'none';
    if (addrWrap) addrWrap.style.display = '';
  } else if (plat === 'other' || plat === 'zoom' || plat === 'google_meet') {
    if (linkWrap) linkWrap.style.display = '';
    if (addrWrap) addrWrap.style.display = 'none';
  } else {
    if (linkWrap) linkWrap.style.display = 'none';
    if (addrWrap) addrWrap.style.display = 'none';
  }
  markScheduleDirty();
}

/* ═══════════════════════════════════════════
   SLIDER SMART + IEO INTEGRATION
═══════════════════════════════════════════ */
function updateSliderSmart(inp, valId) {
  var v = parseInt(inp.value);
  var el = document.getElementById(valId);
  if (el) el.textContent = sliderLabel(v);
  var pct = ((v - inp.min) / (inp.max - inp.min)) * 100;
  inp.style.background = 'linear-gradient(to right,var(--a) ' + pct + '%,var(--s3) ' + pct + '%)';
}

var _ieoSliderId = null;
var _ieoLabelId = null;

function openSliderEdit(sliderId, labelId, min, max, unit, title) {
  _ieoSliderId = sliderId;
  _ieoLabelId = labelId;
  var inp = document.getElementById(sliderId);
  var val = inp ? parseInt(inp.value) : 0;
  showIeo(title, val, unit);
}

/* ═══════════════════════════════════════════
   SHARE / COPY / DELETE ACTIONS
═══════════════════════════════════════════ */
function openShareSheet(schedId) {
  var id = schedId || _editScheduleId;
  if (!id) { showSheet('sheet-share'); return; }
  state._shareScheduleId = id;
  var url = getScheduleUrl(id);
  state._shareUrl = url;
  var el = document.getElementById('sheet-share-url');
  if (el) el.textContent = url.replace(/^https?:\/\//, '');
  showSheet('sheet-share');
}

/* Общий текст для шаринга (формат как в inline-режиме бота) */
function buildShareText(schedule) {
  if (!schedule) return '';
  var title = schedule.title || 'Встреча';
  var dur = schedule.duration || 60;
  var plat = PLAT_NAMES[schedule.platform] || schedule.platform || '';
  var days = formatWorkDays(schedule.work_days);
  var start = fmtTimeStr(schedule.start_time) || '';
  var end = fmtTimeStr(schedule.end_time) || '';
  var desc = schedule.description || '';

  var text = '📅 ' + title + '\n\n'
    + '⏱ ' + dur + ' мин · ' + plat + '\n';
  if (days) text += '📆 ' + days + ', ' + start + '–' + end + '\n';
  if (desc) text += '📝 ' + desc + '\n';
  text += '\n👉 Записаться на встречу';
  return text;
}

function shareTelegram() {
  var schedId = state._shareScheduleId || _editScheduleId || '';
  var url = schedId ? getScheduleTelegramUrl(schedId) : state._shareUrl;
  closeSheet('sheet-share');
  if (!url) return;

  var schedule = (state.schedules || []).find(function(s) { return s.id === schedId; });
  var text = buildShareText(schedule) || '📅 Запишись ко мне';

  var shareUrl = 'https://t.me/share/url'
    + '?url=' + encodeURIComponent(url)
    + '&text=' + encodeURIComponent(text);

  if (tg?.openTelegramLink) {
    tg.openTelegramLink(shareUrl);
  } else {
    window.open(shareUrl, '_blank');
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function copyShareLink() {
  if (state._shareUrl) copyText(state._shareUrl);
  closeSheet('sheet-share');
  showToast('Ссылка скопирована');
}

function copyScheduleLink(id) {
  var url = getScheduleUrl(id || _editScheduleId);
  copyText(url);
  showToast('Ссылка скопирована');
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
}

function pauseSchedule() {
  toggleSchedulePause();
}

async function openDeleteConfirm() {
  var id = _editScheduleId;
  if (!id) return;

  /* Check for future bookings on this schedule */
  var hasFuture = false;
  var futureCount = 0;
  var { data } = await apiFetch('GET', '/api/bookings?schedule_id=' + id + '&future_only=true');
  if (data && Array.isArray(data)) {
    futureCount = data.length;
    hasFuture = futureCount > 0;
  }

  state.pendingDeleteId = id;

  var titleEl = document.getElementById('sheet-delete-title');
  var subEl   = document.getElementById('sheet-delete-sub');
  var keepDiv = document.getElementById('sheet-delete-keep');
  var cancelAllDiv = document.getElementById('sheet-delete-cancel-all');
  var simpleDiv = document.getElementById('sheet-delete-simple');

  if (titleEl) titleEl.textContent = 'Удалить расписание?';

  if (hasFuture) {
    if (subEl) subEl.innerHTML = 'У этого расписания <b>' + futureCount + ' ' + _pluralMeetings(futureCount) + '</b>.<br>Что с ними сделать?';
    if (keepDiv) keepDiv.style.display = '';
    if (cancelAllDiv) cancelAllDiv.style.display = '';
    if (simpleDiv) simpleDiv.style.display = 'none';
  } else {
    if (subEl) subEl.textContent = 'Расписание будет перемещено в архив.';
    if (keepDiv) keepDiv.style.display = 'none';
    if (cancelAllDiv) cancelAllDiv.style.display = 'none';
    if (simpleDiv) simpleDiv.style.display = '';
  }

  showSheet('sheet-delete-schedule');
}

function _pluralMeetings(n) {
  if (n % 10 === 1 && n % 100 !== 11) return 'активная встреча';
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return 'активные встречи';
  return 'активных встреч';
}

function _finishScheduleDelete(id, toast) {
  _markDeleted(id);
  var s = (state.schedules || []).find(function(x) { return x.id === id; });
  if (s) s.is_active = false;
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast(toast, 'success');
  state.pendingDeleteId = null;
  goBack();
  loadSchedules();
}

async function deleteScheduleKeepMeetings() {
  var id = state.pendingDeleteId;
  if (!id) return;
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
  var { error } = await apiFetch('DELETE', '/api/schedules/' + id + '?cancel_meetings=false');
  closeSheet('sheet-delete-schedule');
  if (error) { showToast('Не удалось удалить', 'error'); return; }
  _finishScheduleDelete(id, 'Расписание удалено, встречи сохранены');
}

async function deleteScheduleCancelMeetings() {
  var id = state.pendingDeleteId;
  if (!id) return;
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('heavy');
  var { error } = await apiFetch('DELETE', '/api/schedules/' + id + '?cancel_meetings=true');
  closeSheet('sheet-delete-schedule');
  if (error) { showToast('Не удалось удалить', 'error'); return; }
  _finishScheduleDelete(id, 'Расписание и встречи удалены');
  if (typeof loadMeetings === 'function') loadMeetings();
}

/* kept for backward compat — called from confirmCancelMeeting() when _deleteMode=true */
async function confirmDeleteSchedule() {
  await deleteScheduleKeepMeetings();
}

/* ═══════════════════════════════════════════
   CREATE SCHEDULE (s-new-link)
═══════════════════════════════════════════ */
function startCreate() { openNewSchedule(); }

function openNewSchedule() {
  /* reset all fields to defaults */
  var el;
  el = document.getElementById('nw-name-inp'); if (el) el.value = '';
  el = document.getElementById('nw-desc-inp'); if (el) el.value = '';

  /* duration 60 */
  var durInp = document.getElementById('nw-dur');
  if (durInp) { durInp.value = 60; updateSliderSmart(durInp, 'nw-dur-val'); }

  /* buffer 0 */
  var bufInp = document.getElementById('nw-buf');
  if (bufInp) { bufInp.value = 0; updateSliderSmart(bufInp, 'nw-buf-val'); }

  /* advance 0 */
  var advInp = document.getElementById('nw-advance');
  if (advInp) { advInp.value = 0; updateAdvanceLabel('nw-advance', 'nw-advance-val'); }

  /* Пн–Пт on, Сб Вс off */
  var daysEl = document.getElementById('nw-days');
  if (daysEl) {
    daysEl.querySelectorAll('.chip-day').forEach(function(c, i) {
      if (i < 5) c.classList.add('on'); else c.classList.remove('on');
    });
  }

  /* time 10:00-18:00 */
  el = document.getElementById('nw-start'); if (el) el.value = '10:00';
  el = document.getElementById('nw-end'); if (el) el.value = '18:00';

  /* platform: jitsi selected */
  var platCont = document.getElementById('nw-platforms');
  if (platCont) {
    platCont.querySelectorAll('.chip').forEach(function(c) {
      if (c.getAttribute('data-plat') === 'jitsi') c.classList.add('on');
      else c.classList.remove('on');
    });
  }
  el = document.getElementById('nw-link-wrap'); if (el) el.style.display = 'none';
  el = document.getElementById('nw-link-inp'); if (el) el.value = '';
  el = document.getElementById('nw-addr-wrap'); if (el) el.style.display = 'none';
  el = document.getElementById('nw-addr-inp'); if (el) el.value = '';

  /* manual confirm toggle — default ON (require confirmation) */
  el = document.getElementById('nw-manual-tog'); if (el) el.classList.add('on');

  /* reset button */
  var btn = document.getElementById('nw-submit-btn');
  if (btn) { btn.className = 'btn btn-primary'; btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>Создать расписание'; }

  showScreen('s-new-link');
}

function cancelCreate() {
  goBack();
}

function getFormScheduleData() {
  var nameVal = (document.getElementById('nw-name-inp') || {}).value || '';
  var descVal = (document.getElementById('nw-desc-inp') || {}).value || '';
  var dur = parseInt((document.getElementById('nw-dur') || {}).value) || 60;
  var buf = parseInt((document.getElementById('nw-buf') || {}).value) || 0;
  var startVal = (document.getElementById('nw-start') || {}).value || '10:00';
  var endVal = (document.getElementById('nw-end') || {}).value || '18:00';

  var days = [];
  var daysEl = document.getElementById('nw-days');
  if (daysEl) {
    daysEl.querySelectorAll('.chip-day').forEach(function(c, i) {
      if (c.classList.contains('on')) days.push(i);
    });
  }

  var plat = 'jitsi';
  var platCont = document.getElementById('nw-platforms');
  if (platCont) {
    var sel = platCont.querySelector('.chip.on');
    if (sel) plat = sel.getAttribute('data-plat') || 'jitsi';
  }

  var advance = parseInt((document.getElementById('nw-advance') || {}).value) || 0;
  var manualTog = document.getElementById('nw-manual-tog');
  var addrVal = (document.getElementById('nw-addr-inp') || {}).value || '';

  return {
    title: nameVal,
    description: descVal || null,
    duration: dur,
    buffer_time: buf,
    work_days: days,
    start_time: startVal,
    end_time: endVal,
    location_mode: 'fixed',
    platform: plat,
    location_address: addrVal || null,
    min_booking_advance: advance,
    requires_confirmation: !!(manualTog && manualTog.classList.contains('on')),
    custom_link: (document.getElementById('nw-link-inp') || {}).value || null,
  };
}

function pickPlatNew(el) {
  var cont = document.getElementById('nw-platforms');
  if (cont) cont.querySelectorAll('.chip').forEach(function(c) { c.classList.remove('on'); });
  el.classList.add('on');
  var plat = el.getAttribute('data-plat');
  var linkWrap = document.getElementById('nw-link-wrap');
  var addrWrap = document.getElementById('nw-addr-wrap');
  if (plat === 'offline') {
    if (linkWrap) linkWrap.style.display = 'none';
    if (addrWrap) addrWrap.style.display = '';
  } else if (plat === 'other' || plat === 'zoom' || plat === 'google_meet') {
    if (linkWrap) linkWrap.style.display = '';
    if (addrWrap) addrWrap.style.display = 'none';
  } else {
    if (linkWrap) linkWrap.style.display = 'none';
    if (addrWrap) addrWrap.style.display = 'none';
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

async function submitNewSchedule() {
  var form = getFormScheduleData();

  /* validate */
  if (!form.title || form.title.trim().length < 1) {
    showToast('Введите название');
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    return;
  }
  if (form.work_days.length === 0) {
    showToast('Выберите хотя бы один день');
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    return;
  }

  /* loading state */
  var btn = document.getElementById('nw-submit-btn');
  if (btn) { btn.className = 'btn btn-disabled'; btn.disabled = true; btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px"></div>Создание…'; }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  var { data, error } = await apiFetch('POST', '/api/schedules', form);

  /* restore button */
  if (btn) { btn.className = 'btn btn-primary'; btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>Создать расписание'; }

  if (error) {
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast('Не удалось создать: ' + error);
    return;
  }

  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast('Расписание создано ✓', 'success');

  /* add to local state */
  if (data) {
    if (!state.schedules) state.schedules = [];
    state.schedules.unshift(data);
  }

  goBack();
  loadSchedules();
}

/* ═══════════════════════════════════════════
   SCHEDULE CALENDAR CONFIG (sv-cal-config)
═══════════════════════════════════════════ */
var _schedCalSaveTimer = null;

async function loadScheduleCalConfig(scheduleId) {
  var container = document.getElementById('sv-cal-config');
  if (!container) return;

  /* parallel fetch: accounts + current rules */
  var results = await Promise.all([
    apiFetch('GET', '/api/calendar/accounts'),
    apiFetch('GET', '/api/calendar/schedules/' + scheduleId + '/calendar-config'),
  ]);
  var accounts = (results[0].data || []).filter(function(a) {
    return a.status === 'active' || a.status === 'active';
  });
  var rules = (results[1].data && results[1].data.rules) ? results[1].data.rules : [];

  /* flatten connections from all active accounts */
  var connections = [];
  accounts.forEach(function(acc) {
    (acc.calendars || []).forEach(function(c) {
      connections.push({
        id: c.id,
        calendar_name: c.calendar_name,
        calendar_color: c.calendar_color || '#888',
        provider: acc.provider,
      });
    });
  });

  container.innerHTML = renderSchedCalSection(scheduleId, accounts, connections, rules);
}

function renderSchedCalSection(scheduleId, accounts, connections, rules) {
  var sid = escHtml(String(scheduleId));

  /* build rules lookup */
  var rulesMap = {};
  rules.forEach(function(r) { rulesMap[r.connection_id] = r; });

  var inner = '';

  if (!accounts.length) {
    /* no accounts at all → CTA */
    inner = '<div style="padding:0 16px 24px">'
      + '<div class="sc-cal-cta" onclick="showScreen(\'s-calendars\')">'
      +   '<div class="sc-cal-cta-icon">'
      +     '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="var(--a)" stroke-width="2" stroke-linecap="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/></svg>'
      +   '</div>'
      +   '<div class="sc-cal-cta-text">'
      +     '<div class="sc-cal-cta-title">Подключите календарь</div>'
      +     '<div class="sc-cal-cta-sub">Блокируйте занятые слоты из Google Calendar</div>'
      +   '</div>'
      +   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="var(--t3)" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>'
      + '</div>'
      + '</div>';
  } else if (!connections.length) {
    /* accounts exist but no calendars yet */
    inner = '<div style="padding:0 16px 24px;font-size:12px;color:var(--t3);text-align:center;padding-top:8px">Синхронизация календарей…</div>';
  } else {
    /* list of connections with checkbox (blocking) + radio (write target) */
    var rows = connections.map(function(c) {
      var cid = escHtml(String(c.id));
      var rule = rulesMap[c.id] || {};
      var blocking = rule.use_for_blocking !== false; /* default ON */
      var writing  = rule.use_for_writing === true;
      var colorSafe = escHtml(c.calendar_color || '#888');

      return '<div class="sc-cal-row">'
        + '<div class="sc-cal-dot" style="background:' + colorSafe + '"></div>'
        + '<div class="sc-cal-info"><div class="sc-cal-name">' + escHtml(c.calendar_name) + '</div></div>'
        + '<div class="sc-cal-controls">'
        +   '<label class="sc-cal-label" title="Учитывать занятость при показе свободных слотов">'
        +     '<input type="checkbox" class="sc-cal-cb"'
        +     ' data-conn="' + cid + '" data-schedid="' + sid + '"'
        +     (blocking ? ' checked' : '')
        +     ' onclick="onSchedCalChange(\'' + sid + '\')">'
        +     '<span>Занятость</span>'
        +   '</label>'
        +   '<label class="sc-cal-label" title="Записывать бронирования в этот календарь">'
        +     '<input type="radio" class="sc-cal-rb"'
        +     ' name="sc-write-' + sid + '"'
        +     ' data-conn="' + cid + '" data-schedid="' + sid + '"'
        +     (writing ? ' checked' : '')
        +     ' onclick="onSchedCalChange(\'' + sid + '\')">'
        +     '<span>Запись</span>'
        +   '</label>'
        + '</div>'
        + '</div>';
    }).join('');

    inner = '<div style="padding:0 16px 24px"><div class="sc-cal-list">' + rows + '</div></div>';
  }

  return '<div style="margin-top:4px">'
    + '<div class="group-title" style="padding-top:24px">Внешние календари</div>'
    + inner
    + '</div>';
}

function onSchedCalChange(scheduleId) {
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
  if (_schedCalSaveTimer) clearTimeout(_schedCalSaveTimer);
  _schedCalSaveTimer = setTimeout(function() {
    saveScheduleCalConfig(scheduleId);
  }, 500);
}

async function saveScheduleCalConfig(scheduleId) {
  var container = document.getElementById('sv-cal-config');
  if (!container) return;

  var rules = [];
  container.querySelectorAll('.sc-cal-cb').forEach(function(cb) {
    var connId = cb.getAttribute('data-conn');
    var radio = container.querySelector('.sc-cal-rb[data-conn="' + connId + '"]');
    rules.push({
      connection_id: connId,
      use_for_blocking: cb.checked,
      use_for_writing: radio ? radio.checked : false,
    });
  });

  var result = await apiFetch('PUT', '/api/calendar/schedules/' + scheduleId + '/calendar-config', {
    rules: rules,
  });

  if (result.error) {
    if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast('Ошибка сохранения', 'error');
    return;
  }

  if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast('Сохранено');
}

