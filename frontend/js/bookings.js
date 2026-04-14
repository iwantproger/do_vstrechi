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
  const tid = u.id || (state.user && state.user.telegram_id);

  /* home-avatar — inject img inside the existing circle div (preserves onclick) */
  const ha = document.getElementById('home-avatar');
  if (ha) {
    if (tid) {
      ha.innerHTML = '<img src="/api/users/' + tid + '/avatar"'
        + ' style="width:100%;height:100%;object-fit:cover;border-radius:inherit"'
        + ' onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"'
        + ' loading="lazy">'
        + '<span style="display:none;width:100%;height:100%;align-items:center;justify-content:center">' + escHtml(ini || '?') + '</span>';
    } else {
      ha.textContent = ini || '?';
    }
  }

  /* profile-avatar — same approach */
  const pa = document.getElementById('profile-avatar');
  if (pa) {
    if (tid) {
      pa.innerHTML = '<img src="/api/users/' + tid + '/avatar"'
        + ' style="width:100%;height:100%;object-fit:cover;border-radius:inherit"'
        + ' onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"'
        + ' loading="lazy">'
        + '<span style="display:none;width:100%;height:100%;align-items:center;justify-content:center">' + escHtml(ini || '?') + '</span>';
    } else {
      pa.textContent = ini || '?';
    }
  }

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

  var { data, error } = await apiFetch('GET', '/api/bookings?role=all');
  if (error) { setHomeSubtitle('Не удалось загрузить данные', true); return; }
  if (data) state.bookings = data;

  const now = new Date();
  const todayStr = formatDate(now);

  const allToday = (state.bookings || [])
    .filter(b => formatDate(new Date(b.scheduled_time)) === todayStr && b.status !== 'cancelled')
    .sort((a, b) => new Date(a.scheduled_time) - new Date(b.scheduled_time));
  const todayMeetings = allToday.filter(function(b) {
    var ds = getMeetingStatus(b);
    return ds !== 'completed' && ds !== 'noans';
  });

  /* External calendar events for today (display-enabled, deduped by backend) */
  var todayExtEvents = [];
  try {
    var extRes = await apiFetch('GET', '/api/calendar/external-events?from_date=' + todayStr + '&to_date=' + todayStr);
    if (extRes.data && extRes.data.events) {
      todayExtEvents = extRes.data.events
        .filter(function(e) { return formatDate(new Date(e.start_time)) === todayStr; })
        .map(function(e) { return Object.assign({}, e, { _dt: new Date(e.start_time), _isExt: true }); });
    }
  } catch (e) { /* optional — ignore */ }

  /* Merge and sort all items by time */
  var todayAll = todayMeetings.map(function(m) {
    return Object.assign({}, m, { _dt: new Date(m.scheduled_time) });
  }).concat(todayExtEvents);
  todayAll.sort(function(a, b) { return a._dt - b._dt; });

  const totalCount = todayAll.length;

  /* subtitle */
  const sub = document.getElementById('home-subtitle');
  if (sub) {
    const n = totalCount;
    if (n === 0) {
      sub.innerHTML = '<span style="font-weight:800;color:var(--t1)">Нет встреч на сегодня</span>';
    } else {
      const w = n === 1 ? 'встреча' : (n >= 2 && n <= 4) ? 'встречи' : 'встреч';
      sub.innerHTML = '<span style="font-weight:800;color:var(--t1)">У тебя </span>'
        + '<span style="font-weight:800;color:var(--a)">' + n + ' ' + w + '</span>'
        + '<span style="font-weight:800;color:var(--t1)"> на сегодня</span>';
    }
  }

  /* hero card — nearest booking (not ext event) that hasn't ended yet */
  const nearest = todayMeetings.find(b => {
    const end = new Date(b.scheduled_time);
    end.setMinutes(end.getMinutes() + (b.schedule_duration || 60));
    return end > now;
  });
  state.nextBooking = nearest || null;
  const heroEl = document.getElementById('home-hero');
  if (heroEl) heroEl.innerHTML = nearest ? renderHeroCard(nearest, now) : '';

  /* meetings list — bookings + external events merged, exclude hero booking */
  const heroId = nearest ? nearest.id : null;
  const label = document.getElementById('home-section-label');
  const listEl = document.getElementById('home-meetings');
  const todayList = heroId ? todayAll.filter(function(m) { return m.id !== heroId; }) : todayAll;
  if (todayList.length) {
    if (label) label.classList.remove('hidden');
    if (listEl) listEl.innerHTML = todayList.map(function(m) {
      return m._isExt ? renderExtEventCard(m) : renderMeetingCard(m);
    }).join('');
  } else {
    if (label) label.classList.add('hidden');
    if (listEl) listEl.innerHTML = todayList.length === 0 && nearest
      ? ''
      : renderEmpty('Нет встреч', 'На сегодня ничего не запланировано');
  }
}

