#!/usr/bin/env python3
"""Configure the lab's FlowPorts instance through its documented management API.

Run it from the repository root after `docker compose up -d kafka kafka-init flowports`:

    python3 scripts/flowports-setup.py                     # TrueWatch + Kafka destinations
    python3 scripts/flowports-setup.py --map-direct-spans  # also map route-B spans to APM columns
    python3 scripts/flowports-setup.py --kafka-only        # no TrueWatch destination (offline test)

What it does: first-run setup (admin password from the one-time setup token) -> write API key ->
two destinations (TrueWatch DataWay, Kafka acks=all) -> four flows, each delivering to both ->
publish -> start -> wait until each flow reports `running`. It then writes the per-service env files
that docker compose reads (.lab/*.env). Every secret it creates stays in .lab/ (mode 0700/0600).
Never paste those files, or DataKit's log, anywhere: they contain the FlowPorts source tokens.
"""
import argparse
import json
import os
import pathlib
import secrets
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fpapi import BASE, LAB, ROOT, Client  # noqa: E402

PIPE = ROOT / "flowports" / "pipelines"
FLOWS = {
    # flow id: (name, source type, source config, pipelines by category)
    "lab-app": ("App OTLP direct (route B)", "opentelemetry", {}, {"logging": "app.p", "tracing": "app.p"}),
    "lab-dk": ("DataKit relay (route A)", "datakit", {}, {"logging": "app.p", "tracing": "app.p"}),
    "lab-nfs": ("NetFlowScout (wire)", "datakit", {}, {"logging": "nfs.p"}),
    "lab-cef": ("CEF security device", "socket", {"address": "0.0.0.0:1515", "transport": "tcp", "format": "text"}, {"logging": "cef.p"}),
}
TOKEN_FLOWS = ("lab-app", "lab-dk", "lab-nfs")  # sources that authenticate with a source token
QUEUE_BYTES = 33554432


def load_env():
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k in ("DATAWAY_URL", "DATAWAY_TOKEN", "KAFKA_TOPIC")})
    return env


def write_private(path, text):
    LAB.mkdir(mode=0o700, exist_ok=True)
    os.chmod(LAB, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)


def must(status, out, what, ok=(200, 201, 204)):
    if status not in ok:
        sys.exit(f"FAILED {what}: HTTP {status} {str(out)[:400]}")
    return out


