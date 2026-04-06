/* ═══════════════════════════════════════════════════
   AUTH
═══════════════════════════════════════════════════ */
async function checkSession() {
  try {
    sessionData = await api('GET', '/api/admin/auth/me');
    showApp();
  } catch {
    showLogin();
  }
}

function onTelegramAuth(user) {
  console.log('[ADMIN AUTH] Telegram callback received, id=' + user.id + ' fields=' + Object.keys(user).join(','));
  const errorEl = document.getElementById('loginError');
  const loadingEl = document.getElementById('loginLoading');
  errorEl.classList.remove('visible');
  loadingEl.classList.add('visible');

  api('POST', '/api/admin/auth/login', user)
    .then(data => {
      console.log('[ADMIN AUTH] Login success');
      loadingEl.classList.remove('visible');
      sessionData = { telegram_id: user.id };
      showApp();
      return api('GET', '/api/admin/auth/me');
    })
    .then(me => { sessionData = me; updateHeaderMeta(); })
    .catch(err => {
      console.error('[ADMIN AUTH] Login failed, status=' + err.status + ' detail=' + err.detail);
      loadingEl.classList.remove('visible');
      if (err.status === 429) {
        errorEl.textContent = 'Слишком много попыток. Подождите.';
      } else {
        errorEl.textContent = 'Доступ запрещён';
      }
      errorEl.classList.add('visible');
    });
}

// Expose globally for Telegram widget callback
window.onTelegramAuth = onTelegramAuth;

async function logout() {
  try { await api('POST', '/api/admin/auth/logout'); } catch {}
  sessionData = null;
  stopDashboardRefresh();
  showLogin();
}

/* ═══════════════════════════════════════════════════
   SCREENS
═══════════════════════════════════════════════════ */
function showLogin() {
  document.getElementById('loginScreen').classList.remove('hidden');
  document.getElementById('app').classList.remove('visible');
  document.getElementById('hamburger').style.display = 'none';
  window.location.hash = '';
}

function showApp() {
  document.getElementById('loginScreen').classList.add('hidden');
  document.getElementById('app').classList.add('visible');
  updateHeaderMeta();
  startDashboardRefresh();

  // Restore page from hash
  const hash = window.location.hash.replace('#', '') || 'dashboard';
  navigateTo(hash);
}

function updateHeaderMeta() {
  const el = document.getElementById('headerMeta');
  if (sessionData && sessionData.expires_at) {
    const exp = new Date(sessionData.expires_at);
    el.textContent = 'Сессия до ' + exp.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
}

/* ═══════════════════════════════════════════════════
   NAVIGATION
═══════════════════════════════════════════════════ */
function navigateTo(page) {
  if (!PAGE_TITLES[page]) page = 'dashboard';
  window.location.hash = page;

  // Update sidebar
  document.querySelectorAll('.nav-item[data-page]').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });

  // Update pages
  document.querySelectorAll('.page').forEach(el => {
    el.classList.remove('active');
  });
  const pageEl = document.getElementById('page-' + page);
  if (pageEl) {
    pageEl.classList.add('active');
    // Re-trigger fade animation
    const card = pageEl.querySelector('.fade-in');
    if (card) {
      card.style.animation = 'none';
      card.offsetHeight; // force reflow
      card.style.animation = '';
    }
  }

  // Update header
  document.getElementById('pageTitle').textContent = PAGE_TITLES[page] || page;

  // Load page data
  if (page === 'dashboard') loadDashboard();
  if (page === 'logs') loadLogs();
  if (page === 'tasks') loadTasks();
  if (page === 'settings') loadSettings();

  // Close mobile sidebar
  closeSidebar();
}

// Hash change listener
window.addEventListener('hashchange', () => {
  if (!document.getElementById('app').classList.contains('visible')) return;
  const page = window.location.hash.replace('#', '') || 'dashboard';
  navigateTo(page);
});

/* ═══════════════════════════════════════════════════
   MOBILE SIDEBAR
═══════════════════════════════════════════════════ */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const btn = document.getElementById('hamburger');
  const isOpen = sidebar.classList.toggle('open');
  overlay.classList.toggle('open', isOpen);
  btn.classList.toggle('open', isOpen);
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
  document.getElementById('hamburger').classList.remove('open');
}

document.getElementById('hamburger').addEventListener('click', toggleSidebar);
document.getElementById('sidebarOverlay').addEventListener('click', closeSidebar);

/* ═══════════════════════════════════════════════════
   TELEGRAM WIDGET LOADER
═══════════════════════════════════════════════════ */
function loadTelegramWidget() {
  const container = document.getElementById('loginWidget');
  const script = document.createElement('script');
  script.src = 'https://telegram.org/js/telegram-widget.js?22';
  script.async = true;
  script.setAttribute('data-telegram-login', 'do_vstrechi_bot');
  script.setAttribute('data-size', 'large');
  script.setAttribute('data-radius', '8');
  script.setAttribute('data-onauth', 'onTelegramAuth(user)');
  script.setAttribute('data-request-access', 'write');

  script.onload = () => { widgetLoaded = true; };
  script.onerror = () => {
    document.getElementById('widgetFallback').classList.add('visible');
  };

  container.insertBefore(script, container.firstChild);

  // Fallback timeout — if widget iframe doesn't appear in 5s
  setTimeout(() => {
    if (!widgetLoaded && !container.querySelector('iframe')) {
      document.getElementById('widgetFallback').classList.add('visible');
    }
  }, 5000);
}
