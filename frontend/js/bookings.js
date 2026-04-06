function setHomeSubtitle(text, isError) {
  const sub = document.getElementById('home-subtitle');
  if (!sub) return;
  var color = isError ? 'var(--red)' : 'var(--t1)';
  sub.innerHTML = '<span style="font-weight:800;color:' + color + '">' + escHtml(text) + '</span>';
}

function setupProfile() {
  const u = tg?.initDataUnsafe?.user;
  if (!u) return;
  const greeting = document.getElementById('home-greeting');
  if (greeting) greeting.textContent = 'Привет, ' + u.first_name + ' ';
  const ini = (u.first_name?.[0] || '') + (u.last_name?.[0] || '');
  const ha = document.getElementById('home-avatar');
  if (ha) ha.textContent = ini || '?';
  const pa = document.getElementById('profile-avatar');
  if (pa) pa.textContent = ini || '?';
  const pn = document.getElementById('profile-name');
  if (pn) pn.textContent = (u.first_name || '') + (u.last_name ? ' ' + u.last_name : '');
  const ps = document.getElementById('profile-sub');
  if (ps) ps.textContent = u.username ? '@' + u.username : 'ID: ' + u.id;
}


/* ═══════════════════════════════════════════
   HOME SCREEN
═══════════════════════════════════════════ */
async function loadHome() {
  if (!state.user) return;

  /* auto-refresh every 60s to flip ongoing → completed */
  if (window._homeRefreshTimer) clearInterval(window._homeRefreshTimer);
  window._homeRefreshTimer = setInterval(function() {
    if (state.currentScreen === 's-home') loadHome();
  }, 60000);

  var { data, error } = await apiFetch('GET', '/api/bookings?role=organizer');
  if (error) { setHomeSubtitle('Не удалось загрузить данные', true); return; }
  if (data) state.bookings = data;

  const now = new Date();
  const todayStr = formatDate(now);
  const todayMeetings = (state.bookings || [])
    .filter(b => formatDate(new Date(b.scheduled_time)) === todayStr && b.status !== 'cancelled')
    .sort((a, b) => new Date(a.scheduled_time) - new Date(b.scheduled_time));

  /* subtitle */
  const sub = document.getElementById('home-subtitle');
  if (sub) {
    const n = todayMeetings.length;
    if (n === 0) {
      sub.innerHTML = '<span style="font-weight:800;color:var(--t1)">Нет встреч на сегодня</span>';
    } else {
      const w = n === 1 ? 'встреча' : (n >= 2 && n <= 4) ? 'встречи' : 'встреч';
      sub.innerHTML = '<span style="font-weight:800;color:var(--t1)">У тебя </span>'
        + '<span style="font-weight:800;color:var(--a)">' + n + ' ' + w + '</span>'
        + '<span style="font-weight:800;color:var(--t1)"> на сегодня</span>';
    }
  }

  /* hero card — nearest meeting that hasn't ended yet */
  const nearest = todayMeetings.find(b => {
    const end = new Date(b.scheduled_time);
    end.setMinutes(end.getMinutes() + (b.schedule_duration || 60));
    return end > now;
  });
  state.nextBooking = nearest || null;
  const heroEl = document.getElementById('home-hero');
  if (heroEl) heroEl.innerHTML = nearest ? renderHeroCard(nearest, now) : '';

  /* meetings list */
  const label = document.getElementById('home-section-label');
  const listEl = document.getElementById('home-meetings');
  if (todayMeetings.length) {
    if (label) label.classList.remove('hidden');
    if (listEl) listEl.innerHTML = todayMeetings.map(m => renderMeetingCard(m)).join('');
  } else {
    if (label) label.classList.add('hidden');
    if (listEl) listEl.innerHTML = renderEmpty('Нет встреч', 'На сегодня ничего не запланировано');
  }
}

