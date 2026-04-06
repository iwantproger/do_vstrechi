/* ═══════════════════════════════════════════
   API
═══════════════════════════════════════════ */
async function apiFetch(method, path, body = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (tg?.initData) opts.headers['X-Init-Data'] = tg.initData;
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(BACKEND + path, opts);
    if (res.status === 401) {
      showToast('Ошибка авторизации. Перезапустите приложение.', 'error');
      return { data: null, error: 'auth' };
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return { data: null, error: data.detail || 'HTTP ' + res.status };
    return { data, error: null };
  } catch (e) {
    return { data: null, error: e.message };
  }
}

/* ═══════════════════════════════════════════
   AUTH
═══════════════════════════════════════════ */
async function authUser() {
  const u = tg?.initDataUnsafe?.user;
  if (!u) {
    setHomeSubtitle('Откройте приложение через Telegram', true);
    return;
  }
  const { data, error } = await apiFetch('POST', '/api/users/auth', {
    telegram_id: u.id,
    first_name: u.first_name,
    last_name: u.last_name || '',
    username: u.username || '',
    timezone: userTimezone,
  });
  if (data) {
    state.user = data;
  } else {
    setHomeSubtitle('Ошибка авторизации' + (error ? ': ' + error : ''), true);
  }
}

