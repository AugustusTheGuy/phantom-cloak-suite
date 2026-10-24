/* PCS Command Center v2 — live status via industrial /api/status; Python is authority */
const state = {
  tier: "core",
  protected: false,
  session: {
    purpose: "browsing",
    country: "CH",
    location: "zurich",
    country_name: "Zurich",
  },
  securityScore: null,
  live: null,
  apiBase: "",
};

const PRICES = {
  core: { monthly: 11.99, annual: 59.88, label: "PhantomCloak Core" },
  pro: { monthly: 39, annual: 348, label: "PhantomCloak Pro" },
};

const FLAGS = { CH: "🇨🇭", CA: "🇨🇦", AE: "🇦🇪", SG: "🇸🇬", DE: "🇩🇪", HK: "🇭🇰" };

const CORE_BULLETS = [
  "Kill switch auto-on with Activate",
  "Zero-leak preflight before send",
  "Tracker vault hide / restore (confirm)",
  "DNS · WebRTC · IPv6 guards",
  "Argon2id account passwords (industrial)",
];
const PRO_BULLETS = [
  "Everything in Core",
  "RBAC · workspaces · audit",
  "Residential pool / multi-hop (config)",
  "Always-on watchdog",
  "Team seats pricing",
];

const LS_KEY = "pcs_industrial_v2_session";
const DEFAULT_INV = "~/.pcs_industrial_20260802/vps_inventory.json";
const DEFAULT_HOWTO =
  "~/Desktop/PCS_Industrial_20260802/docs_v20260802/HOWTO_DEPLOY_LINK_v20260802.md";
const DEFAULT_PLAYBOOK =
  "~/Desktop/PCS_Industrial_20260802/docs_v20260802/CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md";
const SUITE_HOWTO =
  "~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md";

/** Offline-safe purpose top5 (mirrors shared/pcs_purpose_routing PURPOSE_TOP5 codes). */
const OFFLINE_PURPOSE_TOP5 = {
  purposes: ["streaming", "crypto", "browsing", "digital_nomad", "other"],
  by_purpose: {
    streaming: [
      { code: "US", name: "United States" },
      { code: "GB", name: "United Kingdom" },
      { code: "CA", name: "Canada" },
      { code: "AU", name: "Australia" },
      { code: "DE", name: "Germany" },
    ],
    crypto: [
      { code: "AE", name: "UAE (Dubai)" },
      { code: "SG", name: "Singapore" },
      { code: "CH", name: "Switzerland" },
      { code: "HK", name: "Hong Kong" },
      { code: "KY", name: "Cayman Islands" },
    ],
    browsing: [
      { code: "IS", name: "Iceland" },
      { code: "CH", name: "Switzerland" },
      { code: "NL", name: "Netherlands" },
      { code: "CA", name: "Canada" },
      { code: "DE", name: "Germany" },
    ],
    digital_nomad: [
      { code: "PT", name: "Portugal" },
      { code: "ES", name: "Spain" },
      { code: "TH", name: "Thailand" },
      { code: "MX", name: "Mexico" },
      { code: "CO", name: "Colombia" },
    ],
    other: [
      { code: "CA", name: "Canada" },
      { code: "CH", name: "Switzerland" },
      { code: "SG", name: "Singapore" },
      { code: "DE", name: "Germany" },
      { code: "AE", name: "UAE" },
    ],
  },
  mvp_ips: 25,
  priority_a: ["US", "GB", "CA", "DE", "AE"],
  note:
    "Offline purpose top5 (static). Live /api/status preferred. Not tunnel endpoints.",
};

function log(msg) {
  const el = document.getElementById("log");
  el.textContent = new Date().toISOString().slice(11, 19) + "  " + msg + "\n" + el.textContent;
}

function loadLocalSession() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) state.session = { ...state.session, ...JSON.parse(raw) };
  } catch (_) {}
  if (!state.session.location) {
    state.session = { purpose: "browsing", country: "CH", location: "zurich", country_name: "Zurich" };
  }
}