function renderHeroCard(m, now) {
  const dt = new Date(m.scheduled_time);
  const time = fmtTime(dt);
  const dur = m.schedule_duration || 60;
  const datePart = dt.getDate() + ' ' + MONTHS_GEN[dt.getMonth()].slice(0, 3);
  const plat = PLAT_NAMES[m.schedule_platform] || m.schedule_platform || '';
  const meta = datePart + ' · ' + dur + ' мин' + (plat ? ' · ' + plat : '');
  const name = escHtml(m.guest_name);
  const title = escHtml(m.schedule_title || '');
  const withinHour = (dt - now) > 0 && (dt - now) < 3600000;
  const heroStatus = getMeetingStatus(m);

  if (heroStatus === 'confirmed' || heroStatus === 'ongoing') {
    const heroLabel = heroStatus === 'ongoing' ? 'ВСТРЕЧА ИДЁТ' : 'БЛИЖАЙШАЯ ВСТРЕЧА';
    const heroBorder = heroStatus === 'ongoing' ? 'rgba(45,212,160,.4)' : 'rgba(0,229,168,.18)';
    return '<div onclick="if(!event.target.closest(\'button\')){openMeetDetail(\'' + m.id + '\')}" style="margin:32px 16px 0;background:#182020;border-radius:20px;padding:18px;border:1px solid ' + heroBorder + ';cursor:pointer">'
      + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--a);margin-bottom:8px">' + heroLabel + '</div>'
      + '<div style="font-size:18px;font-weight:800;color:#fff">' + name + '</div>'
      + '<div style="font-size:13px;font-weight:500;color:#fff;margin-top:2px">' + title + '</div>'
      + '<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-top:12px;gap:16px">'
        + '<div>'
          + '<div style="font-size:30px;font-weight:800;color:#fff;line-height:1">' + time + '</div>'
          + '<div style="font-size:12px;font-weight:500;color:var(--t2);margin-top:2px">' + meta + '</div>'
        + '</div>'
        + (m.meeting_link
          ? '<button data-link="' + escHtml(m.meeting_link) + '" onclick="openLink(this.dataset.link)" style="height:40px;padding:0 16px;background:var(--a);border:none;border-radius:999px;font-family:var(--font);font-size:13px;font-weight:700;color:#000;cursor:pointer;white-space:nowrap;flex-shrink:0">Подключиться</button>'
          : '')
      + '</div>'
    + '</div>';
  }

  /* pending — amber card, label depends on urgency */
  const heroLabel = withinHour ? 'До встречи меньше часа' : 'Ожидает подтверждения';
  return '<div onclick="if(!event.target.closest(\'button\')){openMeetDetail(\'' + m.id + '\')}" style="margin:32px 16px 0;background:#1E1200;border-radius:20px;padding:18px;border:1px solid rgba(245,166,35,.3);cursor:pointer">'
    + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--amber);margin-bottom:8px">' + heroLabel + '</div>'
    + '<div style="font-size:18px;font-weight:800;color:#fff">' + name + '</div>'
    + '<div style="font-size:13px;font-weight:500;color:#fff;margin-top:2px">' + title + '</div>'
    + '<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-top:12px;gap:16px">'
      + '<div>'
        + '<div style="font-size:30px;font-weight:800;color:#fff;line-height:1">' + time + '</div>'
        + '<div style="font-size:12px;font-weight:500;color:var(--t2);margin-top:2px">' + meta + '</div>'
      + '</div>'
    + '</div>'
    + '<div style="display:flex;gap:8px;margin-top:14px">'
      + '<button class="btn btn-confirm" onclick="confirmMeeting(\'' + m.id + '\')" style="flex:1;height:40px;padding:0;font-size:13px">Подтвердить</button>'
      + '<button class="btn btn-danger" onclick="openCancelSheet(\'' + m.id + '\')" style="flex:1;height:40px;padding:0;font-size:13px">Отклонить</button>'
    + '</div>'
  + '</div>';
}

function renderMeetingCard(m) {
  const dt = new Date(m.scheduled_time);
  const dur = m.schedule_duration || 60;
  const timeStart = fmtTime(dt);
  const timeEnd = fmtTimeOffset(dt, dur);
  const name = escHtml(m.guest_name || (m.is_manual ? 'Личная встреча' : ''));
  const title = escHtml(m.is_manual ? (m.title || m.display_title || '') : (m.schedule_title || ''));
  const dStatus = m._ds || getMeetingStatus(m);
  const isPending = dStatus === 'pending' && !m.is_manual;

  return '<div onclick="openMeetDetail(\'' + m.id + '\')" style="margin:0 16px 8px;background:var(--s1);border-radius:14px;padding:14px 16px;cursor:pointer">'
    + '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px' + (isPending ? ';margin-bottom:24px' : '') + '">'
      + '<div style="flex:1;min-width:0">'
        + '<div style="font-size:14px;font-weight:700;color:var(--t1)">' + name + '</div>'
        + '<div style="font-size:12px;font-weight:400;color:var(--t1);margin-top:1px">' + timeStart + ' – ' + timeEnd + '</div>'
        + '<div style="font-size:12px;font-weight:400;color:var(--t2);margin-top:2px">' + title + '</div>'
      + '</div>'
      + meetingStatusHtml(dStatus)
    + '</div>'
    + (isPending
      ? '<div style="display:flex;gap:8px">'
        + '<button class="btn btn-confirm" onclick="event.stopPropagation();confirmMeeting(\'' + m.id + '\')" style="flex:1;height:40px;padding:0;font-size:13px">Подтвердить</button>'
        + '<button class="btn btn-danger" onclick="event.stopPropagation();openCancelSheet(\'' + m.id + '\')" style="flex:1;height:40px;padding:0;font-size:13px">Отклонить</button>'
      + '</div>'
      : '')
  + '</div>';
}

