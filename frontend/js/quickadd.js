/* ═══════════════════════════════════════════
   QUICK ADD MEETING
═══════════════════════════════════════════ */
var _qaMode = 'personal';
var _qaSelectedSlot = null;
var _qaSchedules = [];

function openQuickAdd() {
  // Reset form
  _qaMode = 'personal';
  _qaSelectedSlot = null;
  document.getElementById('qa-title').value = '';
  var today = new Date();
  var yyyy = today.getFullYear();
  var mm = String(today.getMonth() + 1).padStart(2, '0');
  var dd = String(today.getDate()).padStart(2, '0');
  document.getElementById('qa-date').value = yyyy + '-' + mm + '-' + dd;
  document.getElementById('qa-time').value = '';
  document.getElementById('qa-sched-date').value = yyyy + '-' + mm + '-' + dd;
  document.getElementById('qa-guest-name').value = '';
  document.getElementById('qa-guest-contact').value = '';
  document.getElementById('qa-notes').value = '';
  document.getElementById('qa-error').style.display = 'none';
  document.getElementById('qa-extra-fields').style.display = 'none';
  document.getElementById('qa-extra-lbl').textContent = 'Участник и заметки';
  document.getElementById('qa-slots-wrap').style.display = 'none';
  document.getElementById('qa-slots').innerHTML = '';
  document.getElementById('qa-submit-btn').textContent = 'Создать встречу';

  // Fill schedule dropdown
  var sel = document.getElementById('qa-schedule-sel');
  sel.innerHTML = '<option value="">Выберите расписание…</option>';
  _qaSchedules = state.schedules || [];
  _qaSchedules.forEach(function(s) {
    var opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = escHtml(s.title);
    sel.appendChild(opt);
  });

  setQaMode('personal');
  showSheet('sheet-quick-add');
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function setQaMode(mode) {
  _qaMode = mode;
  _qaSelectedSlot = null;
  document.getElementById('qa-mode-personal').classList.toggle('on', mode === 'personal');
  document.getElementById('qa-mode-schedule').classList.toggle('on', mode === 'schedule');
  document.getElementById('qa-personal-fields').style.display = mode === 'personal' ? '' : 'none';
  document.getElementById('qa-schedule-fields').style.display = mode === 'schedule' ? '' : 'none';
  document.getElementById('qa-submit-btn').textContent = mode === 'personal' ? 'Создать встречу' : 'Записать';
  document.getElementById('qa-error').style.display = 'none';
}

function toggleQaExtra() {
  var el = document.getElementById('qa-extra-fields');
  var lbl = document.getElementById('qa-extra-lbl');
  var visible = el.style.display !== 'none';
  el.style.display = visible ? 'none' : '';
  lbl.textContent = visible ? 'Участник и заметки' : 'Скрыть';
}

async function onQaScheduleChange() {
  var schedId = document.getElementById('qa-schedule-sel').value;
  var date = document.getElementById('qa-sched-date').value;
  var slotsWrap = document.getElementById('qa-slots-wrap');
  var slotsEl = document.getElementById('qa-slots');
  if (!schedId || !date) { slotsWrap.style.display = 'none'; return; }
  slotsEl.innerHTML = '<div style="color:var(--t2);font-size:13px;padding:6px 0">Загрузка…</div>';
  slotsWrap.style.display = '';
  var res = await apiFetch('GET', '/api/available-slots/' + schedId + '?date=' + date);
  if (res.error || !res.data) {
    slotsEl.innerHTML = '<div style="color:var(--t2);font-size:13px;padding:6px 0">Нет доступных слотов</div>';
    return;
  }
  var slots = res.data.slots || res.data || [];
  if (!slots.length) {
    slotsEl.innerHTML = '<div style="color:var(--t2);font-size:13px;padding:6px 0">Нет доступных слотов</div>';
    return;
  }
  slotsEl.innerHTML = slots.map(function(t) {
    return '<div class="slot s-free" onclick="pickQaSlot(\'' + escHtml(t) + '\')">' + escHtml(t) + '</div>';
  }).join('');
}

function pickQaSlot(time) {
  _qaSelectedSlot = time;
  document.querySelectorAll('#qa-slots .slot').forEach(function(el) {
    if (el.textContent.trim() === time) {
      el.classList.add('s-sel');
      el.classList.remove('s-free');
    } else {
      el.classList.remove('s-sel');
      el.classList.add('s-free');
    }
  });
}

async function submitQuickAdd() {
  var btn = document.getElementById('qa-submit-btn');
  document.getElementById('qa-error').style.display = 'none';

  if (_qaMode === 'personal') {
    var title = document.getElementById('qa-title').value.trim();
    var date = document.getElementById('qa-date').value;
    var time = document.getElementById('qa-time').value;
    if (!title) { showQaError('Введите название встречи'); return; }
    if (!date) { showQaError('Выберите дату'); return; }
    if (!time) { showQaError('Выберите время'); return; }
    var scheduledTime = date + 'T' + time + ':00';
    var body = {
      is_manual: true,
      title: title,
      scheduled_time: scheduledTime,
      guest_name: document.getElementById('qa-guest-name').value.trim() || undefined,
      guest_contact: document.getElementById('qa-guest-contact').value.trim() || undefined,
      notes: document.getElementById('qa-notes').value.trim() || undefined
    };
    btn.disabled = true; btn.textContent = '…';
    var res = await apiFetch('POST', '/api/meetings/quick', body);
    btn.disabled = false; btn.textContent = 'Создать встречу';
    if (res.error) { showQaError(res.error.detail || 'Ошибка при создании встречи'); return; }
    closeSheet('sheet-quick-add');
    showToast('Встреча создана', 'success');
    if (state.currentScreen === 's-home') loadHome();
    else if (state.currentScreen === 's-meetings') loadMeetings();
  } else {
    var schedId = document.getElementById('qa-schedule-sel').value;
    if (!schedId) { showQaError('Выберите расписание'); return; }
    if (!_qaSelectedSlot) { showQaError('Выберите слот'); return; }
    var schedDate = document.getElementById('qa-sched-date').value;
    var scheduledTime2 = schedDate + 'T' + _qaSelectedSlot + ':00';
    var body2 = {
      schedule_id: schedId,
      scheduled_time: scheduledTime2,
      guest_name: document.getElementById('qa-guest-name').value.trim() || 'Гость',
      guest_contact: document.getElementById('qa-guest-contact').value.trim() || undefined,
      notes: document.getElementById('qa-notes').value.trim() || undefined
    };
    btn.disabled = true; btn.textContent = '…';
    var res2 = await apiFetch('POST', '/api/bookings', body2);
    btn.disabled = false; btn.textContent = 'Записать';
    if (res2.error) { showQaError(res2.error.detail || 'Ошибка при бронировании'); return; }
    closeSheet('sheet-quick-add');
    showToast('Встреча забронирована', 'success');
    if (state.currentScreen === 's-home') loadHome();
    else if (state.currentScreen === 's-meetings') loadMeetings();
  }
}

function showQaError(msg) {
  var el = document.getElementById('qa-error');
  el.textContent = msg;
  el.style.display = '';
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
