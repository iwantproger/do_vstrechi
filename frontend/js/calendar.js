/* ═══════════════════════════════════════════
   GUEST BOOKING FLOW (calendar → form → success)
═══════════════════════════════════════════ */

async function loadCalendar(scheduleId) {
  /* show loading */
  var landing = document.getElementById('client-landing-content');
  var calContent = document.getElementById('client-cal-content');
  if (landing) landing.style.display = '';
  if (calContent) calContent.style.display = 'none';

  var { data, error } = await apiFetch('GET', '/api/schedules/' + scheduleId);
  if (error || !data) {
    if (landing) landing.innerHTML = '<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></div><div class="empty-title">Расписание не найдено</div><div class="empty-desc">Ссылка недействительна или расписание удалено</div></div>';
    return;
  }

  if (data.is_active === false) {
    if (landing) landing.innerHTML = '<div class="empty-state"><div class="empty-icon" style="font-size:48px">⏸</div><div class="empty-title">Расписание на паузе</div><div class="empty-desc">Организатор временно приостановил запись. Попробуйте позже или свяжитесь напрямую.</div></div>';
    return;
  }

  state.schedule = data;
  state.selectedDate = null;
  state.selectedTime = null; state.selectedSlotUtc = null; state.selectedTimeLocal = null;
  state.monthSlots = {};
  state.currentMonth = new Date();

  /* header title stays as "Выберите время" — schedule name shown in the card below */

  /* apply guest colour theme to calendar and success screens */
  var calScreen = document.getElementById('s-calendar');
  if (calScreen) calScreen.classList.add('guest-theme');
  var successScreen = document.getElementById('s-success');
  if (successScreen) successScreen.classList.add('guest-theme');

  /* schedule info card */
  var info = document.getElementById('cal-schedule-info');
  if (info) {
    var pills = '<span class="lc-pill">' + sliderLabel(data.duration) + '</span>';
    pills += '<span class="lc-pill">' + escHtml(PLAT_NAMES[data.platform] || data.platform) + '</span>';
    var desc = data.description ? '<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--b1);font-size:13px;color:var(--t2);line-height:1.6">' + escHtml(data.description) + '</div>' : '';
    info.innerHTML = '<div style="background:var(--s1);border-radius:var(--r3);border:1px solid var(--b1);padding:16px">'
      + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);margin-bottom:10px">Тип встречи</div>'
      + '<div style="font-size:18px;font-weight:800;color:var(--t1);letter-spacing:-.01em">' + escHtml(data.title) + '</div>'
      + '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">' + pills + '</div>'
      + desc + '</div>';
  }

  /* show calendar, hide loading */
  if (landing) landing.style.display = 'none';
  if (calContent) calContent.style.display = '';

  /* preview mode banner */
  var existingBanner = document.getElementById('preview-banner');
  if (existingBanner) existingBanner.remove();
  if (state._previewMode) {
    var b = document.createElement('div');
    b.id = 'preview-banner';
    b.style.cssText = 'padding:8px 16px;background:rgba(124,92,252,.15);border-bottom:1px solid rgba(124,92,252,.2);display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:#7C5CFC;margin-bottom:4px';
    b.innerHTML = '<svg viewBox="0 0 24 24" style="width:16px;height:16px;flex-shrink:0;stroke:currentColor;fill:none;stroke-width:2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> Режим предпросмотра';
    var calContent2 = document.getElementById('client-cal-content');
    if (calContent2) calContent2.insertBefore(b, calContent2.firstChild);
  }

  renderCalendar();
  loadMonthSlots();
}

