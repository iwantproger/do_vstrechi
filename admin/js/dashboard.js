/* ═══════════════════════════════════════════════════
   CHART.JS GLOBAL DEFAULTS
═══════════════════════════════════════════════════ */
Chart.defaults.font.family = "'DM Sans', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#94A3B8';
Chart.defaults.plugins.legend.display = false;
Chart.defaults.elements.line.borderWidth = 2;
Chart.defaults.elements.line.tension = 0.35;
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 5;
Chart.defaults.elements.bar.borderRadius = 6;
Chart.defaults.plugins.tooltip.backgroundColor = '#0F172A';
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.tooltip.displayColors = false;

/* ═══════════════════════════════════════════════════
   STATE
═══════════════════════════════════════════════════ */
let currentTab = 'overview';
let currentDays = 30;
let chartTrend = null;
let chartPlatforms = null;
let chartWeekday = null;
let chartRegistrations = null;
let chartTTV = null;
let dashboardInterval = null;

/* ═══════════════════════════════════════════════════
   ENTRY POINT
═══════════════════════════════════════════════════ */
async function loadDashboard() {
  switchTab(currentTab);
}

function refreshDashboard() {
  loadTabData(currentTab);
}

/* ═══════════════════════════════════════════════════
   TABS
═══════════════════════════════════════════════════ */
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.dashboard-tabs .tab-btn').forEach(function(t) {
    t.classList.toggle('active', t.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-content').forEach(function(s) {
    s.style.display = s.dataset.tab === tab ? 'block' : 'none';
  });
  loadTabData(tab);
}

function setPeriod(days) {
  currentDays = days;
  document.querySelectorAll('.period-filter .pf-btn').forEach(function(b) {
    b.classList.toggle('active', parseInt(b.dataset.days) === days);
  });
  var label = document.getElementById('period-label');
  if (label) label.textContent = days + ' дней';
  loadTabData(currentTab);
}

async function loadTabData(tab) {
  switch (tab) {
    case 'overview': await loadOverview(); break;
    case 'activation': await loadActivation(); break;
    case 'guest-funnel': await loadGuestFunnel(); break;
    case 'retention': await loadRetentionTab(); break;
    case 'quality': await loadQuality(); break;
    case 'system': await loadSystem(); break;
  }
}

/* ═══════════════════════════════════════════════════
   TAB: OVERVIEW
═══════════════════════════════════════════════════ */
async function loadOverview() {
  showDashboardLoading(true);
  try {
    var summary = await api('GET', '/api/admin/dashboard/summary');
    updateMetric('m-total-users', summary.total_users);
    updateMetric('m-active-users', summary.active_users_7d);
    updateMetric('m-total-bookings', summary.total_bookings);
    updateMetric('m-bookings-today', summary.bookings_today);
    updateMetric('m-pending', summary.pending_bookings, summary.pending_bookings > 0 ? 'warning' : '');
    updateMetric('m-errors', summary.errors_24h, summary.errors_24h > 0 ? 'danger' : 'success');
  } catch (e) { console.error('Summary failed', e); }
  showDashboardLoading(false);

  try {
    var trend = await api('GET', '/api/admin/dashboard/bookings-trend?days=' + currentDays);
    renderTrendChart(trend);
    renderWeekdayChart(trend);
  } catch (e) { console.error('Trend failed', e); }

  try {
    var reg = await api('GET', '/api/admin/analytics/registrations-trend?days=' + currentDays);
    renderRegistrationsTrend(reg);
  } catch (e) { console.error('Registrations failed', e); }

  try {
    var funnel = await api('GET', '/api/admin/analytics/funnel');
    renderFunnelChart(funnel);
  } catch (e) { setAnalyticsError('funnel-chart'); }

  try {
    var platforms = await api('GET', '/api/admin/dashboard/platforms');
    renderPlatformsChart(platforms);
  } catch (e) { console.error('Platforms failed', e); }

  // Prod launch date
  try {
    var sysInfo = await api('GET', '/api/admin/system/info');
    if (sysInfo && sysInfo.prod_launch_date) {
      var noteEl = document.getElementById('stats-note');
      if (noteEl) {
        var parts = sysInfo.prod_launch_date.split('-');
        noteEl.textContent = 'С ' + parts[2] + '.' + parts[1] + '.' + parts[0] + ' \u00B7 без аккаунта владельца';
      }
    }
  } catch (e) {}
}

