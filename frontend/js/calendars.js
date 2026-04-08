/* ═══════════════════════════════════════════
   CALENDARS — integration with external calendars
═══════════════════════════════════════════ */

var _calPollTimer = null;
var _calPollTimeout = null;
var _calDAVProvider = null;  // текущий провайдер открытого CalDAV модала

async function loadCalendarAccounts() {
  var list = document.getElementById('calendars-list');
  var empty = document.getElementById('calendars-empty');
  if (!list) return;

  list.innerHTML = '<div class="cal-skeleton"><div class="skel-block"></div><div class="skel-block short"></div></div>';
  if (empty) empty.style.display = 'none';

  var { data, error } = await apiFetch('GET', '/api/calendar/accounts');
  if (error) {
    list.innerHTML = '<div class="cal-error">'
      + '<p>Не удалось загрузить</p>'
      + '<button class="btn btn-sm" onclick="loadCalendarAccounts()">Повторить</button>'
      + '</div>';
    return;
  }

  if (!data || !data.length) {
    list.innerHTML = '';
    if (empty) empty.style.display = '';
    return;
  }

  if (empty) empty.style.display = 'none';
  list.innerHTML = data.map(renderCalendarAccount).join('');
}

function renderCalendarAccount(acc) {
  var icon = providerIcon(acc.provider);
  var statusCls = (acc.status === 'active') ? 'dot-green' : 'dot-red';
  var statusText = acc.status === 'active' ? 'Подключён' : acc.status === 'expired' ? 'Требуется переподключение' : acc.status;
  var email = acc.provider_email ? escHtml(acc.provider_email) : '';
  var accId = escHtml(String(acc.id));

  var calendarsHtml = '';
  if (acc.calendars && acc.calendars.length) {
    calendarsHtml = '<div class="cal-connections" id="cal-conn-' + accId + '">'
      + acc.calendars.map(function(c) { return renderCalendarConnection(c, accId); }).join('')
      + '</div>';
  }

  var reconnectBtn = '';
  if (acc.status === 'expired' || acc.status === 'revoked') {
    reconnectBtn = '<button class="btn btn-sm btn-accent" onclick="connectGoogle()" style="margin-top:8px">Переподключить</button>';
  }

  return '<div class="cal-account">'
    + '<div class="cal-account-header" onclick="toggleCalExpand(\'' + accId + '\')">'
    +   '<div class="cal-provider-info">'
    +     '<div class="cal-provider-icon">' + icon + '</div>'
    +     '<div class="cal-provider-details">'
    +       '<div class="cal-provider-name">' + escHtml(providerName(acc.provider)) + '</div>'
    +       '<div class="cal-provider-email">' + email + '</div>'
    +     '</div>'
    +   '</div>'
    +   '<div class="cal-account-right">'
    +     '<span class="status-dot ' + statusCls + '"></span>'
    +     '<svg class="cal-chevron" id="cal-chev-' + accId + '" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>'
    +   '</div>'
    + '</div>'
    + (acc.status !== 'active' ? '<div class="cal-status-warn">' + escHtml(statusText) + reconnectBtn + '</div>' : '')
    + calendarsHtml
    + '<div class="cal-account-footer">'
    +   '<button class="btn-text btn-danger" onclick="disconnectAccount(\'' + accId + '\')">Отключить</button>'
    + '</div>'
    + '</div>';
}

function renderCalendarConnection(c, accountId) {
  var color = c.calendar_color || '#888';
  var connId = escHtml(String(c.id));
  var readOn = c.is_read_enabled ? ' on' : '';
  var writeOn = c.is_write_target ? ' on' : '';

  return '<div class="cal-conn">'
    + '<div class="cal-conn-info">'
    +   '<span class="cal-color-dot" style="background:' + escHtml(color) + '"></span>'
    +   '<span class="cal-conn-name">' + escHtml(c.calendar_name) + '</span>'
    + '</div>'
    + '<div class="cal-conn-toggles">'
    +   '<div class="cal-tog-wrap">'
    +     '<span class="cal-tog-label">Блокировать</span>'
    +     '<div class="tog-sm' + readOn + '" onclick="toggleCalConnection(\'' + connId + '\',\'is_read_enabled\',this)"></div>'
    +   '</div>'
    +   '<div class="cal-tog-wrap">'
    +     '<span class="cal-tog-label">Записывать</span>'
    +     '<div class="tog-sm' + writeOn + '" onclick="toggleCalConnection(\'' + connId + '\',\'is_write_target\',this)"></div>'
    +   '</div>'
    + '</div>'
    + '</div>';
}


