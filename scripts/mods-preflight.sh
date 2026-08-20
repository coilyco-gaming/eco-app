#!/bin/sh
# Toolchain + NuGet egress preflight for the C# mod diagnostic. A blocked
# api.nuget.org is the failure this separates from a genuine build break.

set -eu

dotnet --version
dotnet --list-sdks

curl -fsS --max-time 20 -o /dev/null \
    -w 'api.nuget.org index: HTTP %{http_code} in %{time_total}s\n' \
    https://api.nuget.org/v3/index.json ||
    { echo "FAIL: api.nuget.org is unreachable from this runner." >&2; exit 1; }