/* ═══════════════════════════════════════════════════
   TAB: ACTIVATION
═══════════════════════════════════════════════════ */
async function loadActivation() {
  var container = document.getElementById('tab-activation-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Загрузка...</p>';
  try {
    var data = await api('GET', '/api/admin/analytics/activation');
    var ttv = await api('GET', '/api/admin/analytics/time-to-value');
    var html = '<div class="metrics-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:24px">';
    html += metricCard(formatDuration(data.ttfv_organizer?.median_hours), 'TTFV медиана', 'До первого бронирования');
    html += metricCard((data.activation_rate?.rate || 0).toFixed(1) + '%', 'Activation rate',
      (data.activation_rate?.activated || 0) + ' из ' + (data.activation_rate?.total || 0),
      data.activation_rate?.rate < 20 ? 'danger' : '');
    html += metricCard(formatDuration(ttv?.median_hours), 'TTV медиана', 'Время до ценности');
    html += '</div>';
    // Distribution
    if (ttv && ttv.distribution) {
      html += '<div class="chart-card"><h3>Распределение TTV</h3><canvas id="chart-ttv-act"></canvas></div>';
    }
    container.innerHTML = html;
    if (ttv && ttv.distribution) renderTTVChartIn('chart-ttv-act', ttv.distribution);
  } catch (e) {
    container.innerHTML = '<div class="section-error">Ошибка загрузки</div>';
  }
}

/* ═══════════════════════════════════════════════════
   TAB: GUEST FUNNEL
═══════════════════════════════════════════════════ */
async function loadGuestFunnel() {
  var container = document.getElementById('tab-guest-funnel-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Загрузка...</p>';
  try {
    var data = await api('GET', '/api/admin/analytics/guest-funnel?days=' + currentDays);
    if (!data.steps || !data.steps.length || data.steps[0].count === 0) {
      container.innerHTML = '<div class="empty-analytics">Данные воронки появятся когда гости начнут открывать расписания.<br><span style="font-size:12px;color:var(--text-tertiary)">Трекинг: schedule_viewed → booking_success</span></div>';
      return;
    }
    var maxCount = data.steps[0].count;
    var html = '<div style="font-size:14px;margin-bottom:20px">Конверсия: <strong style="color:var(--primary);font-size:18px">' + (data.conversion_rate || 0).toFixed(1) + '%</strong></div>';
    data.steps.forEach(function(step, i) {
      var width = maxCount > 0 ? (step.count / maxCount * 100) : 0;
      if (i > 0 && data.steps[i-1].count > 0) {
        var drop = Math.round((1 - step.count / data.steps[i-1].count) * 100);
        if (drop > 0) html += '<div style="text-align:center;font-size:11px;color:var(--danger);padding:2px 0;font-weight:500">\u2193 \u2212' + drop + '% отсев</div>';
      }
      html += '<div class="funnel-step"><div class="funnel-label"><span>' + escHtml(step.name) + '</span><span class="funnel-numbers">' + step.count + '</span></div>';
      html += '<div class="funnel-bar-bg"><div class="funnel-bar" style="width:' + width + '%"></div></div></div>';
    });
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="section-error">Ошибка загрузки</div>';
  }
}

/* ═══════════════════════════════════════════════════
   TAB: RETENTION
═══════════════════════════════════════════════════ */
async function loadRetentionTab() {
  var container = document.getElementById('tab-retention-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Загрузка...</p>';
  try {
    var data = await api('GET', '/api/admin/analytics/retention?period=day7');
    var growth = await api('GET', '/api/admin/analytics/growth');
    var html = '<div class="metrics-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:24px">';
    html += metricCard((data.overall_rate || 0) + '%', 'Day 7 Retention', '');
    html += metricCard((growth?.wau || 0).toString(), 'WAU', 'Активных за неделю');
    html += metricCard(growth?.wau_mau_ratio ? growth.wau_mau_ratio + '%' : '—', 'WAU/MAU', 'Вовлечённость');
    html += '</div>';
    html += '<div class="retention-periods" style="margin-bottom:16px">';
    html += '<button class="period-btn" onclick="loadRetention(\'day1\')">Day 1</button>';
    html += '<button class="period-btn active" onclick="loadRetention(\'day7\')">Day 7</button>';
    html += '<button class="period-btn" onclick="loadRetention(\'day30\')">Day 30</button></div>';
    html += '<div id="retention-chart"></div>';
    container.innerHTML = html;
    renderRetentionTable(data);
  } catch (e) {
    container.innerHTML = '<div class="section-error">Ошибка загрузки</div>';
  }
}

/* ═══════════════════════════════════════════════════
   TAB: QUALITY
═══════════════════════════════════════════════════ */
async function loadQuality() {
  var container = document.getElementById('tab-quality-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Загрузка...</p>';
  try {
    var data = await api('GET', '/api/admin/analytics/quality');
    var cancel = await api('GET', '/api/admin/analytics/cancellations?days=' + currentDays);
    var notif = await api('GET', '/api/admin/analytics/notifications?days=1');
    var html = '<div class="metrics-grid" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));margin-bottom:24px">';
    html += metricCard((data.pending_timeout_rate || 0).toFixed(1) + '%', 'Pending timeout', 'Цель: < 20%', data.pending_timeout_rate > 20 ? 'warning' : '');
    html += metricCard((cancel?.total_cancelled?.rate || 0).toFixed(1) + '%', 'Отмены всего', (cancel?.total_cancelled?.count || 0) + ' букингов');
    html += metricCard((cancel?.by_guest?.rate || 0).toFixed(1) + '%', 'Отмены гостем', '');
    html += metricCard((cancel?.by_organizer?.rate || 0).toFixed(1) + '%', 'Отмены орг-ром', '');
    html += metricCard((data.error_per_1000_bookings || 0).toFixed(1), 'Ошибок / 1K', 'Цель: < 5', data.error_per_1000_bookings > 5 ? 'danger' : '');
    html += metricCard((data.avg_meetings_per_organizer || 0).toFixed(1), 'Встреч / орг-р', 'Больше = лучше');
    html += metricCard((notif?.overall_delivery_rate || 100).toFixed(0) + '%', 'Доставка уведомлений', (notif?.failed_total || 0) + ' сбоев');
    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="section-error">Ошибка загрузки</div>';
  }
}

/* ═══════════════════════════════════════════════════
   TAB: SYSTEM
═══════════════════════════════════════════════════ */
async function loadSystem() {
  var container = document.getElementById('tab-system-content');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted)">Загрузка...</p>';
  try {
    var [pool, uptime, latency, inlineData, operational] = await Promise.all([
      api('GET', '/api/admin/analytics/db-pool').catch(function() { return null; }),
      api('GET', '/api/admin/analytics/bot-uptime').catch(function() { return null; }),
      api('GET', '/api/admin/analytics/api-latency').catch(function() { return null; }),
      api('GET', '/api/admin/analytics/inline-usage?days=' + currentDays).catch(function() { return null; }),
      api('GET', '/api/admin/analytics/operational').catch(function() { return null; }),
    ]);
    var html = '<div class="metrics-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr));margin-bottom:24px">';
    // Bot status
    if (uptime) {
      var dotColor = uptime.status === 'online' ? 'var(--success)' : (uptime.status === 'degraded' ? 'var(--warning)' : 'var(--danger)');
      html += '<div class="metric-card"><div class="metric-value" style="display:flex;align-items:center;gap:8px"><span style="width:8px;height:8px;border-radius:50%;background:' + dotColor + ';display:inline-block"></span>' + escHtml(uptime.status) + '</div><div class="metric-label">Bot ' + (uptime.uptime_percent || 0) + '% uptime</div></div>';
    }
    // Pool
    if (pool) {
      html += metricCard(pool.used + '/' + pool.max, 'DB Pool', pool.usage_percent + '% занят');
    }
    // Events 24h
    if (operational) {
      html += metricCard(operational.events_24h?.total || 0, 'Events 24ч', (operational.events_24h?.errors || 0) + ' ошибок');
    }
    // Inline
    if (inlineData) {
      html += metricCard(inlineData.total_queries || 0, 'Inline запросов', (inlineData.unique_users || 0) + ' юзеров');
    }
    html += '</div>';

    // API Latency table
    if (latency && latency.endpoints && latency.endpoints.length) {
      html += '<div class="chart-card"><h3>API Latency (24ч)</h3><table class="log-table" style="font-size:12px"><thead><tr><th>Path</th><th>p50</th><th>p95</th><th>p99</th><th>Req</th></tr></thead><tbody>';
      latency.endpoints.forEach(function(e) {
        html += '<tr><td style="font-family:var(--font-mono);font-size:11px">' + escHtml(e.path) + '</td>';
        html += '<td>' + Math.round(e.p50) + 'ms</td>';
        html += '<td style="' + (e.p95 > 500 ? 'color:var(--danger)' : '') + '">' + Math.round(e.p95) + 'ms</td>';
        html += '<td>' + Math.round(e.p99) + 'ms</td>';
        html += '<td>' + e.count + '</td></tr>';
      });
      html += '</tbody></table></div>';
    } else {
      html += '<div class="chart-card"><h3>API Latency</h3><div class="empty-analytics">Данные появятся после первых запросов к API</div></div>';
    }
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="section-error">Ошибка загрузки</div>';
  }
}

/* ═══════════════════════════════════════════════════
   SHARED HELPERS
═══════════════════════════════════════════════════ */
function metricCard(value, label, hint, modifier) {
  var cls = 'metric-card' + (modifier ? ' ' + modifier : '');
  var hintHtml = hint ? '<div class="metric-hint">' + escHtml(hint) + '</div>' : '';
  return '<div class="' + cls + '"><div class="metric-value">' + escHtml(String(value)) + '</div><div class="metric-label">' + escHtml(label) + '</div>' + hintHtml + '</div>';
}

function updateMetric(elementId, value, modifier) {
  var el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = typeof value === 'number' ? value.toLocaleString('ru-RU') : value;
  el.classList.remove('loading');
  var card = el.closest('.metric-card');
  if (card) {
    card.classList.remove('danger', 'warning', 'success');
    if (modifier) card.classList.add(modifier);
  }
}

function setAnalyticsError(elementId) {
  var el = document.getElementById(elementId);
  if (el) el.innerHTML = '<div class="section-error">Ошибка загрузки</div>';
}

function showDashboardLoading(show) {
  document.querySelectorAll('#tab-overview .metric-value').forEach(function(el) {
    if (show) { el.textContent = ''; el.classList.add('loading'); }
  });
}

function formatDuration(hours) {
  if (hours == null || isNaN(hours)) return '\u2014';
  var totalSeconds = Math.round(hours * 3600);
  var d = Math.floor(totalSeconds / 86400);
  var h = Math.floor((totalSeconds % 86400) / 3600);
  var m = Math.floor((totalSeconds % 3600) / 60);
  var s = totalSeconds % 60;
  if (d > 0) return d + 'д ' + h + 'ч ' + m + 'м';
  if (h > 0) return h + 'ч ' + m + 'м ' + s + 'с';
  if (m > 0) return m + 'м ' + s + 'с';
  return s + 'с';
}

/* ═══════════════════════════════════════════════════
   CHART RENDERERS
═══════════════════════════════════════════════════ */
function renderTrendChart(data) {
  var ctx = document.getElementById('chart-bookings-trend');
  if (!ctx) return;
  if (chartTrend) chartTrend.destroy();
  chartTrend = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(function(d) { return new Date(d.date).toLocaleDateString('ru-RU', {day:'numeric',month:'short'}); }),
      datasets: [{ data: data.map(function(d) { return d.count; }), borderColor: '#0D9488', backgroundColor: 'rgba(13,148,136,0.06)', fill: true }]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
  });
}

function renderPlatformsChart(data) {
  var ctx = document.getElementById('chart-platforms');
  if (!ctx) return;
  if (chartPlatforms) chartPlatforms.destroy();
  if (!data || !data.length) return;
  var colors = { jitsi: '#0D9488', zoom: '#2D8CFF', google_meet: '#00897B', other: '#94A3B8', offline: '#64748B' };
  chartPlatforms = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(function(d) { return d.platform; }),
      datasets: [{ data: data.map(function(d) { return d.count; }), backgroundColor: data.map(function(d) { return colors[d.platform] || '#94A3B8'; }), borderWidth: 0 }]
    },
    options: { responsive: true, cutout: '60%', plugins: { legend: { display: true, position: 'bottom' } } }
  });
}