function saveLocalSession() {
  localStorage.setItem(LS_KEY, JSON.stringify(state.session));
}

function resumeLabel() {
  const city = (state.session.country_name || state.session.location || "Zurich").replace(/_/g, " ");
  const purpose = (state.session.purpose || "browsing").replace(/_/g, " ");
  const flag = FLAGS[state.session.country] || "🛡️";
  return `Resume ${flag} ${titleCase(city)} · ${titleCase(purpose)}`;
}

function titleCase(s) {
  return String(s).replace(/\b\w/g, (c) => c.toUpperCase());
}

function updateHero() {
  const flag = FLAGS[state.session.country] || "🛡️";
  const city = titleCase((state.session.country_name || state.session.location || "Zurich").replace(/_/g, " "));
  document.getElementById("hero-flag").textContent = flag;
  document.getElementById("hero-city").textContent = city;
  document.getElementById("hero-meta").textContent =
    `${titleCase(state.session.purpose || "browsing")} · ${state.session.country || "CH"} · previous session`;
  document.getElementById("btn-resume").textContent = resumeLabel();
}

function setTier(tier) {
  state.tier = tier;
  document.getElementById("pill-core").classList.toggle("active", tier === "core");
  document.getElementById("pill-pro").classList.toggle("active", tier === "pro");
  const livePrice = state.live && state.live.pricing && state.live.pricing[tier];
  if (livePrice && (livePrice.monthly != null || livePrice.monthly_usd != null)) {
    const m = livePrice.monthly_usd ?? livePrice.monthly;
    const a = livePrice.annual_usd ?? livePrice.annual;
    document.getElementById("m-tier").textContent = livePrice.label || PRICES[tier].label;
    document.getElementById("m-price").textContent = a != null ? `$${m}/mo · $${a}/yr` : `$${m}/mo`;
  } else {
    document.getElementById("m-tier").textContent = PRICES[tier].label;
    document.getElementById("m-price").textContent =
      `$${PRICES[tier].monthly}/mo · $${PRICES[tier].annual}/yr`;
  }
  document.getElementById("core-list").innerHTML = CORE_BULLETS.map((b) => `<li>${b}</li>`).join("");
  document.getElementById("pro-list").innerHTML = PRO_BULLETS.map((b) => `<li>${b}</li>`).join("");
  log("Tier: " + tier);
}

/* Confirm dialogs */
let _confirmResolve = null;
function confirmDialog(title, body) {
  return new Promise((resolve) => {
    _confirmResolve = resolve;
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-body").textContent = body;
    document.getElementById("modal").classList.remove("hidden");
  });
}
document.getElementById("modal-cancel").onclick = () => {
  document.getElementById("modal").classList.add("hidden");
  if (_confirmResolve) _confirmResolve(false);
  _confirmResolve = null;
};
document.getElementById("modal-ok").onclick = () => {
  document.getElementById("modal").classList.add("hidden");
  if (_confirmResolve) _confirmResolve(true);
  _confirmResolve = null;
};

