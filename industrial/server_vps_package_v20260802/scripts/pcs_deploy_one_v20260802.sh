#!/usr/bin/env bash
# Deploy one filled industrial sing-box package to a single VPS.
# Industrial tree only — does not modify PhantomCloak Suite deploy_all.sh.
#
# Usage:
#   pcs_deploy_one_v20260802.sh [--dry-run] user@host location
#   pcs_deploy_one_v20260802.sh --dry-run root@203.0.113.10 dubai
#
# Args:
#   user@host   SSH target (no real IPs required for --dry-run demos)
#   location    dubai | hongkong | vancouver | germany | bahamas | cayman | mauritius | seychelles
#
# Environment:
#   PCS_VPS_PKG     Override package dir (default: ~/.pcs_industrial_20260802/vps_server_package)
#   PCS_SSH_OPTS    Extra ssh/scp options (default: -o StrictHostKeyChecking=accept-new)
#   PCS_DRY_RUN=1   Same as --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_PKG="${PCS_VPS_PKG:-${HOME}/.pcs_industrial_20260802/vps_server_package}"
# Prefer co-located scripts; fall back to state package copy
REWRITE_PY="${SCRIPT_DIR}/pcs_rewrite_singbox_paths_v20260802.py"
BOOTSTRAP_SH="${SCRIPT_DIR}/pcs_remote_bootstrap_singbox_v20260802.sh"
if [[ ! -f "$REWRITE_PY" ]]; then
  REWRITE_PY="${STATE_PKG}/scripts/pcs_rewrite_singbox_paths_v20260802.py"
fi
if [[ ! -f "$BOOTSTRAP_SH" ]]; then
  BOOTSTRAP_SH="${STATE_PKG}/scripts/pcs_remote_bootstrap_singbox_v20260802.sh"
fi

SSH_OPTS="${PCS_SSH_OPTS:--o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new}"
DRY_RUN="${PCS_DRY_RUN:-0}"
TARGET=""
LOCATION=""

log()  { printf '[pcs-deploy-one] %s\n' "$*"; }
die()  { printf '[pcs-deploy-one] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: pcs_deploy_one_v20260802.sh [--dry-run] user@host location

  --dry-run     Print scp/ssh plan; rewrite config locally to /tmp; no network
  user@host     SSH destination (e.g. root@YOUR_VPS_IP)
  location      One of: dubai hongkong vancouver germany bahamas cayman mauritius seychelles

Examples:
  # Safe local demo (no VPS, no network):
  ./pcs_deploy_one_v20260802.sh --dry-run root@203.0.113.10 dubai

  # Real deploy after inventory IP is set:
  ./pcs_deploy_one_v20260802.sh root@YOUR_VPS_IP dubai
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|-n) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option: $1" ;;
    *)
      if [[ -z "$TARGET" ]]; then
        TARGET="$1"
      elif [[ -z "$LOCATION" ]]; then
        LOCATION="$1"
      else
        die "unexpected arg: $1"
      fi
      shift
      ;;
  esac
done

[[ -n "$TARGET" && -n "$LOCATION" ]] || { usage; exit 2; }
LOCATION="$(printf '%s' "$LOCATION" | tr '[:upper:]' '[:lower:]')"

# Reject obviously placeholder targets in non-dry-run
if [[ "$DRY_RUN" -eq 0 ]]; then
  case "$TARGET" in
    *YOUR*|*your-*|*example.com*|*203.0.113.*|*198.51.100.*|*192.0.2.*)
      die "refusing placeholder/documentation target in live mode: $TARGET (use --dry-run)"
      ;;
  esac
fi

CFG_SRC="${STATE_PKG}/sing-box-${LOCATION}-reality.json"
[[ -f "$CFG_SRC" ]] || die "missing filled config: $CFG_SRC (run materialize first)"
[[ -f "$REWRITE_PY" ]] || die "missing path rewriter: $REWRITE_PY"
[[ -f "$BOOTSTRAP_SH" ]] || die "missing remote bootstrap: $BOOTSTRAP_SH"

_TMPROOT="${TMPDIR:-/tmp}"
_TMPROOT="${_TMPROOT%/}"
WORKDIR="$(mktemp -d "${_TMPROOT}/pcs_deploy_${LOCATION}.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

REWRITTEN="${WORKDIR}/config.json"
STAGE_REMOTE="/tmp/pcs_stage"

log "pkg=${STATE_PKG}"
log "target=${TARGET} location=${LOCATION} dry_run=${DRY_RUN}"
log "rewrite Mac→/etc/sing-box paths…"

