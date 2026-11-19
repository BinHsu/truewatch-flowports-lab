#!/usr/bin/env python3
"""Check a Kafka dump (scripts/kafka-dump.sh): offsets contiguous, records per flow and category, exact duplicates.

    python3 scripts/kafka-check.py out/kafka-dump.txt
    python3 scripts/kafka-check.py out/kafka-dump.txt --drill lab-d1   # also: drill CEF sequence complete?
"""
import argparse
import collections
import json
import re

ap = argparse.ArgumentParser()
ap.add_argument("dump")
ap.add_argument("--drill", help="probe run name of a drill, e.g. lab-d1 (checks cs1 sequence 1..N)")
ap.add_argument("--drill-n", type=int, default=240)
a = ap.parse_args()

recs = []
for line in open(a.dump, encoding="utf-8"):
    m = re.match(r"CreateTime:(\d+)\tOffset:(\d+)\t(.*)$", line.rstrip("\n"))
    if m:
        recs.append((int(m[2]), int(m[1]), m[3]))
if not recs:
    raise SystemExit("no records in dump")
offs = sorted(r[0] for r in recs)
print(f"records {len(recs)}  offsets {offs[0]}-{offs[-1]}  contiguous {offs == list(range(offs[0], offs[-1] + 1))}")


def g(j, k):
    return (j.get("tags") or {}).get(k, (j.get("fields") or {}).get(k))


per = collections.Counter()
dups = collections.Counter(body for _, _, body in recs)
for _, _, body in recs:
    j = json.loads(body)
    per[(g(j, "collectway_flow"), j.get("category"))] += 1
for (flow, cat), n in sorted(per.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
    print(f"  {flow:<10} {cat:<14} {n}")
print(f"exact duplicate records: {sum(n - 1 for n in dups.values() if n > 1)}")

if a.drill:
    seen = collections.Counter()
    for _, _, body in recs:
        run = g(json.loads(body), "cef_probe_run") or ""
        if run.startswith(a.drill + "-"):
            seen[int(run.rsplit("-", 1)[1])] += 1
    missing = sorted(set(range(1, a.drill_n + 1)) - set(seen))
    print(f"drill {a.drill}: CEF lines {sum(seen.values())}, unique {len(seen)}, duplicated {sum(n - 1 for n in seen.values())}, "
          f"missing {len(missing)} {missing[:20]}")
