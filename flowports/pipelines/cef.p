# Synthetic CEF over syslog (socket source, text lines) -> columns.
# Device time: default_time() only converts the field (to ns); the row time follows a key named `time`,
# so the converted value is renamed to `time`. Without the rename the row carries the FlowPorts receive time.
grok(_, "<%{INT:syslog_pri}>%{SYSLOGTIMESTAMP:syslog_ts} %{NOTSPACE:device_host} CEF:%{INT:cef_version}\\|%{DATA:cef_vendor}\\|%{DATA:cef_product}\\|%{DATA:cef_dev_version}\\|%{DATA:cef_sig}\\|%{DATA:cef_name}\\|%{INT:cef_severity}\\|%{GREEDYDATA:cef_ext}")
grok(cef_ext, "rt=%{INT:cef_rt} src=%{IP:client_ip} dst=%{IP:dst_ip} dpt=%{INT:dst_port} requestMethod=%{WORD:http_method} request=%{DATA:http_path} requestClientApplication=%{DATA:user_agent} act=%{WORD:cef_act} cs1Label=probeRun cs1=%{NOTSPACE:cef_probe_run}$")
replace(http_path, "\\\\=", "=")
replace(user_agent, "\\\\=", "=")
cast(cef_severity, "int")
cast(cef_rt, "int")
if cef_severity >= 7 {
  add_key(status, "warning")
} else {
  add_key(status, "info")
}
default_time(cef_rt)
rename(time, cef_rt)
drop_key(cef_ext)
set_tag(lab_run, "flowports-lab")
set_tag(signal, "device")
set_tag(client_ip)
