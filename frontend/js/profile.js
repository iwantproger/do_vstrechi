/* ═══════════════════════════════════════════
   PROFILE (s-profile)
═══════════════════════════════════════════ */
function getNotifSettings() {
  try {
    var s = JSON.parse(localStorage.getItem('sb_settings') || '{}');
    /* Миграция: reminder (строка) → reminders (массив) */
    if (s.reminder !== undefined && !s.reminders) {
      s.reminders = (s.reminder === 'off') ? [] : [s.reminder];
      delete s.reminder;
    }
    /* Миграция: старый notif → booking_notif + reminder_notif */
    if (s.notif !== undefined && s.booking_notif === undefined) {
      s.booking_notif = s.notif;
      s.reminder_notif = s.notif;
      delete s.notif;
    }
    if (!s.reminders) s.reminders = ['60'];
    if (!s.customReminders) s.customReminders = [];
    if (s.booking_notif === undefined) s.booking_notif = true;
    if (s.reminder_notif === undefined) s.reminder_notif = true;
    try { localStorage.setItem('sb_settings', JSON.stringify(s)); } catch(e) {}
    return s;
  } catch(e) { return { booking_notif: true, reminder_notif: true, reminders: ['60'], customReminders: [] }; }
}

function formatReminderMinutes(mins) {
  mins = parseInt(mins);
  if (isNaN(mins) || mins <= 0) return '0 мин';
  if (mins < 60) return mins + ' мин';
  if (mins === 60) return '1 ч';
  if (mins < 1440) {
    var h = Math.floor(mins / 60), m = mins % 60;
    return h + ' ч' + (m ? ' ' + m + ' м' : '');
  }
  if (mins === 1440) return '1 дн';
  var d = Math.floor(mins / 1440), rest = mins % 1440;
  return d + ' дн' + (rest ? ' ' + formatReminderMinutes(rest) : '');
}

function detectTimezone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
  catch(e) { return 'Europe/Moscow'; }
}