/* ── CalDAV Connect (Yandex, Apple) ─────── */

var _CALDAV_CONFIG = {
  yandex: {
    title:       'Подключить Яндекс Календарь',
    desc:        'Введите ваш Яндекс email и пароль приложения (не основной пароль от аккаунта).',
    placeholder: 'user@yandex.ru',
    help: '<ol>'
      + '<li>Откройте <a href="https://id.yandex.ru/security/app-passwords" target="_blank">id.yandex.ru</a> → Пароли приложений</li>'
      + '<li>Нажмите «Создать новый пароль»</li>'
      + '<li>Выберите тип «Календарь (CalDAV)»</li>'
      + '<li>Скопируйте сгенерированный пароль</li>'
      + '<li>Вставьте его в поле выше</li>'
      + '</ol>',
  },
  apple: {
    title:       'Подключить Apple Calendar',
    desc:        'Введите ваш Apple ID и пароль приложения (создаётся отдельно от основного пароля).',
    placeholder: 'apple-id@icloud.com',
    help: '<ol>'
      + '<li>Откройте <a href="https://appleid.apple.com" target="_blank">appleid.apple.com</a> → Вход и безопасность</li>'
      + '<li>Нажмите «Пароли приложений» → «Создать пароль»</li>'
      + '<li>Введите название (например, «До встречи»)</li>'
      + '<li>Скопируйте 16-символьный пароль (формат: xxxx-xxxx-xxxx-xxxx)</li>'
      + '<li>Вставьте его в поле выше</li>'
      + '</ol>',
  },
};

function openCalDAVModal(provider) {
  var cfg = _CALDAV_CONFIG[provider];
  if (!cfg) return;

  _calDAVProvider = provider;

  var modal = document.getElementById('modal-caldav');
  var title = document.getElementById('caldav-modal-title');
  var desc = document.getElementById('caldav-modal-desc');
  var emailInp = document.getElementById('caldav-email');
  var pwdInp = document.getElementById('caldav-password');
  var errEl = document.getElementById('caldav-error');
  var helpEl = document.getElementById('caldav-help-content');
  var details = modal.querySelector('.caldav-help');

  title.textContent = cfg.title;
  desc.textContent = cfg.desc;
  emailInp.placeholder = cfg.placeholder;
  helpEl.innerHTML = cfg.help;

  /* Сброс полей */
  emailInp.value = '';
  pwdInp.value = '';
  errEl.style.display = 'none';
  errEl.textContent = '';
  if (details) details.removeAttribute('open');

  /* Сброс кнопки Submit */
  var submitBtn = document.getElementById('caldav-submit');
  submitBtn.disabled = false;
  submitBtn.textContent = 'Подключить';

  modal.style.display = 'flex';
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');

  /* Фокус на email с небольшой задержкой (анимация) */
  setTimeout(function() { emailInp.focus(); }, 250);
}

function closeCalDAVModal() {
  var modal = document.getElementById('modal-caldav');
  if (!modal) return;
  modal.style.display = 'none';
  _calDAVProvider = null;
  /* Очистить пароль из памяти */
  var pwdInp = document.getElementById('caldav-password');
  if (pwdInp) pwdInp.value = '';
}

