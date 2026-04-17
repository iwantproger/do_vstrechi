/* ═══════════════════════════════════════════════════
   DASHBOARD
═══════════════════════════════════════════════════ */
let chartTrend = null;
let chartPlatforms = null;
let chartWeekday = null;
let chartRegistrations = null;
let chartTTV = null;
let dashboardInterval = null;

async function loadDashboard() {
  showDashboardLoading(true);
  try {
    const [summary, trend, platforms] = await Promise.all([
      api('GET', '/api/admin/dashboard/summary'),
      api('GET', '/api/admin/dashboard/bookings-trend?days=30'),
      api('GET', '/api/admin/dashboard/platforms'),
    ]);

    updateMetric('m-total-users', summary.total_users);
    updateMetric('m-active-users', summary.active_users_7d);
    updateMetric('m-total-bookings', summary.total_bookings);
    updateMetric('m-bookings-today', summary.bookings_today);
    updateMetric('m-pending', summary.pending_bookings, summary.pending_bookings > 0 ? 'warning' : '');
    updateMetric('m-errors', summary.errors_24h, summary.errors_24h > 0 ? 'danger' : 'success');

    renderTrendChart(trend);
    renderPlatformsChart(platforms);
    renderWeekdayChart(trend);

    const now = new Date();
    document.getElementById('dashboard-updated').textContent =
      'Обновлено: ' + now.toLocaleTimeString('ru-RU');
  } catch (err) {
    console.error('Dashboard load failed', err);
    showNotification('Ошибка загрузки дашборда', 'error');
  } finally {
    showDashboardLoading(false);
  }

  // Analytics — Promise.allSettled so one failure doesn't block others
  var results = await Promise.allSettled([
    api('GET', '/api/admin/analytics/funnel'),
    api('GET', '/api/admin/analytics/retention?period=day7'),
    api('GET', '/api/admin/analytics/organizer-stats'),
    api('GET', '/api/admin/analytics/registrations-trend?days=30'),
    api('GET', '/api/admin/analytics/time-to-value'),
  ]);

  var val = function(i) { return results[i].status === 'fulfilled' ? results[i].value : null; };

  if (val(0)) renderFunnelChart(val(0));
  else setAnalyticsError('funnel-chart');
  if (val(1)) renderRetentionTable(val(1));
  else setAnalyticsError('retention-chart');
  if (val(2)) renderOrganizerTable(val(2));
  else setAnalyticsError('organizer-table');
  if (val(3)) renderRegistrationsTrend(val(3));
  if (val(4)) renderTTVChart(val(4));

  results.forEach(function(r, i) {
    if (r.status === 'rejected') console.error('Analytics endpoint ' + i + ' failed', r.reason);
  });
}

function updateMetric(elementId, value, modifier) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = typeof value === 'number' ? value.toLocaleString('ru-RU') : value;
  el.classList.remove('loading');
  const card = el.closest('.metric-card');
  if (card) {
    card.classList.remove('danger', 'warning', 'success');
    if (modifier) card.classList.add(modifier);
  }
}

function setAnalyticsError(elementId) {
  var el = document.getElementById(elementId);
  if (el) el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--danger);font-size:13px">Ошибка загрузки</div>';
}

function showDashboardLoading(show) {
  document.querySelectorAll('#page-dashboard .metric-value').forEach(el => {
    if (show) { el.textContent = ''; el.classList.add('loading'); }
  });
}

function renderTrendChart(data) {
  const ctx = document.getElementById('chart-bookings-trend');
  if (!ctx) return;
  if (chartTrend) chartTrend.destroy();

  const labels = data.map(d => {
    const dt = new Date(d.date);
    return dt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  });
  const values = data.map(d => d.count);

  chartTrend = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Бронирования',
        data: values,
        borderColor: '#0D9488',
        backgroundColor: 'rgba(13,148,136,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 3,
        pointHoverRadius: 6,
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0F172A',
          titleFont: { family: 'Inter' },
          bodyFont: { family: 'Inter' },
          callbacks: {
            title: (items) => data[items[0].dataIndex]?.date || '',
            label: (item) => item.raw + ' бронирований',
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 11, family: 'Inter' }, color: '#94A3B8', maxTicksLimit: 10 }
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 11, family: 'Inter' }, color: '#94A3B8', stepSize: 1 },
          grid: { color: '#F1F5F9' }
        }
      }
    }
  });
}