function renderWeekdayChart(trendData) {
  var ctx = document.getElementById('chart-weekday');
  if (!ctx) return;
  if (chartWeekday) chartWeekday.destroy();
  var weekdays = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
  var counts = [0,0,0,0,0,0,0];
  trendData.forEach(function(d) { var day = new Date(d.date).getDay(); counts[day === 0 ? 6 : day - 1] += d.count; });
  chartWeekday = new Chart(ctx, {
    type: 'bar',
    data: { labels: weekdays, datasets: [{ data: counts, backgroundColor: counts.map(function(_,i) { return i < 5 ? '#0D9488' : '#94A3B8'; }) }] },
    options: { responsive: true, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
  });
}

function renderRegistrationsTrend(data) {
  var ctx = document.getElementById('chart-registrations');
  if (!ctx) return;
  if (chartRegistrations) chartRegistrations.destroy();
  if (!data || !data.length) return;
  chartRegistrations = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(function(d) { return new Date(d.date).toLocaleDateString('ru-RU', {day:'numeric',month:'short'}); }),
      datasets: [{ data: data.map(function(d) { return d.count; }), borderColor: '#6366F1', backgroundColor: 'rgba(99,102,241,0.06)', fill: true }]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
  });
}

function renderFunnelChart(data) {
  var container = document.getElementById('funnel-chart');
  if (!container) return;
  if (!data || !data.steps || !data.steps.length) { container.innerHTML = '<div class="empty-analytics">Нет данных</div>'; return; }
  var maxCount = data.steps[0].count || 1;
  var colors = ['#0D9488', '#14B8A6', '#10B981'];
  container.innerHTML = data.steps.map(function(step, i) {
    var width = maxCount > 0 ? (step.count / maxCount * 100) : 0;
    return '<div class="funnel-step"><div class="funnel-label"><span>' + escHtml(step.name) + '</span><span class="funnel-numbers">' + step.count + ' (' + step.percent + '%)</span></div><div class="funnel-bar-bg"><div class="funnel-bar" style="width:' + width + '%;background:' + colors[i % 3] + '"></div></div></div>';
  }).join('');
}

