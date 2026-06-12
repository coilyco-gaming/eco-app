# EcoTelemetry features

Baseline snapshot of what this repo does. Compare against this to detect scope drift over time.

Last refreshed: 2026-05-08, against v0.1.0.

## What this repo is

EcoTelemetry is an OpenTelemetry-backed observability mod for Eco game servers. It bridges Eco's built-in economic and ecological stats with SRE-shaped operational signals (logs, metrics, runtime health, exceptions) and exports them over OTLP to any compatible backend (Sentry, Grafana, VictoriaMetrics, Honeycomb, Datadog, others). Ships as a precompiled DLL that drops into the server's `Mods/` directory and reads JSON config from `Configs/`.

## Headline features

### Telemetry signals

- **Exception capture** - Subscribes to `AppDomain.UnhandledException` (always on) plus an optional `FirstChanceException` hook for high-volume exception tracing.
- **Log interception** - Mirrors Eco's built-in `ILogWriter` through the OTel logs pipeline via a reflection-based decorator. Warnings and errors flow to the backend.
- **Runtime metrics** - Auto-instruments .NET runtime via `OpenTelemetry.Instrumentation.Runtime` (GC, threadpool, memory allocation counters).
- **Player online gauge** - Exports `eco.players.online` as an observable metric pulled from `UserManager.OnlineUserCount`.

### Configuration and routing

- **Per-signal endpoint overrides** - Logs can route to Sentry, metrics to VictoriaMetrics, and so on. Each signal independently configurable with its own OTLP endpoint, protocol (gRPC or HttpProtobuf), and auth headers.
- **Fallback endpoint logic** - Per-signal endpoint, protocol, and headers fall back to top-level defaults. Empty everywhere triggers a console-only exporter for local validation.
- **JSON config file** - `Configs/EcoTelemetry.json`, loaded at plugin init. Comments and trailing commas supported. Sensible defaults plus optional resource attributes for service metadata.
- **Toggleable signals** - Feature flags `EnableLogs`, `EnableMetrics`, `EnableTraces` (traces stubbed for v1). Metrics export interval configurable (default 15s).

### Operations and build

Operational tooling, resilience, and packaging live in [operations.md](operations.md).

## Scope and boundaries

- **Version** - v0.1.0 (early). Targets `net10.0` to match current Eco `EcoServerTargetFramework`. Pinned to OpenTelemetry SDK 1.12.0.
- **Out of scope (today)** - Traces are stubbed and earmarked for v2. No `IConfigurablePlugin` web UI integration. No runtime modification of game-simulation logic.
- **Eco version coupling** - Depends on the `Eco.ReferenceAssemblies` NuGet package (currently 0.13.0-beta-release-998). No forward or backward compatibility guarantees.
- **Public repo discipline** - All references anchor to public wikis (`wiki.play.eco/en/Modding`, `docs.play.eco/`) and the official ModKit on GitHub. No internal Eco source leaks.

## See also

- [README.md](../README.md) - human-facing intro.
- [AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [.coily/coily.yaml](../.coily/coily.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