function renderHeroCard(m, now) {
  const dt = new Date(m.scheduled_time);
  const time = fmtTime(dt);
  const dur = m.schedule_duration || 60;
  const datePart = dt.getDate() + ' ' + MONTHS_GEN[dt.getMonth()].slice(0, 3);
  const heroIsDefault = m.is_manual && (!m.schedule_title || m.schedule_title === 'Личные встречи');
  const plat = heroIsDefault ? '' : (PLAT_NAMES[m.platform || m.schedule_platform] || m.schedule_platform || '');
  const meta = datePart + ' · ' + dur + ' мин' + (plat ? ' · ' + plat : '');
  const isGuest = m.my_role === 'guest';
  /* For guest meetings show the organizer's name; for organizer meetings show the guest's name */
  const name = isGuest
    ? escHtml(m.organizer_first_name || 'Организатор')
    : escHtml(m.guest_name || '');
  const title = m.is_manual ? escHtml(m.title || m.display_title || '') : escHtml(m.schedule_title || '');
  const withinHour = (dt - now) > 0 && (dt - now) < 3600000;
  const heroStatus = getMeetingStatus(m);
  const guestBadge = isGuest ? '<div style="margin-bottom:6px">' + badgeParticipant() + '</div>' : '';

  if (heroStatus === 'confirmed' || heroStatus === 'ongoing') {
    const heroLabel = heroStatus === 'ongoing' ? 'ВСТРЕЧА ИДЁТ' : 'БЛИЖАЙШАЯ ВСТРЕЧА';
    const heroBorder = heroStatus === 'ongoing' ? 'rgba(45,212,160,.4)' : 'rgba(0,229,168,.18)';
    return '<div onclick="if(!event.target.closest(\'button\')){openMeetDetail(\'' + m.id + '\')}" style="margin:32px 16px 0;background:#182020;border-radius:20px;padding:18px;border:1px solid ' + heroBorder + ';cursor:pointer">'
      + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--a);margin-bottom:8px">' + heroLabel + '</div>'
      + guestBadge
      + '<div style="font-size:18px;font-weight:800;color:#fff">' + name + '</div>'
      + '<div style="font-size:13px;font-weight:500;color:#fff;margin-top:2px">' + title + '</div>'
      + '<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-top:12px;gap:16px">'
        + '<div>'
          + '<div style="font-size:30px;font-weight:800;color:#fff;line-height:1">' + time + '</div>'
          + '<div style="font-size:12px;font-weight:500;color:var(--t2);margin-top:2px">' + meta + '</div>'
        + '</div>'
        + renderMeetingActionButton(m, 'hero')
      + '</div>'
    + '</div>';
  }

  /* pending — amber card, label depends on role + urgency */
  const heroLabel = isGuest
    ? (withinHour ? 'До встречи меньше часа' : 'Ожидает начала')
    : (withinHour ? 'До встречи меньше часа' : 'Ожидает подтверждения');
  const pendingBtns = !isGuest
    ? '<div style="display:flex;gap:8px;margin-top:14px">'
        + '<button class="btn btn-confirm" onclick="confirmMeeting(\'' + m.id + '\')" style="flex:1;height:40px;padding:0;font-size:13px">Подтвердить</button>'
        + '<button class="btn btn-danger" onclick="openCancelSheet(\'' + m.id + '\')" style="flex:1;height:40px;padding:0;font-size:13px">Отклонить</button>'
      + '</div>'
    : '';
  return '<div onclick="if(!event.target.closest(\'button\')){openMeetDetail(\'' + m.id + '\')}" style="margin:32px 16px 0;background:#1E1200;border-radius:20px;padding:18px;border:1px solid rgba(245,166,35,.3);cursor:pointer">'
    + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--amber);margin-bottom:8px">' + heroLabel + '</div>'
    + guestBadge
    + '<div style="font-size:18px;font-weight:800;color:#fff">' + name + '</div>'
    + '<div style="font-size:13px;font-weight:500;color:#fff;margin-top:2px">' + title + '</div>'
    + '<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-top:12px;gap:16px">'
      + '<div>'
        + '<div style="font-size:30px;font-weight:800;color:#fff;line-height:1">' + time + '</div>'
        + '<div style="font-size:12px;font-weight:500;color:var(--t2);margin-top:2px">' + meta + '</div>'
      + '</div>'
    + '</div>'
    + pendingBtns
  + '</div>';
}