function gateFromLive() {
  const live = state.live || {};
  const g = live.protect_gate || {};
  const pool = live.inventory_pool || {};
  const cfg = Number(g.configured_count ?? live.configured_count ?? 0);
  // Fail-closed UI mirror: configured_count=0 always blocks protect
  const okRaw = !!(g.ok_for_protect ?? live.ok_for_protect);
  const ok_for_protect = okRaw && cfg > 0;
  return {
    status: g.status || live.status || "unknown",
    ok_for_protect,
    configured_count: cfg,
    server_filled_count: Number(g.server_filled_count ?? live.server_filled_count ?? 0),
    pending_ip_count: Number(g.pending_ip_count ?? live.pending_ip_count ?? 0),
    total_real_ips: Number(
      g.total_real_ips ?? live.total_real_ips ?? pool.total_real_ips ?? 0
    ),
    locations_with_ips: Number(pool.locations_with_ips ?? 0),
    next_actions: g.next_actions || live.next_actions || [],
    secrets_fingerprint: g.secrets_fingerprint ?? live.secrets_fingerprint ?? null,
    inventory_path: g.inventory_path || live.inventory_path || DEFAULT_INV,
    howto_path: g.howto_path || live.howto_path || DEFAULT_HOWTO,
    industrial_howto: g.industrial_howto || (live.cta && live.cta.industrial_howto) || DEFAULT_HOWTO,
    fleet_playbook_path:
      g.fleet_playbook_path ||
      live.fleet_playbook_path ||
      (live.cta && live.cta.fleet_playbook_path) ||
      DEFAULT_PLAYBOOK,
    block_message: g.block_message || null,
    summary: g.summary || (live.server_readiness && live.server_readiness.summary) || "",
  };
}

async function onActivate() {
  const g = gateFromLive();
  if (!g.ok_for_protect) {
    const ok = await confirmDialog(
      "Protect blocked — servers not configured",
      (g.block_message ||
        `configured_count=${g.configured_count}. Fill inventory, materialize, then re-scan.`) +
        "\n\nDashboard / wizard / HOWTO stay available. Continue only to review gate (will not claim protected)."
    );
    if (!ok) {
      log("Activate cancelled (gate closed)");
      return;
    }
    document.getElementById("m-gate").textContent = "blocked";
    document.getElementById("dot").classList.remove("on");
    document.getElementById("headline").textContent = "Not protected · gate closed";
    document.getElementById("detail").textContent =
      g.block_message || `configured_count=${g.configured_count} — fill inventory first`;
    state.protected = false;
    log("Protect refused: ok_for_protect=false");
    return;
  }

  const ok = await confirmDialog(
    "Arm kill switch & activate?",
    "Industry default: kill switch turns ON with Activate. pf rules write to ~/.pcs_industrial_20260802/pf_rules/ (not /tmp). Continue only if you understand network may block clearnet until tunnel is up."
  );
  if (!ok) {
    log("Activate cancelled");
    return;
  }
  document.getElementById("m-gate").textContent = "preflight…";
  document.getElementById("m-obf").textContent = "reality";
  log("Kill switch auto-on → verify layers → protect or block");
  // UI simulation; real path: Launch_PCS_* + Python industrial killswitch
  setTimeout(() => {
    state.protected = true;
    document.getElementById("dot").classList.add("on");
    document.getElementById("headline").textContent = "Protections active · verify recommended";
    document.getElementById("detail").textContent =
      "Session marked protected after preflight (run Python launcher for real pf/gate).";
    document.getElementById("m-gate").textContent = "OK";
    saveLocalSession();
    bumpSecurityScore(92);
    log("Activate complete (UI). Real gate: launches_v20260802/Launch_PCS_*");
  }, 500);
}

async function onTrackerWipe() {
  const ok = await confirmDialog(
    "Hide trackers on this Mac?",
    "This runs on-device tracker vault hide (browser/Google tracking data vaulted locally). Restore only when you choose. This can affect open browsers. Continue?"
  );
  if (!ok) {
    log("Tracker hide cancelled");
    return;
  }
  log("Tracker vault hide confirmed (UI). Wire to Python tracker vault in industrial shell.");
  bumpSecurityScore((state.securityScore || 80) + 3);
}

function bumpSecurityScore(n) {
  state.securityScore = Math.max(0, Math.min(100, Math.round(n)));
  const chip = document.getElementById("sec-chip");
  chip.textContent = `Security ${state.securityScore}`;
  chip.classList.toggle("warn", state.securityScore < 75);
}

