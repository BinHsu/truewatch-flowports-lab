#!/usr/bin/env python3
"""Join the three views of each probe request, using the Kafka copy (scripts/kafka-dump.sh) only.

    python3 scripts/join-kafka.py out/kafka-dump.txt --trace-prefix 5eeda1 --cef-run lab-a1

Key 1: trace_id. The client's traceparent is captured on the wire by NetFlowScout, continued by the app
       span, and carried by the Beacon finding.
Key 2: client IP + client source port (span peer address vs. the wire event), for traffic without trace context.
Key 3: the device (CEF) line has neither: client IP + path before '?' + nearest device time (rt) to the span.
TrueWatch holds the same records; queries/join.dql is the console version of the same three steps.
"""
import argparse
import json
import re

ap = argparse.ArgumentParser()
ap.add_argument("dump")
ap.add_argument("--trace-prefix", required=True, help="e.g. 5eeda1 (the probe writes 5eed + ROUTE into every trace id)")
ap.add_argument("--cef-run", help="limit device lines to this probe run, e.g. lab-a1")
a = ap.parse_args()

R = []
for line in open(a.dump, encoding="utf-8"):
    m = re.match(r"CreateTime:(\d+)\tOffset:(\d+)\t(.*)$", line.rstrip("\n"))
    if m:
        R.append((int(m[2]), json.loads(m[3])))


def g(j, *ks):
    for k in ks:
        v = (j.get("tags") or {}).get(k, (j.get("fields") or {}).get(k))
        if v not in (None, ""):
            return v
    return None


def path0(p):
    return (p or "").split("?")[0]


def device_ns(j):  # cef_rt (ns) if the pipeline kept it as a field, else the point time (= rt with the time fix)
    v = g(j, "cef_rt")
    return int(v) if v is not None else int(j["timestamp"])


wire = [(o, j) for o, j in R if j.get("measurement") == "netflowscout" and str(g(j, "nfs_event") or "").endswith("http_request")]
spans = [(o, j) for o, j in R if j.get("category") == "tracing" and str(g(j, "span_kind")) in ("server", "2")]
finds = [(o, j) for o, j in R if (j.get("category") == "keyevent" and g(j, "df_source") == "beacon_security")
         or (j.get("measurement") == "otel_log" and g(j, "event.name") == "beacon.security.finding")]
cefs = [(o, j) for o, j in R if j.get("measurement") == "socket" and g(j, "signal") == "device"
        and (not a.cef_run or str(g(j, "cef_probe_run") or "").startswith(a.cef_run + "-"))]

tids = sorted({g(j, "trace_id") for _, j in spans + wire if str(g(j, "trace_id") or "").startswith(a.trace_prefix)})
if not tids:
    raise SystemExit(f"no spans or wire events with trace ids starting {a.trace_prefix}")
ok = 0
for tid in tids:
    sp = [(o, j) for o, j in spans if g(j, "trace_id") == tid]
    w1 = [(o, j) for o, j in wire if g(j, "trace_id") == tid]
    print(f"trace {tid}")
    if not sp:
        print("  span    none")
        continue
    so, s = sp[0]
    ip, port = g(s, "client_address", "client.address"), g(s, "network_peer_port", "network.peer.port")
    route = path0(g(s, "http_route", "http.route", "http.target"))
    f = [(o, j) for o, j in finds if g(j, "trace_id") == tid and g(j, "server_span_id", "span_id") == g(s, "span_id")]
    w2 = [(o, j) for o, j in wire if g(j, "client_ip") == ip and str(g(j, "client_port")) == str(port)]
    dev = sorted([(o, j) for o, j in cefs if g(j, "client_ip") == ip and path0(g(j, "http_path")) == route],
                 key=lambda x: abs(device_ns(x[1]) - int(s["timestamp"])))
    same = {o for o, _ in w1} == {o for o, _ in w2} and bool(w1)
    ok += same
    print(f"  span    offset {so}  {g(s, 'resource', 'span_name') or s.get('measurement')}  peer {ip}:{port}")
    print(f"  finding offsets {[o for o, _ in f]}  rule {[g(j, 'rule') or json.loads(g(j, 'message') or '{}').get('rule') for _, j in f]}")
    print(f"  wire    by trace_id {[o for o, _ in w1]}  by ip+port {[o for o, _ in w2]}  same={same}")
    if dev:
        o, d = dev[0]
        print(f"  device  offset {o}  sig {g(d, 'cef_sig')} {g(d, 'cef_name')!r}  rt-span {round((device_ns(d) - int(s['timestamp'])) / 1e6, 1)} ms")
    else:
        print("  device  none")
print(f"{ok}/{len(tids)} requests: the wire event found by trace_id is the one found by IP + port")