function isGuestBooking(m) {
  return m.my_role === 'guest';
}

/* Returns HTML for the primary action button on a meeting card/detail.
   - Online platforms (jitsi/zoom/google_meet): "Подключиться" opens meeting_link
   - Offline: "Место" copies address to clipboard (or opens maps if URL)
   - Other/no link: empty string
   style: 'hero' → inline style pill, 'detail' → .btn.btn-primary */
function renderMeetingActionButton(m, style) {
  var plat = m.platform || m.schedule_platform || '';
  var link = m.meeting_link || '';
  var addr = m.location_address || '';

  if (['jitsi', 'zoom', 'google_meet'].indexOf(plat) >= 0 && link) {
    if (style === 'hero') {
      return '<button data-link="' + escHtml(link) + '" onclick="openLink(this.dataset.link)" style="height:40px;padding:0 16px;background:var(--a);border:none;border-radius:999px;font-family:var(--font);font-size:13px;font-weight:700;color:#000;cursor:pointer;white-space:nowrap;flex-shrink:0">Подключиться</button>';
    }
    return '<button class="btn btn-primary" style="flex:1;height:40px;padding:0;font-size:13px" data-link="' + escHtml(link) + '" onclick="openLink(this.dataset.link)">Подключиться</button>';
  }

  if (plat === 'offline' && addr) {
    var safeAddr = escHtml(addr);
    /* If the address looks like a URL, open it; otherwise copy to clipboard */
    var isUrl = /^https?:\/\//i.test(addr);
    var action = isUrl
      ? 'openLink(\'' + escHtml(addr).replace(/'/g, '\\\'') + '\')'
      : 'navigator.clipboard && navigator.clipboard.writeText(\'' + escHtml(addr).replace(/'/g, '\\\'') + '\').then(function(){showToast(\'Адрес скопирован\')})';
    if (style === 'hero') {
      return '<button onclick="' + action + '" style="height:40px;padding:0 16px;background:var(--a);border:none;border-radius:999px;font-family:var(--font);font-size:13px;font-weight:700;color:#000;cursor:pointer;white-space:nowrap;flex-shrink:0">Место</button>';
    }
    return '<button class="btn btn-primary" style="flex:1;height:40px;padding:0;font-size:13px" onclick="' + action + '">Место</button>';
  }

  return '';
}