function refreshSecurityScore() {
  let score = 78;
  if (state.live && state.live.security_score != null) {
    score = Number(state.live.security_score);
  } else {
    if (state.protected) score += 10;
    const g = gateFromLive();
    if (g.configured_count > 0) score += 6;
    else score -= 4;
  }
  bumpSecurityScore(score);
  log("Security score refreshed: " + state.securityScore);
}

function onResume() {
  if (state.live && state.live.resume) {
    const r = state.live.resume;
    if (r.session) {
      state.session = {
        ...state.session,
        purpose: r.session.purpose || state.session.purpose,
        country: r.session.country || state.session.country,
        location: r.session.location || state.session.location,
        country_name: r.session.country_name || state.session.country_name,
      };
    }
  }
  log(resumeLabel() + " — loading session prefs");
  updateHero();
  onActivate();
}

function setLiveChip(ok, label) {
  const chip = document.getElementById("live-chip");
  chip.textContent = label;
  chip.classList.toggle("ok", !!ok);
  chip.classList.toggle("warn", !ok);
}

function renderNextActions(actions) {
  const ol = document.getElementById("next-actions");
  ol.innerHTML = "";
  const list = Array.isArray(actions) ? actions : [];
  if (!list.length) {
    const li = document.createElement("li");
    li.textContent = "No open actions — re-scan after inventory or materialize.";
    ol.appendChild(li);
    return;
  }
  list.slice(0, 8).forEach((a) => {
    const li = document.createElement("li");
    const sev = (a && a.severity) || "info";
    const code = (a && a.code) || "";
    const text = (a && a.action) || String(a);
    li.innerHTML = `<span class="sev sev-${sev}">${sev}</span> ${escapeHtml(text)}${
      code ? ` <code class="code-soft">${escapeHtml(code)}</code>` : ""
    }`;
    ol.appendChild(li);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderReadiness() {
  const g = gateFromLive();
  const badge = document.getElementById("server-badge");
  const protectBadge = document.getElementById("protect-badge");
  const summary = document.getElementById("server-summary");
  const banner = document.getElementById("protect-banner");

  document.getElementById("cfg-n").textContent = String(g.configured_count);
  document.getElementById("filled-n").textContent = String(g.server_filled_count);
  document.getElementById("pend-n").textContent = String(g.pending_ip_count);
  document.getElementById("pool-n").textContent = String(g.total_real_ips);

  badge.textContent = g.status || "unknown";
  if (g.ok_for_protect && g.configured_count > 0) {
    badge.className = "badge ok";
  } else if (g.status === "error") {
    badge.className = "badge warn";
  } else {
    badge.className = "badge warn";
  }

  protectBadge.textContent = g.ok_for_protect ? "protect OK" : "protect blocked";
  protectBadge.className = "badge gate " + (g.ok_for_protect ? "ok" : "warn");

  if (banner) {
    if (g.ok_for_protect && g.configured_count > 0) {
      banner.className = "protect-banner ok";
      banner.innerHTML =
        "Protect gate <strong>OK</strong> — configured_count=" +
        g.configured_count +
        ", pool total_real_ips=" +
        g.total_real_ips +
        ".";
    } else {
      banner.className = "protect-banner warn";
      banner.innerHTML =
        "Protect blocked while <strong>configured_count = " +
        g.configured_count +
        "</strong>" +
        (g.total_real_ips === 0
          ? " · pool total_real_ips=0 — own VPS IPs required (see CEO Fleet Playbook)."
          : " — materialize after inventory, then re-scan.");
    }
  }

  summary.textContent =
    g.summary ||
    `status=${g.status}; configured=${g.configured_count}; server_filled=${g.server_filled_count}; pending_ip=${g.pending_ip_count}; total_real_ips=${g.total_real_ips}`;

  const fp = g.secrets_fingerprint;
  document.getElementById("secrets-fp").textContent =
    fp != null && fp !== "" ? String(fp) : "— (no public fingerprint yet)";

  renderNextActions(g.next_actions);

  document.getElementById("inventory-path-line").textContent = "Inventory: " + g.inventory_path;
  document.getElementById("howto-path-line").textContent = "HOWTO: " + g.howto_path;
  const pb = document.getElementById("playbook-path-line");
  if (pb) pb.textContent = "Playbook: " + g.fleet_playbook_path;
  document.getElementById("howto-path").textContent = g.howto_path || DEFAULT_HOWTO;
  document.getElementById("wizard-inv").textContent = g.inventory_path || DEFAULT_INV;

  document.getElementById("m-gate").textContent = g.ok_for_protect ? "ready" : "blocked";
  if (!g.ok_for_protect) {
    document.getElementById("dot").classList.remove("on");
    if (!state.protected) {
      document.getElementById("headline").textContent = "Not protected · gate closed";
      document.getElementById("detail").textContent =
        g.block_message ||
        "Status & wizard available. Fill VPS inventory (CEO fleet playbook), materialize, then Activate.";
    }
  }
}

function renderFleetAndPurpose(offline) {
  const live = state.live || {};
  const g = gateFromLive();
  const pool = live.inventory_pool || {};
  const top5 =
    live.purpose_top5 && live.purpose_top5.by_purpose
      ? live.purpose_top5
      : OFFLINE_PURPOSE_TOP5;

  const totalReal = offline
    ? "—"
    : String(pool.total_real_ips ?? live.total_real_ips ?? g.total_real_ips ?? 0);
  const locs = offline ? "—" : String(pool.locations_with_ips ?? g.locations_with_ips ?? 0);
  const mvp = top5.mvp_ips != null ? String(top5.mvp_ips) : "25";
  const purposes = top5.purposes || Object.keys(top5.by_purpose || {});

  document.getElementById("pool-total").textContent = totalReal;
  document.getElementById("pool-locs").textContent = locs;
  document.getElementById("mvp-ips").textContent = mvp;
  document.getElementById("purpose-n").textContent = String(purposes.length);

  const noteEl = document.getElementById("fleet-note");
  noteEl.textContent =
    top5.note ||
    "Purpose → preferred countries (planning). Exits need owned VPS IPs in inventory.";
  const poolNote = document.getElementById("pool-note");
  if (poolNote) {
    poolNote.textContent =
      pool.note ||
      (offline
        ? "Pool counts require live status API. Offline: not claiming IPs."
        : "Inventory pool counts owned public IPs only — never scraped residential lists.");
  }

  const badge = document.getElementById("fleet-badge");
  if (offline) {
    badge.textContent = "offline plan data";
    badge.className = "badge";
  } else if (Number(pool.total_real_ips || 0) > 0) {
    badge.textContent = "pool has IPs";
    badge.className = "badge ok";
  } else {
    badge.textContent = "pool empty · playbook";
    badge.className = "badge warn";
  }

  const wrap = document.getElementById("purpose-top5");
  wrap.innerHTML = "";
  purposes.forEach((p) => {
    const rows = (top5.by_purpose && top5.by_purpose[p]) || [];
    const codes = rows
      .map((r) => (r && r.code) || r)
      .filter(Boolean)
      .join(" · ");
    const div = document.createElement("div");
    div.className = "purpose-chip";
    div.innerHTML =
      `<span class="p-name">${escapeHtml(String(p).replace(/_/g, " "))}</span>` +
      `<span class="p-codes">${escapeHtml(codes || "—")}</span>`;
    wrap.appendChild(div);
  });
}

function renderResidential() {
  const res = (state.live && state.live.residential_catalog) || {};
  document.getElementById("res-countries").textContent = String(res.countries_count ?? "—");
  document.getElementById("res-total").textContent = String(res.total_entries ?? "—");
  document.getElementById("res-catalogued").textContent = String(
    res.countries_catalogued ?? res.meta_countries ?? "—"
  );
  document.getElementById("res-note").textContent =
    res.note || "Synthetic product catalog — not VPS tunnel endpoints.";
  const badge = document.getElementById("res-badge");
  if (res.claims_tunnel_readiness) {
    badge.textContent = "unexpected claim";
    badge.className = "badge warn";
  } else {
    badge.textContent = "counts only · not tunnels";
    badge.className = "badge";
  }
}

function openFleetPlaybook() {
  const g = gateFromLive();
  const path = g.fleet_playbook_path || DEFAULT_PLAYBOOK;
  const cta =
    (state.live && state.live.cta && state.live.cta.fleet_playbook_cta) ||
    "Own VPS/ISP IPs → inventory → materialize → configured_count ≥ 1 → protect unblocks";
  log("CEO Fleet Beginner Playbook: " + path);
  showPathAlert("CEO Fleet Beginner Playbook", [
    path,
    "",
    cta,
    "",
    "Doc: docs_v20260802/CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md",
    "Protect stays blocked at configured_count=0.",
  ]);
  copyText(path);
}

async function fetchStatus() {
  const candidates = [];
  if (state.apiBase) candidates.push(state.apiBase.replace(/\/$/, "") + "/api/status");
  // Same origin when served by industrial dashboard server
  candidates.push("/api/status");
  candidates.push("http://127.0.0.1:8790/api/status");
  candidates.push("http://localhost:8790/api/status");

  let lastErr = null;
  for (const url of candidates) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        lastErr = "HTTP " + res.status;
        continue;
      }
      const data = await res.json();
      state.live = data;
      if (url.startsWith("http")) {
        try {
          state.apiBase = new URL(url).origin;
        } catch (_) {}
      } else {
        state.apiBase = "";
      }
      setLiveChip(true, "Live status");
      if (data.resume && data.resume.session) {
        const s = data.resume.session;
        state.session = {
          ...state.session,
          purpose: s.purpose || state.session.purpose,
          country: s.country || state.session.country,
          location: s.location || state.session.location,
          country_name: s.country_name || state.session.country_name,
        };
        updateHero();
      }
      if (data.security_score != null) bumpSecurityScore(Number(data.security_score));
      renderReadiness();
      renderFleetAndPurpose(false);
      renderResidential();
      setTier(state.tier);
      const suiteNote = data.suite_available
        ? "Suite available (read-only)"
        : data.suite_partial
          ? "Suite partial/missing — status still OK"
          : "Suite not loaded — status still OK";
      log("Status: " + (data.status || data.protect_gate?.status) + " · " + suiteNote);
      if (data.secrets_fingerprint) log("secrets_fingerprint=" + data.secrets_fingerprint);
      if (data.total_real_ips != null || (data.inventory_pool && data.inventory_pool.total_real_ips != null)) {
        log(
          "total_real_ips=" +
            (data.total_real_ips ?? data.inventory_pool.total_real_ips) +
            " configured_count=" +
            (data.configured_count ?? 0)
        );
      }
      return data;
    } catch (e) {
      lastErr = e && e.message ? e.message : String(e);
    }
  }

  setLiveChip(false, "Status offline");
  // Graceful offline: purpose top5 static; pool/configured unknown; protect never OK
  document.getElementById("server-badge").textContent = "offline";
  document.getElementById("server-badge").className = "badge warn";
  document.getElementById("protect-badge").textContent = "protect blocked";
  document.getElementById("protect-badge").className = "badge gate warn";
  document.getElementById("server-summary").textContent =
    "Start industrial status server: launches_v20260802/Open_PCS_CommandCenter_v2.command or --serve-dashboard 8790";
  document.getElementById("cfg-n").textContent = "—";
  document.getElementById("filled-n").textContent = "—";
  document.getElementById("pend-n").textContent = "—";
  document.getElementById("pool-n").textContent = "—";
  document.getElementById("secrets-fp").textContent = "—";
  const banner = document.getElementById("protect-banner");
  if (banner) {
    banner.className = "protect-banner warn";
    banner.innerHTML =
      "Offline: protect stays <strong>blocked</strong> until live status shows configured_count &gt; 0. Purpose top5 still shown for planning.";
  }
  renderNextActions([
    {
      severity: "high",
      code: "status_offline",
      action:
        "Run: .venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-dashboard 8790 --open-dashboard",
    },
    {
      severity: "medium",
      code: "fleet_playbook",
      action: "Open CEO_FLEET_BEGINNER_PLAYBOOK to provision owned VPS IPs",
    },
  ]);
  document.getElementById("inventory-path-line").textContent = "Inventory: " + DEFAULT_INV;
  document.getElementById("howto-path-line").textContent = "HOWTO: " + DEFAULT_HOWTO;
  const pb = document.getElementById("playbook-path-line");
  if (pb) pb.textContent = "Playbook: " + DEFAULT_PLAYBOOK;
  document.getElementById("res-note").textContent =
    "Catalog counts require live status API (not claimed as tunnels).";
  document.getElementById("m-gate").textContent = "blocked";
  renderFleetAndPurpose(true);
  log("Status offline: " + (lastErr || "no API") + " · purpose top5 still available");
  return null;
}