/* ═══════════════════════════════════════════
   MEETINGS SCREEN
═══════════════════════════════════════════ */
let _meetFilter = 'confirm';
let _meetGroup = 'date';

async function loadMeetings() {
  var { data, error } = await apiFetch('GET', '/api/bookings?role=organizer');
  if (error) { showToast('Ошибка загрузки встреч', 'error'); return; }
  if (data) state.bookings = data;

  /* FIX: умный дефолтный таб — confirm если есть pending, иначе all */
  var hasPending = (state.bookings || []).some(function(b) { return getMeetingStatus(b) === 'pending'; });
  _meetFilter = hasPending ? 'confirm' : 'all';
  document.querySelectorAll('[id^=mtab-]').forEach(function(t) { t.classList.remove('on'); });
  var defTabEl = document.getElementById(_meetFilter === 'confirm' ? 'mtab-confirm' : 'mtab-all');
  if (defTabEl) defTabEl.classList.add('on');

  renderMeetingsList();
}

function switchMeetStatus(filter, el) {
  _meetFilter = filter;
  document.querySelectorAll('[id^=mtab-]').forEach(t => t.classList.remove('on'));
  if (el) el.classList.add('on');
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
  renderMeetingsList();
}

function switchMeetGroup(mode) {
  _meetGroup = mode;
  const menu = document.getElementById('group-menu');
  if (menu) menu.style.display = 'none';
  document.querySelectorAll('.group-menu-item').forEach(function(item, i) {
    const active = (mode === 'date' && i === 0) || (mode === 'fmt' && i === 1);
    item.style.color = active ? 'var(--a)' : 'var(--t1)';
    item.style.background = active ? 'var(--as)' : '';
  });
  renderMeetingsList();
}

function toggleGroupMenu(btn) {
  const menu = document.getElementById('group-menu');
  if (!menu) return;
  if (menu.style.display === 'none') {
    const r = btn.getBoundingClientRect();
    menu.style.top = (r.bottom + 4) + 'px';
    /* FIX: align dropdown to right edge of button so it doesn't overflow screen */
    menu.style.left = 'auto';
    menu.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
    menu.style.display = 'block';
  } else {
    menu.style.display = 'none';
  }
}

document.addEventListener('click', function(e) {
  const menu = document.getElementById('group-menu');
  if (menu && menu.style.display !== 'none') {
    if (!menu.contains(e.target) && !e.target.closest('[data-group-toggle]')) {
      menu.style.display = 'none';
    }
  }
});

