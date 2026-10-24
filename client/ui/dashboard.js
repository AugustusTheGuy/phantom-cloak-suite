/* PhantomCloak — Dashboard Controller v3 */

const GHOST_IMG = '<img src="ghost-icon.png" alt="" width="28" height="28">';
const GHOST_DIM = '<img src="ghost-icon.png" alt="" width="28" height="28" style="opacity:0.45;filter:grayscale(0.6)">';

const state = {
  active: false,
  purpose: null,
  country: null,
  countryName: null,
  ipId: null,
  googleHidden: false,
  allHidden: false,
  killswitch: false,
  wizardStep: 1,
  createStep: 1,
  broadcastLang: 'en',
  onContentPage: false,
  selectedAccountId: null,
  createMode: false,
};

const PURPOSE_LABELS = {
  streaming: 'Streaming', crypto: 'Crypto', browsing: 'Content Access',
  digital_nomad: 'Digital Nomad', other: 'General',
};

const api = () => window.pywebview?.api;

/* ── SPLASH LOADER ── */
function runSplashLoader() {
  const splash = document.getElementById('splash-screen');
  const appRoot = document.getElementById('app-root');
  const status = document.getElementById('splash-status');
  const bars = ['bar-1', 'bar-2', 'bar-3'];
  const dot = document.querySelector('.splash-wifi .wifi-dot');
  const duration = 3000;
  const start = performance.now();

  const phases = [
    { until: 0.33, active: ['bar-1'], text: 'Establishing secure channel…' },
    { until: 0.66, active: ['bar-1', 'bar-2'], text: 'Verifying zero-leak tunnel…' },
    { until: 1.0, active: ['bar-1', 'bar-2', 'bar-3'], text: 'Loading command center…' },
  ];

  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const phase = phases.find(p => t <= p.until) || phases[2];
    status.textContent = phase.text;
    bars.forEach(b => {
      const el = document.querySelector(`.splash-wifi .${b}`);
      if (el) el.classList.toggle('active', phase.active.includes(b));
    });
    if (dot) dot.classList.toggle('active', t > 0.1);

    if (t < 1) {
      requestAnimationFrame(tick);
    } else {
      splash.classList.add('fade-out');
      appRoot.classList.remove('hidden');
      setTimeout(() => splash.remove(), 700);
    }
  }
  requestAnimationFrame(tick);
}

/* ── GHOST BUTTON STATES ── */
function setPhantomState(mode) {
  const title = document.getElementById('pc-title');
  const activateBtn = document.getElementById('btn-activate');
  const deactivateBtn = document.getElementById('btn-deactivate');
  title.className = 'title';
  if (mode === 'active') {
    title.classList.add('state-green');
    title.textContent = 'PhantomCloak: ACTIVE';
    activateBtn.innerHTML = GHOST_IMG;
    activateBtn.className = 'ghost-btn on-green';
    deactivateBtn.innerHTML = GHOST_IMG;
    deactivateBtn.className = 'ghost-btn on-red';
  } else if (mode === 'standby') {
    title.classList.add('state-purple');
    title.textContent = 'PhantomCloak: STANDBY';
    activateBtn.innerHTML = GHOST_IMG;
    activateBtn.className = 'ghost-btn on-purple';
    deactivateBtn.innerHTML = GHOST_DIM;
    deactivateBtn.className = 'ghost-btn';
  } else {
    title.classList.add('state-red');
    title.textContent = 'PhantomCloak: INACTIVE';
    activateBtn.innerHTML = GHOST_IMG;
    activateBtn.className = 'ghost-btn on-purple';
    deactivateBtn.innerHTML = GHOST_IMG;
    deactivateBtn.className = 'ghost-btn on-red';
  }
}

function initGhostButtons() {
  document.querySelectorAll('.ghost-btn').forEach(btn => {
    if (!btn.innerHTML.trim()) btn.innerHTML = GHOST_IMG;
  });
  setPhantomState('standby');
}

/* ── NAVIGATION ── */
function showMainPage() {
  document.getElementById('main-page').classList.remove('hidden');
  document.getElementById('content-page').classList.add('hidden');
  state.onContentPage = false;
}

function showContentPage() {
  if (!state.active) {
    alert('Activate PhantomCloak first to enter the Content Platform.');
    return;
  }
  document.getElementById('main-page').classList.add('hidden');
  document.getElementById('content-page').classList.remove('hidden');
  state.onContentPage = true;
  renderContentPage();
}

/* ── CONTENT PLATFORM ── */
async function refreshContentAccessPanel() {
  const panel = document.getElementById('content-access-window');
  const btn = document.getElementById('btn-open-content');
  const status = document.getElementById('content-access-status');
  const purposeBadge = document.getElementById('content-access-purpose');
  const countBadge = document.getElementById('content-access-count');
  if (!panel || !btn) return;

  if (state.active) {
    panel.classList.add('unlocked');
    btn.disabled = false;
    const purpose = state.purpose || 'other';
    purposeBadge.textContent = `Purpose: ${PURPOSE_LABELS[purpose] || purpose}`;
    status.innerHTML = '<span class="state-green">●</span> <span>Protected · Camoufox ready</span>';
    const a = api();
    if (a?.get_content_services) {
      try {
        const catalog = await a.get_content_services(purpose);
        const total = (catalog.sections || []).reduce((n, s) => n + (s.services?.length || 0), 0);
        countBadge.textContent = `${total} services`;
        countBadge.classList.remove('hidden');
      } catch { countBadge.classList.add('hidden'); }
    }
  } else {
    panel.classList.remove('unlocked');
    btn.disabled = true;
    purposeBadge.textContent = 'Purpose: —';
    countBadge.classList.add('hidden');
    status.innerHTML = '<span class="content-access-lock">Locked</span><span>Activate PhantomCloak to unlock</span>';
  }
}