function renderPlatformsChart(data) {
  const ctx = document.getElementById('chart-platforms');
  if (!ctx) return;
  if (chartPlatforms) chartPlatforms.destroy();

  // Remove previous "no data" message if any
  const prev = ctx.parentElement.querySelector('.chart-empty');
  if (prev) prev.remove();

  if (!data.length) {
    const p = document.createElement('p');
    p.className = 'chart-empty';
    p.textContent = 'Нет данных';
    ctx.parentElement.appendChild(p);
    ctx.style.display = 'none';
    return;
  }
  ctx.style.display = '';

  const colors = { jitsi: '#0D9488', zoom: '#2D8CFF', google_meet: '#00897B', other: '#94A3B8' };

  chartPlatforms = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.platform.charAt(0).toUpperCase() + d.platform.slice(1)),
      datasets: [{
        data: data.map(d => d.count),
        backgroundColor: data.map(d => colors[d.platform] || colors.other),
        borderWidth: 0,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '60%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { font: { size: 12, family: 'Inter' }, padding: 16, usePointStyle: true }
        }
      }
    }
  });
}

function renderWeekdayChart(trendData) {
  const ctx = document.getElementById('chart-weekday');
  if (!ctx) return;
  if (chartWeekday) chartWeekday.destroy();

  const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
  const counts = new Array(7).fill(0);
  trendData.forEach(d => {
    const day = new Date(d.date).getDay(); // 0=Sun
    const idx = day === 0 ? 6 : day - 1;
    counts[idx] += d.count;
  });

  chartWeekday = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: weekdays,
      datasets: [{
        label: 'Бронирования',
        data: counts,
        backgroundColor: counts.map((_, i) => i < 5 ? '#0D9488' : '#94A3B8'),
        borderRadius: 6,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 12, family: 'Inter' }, color: '#94A3B8' }
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 11, family: 'Inter' }, color: '#94A3B8', stepSize: 1 },
          grid: { color: '#F1F5F9' }
        }
      }
    }
  });
}

/* ═══════════════════════════════════════════════════
   ANALYTICS: Funnel
═══════════════════════════════════════════════════ */
function renderFunnelChart(data) {
  var container = document.getElementById('funnel-chart');
  if (!container) return;
  if (!data || !data.steps || !data.steps.length) {
    container.innerHTML = '<p style="color:var(--text-muted)">Нет данных</p>';
    return;
  }
  var maxCount = data.steps[0].count || 1;
  var colors = ['#0D9488', '#14B8A6', '#10B981'];
  container.innerHTML = data.steps.map(function(step, i) {
    var width = maxCount > 0 ? (step.count / maxCount * 100) : 0;
    return '<div class="funnel-step">'
      + '<div class="funnel-label"><span>' + escHtml(step.name) + '</span>'
      + '<span class="funnel-numbers">' + step.count + ' (' + step.percent + '%)</span></div>'
      + '<div class="funnel-bar-bg"><div class="funnel-bar" style="width:'
      + width + '%;background:' + colors[i % colors.length] + '"></div></div></div>';
  }).join('');
}

/* ═══════════════════════════════════════════════════
   ANALYTICS: Retention
═══════════════════════════════════════════════════ */
function renderRetentionTable(data) {
  var container = document.getElementById('retention-chart');
  if (!container) return;
  if (!data) { container.innerHTML = '<p style="color:var(--text-muted)">Нет данных</p>'; return; }

  var periodLabel = (data.period || 'day7').replace('day', '');
  var overallHtml = '<div class="retention-overall">'
    + '<span class="retention-rate">' + (data.overall_rate || 0) + '%</span>'
    + '<span class="retention-label">Day ' + escHtml(periodLabel) + ' retention</span></div>';

  var tableHtml = '';
  if (data.cohorts && data.cohorts.length) {
    tableHtml = '<table class="retention-table"><thead><tr>'
      + '<th>Когорта</th><th>Размер</th><th>Вернулись</th><th>Rate</th></tr></thead><tbody>';
    data.cohorts.forEach(function(c) {
      var bg = c.rate > 30 ? 'var(--success)' : c.rate > 10 ? 'var(--warning)' : 'var(--danger)';
      tableHtml += '<tr><td>' + escHtml(c.date) + '</td><td>' + c.cohort_size
        + '</td><td>' + c.retained + '</td><td><span class="retention-badge" style="background:'
        + bg + '">' + c.rate + '%</span></td></tr>';
    });
    tableHtml += '</tbody></table>';
  } else {
    tableHtml = '<p style="color:var(--text-muted)">Недостаточно данных</p>';
  }

  container.innerHTML = overallHtml + tableHtml;
}