function renderRetentionTable(data) {
  var container = document.getElementById('retention-chart');
  if (!container) return;
  if (!data) { container.innerHTML = '<div class="empty-analytics">Нет данных</div>'; return; }
  var periodLabel = (data.period || 'day7').replace('day', '');
  var html = '<div class="retention-overall"><span class="retention-rate">' + (data.overall_rate || 0) + '%</span><span class="retention-label">Day ' + escHtml(periodLabel) + ' retention</span></div>';
  if (data.cohorts && data.cohorts.length) {
    html += '<table class="retention-table"><thead><tr><th>Когорта</th><th>Размер</th><th>Верн.</th><th>Rate</th></tr></thead><tbody>';
    data.cohorts.forEach(function(c) {
      var bg = c.rate > 30 ? 'var(--success)' : c.rate > 10 ? 'var(--warning)' : 'var(--danger)';
      html += '<tr><td>' + escHtml(c.date) + '</td><td>' + c.cohort_size + '</td><td>' + c.retained + '</td><td><span class="retention-badge" style="background:' + bg + '">' + c.rate + '%</span></td></tr>';
    });
    html += '</tbody></table>';
  }
  container.innerHTML = html;
}

async function loadRetention(period) {
  document.querySelectorAll('.retention-periods .period-btn').forEach(function(b) { b.classList.remove('active'); });
  if (event && event.target) event.target.classList.add('active');
  try {
    var data = await api('GET', '/api/admin/analytics/retention?period=' + period);
    renderRetentionTable(data);
  } catch (e) { console.error('Retention error', e); }
}

