# EcoTelemetry operations and build

Operational behavior and packaging, split out of [FEATURES.md](FEATURES.md) to
keep that file under the size cap.

## Operational tooling and resilience

- **Smoke-probe diagnostics** - Synchronous HTTP POST to the metrics endpoint on startup with a timeout. Result persisted to `Logs/EcoTelemetry/smoke-probe.txt` for visibility after journal rotation.
- **Console exporter fallback** - Empty OTLP endpoint defaults to the OpenTelemetry console exporter so admins can validate the signal pipeline locally.
- **Dual-export diagnostic mode** - Optional `EmitConsoleAlongsideOtlp` flag mirrors each export batch to stdout alongside OTLP. Diagnostic only, off by default.
- **Defensive error handling** - Log interception falls back gracefully if reflection fails. Exception hooks swallow internal errors to prevent re-entrance. `UserManager` readiness checks guard against early-init crashes.

## Build and deployment

- **Single-package mod distribution** - Release ZIP contains the precompiled DLL plus all transitive OpenTelemetry NuGet dependencies. No runtime `.nuget/` step required on the Eco server.
- **GitHub Actions release workflow** - Automates .NET build and dependency bundling.

## See also

- [FEATURES.md](FEATURES.md) - inventory of what ships today.
- [internals.md](internals.md) - design notes behind the source.
- [../README.md](../README.md) - human-facing intro.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