async function renderContentPage() {
  const catalog = await api()?.get_content_services(state.purpose);
  if (!catalog) return;
  document.getElementById('content-title-text').textContent = catalog.title || 'Quick Connect';
  document.getElementById('content-subtitle').textContent =
    `Protected browsing via Camoufox · ${catalog.purpose || state.purpose || 'general'}`;
  document.getElementById('content-sections').innerHTML = (catalog.sections || []).map(sec => `
    <div class="content-section">
      <h3>${sec.label}</h3>
      <div class="service-grid">${(sec.services || []).map(svc => renderServiceCard(svc)).join('')}</div>
    </div>
  `).join('');
}

function renderServiceCard(svc) {
  const fav = faviconUrl(svc.url);
  const iconHtml = fav
    ? `<img src="${fav}" alt="${svc.name}" onerror="this.parentElement.textContent='${svc.icon}'"/>`
    : svc.icon;
  const descHtml = (svc.desc || []).slice(0, 5).map(d => `<li>${d}</li>`).join('');
  return `<div class="service-card glass-card" onclick="openService('${svc.url.replace(/'/g, "\\'")}')">
    <div class="service-icon" style="background:${svc.color || '#7c3aed'}">${iconHtml}</div>
    <div class="service-name">${svc.name}</div>
    <ul class="service-desc">${descHtml}</ul>
  </div>`;
}

function faviconUrl(url) {
  try { return `https://www.google.com/s2/favicons?domain=${new URL(url).hostname}&sz=64`; }
  catch { return null; }
}

async function openService(url) {
  const res = await api()?.open_service_url(url);
  if (res?.status === 'error') alert(res.message || 'Could not open service');
}

/* ── COMMAND CENTER (hero summary — Mullvad/Surfshark-style clarity) ── */
function updateCommandCenter(s) {
  const active = !!(s && s.phantomcloak_active);
  const ks = !!(s && s.killswitch_active);
  const dot = document.getElementById('cc-dot');
  const headline = document.getElementById('cc-headline');
  const sub = document.getElementById('cc-sub');
  const primary = document.getElementById('cc-primary');
  const badge = document.getElementById('live-badge');
  if (!headline) return;

  if (dot) {
    dot.classList.toggle('on', active && ks);
    dot.classList.toggle('warn', active && !ks);
  }
  if (active) {
    headline.textContent = ks ? 'Protected' : 'Protected — kill switch off';
    sub.textContent = ks
      ? 'Traffic is routed through your selected location. Kill switch is armed.'
      : 'Suite is on but kill switch is disarmed — enable it to block leaks if the tunnel drops.';
    if (primary) {
      primary.textContent = 'Change purpose / location';
      primary.onclick = () => openWizard();
    }
    if (badge) {
      badge.textContent = 'PROTECTED';
      badge.className = 'badge badge-green';
    }
  } else {
    headline.textContent = 'Not protected';
    sub.textContent = 'Choose Activate to pick a purpose and location, then arm protections.';
    if (primary) {
      primary.textContent = 'Activate protection';
      primary.onclick = () => openWizard();
    }
    if (badge) {
      badge.textContent = 'STANDBY';
      badge.className = 'badge badge-purple';
    }
  }

  const loc = document.getElementById('cc-location');
  const purpose = document.getElementById('cc-purpose');
  const kill = document.getElementById('cc-kill');
  const sec = document.getElementById('cc-sec');
  if (loc) loc.textContent = (s && (s.displayed_location || state.countryName || state.country)) || '—';
  if (purpose) {
    const p = state.purpose || (s && s.purpose);
    purpose.textContent = p ? (PURPOSE_LABELS[p] || p) : '—';
  }
  if (kill) kill.textContent = ks ? 'Armed' : 'Off';
  if (sec) {
    const m = s && s.mimicry_score != null ? `${s.mimicry_score}/100` : '—';
    sec.textContent = m;
  }
}

