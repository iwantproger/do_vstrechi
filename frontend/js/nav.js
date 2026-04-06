/* ═══════════════════════════════════════════
   NAVIGATION
═══════════════════════════════════════════ */
function showScreen(id, push = true) {
  const cur = document.getElementById(state.currentScreen);
  const next = document.getElementById(id);
  if (!next || id === state.currentScreen) return;

  if (push) state.screenStack.push(state.currentScreen);

  cur.classList.remove('active');
  cur.classList.add('prev');
  next.classList.add('active');
  state.currentScreen = id;

  const isTab = TAB_SCREENS.includes(id);
  if (isTab) showNavbar(); else hideNavbar();

  if (tg) {
    tg.BackButton.offClick(back);
    if (state.screenStack.length) { tg.BackButton.show(); tg.BackButton.onClick(back); }
    else tg.BackButton.hide();
  }

  setTimeout(() => cur.classList.remove('prev'), 320);
}

function back() {
  /* preview mode: clean up banner and flag */
  if (state._previewMode && state.currentScreen === 's-calendar') {
    state._previewMode = false;
    var banner = document.getElementById('preview-banner');
    if (banner) banner.remove();
    var formBlock = document.getElementById('cal-guest-form');
    if (formBlock) formBlock.style.display = 'none';
  }

  if (!state.screenStack.length) {
    /* guest mode: nothing to go back to — close app */
    if (state.isGuestMode && tg) tg.close();
    return;
  }
  const prev = state.screenStack.pop();
  const cur = document.getElementById(state.currentScreen);
  const prevEl = document.getElementById(prev);

  cur.classList.remove('active');
  cur.classList.add('leaving');
  setTimeout(() => cur.classList.remove('leaving'), 300);
  prevEl.classList.remove('prev');
  prevEl.classList.add('active');
  state.currentScreen = prev;

  /* FIX: обновить данные при возврате на таб-экраны */
  if (state.user) {
    if (prev === 's-schedules') loadSchedules();
    else if (prev === 's-meetings') renderMeetingsList(); /* re-render from already-updated state */
    else if (prev === 's-home') loadHome();
  }

  const isTab = TAB_SCREENS.includes(prev);
  if (isTab) showNavbar(); else hideNavbar();

  if (tg) {
    tg.BackButton.offClick(back);
    if (state.screenStack.length) { tg.BackButton.show(); tg.BackButton.onClick(back); }
    else tg.BackButton.hide();
  }
}

function goBack() { back(); }

function navTab(screenId, navId) {
  document.querySelectorAll('.overlay.show').forEach(o => o.classList.remove('show'));

  const cur = document.getElementById(state.currentScreen);
  const next = document.getElementById(screenId);
  if (!next) return;

  state.screenStack.length = 0;
  setActiveNav(navId);

  if (screenId === state.currentScreen) { next.scrollTop = 0; return; }

  cur.classList.remove('active', 'prev');
  next.classList.add('active');
  next.classList.remove('prev');
  state.currentScreen = screenId;

  showNavbar();
  if (tg) tg.BackButton.hide();
  next.scrollTop = 0;

  if (screenId === 's-meetings') loadMeetings();
  else if (screenId === 's-schedules') loadSchedules();
  else if (screenId === 's-home') loadHome();
  else if (screenId === 's-profile') loadProfile();
}

/* ═══════════════════════════════════════════
   NAVBAR
═══════════════════════════════════════════ */
function hideNavbar() {
  const el = document.getElementById('navbar');
  if (el) el.style.display = 'none';
}

function showNavbar() {
  const el = document.getElementById('navbar');
  if (el) el.style.display = 'flex';
}

function setActiveNav(tabId) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('on'));
  const el = document.getElementById(tabId);
  if (el) el.classList.add('on');
}

