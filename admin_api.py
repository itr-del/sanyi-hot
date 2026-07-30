#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sanyi-hot 管理 API（轻量，仅标准库）
提供 SSL 证书复核管理接口
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SITE_DIR = os.environ.get("SANYI_SITE_DIR", "/var/www/sanyi-hot")
PENDING_FILE = os.path.join(SITE_DIR, "monitors-pending.json")
TRUSTED_FILE = os.path.join(SITE_DIR, "monitors-trusted.json")
ADMIN_PWD = os.environ.get("SANYI_ADMIN_PWD", "admin2026")

CST = timezone(timedelta(hours=8))


def check_auth(headers):
    auth = headers.get("X-Admin-Pwd", "")
    return auth == ADMIN_PWD


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/admin/monitors/pending":
            if not check_auth(self.headers):
                self.send_response(401)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
                return
            pending = load_json(PENDING_FILE, [])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"pending": pending}).encode())

        elif path == "/api/admin/monitors/trusted":
            if not check_auth(self.headers):
                self.send_response(401)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
                return
            trusted = load_json(TRUSTED_FILE, [])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"trusted": trusted}).encode())

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/admin/monitors/approve":
            if not check_auth(self.headers):
                self.send_response(401)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
                return
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len).decode())
            url = body.get("url", "")
            name = body.get("name", url)
            if not url:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "url required"}).encode())
                return

            trusted = load_json(TRUSTED_FILE, [])
            trusted_urls = {t["url"] for t in trusted}
            if url in trusted_urls:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "msg": "already approved"}).encode())
                return

            pending = load_json(PENDING_FILE, [])
            pending = [p for p in pending if p.get("url") != url]
            save_json(PENDING_FILE, pending)

            trusted.append({
                "name": name,
                "url": url,
                "error": "web approve",
                "time": "",
                "approved_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
            })
            save_json(TRUSTED_FILE, trusted)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "msg": "approved"}).encode())

        elif path == "/api/admin/monitors/revoke":
            if not check_auth(self.headers):
                self.send_response(401)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
                return
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len).decode())
            url = body.get("url", "")
            if not url:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "url required"}).encode())
                return

            trusted = load_json(TRUSTED_FILE, [])
            original_len = len(trusted)
            trusted = [t for t in trusted if t.get("url") != url]
            if len(trusted) < original_len:
                save_json(TRUSTED_FILE, trusted)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "msg": "revoked"}).encode())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "msg": "not found"}).encode())

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Pwd")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("[admin-api] " + fmt % args + "\n")


def main():
    port = int(os.environ.get("SANYI_API_PORT", "18790"))
    server = HTTPServer(("127.0.0.1", port), AdminHandler)
    print(f"[admin-api] running on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