async function submitCalDAVConnect() {
  var provider = _calDAVProvider;
  if (!provider) return;

  var emailInp = document.getElementById('caldav-email');
  var pwdInp = document.getElementById('caldav-password');
  var errEl = document.getElementById('caldav-error');
  var submitBtn = document.getElementById('caldav-submit');

  var email = (emailInp.value || '').trim();
  var password = pwdInp.value || '';

  /* Валидация */
  if (!email) {
    emailInp.focus();
    _caldavShowError('Введите email');
    return;
  }
  if (!password) {
    pwdInp.focus();
    _caldavShowError('Введите пароль приложения');
    return;
  }

  errEl.style.display = 'none';
  submitBtn.disabled = true;
  submitBtn.textContent = 'Подключение…';

  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

  var { data, error } = await apiFetch('POST', '/api/calendar/caldav/connect', {
    provider: provider,
    email: email,
    password: password,
  });

  /* Очистить пароль из памяти сразу после отправки */
  pwdInp.value = '';

  if (error || !data) {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Подключить';

    /* Бэкенд возвращает detail в error — "Неверный email или пароль" для 400 */
    var isAuthErr = error && (error.indexOf('Неверный') !== -1 || error.indexOf('пароль') !== -1);
    if (isAuthErr) {
      _caldavShowError('Неверный email или пароль. Убедитесь, что вы используете пароль приложения, а не основной пароль аккаунта.');
    } else {
      _caldavShowError('Не удалось подключить. Проверьте соединение и попробуйте позже.');
    }
    if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
    return;
  }

  /* Успех */
  if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  closeCalDAVModal();
  showToast('Календарь подключён!', 'success');
  loadCalendarAccounts();
}

function _caldavShowError(msg) {
  var errEl = document.getElementById('caldav-error');
  if (!errEl) return;
  errEl.textContent = msg;
  errEl.style.display = 'block';
}

/* Enter + keyboard-avoid для модала */
document.addEventListener('DOMContentLoaded', function() {
  var pwdInp = document.getElementById('caldav-password');
  if (pwdInp) {
    pwdInp.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); submitCalDAVConnect(); }
    });
    pwdInp.addEventListener('focus', function() {
      setTimeout(function() { pwdInp.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 300);
    });
  }
  var emailInp = document.getElementById('caldav-email');
  if (emailInp) {
    emailInp.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        var pwd = document.getElementById('caldav-password');
        if (pwd) pwd.focus();
      }
    });
    emailInp.addEventListener('focus', function() {
      setTimeout(function() { emailInp.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 300);
    });
  }

  /* visualViewport: подтягивать активный элемент при изменении высоты (открытие клавиатуры) */
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function() {
      var modal = document.getElementById('modal-caldav');
      if (!modal || modal.style.display === 'none') return;
      var active = document.activeElement;
      if (active && (active.id === 'caldav-email' || active.id === 'caldav-password')) {
        setTimeout(function() {
          active.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }, 50);
      }
    });
  }
});


/* ── Connect Google ────────────────────── */

function showConnectProviders() {
  var el = document.getElementById('connect-providers');
  if (!el) return;
  el.style.display = el.style.display === 'none' ? '' : 'none';
}

async function connectGoogle() {
  /* Step 1: get signed Google OAuth URL from backend (with initData auth) */
  var res = await apiFetch('GET', '/api/calendar/google/auth-url');
  if (res.error || !res.data || !res.data.url) {
    showToast('Не удалось получить ссылку для авторизации', 'error');
    return;
  }

  var googleUrl = res.data.url;

  /* Step 2: open Google consent screen in external browser */
  if (tg && tg.openLink) {
    tg.openLink(googleUrl);
  } else {
    window.open(googleUrl, 'google-auth', 'width=500,height=600');
  }

  showToast('Авторизуйтесь в открывшемся окне');
  startOAuthPolling('google');
}

function startOAuthPolling(provider) {
  stopOAuthPolling();
  var startCount = 0;

  /* remember current account count to detect new ones */
  apiFetch('GET', '/api/calendar/accounts').then(function(res) {
    var existing = (res.data || []).filter(function(a) { return a.provider === provider; });
    startCount = existing.length;
    poll();
  });

  function poll() {
    _calPollTimer = setTimeout(async function() {
      var { data } = await apiFetch('GET', '/api/calendar/accounts');
      var now = (data || []).filter(function(a) { return a.provider === provider; });
      if (now.length > startCount) {
        stopOAuthPolling();
        showToast('Календарь подключён!', 'success');
        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        loadCalendarAccounts();
        return;
      }
      poll();
    }, 3000);
  }

  /* 2-minute timeout */
  _calPollTimeout = setTimeout(function() {
    stopOAuthPolling();
    showToast('Время ожидания истекло. Попробуйте снова.', 'error');
  }, 120000);
}

function stopOAuthPolling() {
  if (_calPollTimer) { clearTimeout(_calPollTimer); _calPollTimer = null; }
  if (_calPollTimeout) { clearTimeout(_calPollTimeout); _calPollTimeout = null; }
}