/* ── STATUS ── */
async function refreshStatus() {
  const a = api();
  if (!a?.get_status) return;
  try {
    const s = await a.get_status();
    const _dloc = s.displayed_location || '';
    const _m = _dloc.match(/^(.*?)\s*\((.*)\)\s*$/);
    const cloakedLoc = _m ? _m[1] : _dloc;
    const resName = _m ? _m[2] : '\u2014';
    const color = s.phantomcloak_active ? 'val-green' : 'val-purple';
    const langNote = s.broadcast_language
      ? `<div><span class="label">BROADCAST:</span> <span class="val-blue">${s.broadcast_language}</span></div>` : '';
    document.getElementById('status-content').innerHTML = `
      <div><span class="label">STATUS:</span> <span class="${color}">${s.phantomcloak_active ? 'ACTIVE' : 'INACTIVE'}</span></div>
      <div><span class="label">TRUE IP:</span> <span class="val-red">${s.true_ip}</span></div>
      <div><span class="label">LOCATION ID:</span> <span class="val-red">${s.true_location}</span></div>
      <div><span class="label">CLOAKED IP:</span> <span class="val-purple">${s.displayed_ip}</span></div>
      <div><span class="label">CLOAKED LOCATION:</span> <span class="val-purple">${cloakedLoc}</span></div>
      <div><span class="label">RESIDENTIAL IP:</span> <span class="${s.phantomcloak_active ? 'val-green' : 'val-red'}">${s.phantomcloak_active ? 'Yes' : 'No'}</span></div>
      <div><span class="label">RESIDENTIAL IP NAME:</span> <span class="val-purple">${resName}</span></div>
      <div><span class="label">KILLSWITCH:</span> <span class="${s.killswitch_active ? 'val-green' : 'val-red'}">${s.killswitch_active ? 'ARMED' : 'DISARMED'}</span></div>
      <div><span class="label">ONION:</span> <span class="val-purple">${s.double_onion_status}</span></div>
      <div><span class="label">ZERO-LEAK:</span> <span class="${s.zero_leak_verification === 'PASS' ? 'val-green' : 'val-orange'}">${s.zero_leak_verification}</span></div>
      <div><span class="label">WEBRTC:</span> <span class="${s.webrtc_leak === 'BLOCKED' ? 'val-green' : 'val-red'}">${s.webrtc_leak}</span></div>
      <div><span class="label">DNS:</span> <span class="${s.dns_leak === 'BLOCKED' ? 'val-green' : 'val-red'}">${s.dns_leak}</span></div>
      <div><span class="label">TUNNEL:</span> <span class="${s.tunnel_status === 'CONNECTED' ? 'val-green' : 'val-purple'}">${s.tunnel_status}</span></div>
      <div><span class="label">MIMICRY:</span> <span class="val-green">${s.mimicry_score}/100</span></div>
      ${langNote}`;

    const mini = document.getElementById('content-status-mini');
    if (mini) {
      mini.innerHTML = `<span class="val-green">PROTECTED</span>
        <span>IP: <span class="val-purple">${s.displayed_ip}</span></span>
        <span>LOC: <span class="val-purple">${s.displayed_location}</span></span>`;
    }

    state.active = s.phantomcloak_active;
    state.purpose = s.purpose || state.purpose;
    state.killswitch = s.killswitch_active;
    state.googleHidden = s.google_trackers_hidden;
    setPhantomState(s.phantomcloak_active ? 'active' : 'standby');
    updateCommandCenter(s);
    document.getElementById('active-bar').classList.toggle('visible', s.phantomcloak_active);
    document.getElementById('google-status').innerHTML = s.google_trackers_hidden
      ? '<span class="state-green">Google + trackers hidden</span>' : '';
    const ksLabel = document.getElementById('killswitch-label');
    ksLabel.textContent = s.killswitch_active ? 'pf Killswitch: ARMED' : 'pf Killswitch: DISARMED';
    ksLabel.className = s.killswitch_active ? 'title state-green' : 'title state-red';
    refreshContentAccessPanel();
    refreshHealthPanel();
    refreshLanReach();
  } catch (e) { console.warn('status', e); }
}

async function setBroadcastLanguage(lang) {
  await api()?.set_broadcast_language(lang, true);
  refreshStatus();
  if (state.onContentPage) renderContentPage();
}

async function loadLanguageOptions() {
  const cfg = await api()?.get_translation_config();
  if (!cfg?.supported) return;
  document.getElementById('lang-select').innerHTML = Object.entries(cfg.supported).map(([c, n]) =>
    `<option value="${c}" ${c === cfg.target_lang ? 'selected' : ''}>${n}</option>`
  ).join('');
}

/* ── ACTIVATION WIZARD ── */
function openWizard() {
  state.wizardStep = 1;
  state.createMode = false;
  document.getElementById('wizard-modal').classList.add('open');
  showWizardStep(1);
}

function closeWizard() {
  document.getElementById('wizard-modal').classList.remove('open');
  clearInterval(ipPollTimer);
}

async function showWizardStep(step) {
  state.wizardStep = step;
  const body = document.getElementById('wizard-body');
  const label = document.getElementById('wizard-step-label');
  const back = document.getElementById('wizard-back');
  const next = document.getElementById('wizard-next');
  back.classList.toggle('hidden', step === 1);

  if (step === 1) {
    label.textContent = 'Step 1 of 4 — Select your purpose';
    const purposes = await api()?.get_purposes() || {};
    body.innerHTML = purposeGridHTML(purposes, 'selectPurpose');
    next.textContent = 'Continue';
    next.onclick = () => state.purpose && showWizardStep(2);
  } else if (step === 2) {
    label.textContent = `Step 2 of 4 — Best countries for ${state.purpose}`;
    const countries = await api()?.get_countries(state.purpose) || [];
    body.innerHTML = countryGridHTML(countries);
    next.onclick = () => state.country && showWizardStep(3);
  } else if (step === 3) {
    label.textContent = `Step 3 of 4 — Residential IP (${state.countryName})`;
    body.innerHTML = ipTableHTML();
    next.onclick = () => state.ipId && showWizardStep(4);
    loadResidentialIPs();
  } else if (step === 4) {
    label.textContent = 'Step 4 of 4 — Save account (optional)';
    body.innerHTML = accountFieldsHTML();
    next.textContent = 'Activate PhantomCloak';
    next.onclick = finishActivation;
  }
}

function purposeGridHTML(purposes, handler) {
  return `<div class="purpose-grid">${Object.entries(purposes).map(([k, p]) =>
    `<div class="card-select" data-purpose="${k}" onclick="${handler}('${k}')">
      <div class="icon">${p.icon}</div><div class="name">${p.label}</div>
      <div style="font-size:0.7rem;color:var(--muted);margin-top:4px">${p.description}</div>
    </div>`
  ).join('')}</div>`;
}

function countryGridHTML(countries) {
  return `<div class="country-grid">${countries.map(c =>
    `<div class="card-select" data-country="${c.code}" onclick="selectCountry('${c.code}','${c.name.replace(/'/g, "\\'")}')">
      <div class="name">${c.name}</div>
      <div style="font-size:0.7rem;color:var(--muted)">${c.note}</div>
      <div class="badge badge-purple" style="margin-top:6px">Score ${c.score}</div>
    </div>`
  ).join('')}</div>`;
}

function ipTableHTML() {
  return `<div id="ip-loading">Loading residential IPs…</div>
    <table class="ip-table hidden" id="ip-table"><thead><tr>
      <th>IP</th><th>Latency</th><th>Jitter</th><th>Loss</th><th>ISP</th><th>Rep</th>
    </tr></thead><tbody id="ip-tbody"></tbody></table>`;
}

