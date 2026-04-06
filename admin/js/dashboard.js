/* ═══════════════════════════════════════════════════
   DASHBOARD
═══════════════════════════════════════════════════ */
let chartTrend = null;
let chartPlatforms = null;
let chartWeekday = null;
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
