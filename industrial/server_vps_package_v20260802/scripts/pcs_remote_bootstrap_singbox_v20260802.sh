#!/usr/bin/env bash
# Industrial remote bootstrap for sing-box on Ubuntu 22.04 / 24.04
# Idempotent: safe to re-run. Designed to run ON the VPS (via ssh).
#
# Expects (optional) staged files under /tmp/pcs_stage/ before invoke, or args:
#   CONFIG   → /tmp/pcs_stage/config.json  (or --config PATH)
#   CERTS    → /tmp/pcs_stage/hy2_certs/<location>/{fullchain,privkey}.pem
#
# Usage (on VPS as root or sudo-capable):
#   sudo bash pcs_remote_bootstrap_singbox_v20260802.sh --location dubai
#   sudo bash pcs_remote_bootstrap_singbox_v20260802.sh --location dubai --dry-run
#   sudo bash pcs_remote_bootstrap_singbox_v20260802.sh --location dubai --config /tmp/cfg.json
#
# Ports opened (ufw): 443/tcp 443/udp 8443/udp 22/tcp
# Does NOT disable ufw or open arbitrary ports.

set -euo pipefail

LOCATION=""
CONFIG_SRC="/tmp/pcs_stage/config.json"
STAGE_DIR="/tmp/pcs_stage"
DRY_RUN=0
SKIP_INSTALL=0
SKIP_UFW=0
ENABLE_UFW=1

log()  { printf '[pcs-bootstrap] %s\n' "$*"; }
warn() { printf '[pcs-bootstrap] WARN: %s\n' "$*" >&2; }
die()  { printf '[pcs-bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: $*"
    return 0
  fi
  # shellcheck disable=SC2086
  eval "$@"
}

usage() {
  cat <<'EOF'
pcs_remote_bootstrap_singbox_v20260802.sh — Ubuntu 22.04/24.04 sing-box bootstrap

Options:
  --location NAME     Location key (dubai, hongkong, …)  [required]
  --config PATH       Staged config JSON (default: /tmp/pcs_stage/config.json)
  --stage-dir PATH    Staging root (default: /tmp/pcs_stage)
  --dry-run           Print actions only; no install/copy/systemctl/ufw
  --skip-install      Do not install sing-box package if missing
  --skip-ufw          Do not touch ufw rules
  --no-enable-ufw     Allow rules but do not `ufw --force enable`
  -h, --help          This help

Idempotent layout:
  /etc/sing-box/config.json
  /etc/sing-box/hy2_certs/<location>/{fullchain,privkey}.pem
  systemctl enable --now sing-box
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --location) LOCATION="${2:-}"; shift 2 ;;
    --config) CONFIG_SRC="${2:-}"; shift 2 ;;
    --stage-dir) STAGE_DIR="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --skip-ufw) SKIP_UFW=1; shift ;;
    --no-enable-ufw) ENABLE_UFW=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

[[ -n "$LOCATION" ]] || die "--location is required"
LOCATION="$(printf '%s' "$LOCATION" | tr '[:upper:]' '[:lower:]')"