function renderMeetingCard(m) {
  const dt = new Date(m.scheduled_time);
  const dur = m.schedule_duration || 60;
  const timeStart = fmtTime(dt);
  const cardEndDt = m.booking_end_time || m.end_time;
  const timeEnd = cardEndDt ? fmtTime(new Date(cardEndDt)) : fmtTimeOffset(dt, dur);
  const isGuest = isGuestBooking(m);
  /* for guest bookings: show organizer name instead of guest name */
  const personName = isGuest ? (m.organizer_first_name || 'Организатор') : (m.guest_name || (m.is_manual ? 'Личная встреча' : ''));
  const name = escHtml(personName);
  const title = escHtml(m.is_manual ? (m.title || m.display_title || '') : (m.schedule_title || ''));
  const dStatus = m._ds || getMeetingStatus(m);
  const isPending = dStatus === 'pending' && !m.is_manual && !isGuest;
  const guestBadge = isGuest ? badgeParticipant() : '';

  /* avatar: organizer sees guest photo, guest sees organizer photo */
  const personTid = isGuest ? m.organizer_telegram_id : m.guest_telegram_id;
  const personIni = getInitials(personName);
  const avatarHtml = renderAvatar(personTid, personIni, 40);

  return '<div onclick="openMeetDetail(\'' + m.id + '\')" style="margin:0 16px 8px;background:var(--s1);border-radius:14px;padding:14px 16px;cursor:pointer">'
    + '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px' + (isPending ? ';margin-bottom:24px' : '') + '">'
      + avatarHtml
      + '<div style="flex:1;min-width:0">'
        + '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px"><span style="font-size:14px;font-weight:700;color:var(--t1)">' + name + '</span>' + guestBadge + '</div>'
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
  /* FIX: role=all — показывать и организаторские, и гостевые встречи */
  var { data, error } = await apiFetch('GET', '/api/bookings?role=all');
  if (error) { showToast('Ошибка загрузки встреч', 'error'); return; }
  if (data) state.bookings = data;

  /* Load external calendar events (display-enabled) — non-blocking */
  state.extEvents = [];
  try {
    var now = new Date();
    var from = new Date(now); from.setDate(from.getDate() - 1);
    var to = new Date(now); to.setDate(to.getDate() + 60);
    var fromStr = from.toISOString().slice(0, 10);
    var toStr = to.toISOString().slice(0, 10);
    var extRes = await apiFetch('GET', '/api/calendar/external-events?from_date=' + fromStr + '&to_date=' + toStr);
    if (extRes.data && extRes.data.events) state.extEvents = extRes.data.events;
  } catch (e) { /* ignore — calendar integration is optional */ }

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
    if (_meetFilter === 'all')     return m._ds === 'pending' || m._ds === 'confirmed' || m._ds === 'ongoing' || m._ds === 'noans';
    if (_meetFilter === 'noans')   return m._ds === 'noans';
    if (_meetFilter === 'ok')      return m._ds === 'confirmed' || m._ds === 'ongoing';
    if (_meetFilter === 'archive') return m._ds === 'completed' || m._ds === 'cancelled';
    return true;
  });

  /* merge external events for all/ok tabs */
  var showExt = _meetFilter === 'all' || _meetFilter === 'ok';
  var extItems = [];
  if (showExt && state.extEvents && state.extEvents.length) {
    extItems = state.extEvents.map(function(e) {
      return Object.assign({}, e, { _dt: new Date(e.start_time), _isExt: true });
    });
  }

  /* sort: upcoming asc, archive desc */
  var isArchive = _meetFilter === 'archive';
  filtered.sort(function(a, b) { return isArchive ? b._dt - a._dt : a._dt - b._dt; });

  /* merge and sort all items */
  var allItems = filtered.concat(extItems);
  allItems.sort(function(a, b) { return isArchive ? b._dt - a._dt : a._dt - b._dt; });

  if (!allItems.length) {
    list.innerHTML = renderEmpty('Нет встреч', 'В этой категории пока ничего нет');
    return;
  }

  /* group */
  var groups = {};
  var groupOrder = [];
  var LMAP = { date: 'По дате', fmt: 'По расписаниям' };

  allItems.forEach(function(m) {
    var key;
    if (_meetGroup === 'date') {
      key = dateGroupLabel(m._dt, now);
    } else {
      key = m._isExt ? (m.calendar_name || 'Внешний календарь') : (m.schedule_title || 'Без расписания');
    }
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
      if (m._isExt) {
        list.insertAdjacentHTML('beforeend', renderExtEventCard(m));
      } else {
        list.insertAdjacentHTML('beforeend', renderMeetingCard(m));
      }
    });
  });
}