function accountFieldsHTML() {
  return `<p style="color:var(--muted);margin-bottom:14px;font-size:0.84rem">Optionally save this session for quick reload.</p>
    <label style="font-size:0.78rem;color:var(--muted)">Account name</label>
    <input class="input-field" id="acct-name" placeholder="My session" style="margin-bottom:10px" onkeydown="acctFieldsKey(event)"/>
    <label style="font-size:0.78rem;color:var(--muted)">Password (stored encrypted in cloud vault)</label>
    <input class="input-field" id="acct-pass" type="password" placeholder="Optional password" onkeydown="acctFieldsKey(event)"/>`;
}

function selectPurpose(p) {
  state.purpose = p;
  document.querySelectorAll('[data-purpose]').forEach(el => el.classList.toggle('selected', el.dataset.purpose === p));
}

function selectCountry(code, name) {
  state.country = code;
  state.countryName = name;
  document.querySelectorAll('[data-country]').forEach(el => el.classList.toggle('selected', el.dataset.country === code));
}

let ipPollTimer = null;
async function loadResidentialIPs() {
  const a = api();
  if (!a) return;
  const render = async () => {
    const ips = await a.get_residential_ips(state.country, 15);
    document.getElementById('ip-loading')?.classList.add('hidden');
    document.getElementById('ip-table')?.classList.remove('hidden');
    const tbody = document.getElementById('ip-tbody');
    if (!tbody) return;
    tbody.innerHTML = ips.map(ip => `
      <tr class="${state.ipId === ip.id ? 'selected' : ''}" onclick="selectIP('${ip.id}')">
        <td>${ip.ip}</td><td>${ip.latency_ms} ms</td><td>${ip.jitter_ms} ms</td>
        <td>${ip.packet_loss_pct}%</td><td>${ip.isp}</td><td>${ip.reputation_score}</td>
      </tr>`).join('');
  };
  await render();
  clearInterval(ipPollTimer);
  ipPollTimer = setInterval(render, 500);
}

function selectIP(id) {
  state.ipId = id;
  document.querySelectorAll('#ip-tbody tr').forEach(tr => tr.classList.remove('selected'));
  event?.currentTarget?.classList.add('selected');
}

async function finishActivation() {
  const a = api();
  if (!a) { closeWizard(); return; }
  const name = (document.getElementById('acct-name')?.value || '').trim();
  const pass = document.getElementById('acct-pass')?.value;
  const next = document.getElementById('wizard-next');
  if (next) { next.disabled = true; next.textContent = 'Activating…'; }
  try {
    if (name) await a.save_account(name, state.purpose, state.country, state.countryName, state.ipId, pass || null);
    const res = await a.activate_phantomcloak(state.purpose, state.country, state.ipId);
    clearInterval(ipPollTimer);
    closeWizard();
    if (name) showSuccessToast(name);
    await refreshStatus();
    if (res?.navigate_content) showContentPage();
  } catch (err) {
    if (next) { next.disabled = false; next.textContent = 'Activate PhantomCloak'; }
    alert('Activation failed: ' + (err?.message || err));
  }
}

async function deactivate() {
  if (!confirm('Deactivate PhantomCloak and restore all settings?')) return;
  await api()?.deactivate_phantomcloak();
  showMainPage();
  refreshStatus();
}

async function toggleKillswitch() {
  await api()?.toggle_killswitch(!state.killswitch);
  refreshStatus();
}

async function hideGoogle() { await api()?.hide_google_trackers(); refreshStatus(); }
async function restoreGoogle() { await api()?.restore_google_data(); refreshStatus(); }
async function hideAll() { await api()?.hide_all_trackers(); refreshStatus(); }

/* ── ACCOUNT HUB ── */
async function openAccountHub() {
  document.getElementById('account-hub-modal').classList.add('open');
  await renderAccountList();
}

function closeAccountHub() {
  document.getElementById('account-hub-modal').classList.remove('open');
}

async function renderAccountList() {
  const list = document.getElementById('account-list');
  const accounts = await api()?.list_accounts() || [];
  if (!accounts.length) {
    list.innerHTML = `<p style="color:var(--muted);font-size:0.84rem;padding:16px;text-align:center">
      No saved accounts yet.<br>Tap <strong>Create Account</strong> to get started.</p>`;
    return;
  }
  list.innerHTML = accounts.map(a => `
    <div class="account-row" onclick="selectAccountForLogin('${a.id}','${a.name.replace(/'/g, "\\'")}',${a.protected})">
      <span class="account-flag">${a.country_flag || '🌐'}</span>
      <div class="account-row-info">
        <div class="account-row-name">${a.name}</div>
        <div class="account-row-meta">${PURPOSE_LABELS[a.purpose] || a.purpose} · ${a.country_name || a.country}</div>
      </div>
      ${a.protected ? '<span class="account-lock">Protected</span>' : ''}
    </div>`).join('');
}

function selectAccountForLogin(id, name, protected_) {
  state.selectedAccountId = id;
  closeAccountHub();
  document.getElementById('login-account').value = name;
  document.getElementById('login-password').value = '';
  document.getElementById('login-modal').classList.add('open');
  if (!protected_) {
    submitLoginDirect(id, null);
  } else {
    setTimeout(() => document.getElementById('login-password').focus(), 100);
  }
}

function closeLogin() {
  document.getElementById('login-modal').classList.remove('open');
  state.selectedAccountId = null;
}

async function submitLogin(e) {
  e.preventDefault();
  const pass = document.getElementById('login-password').value;
  await submitLoginDirect(state.selectedAccountId, pass);
}

