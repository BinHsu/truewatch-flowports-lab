#!/usr/bin/env bash
# Kafka-down drill: 240 requests at 1/s (one CEF line each); Kafka is stopped at +60 s and started at +180 s.
# FlowPorts delivery state is sampled every 10 s into out/drill-delivery.txt; the timeline goes to out/drill-timeline.txt.
# Afterwards: scripts/kafka-dump.sh, then scripts/kafka-check.py out/kafka-dump.txt --drill lab-d1, and queries/drill.dql.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out
T=out/drill-timeline.txt; D=out/drill-delivery.txt; : > "$T"; : > "$D"
ev() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$T"; }
ev traffic start
docker compose run --rm -e MODE=drill -e ROUTE=d1 -e DRILL_N=240 -e DRILL_GAP=1 client > out/drill-client.txt 2>&1 &
CLIENT=$!
S=$(date +%s); stopped=0; started=0
while :; do
  el=$(( $(date +%s) - S ))
  if [ "$el" -ge 60 ] && [ "$stopped" = 0 ]; then ev kafka stop; docker compose stop -t 10 kafka >/dev/null; ev kafka stopped; stopped=1; fi
  if [ "$el" -ge 180 ] && [ "$started" = 0 ]; then ev kafka start; docker compose start kafka >/dev/null; ev kafka started; started=1; fi
  for f in lab-app lab-cef lab-nfs; do
    printf '== %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$f" >> "$D"
    python3 scripts/fpapi.py GET "/api/v1/flows/$f/delivery" >> "$D" 2>&1 || true
  done
  [ "$el" -ge 420 ] && break
  sleep 10
done
wait "$CLIENT" || true
ev traffic done
echo "CEF send errors: $(grep -c '^CEF-ERR' out/drill-client.txt || true)"
python3 - "$D" <<'PY'
import json, re, sys
cur = None
for line in open(sys.argv[1]):
    m = re.match(r"== (\S+) (\S+)", line)
    if m:
        cur = m.groups(); continue
    if line.startswith("["):
        for w in json.loads(line):
            for c in w.get("channels", []):
                if c["destination_id"] == "lab-kafka":
                    print(cur[0], cur[1], c["state"], "pending", c.get("pending"), "cap_drop", c.get("capacity_dropped_records"),
                          "retry_exhausted", c.get("retry_exhausted_records"))
PY