# Always rewrite locally (works offline; dry-run included).
# Use array args so set -e never trips on a false $( [[ dry ]] && … ) expansion.
REWRITE_ARGS=(
  --in "$CFG_SRC"
  --out "$REWRITTEN"
  --location "$LOCATION"
)
if [[ "$DRY_RUN" -eq 1 ]]; then
  REWRITE_ARGS+=(--dry-run --write-on-dry-run)
fi
python3 "$REWRITE_PY" "${REWRITE_ARGS[@]}"

# Stage hy2 certs if present
HY2_SRC="${STATE_PKG}/hy2_certs/${LOCATION}"
HAS_HY2=0
if [[ -d "$HY2_SRC" ]] && [[ -f "${HY2_SRC}/fullchain.pem" || -f "${HY2_SRC}/privkey.pem" ]]; then
  HAS_HY2=1
  mkdir -p "${WORKDIR}/hy2_certs/${LOCATION}"
  cp -f "${HY2_SRC}/"* "${WORKDIR}/hy2_certs/${LOCATION}/" 2>/dev/null || true
  log "hy2 certs staged from ${HY2_SRC}"
else
  log "no hy2 certs for ${LOCATION} (OK if Reality-only)"
fi

plan() {
  log "PLAN: $*"
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  plan "ssh ${SSH_OPTS} ${TARGET} 'mkdir -p ${STAGE_REMOTE}/hy2_certs/${LOCATION}'"
  plan "scp ${SSH_OPTS} ${REWRITTEN} ${TARGET}:${STAGE_REMOTE}/config.json"
  if [[ "$HAS_HY2" -eq 1 ]]; then
    plan "scp ${SSH_OPTS} ${WORKDIR}/hy2_certs/${LOCATION}/fullchain.pem ${WORKDIR}/hy2_certs/${LOCATION}/privkey.pem ${TARGET}:${STAGE_REMOTE}/hy2_certs/${LOCATION}/"
  fi
  plan "scp ${SSH_OPTS} ${BOOTSTRAP_SH} ${TARGET}:${STAGE_REMOTE}/pcs_remote_bootstrap.sh"
  plan "ssh ${SSH_OPTS} ${TARGET} 'sudo bash ${STAGE_REMOTE}/pcs_remote_bootstrap.sh --location ${LOCATION} --config ${STAGE_REMOTE}/config.json --stage-dir ${STAGE_REMOTE}'"
  log "rewritten config preview (first 40 lines):"
  head -n 40 "$REWRITTEN" | sed 's/^/  | /'
  # Show cert path keys after rewrite
  python3 - <<PY
import json
from pathlib import Path
d=json.loads(Path("${REWRITTEN}").read_text())
for i,ib in enumerate(d.get("inbounds",[])):
    tls=ib.get("tls") or {}
    for k in ("certificate_path","key_path"):
        if k in tls:
            print(f"  | inbound[{i}].tls.{k} = {tls[k]}")
print("PCS_DEPLOY_ONE_DRY_RUN=OK location=${LOCATION} target=${TARGET}")
PY
  log "DRY-RUN complete — no SSH/SCP performed"
  exit 0
fi

# --- live deploy ---
log "ssh mkdir stage"
# shellcheck disable=SC2086
ssh $SSH_OPTS "$TARGET" "mkdir -p ${STAGE_REMOTE}/hy2_certs/${LOCATION}"

log "scp rewritten config"
# shellcheck disable=SC2086
scp $SSH_OPTS "$REWRITTEN" "${TARGET}:${STAGE_REMOTE}/config.json"

if [[ "$HAS_HY2" -eq 1 ]]; then
  log "scp hy2 certs"
  # shellcheck disable=SC2086
  scp $SSH_OPTS \
    "${WORKDIR}/hy2_certs/${LOCATION}/fullchain.pem" \
    "${WORKDIR}/hy2_certs/${LOCATION}/privkey.pem" \
    "${TARGET}:${STAGE_REMOTE}/hy2_certs/${LOCATION}/"
fi

log "scp remote bootstrap"
# shellcheck disable=SC2086
scp $SSH_OPTS "$BOOTSTRAP_SH" "${TARGET}:${STAGE_REMOTE}/pcs_remote_bootstrap.sh"

log "remote bootstrap"
# shellcheck disable=SC2086
ssh $SSH_OPTS "$TARGET" \
  "sudo bash ${STAGE_REMOTE}/pcs_remote_bootstrap.sh --location ${LOCATION} --config ${STAGE_REMOTE}/config.json --stage-dir ${STAGE_REMOTE}"

log "DEPLOY OK ${LOCATION} → ${TARGET}"
echo "PCS_DEPLOY_ONE=OK location=${LOCATION} target=${TARGET}"