async function submitLoginDirect(id, pass) {
  const res = await api()?.load_account(id, pass);
  closeLogin();
  if (res?.status === 'loaded') {
    state.purpose = res.account.purpose;
    state.country = res.account.country;
    state.countryName = res.account.country_name;
    state.ipId = res.account.residential_ip_id;
    await refreshStatus();
  } else if (res?.status === 'password_required') {
    document.getElementById('login-account').value = res.name;
    document.getElementById('login-modal').classList.add('open');
  } else {
    alert(res?.message || 'Could not load account');
  }
}

/* ── CREATE ACCOUNT ── */
function startCreateAccount() {
  closeAccountHub();
  state.createStep = 1;
  state.createMode = true;
  document.getElementById('create-account-modal').classList.add('open');
  showCreateStep(1);
}

function closeCreateAccount() {
  document.getElementById('create-account-modal').classList.remove('open');
  clearInterval(ipPollTimer);
}

async function showCreateStep(step) {
  state.createStep = step;
  const body = document.getElementById('create-body');
  const label = document.getElementById('create-step-label');
  const back = document.getElementById('create-back');
  const next = document.getElementById('create-next');
  back.classList.toggle('hidden', step === 1);

  if (step === 1) {
    label.textContent = 'Step 1 of 4 — Select use-case';
    const purposes = await api()?.get_purposes() || {};
    body.innerHTML = purposeGridHTML(purposes, 'selectCreatePurpose');
    next.onclick = () => state.purpose && showCreateStep(2);
  } else if (step === 2) {
    label.textContent = `Step 2 of 4 — Country for ${state.purpose}`;
    body.innerHTML = countryGridHTML(await api()?.get_countries(state.purpose) || []);
    next.onclick = () => state.country && showCreateStep(3);
  } else if (step === 3) {
    label.textContent = `Step 3 of 4 — Residential IP (${state.countryName})`;
    body.innerHTML = ipTableHTML();
    next.onclick = () => state.ipId && showCreateStep(4);
    loadResidentialIPs();
  } else if (step === 4) {
    label.textContent = 'Step 4 of 4 — Name & password';
    body.innerHTML = accountFieldsHTML();
    next.textContent = 'Create Account';
    next.onclick = finishCreateAccount;
  }
}

function selectCreatePurpose(p) { selectPurpose(p); }

async function finishCreateAccount() {
  const name = document.getElementById('acct-name')?.value?.trim();
  const pass = document.getElementById('acct-pass')?.value;
  if (!name) { alert('Please enter an account name.'); return; }
  const next = document.getElementById('create-next');
  if (next) { next.disabled = true; next.textContent = 'Creating…'; }
  try {
    const res = await api()?.save_account(name, state.purpose, state.country, state.countryName, state.ipId, pass || null);
    clearInterval(ipPollTimer);
    if (res?.status === 'saved') {
      closeCreateAccount();
      showSuccessToast(name);
      await refreshStatus();
    } else {
      if (next) { next.disabled = false; next.textContent = 'Create Account'; }
      alert(res?.message || 'Could not save account');
    }
  } catch (err) {
    if (next) { next.disabled = false; next.textContent = 'Create Account'; }
    alert('Could not save account: ' + (err?.message || err));
  }
}

function acctFieldsKey(e) {
  if (e.key === 'Enter') { e.preventDefault(); state.createMode ? finishCreateAccount() : finishActivation(); }
}

function showSuccessToast(name, okText, opts) {
  opts = opts || {};
  const prev = document.getElementById('pc-success-toast');
  if (prev) prev.remove();
  const safe = String(name || 'Your').replace(/</g, '&lt;');
  const namePart = opts.rawName ? safe : (safe + ' account');
  const ok = okText || 'created successfully!';
  const el = document.createElement('div');
  el.id = 'pc-success-toast';
  el.className = 'pc-success-toast';
  el.innerHTML = `<div class="pc-toast-card"><span class="pc-toast-name">${namePart}</span> <span class="pc-toast-ok">${ok}</span></div>`;
  document.body.appendChild(el);
  setTimeout(() => el.classList.add('pc-toast-out'), 2100);
  setTimeout(() => el.remove(), 2500);
}

/* ── TOP 30 HEALTH HARNESS ── */
const HEALTH_STATUS_LABEL = {
  nominal: 'NOMINAL',
  degraded: 'DEGRADED',
  critical: 'CRITICAL',
};

const CT_GROUPS = {
  1: 'Transport Obfuscation',
  2: 'Browser Fingerprint',
  3: 'Network Stack',
  4: 'Tunnel Layers',
  5: 'Leak Prevention',
  6: 'Kill Switch & Watchdog',
  7: 'Anti-Forensics',
  8: 'Monitoring & Rotation',
};

function renderHealthPanel(panel) {
  if (!panel) return;
  const overall = document.getElementById('health-overall');
  const summary = document.getElementById('health-summary');
  const list = document.getElementById('health-list');
  if (!overall || !summary || !list) return;

  const state = panel.overall || 'standby';
  overall.textContent = panel.phantomcloak_active
    ? (HEALTH_STATUS_LABEL[state] || state.toUpperCase())
    : 'STANDBY';
  overall.className = 'health-overall badge ' + (
    state === 'nominal' ? 'badge-green' :
    state === 'critical' ? 'badge-red' : 'badge-purple'
  );

  const c = panel.counts || {};
  const techs = panel.techniques || [];
  const countEl = document.getElementById('health-count');
  if (countEl) countEl.textContent = `${techs.length} Cloaking Techniques`;
  summary.innerHTML = panel.phantomcloak_active
    ? `<span class="val-green">${c.green || 0} green</span> · <span class="val-orange">${c.yellow || 0} yellow</span> · <span class="val-red">${c.red || 0} red</span> · Mimicry ${panel.mimicry_score || 0}/100`
    : 'Activate PhantomCloak to evaluate all cloaking techniques.';

  let n = 0, lastPillar = null, html = '';
  for (const t of techs) {
    if (t.pillar !== lastPillar) {
      lastPillar = t.pillar;
      html += `<div class="ct-group-header">${CT_GROUPS[t.pillar] || 'Other'}</div>`;
    }
    n++;
    html += `<div class="health-row" title="${t.reason}">
      <span class="health-dot ${t.status}"></span>
      <div class="health-row-body">
        <div class="health-row-name">${n}. ${t.name}</div>
        <div class="health-row-reason">${t.reason}</div>
      </div>
      ${t.status !== 'green' ? `<button class="health-heal-btn" onclick="healTechnique('${t.id}')">HEAL</button>` : ''}
    </div>`;
  }
  list.innerHTML = html;
}

