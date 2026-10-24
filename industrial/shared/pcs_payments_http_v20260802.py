"""Minimal HTTP server for checkout + industrial landing API (stdlib only)."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import pcs_payments_industrial_v20260802 as pay

LANDING = Path(__file__).resolve().parents[1] / "landing_v20260802" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[payments-http]", fmt % args)

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, path: Path):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            if LANDING.exists():
                return self._html(LANDING)
            return self._json(404, {"error": "landing missing"})
        if u.path == "/api/pricing":
            return self._json(200, pay.tier_prices())
        if u.path == "/api/methods":
            return self._json(200, pay.supported_methods())
        if u.path.startswith("/api/order/"):
            oid = u.path.rsplit("/", 1)[-1]
            orders = pay._load()
            o = orders.get(oid)
            if not o:
                return self._json(404, {"error": "not found"})
            from dataclasses import asdict

            return self._json(200, asdict(o))
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except Exception:
            body = {}

        try:
            if u.path == "/api/create_order":
                o = pay.create_order(
                    body.get("tier", "core"),
                    body.get("term", "annual"),
                    body.get("asset", "BTC"),
                )
                return self._json(200, o)
            if u.path == "/api/confirm_crypto":
                return self._json(
                    200,
                    pay.confirm_crypto_payment(
                        body["order_id"],
                        body.get("txid", ""),
                        int(body.get("confirmations", 0)),
                        bool(body.get("amount_ok", False)),
                    ),
                )
            if u.path == "/api/confirm_card":
                return self._json(
                    200,
                    pay.confirm_card_payment(body["order_id"], body.get("payment_intent_id")),
                )
            if u.path == "/api/confirm_demo":
                return self._json(200, pay.confirm_demo(body["order_id"]))
            if u.path == "/api/redeem":
                return self._json(200, pay.redeem_access_code(body.get("code", "")))
        except Exception as e:
            return self._json(400, {"error": str(e)[:300]})
        return self._json(404, {"error": "not found"})


def serve(port: int = 8787):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"PCS payments + landing on http://127.0.0.1:{port}/")
    print("  GET  /              landing")
    print("  GET  /api/pricing")
    print("  POST /api/create_order  {tier,term,asset}")
    print("  POST /api/confirm_demo  {order_id}")
    print("  POST /api/redeem        {code}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