async function loadRetention(period) {
  document.querySelectorAll('.period-btn').forEach(function(b) { b.classList.remove('active'); });
  if (event && event.target) event.target.classList.add('active');
  try {
    var data = await api('GET', '/api/admin/analytics/retention?period=' + period);
    renderRetentionTable(data);
  } catch (err) {
    console.error('Retention load error', err);
  }
}

/* ═══════════════════════════════════════════════════
   ANALYTICS: Registrations Trend
═══════════════════════════════════════════════════ */
function renderRegistrationsTrend(data) {
  var ctx = document.getElementById('chart-registrations');
  if (!ctx) return;
  if (chartRegistrations) chartRegistrations.destroy();
  if (!data || !data.length) return;

  chartRegistrations = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(function(d) {
        return new Date(d.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
      }),
      datasets: [{
        label: 'Регистрации',
        data: data.map(function(d) { return d.count; }),
        borderColor: '#8B5CF6',
        backgroundColor: 'rgba(139,92,246,0.1)',
        fill: true, tension: 0.3, pointRadius: 3, borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11, family: 'Inter' }, color: '#94A3B8', maxTicksLimit: 10 } },
        y: { beginAtZero: true, ticks: { font: { size: 11, family: 'Inter' }, color: '#94A3B8', stepSize: 1 }, grid: { color: '#F1F5F9' } }
      }
    }
  });
}

/* ═══════════════════════════════════════════════════
   ANALYTICS: Time to Value
═══════════════════════════════════════════════════ */
function renderTTVChart(data) {
  if (!data) return;
  var medianEl = document.getElementById('ttv-median');
  var usersEl = document.getElementById('ttv-users');
  if (medianEl) medianEl.textContent = data.median_hours != null ? data.median_hours + 'ч' : '—';
  if (usersEl) usersEl.textContent = data.users_with_value + ' из ' + (data.users_with_value + data.users_without_value);

  var ctx = document.getElementById('chart-ttv');
  if (!ctx || !data.distribution) return;
  if (chartTTV) chartTTV.destroy();

  chartTTV = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.distribution.map(function(d) { return d.bucket; }),
      datasets: [{
        data: data.distribution.map(function(d) { return d.count; }),
        backgroundColor: '#0D9488',
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11, family: 'Inter' }, color: '#94A3B8' } },
        y: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 11 }, color: '#94A3B8' }, grid: { color: '#F1F5F9' } }
      }
    }
  });
}

/* ═══════════════════════════════════════════════════
   ANALYTICS: Organizer Stats
═══════════════════════════════════════════════════ */
function renderOrganizerTable(data) {
  var container = document.getElementById('organizer-table');
  if (!container) return;
  if (!data || !data.organizers || !data.organizers.length) {
    container.innerHTML = '<p style="color:var(--text-muted)">Нет данных</p>';
    return;
  }

  var avgHtml = '<div class="org-averages">Среднее: '
    + data.averages.schedules_per_organizer + ' расп. / '
    + data.averages.bookings_per_organizer + ' встреч на организатора</div>';

  var rows = data.organizers.map(function(o) {
    var name = escHtml(o.name);
    if (o.username) name += ' <span style="color:var(--text-muted)">@' + escHtml(o.username) + '</span>';
    var lastDate = o.last_booking ? new Date(o.last_booking).toLocaleDateString('ru-RU') : '—';
    return '<tr><td>' + name + '</td><td>' + o.schedules + '</td><td><strong>'
      + o.bookings + '</strong></td><td class="time-cell">' + lastDate + '</td></tr>';
  }).join('');

  container.innerHTML = avgHtml + '<table class="log-table"><thead><tr>'
    + '<th>Организатор</th><th>Расписания</th><th>Встречи</th><th>Посл. активность</th>'
    + '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/* ═══════════════════════════════════════════════════
   DASHBOARD REFRESH
═══════════════════════════════════════════════════ */
function startDashboardRefresh() {
  stopDashboardRefresh();
  dashboardInterval = setInterval(() => {
    const cur = window.location.hash.replace('#', '') || 'dashboard';
    if (cur === 'dashboard') loadDashboard();
  }, 60000);
}

function stopDashboardRefresh() {
  if (dashboardInterval) { clearInterval(dashboardInterval); dashboardInterval = null; }
}