function gradeFromCounts(c, mimicry) {
  const total = (c.green || 0) + (c.yellow || 0) + (c.red || 0) || 30;
  const green = c.green || 0, red = c.red || 0;
  const pct = green / total;
  let score = Math.round(pct * 70 + ((mimicry || 0) / 100) * 30);
  let letter = score >= 90 ? 'A' : score >= 80 ? 'B' : score >= 70 ? 'C' : score >= 60 ? 'D' : 'F';
  if (red > 0 && letter === 'A') letter = 'B';
  return { letter, score };
}

function renderGradePanel(panel) {
  const el = document.getElementById('grade-content');
  if (!el) return;
  if (!panel || !panel.phantomcloak_active) {
    el.innerHTML = '<div class="grade-empty">Activate to grade protections</div>';
    return;
  }
  const c = panel.counts || {};
  const g = gradeFromCounts(c, panel.mimicry_score);
  const cls = (g.letter === 'A' || g.letter === 'B') ? 'val-green' : (g.letter === 'C' ? 'val-orange' : 'val-red');
  el.innerHTML = `
    <div class="grade-title">Health + Security Audit</div>
    <div class="grade-row">
      <div class="grade-metric"><div class="grade-label">GRADE</div><div class="grade-big ${cls}">${g.letter}</div><div class="grade-score">${g.score}/100</div></div>
      <div class="grade-metric"><div class="grade-label">MIMICRY</div><div class="grade-big val-green">${panel.mimicry_score || 0}</div><div class="grade-score">/100</div></div>
    </div>
    <div class="grade-counts"><span class="val-green">${c.green || 0} green</span> · <span class="val-orange">${c.yellow || 0} yellow</span> · <span class="val-red">${c.red || 0} red</span></div>`;
}

async function refreshHealthPanel() {
  const panel = await api()?.get_health_panel?.();
  if (panel) { renderHealthPanel(panel); renderGradePanel(panel); }
}

async function runHealthHarness() {
  const panel = await api()?.run_health_harness?.();
  if (panel) renderHealthPanel(panel);
}

async function healTechnique(id) {
  const btns = document.querySelectorAll(`.health-heal-btn[onclick*="${id}"]`);
  btns.forEach(b => { b.disabled = true; b.textContent = '…'; });
  const res = await api()?.heal_technique?.(id);
  if (res?.refreshed) { renderHealthPanel(res.refreshed); renderGradePanel(res.refreshed); }
  if (res?.message) showHealToast(res.status, res.message);
  refreshStatus();
}

function showHealToast(status, message) {
  const map = { healed: 'ht-green', partial: 'ht-amber', blocked: 'ht-amber', error: 'ht-red', noop: 'ht-amber' };
  const label = { healed: 'HEALED', partial: 'PARTIAL', blocked: 'BLOCKED', error: 'ERROR', noop: 'OK' }[status] || 'HEAL';
  const prev = document.getElementById('heal-toast'); if (prev) prev.remove();
  const el = document.createElement('div');
  el.id = 'heal-toast';
  el.className = 'heal-toast ' + (map[status] || 'ht-amber');
  el.innerHTML = `<span class="ht-tag">${label}</span> <span class="ht-msg">${String(message).replace(/</g, '&lt;')}</span>`;
  document.body.appendChild(el);
  setTimeout(() => el.classList.add('ht-out'), 4200);
  setTimeout(() => el.remove(), 4700);
}

async function healAll() {
  const btn = document.getElementById('heal-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Healing…'; }
  try {
    const res = await api()?.heal_all?.();
    if (res?.refreshed) { renderHealthPanel(res.refreshed); renderGradePanel(res.refreshed); }
    if (res) {
      const b = res.before || {}, a = res.after || {};
      const gained = (a.green || 0) - (b.green || 0);
      const blocked = (res.blocked_needs_infra || []).length;
      const msg = `Ran ${res.actions_run} fixes · +${gained} green `
        + `(${a.green || 0} green / ${a.yellow || 0} yellow / ${a.red || 0} red)`
        + (blocked ? ` · ${blocked} still need a real VPS/server` : '');
      showHealToast(gained > 0 ? 'healed' : 'partial', msg);
    }
  } catch (e) {
    showHealToast('error', 'Heal ALL failed: ' + (e?.message || e));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Heal ALL ⊕'; }
  }
  refreshStatus();
}

async function enableOnion() {
  await api()?.toggle_double_onion?.(true);
  document.getElementById('quick-settings')?.classList.remove('open');
  showHealToast('healed', 'Double Onion enabled (VPN → Tor). Expect higher latency.');
  refreshStatus();
}

async function disableOnion() {
  await api()?.toggle_double_onion?.(false);
  document.getElementById('quick-settings')?.classList.remove('open');
  showHealToast('partial', 'Double Onion disabled (performance mode).');
  refreshStatus();
}