/* ── Toggle connection ─────────────────── */

async function toggleCalConnection(connectionId, field, el) {
  var newVal = !el.classList.contains('on');
  var body = {};
  body[field] = newVal;

  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');

  var { data, error } = await apiFetch('POST', '/api/calendar/connections/' + connectionId + '/toggle', body);
  if (error) {
    showToast('Ошибка: ' + error, 'error');
    return;
  }

  /* If turning on write_target — reset others visually */
  if (field === 'is_write_target' && newVal) {
    var parent = el.closest('.cal-connections');
    if (parent) {
      parent.querySelectorAll('.cal-tog-wrap:last-child .tog-sm').forEach(function(t) {
        t.classList.remove('on');
      });
    }
  }

  el.classList.toggle('on', newVal);
}


/* ── Expand/Collapse ───────────────────── */

function toggleCalExpand(accId) {
  var conn = document.getElementById('cal-conn-' + accId);
  var chev = document.getElementById('cal-chev-' + accId);
  if (!conn) return;
  var isOpen = conn.style.display !== 'none';
  conn.style.display = isOpen ? 'none' : '';
  if (chev) chev.classList.toggle('rotated', !isOpen);
}


/* ── Disconnect ────────────────────────── */

async function disconnectAccount(accountId) {
  if (!confirm('Отключить календарь?\nВсе привязки к расписаниям будут удалены.')) return;

  var { error } = await apiFetch('DELETE', '/api/calendar/accounts/' + accountId);
  if (error) {
    showToast('Ошибка: ' + error, 'error');
    return;
  }

  if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
  showToast('Календарь отключён', 'success');
  loadCalendarAccounts();
}


/* ── Helpers ───────────────────────────── */

function providerIcon(provider) {
  if (provider === 'google') {
    return '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09a6.97 6.97 0 0 1 0-4.17V7.07H2.18a11.01 11.01 0 0 0 0 9.86l3.66-2.84z" fill="#FBBC05"/><path d="M12 4.75c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 1.09 14.97 0 12 0 7.7 0 3.99 2.47 2.18 6.07l3.66 2.85c.87-2.6 3.3-4.17 6.16-4.17z" fill="#EA4335"/></svg>';
  }
  if (provider === 'yandex') {
    return '<svg viewBox="0 0 24 24" width="22" height="22"><rect width="24" height="24" rx="4" fill="#FC3F1D"/><text x="12" y="17" text-anchor="middle" fill="#fff" font-size="14" font-weight="700" font-family="Arial">Я</text></svg>';
  }
  if (provider === 'apple') {
    return '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83" fill="#555"/><path d="M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" fill="#555"/></svg>';
  }
  return '<svg viewBox="0 0 24 24" width="22" height="22"><rect x="3" y="4" width="18" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><line x1="3" y1="10" x2="21" y2="10" stroke="currentColor" stroke-width="1.5"/></svg>';
}

function providerName(provider) {
  var names = { google: 'Google Calendar', yandex: 'Яндекс Календарь', apple: 'Apple Calendar', outlook: 'Outlook' };
  return names[provider] || provider;
}


/* ── URL param check (after OAuth redirect) ── */

function checkCalendarConnectParam() {
  var params = new URLSearchParams(window.location.search);
  if (params.get('calendar_connected')) {
    showToast('Календарь подключён!', 'success');
    /* clean URL */
    var url = new URL(window.location);
    url.searchParams.delete('calendar_connected');
    history.replaceState(null, '', url.pathname + url.search);
  }
  if (params.get('calendar_error')) {
    var errMap = {
      cancelled: 'Подключение отменено',
      invalid_state: 'Ошибка авторизации. Попробуйте снова.',
      token_exchange: 'Ошибка получения токена',
      user_not_found: 'Пользователь не найден. Сначала откройте бота.',
      no_code: 'Нет кода авторизации',
    };
    var msg = errMap[params.get('calendar_error')] || 'Ошибка подключения';
    showToast(msg, 'error');
    var url2 = new URL(window.location);
    url2.searchParams.delete('calendar_error');
    history.replaceState(null, '', url2.pathname + url2.search);
  }
}
