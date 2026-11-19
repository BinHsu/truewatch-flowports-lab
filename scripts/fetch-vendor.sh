#!/usr/bin/env bash
# Download the third-party pieces this repo does not redistribute, from their official locations, and refuse
# anything whose SHA-256 differs from the value pinned here. linux/arm64 only (what the lab was measured on).
#   vendor/flowports/      FlowPorts 0.5.6 (binary: collectway)
#   vendor/netflowscout/   NetFlowScout 0.3.0-dev-20261019-arm64-ba165ef4-r2
#   app/java/lib/          Beacon Java agent 1.3.4 + Tomcat embed 11.0.27 + H2 2.5.252 (test app)
# Read each vendor's licence and terms before you use their software; this script only fetches and verifies.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v curl >/dev/null || { echo "curl is required"; exit 1; }
if command -v sha256sum >/dev/null; then SHA="sha256sum"; else SHA="shasum -a 256"; fi

get() {  # get URL DEST SHA256
  local url=$1 dest=$2 want=$3
  if [ -f "$dest" ] && [ "$($SHA "$dest" | cut -d' ' -f1)" = "$want" ]; then echo "ok (cached) $dest"; return; fi
  mkdir -p "$(dirname "$dest")"
  curl -fsSL --proto '=https' --tlsv1.2 -o "$dest.part" "$url"
  local got; got=$($SHA "$dest.part" | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then rm -f "$dest.part"; echo "SHA-256 MISMATCH for $url: got $got, want $want"; exit 1; fi
  mv "$dest.part" "$dest"; echo "ok $dest"
}

DL=vendor/downloads
# FlowPorts 0.5.6 (https://flowport.pages.dev/en/downloads/ ; SHA256SUMS published next to the package)
FP_BUILD=5e449b1e594b71c0b764d3247e18725ddc1e36d1
get "https://flowport.pages.dev/releases/0.5.6/flowport_0.5.6_linux_arm64.tar.gz?build=$FP_BUILD" \
    "$DL/flowport_0.5.6_linux_arm64.tar.gz" cfc9c798652e4c080fc859246602e83246da50a7b754f23ae8f79e6327f0c868
# NetFlowScout (https://netflowscout-downloads.pages.dev/releases.json ; the package is published in three parts)
NFS_REL=https://netflowscout-downloads.pages.dev/releases/0.3.0-dev-20261019-arm64-ba165ef4-r2
get "$NFS_REL/netflowscout-linux-arm64.tar.gz.part01" "$DL/nfs.part01" f1563fd5d8aa167ef01bcc8610eabc98020f3705b588a5f23e1e69da0f7d7b63
get "$NFS_REL/netflowscout-linux-arm64.tar.gz.part02" "$DL/nfs.part02" 05832fb65e9cf6274997854d4308106c8861fac5b94a9e91a4eae7ce8d52174e
get "$NFS_REL/netflowscout-linux-arm64.tar.gz.part03" "$DL/nfs.part03" ef301f601b5fa17d835a0a8db649076732c4f449e323b7e763d0076ddbdc3c39
cat "$DL/nfs.part01" "$DL/nfs.part02" "$DL/nfs.part03" > "$DL/netflowscout-linux-arm64.tar.gz"
[ "$($SHA "$DL/netflowscout-linux-arm64.tar.gz" | cut -d' ' -f1)" = dadd5fefc9844b41600e321e9f08bc40a8d0943c737bfe81f29e6ff7fef95068 ] \
  || { echo "SHA-256 MISMATCH for the joined NetFlowScout package"; exit 1; }
# Beacon Java agent (GitHub release of beacon-observability/beacon-java) and the test app's JARs (Maven Central)
get https://github.com/beacon-observability/beacon-java/releases/download/v1.3.4/beacon-javaagent-1.3.4.jar \
    app/java/lib/beacon-javaagent-1.3.4.jar c23a7c79b01cc45c3046198a0d8a9ed2bf9b8b4aca74a893f69ef1b59e15b2d1
MC=https://repo1.maven.org/maven2
get "$MC/org/apache/tomcat/embed/tomcat-embed-core/11.0.27/tomcat-embed-core-11.0.27.jar" \
    app/java/lib/tomcat-embed-core-11.0.27.jar b71785ff101c0df501064b3e3b8c4a02e4f9cc3047a7fa686c41fc4edc2f0cb4
get "$MC/org/apache/tomcat/tomcat-annotations-api/11.0.27/tomcat-annotations-api-11.0.27.jar" \
    app/java/lib/tomcat-annotations-api-11.0.27.jar 34e004c54a23b8486a8f0c1541a31594afab12f85fbc84243a3271c4ce1b420b
get "$MC/com/h2database/h2/2.5.252/h2-2.5.252.jar" \
    app/java/lib/h2-2.5.252.jar 90b11dc413da82070ef15fc943282c1408e6ffd34fa68998335fea8603b5ff20

# Unpack into fresh directories (nothing from the archives is executed here).
rm -rf vendor/flowports vendor/netflowscout vendor/.x
mkdir -p vendor/.x/fp vendor/.x/nfs
tar -xzf "$DL/flowport_0.5.6_linux_arm64.tar.gz" -C vendor/.x/fp
tar -xzf "$DL/netflowscout-linux-arm64.tar.gz" -C vendor/.x/nfs
mv "$(dirname "$(find vendor/.x/fp -type f -name collectway | head -1)")" vendor/flowports
mv "$(dirname "$(dirname "$(find vendor/.x/nfs -type f -path '*/bin/netflowscout' | head -1)")")" vendor/netflowscout
rm -rf vendor/.x
echo "collectway: $($SHA vendor/flowports/collectway | cut -d' ' -f1)  (lab: e5044238eb7e2a84b8c37214744c9677ba15c532f900df2a7e8c37645d97d171)"
echo "netflowscout: $($SHA vendor/netflowscout/bin/netflowscout | cut -d' ' -f1)  (lab: ba165ef46ed6d0c0307198eae348454f0421f519cea659651dd0ac720d13dc84)"