function _extProviderBadge(provider) {
  if (provider === 'google') {
    return '<div class="ext-prov-badge ext-prov-google">'
      + '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09a6.97 6.97 0 0 1 0-4.17V7.07H2.18a11.01 11.01 0 0 0 0 9.86l3.66-2.84z" fill="#FBBC05"/><path d="M12 4.75c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 1.09 14.97 0 12 0 7.7 0 3.99 2.47 2.18 6.07l3.66 2.85c.87-2.6 3.3-4.17 6.16-4.17z" fill="#EA4335"/></svg>'
      + '</div>';
  }
  if (provider === 'yandex') {
    return '<div class="ext-prov-badge ext-prov-yandex">'
      + '<svg viewBox="0 0 24 24" width="14" height="14"><rect width="24" height="24" rx="4" fill="#FC3F1D"/><text x="12" y="17" text-anchor="middle" fill="#fff" font-size="13" font-weight="700" font-family="Arial">Я</text></svg>'
      + '</div>';
  }
  if (provider === 'apple') {
    return '<div class="ext-prov-badge ext-prov-apple">'
      + '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83" fill="#aaa"/><path d="M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" fill="#aaa"/></svg>'
      + '</div>';
  }
  return '<div class="ext-prov-badge">'
    + '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
    + '</div>';
}

function renderExtEventCard(e) {
  var startDt = new Date(e.start_time);
  var endDt = new Date(e.end_time);
  var timeStr = e.is_all_day ? 'Весь день' : (fmtTime(startDt) + ' – ' + fmtTime(endDt));
  var color = e.calendar_color || '#888';
  var calName = escHtml(e.calendar_name || '');
  var title = escHtml(e.summary || 'Занято');
  var badge = _extProviderBadge(e.provider || '');
  return '<div class="ext-event-card" style="position:relative">'
    + badge
    + '<div class="ext-event-cal-row">'
    +   '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + escHtml(color) + ';flex-shrink:0;margin-top:1px"></span>'
    +   '<span class="ext-event-cal-name">' + calName + '</span>'
    + '</div>'
    + '<div class="ext-event-title">' + title + '</div>'
    + '<div class="ext-event-time">' + timeStr + '</div>'
    + '</div>';
}

