/* PCS Industrial command center UI demo (static). Launchers run real Python gates. */
const state = { tier: "core", protected: false };

const PRICES = {
  core: { monthly: 8.99, annual: 71.88, label: "PhantomCloak Core" },
  pro: { monthly: 24.99, annual: 239.88, label: "PhantomCloak Pro" },
};

const CORE_BULLETS = [
  "Zero-leak preflight before any protected send",
  "Kill switch fail-closed on layer failure",
  "On-device tracker vault (hide / restore on request)",
  "DNS / WebRTC / IPv6 leak guards",
  "Auto obfuscation (REALITY / QUIC / …)",
];
const PRO_BULLETS = [
  "Everything in Core",
  "RBAC + workspaces + audit log",
  "Residential pool + IP health (config)",
  "Multi-hop / Double Onion (config)",
  "Always-on watchdog + API/automation scaffolds",
];

function log(msg) {
  const el = document.getElementById("log");
  el.textContent = new Date().toISOString() + "  " + msg + "\n" + el.textContent;
}

function setTier(tier) {
  state.tier = tier;
  document.getElementById("pill-core").classList.toggle("active", tier === "core");
  document.getElementById("pill-pro").classList.toggle("active", tier === "pro");
  document.getElementById("m-tier").textContent = PRICES[tier].label;
  document.getElementById("m-price").textContent =
    "$" + PRICES[tier].monthly + "/mo · $" + PRICES[tier].annual + "/yr";
  document.getElementById("core-list").innerHTML = CORE_BULLETS.map((b) => `<li>${b}</li>`).join("");
  document.getElementById("pro-list").innerHTML = PRO_BULLETS.map((b) => `<li>${b}</li>`).join("");
  log("Tier selected: " + tier);
}

function simulateActivate() {
  // UI-only simulation; real gate is Python pcs_preflight_obfuscation_gate_v20260802
  document.getElementById("m-obf").textContent = "reality";
  document.getElementById("m-gate").textContent = "running…";
  log("Preflight: arm killswitch → verify layers → allow or trip");
  setTimeout(() => {
    state.protected = true;
    document.getElementById("dot").classList.add("on");
    document.getElementById("headline").textContent = "Protected (demo UI)";
    document.getElementById("detail").textContent =
      "Run Launch_PCS_*_v20260802.command for real Python fail-closed gate.";
    document.getElementById("m-gate").textContent = "OK (demo)";
    log("Demo protected — use Python launchers for real verification");
  }, 600);
}

document.getElementById("pill-core").onclick = () => setTier("core");
document.getElementById("pill-pro").onclick = () => setTier("pro");
document.getElementById("btn-activate").onclick = simulateActivate;
document.getElementById("btn-audit").onclick = () => {
  log("See docs_v20260802/CODE_REVIEW_SECURITY_AUDIT_v20260802.md and run /security_audit workflow");
  alert("Open docs_v20260802/CODE_REVIEW_SECURITY_AUDIT_v20260802.md\nRun workflow: /security_audit");
};

setTier("core");
