# Application signals (logs, spans, Beacon findings): tag only. Parsing happens upstream (DataKit or the OTel SDK).
set_tag(lab_run, "flowports-lab")
set_tag(signal, "app")
