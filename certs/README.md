Put a PEM CA bundle here as `ca-bundle.pem` (git-ignored). FlowPorts runs on a bare `ubuntu` image without a CA
store and needs one to reach DataWay over HTTPS.

- macOS: `cp /etc/ssl/cert.pem certs/ca-bundle.pem`
- Debian/Ubuntu: `cp /etc/ssl/certs/ca-certificates.crt certs/ca-bundle.pem`
- Behind a TLS-inspecting proxy: append your organisation's root CA to that file.