async function setLocalNetwork(enabled) {
  const label = document.getElementById('lan-label');
  if (label) {
    label.textContent = 'Local Network Access: ' + (enabled ? 'ON' : 'OFF');
    label.className = 'title ' + (enabled ? 'state-green' : 'state-red');
  }
  const res = await api()?.set_local_network_access?.(enabled);
  if (res?.rearmed) {
    showHealToast('healed', 'Local Network Access ' + (enabled ? 'ON' : 'OFF') + ' — kill-switch rules re-applied live.');
  } else {
    showHealToast(enabled ? 'healed' : 'partial',
      enabled ? 'Local Network Access ON — AirPlay, casting & mirroring can reach LAN devices.'
              : 'Local Network Access OFF — LAN devices blocked while protected.');
  }
}

async function syncLocalNetworkToggle() {
  const r = await api()?.get_local_network_access?.();
  if (!r) return;
  const cb = document.getElementById('lan-toggle');
  const label = document.getElementById('lan-label');
  if (cb) cb.checked = !!r.enabled;
  if (label) {
    label.textContent = 'Local Network Access: ' + (r.enabled ? 'ON' : 'OFF');
    label.className = 'title ' + (r.enabled ? 'state-green' : 'state-red');
  }
}

async function refreshLanReach() {
  const el = document.getElementById('lan-reach');
  if (!el) return;
  const r = await api()?.lan_gateway_check?.();
  if (!r) { el.textContent = ''; return; }
  if (r.reachable) {
    el.textContent = `LAN ✓${r.latency_ms != null ? ' ' + r.latency_ms + 'ms' : ''}`;
    el.className = 'lan-reach lr-ok';
    el.title = 'Gateway ' + (r.gateway || '') + ' reachable';
  } else {
    el.textContent = r.gateway ? 'LAN ✗' : 'no gateway';
    el.className = 'lan-reach lr-bad';
    el.title = r.gateway ? ('Gateway ' + r.gateway + ' not reachable') : 'No default gateway found';
  }
}

/* ── SECURITY AUDIT ── */
async function runSecurityAudit() {
  const audit = await api()?.run_security_audit();
  if (!audit) return;
  const panel = document.getElementById('audit-panel');
  panel.classList.remove('hidden');
  const issues = audit.findings?.filter(f => f.severity !== 'info') || [];
  panel.innerHTML = `
    <div class="audit-score">${audit.score}/100 <span class="audit-grade">Grade ${audit.grade}</span></div>
    <div style="margin-top:8px;color:var(--muted);font-size:0.72rem">
      ${issues.length ? issues.map(i => `• ${i.issue}`).join('<br>') : 'All checks passed'}
    </div>`;
}

function toggleDropdown(id) {
  document.getElementById(id)?.classList.toggle('open');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.dropdown-wrap')) {
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('open'));
  }
});

let _appReady = false;
function onReady() {
  if (_appReady) return;
  _appReady = true;
  initGhostButtons();
  runSplashLoader();
  loadLanguageOptions();
  refreshStatus();
  refreshHealthPanel();
  setInterval(refreshStatus, 2000);
}

window.addEventListener('pywebviewready', onReady);
window.onload = () => {
  if (!window.pywebview) { runSplashLoader(); initGhostButtons(); }
};

/* ── Ensure the window opens at the very top so the header / account bar is
   visible (fixes the "opens scrolled down, header cut off" issue). ── */
(function () {
  function toTop() {
    try {
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
      var ar = document.getElementById('app-root');
      if (ar) ar.scrollTop = 0;
    } catch (e) {}
  }
  var _n = 0, _iv = setInterval(function () { toTop(); if (++_n > 24) clearInterval(_iv); }, 250);
  window.addEventListener('load', toTop);
  document.addEventListener('DOMContentLoaded', toTop);
})();


/* ── Green/red ghost status sync for the tracker toggles ── */
(function () {
  function pair(onId, offId, active) {
    var on = document.getElementById(onId), off = document.getElementById(offId);
    if (on) { on.classList.remove('on-purple', 'g-pulse', 'g-dim'); on.classList.add(active ? 'g-pulse' : 'g-dim'); }
    if (off) { off.classList.remove('r-pulse', 'r-dim'); off.classList.add(active ? 'r-dim' : 'r-pulse'); }
  }
  async function sync() {
    var a = (window.pywebview && window.pywebview.api);
    if (!a || !a.get_status) return;
    try {
      var s = await a.get_status();
      pair('gh-google-on', 'gh-google-off', !!s.google_trackers_hidden);
      pair('gh-all-on', 'gh-all-off', !!(s.all_trackers_hidden || s.trackers_hidden));
    } catch (e) {}
  }
  setInterval(sync, 1000);
  setTimeout(sync, 3600);
})();


/* ── CHECKOUT / SUBSCRIBE (crypto chain-watch -> mint -> redeem) ── */
const CO = { tier: null, term: null, asset: null, order: null, poll: null };

function openCheckout() {
  CO.tier = CO.term = CO.asset = null; CO.order = null;
  clearInterval(CO.poll);
  document.getElementById('quick-settings')?.classList.remove('open');
  document.getElementById('checkout-modal').classList.add('open');
  renderCheckoutPlan();
}
function closeCheckout() {
  clearInterval(CO.poll);
  document.getElementById('checkout-modal').classList.remove('open');
}

