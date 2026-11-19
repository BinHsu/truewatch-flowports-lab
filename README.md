# FlowPorts lab: one attack, three views, one pipeline

A scripted probe attacks a small test app. Three witnesses record it:

- **in the app**: Beacon (Java or Python) reports SQL injection and path traversal findings, tied to the request span;
- **on the wire**: NetFlowScout captures each HTTP request, including the client's `traceparent` header;
- **at the perimeter**: a fictional security device sends one CEF line per request over syslog/TCP.

All three go through one FlowPorts instance, which parses each format once and delivers every record to two places:
TrueWatch and Kafka (`acks=all`). The three views are then joined: by `trace_id`, then by client IP + source port, then
by client IP + path + device time.

This repository is the runnable part of the write-up
[One attack, three views, one pipeline](https://binhsu.github.io/posts/one-attack-three-views-one-pipeline/). Everything here was written for the lab; the
third-party software it uses is downloaded from its publishers and checked against pinned SHA-256 values, never
copied into this repository.

```
 probe ──HTTP──▶ app + Beacon ──OTLP──▶ DataKit 2.19.1 ──▶┐            ┌──▶ TrueWatch (DataWay)
   │                 ▲                                    │            │
   │       NetFlowScout (same netns) ─────────────────────┼─▶ FlowPorts┤
   │                                                      │   0.5.6    │
   └──CEF over TCP (one line per request) ───────────────▶┘            └──▶ Kafka 4.3.2 (acks=all)
```

## What you need

| | |
|---|---|
| Machine | linux/arm64 containers. Measured on Apple silicon with colima (VM: 4 CPU, 8 GiB, 30 GiB disk). amd64 was **not tested**: the download hashes and the Python lock below are arm64. |
| Docker | Docker Engine with Compose v2.24 or later (`env_file` with `required: false`). |
| colima | If `colima start` refuses because `kubectl` is missing (a profile with Kubernetes enabled), install `kubectl`, use a profile without Kubernetes, or start the VM directly with `LIMA_HOME=$HOME/.colima/_lima limactl start colima-<profile>` (what we did; without `LIMA_HOME`, `limactl` does not see colima's VMs) and `export DOCKER_HOST=unix://$HOME/.colima/<profile>/docker.sock` in every shell you use: the scripts call `docker compose` too. Stop it afterwards with `LIMA_HOME=$HOME/.colima/_lima limactl stop colima-<profile>`. Kubernetes itself is not used. |
| Tools on the host | `curl`, `python3` (3.9+), `sha256sum` or `shasum`. |
| TrueWatch | A workspace you may write test data to. Console: **Integrations > FlowPorts** shows the DataWay address and the workspace token. A full run writes a few thousand rows. |
| Disk | About 5 GB of images (the DataKit image alone is 2.6 GB on arm64). |

## Versions

| Component | Version | Where it comes from | Pinned by |
|---|---|---|---|
| FlowPorts | 0.5.6 (binary `collectway`) | [flowport.pages.dev downloads](https://flowport.pages.dev/en/downloads/) | tarball `cfc9c798652e4c080fc859246602e83246da50a7b754f23ae8f79e6327f0c868` |
| NetFlowScout | 0.3.0-dev-20261019-arm64-ba165ef4-r2 (development channel) | [netflowscout-downloads.pages.dev](https://netflowscout-downloads.pages.dev/releases.json) | package `dadd5fefc9844b41600e321e9f08bc40a8d0943c737bfe81f29e6ff7fef95068` (three parts) |
| Beacon Java agent | 1.3.4 | [GitHub release](https://github.com/beacon-observability/beacon-java/releases/tag/v1.3.4) | `c23a7c79b01cc45c3046198a0d8a9ed2bf9b8b4aca74a893f69ef1b59e15b2d1` |
| Beacon Python | `beacon-otel` 1.2.7 | PyPI | hash-pinned lock, `app/python/requirements.txt` |
| DataKit | 2.19.1 | `pubrepo.truewatch.com/truewatch/datakit` | `sha256:e409a78f25b92a8b533db7ed798f4f500f70a690f35039d5771bf7159c58955e` |
| Kafka | 4.3.2 (single node, KRaft) | `apache/kafka` | `sha256:852a0d49fc4e656b022e7f23785411802c9a088c78a7c5e39f33969de9c227a7` |
| Base images | `ubuntu:24.04`, `python:3.12.7-slim`, `eclipse-temurin:17.0.11_9-jdk` | Docker Hub | digests in `compose.yaml` and the Dockerfiles |

FlowPorts and NetFlowScout are closed-source prebuilt binaries; read their publishers' terms before you use them.

## Run it

```bash
# 1. Third-party pieces, hash-checked (refuses any mismatch)
scripts/fetch-vendor.sh

# 2. Settings and a CA bundle for FlowPorts' HTTPS connection to DataWay
cp .env.example .env               # set DATAWAY_URL and DATAWAY_TOKEN
cp /etc/ssl/cert.pem certs/ca-bundle.pem    # macOS; see certs/README.md for Linux

# 3. Kafka, the topic, FlowPorts; then configure FlowPorts (destinations, four flows, publish, start)
docker compose up -d kafka kafka-init flowports
python3 scripts/flowports-setup.py

# 4. DataKit, the app (Java by default) and NetFlowScout
docker compose up -d --build datakit app nfs

# 5. The probe: 3 requests (benign; SQL injection with a sqlmap user agent and a JNDI header; JNDI in a parameter).
#    ROUTE here is the probe marker: two hex characters written into every trace id (5eed<marker>...) and CEF run
#    name (lab-<marker>). It is not the ROUTE in .env, which picks the app's route.
mkdir -p out && docker compose run --rm -e ROUTE=a1 client | tee out/probe-a1.txt
```

Give TrueWatch a minute or two to show the rows, then follow `queries/README.md`. The same records are in Kafka (wait
about 30 s after the probe before `count-check.py`: DataKit sends in batches, and an early run can read the topic
before the last points arrive):

```bash
scripts/kafka-dump.sh
python3 scripts/join-kafka.py out/kafka-dump.txt --trace-prefix 5eeda1 --cef-run lab-a1
python3 scripts/kafka-check.py out/kafka-dump.txt
python3 scripts/count-check.py
```

The FlowPorts management UI is on http://127.0.0.1:18080 (the admin password is in `.lab/admin.json`).

### Python instead of Java, route B instead of route A

Set `APP_LANG=python` and/or `ROUTE=b` in `.env`, then `docker compose up -d --build --force-recreate app nfs`.
NetFlowScout lives in the app's network namespace, so recreate both together. The Python image installs its wheels from
PyPI with `--require-hashes`, so the build needs PyPI access. Give each probe run a new marker, e.g.
`docker compose run --rm -e ROUTE=b1 client`, and pass the same marker to `join-kafka.py` (`--trace-prefix 5eedb1
--cef-run lab-b1`).

- **Route A** (default): app → DataKit 2.19.1 → FlowPorts `datakit` source. Beacon findings arrive in TrueWatch as
  **security events** (`E::`, `df_source = beacon_security`) whose `server_span_id` points at the request span, and
  spans arrive as full APM rows (`resource`, `status`, `span_type`).
- **Route B**: app → FlowPorts `opentelemetry` source directly. Findings arrive as **logs** (`L::otel_log`,
  `event.name = beacon.security.finding`), and spans lack the APM columns. `python3 scripts/flowports-setup.py
  --map-direct-spans` adds a five-statement tracing pipeline that fills them in (`flowports/pipelines/spans-direct.p`).

### Kafka-down drill

```bash
scripts/drill.sh          # 240 requests at 1/s; Kafka stopped at +60 s, started at +180 s; about 7 minutes
scripts/kafka-dump.sh && python3 scripts/kafka-check.py out/kafka-dump.txt --drill lab-d1
```

## What we measured (2026-11-19, this setup)

| Check | Result |
|---|---|
| Route A, Java and Python | 7/7 (Java) and 5/5 (Python) findings are `E::` security events; each one's `server_span_id` is a span with the same `trace_id` |
| Route B, Java and Python | the same findings as `L::otel_log` rows with `trace_id`/`span_id` equal to their span; 0 `E::` rows |
| Join | 3/3 story requests per route: `trace_id` links client, wire, span and finding; IP + source port finds the same wire row as `trace_id`; the device line matches by IP + path + time |
| Count | topic offsets 0–1114, contiguous: **1115 records** in Kafka and **1115 rows** in TrueWatch, equal per flow and per category. In a smaller earlier run, FlowPorts' `sent` counter per destination matched the receiver (37 = 37) |
| Kafka stopped for 1 min 59 s | TrueWatch branch stayed `normal`; Kafka branch went `retrying` → `unhealthy`, peaked at 145 pending, caught up 31–34 s after Kafka returned. 240/240 per signal on both sides, 0 duplicates, 0 drops |
| Broker killed (SIGKILL) 7 times under load | 0 duplicates in Kafka and TrueWatch |
| This repository, end to end, with the TrueWatch destination (route A, Java then Python) | story probe joined 3/3 per app in TrueWatch and in Kafka (trace id; IP + source port; device line by IP + path); device row time equal to `rt` 6/6; Kafka end offset = FlowPorts `sent` per destination = TrueWatch rows: **37 = 37 = 37**, equal per flow. Then the drill (Python app): 240/240 CEF lines in Kafka and in TrueWatch, 0 duplicates; 999 records = 999 `sent` to each destination; TrueWatch 995 `L`/`T`/`E` rows = 995 such records, and 2 `CO` objects = 2 object names (4 SBOM records) |
| This repository, end to end (Java app, `--kafka-only`) | story probe joined 3/3 on route A and on route B; device row time equal to `rt`; Kafka end offset = FlowPorts `sent` (22 = 22); drill 240/240 CEF lines in Kafka, 0 duplicates, offsets contiguous |

## Things to know

- **Do not paste DataKit's log anywhere.** DataKit logs its full `ENV_DATAWAY` URL, and here that URL contains the
  FlowPorts source token. The same goes for `.lab/` and `.env`.
- DataKit behind FlowPorts logs 404s for its non-write calls (remote config pull, NTP, usage trace) and carries on;
  FlowPorts does not provide those endpoints.
- **Device time.** `default_time(cef_rt)` alone converts the field but leaves the row at FlowPorts receive time.
  `cef.p` renames the converted value to `time`, which makes the row time the device's `rt`.
- **Kafka `CreateTime` is the point's own time**, set by FlowPorts as the producer timestamp. An outage does not show up
  as a gap in it; use FlowPorts delivery state (`/api/v1/flows/<id>/delivery`) instead.
- **FlowPorts sets `source` to the source type**: `socket`, `netflowscout`, `otel_log`.
- **NetFlowScout records trace context, paths and headers only when asked**: `http.request_events`, `http.headers` and
  `privacy.raw_fields` in `netflowscout/netflowscout.json`. Its `http_path` excludes the query string.
- **Lab-tight joins.** Each probe request opens a new TCP connection, so IP + source port is unique here. Keep-alive,
  NAT and proxies were not tested; there the port is shared or rewritten.
- The probe stamps the CEF `rt` with its own send time, so device-to-span gaps measure the generator, not a device.

## Known behaviours (FlowPorts 0.5.6)

- **Socket source under Kafka back-pressure.** In one drill (broker killed 5 times, 4–6 s each, about 12 s apart, with
  one CEF line per TCP connection, 5 lines per request), the `socket` flow stopped counting received batches three
  seconds after the fourth kill and did not resume during the drill. The sender kept sending without a socket error;
  825 lines (requests 436–600) never reached Kafka or TrueWatch, and no drop, overflow or retry-exhausted counter moved.
  The DataKit (HTTP) flow in the same window lost nothing. Our reading, not confirmed: each one-line connection becomes
  its own batch, the Kafka branch's queue (166 batches) filled while retrying, and the socket source was back-pressured
  while the kernel kept accepting connections. Mitigation: send many lines per connection, and compare FlowPorts'
  `received` with the sender's own count rather than relying on the drop counters.
- **Updating a running `socket` flow did not install.** A pipeline-only change to a running socket flow stayed at
  `partial_failure` ("Configuration installation or Source startup failed"), and the worker kept running the previous
  revision, even after stop/start. A new flow with the same pipeline on another port installed at once. Our reading:
  the new revision cannot bind the port the old one still holds.

## Clean up

```bash
docker compose --profile tools down --volumes
docker image rm flowports-lab/app-java:local flowports-lab/app-python:local 2>/dev/null
rm -rf .lab out
```

The pulled images (Kafka, DataKit, base images) stay until you remove them.

## Not covered

amd64; keep-alive, NAT and load; multi-partition topics; the native FlowPorts `syslog` source; how the console's
security-event and APM views render route-B spans.
