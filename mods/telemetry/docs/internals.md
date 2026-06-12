# EcoTelemetry internals

Durable design notes that back the one-line pointers in `src/`. Code comments
stay terse and link here for the full explanation.

## Config (EcoTelemetryConfig)

Loaded from `Configs/EcoTelemetry.json` at plugin init. Comments and trailing
commas are tolerated.

- `OtlpEndpoint` - fallback endpoint for any signal without its own override. Empty falls back to the console exporter.
- `OtlpProtocol` - `Grpc` or `HttpProtobuf`. Defaults to `HttpProtobuf` since most managed backends accept it.
- `OtlpHeaders` - W3C-style `key1=val1,key2=val2`. Auth tokens go here.
- `OtlpLogsEndpoint` / `OtlpMetricsEndpoint` - per-signal overrides. Empty falls back to `OtlpEndpoint`. Common split: Sentry for logs, VictoriaMetrics for metrics.
- `EmitConsoleAlongsideOtlp` - when an OTLP metrics endpoint is set, also attach a console exporter so each export tick shows in the host log. Diagnostic only, off by default.
- `FirstChanceExceptionsEnabled` - subscribe to `AppDomain.FirstChanceException`, which catches every throw including caught ones. High-volume on a busy server, off by default.
- `InterceptLogWriter` - wrap Eco's `ILogWriter` so warnings and errors flow through the OTel logs pipeline. Best-effort via reflection.

## Plugin lifecycle (EcoTelemetryPlugin)

The Eco server discovers the plugin via `IInitializablePlugin` and calls
`Initialize` once at startup. v1 wires the OTel pipeline plus exception capture.
Metrics and traces are present as stubs.

## Exception capture (ExceptionCapture)

`AppDomain.UnhandledException` catches fatal exits and is always on.
`FirstChanceException` catches every throw, is high-volume, and is config-gated.
The first-chance handler must be defensive: a logging failure inside it can
re-enter and recurse, so it swallows its own errors.

## Log writer interception (LogWriterInterceptor)

Wraps Eco's `ILogWriter` so every log line also flows through the OTel logs
pipeline. The game's `Log.Writer` is set-once, so replacing it after init means
reflecting on the static backing field. Best-effort: if the field shape changes,
the wrapper is skipped silently.

## Metrics worker (MetricsWorker)

Registers Eco-specific observable instruments on the supplied `Meter`. Gauges
are pull-based, so the OTel reader polls the callbacks on its export interval and
the worker has no per-tick work beyond staying alive until shutdown.
`UserManager` may not be ready during early init, so the player-count callback
reports 0 rather than throwing into the OTel reader.

## Telemetry pipeline (TelemetryPipeline)

Owns the OTel SDK objects (LoggerFactory, MeterProvider, TracerProvider) for the
plugin lifetime. Each signal can route to its own endpoint.

The metrics path carries diagnostics tracked under issue #5:

- Diagnostic `Console.Error` prints go to stdout then the journal, so we can see which branch the config resolution lands in.
- Both `AddOtlpExporter` overloads silently failed to add a reader despite `Build` returning OK, so the exporter and reader are constructed manually and passed to `builder.AddReader`, bypassing the helper indirection.
- A synchronous smoke probe POSTs to the metrics endpoint on startup so we know the runtime can reach it before the periodic exporter starts. The result is persisted to `Logs/EcoTelemetry/smoke-probe.txt` so it survives journal rotation past the start-of-day window.

Trim these once the pipeline is proven end-to-end.

## Trace surface (TraceSurface)

v1 stub. The plan is a single `ActivitySource` wrapped around plugin init, slow
handler detection, and web-request hooks once those integration points are
scoped. See the TODO in the source.

## See also

- [FEATURES.md](FEATURES.md) - inventory of what ships today.
- [../AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [../README.md](../README.md) - human-facing intro.
