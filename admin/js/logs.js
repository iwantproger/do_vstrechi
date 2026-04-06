/* ═══════════════════════════════════════════════════
   LOGS
═══════════════════════════════════════════════════ */
let logsState = { page: 1, perPage: 50, total: 0, filters: {} };
let logTypesPopulated = false;
let filterDebounceTimer = null;

function debounceFilterLogs() {
  clearTimeout(filterDebounceTimer);
  filterDebounceTimer = setTimeout(() => filterLogs(), 400);
}

function filterLogs() {
  logsState.page = 1;
  logsState.filters = {
    severity: document.getElementById('log-f-severity')?.value || '',
    event_type: document.getElementById('log-f-type')?.value || '',
    search: document.getElementById('log-f-search')?.value || '',
    date_from: document.getElementById('log-f-from')?.value || '',
    date_to: document.getElementById('log-f-to')?.value || '',
  };
  loadLogs();
}

function resetLogFilters() {
  ['log-f-severity','log-f-type','log-f-search','log-f-from','log-f-to']
    .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  logsState.filters = {};
  logsState.page = 1;
  loadLogs();
}

function filterBySeverity(sev) {
  document.getElementById('log-f-severity').value = sev;
  filterLogs();
}

function filterByUser(anonymousId) {
  const searchInput = document.getElementById('log-f-search');
  if (searchInput) searchInput.value = anonymousId;
  logsState.filters.anonymous_id = anonymousId;
  logsState.filters.search = '';
  logsState.page = 1;
  loadLogs();
}

async function loadLogs() {
  try {
    const stats = await api('GET', '/api/admin/logs/stats');
    document.getElementById('ls-info').textContent = stats.by_severity?.info || 0;
    document.getElementById('ls-warn').textContent = stats.by_severity?.warn || 0;
    document.getElementById('ls-error').textContent = stats.by_severity?.error || 0;
    document.getElementById('ls-critical').textContent = stats.by_severity?.critical || 0;
    document.getElementById('ls-users').textContent = stats.unique_users || 0;

    // Populate type dropdown once
    const typeSelect = document.getElementById('log-f-type');
    if (typeSelect && !logTypesPopulated && stats.by_type) {
      Object.keys(stats.by_type).sort().forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t + ' (' + stats.by_type[t] + ')';
        typeSelect.appendChild(opt);
      });
      logTypesPopulated = true;
    }

    // Build query
    const params = new URLSearchParams();
    params.set('page', logsState.page);
    params.set('per_page', logsState.perPage);
    const f = logsState.filters;
    if (f.severity) params.set('severity', f.severity);
    if (f.event_type) params.set('event_type', f.event_type);
    if (f.search) params.set('search', f.search);
    if (f.anonymous_id) params.set('anonymous_id', f.anonymous_id);
    if (f.date_from) params.set('date_from', f.date_from);
    if (f.date_to) params.set('date_to', f.date_to);

    const data = await api('GET', '/api/admin/logs?' + params.toString());
    logsState.total = data.total;

    renderLogTable(data.items);
    renderLogPagination(data.total, data.page, data.per_page);
  } catch (err) {
    console.error('Failed to load logs', err);
    showNotification('Ошибка загрузки логов', 'error');
  }
}

function renderLogTable(items) {
  const tbody = document.getElementById('log-tbody');
  const empty = document.getElementById('log-empty');

  if (!items.length) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  const sevIcons = { info: '\u2139\uFE0F', warn: '\u26A0\uFE0F', error: '\u274C', critical: '\uD83D\uDD34' };

  tbody.innerHTML = items.map(ev => {
    const time = new Date(ev.created_at);
    const timeStr = time.toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    const metaStr = ev.metadata ? JSON.stringify(ev.metadata) : '\u2014';
    const sevClass = ['error','critical','warn'].includes(ev.severity) ? 'sev-' + ev.severity : '';

    return '<tr class="' + sevClass + '">'
      + '<td class="time-cell">' + escHtml(timeStr) + '</td>'
      + '<td>' + escHtml(ev.event_type) + '</td>'
      + '<td class="severity-icon">' + (sevIcons[ev.severity] || '\u2022') + '</td>'
      + '<td class="user-id" onclick="filterByUser(\'' + escHtml(ev.anonymous_id) + '\')">' + escHtml(ev.anonymous_id) + '</td>'
      + '<td class="metadata-cell" title="' + escHtml(metaStr) + '">' + escHtml(metaStr) + '</td>'
      + '</tr>';
  }).join('');
}

function renderLogPagination(total, page, perPage) {
  const container = document.getElementById('log-pagination');
  const totalPages = Math.ceil(total / perPage);

  if (totalPages <= 1) {
    container.innerHTML = '<span class="page-info">' + total + ' событий</span>';
    return;
  }

  let html = '';
  if (page > 1) html += '<button onclick="goToLogPage(' + (page - 1) + ')">\u25C0</button>';

  const start = Math.max(1, page - 3);
  const end = Math.min(totalPages, start + 6);

  if (start > 1) html += '<button onclick="goToLogPage(1)">1</button><span>\u2026</span>';

  for (let i = start; i <= end; i++) {
    html += '<button class="' + (i === page ? 'active' : '') + '" onclick="goToLogPage(' + i + ')">' + i + '</button>';
  }

  if (end < totalPages) html += '<span>\u2026</span><button onclick="goToLogPage(' + totalPages + ')">' + totalPages + '</button>';
  if (page < totalPages) html += '<button onclick="goToLogPage(' + (page + 1) + ')">\u25B6</button>';

  html += '<span class="page-info">Показано ' + ((page-1)*perPage+1) + '\u2013' + Math.min(page*perPage, total) + ' из ' + total + '</span>';
  container.innerHTML = html;
}

function goToLogPage(p) {
  logsState.page = p;
  loadLogs();
  document.querySelector('.log-table-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
