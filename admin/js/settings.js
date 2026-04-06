/* ═══════════════════════════════════════════════════
   SETTINGS
═══════════════════════════════════════════════════ */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

async function loadSettings() {
  try {
    const [sysInfo, auditLog] = await Promise.all([
      api('GET', '/api/admin/system/info'),
      api('GET', '/api/admin/audit-log?per_page=10'),
    ]);
    renderSystemInfo(sysInfo);
    renderAuditMini(auditLog.items || []);
  } catch (err) {
    console.error('Settings load failed', err);
    showNotification('Ошибка загрузки настроек', 'error');
  }
}

function renderSystemInfo(info) {
  const secs = info.uptime_seconds || 0;
  const days = Math.floor(secs / 86400);
  const hours = Math.floor((secs % 86400) / 3600);
  const mins = Math.floor((secs % 3600) / 60);
  const uptime = days > 0 ? days + 'д ' + hours + 'ч ' + mins + 'м'
                           : hours + 'ч ' + mins + 'м';

  setText('si-version', info.version || '—');
  setText('si-python', info.python_version || '—');
  setText('si-uptime', uptime);
  setText('si-pool', (info.database?.pool_free || 0) + '/' + (info.database?.pool_size || 0) + ' free');
  setText('si-tables', info.database?.tables_count ?? '—');
  setText('si-events', (info.counts?.events_total || 0).toLocaleString('ru-RU'));

  setText('si-ip-allowlist', info.environment?.admin_ip_allowlist || 'не задан');
  setText('si-cors', (info.environment?.cors_origins || []).join(', '));
  setText('si-rate-limits', info.environment?.rate_limits || '—');

  setText('si-users', info.counts?.users ?? '—');
  setText('si-schedules', info.counts?.schedules_active ?? '—');
  setText('si-bookings', info.counts?.bookings_total ?? '—');
  setText('si-tasks', info.counts?.tasks_total ?? '—');
}

function renderAuditMini(items) {
  const container = document.getElementById('audit-mini-list');
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div style="color:var(--text-muted);padding:12px;">Нет записей</div>';
    return;
  }
  container.innerHTML = items.map(function(a) {
    const t = new Date(a.created_at);
    const timeStr = t.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    const dateStr = t.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
    return '<div class="audit-mini-item">'
      + '<span class="time">' + escHtml(dateStr) + ' ' + escHtml(timeStr) + '</span>'
      + '<span class="action">' + escHtml(a.action) + '</span>'
      + '<span>' + escHtml(a.ip_address || '') + '</span>'
      + '</div>';
  }).join('');
}

async function invalidateAllSessions() {
  if (!confirm('Сбросить все сессии кроме текущей?\nПотребуется повторный вход на других устройствах.')) return;
  try {
    const result = await api('POST', '/api/admin/sessions/invalidate-all');
    showNotification('Сброшено сессий: ' + result.invalidated, 'success');
  } catch (err) {
    showNotification('Ошибка сброса сессий', 'error');
  }
}

async function cleanupEvents() {
  const days = parseInt(document.getElementById('cleanup-days')?.value || '30', 10);
  if (!confirm('Удалить info-события старше ' + days + ' дней?\nЭто действие нельзя отменить.')) return;
  try {
    const result = await api('POST', '/api/admin/maintenance/cleanup-events', {
      older_than_days: days,
      severity: 'info',
    });
    showNotification('Удалено событий: ' + result.deleted, 'success');
    loadSettings();
  } catch (err) {
    showNotification('Ошибка очистки', 'error');
  }
}