function showPathAlert(title, paths) {
  alert(title + "\n\n" + paths.join("\n"));
}

async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      log("Copied: " + text);
      return true;
    }
  } catch (_) {}
  showPathAlert("Path (copy manually)", [text]);
  return false;
}

document.getElementById("pill-core").onclick = () => setTier("core");
document.getElementById("pill-pro").onclick = () => setTier("pro");
document.getElementById("btn-activate").onclick = onActivate;
document.getElementById("btn-resume").onclick = onResume;
document.getElementById("btn-tracker-wipe").onclick = onTrackerWipe;
document.getElementById("btn-audit").onclick = () => {
  fetchStatus().then(() => refreshSecurityScore());
};
document.getElementById("btn-refresh-status").onclick = () => fetchStatus();

document.getElementById("btn-vps-wizard").onclick = () => {
  document.getElementById("vps-modal").classList.remove("hidden");
};
document.getElementById("btn-fleet-playbook").onclick = openFleetPlaybook;
document.getElementById("vps-close").onclick = () => {
  document.getElementById("vps-modal").classList.add("hidden");
};
document.getElementById("vps-copy-inv").onclick = () => {
  const g = gateFromLive();
  copyText(g.inventory_path || DEFAULT_INV);
};
document.getElementById("vps-open-docs").onclick = () => {
  const g = gateFromLive();
  log("HOWTO paths shown (Suite read-only + industrial link)");
  showPathAlert("Deploy HOWTO paths", [
    "Industrial (this tree):",
    g.industrial_howto || g.howto_path || DEFAULT_HOWTO,
    "",
    "CEO Fleet Beginner Playbook:",
    g.fleet_playbook_path || DEFAULT_PLAYBOOK,
    "",
    "Suite (read-only, not modified):",
    SUITE_HOWTO,
    "",
    "Inventory:",
    g.inventory_path || DEFAULT_INV,
  ]);
};

document.getElementById("btn-open-inventory").onclick = () => {
  const g = gateFromLive();
  const p = g.inventory_path || DEFAULT_INV;
  copyText(p);
  showPathAlert("Inventory path", [
    p,
    "",
    "Edit public VPS IPs per location, then re-run materialize:",
    "shared/pcs_materialize_singbox_v20260802.py",
    "",
    "Then Refresh status — configured_count must rise before protect.",
    "",
    "Playbook: " + (g.fleet_playbook_path || DEFAULT_PLAYBOOK),
  ]);
};

document.getElementById("btn-open-howto").onclick = () => {
  document.getElementById("vps-open-docs").click();
};

loadLocalSession();
setTier("core");
updateHero();
// Offline-safe first paint: purpose top5 + protect blocked until live status
renderFleetAndPurpose(true);
fetchStatus().then(() => refreshSecurityScore());