function renderMeetingsList() {
  const list = document.getElementById('meetings-list');
  if (!list) return;
  list.innerHTML = '';

  const now = new Date();

  /* compute display status */
  const meetings = (state.bookings || []).map(function(b) {
    const dt = new Date(b.scheduled_time);
    const ds = getMeetingStatus(b);
    return Object.assign({}, b, { _dt: dt, _ds: ds });
  });

  /* pending counter badge on confirm tab */
  const pendingCount = meetings.filter(function(m) { return m._ds === 'pending'; }).length;
  const confirmTab = document.getElementById('mtab-confirm');
  if (confirmTab) {
    confirmTab.innerHTML = 'Нужно подтвердить'
      + (pendingCount
        ? ' <span style="background:rgba(245,166,35,.18);color:var(--amber);padding:1px 7px;border-radius:99px;font-size:10px;font-weight:800;margin-left:2px;vertical-align:middle">' + pendingCount + '</span>'
        : '');
  }

  /* filter */
  var filtered = meetings.filter(function(m) {
    if (_meetFilter === 'confirm') return m._ds === 'pending';
    if (_meetFilter === 'all')     return m._ds === 'pending' || m._ds === 'confirmed' || m._ds === 'ongoing';
    if (_meetFilter === 'noans')   return m._ds === 'noans';
    if (_meetFilter === 'ok')      return m._ds === 'confirmed' || m._ds === 'ongoing';
    if (_meetFilter === 'archive') return m._ds === 'completed' || m._ds === 'cancelled';
    return true;
  });

  /* sort: upcoming asc, archive desc */
  var isArchive = _meetFilter === 'archive';
  filtered.sort(function(a, b) { return isArchive ? b._dt - a._dt : a._dt - b._dt; });

  if (!filtered.length) {
    list.innerHTML = renderEmpty('Нет встреч', 'В этой категории пока ничего нет');
    return;
  }

  /* group */
  var groups = {};
  var groupOrder = [];
  var LMAP = { date: 'По дате', fmt: 'По расписаниям' };

  filtered.forEach(function(m) {
    var key = _meetGroup === 'date'
      ? dateGroupLabel(m._dt, now)
      : (m.schedule_title || 'Без расписания');
    if (!groups[key]) { groups[key] = []; groupOrder.push(key); }
    groups[key].push(m);
  });

  var isFirst = true;
  groupOrder.forEach(function(g) {
    var toggleHtml = isFirst && _meetFilter !== 'confirm'
      ? '<button data-group-toggle onclick="toggleGroupMenu(this)" style="display:flex;align-items:center;gap:4px;background:none;border:none;font-family:var(--font);font-size:12px;font-weight:700;color:var(--t2);cursor:pointer;padding:0">'
        + LMAP[_meetGroup]
        + ' <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>'
        + '</button>'
      : '';

    list.insertAdjacentHTML('beforeend',
      '<div style="padding:14px 20px 8px;display:flex;align-items:center;justify-content:space-between">'
      + '<span style="font-size:12px;font-weight:700;color:var(--t2)">' + escHtml(g) + '</span>'
      + toggleHtml
      + '</div>');
    isFirst = false;

    groups[g].forEach(function(m) {
      list.insertAdjacentHTML('beforeend', renderMeetingCard(m));
    });
  });
}

/* ═══════════════════════════════════════════
   MEET DETAIL + NO-ANSWER
═══════════════════════════════════════════ */
function openMeetDetail(id) {
  const m = (state.bookings || []).find(function(b) { return b.id === id; });
  if (!m) return;

  var dStatus = getMeetingStatus(m);

  state.detailMeetingId = id;

  if (dStatus === 'noans') {
    var el = document.getElementById('meet-noans-content');
    if (el) el.innerHTML = renderMeetDetailHtml(m, dStatus);
    showScreen('s-meet-noans');
  } else {
    var el2 = document.getElementById('meet-detail-content');
    if (el2) el2.innerHTML = renderMeetDetailHtml(m, dStatus);
    showScreen('s-meet-detail');
  }
}

