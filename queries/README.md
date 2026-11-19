# DQL for the lab

Run these in the TrueWatch console (Query Tools / DQL query). Each one passed the DQL syntax checker. Replace the trace id,
the client IP and the port with values from your own run: the probe prints its trace ids and client IP, and step 1
returns the span's `client_address` and `network_peer_port`.

**Name the columns.** With `*`, some columns were missing from FlowPorts OTLP log rows (`trace_id`, `span_id`); listing
them explicitly returned them.

## Join one request

Step 1, trace id: the wire event, the app span and the Beacon finding share it.

```
L::re(`.*`):(time, __docid, source, collectway_flow, trace_id, span_id, client_ip, client_port, http_path, user_agent) { trace_id = '5eeda2000000000000000000000002' } [30m]
```

```
T::re(`.*`):(time, __docid, service, resource, status, span_id, trace_id, client_address, network_peer_port) { trace_id = '5eeda2000000000000000000000002' } [30m]
```

```
E::re(`.*`):(time, __docid, rule, trace_id, server_span_id, occurrence_id) { df_source = 'beacon_security' and trace_id = '5eeda2000000000000000000000002' } [30m]
```

The finding's `server_span_id` is the server span's `span_id` (route A). On route B the finding is a log row in
`L::otel_log` and carries `span_id` instead.

Step 2, client IP + source port, for traffic without a traceparent: use the span's `client_address` and
`network_peer_port`.

```
L::netflowscout:(time, __docid, trace_id, client_ip, client_port, http_path, user_agent) { client_ip = '192.0.2.10' and client_port = 49152 } [30m]
```

Step 3, the device line: no trace id, no source port. Match the client IP and the path before `?`, then take the row
nearest in time to the span. With the `cef.p` time fix, the row time is the device's own `rt`.

```
L::socket:(time, __docid, cef_sig, cef_name, client_ip, http_path, user_agent, status) { client_ip = '192.0.2.10' and http_path = wildcard('/user*') } [30m]
```

## Count check

Rows per flow, to compare with the Kafka end offset and FlowPorts `sent` (`scripts/count-check.py`). Add the four
results per flow.

```
L::re(`.*`):(count(*)) { collectway_flow = re('lab-.*') } [1h] by collectway_flow
```

```
T::re(`.*`):(count(*)) { collectway_flow = re('lab-.*') } [1h] by collectway_flow
```

```
E::re(`.*`):(count(*)) { collectway_flow = re('lab-.*') } [1h] by collectway_flow
```

```
CO::re(`.*`):(count(*)) { collectway_flow = re('lab-.*') } [1h] by collectway_flow
```

## Drill

All device lines of the drill, to check that the sequence 1–240 is complete and nothing is duplicated. Count exact
rows rather than `count_distinct`, which is approximate.

```
L::socket:(cef_probe_run, __docid) { cef_probe_run = wildcard('lab-d1-*') } [1h] limit 1000
```
