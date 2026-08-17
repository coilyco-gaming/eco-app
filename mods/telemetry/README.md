# EcoTelemetry

OpenTelemetry-backed observability for [Eco](https://play.eco) game servers. Exports exceptions, runtime metrics, simulation perf, and traces over OTLP so server admins can point them at SigNoz, Grafana, Datadog, Honeycomb, or any other OTLP-compatible backend.

Eco's built-in stats system is designed for in-game economic and ecological reporting. It does not surface SRE-shaped signals: process health, exception rates, simulation tick latency, or web-request latency. EcoTelemetry fills that gap.

## Status

Early. v1 ships:

- **Logs:** exception capture (`AppDomain.UnhandledException`, optional `FirstChanceException`) and an Eco `ILogWriter` decorator that mirrors the server's own log lines through OTel.
- **Metrics:** runtime instrumentation (GC, threadpool, allocations) plus `eco.players.online`. Each signal can route to its own OTLP endpoint via per-signal overrides.

Traces are stubbed.

## Install

1. Download `EcoTelemetry-<version>.zip` from the [latest release](https://github.com/coilyco-flight-deck/eco-telemetry/releases).
2. Extract into your Eco server's `Mods/` directory so the result looks like `Mods/EcoTelemetry/EcoTelemetry.dll`.
3. Copy `Configs/EcoTelemetry.example.json` to `Configs/EcoTelemetry.json` and edit:
   - `OtlpEndpoint`: your collector's OTLP HTTP or gRPC endpoint
   - `OtlpHeaders`: any auth headers required by the selected OTLP backend
   - `ServiceName`, `ResourceAttributes`: how this server identifies itself
   - per-signal toggles: `EnableLogs`, `EnableMetrics`, `EnableTraces`
4. Restart the Eco server.

If `OtlpEndpoint` is empty, EcoTelemetry falls back to the console exporter so you can verify the pipeline locally before pointing it at a real backend.

## Build

```bash
dotnet build EcoTelemetry.csproj -c Release
```

The build pulls `Eco.ReferenceAssemblies` from NuGet for type-checking. The DLL plus its OpenTelemetry dependencies must be deployed together — see `.github/workflows/release.yml` for how the release artifact is assembled.

## Routing signals

Each signal (logs, metrics) can target its own OTLP endpoint via the `OtlpLogsEndpoint` / `OtlpMetricsEndpoint` overrides; anything left blank falls back to the top-level `OtlpEndpoint`. Empty everywhere means console exporter (handy for first-boot smoke test).

### SigNoz

Point `OtlpEndpoint` at the SigNoz collector. The collector accepts standard
OTLP and turns recorded exception span events into entries in the Exceptions
pane.

### VictoriaMetrics (metrics)

vmsingle exposes a native OTLP ingest endpoint at `/opentelemetry/api/v1/push` on its HTTP API port (8428 by default). No auth header required.

- `OtlpMetricsEndpoint`: `http://<vmsingle-host>:8428/opentelemetry/api/v1/push`
- `OtlpMetricsProtocol`: `HttpProtobuf`

Any OTLP-capable backend (Honeycomb, Grafana Cloud, OTel Collector) works the same way - there is no backend-specific code path.

## Public sources

EcoTelemetry is built against [Eco.ReferenceAssemblies](https://www.nuget.org/packages/Eco.ReferenceAssemblies) and the public modding documentation at <https://wiki.play.eco/en/Modding>, <https://docs.play.eco/>, and <https://github.com/StrangeLoopGames/EcoModKit>.

## License

MIT. See [LICENSE](LICENSE).

## Commands

Dev commands are declared in the repo-root [`justfile`](../../justfile). Run them as `just <verb>` (this mod builds via `just build-mod-telemetry`).

## See also

- [AGENTS.md](../../AGENTS.md) - agent-facing operating rules.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [justfile](../../justfile) - dev verbs.
- [.ward/ward.yaml](../../.ward/ward.yaml) - catalog metadata only.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
