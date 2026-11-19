"""Minimal FlowPorts management API client (Python standard library only).

Used by flowports-setup.py, count-check.py and drill.sh. It reads the API key that
flowports-setup.py stored in .lab/admin.json (mode 0600).

    python3 scripts/fpapi.py GET /api/v1/flows/lab-cef/delivery
"""
import http.cookiejar
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAB = ROOT / ".lab"
BASE = os.environ.get("FP_ADMIN", "http://127.0.0.1:18080")


class Client:
    def __init__(self, key=None, csrf=None):
        self.key, self.csrf = key, csrf
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    @classmethod
    def from_lab(cls):
        state = json.loads((LAB / "admin.json").read_text())
        return cls(key=state["api_key"])

    def call(self, method, path, body=None):
        headers = {"Origin": BASE, "Content-Type": "application/json", "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as resp:
                text = resp.read().decode()
                status = resp.status
        except urllib.error.HTTPError as err:
            text, status = err.read().decode(), err.code
        try:
            return status, json.loads(text) if text.strip() else None
        except json.JSONDecodeError:
            return status, text


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: fpapi.py METHOD PATH [JSON_BODY_FILE]")
    body = json.loads(pathlib.Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else None
    status, out = Client.from_lab().call(sys.argv[1], sys.argv[2], body)
    print(status)
    print(json.dumps(out) if not isinstance(out, str) else out)  # one line: drill.sh parses it