function renderTTVChartIn(canvasId, distribution) {
  var ctx = document.getElementById(canvasId);
  if (!ctx || !distribution) return;
  var barColors = ['#10B981', '#14B8A6', '#0D9488', '#F59E0B', '#EF4444'];
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: distribution.map(function(d) { return d.bucket; }),
      datasets: [{ data: distribution.map(function(d) { return d.count; }), backgroundColor: distribution.map(function(_,i) { return barColors[Math.min(i, 4)]; }) }]
    },
    options: { responsive: true, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
  });
}

/* ═══════════════════════════════════════════════════
   DASHBOARD SETTINGS (localStorage)
═══════════════════════════════════════════════════ */
function openDashboardSettings() {
  document.getElementById('dashboard-settings-modal').style.display = 'flex';
}
function closeDashboardSettings(ev) {
  if (ev && ev.target !== ev.currentTarget) return;
  document.getElementById('dashboard-settings-modal').style.display = 'none';
}

/* ═══════════════════════════════════════════════════
   AUTO REFRESH
═══════════════════════════════════════════════════ */
function startDashboardRefresh() {
  stopDashboardRefresh();
  dashboardInterval = setInterval(function() {
    var cur = window.location.hash.replace('#', '') || 'dashboard';
    if (cur === 'dashboard') loadTabData(currentTab);
  }, 60000);
}

function stopDashboardRefresh() {
  if (dashboardInterval) { clearInterval(dashboardInterval); dashboardInterval = null; }
}
