#!/usr/bin/env python3
"""Industrial Command Center HTTP server (status API + static dashboards).

Serves only files under dashboards_v20260802/ — never Suite trees.
Status works when Suite is missing or partial.

  .venv/bin/python core_product/pcs_dashboard_server_v20260802.py
  .venv/bin/python core_product/pcs_dashboard_server_v20260802.py --port 8790
  .venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-dashboard 8790
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

INDUSTRIAL_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = INDUSTRIAL_ROOT / "dashboards_v20260802"
DEFAULT_PAGE = "pcs_suite_command_center_v2_20260802.html"
DEFAULT_PORT = 8790

sys.path.insert(0, str(INDUSTRIAL_ROOT))


def _build_status(tier: str = "core") -> dict[str, Any]:
    """Load app-shell status; never raise — always return JSON-safe dict."""
    try:
        from core_product.pcs_app_shell_v20260802 import PcsAppShell

        return PcsAppShell(tier=tier).status()
    except Exception as e:
        # Last-resort status when shell itself cannot load (Suite partial, etc.)
        industrial_howto = str(
            INDUSTRIAL_ROOT / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"
        )
        inv = str(Path.home() / ".pcs_industrial_20260802" / "vps_inventory.json")
        err = f"{type(e).__name__}: {e}"
        readiness: dict[str, Any] = {}
        try:
            from shared.pcs_server_readiness_v20260802 import gate_snapshot, scan_readiness

            readiness = scan_readiness()
            gate = gate_snapshot(readiness)
        except Exception as e2:
            readiness = {
                "ok": False,
                "status": "error",
                "error": f"{type(e2).__name__}: {e2}",
                "configured_count": 0,
                "server_filled_count": 0,
                "pending_ip_count": 0,
            }
            gate = {
                "status": "error",
                "ok_for_protect": False,
                "configured_count": 0,
                "server_filled_count": 0,
                "pending_ip_count": 0,
                "next_actions": [
                    {
                        "severity": "critical",
                        "code": "status_fallback",
                        "action": f"Shell status failed: {err}; readiness: {type(e2).__name__}",
                    }
                ],
                "inventory_path": inv,
                "howto_path": industrial_howto,
                "secrets_fingerprint": None,
            }
        fleet_playbook = str(
            INDUSTRIAL_ROOT
            / "docs_v20260802"
            / "CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md"
        )
        residential: dict[str, Any] = {
            "countries_count": 0,
            "total_entries": 0,
            "not_a_tunnel_endpoint": True,
            "claims_tunnel_readiness": False,
            "note": "Synthetic product catalog only — not VPS tunnel endpoints.",
        }
        try:
            from shared.pcs_residential_pool_industrial_v20260802 import catalog_summary

            residential = catalog_summary()
        except Exception:
            pass
        purpose_top5: dict[str, Any] = {
            "purposes": [],
            "by_purpose": {},
            "mvp_ips": 0,
            "note": "Purpose routing unavailable",
        }
        try:
            from shared.pcs_purpose_routing_v20260802 import purpose_top5_summary

            purpose_top5 = purpose_top5_summary()
        except Exception:
            pass
        inventory_pool: dict[str, Any] = {
            "version": 2,
            "total_real_ips": 0,
            "locations_with_ips": 0,
            "by_location": {},
            "note": "No real owned VPS IPs in inventory yet",
        }
        try:
            from shared.pcs_inventory_v2_v20260802 import pool_summary

            ps = pool_summary()
            inventory_pool = {
                "version": int(ps.get("version") or 2),
                "total_real_ips": int(ps.get("total_real_ips") or 0),
                "locations_with_ips": int(ps.get("locations_with_ips") or 0),
                "by_location": ps.get("by_location") or {},
                "note": (
                    "Owned public IPs in inventory pools only — not catalog entries."
                    if int(ps.get("total_real_ips") or 0) > 0
                    else "No real owned VPS IPs in inventory yet"
                ),
            }
        except Exception:
            pass
        cfg_n = int(gate.get("configured_count") or 0)
        ok_protect = bool(gate.get("ok_for_protect")) and cfg_n > 0
        return {
            "tier": tier,
            "suite_available": False,
            "suite_partial": True,
            "suite_required_for_status": False,
            "status_ok_without_suite": True,
            "shell_error": err,
            "server_readiness": readiness,
            "protect_gate": {
                "status": gate.get("status") or readiness.get("status"),
                "ok_for_protect": ok_protect,
                "configured_count": cfg_n,
                "server_filled_count": int(gate.get("server_filled_count") or 0),
                "pending_ip_count": int(gate.get("pending_ip_count") or 0),
                "next_actions": gate.get("next_actions") or [],
                "next_step": gate.get("next_step"),
                "block_message": gate.get("block_message")
                or (
                    None
                    if ok_protect
                    else (
                        f"Protect blocked: configured_count={cfg_n}. "
                        "Fill inventory (CEO fleet playbook), materialize, then re-scan."
                    )
                ),
                "inventory_path": gate.get("inventory_path") or inv,
                "howto_path": gate.get("howto_path") or industrial_howto,
                "fleet_playbook_path": fleet_playbook,
                "secrets_fingerprint": gate.get("secrets_fingerprint")
                or readiness.get("secrets_fingerprint"),
                "total_real_ips": inventory_pool["total_real_ips"],
            },
            "status": gate.get("status") or readiness.get("status"),
            "configured_count": cfg_n,
            "server_filled_count": int(gate.get("server_filled_count") or 0),
            "pending_ip_count": int(gate.get("pending_ip_count") or 0),
            "next_actions": gate.get("next_actions") or [],
            "secrets_fingerprint": gate.get("secrets_fingerprint")
            or readiness.get("secrets_fingerprint"),
            "ok_for_protect": ok_protect,
            "inventory_path": gate.get("inventory_path") or inv,
            "howto_path": gate.get("howto_path") or industrial_howto,
            "fleet_playbook_path": fleet_playbook,
            "purpose_top5": purpose_top5,
            "inventory_pool": inventory_pool,
            "total_real_ips": inventory_pool["total_real_ips"],
            "residential_catalog": residential,
            "honest_copy": "protections active · verify recommended",
            "industrial_root": str(INDUSTRIAL_ROOT),
            "overwrites": "none — Suite/legacy read-only imports only",
            "cta": {
                "inventory_path": gate.get("inventory_path") or inv,
                "wizard": "Open VPS deploy wizard in Command Center",
                "howto_path": gate.get("howto_path") or industrial_howto,
                "industrial_howto": industrial_howto,
                "fleet_playbook_path": fleet_playbook,
                "fleet_playbook_label": "CEO Fleet Beginner Playbook",
                "fleet_playbook_cta": (
                    "Open CEO_FLEET_BEGINNER_PLAYBOOK — own VPS IPs → raise configured_count"
                ),
            },
        }


class DashboardHandler(BaseHTTPRequestHandler):
    tier: str = "core"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[dashboard]", fmt % args)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def _json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            return self._json(404, {"error": "not found", "path": str(path.name)})
        # Path traversal guard: only dashboard dir
        try:
            resolved = path.resolve()
            root = DASHBOARD_DIR.resolve()
            if not str(resolved).startswith(str(root) + os.sep) and resolved != root:
                return self._json(403, {"error": "forbidden"})
        except Exception:
            return self._json(403, {"error": "forbidden"})
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        if path.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif path.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif path.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        elif not ctype:
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        u = urlparse(self.path)
        path = u.path or "/"

        if path in ("/api/status", "/api/v1/status"):
            return self._json(200, _build_status(self.tier))

        if path in ("/api/health", "/healthz"):
            return self._json(
                200,
                {
                    "ok": True,
                    "service": "pcs_industrial_command_center",
                    "dashboard_dir": str(DASHBOARD_DIR),
                    "suite_required": False,
                },
            )

        if path in ("/", "/index.html", "/command-center", "/v2"):
            return self._file(DASHBOARD_DIR / DEFAULT_PAGE)

        # Static asset under dashboards_v20260802 only
        name = path.lstrip("/")
        if ".." in name or name.startswith("/"):
            return self._json(400, {"error": "bad path"})
        return self._file(DASHBOARD_DIR / name)


def serve(
    port: int = DEFAULT_PORT,
    *,
    tier: str = "core",
    open_browser: bool = False,
    host: str = "127.0.0.1",
) -> None:
    if not DASHBOARD_DIR.is_dir():
        raise FileNotFoundError(f"Dashboard dir missing: {DASHBOARD_DIR}")

    handler = type(
        "BoundDashboardHandler",
        (DashboardHandler,),
        {"tier": tier},
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"PCS Industrial Command Center → {url}")
    print(f"  GET  /                 v2 Command Center")
    print(f"  GET  /api/status       readiness + protect_gate + residential counts")
    print(f"  GET  /api/health       liveness")
    print(f"  dashboards: {DASHBOARD_DIR}")
    print("  Suite not required for status (partial/missing Suite OK).")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    httpd.serve_forever()


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="PCS Industrial Command Center server")
    p.add_argument("--port", type=int, default=int(os.environ.get("PCS_DASHBOARD_PORT", DEFAULT_PORT)))
    p.add_argument("--host", default=os.environ.get("PCS_DASHBOARD_HOST", "127.0.0.1"))
    p.add_argument("--tier", default=os.environ.get("PCS_TIER", "core"), choices=["core", "pro"])
    p.add_argument("--open", action="store_true", help="Open browser to Command Center")
    args = p.parse_args(argv)
    serve(args.port, tier=args.tier, open_browser=args.open, host=args.host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