function renderCalendar() {
  var now = new Date();
  var y = state.currentMonth.getFullYear();
  var m = state.currentMonth.getMonth();
  var sched = state.schedule;
  var workDays = sched ? (sched.work_days || []) : [];

  /* month label */
  var lbl = document.getElementById('cal-month-label');
  if (lbl) lbl.textContent = MONTHS[m] + ' ' + y;

  var grid = document.getElementById('cal-grid');
  if (!grid) return;

  var html = '';
  /* day headers: Пн..Вс */
  DAYS.forEach(function(d) { html += '<div class="cal-dh">' + d + '</div>'; });

  /* first day of month — weekday (0=Mon in our system) */
  var firstDay = new Date(y, m, 1);
  var startDow = (firstDay.getDay() + 6) % 7; /* convert Sun=0 to Mon=0 */
  var daysInMonth = new Date(y, m + 1, 0).getDate();

  /* empty cells before first day */
  for (var i = 0; i < startDow; i++) html += '<div class="cal-empty"></div>';

  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  for (var d = 1; d <= daysInMonth; d++) {
    var dt = new Date(y, m, d);
    var dow = (dt.getDay() + 6) % 7;
    var ds = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
    var isPast = dt < today;
    var isToday = dt.getTime() === today.getTime();
    var isWorkDay = workDays.indexOf(dow) >= 0;
    var isSelected = state.selectedDate === ds;

    var cls = 'cal-cell';
    if (isToday) cls += ' c-today';
    if (isSelected) cls += ' c-sel';

    if (isPast || !isWorkDay) {
      cls += ' c-past';
      html += '<div class="' + cls + '"><div class="cn">' + d + '</div></div>';
    } else {
      /* check slot availability from monthSlots cache */
      var daySlots = state.monthSlots[ds];
      if (daySlots === undefined) {
        /* not loaded yet — show as potentially available */
        cls += ' c-free';
      } else if (daySlots.length === 0) {
        cls += ' c-past';
        html += '<div class="' + cls + '"><div class="cn">' + d + '</div></div>';
        continue;
      } else {
        /* estimate total possible slots — 3 availability tiers */
        var totalPossible = estimateTotalSlots(sched);
        var pct = daySlots.length / totalPossible;
        if (daySlots.length <= 2) cls += ' c-almost';
        else if (pct <= 0.5) cls += ' c-part';
        else cls += ' c-free';
      }
      html += '<div class="' + cls + '" onclick="selectDay(\'' + ds + '\')">'
        + '<div class="cn">' + d + '</div>'
        + '</div>';
    }
  }

  grid.innerHTML = html;
}

function estimateTotalSlots(sched) {
  if (!sched) return 1;
  var sh = parseInt((sched.start_time || '09:00').split(':')[0]);
  var sm = parseInt((sched.start_time || '09:00').split(':')[1]);
  var eh = parseInt((sched.end_time || '18:00').split(':')[0]);
  var em = parseInt((sched.end_time || '18:00').split(':')[1]);
  var totalMin = (eh * 60 + em) - (sh * 60 + sm);
  var step = (sched.duration || 60) + (sched.buffer_time || 0);
  return Math.max(1, Math.floor(totalMin / step));
}

async function loadMonthSlots() {
  var sched = state.schedule;
  if (!sched) return;
  var y = state.currentMonth.getFullYear();
  var m = state.currentMonth.getMonth();
  var daysInMonth = new Date(y, m + 1, 0).getDate();
  var workDays = sched.work_days || [];
  var today = new Date();
  today = new Date(today.getFullYear(), today.getMonth(), today.getDate());

  /* collect dates to fetch (work days, not past, max 8 at a time) */
  var datesToFetch = [];
  for (var d = 1; d <= daysInMonth; d++) {
    var dt = new Date(y, m, d);
    var dow = (dt.getDay() + 6) % 7;
    if (dt < today || workDays.indexOf(dow) < 0) continue;
    var ds = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
    if (state.monthSlots[ds] !== undefined) continue;
    datesToFetch.push(ds);
  }

  /* batch fetch (8 at a time) */
  for (var i = 0; i < datesToFetch.length; i += 8) {
    var batch = datesToFetch.slice(i, i + 8);
    try {
      var promises = batch.map(function(ds) {
        return apiFetch('GET', '/api/available-slots/' + sched.id + '?date=' + ds + '&viewer_tz=' + encodeURIComponent(userTimezone))
          .then(function(res) { return { date: ds, slots: (res.data && res.data.available_slots) || [] }; });
      });
      var results = await Promise.all(promises);
      results.forEach(function(r) { state.monthSlots[r.date] = r.slots; });
      renderCalendar();
    } catch (e) { /* network batch failed, skip */ }
  }
}

