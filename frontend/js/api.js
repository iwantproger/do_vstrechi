/* ═══════════════════════════════════════════
   API
═══════════════════════════════════════════ */

/* In-memory GET cache (TTL 30s). Invalidated on POST/PATCH/DELETE.
   Cacheable prefixes — hot, frequently re-read endpoints. */
const _API_CACHE = new Map();
const _API_CACHE_TTL_MS = 30000;
const _API_CACHEABLE = ['/api/schedules', '/api/stats', '/api/bookings'];

function _apiCacheable(path) {
  /* Exclude query-sensitive sub-resources where freshness matters */
  if (path.indexOf('/pending-reminders') >= 0) return false;
  if (path.indexOf('/confirmation-requests') >= 0) return false;
  if (path.indexOf('/no-answer-candidates') >= 0) return false;
  for (var i = 0; i < _API_CACHEABLE.length; i++) {
    if (path.indexOf(_API_CACHEABLE[i]) === 0) return true;
  }
  return false;
}

function invalidateApiCache(prefix) {
  if (!prefix) { _API_CACHE.clear(); return; }
  _API_CACHE.forEach(function(_, k) {
    if (k.indexOf(prefix) === 0) _API_CACHE.delete(k);
  });
}

async function apiFetch(method, path, body = null) {
  const isGet = method === 'GET';
  const cacheKey = isGet ? path : null;

  if (isGet && _apiCacheable(path)) {
    const hit = _API_CACHE.get(cacheKey);
    if (hit && (Date.now() - hit.t) < _API_CACHE_TTL_MS) {
      return { data: hit.d, error: null };
    }
  }

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

    if (isGet && _apiCacheable(path)) {
      _API_CACHE.set(cacheKey, { t: Date.now(), d: data });
    } else if (!isGet) {
      /* Any write invalidates all cacheable prefixes — simple and safe */
      _API_CACHE.clear();
    }

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