async function loadProfile() {
  var u = state.user || tg?.initDataUnsafe?.user;
  if (!u) return;

  var av = document.getElementById('profile-avatar');
  var nm = document.getElementById('profile-name');
  var sub = document.getElementById('profile-sub');
  var ini = ((u.first_name || '')[0] || '') + ((u.last_name || '')[0] || '');
  if (av) av.textContent = ini || '?';
  if (nm) nm.textContent = (u.first_name || '') + (u.last_name ? ' ' + u.last_name : '');
  if (sub) sub.textContent = u.username ? '@' + u.username : 'ID: ' + (u.telegram_id || u.id);

  /* profile link — ссылка на дефолтное/первое расписание через Direct Link */
  var linkSubEl = document.getElementById('profile-link-sub');
  if (linkSubEl) linkSubEl.textContent = '...';
  state._profileLink = null;
  state._profileTgUrl = null;

  if (!state.schedules || !state.schedules.length) {
    var { data: schData } = await apiFetch('GET', '/api/schedules');
    if (schData) state.schedules = schData;
  }
  var defaultSched = (state.schedules || []).find(function(s) { return s.is_default; })
                  || (state.schedules || [])[0];
  if (defaultSched) {
    state._profileLink = getScheduleUrl(defaultSched.id);
    state._profileTgUrl = getScheduleTelegramUrl(defaultSched.id);
    state._profileSchedTitle = defaultSched.title;
    if (linkSubEl) linkSubEl.textContent = state._profileLink.replace(/^https?:\/\//, '');
  } else {
    state._profileLink = 'https://t.me/do_vstrechi_bot';
    state._profileTgUrl = 'https://t.me/do_vstrechi_bot';
    state._profileSchedTitle = null;
    if (linkSubEl) linkSubEl.textContent = 'Создайте расписание для получения ссылки';
  }

  /* timezone */
  var tz = detectTimezone();
  var tzEl = document.getElementById('profile-tz-val');
  if (tzEl) tzEl.textContent = tz;

  /* version */
  var verEl = document.getElementById('app-version-val');
  if (verEl) verEl.textContent = APP_VERSION;

  /* notification settings: two toggles + reminder chips */
  var s = getNotifSettings();
  var togBook = document.getElementById('tog-booking-notif');
  if (togBook) { if (s.booking_notif) togBook.classList.add('on'); else togBook.classList.remove('on'); }
  var togRem = document.getElementById('tog-reminder-notif');
  if (togRem) { if (s.reminder_notif) togRem.classList.add('on'); else togRem.classList.remove('on'); }

  renderReminderChips();
  var chipsEl = document.getElementById('reminder-chips');
  if (chipsEl) {
    chipsEl.style.opacity = s.reminder_notif ? '' : '0.4';
    chipsEl.style.pointerEvents = s.reminder_notif ? '' : 'none';
  }
}

function renderReminderChips() {
  var chipsEl = document.getElementById('reminder-chips');
  if (!chipsEl) return;
  /* сохранить состояние режима редактирования при перерисовке */
  var wasEditing = chipsEl.classList.contains('chips-editing');
  var s = getNotifSettings();
  var selected = s.reminders || [];
  var defaultOpts = [
    { val: '1440', label: '24 ч' },
    { val: '60',   label: '1 ч' },
    { val: '30',   label: '30 мин' },
    { val: '15',   label: '15 мин' },
    { val: '5',    label: '5 мин' },
  ];
  var customOpts = (s.customReminders || []).map(function(v) {
    return { val: String(v), label: formatReminderMinutes(v), custom: true };
  });
  var allOpts = defaultOpts.concat(customOpts);
  var html = allOpts.map(function(opt) {
    var isOn = selected.indexOf(opt.val) >= 0;
    return '<div class="chip reminder-chip' + (isOn ? ' on' : '') + (opt.custom ? ' removable' : '') + '"'
      + ' data-val="' + opt.val + '"'
      + (opt.custom ? ' data-custom="true"' : '')
      + ' onclick="toggleReminderChip(\'' + opt.val + '\',this)">'
      + escHtml(opt.label)
      /* FIX: Bug #3/6b — rc-x и класс .removable только у кастомных чипов */
      + (opt.custom ? '<span class="rc-x" onclick="event.stopPropagation();removeCustomReminder(\'' + opt.val + '\')">×</span>' : '')
      + '</div>';
  }).join('');
  html += '<div class="chip reminder-chip rc-add" onclick="openAddCustomReminder()">'
    + '<svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>'
    + ' Своё</div>';
  chipsEl.innerHTML = html;
  if (wasEditing) chipsEl.classList.add('chips-editing');
  /* FIX: Bug #3 — вешаем long-press только один раз */
  if (!chipsEl._longPressAttached) {
    attachReminderChipLongPress(chipsEl);
    chipsEl._longPressAttached = true;
  }
}

/* FIX: long-press 500ms для активации режима редактирования чипов */
var _chipEditJustActivated = false; /* флаг: пропустить первый click после активации */
function attachReminderChipLongPress(container) {
  var timer = null;
  function startPress(e) {
    var chip = e.target.closest && e.target.closest('.reminder-chip:not(.rc-add)');
    if (!chip) return;
    timer = setTimeout(function() {
      timer = null;
      _chipEditJustActivated = true;
      container.classList.add('chips-editing');
      if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
      /* сбросить флаг через 400ms — если click не пришёл, значит preventDefault сработал */
      setTimeout(function() { _chipEditJustActivated = false; }, 400);
    }, 500);
  }
  function cancelPress() {
    if (timer) { clearTimeout(timer); timer = null; }
  }
  container.addEventListener('touchstart', startPress, { passive: true });
  container.addEventListener('touchend', cancelPress);
  container.addEventListener('touchcancel', cancelPress);
  container.addEventListener('touchmove', cancelPress, { passive: true });
  /* mouse fallback для dev-режима */
  container.addEventListener('mousedown', startPress);
  container.addEventListener('mouseup', cancelPress);
  container.addEventListener('mouseleave', cancelPress);
}

/* Выход из режима редактирования при клике вне блока */
document.addEventListener('click', function(e) {
  var container = document.getElementById('reminder-chips');
  if (container && !container.contains(e.target)) {
    container.classList.remove('chips-editing');
  }
});

/* FIX: Bug #4 — подсказка по удалению чипов */
function showChipHint() {
  showToast('Удерживайте чип 0.5с, чтобы удалить');
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function showTimezoneInfo() {
  var tz = detectTimezone();
  var el = document.getElementById('tz-value');
  if (el) el.textContent = tz;
  showSheet('sheet-timezone');
}

var _changelogMode = 'simple';

function switchChangelogTab(mode) {
  _changelogMode = mode;
  var stab = document.getElementById('cl-tab-simple');
  var ttab = document.getElementById('cl-tab-tech');
  if (stab) stab.classList.toggle('on', mode === 'simple');
  if (ttab) ttab.classList.toggle('on', mode === 'technical');
  renderChangelog();
}

function renderChangelog() {
  var body = document.getElementById('changelog-body');
  if (!body) return;
  body.innerHTML = CHANGELOG.map(function(release, i) {
    var changes = _changelogMode === 'technical'
      ? (release.technical || release.changes || [])
      : (release.simple || release.changes || []);
    return (i > 0 ? '<div style="height:1px;background:var(--b1);margin:4px 0 16px"></div>' : '')
      + '<div style="margin-bottom:4px">'
        + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
          + '<span style="font-size:15px;font-weight:800;color:var(--t1)">v' + release.version + '</span>'
          + '<span style="font-size:11px;color:var(--t3);font-weight:500">' + release.date + '</span>'
        + '</div>'
        + '<div style="display:flex;flex-direction:column;gap:6px">'
          + changes.map(function(c) {
              return '<div style="font-size:13px;color:var(--t2);line-height:1.5">' + escHtml(c) + '</div>';
            }).join('')
        + '</div>'
      + '</div>';
  }).join('');
}

function showChangelog() {
  /* reset to simple tab each open */
  _changelogMode = 'simple';
  var stab = document.getElementById('cl-tab-simple');
  var ttab = document.getElementById('cl-tab-tech');
  if (stab) stab.classList.add('on');
  if (ttab) ttab.classList.remove('on');
  renderChangelog();
  showSheet('sheet-changelog');
}

function toggleBookingNotif(el) {
  el.classList.toggle('on');
  var s = getNotifSettings();
  s.booking_notif = el.classList.contains('on');
  try { localStorage.setItem('sb_settings', JSON.stringify(s)); } catch(e) {}
  showToast(s.booking_notif ? 'Уведомления о записях включены' : 'Уведомления о записях отключены');
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function toggleReminderNotif(el) {
  el.classList.toggle('on');
  var s = getNotifSettings();
  s.reminder_notif = el.classList.contains('on');
  try { localStorage.setItem('sb_settings', JSON.stringify(s)); } catch(e) {}
  showToast(s.reminder_notif ? 'Напоминания включены' : 'Напоминания отключены');
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
  var chipsEl = document.getElementById('reminder-chips');
  if (chipsEl) {
    chipsEl.style.opacity = s.reminder_notif ? '' : '0.4';
    chipsEl.style.pointerEvents = s.reminder_notif ? '' : 'none';
  }
}

function toggleReminderChip(val, el) {
  /* FIX: пропустить click, который пришёл сразу после активации editing (long-press) */
  if (_chipEditJustActivated) {
    _chipEditJustActivated = false;
    return;
  }
  /* В режиме редактирования клик по чипу выходит из режима */
  var container = document.getElementById('reminder-chips');
  if (container && container.classList.contains('chips-editing')) {
    container.classList.remove('chips-editing');
    return;
  }
  el.classList.toggle('on');
  var selected = [];
  document.querySelectorAll('.reminder-chip.on:not(.rc-add)').forEach(function(c) {
    var v = c.getAttribute('data-val');
    if (v) selected.push(v);
  });
  var s = getNotifSettings();
  s.reminders = selected;
  try { localStorage.setItem('sb_settings', JSON.stringify(s)); } catch(e) {}
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
  if (selected.length === 0) {
    showToast('Напоминания отключены');
  } else {
    var labels = selected.map(function(v) { return formatReminderMinutes(parseInt(v)); });
    showToast('Напоминание: ' + labels.join(', '));
  }
}

function openAddCustomReminder() {
  var inp = document.getElementById('custom-reminder-inp');
  if (inp) inp.value = 45;
  showSheet('sheet-custom-reminder');
}

function submitCustomReminder() {
  var val = parseInt(document.getElementById('custom-reminder-inp').value);
  closeSheet('sheet-custom-reminder');
  if (val && val > 0) addCustomReminder(val);
}

function addCustomReminder(minutes) {
  minutes = parseInt(minutes);
  if (!minutes || minutes < 1) { showToast('Введите число от 1'); return; }
  if (minutes > 10080) { showToast('Максимум 7 дней (10080 мин)'); return; }
  var standard = [1440, 60, 30, 15, 5];
  if (standard.indexOf(minutes) >= 0) {
    showToast('Это стандартное значение — выберите из списка');
    return;
  }
  var s = getNotifSettings();
  if (s.customReminders.indexOf(minutes) >= 0) {
    showToast('Такое напоминание уже есть');
    return;
  }
  s.customReminders.push(minutes);
  s.customReminders.sort(function(a, b) { return b - a; });
  var valStr = String(minutes);
  if (s.reminders.indexOf(valStr) < 0) s.reminders.push(valStr);
  try { localStorage.setItem('sb_settings', JSON.stringify(s)); } catch(e) {}
  renderReminderChips();
  showToast('Напоминание за ' + formatReminderMinutes(minutes) + ' добавлено');
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
}

function removeCustomReminder(val) {
  val = String(val);
  var s = getNotifSettings();
  s.customReminders = s.customReminders.filter(function(v) { return String(v) !== val; });
  s.reminders = s.reminders.filter(function(v) { return v !== val; });
  try { localStorage.setItem('sb_settings', JSON.stringify(s)); } catch(e) {}
  renderReminderChips();
  showToast('Напоминание удалено');
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
}

function copyProfileLink() {
  var url = state._profileLink;
  if (!url) return;
  navigator.clipboard?.writeText(url).catch(function() {});
  showToast('Ссылка скопирована ✓', 'success');
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
}

function shareProfileLink() {
  var url = state._profileLink;
  if (!url) return;
  if (tg?.openTelegramLink) {
    tg.openTelegramLink('https://t.me/share/url?url=' + encodeURIComponent(url));
  } else {
    navigator.clipboard?.writeText(url).catch(function() {});
    showToast('Ссылка скопирована ✓', 'success');
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
}

/* FIX: профиль — шаринг через Direct Link (t.me/app?startapp=UUID), не /u/slug */
async function shareMyLink() {
  /* Если ссылка ещё не загружена — ждём загрузки профиля */
  if (!state._profileTgUrl) {
    await loadProfile();
  }
  var tgUrl = state._profileTgUrl || 'https://t.me/do_vstrechi_bot';
  var webUrl = state._profileLink || tgUrl;
  var title = state._profileSchedTitle || 'встречу';
  var text = '📅 Запишись ко мне — ' + title;

  if (navigator.share) {
    try {
      await navigator.share({ title: 'До встречи', text: text, url: tgUrl });
      if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    } catch(e) { /* пользователь отменил */ }
    return;
  }
  /* Fallback: Telegram share через openTelegramLink */
  if (tg?.openTelegramLink) {
    var shareUrl = 'https://t.me/share/url'
      + '?url=' + encodeURIComponent(tgUrl)
      + '&text=' + encodeURIComponent(text);
    tg.openTelegramLink(shareUrl);
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
  } else {
    try {
      await navigator.clipboard.writeText(tgUrl);
      showToast('Ссылка скопирована ✓', 'success');
    } catch(e) {
      showToast('Не удалось скопировать');
    }
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  }
}

/* ── Legal pages (privacy / terms) ──────── */
function showLegal(url, title) {
  var el = document.getElementById('legal-title');
  if (el) el.textContent = title;
  var frame = document.getElementById('legal-frame');
  if (frame) frame.src = url;
  showScreen('s-legal');
}

