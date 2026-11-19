# Optional, route B only (OTLP straight into FlowPorts): fill the APM columns that DataKit sets on spans.
# scripts/flowports-setup.py --map-direct-spans installs it as the tracing pipeline of flow lab-app.
set_tag(lab_run, "flowports-lab")
set_tag(signal, "app")
add_key(resource, span_name)
if status_code == 2 {
  set_tag(status, "error")
} else {
  set_tag(status, "ok")
}
if span_kind == 2 {
  set_tag(span_type, "entry")
} elif span_kind == 3 {
  set_tag(span_type, "exit")
} else {
  set_tag(span_type, "local")
}
duration = duration / 1000
cast(duration, "int")