if [[ "$DRY_RUN" -eq 0 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      log "re-exec with sudo"
      exec sudo -E bash "$0" --location "$LOCATION" --config "$CONFIG_SRC" \
        --stage-dir "$STAGE_DIR" \
        $([ "$SKIP_INSTALL" -eq 1 ] && echo --skip-install) \
        $([ "$SKIP_UFW" -eq 1 ] && echo --skip-ufw) \
        $([ "$ENABLE_UFW" -eq 0 ] && echo --no-enable-ufw)
    fi
    die "must run as root (or with sudo)"
  fi
fi

ETC_SB="/etc/sing-box"
HY2_DIR="${ETC_SB}/hy2_certs/${LOCATION}"

# --- detect OS (informational) ---
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  log "host=${HOSTNAME:-unknown} os=${PRETTY_NAME:-unknown} loc=${LOCATION}"
else
  log "host=${HOSTNAME:-unknown} os=unknown loc=${LOCATION}"
fi

# --- packages: curl ufw ---
ensure_pkg() {
  local pkg="$1"
  if dpkg -s "$pkg" >/dev/null 2>&1; then
    log "package present: $pkg"
    return 0
  fi
  log "installing package: $pkg"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: apt-get install -y $pkg"
    return 0
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq "$pkg"
}

if [[ "$DRY_RUN" -eq 0 ]]; then
  ensure_pkg curl
  ensure_pkg ca-certificates
  if [[ "$SKIP_UFW" -eq 0 ]]; then
    ensure_pkg ufw
  fi
else
  log "DRY-RUN: would ensure packages: curl ca-certificates ufw"
fi

# --- sing-box install if missing ---
install_singbox() {
  if command -v sing-box >/dev/null 2>&1; then
    log "sing-box already installed: $(sing-box version 2>/dev/null | head -1 || echo present)"
    return 0
  fi
  if [[ "$SKIP_INSTALL" -eq 1 ]]; then
    die "sing-box missing and --skip-install set"
  fi
  log "installing sing-box via official deb-install.sh"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: bash <(curl -fsSL https://sing-box.sagernet.org/deb-install.sh)"
    return 0
  fi
  curl -fsSL https://sing-box.sagernet.org/deb-install.sh -o /tmp/pcs_singbox_deb_install.sh
  bash /tmp/pcs_singbox_deb_install.sh
  command -v sing-box >/dev/null 2>&1 || die "sing-box install failed"
  log "sing-box installed: $(sing-box version 2>/dev/null | head -1 || true)"
}

install_singbox

# --- layout ---
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN: mkdir -p ${ETC_SB} ${HY2_DIR}"
else
  mkdir -p "$ETC_SB" "$HY2_DIR"
fi

# --- place config ---
if [[ -f "$CONFIG_SRC" ]]; then
  log "install config: $CONFIG_SRC → ${ETC_SB}/config.json"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: install -m 600 $CONFIG_SRC ${ETC_SB}/config.json"
  else
    install -m 600 "$CONFIG_SRC" "${ETC_SB}/config.json"
  fi
elif [[ -f "${ETC_SB}/config.json" ]]; then
  log "config already at ${ETC_SB}/config.json (no staged source)"
else
  if [[ "$DRY_RUN" -eq 1 ]]; then
    warn "no config at $CONFIG_SRC (dry-run continues; live mode would fail)"
    log "DRY-RUN: would require staged config → ${ETC_SB}/config.json"
  else
    die "no config at $CONFIG_SRC and none at ${ETC_SB}/config.json"
  fi
fi

# --- hy2 certs from stage ---
STAGE_HY2="${STAGE_DIR}/hy2_certs/${LOCATION}"
if [[ -d "$STAGE_HY2" ]]; then
  for f in fullchain.pem privkey.pem; do
    if [[ -f "${STAGE_HY2}/${f}" ]]; then
      log "install cert: ${STAGE_HY2}/${f} → ${HY2_DIR}/${f}"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        log "DRY-RUN: install -m 600 ${STAGE_HY2}/${f} ${HY2_DIR}/${f}"
      else
        install -m 600 "${STAGE_HY2}/${f}" "${HY2_DIR}/${f}"
      fi
    fi
  done
else
  # also accept flat stage: /tmp/pcs_stage/fullchain.pem
  for f in fullchain.pem privkey.pem; do
    if [[ -f "${STAGE_DIR}/${f}" ]]; then
      log "install cert (flat stage): ${STAGE_DIR}/${f} → ${HY2_DIR}/${f}"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        log "DRY-RUN: install -m 600 ${STAGE_DIR}/${f} ${HY2_DIR}/${f}"
      else
        install -m 600 "${STAGE_DIR}/${f}" "${HY2_DIR}/${f}"
      fi
    fi
  done
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  chmod 700 "${ETC_SB}/hy2_certs" 2>/dev/null || true
  chmod 700 "$HY2_DIR" 2>/dev/null || true
fi

# --- sing-box check ---
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN: sing-box check -c ${ETC_SB}/config.json"
  if [[ -f "$CONFIG_SRC" ]] && command -v sing-box >/dev/null 2>&1; then
    # Optional local validation of staged config when available
    if sing-box check -c "$CONFIG_SRC" 2>/dev/null; then
      log "DRY-RUN: staged config validates with local sing-box"
    else
      warn "DRY-RUN: staged config not validated (missing paths on this host is OK)"
    fi
  fi
else
  if command -v sing-box >/dev/null 2>&1; then
    log "running: sing-box check -c ${ETC_SB}/config.json"
    sing-box check -c "${ETC_SB}/config.json" || die "sing-box check failed"
    log "sing-box check: OK"
  else
    die "sing-box binary not found after install"
  fi
fi

# --- systemd unit (package usually ships one; ensure enable) ---
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN: systemctl enable --now sing-box && systemctl restart sing-box"
else
  if systemctl list-unit-files | grep -q '^sing-box\.service'; then
    systemctl enable sing-box
    systemctl restart sing-box
    systemctl --no-pager --full status sing-box | head -20 || true
    systemctl is-active --quiet sing-box || die "sing-box service not active"
    log "systemd: sing-box active"
  else
    warn "sing-box.service not found — starting manually is not managed; install package unit"
    # fallback: try enable anyway
    systemctl enable --now sing-box 2>/dev/null || warn "could not enable sing-box unit"
  fi
fi

# --- ufw ---
if [[ "$SKIP_UFW" -eq 0 ]]; then
  for rule in "443/tcp" "443/udp" "8443/udp" "22/tcp"; do
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "DRY-RUN: ufw allow ${rule}"
    else
      ufw allow "${rule}" >/dev/null 2>&1 || ufw allow "${rule}" || warn "ufw allow ${rule} failed"
      log "ufw allow ${rule}"
    fi
  done
  if [[ "$ENABLE_UFW" -eq 1 ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "DRY-RUN: ufw --force enable"
    else
      ufw --force enable || warn "ufw enable failed"
      log "ufw enabled"
    fi
  fi
else
  log "skipping ufw (--skip-ufw)"
fi

# --- health echo ---
HEALTH_OK=1
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN health: would verify systemctl is-active sing-box + config present"
  HEALTH_OK=1
else
  if ! systemctl is-active --quiet sing-box 2>/dev/null; then
    HEALTH_OK=0
  fi
  if [[ ! -f "${ETC_SB}/config.json" ]]; then
    HEALTH_OK=0
  fi
fi

if [[ "$HEALTH_OK" -eq 1 ]]; then
  log "HEALTH OK location=${LOCATION} config=${ETC_SB}/config.json dry_run=${DRY_RUN}"
  echo "PCS_BOOTSTRAP_HEALTH=OK location=${LOCATION}"
  exit 0
else
  log "HEALTH FAIL location=${LOCATION}"
  echo "PCS_BOOTSTRAP_HEALTH=FAIL location=${LOCATION}"
  exit 1
fi
