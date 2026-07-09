#!/bin/sh

set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

timed() {
    label=$1
    shift

    start=$(date +%s)
    printf '::group::%s\n' "$label"
    if "$@"; then
        status=0
    else
        status=$?
    fi
    elapsed=$(( $(date +%s) - start ))

    if [ "$status" -eq 0 ]; then
        printf '%s finished in %ss\n' "$label" "$elapsed"
    else
        printf '%s failed after %ss\n' "$label" "$elapsed" >&2
    fi
    printf '::endgroup::\n'

    return "$status"
}

restore_then_build() {
    label=$1
    project=$2
    config=${3:-Release}

    timed "$label: restore" dotnet restore "$project" -c "$config" --nologo -v minimal
    timed "$label: build" dotnet build "$project" -c "$config" --no-restore --nologo -v minimal
}

restore_then_test() {
    label=$1
    project=$2
    config=${3:-Release}

    timed "$label: restore" dotnet restore "$project" -c "$config" --nologo -v minimal
    timed "$label: test" dotnet test "$project" -c "$config" --no-restore --nologo -v minimal
}

case "${1:-}" in
    build-mods)
        echo "build-mods gate: restore/build each project once, then fail fast on the first broken phase."
        restore_then_build "mods/jobs" "$ROOT/mods/jobs/src/EcoJobsTracker.csproj"
        restore_then_build "mods/replay" "$ROOT/mods/replay/src/EcoReplay.csproj"
        restore_then_build "mods/telemetry" "$ROOT/mods/telemetry/EcoTelemetry.csproj"
        restore_then_build "mods/stores" "$ROOT/mods/stores/src/EcoStoreExporter.csproj"
        ;;
    test-mod-replay)
        echo "test-mod-replay gate: restore/test the replay project once, then fail fast on the first broken phase."
        restore_then_test "mods/replay tests" "$ROOT/mods/replay/tests/EcoReplay.Tests.csproj"
        ;;
    *)
        echo "usage: $0 {build-mods|test-mod-replay}" >&2
        exit 2
        ;;
esac
