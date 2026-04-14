/* ═══════════════════════════════════════════
   QUICK ADD MEETING — Apple Calendar Style
═══════════════════════════════════════════ */
'use strict';

var _qaScheduleId = null;
var _qaScheduleTitle = 'Без расписания';
var _qaOpenPicker = null;

function openQuickAdd() {
  _qaScheduleId = null;
  _qaScheduleTitle = 'Без расписания';
  _qaOpenPicker = null;

  // Defaults: next full hour → +1h
  var now = new Date();
  var nextHour = new Date(now);
  nextHour.setHours(now.getHours() + 1, 0, 0, 0);
  var endHour = new Date(nextHour);
  endHour.setHours(nextHour.getHours() + 1);

  document.getElementById('qa-title').value = '';
  document.getElementById('qa-notes').value = '';

  // Start
  document.getElementById('qa-start-date-input').value = _qaISODate(nextHour);
  document.getElementById('qa-start-time-input').value = _qaHHMM(nextHour);
  document.getElementById('qa-start-date-label').textContent = _qaDateLabel(nextHour);
  document.getElementById('qa-start-time-label').textContent = _qaHHMM(nextHour);

  // End
  document.getElementById('qa-end-date-input').value = _qaISODate(endHour);
  document.getElementById('qa-end-time-input').value = _qaHHMM(endHour);
  document.getElementById('qa-end-date-label').textContent = _qaDateLabel(endHour);
  document.getElementById('qa-end-time-label').textContent = _qaHHMM(endHour);

  document.getElementById('qa-schedule-label').textContent = _qaScheduleTitle;
  updateQaSaveBtn();
  _qaCloseAllPickers();

  document.getElementById('qa-overlay').style.display = '';
  setTimeout(function() { document.getElementById('qa-title').focus(); }, 350);
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function closeQuickAdd() {
  document.getElementById('qa-overlay').style.display = 'none';
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

/* ── Save button state ── */
function updateQaSaveBtn() {
  var btn = document.getElementById('qa-save-btn');
  var title = (document.getElementById('qa-title').value || '').trim();
  btn.classList.toggle('active', title.length > 0);
}

document.addEventListener('input', function(e) {
  if (e.target.id === 'qa-title') updateQaSaveBtn();
});

/* ── Date/Time pickers ── */
function toggleQaPicker(pickerId) {
  var wrap = document.getElementById('qa-picker-' + pickerId);
  if (!wrap) return;

  var isOpen = wrap.style.display !== 'none';
  _qaCloseAllPickers();

  if (!isOpen) {
    wrap.style.display = '';
    _qaOpenPicker = pickerId;
    var chips = {
      'start-date': 'qa-start-date-label',
      'start-time': 'qa-start-time-label',
      'end-date': 'qa-end-date-label',
      'end-time': 'qa-end-time-label'
    };
    var chipEl = document.getElementById(chips[pickerId]);
    if (chipEl) chipEl.classList.add('active');
  }
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function _qaCloseAllPickers() {
  ['start-date', 'start-time', 'end-date', 'end-time'].forEach(function(id) {
    var w = document.getElementById('qa-picker-' + id);
    if (w) w.style.display = 'none';
  });
  document.querySelectorAll('.qa-date-chip, .qa-time-chip').forEach(function(el) {
    el.classList.remove('active');
  });
  _qaOpenPicker = null;
}

function onQaDateChange(which) {
  var input = document.getElementById('qa-' + which + '-date-input');
  var label = document.getElementById('qa-' + which + '-date-label');
  if (input && label) {
    var d = new Date(input.value + 'T00:00');
    label.textContent = _qaDateLabel(d);
  }
  _qaSyncEnd();
}

function onQaTimeChange(which) {
  var input = document.getElementById('qa-' + which + '-time-input');
  var label = document.getElementById('qa-' + which + '-time-label');
  if (input && label) label.textContent = input.value;
  _qaSyncEnd();
}

function _qaSyncEnd() {
  var sd = document.getElementById('qa-start-date-input').value;
  var st = document.getElementById('qa-start-time-input').value;
  var ed = document.getElementById('qa-end-date-input').value;
  var et = document.getElementById('qa-end-time-input').value;
  if (!sd || !st || !ed || !et) return;

  var startDt = new Date(sd + 'T' + st);
  var endDt = new Date(ed + 'T' + et);
  if (endDt <= startDt) {
    var newEnd = new Date(startDt);
    newEnd.setHours(newEnd.getHours() + 1);
    document.getElementById('qa-end-date-input').value = _qaISODate(newEnd);
    document.getElementById('qa-end-time-input').value = _qaHHMM(newEnd);
    document.getElementById('qa-end-date-label').textContent = _qaDateLabel(newEnd);
    document.getElementById('qa-end-time-label').textContent = _qaHHMM(newEnd);
  }
}

/* ── Schedule picker ── */
function openSchedulePicker() {
  var list = document.getElementById('qa-schedule-list');
  var schedules = state.schedules || [];

  var html = '';

  // "Без расписания"
  var isNone = !_qaScheduleId;
  html += '<div class="qa-sched-item" onclick="pickSchedule(null, \'Без расписания\')">'
    + '<div>'
    + '<div class="qa-sched-item-title">Без расписания</div>'
    + '<div class="qa-sched-item-sub">Личная встреча</div>'
    + '</div>'
    + (isNone ? '<svg class="qa-sched-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>' : '')
    + '</div>';

  schedules.forEach(function(s) {
    if (s.is_active === false) return;
    var isSel = _qaScheduleId === s.id;
    html += '<div class="qa-sched-item" onclick="pickSchedule(\'' + s.id + '\', \'' + escHtml(s.title) + '\')">'
      + '<div>'
      + '<div class="qa-sched-item-title">' + escHtml(s.title) + '</div>'
      + '<div class="qa-sched-item-sub">' + (s.duration || 60) + ' мин · ' + (PLAT_NAMES[s.platform] || s.platform) + '</div>'
      + '</div>'
      + (isSel ? '<svg class="qa-sched-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>' : '')
      + '</div>';
  });

  list.innerHTML = html;
  document.getElementById('qa-schedule-picker').style.display = '';
}

function closeSchedulePicker() {
  document.getElementById('qa-schedule-picker').style.display = 'none';
}

function pickSchedule(id, title) {
  _qaScheduleId = id;
  _qaScheduleTitle = title;
  document.getElementById('qa-schedule-label').textContent = title;
  closeSchedulePicker();
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

/* ── Submit ── */
async function submitQuickAdd() {
  var title = (document.getElementById('qa-title').value || '').trim();
  if (!title) {
    showToast('Введите название', 'error');
    return;
  }

  var startDate = document.getElementById('qa-start-date-input').value;
  var startTime = document.getElementById('qa-start-time-input').value;
  var endDate = document.getElementById('qa-end-date-input').value;
  var endTime = document.getElementById('qa-end-time-input').value;
  var notes = (document.getElementById('qa-notes').value || '').trim();

  if (!startDate || !startTime) {
    showToast('Выберите дату и время начала', 'error');
    return;
  }

  var body = {
    title: title,
    date: startDate,
    start_time: startTime,
    end_time: endTime || null,
    end_date: endDate !== startDate ? endDate : null,
    schedule_id: _qaScheduleId || null,
    notes: notes || null
  };

  var btn = document.getElementById('qa-save-btn');
  btn.style.pointerEvents = 'none';
  btn.style.opacity = '0.5';

  var result = await apiFetch('POST', '/api/meetings/quick', body);

  btn.style.pointerEvents = '';
  btn.style.opacity = '';

  if (result.error) {
    showToast(result.error.detail || 'Ошибка создания', 'error');
    if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    return;
  }

  if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  closeQuickAdd();
  showToast('Встреча создана', 'success');

  if (typeof loadHome === 'function' && state.currentScreen === 's-home') loadHome();
  if (typeof loadMeetings === 'function' && state.currentScreen === 's-meetings') loadMeetings();
}

/* ── Helpers ── */
function _qaISODate(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function _qaHHMM(d) {
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function _qaDateLabel(d) {
  var months = ['янв.', 'фев.', 'мар.', 'апр.', 'мая', 'июн.', 'июл.', 'авг.', 'сен.', 'окт.', 'ноя.', 'дек.'];
  return d.getDate() + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();
}
