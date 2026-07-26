#!/bin/sh
# Resolve the eco game server base URL for the local dev loop, mirroring the
# ssh-config pattern from coilyco-flight-deck/infrastructure#294: prefer the
# plain-LAN mDNS path (the home router blackholes same-LAN tailnet WireGuard
# data), fall back to the SSM-resolved tailnet FQDN off-LAN, and last to the
# public host. Prints the chosen base URL on stdout; the path label goes to
# stderr. The tailnet FQDN stays out of tracked files and terminal output per
# the opaque-ids rule - only its SSM path is named here.
#
# An explicit ECO_INFO_URL wins outright: its base is reused so the admin and
# map endpoints target the same server, matching how server.py derives them.
set -eu

PORT="${ECO_INFO_PORT:-3001}"
PUBLIC_BASE="http://eco.coilysiren.me:${PORT}"
LAN_BASE="http://kai-server.local:${PORT}"
SSM_FQDN_PATH="/coilysiren/kai-server/tailnet-fqdn"

probe() {
    curl -fsS -o /dev/null --max-time "$2" "$1/info" 2>/dev/null
}

if [ -n "${ECO_INFO_URL:-}" ]; then
    echo "eco target: explicit ECO_INFO_URL" >&2
    printf '%s\n' "${ECO_INFO_URL%/info}"
    exit 0
fi

if probe "$LAN_BASE" 1; then
    echo "eco target: LAN (kai-server.local:${PORT})" >&2
    printf '%s\n' "$LAN_BASE"
    exit 0
fi

FQDN="$(ward-kdl ops aws ssm get-parameter --name "$SSM_FQDN_PATH" \
    --with-decryption --query Parameter.Value --output text 2>/dev/null || true)"
if [ -n "$FQDN" ] && probe "http://${FQDN}:${PORT}" 3; then
    echo "eco target: tailnet (SSM-resolved FQDN, not echoed)" >&2
    printf 'http://%s:%s\n' "$FQDN" "$PORT"
    exit 0
fi

echo "eco target: public (eco.coilysiren.me:${PORT})" >&2
printf '%s\n' "$PUBLIC_BASE"
