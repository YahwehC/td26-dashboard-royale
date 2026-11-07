#!/usr/bin/env python3
"""Static checks for the dashboard site (Python standard library only).

Starts http.server on 127.0.0.1:8765 serving this folder, fetches every asset
and data file, validates JSON, and confirms that index.html only references
cdnjs.cloudflare.com as an external script host.

Usage:  python check_site.py
Exit code 0 = all checks passed, 1 = at least one failure.
"""

import glob
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PORT = 8765
ALLOWED_SCRIPT_HOST = "cdnjs.cloudflare.com"
BASE = None


class ScriptCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        for key, value in attrs:
            if key.lower() == "src" and value:
                self.scripts.append(value.strip())


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


def fetch(path, base=None):
    url = (base or BASE) + path.lstrip("/")
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return response.status, body


def port_in_use(host):
    try:
        with socket.create_connection((host, PORT), timeout=0.3):
            return True
    except OSError:
        return False


def make_server(host):
    handler = partial(QuietHandler, directory=str(ROOT))
    if ":" in host:
        class IPv6Server(ThreadingHTTPServer):
            address_family = socket.AF_INET6
        return IPv6Server((host, PORT), handler)
    return ThreadingHTTPServer((host, PORT), handler)


def base_url(host):
    if ":" in host:
        return "http://[%s]:%d/" % (host, PORT)
    return "http://%s:%d/" % (host, PORT)


def is_local_script(src):
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https"):
        return parsed.hostname
    if src.startswith("//"):
        return urlparse("https:" + src).hostname
    return None  # relative path


def main():
    global BASE
    os.chdir(ROOT)

    server = None
    thread = None
    for host in ("127.0.0.1", "127.0.0.2", "::1"):
        if port_in_use(host):
            print("Note: %s:%d is already in use; trying another loopback address." % (host, PORT))
            continue
        try:
            candidate = make_server(host)
        except OSError as exc:
            print("Note: could not bind %s:%d (%s)." % (host, PORT, exc))
            continue
        candidate_thread = threading.Thread(target=candidate.serve_forever, daemon=True)
        candidate_thread.start()
        time.sleep(0.1)
        candidate_base = base_url(host)
        try:
            status, body = fetch("index.html", base=candidate_base)
            if status == 200 and b'id="app"' in body:
                server = candidate
                thread = candidate_thread
                BASE = candidate_base
                break
            print("Note: %s:%d answered with a different site; trying another loopback address." % (host, PORT))
        except Exception as exc:  # noqa: BLE001
            print("Note: %s:%d did not answer (%s)." % (host, PORT, exc))
        candidate.shutdown()
        candidate.server_close()
        candidate_thread.join(timeout=5)

    if server is None:
        print("[FAIL] could not start http.server on port %d serving %s" % (PORT, ROOT))
        return 1

    failures = []
    checks = 0

    def ok(message):
        nonlocal checks
        checks += 1
        print("  [ok] " + message)

    def fail(message):
        nonlocal checks
        checks += 1
        failures.append(message)
        print("  [FAIL] " + message)

    print("Serving %s" % ROOT)
    print("URL      %s" % BASE)
    print()

    try:
        print("Assets")
        for path in ("index.html", "app.js", "style.css"):
            try:
                status, body = fetch(path)
                if status == 200:
                    ok("%s (HTTP 200, %.1f KB)" % (path, len(body) / 1024.0))
                else:
                    fail("%s returned HTTP %s" % (path, status))
            except Exception as exc:  # noqa: BLE001 - report any transport error
                fail("%s could not be fetched (%s)" % (path, exc))

        index_html = ""
        try:
            _, index_raw = fetch("index.html")
            index_html = index_raw.decode("utf-8")
        except Exception:
            pass

        print()
        print("Data files")
        data_paths = sorted(glob.glob(str(ROOT / "data" / "*.json")))
        if not data_paths:
            fail("no data/*.json files found")
        for path in data_paths:
            rel = Path(path).relative_to(ROOT).as_posix()
            try:
                status, body = fetch(rel)
                if status != 200:
                    fail("%s returned HTTP %s" % (rel, status))
                    continue
                try:
                    parsed = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    fail("%s is not valid UTF-8 JSON (%s)" % (rel, exc))
                    continue
                kind = "array[%d]" % len(parsed) if isinstance(parsed, list) else "object[%d keys]" % len(parsed)
                ok("%s (HTTP 200, %.1f KB, valid JSON, %s)" % (rel, len(body) / 1024.0, kind))
            except Exception as exc:  # noqa: BLE001
                fail("%s could not be fetched (%s)" % (rel, exc))

        print()
        print("External script hosts")
        collector = ScriptCollector()
        collector.feed(index_html)
        if not collector.scripts:
            fail("index.html has no <script src=...> tags")
        external_hosts = []
        for src in collector.scripts:
            host = is_local_script(src)
            if host is None:
                ok("local script %s" % src)
            else:
                external_hosts.append(host)
                if host == ALLOWED_SCRIPT_HOST:
                    ok("external script host allowed: %s (%s)" % (host, src))
                else:
                    fail("external script host not allowed: %s (%s)" % (host, src))
        if not external_hosts:
            fail("index.html does not reference the Plotly CDN script")
        elif set(external_hosts) == {ALLOWED_SCRIPT_HOST}:
            ok("only %s is used as an external script host" % ALLOWED_SCRIPT_HOST)

        if "app.js" not in index_html:
            fail("index.html does not reference app.js")
        else:
            ok("index.html references app.js")
        if "style.css" not in index_html:
            fail("index.html does not reference style.css")
        else:
            ok("index.html references style.css")

        print()
        if failures:
            print("FAILED: %d of %d checks failed." % (len(failures), checks))
            for message in failures:
                print("  - " + message)
            return 1
        print("ALL CHECKS PASSED (%d checks)." % checks)
        return 0
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