async function renderCheckoutPlan() {
  const body = document.getElementById('checkout-body');
  const quote = await api()?.payment_quote() || {};
  const assets = await api()?.payment_assets() || {};
  const plans = [['core', 'monthly'], ['core', 'annual'], ['pro', 'monthly'], ['pro', 'annual']];
  const planCards = plans.map(([t, term]) => {
    const price = quote[`${t}|${term}`];
    const sel = (CO.tier === t && CO.term === term) ? ' selected' : '';
    return `<div class="co-card${sel}" onclick="selectPlan('${t}','${term}')">
      <div class="co-tier">${t === 'pro' ? 'Pro' : 'Core'}</div>
      <div class="co-term">${term}</div>
      <div class="co-price">$${price}</div></div>`;
  }).join('');
  const assetCards = Object.entries(assets).map(([k, v]) => {
    const sel = CO.asset === k ? ' selected' : '';
    const ult = v.privacy === 'ultimate' ? '<span class="co-ult">ULTIMATE</span>'
              : (v.privacy === 'high' ? '<span class="co-ult co-high">HIGH</span>' : '');
    return `<div class="co-asset${sel}" onclick="selectAsset('${k}')">
      <span class="co-asset-sym">${k.replace('_TRON', ' (TRON)')}</span>
      <span class="co-asset-name">${v.name}</span>${ult}</div>`;
  }).join('');
  body.innerHTML = `
    <p class="co-lead">Choose a plan, then pay in crypto. Monero is the strongest privacy signal.</p>
    <div class="co-plan-grid">${planCards}</div>
    <div class="co-sub-label">Pay with</div>
    <div class="co-asset-grid">${assetCards}</div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="renderCheckoutRedeem('')">I already have a code</button>
      <button class="btn btn-primary" onclick="generatePayment()">Generate payment</button>
    </div>`;
}
function selectPlan(t, term) { CO.tier = t; CO.term = term; renderCheckoutPlan(); }
function selectAsset(a) { CO.asset = a; renderCheckoutPlan(); }

async function generatePayment() {
  if (!CO.tier || !CO.term) { alert('Pick a plan.'); return; }
  if (!CO.asset) { alert('Pick a payment asset.'); return; }
  const o = await api()?.payment_create_order(CO.tier, CO.term, CO.asset);
  if (!o || o.error) { alert(o?.error || 'Could not create order.'); return; }
  CO.order = o;
  renderCheckoutPay();
  clearInterval(CO.poll);
  CO.poll = setInterval(checkPaymentStatus, 4000);
}

function renderCheckoutPay() {
  const o = CO.order;
  const body = document.getElementById('checkout-body');
  const addr = o.address_configured
    ? `<code class="co-mono">${o.payment_target}</code>`
    : `<span class="co-warn">⚠ No ${o.asset} address configured yet. Add it to wallets.json to receive funds.</span>`;
  const dev = `<button class="btn btn-ghost btn-sm" onclick="devConfirm()">Simulate confirmation (dev)</button>`;
  body.innerHTML = `
    <div class="co-pay">
      <div class="co-row"><span>Plan</span><b>${o.tier === 'pro' ? 'Pro' : 'Core'} · ${o.term}</b></div>
      <div class="co-row"><span>Amount (USD-priced)</span><b>$${o.amount_usd}</b></div>
      <div class="co-row"><span>Pay with</span><b>${o.asset}</b></div>
      <div class="co-field"><label>Send to address</label>${addr}</div>
      <div class="co-field"><label>Payment ID / memo (required)</label><code class="co-mono">${o.payment_tag}</code>
        <div class="co-hint">Include this exact ID so your payment is matched to your order.</div></div>
      <div class="co-field"><label>Confirmations needed</label><b>${o.confirms_needed}</b></div>
      <div class="co-status" id="co-status">Awaiting payment on-chain…</div>
      <div class="modal-actions">
        <button class="btn btn-ghost" onclick="renderCheckoutPlan()">Back</button>
        <button class="btn btn-ghost" onclick="checkPaymentStatus()">Check status</button>
        ${dev}
      </div>
      <p class="co-fine">Your access code is minted only after the blockchain confirms your payment — it can't be guessed, reused, or scooped.</p>
    </div>`;
}

async function checkPaymentStatus() {
  if (!CO.order) return;
  const st = await api()?.payment_status(CO.order.order_id);
  const el = document.getElementById('co-status');
  if (st && st.status === 'activated' && st.access_code) {
    clearInterval(CO.poll);
    renderCheckoutRedeem(st.access_code);
  } else if (el) {
    el.textContent = 'Awaiting payment on-chain…';
  }
}

async function devConfirm() {
  if (!CO.order) return;
  const r = await api()?.payment_dev_confirm(CO.order.order_id);
  if (r && r.error) { alert(r.error); return; }
  checkPaymentStatus();
}

function renderCheckoutRedeem(code) {
  const body = document.getElementById('checkout-body');
  body.innerHTML = `
    <p class="co-lead">${code ? 'Payment confirmed. Your access code:' : 'Paste the access code you received after payment.'}</p>
    ${code ? `<div class="co-code">${code}</div>` : ''}
    <div class="co-field"><label>Access code</label>
      <input class="input-field" id="co-redeem-input" value="${code || ''}" placeholder="PC-XXXX-XXXX-..."
        onkeydown="if(event.key==='Enter'){event.preventDefault();doRedeem();}"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="renderCheckoutPlan()">Back</button>
      <button class="btn btn-primary" onclick="doRedeem()">Activate subscription</button>
    </div>`;
}

async function doRedeem() {
  const code = document.getElementById('co-redeem-input')?.value?.trim();
  if (!code) { alert('Enter your access code.'); return; }
  const r = await api()?.payment_redeem(code);
  if (!r || !r.ok) { alert((r && r.message) || 'Invalid code'); return; }
  clearInterval(CO.poll);
  closeCheckout();
  showSuccessToast((r.tier === 'pro' ? 'Pro' : 'Core') + ' subscription', 'activated!', { rawName: true });
  refreshStatus();
}

/* Sync the Local Network Access toggle to persisted state once the API is ready. */
(function initLocalNetworkSync() {
  let tries = 0;
  const t = setInterval(() => {
    tries++;
    if ((typeof api === 'function' && api()) || tries > 60) {
      clearInterval(t);
      try { syncLocalNetworkToggle(); refreshLanReach(); } catch (e) { /* api not ready yet */ }
    }
  }, 250);
})();