/* ═══════════════════════════════════════════
   MEET DETAIL + NO-ANSWER
═══════════════════════════════════════════ */
async function openMeetDetail(id) {
  var m = (state.bookings || []).find(function(b) { return b.id === id; });

  /* FIX: если встречи нет в state (deep link / гость) — загрузить из API */
  if (!m) {
    var { data, error } = await apiFetch('GET', '/api/bookings/' + id);
    if (error || !data) { showToast('Встреча не найдена', 'error'); return; }
    m = data;
  }

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
  var isGuest = isGuestBooking(m);

  /* FIX: if I'm the guest, show organizer as the main person */
  var name, initials, contact;
  if (isGuest) {
    name = escHtml(m.organizer_first_name || 'Организатор');
    initials = getInitials(m.organizer_first_name || 'O');
    contact = m.organizer_username ? escHtml('@' + m.organizer_username) : '';
  } else {
    name = escHtml(m.guest_name || '');
    initials = getInitials(m.guest_name);
    contact = escHtml(m.guest_contact || '');
  }
  var isDefaultSchedule = m.is_manual && (!m.schedule_title || m.schedule_title === 'Личные встречи');
  var schedTitle = m.is_manual
    ? escHtml(isDefaultSchedule ? 'Без расписания' : (m.schedule_title || m.title || ''))
    : escHtml(m.schedule_title || '');
  var bPlatKey = m.platform || m.schedule_platform || '';
  var platform = isDefaultSchedule ? '' : escHtml(PLAT_NAMES[bPlatKey] || bPlatKey || '');
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
  var endTimeStr;
  var bookingEnd = m.booking_end_time || m.end_time;
  if (bookingEnd) {
    var endDt = new Date(bookingEnd);
    endTimeStr = fmtTime(endDt);
    /* Multi-day: show end date too */
    if (endDt.toDateString() !== dt.toDateString()) {
      endTimeStr = endDt.getDate() + ' ' + MONTHS_GEN[endDt.getMonth()].slice(0, 3) + ' ' + fmtTime(endDt);
    }
  } else {
    endTimeStr = fmtTimeOffset(dt, dur);
  }
  var dateVal = dayLabel + ' · ' + fmtTime(dt) + ' – ' + endTimeStr;

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

  /* meeting link / address row */
  var bPlat = m.platform || m.schedule_platform || '';
  var bAddr = m.location_address || '';
  var linkRow;
  if (bPlat === 'offline' && bAddr) {
    linkRow = '<div class="detail-row"><div class="dr-label">Место встречи</div>'
      + '<div class="dr-val">' + escHtml(bAddr) + '</div></div>';
  } else {
    linkRow = link
      ? '<div class="detail-row"><div class="dr-label">Ссылка на встречу</div>'
        + '<div class="dr-val link" data-link="' + escHtml(link) + '" onclick="openLink(this.dataset.link)" style="cursor:pointer">' + escHtml(linkDisplay) + '</div></div>'
      : '';
  }

  /* notes row */
  var notesRow = notes
    ? '<div class="detail-row"><div class="dr-label">Заметка</div><div class="dr-val">' + notes + '</div></div>'
    : '';

  /* role badge */
  var roleBadge = isGuest ? badgeParticipant() : '';

  /* HTML: avatar + name */
  var personTid = isGuest ? m.organizer_telegram_id : m.guest_telegram_id;
  var detailAvatar = renderAvatar(personTid, initials, 56);
  var html = '<div style="padding:20px 16px 0">'
    + '<div style="display:flex;align-items:center;gap:14px;margin-bottom:20px">'
      + detailAvatar
      + '<div>'
        + '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px"><span style="font-size:20px;font-weight:800;color:var(--t1);letter-spacing:-.02em">' + name + '</span>' + roleBadge + '</div>'
        + (contact ? '<div style="font-size:13px;color:var(--t2);margin-top:3px;font-weight:500">' + contact + '</div>' : '')
      + '</div>'
    + '</div>'
  + '</div>';

  /* detail card */
  var platformRow = platform
    ? '<div class="detail-row"><div class="dr-label">Платформа</div><div class="dr-val">' + platform + '</div></div>'
    : '';
  var linkRowFinal = isDefaultSchedule ? '' : linkRow;
  html += '<div class="detail-card" style="border-color:' + borderColor + '">'
    + '<div class="detail-row"><div class="dr-label">Расписание</div><div class="dr-val">' + schedTitle + '</div></div>'
    + '<div class="detail-row"><div class="dr-label">Дата и время</div><div class="dr-val">' + dateVal + '</div></div>'
    + '<div class="detail-row"><div class="dr-label">Статус</div><div class="dr-val">' + meetingStatusHtml(dStatus) + '</div></div>'
    + platformRow
    + linkRowFinal
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

  /* action buttons — guests only see connect + cancel, not confirm/reject */
  var id = m.id;
  if (dStatus === 'confirmed' || dStatus === 'ongoing') {
    var connectBtn = renderMeetingActionButton(m, 'detail');
    html += '<div style="padding:0 16px;display:flex;gap:8px">'
      + connectBtn
      + '<button class="btn btn-cancel" style="flex:1;height:40px;padding:0;font-size:13px" onclick="openCancelSheet(\'' + id + '\')">Отменить встречу</button>'
    + '</div>';
  } else if (dStatus === 'pending' && !isGuest) {
    html += '<div style="padding:0 16px;display:flex;gap:8px">'
      + '<button class="btn btn-confirm" style="flex:1;height:40px;padding:0;font-size:13px" onclick="confirmMeeting(\'' + id + '\')">Подтвердить</button>'
      + '<button class="btn btn-danger" style="flex:1;height:40px;padding:0;font-size:13px" onclick="openCancelSheet(\'' + id + '\')">Отклонить</button>'
    + '</div>';
  } else if (dStatus === 'pending' && isGuest) {
    html += '<div style="padding:0 16px;display:flex;gap:8px">'
      + '<button class="btn btn-cancel" style="flex:1;height:40px;padding:0;font-size:13px" onclick="openCancelSheet(\'' + id + '\')">Отменить встречу</button>'
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
  /* reset disabled state from any previous operation */
  if (actEl) { actEl.disabled = false; actEl.className = 'btn btn-danger'; }
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

