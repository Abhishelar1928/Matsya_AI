#!/usr/bin/env bash
# =============================================================================
# MatsyaAI — Local HTTPS certificates for testing on a phone (development only)
# =============================================================================
# Phones only allow GPS (Geolocation API) and service workers (offline mode) on a
# trusted HTTPS origin. This script creates:
#   1. A private development Certificate Authority  (ca.crt / ca.key)
#   2. A server certificate for your PC's LAN IP + localhost, signed by that CA
#
# Install ca.crt on the phone once (see README "Testing on a phone"); the Vite dev
# server then serves https://<LAN-IP>:5173 with no certificate warning.
#
# Usage:  bash scripts/dev-https/generate-dev-certs.sh [LAN_IP ...]
#         (auto-detects the Wi-Fi IPv4 address if none given)
#
# SECURITY: ca.key can mint certificates your phone will trust. It never leaves
# frontend/certs/ (git-ignored). Remove the CA from the phone when you are done.
# =============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1   # stop Git Bash rewriting "/CN=..." into a Windows path

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/frontend/certs"
mkdir -p "$OUT"
cd "$OUT"

IPS=("$@")
if [ ${#IPS[@]} -eq 0 ]; then
  if command -v powershell.exe >/dev/null 2>&1; then
    mapfile -t IPS < <(powershell.exe -NoProfile -Command \
      "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { \$_.IPAddress -notlike '127.*' -and \$_.IPAddress -notlike '169.254*' -and \$_.InterfaceAlias -notmatch 'vEthernet|WSL|Docker|Loopback' } | ForEach-Object { \$_.IPAddress }" | tr -d '\r')
  else
    mapfile -t IPS < <(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9.]+$' || true)
  fi
fi
[ ${#IPS[@]} -gt 0 ] || { echo "Could not detect LAN IP; pass it as an argument." >&2; exit 1; }
echo "LAN IPs: ${IPS[*]}"

# --- 1. Development CA (reused if it already exists, so the phone keeps trusting it)
if [ ! -f ca.key ] || [ ! -f ca.crt ]; then
  openssl genrsa -out ca.key 2048 2>/dev/null
  openssl req -x509 -new -key ca.key -sha256 -days 825 -out ca.crt \
    -subj "/CN=MatsyaAI Local Dev CA/O=MatsyaAI Development" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
  echo "Created development CA: $OUT/ca.crt"
else
  echo "Reusing existing CA: $OUT/ca.crt"
fi

# --- 2. Server certificate for localhost + LAN IPs (Chrome: max 398 days)
SAN="DNS:localhost,IP:127.0.0.1"
for ip in "${IPS[@]}"; do SAN="$SAN,IP:$ip"; done

cat > server.ext <<EOF
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN
EOF

openssl genrsa -out server.key 2048 2>/dev/null
openssl req -new -key server.key -out server.csr -subj "/CN=MatsyaAI dev server"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 397 -sha256 -extfile server.ext 2>/dev/null
rm -f server.csr server.ext

# Android installs CA certificates from DER or PEM; provide both.
openssl x509 -in ca.crt -outform DER -out ca.der.crt

echo
echo "Server certificate covers: $SAN"
openssl x509 -in server.crt -noout -subject -enddate
echo
echo "Next: restart the frontend  ->  docker compose up -d --force-recreate frontend"
for ip in "${IPS[@]}"; do
  echo "Phone: download the CA from  https://$ip:5173/dev-ca.crt  then open  https://$ip:5173/#expedition"
done
