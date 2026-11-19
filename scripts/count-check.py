#!/usr/bin/env python3
"""Count check: Kafka end offset = FlowPorts `sent` to Kafka = FlowPorts `sent` to TrueWatch (= rows in TrueWatch).

    python3 scripts/count-check.py

Prints the topic end offset, then, per flow, how many points FlowPorts reports as sent to each destination,
and any capacity drops or exhausted retries. The third number, rows in TrueWatch, comes from queries/count.dql
in the console. Run it after traffic has stopped and both branches show pending 0.

FlowPorts' `sent` counters belong to the running flow version: republishing a flow (for example
flowports-setup.py --map-direct-spans) or restarting FlowPorts starts them again from 0, while the topic keeps its
earlier records. For an exact match, count from a fresh `docker compose up` with no republish in between.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fpapi import ROOT, Client  # noqa: E402

FLOWS = ("lab-app", "lab-dk", "lab-nfs", "lab-cef")
topic = "lab-events"
env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if line.startswith("KAFKA_TOPIC="):
            topic = line.split("=", 1)[1].split("#")[0].strip() or topic

r = subprocess.run(["docker", "compose", "exec", "-T", "kafka", "/opt/kafka/bin/kafka-get-offsets.sh",
                    "--bootstrap-server", "localhost:9092", "--topic", topic], cwd=ROOT, capture_output=True, text=True)
if r.returncode != 0 or not r.stdout.strip():
    sys.exit(f"FAILED to read the topic end offset: {r.stderr.strip()[:300]}")
end = sum(int(x.rsplit(":", 1)[1]) for x in r.stdout.split() if x.count(":") == 2)
print(f"Kafka topic {topic}: end offset sum over partitions = {end}   ({r.stdout.strip() or r.stderr.strip()})")

api = Client.from_lab()
tot = {}
print(f"{'flow':<9} {'destination':<14} {'sent':>7} {'pending':>8} {'cap_drop':>9} {'retry_exh':>10}")
for fid in FLOWS:
    st, obs = api.call("GET", f"/api/v1/flows/{fid}/observe")
    st2, dlv = api.call("GET", f"/api/v1/flows/{fid}/delivery")
    if st != 200:
        print(f"{fid:<9} observe HTTP {st}")
        continue
    pend = {}
    for w in (dlv or []) if st2 == 200 else []:
        for c in w.get("channels", []):
            pend[c["destination_id"]] = pend.get(c["destination_id"], 0) + c.get("pending", 0)
    for t in obs.get("targets", []):
        d = t["destination_id"]
        tot[d] = tot.get(d, 0) + t.get("sent", 0)
        print(f"{fid:<9} {d:<14} {t.get('sent', 0):>7} {pend.get(d, 0):>8} {t.get('capacity_dropped_records', 0):>9} "
              f"{t.get('retry_exhausted_records', 0):>10}")
print("totals sent:", ", ".join(f"{d} {n}" for d, n in sorted(tot.items())))
k = tot.get("lab-kafka")
print("Kafka end offset == FlowPorts sent to Kafka:", "YES" if k == end else
      f"NO ({end} vs {k}); if a flow was republished or FlowPorts restarted, its counter restarted from 0")
