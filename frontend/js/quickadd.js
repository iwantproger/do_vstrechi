/* ═══════════════════════════════════════════
   QUICK ADD MEETING
═══════════════════════════════════════════ */
'use strict';

var _qaScheduleId = null;

async function openQuickAdd() {
  /* Load schedules if not cached */
  if (!state.schedules || !state.schedules.length) {
    var resp = await apiFetch('GET', '/api/schedules');
    if (resp.data) state.schedules = resp.data;
  }

  /* Default times: next full hour → +1h */
  var now = new Date();
  var nextH = new Date(now);
  nextH.setHours(now.getHours() + 1, 0, 0, 0);
  var endH = new Date(nextH);
  endH.setHours(nextH.getHours() + 1);

  document.getElementById('qa-title').value = '';
  document.getElementById('qa-notes').value = '';
  document.getElementById('qa-start-date').value = _qaISO(nextH);
  document.getElementById('qa-start-time').value = _qaHM(nextH);
  document.getElementById('qa-end-date').value = _qaISO(endH);
  document.getElementById('qa-end-time').value = _qaHM(endH);

  _qaScheduleId = null;
  document.getElementById('qa-schedule-label').textContent = 'Без расписания';

  var togEl = document.getElementById('qa-block-slots');
  if (togEl && !togEl.classList.contains('on')) togEl.classList.add('on');

  showScreen('s-quick-add');
  hideNavbar();
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function closeQuickAdd() {
  goBack();
}

/* ── Date/Time sync ── */
function onQaStartChange() {
  var sd = document.getElementById('qa-start-date').value;
  var st = document.getElementById('qa-start-time').value;
  var ed = document.getElementById('qa-end-date').value;
  var et = document.getElementById('qa-end-time').value;
  if (!sd || !st) return;

  var startDt = new Date(sd + 'T' + st);
  var endDt = (ed && et) ? new Date(ed + 'T' + et) : null;

  if (!endDt || endDt <= startDt) {
    var newEnd = new Date(startDt);
    newEnd.setHours(newEnd.getHours() + 1);
    document.getElementById('qa-end-date').value = _qaISO(newEnd);
    document.getElementById('qa-end-time').value = _qaHM(newEnd);
  }
}

function onQaEndChange() {
  var sd = document.getElementById('qa-start-date').value;
  var st = document.getElementById('qa-start-time').value;
  var ed = document.getElementById('qa-end-date').value;
  var et = document.getElementById('qa-end-time').value;
  if (!sd || !st || !ed || !et) return;

  var startDt = new Date(sd + 'T' + st);
  var endDt = new Date(ed + 'T' + et);
  if (endDt <= startDt) {
    showToast('Конец должен быть после начала', 'error');
  }
}

/* ── Schedule picker ── */
async function openSchedulePicker() {
  if (!state.schedules || !state.schedules.length) {
    var resp = await apiFetch('GET', '/api/schedules');
    if (resp.data) state.schedules = resp.data;
  }

  var list = document.getElementById('qa-schedule-list');
  var schedules = state.schedules || [];
  var html = '';

  /* "Без расписания" */
  var isNone = !_qaScheduleId;
  html += '<div class="qa-sched-item" onclick="pickSchedule(null, \'Без расписания\')">'
    + '<div><div class="qa-sched-item-title">Без расписания</div>'
    + '<div class="qa-sched-item-sub">Личная встреча</div></div>'
    + (isNone ? '<svg class="qa-sched-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>' : '')
    + '</div>';

  schedules.forEach(function(s) {
    if (s.is_active === false) return;
    var isSel = _qaScheduleId === s.id;
    html += '<div class="qa-sched-item" onclick="pickSchedule(\'' + s.id + '\', \'' + escHtml(s.title) + '\')">'
      + '<div><div class="qa-sched-item-title">' + escHtml(s.title) + '</div>'
      + '<div class="qa-sched-item-sub">' + (s.duration || 60) + ' мин · ' + (PLAT_NAMES[s.platform] || s.platform) + '</div></div>'
      + (isSel ? '<svg class="qa-sched-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>' : '')
      + '</div>';
  });

  list.innerHTML = html;
  showScreen('s-schedule-picker');
}

function pickSchedule(id, title) {
  _qaScheduleId = id;
  document.getElementById('qa-schedule-label').textContent = title;
  goBack();
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

/* ── Submit ── */
async function submitQuickAdd() {
  var title = (document.getElementById('qa-title').value || '').trim();
  if (!title) {
    showToast('Введите название', 'error');
    return;
  }

  var startDate = document.getElementById('qa-start-date').value;
  var startTime = document.getElementById('qa-start-time').value;
  var endDate = document.getElementById('qa-end-date').value;
  var endTime = document.getElementById('qa-end-time').value;
  var notes = (document.getElementById('qa-notes').value || '').trim();

  if (!startDate || !startTime) {
    showToast('Выберите дату и время начала', 'error');
    return;
  }

  var blocksSlots = document.getElementById('qa-block-slots').classList.contains('on');

  var body = {
    title: title,
    date: startDate,
    start_time: startTime,
    end_time: endTime || null,
    end_date: endDate !== startDate ? endDate : null,
    schedule_id: _qaScheduleId || null,
    notes: notes || null,
    blocks_slots: blocksSlots
  };

  var btn = document.getElementById('qa-submit-btn');
  btn.disabled = true;
  btn.style.opacity = '0.5';

  var result = await apiFetch('POST', '/api/meetings/quick', body);

  btn.disabled = false;
  btn.style.opacity = '';

  if (result.error) {
    showToast(result.error.detail || 'Ошибка создания', 'error');
    if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    return;
  }

  if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  goBack();
  showToast('Встреча создана', 'success');

  if (typeof loadHome === 'function' && state.currentScreen === 's-home') loadHome();
  if (typeof loadMeetings === 'function' && state.currentScreen === 's-meetings') loadMeetings();
}

/* ── Helpers ── */
function _qaISO(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function _qaHM(d) {
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}
