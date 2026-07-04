# EcoTelemetry internals

Durable design notes that back the one-line pointers in `src/`. Code comments
stay terse and link here for the full explanation.

## Config (EcoTelemetryConfig)

Loaded from `Configs/EcoTelemetry.json` at plugin init. Comments and trailing
commas are tolerated.

- `OtlpEndpoint` - fallback endpoint for any signal without its own override. Empty falls back to the console exporter.
- `OtlpProtocol` - `Grpc` or `HttpProtobuf`. Defaults to `HttpProtobuf` since most managed backends accept it.
- `OtlpHeaders` - W3C-style `key1=val1,key2=val2`. Auth tokens go here.
- `OtlpLogsEndpoint` / `OtlpMetricsEndpoint` / `OtlpTracesEndpoint` - per-signal overrides. Empty falls back to `OtlpEndpoint`. Common split: Sentry for logs, VictoriaMetrics for metrics, Tempo/Jaeger for traces.
- `EmitConsoleAlongsideOtlp` - when an OTLP metrics endpoint is set, also attach a console exporter so each export tick shows in the host log. Diagnostic only, off by default.
- `SlowHandlerThresholdMs` - handlers timed by `TraceSurface.TrackHandler` only emit a span when they take at least this long. Default 100ms. Applies once traces are enabled.
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

Instruments emitted (all under `EnableMetrics`):

- `eco.players.online` (gauge) - `UserManager.Obj.OnlineUserCount`.
- `eco.world_objects.count` (gauge, tagged `eco.world_object.type`) - one measurement per world-object C# type, counted through the static `WorldObjectManager.ForEach`. Using `ForEach` avoids a singleton lookup and lets the manager own iteration.
- `eco.sim.world_time_seconds` (counter) - `WorldTime.Seconds`, the monotonically increasing simulated clock.
- `eco.stats.*` (gauges) - a curated slice of `StatGameplaySettings.LatestGlobalStats` (population + economy). The set is deliberately narrow to keep the metric surface legible rather than mirroring every `GlobalStats` field.
- Runtime GC/threadpool/memory counters via `OpenTelemetry.Instrumentation.Runtime`.

Every callback is defensive: `UserManager`, `WorldObjectManager`, `WorldTime`,
and `GlobalStats` can all be unready during early init (or mutate on the game
thread mid-iteration), so each reads inside a `try` and reports 0 / whatever it
gathered rather than throwing into the OTel reader.

## Telemetry pipeline (TelemetryPipeline)

Owns the OTel SDK objects (LoggerFactory, MeterProvider, TracerProvider) for the
plugin lifetime. Each signal can route to its own endpoint.

The metrics path carries diagnostics tracked under issue #5:

- Diagnostic `Console.Error` prints go to stdout then the journal, so we can see which branch the config resolution lands in.
- Both `AddOtlpExporter` overloads silently failed to add a reader despite `Build` returning OK, so the exporter and reader are constructed manually and passed to `builder.AddReader`, bypassing the helper indirection.
- A synchronous smoke probe POSTs to the metrics endpoint on startup so we know the runtime can reach it before the periodic exporter starts. The result is persisted to `Logs/EcoTelemetry/smoke-probe.txt` so it survives journal rotation past the start-of-day window.

Trim these once the pipeline is proven end-to-end.

## Trace surface (TraceSurface)

`TraceSurface` owns the single `EcoTelemetry` `ActivitySource`. Spans only record
once `TelemetryPipeline.StartTraces` attaches a `TracerProvider` listening on that
source (under `EnableTraces`), so with traces off every helper is a cheap no-op
returning `null`.

Two helpers:

- `Start(name)` - opens a span for a unit of work, returns the `Activity` (or
  `null` when no listener). Used to wrap the plugin's own `Initialize` path.
- `TrackHandler(name, work, tags...)` - the slow-handler detector. It times
  `work` with a `Stopwatch` and, only when the elapsed time meets
  `SlowHandlerThresholdMs`, emits a span **backdated** to the real start (via the
  `StartActivity(..., startTime)` overload plus `SetEndTime`) so the span duration
  reflects the handler, not the after-the-fact span construction. The threshold
  gate keeps hot, fast handlers allocation-free. Exceptions thrown by `work` mark
  the span `Error` and still propagate.

The init sub-steps (exception capture, log interceptor, metrics install) are
wrapped in `TrackHandler`, so a pathologically slow startup step surfaces as a
span without adding noise when startup is fast.

Not yet wired, and left as follow-ups because they need Eco integration points
that cannot be exercised from this repo's build alone: wrapping *other* plugins'
init via `PluginManager` reflection, and a Kestrel request-pipeline hook. The
`TrackHandler` mechanism is the reusable primitive those call sites would use
once the hook points are confirmed on a live server.

## See also

- [FEATURES.md](FEATURES.md) - inventory of what ships today.
- [AGENTS.md](../../../AGENTS.md) - agent-facing operating rules.
- [README.md](../README.md) - human-facing intro.