function renderMeetDetailHtml(m, dStatus) {
  var dt = new Date(m.scheduled_time);
  var dur = m.schedule_duration || 60;
  var now = new Date();
  var name = escHtml(m.guest_name || '');
  var initials = getInitials(m.guest_name);
  var contact = escHtml(m.guest_contact || '');
  var schedTitle = escHtml(m.is_manual ? (m.title || 'Личная встреча') : (m.schedule_title || ''));
  var platform = escHtml(m.is_manual ? 'Личная встреча' : (m.schedule_platform || 'Jitsi Meet'));
  var notes = m.notes ? escHtml(m.notes) : '';
  var link = m.meeting_link || '';
  var linkDisplay = link.replace(/^https?:\/\//, '');

  /* status → border & avatar accent colour */
  var borderColor, avatarColor;
  if (dStatus === 'confirmed' || dStatus === 'completed') {
    borderColor = 'rgba(45,212,160,.25)'; avatarColor = 'var(--a)';
  } else if (dStatus === 'pending') {
    borderColor = 'rgba(245,166,35,.3)'; avatarColor = 'var(--amber)';
  } else if (dStatus === 'noans') {
    borderColor = 'rgba(91,142,255,.25)'; avatarColor = '#7aaaff';
  } else if (dStatus === 'cancelled') {
    borderColor = 'rgba(240,100,73,.25)'; avatarColor = 'var(--red)';
  } else {
    borderColor = 'var(--b1)'; avatarColor = 'var(--a)';
  }

  /* date label: "Сегодня, 2 апреля · 15:00 – 16:00" */
  var dayLabel = dateGroupLabel(dt, now);
  if (dayLabel !== 'Ранее') {
    dayLabel += ', ' + dt.getDate() + ' ' + MONTHS_GEN[dt.getMonth()];
  } else {
    dayLabel = fmtDateFull(dt);
  }
  var dateVal = dayLabel + ' · ' + fmtTime(dt) + ' – ' + fmtTimeOffset(dt, dur);

  /* contact "Написать" button */
  var contactUsername = contact.replace(/^@/, '');
  var contactHtml = contact
    ? '<div class="dr-val" style="display:flex;align-items:center;justify-content:space-between;gap:8px">'
        + '<span>' + contact + ' · Telegram</span>'
        + '<button data-user="' + escHtml(contactUsername) + '" onclick="openTelegramChat(this.dataset.user)" style="display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:99px;background:rgba(91,142,255,.18);color:#7aaaff;border:1px solid rgba(91,142,255,.28);font-family:var(--font);font-size:12px;font-weight:700;cursor:pointer;flex-shrink:0">'
          + '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
          + 'Написать'
        + '</button>'
      + '</div>'
    : '<div class="dr-val">Не указан</div>';

  /* meeting link row */
  var linkRow = link
    ? '<div class="detail-row"><div class="dr-label">Ссылка на встречу</div>'
      + '<div class="dr-val link" data-link="' + escHtml(link) + '" onclick="openLink(this.dataset.link)" style="cursor:pointer">' + escHtml(linkDisplay) + '</div></div>'
    : '';

  /* notes row */
  var notesRow = notes
    ? '<div class="detail-row"><div class="dr-label">Заметка</div><div class="dr-val">' + notes + '</div></div>'
    : '';

  /* HTML: avatar + name */
  var html = '<div style="padding:20px 16px 0">'
    + '<div style="display:flex;align-items:center;gap:14px;margin-bottom:20px">'
      + '<div style="width:56px;height:56px;border-radius:16px;background:var(--s3);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;color:' + avatarColor + ';border:1px solid ' + borderColor + '">' + escHtml(initials) + '</div>'
      + '<div>'
        + '<div style="font-size:20px;font-weight:800;color:var(--t1);letter-spacing:-.02em">' + name + '</div>'
        + (contact ? '<div style="font-size:13px;color:var(--t2);margin-top:3px;font-weight:500">' + contact + '</div>' : '')
      + '</div>'
    + '</div>'
  + '</div>';

  /* detail card */
  html += '<div class="detail-card" style="border-color:' + borderColor + '">'
    + '<div class="detail-row"><div class="dr-label">Расписание</div><div class="dr-val">' + schedTitle + '</div></div>'
    + '<div class="detail-row"><div class="dr-label">Дата и время</div><div class="dr-val">' + dateVal + '</div></div>'
    + '<div class="detail-row"><div class="dr-label">Статус</div><div class="dr-val">' + meetingStatusHtml(dStatus) + '</div></div>'
    + '<div class="detail-row"><div class="dr-label">Платформа</div><div class="dr-val">' + platform + '</div></div>'
    + linkRow
    + '<div class="detail-row" style="border-bottom:none"><div class="dr-label">Контакт</div>' + contactHtml + '</div>'
    + notesRow
  + '</div>';

  /* cancelled info banner */
  if (dStatus === 'cancelled') {
    html += '<div style="padding:0 16px">'
      + '<div style="background:var(--rs);border-radius:var(--r2);padding:12px 16px;display:flex;align-items:center;gap:10px">'
        + '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="16" r="1" fill="var(--red)"/></svg>'
        + '<span style="font-size:13px;color:var(--red);font-weight:600">Встреча была отменена</span>'
      + '</div>'
    + '</div>';
  }

  /* action buttons */
  var id = m.id;
  if (dStatus === 'confirmed' || dStatus === 'ongoing') {
    var linkAttr = link ? ' data-link="' + escHtml(link) + '"' : '';
    html += '<div style="padding:0 16px;display:flex;gap:8px">'
      + '<button class="btn btn-primary" style="flex:1;height:40px;padding:0;font-size:13px"' + linkAttr + ' onclick="if(this.dataset.link)openLink(this.dataset.link)">Подключиться</button>'
      + '<button class="btn btn-cancel" style="flex:1;height:40px;padding:0;font-size:13px" onclick="openCancelSheet(\'' + id + '\')">Отменить встречу</button>'
    + '</div>';
  } else if (dStatus === 'pending') {
    html += '<div style="padding:0 16px;display:flex;gap:8px">'
      + '<button class="btn btn-confirm" style="flex:1;height:40px;padding:0;font-size:13px" onclick="confirmMeeting(\'' + id + '\')">Подтвердить</button>'
      + '<button class="btn btn-danger" style="flex:1;height:40px;padding:0;font-size:13px" onclick="openCancelSheet(\'' + id + '\')">Отклонить</button>'
    + '</div>';
  } else if (dStatus === 'noans') {
    var writeAttr = contactUsername ? ' data-user="' + escHtml(contactUsername) + '" onclick="openTelegramChat(this.dataset.user)"' : '';
    html += '<div style="padding:0 16px;display:flex;gap:8px">'
      + '<button class="btn" style="flex:1;height:40px;padding:0;font-size:13px;background:rgba(91,142,255,.15);color:#7AAAFF;border:1px solid rgba(91,142,255,.3)"' + writeAttr + '>Написать</button>'
      + '<button class="btn btn-cancel" style="flex:1;height:40px;padding:0;font-size:13px" onclick="openCancelSheet(\'' + id + '\')">Отменить встречу</button>'
    + '</div>';
  }
  /* cancelled / completed → no action buttons, just scroll-fill */

  return html;
}

async function confirmMeeting(id) {
  var btn = event?.target?.closest('button');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  var { data, error } = await apiFetch('PATCH', '/api/bookings/' + id + '/confirm');
  if (error) {
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast('Не удалось подтвердить', 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Подтвердить'; }
    return;
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast('Встреча подтверждена ✓', 'success');

  /* update local state */
  var idx = state.bookings.findIndex(function(b) { return b.id === id; });
  if (idx >= 0) {
    state.bookings[idx].status = 'confirmed';
    if (data && data.meeting_link) state.bookings[idx].meeting_link = data.meeting_link;
  }

  if (state.currentScreen === 's-home') {
    await loadHome();
  } else {
    /* re-render detail screen */
    if (state.currentScreen === 's-meet-detail' || state.currentScreen === 's-meet-noans') {
      openMeetDetail(id);
    }
    if (typeof renderMeetingsList === 'function') renderMeetingsList();
  }
}

function openCancelSheet(id) {
  state.pendingCancelId = id;
  state._deleteMode = false;
  var m = (state.bookings || []).find(function(b) { return b.id === id; });
  var titleEl = document.getElementById('sheet-cancel-title');
  var subEl = document.getElementById('sheet-cancel-sub');
  var actEl = document.getElementById('sheet-cancel-action');
  if (m && m.status === 'pending') {
    if (titleEl) titleEl.textContent = 'Отклонить встречу?';
    if (subEl) subEl.textContent = 'Встреча с ' + (m.guest_name || 'участником') + ' будет отменена.';
    if (actEl) actEl.textContent = 'Отклонить встречу';
  } else {
    if (titleEl) titleEl.textContent = 'Отменить встречу?';
    if (subEl) subEl.textContent = 'Участник получит уведомление об отмене. Слот освободится.';
    if (actEl) actEl.textContent = 'Отменить встречу';
  }
  showSheet('sheet-cancel');
}

async function confirmCancelMeeting() {
  if (state._deleteMode) { confirmDeleteSchedule(); return; }
  var id = state.pendingCancelId;
  if (!id) { closeSheet('sheet-cancel'); return; }

  var btn = document.getElementById('sheet-cancel-action');
  var origText = btn ? btn.textContent : 'Отменить встречу';
  if (btn) { btn.disabled = true; btn.textContent = 'Отменяем…'; }

  console.log('[cancel] id=', id, 'hasInitData=', !!tg?.initData, 'url=', '/api/bookings/' + id + '/cancel');

  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
  var { data, error } = await apiFetch('PATCH', '/api/bookings/' + id + '/cancel');
  console.log('[cancel] response data=', data, 'error=', error);

  if (error) {
    if (btn) { btn.disabled = false; btn.textContent = origText; }
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    showToast(typeof error === 'string' ? error : 'Не удалось отменить', 'error');
    return;
  }

  closeSheet('sheet-cancel');
  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast('Встреча отменена', 'success');

  /* update local state */
  var idx = (state.bookings || []).findIndex(function(b) { return b.id === id; });
  if (idx >= 0) state.bookings[idx].status = 'cancelled';
  state.pendingCancelId = null;

  if (state.currentScreen === 's-home') {
    await loadHome();
  } else {
    if (state.currentScreen === 's-meet-detail' || state.currentScreen === 's-meet-noans') {
      goBack();
    }
    if (typeof renderMeetingsList === 'function') renderMeetingsList();
  }
}