function selectDay(ds) {
  state.selectedDate = ds;
  state.selectedTime = null; state.selectedSlotUtc = null; state.selectedTimeLocal = null;
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');

  /* hide inline form when new day selected */
  var formBlock = document.getElementById('cal-guest-form');
  if (formBlock) formBlock.style.display = 'none';

  renderCalendar();

  var daySlots = state.monthSlots[ds] || [];
  var panel = document.getElementById('cal-slot-panel');
  var titleEl = document.getElementById('csp-title');
  var gridEl = document.getElementById('csp-grid');

  if (!panel || !gridEl) return;

  /* parse date for title */
  var parts = ds.split('-');
  var dd = parseInt(parts[2]);
  var mm = parseInt(parts[1]) - 1;
  var dt = new Date(parseInt(parts[0]), mm, dd);
  var dow = (dt.getDay() + 6) % 7;
  if (titleEl) titleEl.textContent = DAYS_FULL[dow] + ', ' + dd + ' ' + MONTHS_GEN[mm];

  if (daySlots.length === 0) {
    gridEl.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--t3);font-size:13px">Нет свободного времени</div>';
    panel.style.display = '';
    hideMainButton();
    return;
  }

  var html = '';
  daySlots.forEach(function(slot) {
    var t = slot.time;
    var display = slot.datetime_local || t;
    var sel = state.selectedTime === t ? ' s-sel' : '';
    html += '<div class="slot s-free' + sel + '" onclick="selectTime(\'' + t + '\')">' + display + '</div>';
  });
  gridEl.innerHTML = html;
  panel.style.display = '';

  /* scroll to slot panel */
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function selectTime(time) {
  state.selectedTime = time;
  var daySlots = state.monthSlots[state.selectedDate] || [];
  var slot = daySlots.find(function(s) { return s.time === time; });
  state.selectedSlotUtc = slot ? (slot.datetime_utc || slot.datetime) : null;
  state.selectedTimeLocal = slot ? (slot.datetime_local || time) : time;
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  /* re-render slot grid to update selection */
  var gridEl = document.getElementById('csp-grid');
  if (gridEl) {
    var daySlots2 = state.monthSlots[state.selectedDate] || [];
    var html = '';
    daySlots2.forEach(function(s) {
      var t = s.time;
      var display = s.datetime_local || t;
      var sel = state.selectedTime === t ? ' s-sel' : '';
      html += '<div class="slot s-free' + sel + '" onclick="selectTime(\'' + t + '\')">' + display + '</div>';
    });
    gridEl.innerHTML = html;
  }

  /* show inline guest form */
  var formBlock = document.getElementById('cal-guest-form');
  if (formBlock) {
    formBlock.style.display = 'block';
    /* autofill from Telegram user */
    var u = tg?.initDataUnsafe?.user;
    if (u) {
      var nameInp = document.getElementById('cal-g-name');
      if (nameInp && !nameInp.value) nameInp.value = (u.first_name || '') + (u.last_name ? ' ' + u.last_name : '');
      var contactInp = document.getElementById('cal-g-contact');
      if (contactInp && !contactInp.value && u.username) contactInp.value = '@' + u.username;
    }
    setTimeout(function() {
      formBlock.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 150);
  }
}

function changeMonth(dir) {
  var m = state.currentMonth.getMonth() + dir;
  var y = state.currentMonth.getFullYear();
  state.currentMonth = new Date(y, m, 1);
  state.selectedDate = null;
  state.selectedTime = null; state.selectedSlotUtc = null; state.selectedTimeLocal = null;

  /* hide slot panel and inline form */
  var panel = document.getElementById('cal-slot-panel');
  if (panel) panel.style.display = 'none';
  var formBlock = document.getElementById('cal-guest-form');
  if (formBlock) formBlock.style.display = 'none';

  renderCalendar();
  loadMonthSlots();
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function hideMainButton() { /* MainButton отключён — используем собственные кнопки */ }

/* ── Form setup ── */
function setupForm() {
  if (!state.selectedDate || !state.selectedTime) return;

  var sched = state.schedule;
  var parts = state.selectedDate.split('-');
  var dd = parseInt(parts[2]);
  var mm = parseInt(parts[1]) - 1;
  var dt = new Date(parseInt(parts[0]), mm, dd);
  var dow = (dt.getDay() + 6) % 7;

  /* compute end time */
  var displayTime = state.selectedTimeLocal || state.selectedTime;
  var timeParts = displayTime.split(':');
  var startMin = parseInt(timeParts[0]) * 60 + parseInt(timeParts[1]);
  var endMin = startMin + (sched ? sched.duration : 60);
  var endH = String(Math.floor(endMin / 60)).padStart(2, '0');
  var endM = String(endMin % 60).padStart(2, '0');

  var dtEl = document.getElementById('confirm-datetime');
  if (dtEl) dtEl.textContent = dd + ' ' + MONTHS_GEN[mm] + ' · ' + displayTime + ' – ' + endH + ':' + endM;

  var infoEl = document.getElementById('confirm-info');
  if (infoEl) {
    var infoParts = [];
    if (sched) {
      infoParts.push(escHtml(sched.title));
      infoParts.push(sliderLabel(sched.duration));
      infoParts.push(escHtml(PLAT_NAMES[sched.platform] || sched.platform));
    }
    infoEl.textContent = infoParts.join(' · ');
  }

  /* pre-fill from Telegram user */
  var u = tg?.initDataUnsafe?.user;
  var nameInp = document.getElementById('guest-name');
  var contactInp = document.getElementById('guest-contact');
  if (nameInp && !nameInp.value && u) nameInp.value = (u.first_name || '') + (u.last_name ? ' ' + u.last_name : '');
  if (contactInp && !contactInp.value && u && u.username) contactInp.value = '@' + u.username;

  /* hide error */
  var errEl = document.getElementById('err-guest-name');
  if (errEl) errEl.style.display = 'none';

  /* reset book button */
  var btn = document.getElementById('btn-book');
  if (btn) { btn.className = 'btn btn-primary'; btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>Забронировать'; }

  showScreen('s-form');
}

/* ── Submit booking ── */
var _submitBookingBound = function() { submitBooking(); };

async function submitBooking() {
  var nameInp = document.getElementById('guest-name');
  var contactInp = document.getElementById('guest-contact');
  var notesInp = document.getElementById('guest-notes');
  var errEl = document.getElementById('err-guest-name');
  var nameVal = (nameInp ? nameInp.value : '').trim();

  /* validate */
  if (nameVal.length < 2) {
    if (errEl) errEl.style.display = '';
    if (nameInp) nameInp.focus();
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    return;
  }
  if (errEl) errEl.style.display = 'none';

  /* build scheduled_time — prefer UTC from slot data */
  var scheduled_time = state.selectedSlotUtc || (state.selectedDate + 'T' + state.selectedTime + ':00');

  var u = tg?.initDataUnsafe?.user;
  var body = {
    schedule_id: state.scheduleId,
    guest_name: nameVal,
    guest_contact: (contactInp ? contactInp.value : '').trim() || nameVal,
    guest_telegram_id: u ? u.id : null,
    scheduled_time: scheduled_time,
    notes: (notesInp ? notesInp.value : '').trim() || null,
  };

  /* loading state */
  var btn = document.getElementById('btn-book');
  if (btn) { btn.className = 'btn btn-disabled'; btn.disabled = true; btn.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;gap:8px"><div class="spinner" style="width:18px;height:18px;border-width:2px"></div>Бронирование…</div>'; }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  var { data, error } = await apiFetch('POST', '/api/bookings', body);

  /* restore button */
  if (btn) { btn.className = 'btn btn-primary'; btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>Забронировать'; }

  if (error) {
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast(error === 'Это время уже занято' ? 'Это время уже занято, выберите другое' : 'Ошибка: ' + error);
    return;
  }

  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  renderSuccess(data);
  showScreen('s-success');
}

/* ── Success screen ── */
function renderSuccess(booking) {
  var sched = state.schedule;
  var parts = state.selectedDate.split('-');
  var dd = parseInt(parts[2]);
  var mm = parseInt(parts[1]) - 1;
  var dt = new Date(parseInt(parts[0]), mm, dd);
  var dow = (dt.getDay() + 6) % 7;

  var displayTime2 = state.selectedTimeLocal || state.selectedTime;
  var timeParts = displayTime2.split(':');
  var startMin = parseInt(timeParts[0]) * 60 + parseInt(timeParts[1]);
  var endMin = startMin + (sched ? sched.duration : 60);
  var endH = String(Math.floor(endMin / 60)).padStart(2, '0');
  var endM = String(endMin % 60).padStart(2, '0');

  var subEl = document.getElementById('book-success-sub');
  if (subEl) subEl.textContent = dd + ' ' + MONTHS_GEN[mm] + ' · ' + displayTime2 + ' – ' + endH + ':' + endM;

  /* detail card */
  var detEl = document.getElementById('book-success-details');
  if (detEl && sched) {
    detEl.innerHTML = '<div style="background:var(--s1);border-radius:var(--r3);border:1px solid var(--b1);padding:16px;margin-bottom:16px">'
      + '<div style="font-size:15px;font-weight:700;color:var(--t1);margin-bottom:8px">' + escHtml(sched.title) + '</div>'
      + '<div style="font-size:13px;color:var(--t2);line-height:1.6">'
      + DAYS_FULL[dow] + ', ' + dd + ' ' + MONTHS_GEN[mm] + '<br>'
      + displayTime2 + ' – ' + endH + ':' + endM + ' · ' + sliderLabel(sched.duration) + '<br>'
      + escHtml(PLAT_NAMES[sched.platform] || sched.platform)
      + '</div></div>';
  }

  /* meeting link button */
  var linkBtn = document.getElementById('btn-open-link');
  if (linkBtn && booking && booking.meeting_link) {
    state._meetingLink = booking.meeting_link;
    linkBtn.style.display = '';
  }
}

function openMeetingLink() {
  var link = state._meetingLink;
  if (!link) return;
  if (tg?.openLink) tg.openLink(link);
  else window.open(link, '_blank');
}

/* ── Inline booking (progressive disclosure) ── */
async function submitInlineBooking() {
  if (state._previewMode) { showToast('Это режим предпросмотра'); return; }

  var name = ((document.getElementById('cal-g-name') || {}).value || '').trim();
  var contact = ((document.getElementById('cal-g-contact') || {}).value || '').trim();
  var notes = ((document.getElementById('cal-g-notes') || {}).value || '').trim();

  if (!name || name.length < 2) { showToast('Введите имя (мин. 2 символа)'); return; }
  if (!state.selectedSlotUtc && !state.selectedTime) { showToast('Выберите слот'); return; }

  var scheduled_time = state.selectedSlotUtc || (state.selectedDate + 'T' + state.selectedTime + ':00');
  var u = tg?.initDataUnsafe?.user;
  var body = {
    schedule_id: state.scheduleId || (state.schedule && state.schedule.id),
    guest_name: name,
    guest_contact: contact || name,
    guest_telegram_id: u ? u.id : null,
    scheduled_time: scheduled_time,
    notes: notes || null,
  };

  var btn = document.getElementById('cal-book-btn');
  if (btn) { btn.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;gap:8px"><div class="spinner" style="width:18px;height:18px;border-width:2px"></div>Бронирование…</div>'; btn.disabled = true; }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  var { data, error } = await apiFetch('POST', '/api/bookings', body);

  if (btn) { btn.innerHTML = 'Забронировать'; btn.disabled = false; }

  if (error) {
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast(error === 'Это время уже занято' ? 'Это время уже занято, выберите другое' : 'Ошибка: ' + error);
    return;
  }

  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  renderSuccess(data);
  showScreen('s-success');
}
