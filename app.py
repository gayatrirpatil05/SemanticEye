"""SemanticEye web UI (offline). Run:  python app.py   then open http://localhost:8000"""
import netguard
netguard.install()                       # FIRST: from here on, no outbound network is possible

import argparse
import base64
import hmac
import json
import os
import re
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import ingest
import plagiarism
import report

for _k, _v in {"DO_NOT_TRACK": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}.items():
    os.environ.setdefault(_k, _v)

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = secrets.token_urlsafe(32)        # random per start; other websites cannot guess it
FINGERPRINT = config.build_fingerprint()[:12]
MAX_BODY = 190 * 1024 * 1024
LOCK = threading.Lock()
ALLOWED_HOSTS = set()

with open(os.path.join(HERE, "ui_page.html"), encoding="utf-8") as _f:
    PAGE = _f.read()


def _demo_json() -> str:
    def rd(n):
        try:
            with open(os.path.join(HERE, "samples", n), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    return json.dumps({"text": rd("demo_submission.txt"), "source": rd("source_article.txt")}).replace("</", "<\\/")


DEMO = _demo_json()


def _safe_name(n) -> str:
    n = os.path.basename(str(n or "file"))
    return re.sub(r"[\x00-\x1f]", "", n)[:80] or "file"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):               # skip the reverse-DNS lookup the default does
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name, self.server_port = "localhost", self.server_address[1]


class H(BaseHTTPRequestHandler):
    server_version = "SemanticEye"
    sys_version = ""
    timeout = 60

    def _send(self, code, body, ctype, nonce=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
        if nonce:
            self.send_header("Content-Security-Policy",
                             f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                             "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        else:
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=float).encode("utf-8"), "application/json")

    def _local_only(self):
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in ALLOWED_HOSTS}

    def do_GET(self):
        if not self._local_only() or self.path.split("?")[0] != "/":
            return self._send(403, b"Forbidden", "text/plain")
        nonce = secrets.token_urlsafe(16)
        page = PAGE.replace("__NONCE__", nonce).replace("__TOKEN__", TOKEN).replace("__DEMO__", DEMO)
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8", nonce=nonce)

    def do_POST(self):
        if (not self._local_only() or self.path not in ("/analyze", "/status", "/selftest")
                or not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN)):
            return self._send(403, b"Forbidden", "text/plain")
        if self.path == "/status":
            lib = plagiarism.library()
            return self._json({"guard_active": True, "blocked": netguard.blocked_count(),
                               "fingerprint": FINGERPRINT, "engine": config.ENGINE_VERSION,
                               "library": {"docs": lib["docs"], "words": lib["words"]}})
        if self.path == "/selftest":
            return self._json(netguard.probe())
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > MAX_BODY:
                self.close_connection = True
                raise ValueError("Request is empty or too large.")
            data = json.loads(self.rfile.read(n))
            sources = []
            if str(data.get("source", "")).strip():
                sources.append(("Pasted source", data["source"]))
            for sf in (data.get("source_files") or [])[:30]:
                name = _safe_name(sf.get("name"))
                sources.append((name, ingest.read_bytes(name, base64.b64decode(sf.get("b64", "")))))
            kw = {"sources": sources}
            if data.get("file_b64"):
                kw.update(name=_safe_name(data.get("file_name")), data=base64.b64decode(data["file_b64"]))
            else:
                kw["text"] = data.get("text", "")
            with LOCK:
                res = report.analyze(**kw)
            self._json(res)
        except (ValueError, KeyError, TypeError) as e:          # input problems: messages never echo content
            msg = str(e) if isinstance(e, ingest.InputError) or str(e).startswith("Request") else "The input could not be read."
            self._json({"error": msg})
        except Exception as e:                                  # anything else: never echo user data
            print("Analysis failed:", type(e).__name__)
            self._json({"error": f"Analysis failed ({type(e).__name__}). See the black window."})

    def log_message(self, *a):           # PRIVACY: never log requests
        pass


def make_server(start=8000):
    for p in range(start, start + 20):
        try:
            return Server(("127.0.0.1", p), H), p
        except OSError:
            continue
    raise SystemExit("No free port between 8000 and 8019.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    os.chdir(HERE)
    srv, port = make_server(a.port)
    ALLOWED_HOSTS.update({f"localhost:{port}", f"127.0.0.1:{port}"})
    print(f"SemanticEye running at http://localhost:{port}   (close this window or press Ctrl+C to stop)")
    print("Offline and private: network guard on, nothing is stored or logged. Build fingerprint:", FINGERPRINT)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