def setup_token():
    for _ in range(60):
        r = subprocess.run(["docker", "compose", "exec", "-T", "flowports", "cat", "/data/manager/setup-token"],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        time.sleep(1)
    sys.exit("FAILED: no setup token in the flowports container after 60 s (is it running?)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kafka-only", action="store_true", help="skip the TrueWatch destination")
    ap.add_argument("--map-direct-spans", action="store_true", help="tracing pipeline spans-direct.p on lab-app")
    args = ap.parse_args()
    env = load_env()
    topic = env.get("KAFKA_TOPIC", "lab-events")
    if not args.kafka_only:
        url, tok = env.get("DATAWAY_URL", ""), env.get("DATAWAY_TOKEN", "")
        if not url.startswith("https://") or not tok.startswith("tkn_") or tok == "tkn_EXAMPLE":
            sys.exit("FAILED: set DATAWAY_URL and DATAWAY_TOKEN in .env (TrueWatch console: Integrations > FlowPorts)")

    state_path = LAB / "admin.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state.setdefault("password", secrets.token_urlsafe(24))
    for f in TOKEN_FLOWS:
        state.setdefault("source_tokens", {}).setdefault(f, secrets.token_urlsafe(32))

    admin = Client()
    status, out = admin.call("GET", "/api/v1/setup")
    must(status, out, "GET /setup")
    if out.get("required"):
        status, out = admin.call("POST", "/api/v1/setup", {
            "token": setup_token(), "password": state["password"], "confirm_password": state["password"],
            "listeners": {"admin": "0.0.0.0:8080", "ingest": "0.0.0.0:8081"}})
        must(status, out, "POST /setup")
    else:
        status, out = admin.call("POST", "/api/v1/login", {"password": state["password"]})
        must(status, out, "POST /login (admin already set up; password from .lab/admin.json)")
    admin.csrf = out["csrf"]
    status, out = admin.call("POST", "/api/v1/api-keys", {"name": "flowports-lab", "permission": "write", "expires_in_days": 1})
    state["api_key"] = must(status, out, "POST /api-keys")["token"]
    write_private(state_path, json.dumps(state, indent=1))
    print("admin setup ok, API key stored in .lab/admin.json")

    api = Client(key=state["api_key"])
    dests = []
    if not args.kafka_only:
        must(*api.call("PUT", "/api/v1/destinations/lab-truewatch", {
            "id": "lab-truewatch", "name": "TrueWatch DataWay", "type": "dataway",
            "url": env["DATAWAY_URL"], "token": env["DATAWAY_TOKEN"], "config": {}}), "PUT destination lab-truewatch")
        dests.append("lab-truewatch")
    must(*api.call("PUT", "/api/v1/destinations/lab-kafka", {
        "id": "lab-kafka", "name": "Kafka (local)", "type": "kafka",
        "config": {"brokers": "kafka:9092", "topic": topic, "acks": "all", "encoding": "ndjson"}}), "PUT destination lab-kafka")
    dests.append("lab-kafka")
    print("destinations:", ", ".join(dests))

    for fid, (name, stype, sconf, pipes) in FLOWS.items():
        if fid == "lab-app" and args.map_direct_spans:
            pipes = dict(pipes, tracing="spans-direct.p")
        conf = dict(sconf)
        if fid in TOKEN_FLOWS:
            conf["token"] = state["source_tokens"][fid]
        status, cur = api.call("GET", f"/api/v1/flows/{fid}")
        rev, draft = (cur.get("revision", 0), cur.get("draft_revision", 0)) if status == 200 else (0, 0)
        body = {"id": fid, "name": name, "revision": rev, "draft_revision": draft,
                "source": {"type": stype, "config": conf},
                "pipelines": {cat: (PIPE / p).read_text() for cat, p in pipes.items()},
                "destination_ids": dests, "queue_bytes": QUEUE_BYTES}
        if status == 200 and rev and cur.get("pipelines") == body["pipelines"] \
                and sorted(cur.get("destination_ids") or []) == sorted(dests):
            print(f"flow {fid}: unchanged, left as it is")
            continue
        if status == 200 and rev and stype == "socket":
            print(f"note: updating the running socket flow {fid}. In FlowPorts 0.5.6 such an update did not install (the old "
                  "revision kept the port). If it stays at partial_failure: docker compose up -d --force-recreate flowports, "
                  "then run this script again (it starts from a fresh, empty FlowPorts).")
        saved = must(*api.call("PUT", f"/api/v1/flows/{fid}", body), f"save flow {fid}")
        must(*api.call("POST", f"/api/v1/flows/{fid}/publish", {"draft_revision": saved["draft_revision"]}), f"publish {fid}")
        must(*api.call("POST", f"/api/v1/flows/{fid}/start"), f"start {fid}")
        for _ in range(60):
            status, dep = api.call("GET", f"/api/v1/flows/{fid}/deployment")
            if status == 200 and dep.get("status") == "running":
                break
            time.sleep(1)
        else:
            sys.exit(f"FAILED: flow {fid} is not running after 60 s: {str(dep)[:400]}")
        print(f"flow {fid}: running (version {dep.get('version')})")

    t = state["source_tokens"]
    write_private(LAB / "datakit.env", f"ENV_DATAWAY=http://flowports:8081?flow=lab-dk&token={t['lab-dk']}\n")
    write_private(LAB / "nfs.env", f"NETFLOWSCOUT_DATAWAY_TOKEN={t['lab-nfs']}\n")
    write_private(LAB / "app-a.env", "OTEL_EXPORTER_OTLP_ENDPOINT=http://datakit:9529/otel\n")
    write_private(LAB / "app-b.env", "OTEL_EXPORTER_OTLP_ENDPOINT=http://flowports:8081/ingest/lab-app\n"
                  f"OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20{t['lab-app']}\n")
    print("wrote .lab/datakit.env, .lab/nfs.env, .lab/app-a.env, .lab/app-b.env")
    print(f"next: docker compose up -d datakit app nfs   (management UI: {BASE})")


if __name__ == "__main__":
    main()
