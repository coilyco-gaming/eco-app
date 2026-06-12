// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.Collections.Generic;
using System.Diagnostics.Metrics;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Exporter;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;

/// <summary>Owns the OTel SDK objects per signal. See docs/internals.md.</summary>
internal sealed class TelemetryPipeline : IDisposable
{
    public const string MeterName = "EcoTelemetry";

    public ILoggerFactory? LoggerFactory { get; private set; }
    public ILogger? Logger { get; private set; }
    public MeterProvider? MeterProvider { get; private set; }
    public Meter? Meter { get; private set; }

    private readonly EcoTelemetryConfig config;
    private ResourceBuilder? resourceBuilder;

    public TelemetryPipeline(EcoTelemetryConfig config)
    {
        this.config = config;
    }

    public void Start()
    {
        var version = typeof(TelemetryPipeline).Assembly.GetName().Version?.ToString() ?? "0.0.0";

        this.resourceBuilder = ResourceBuilder.CreateDefault()
            .AddService(serviceName: this.config.ServiceName, serviceVersion: version)
            .AddAttributes(BuildResourceAttributes());

        if (this.config.EnableLogs)
        {
            this.StartLogs();
        }

        if (this.config.EnableMetrics)
        {
            this.StartMetrics(version);
        }
    }

    private void StartLogs()
    {
        this.LoggerFactory = Microsoft.Extensions.Logging.LoggerFactory.Create(builder =>
        {
            builder.AddOpenTelemetry(options =>
            {
                options.IncludeFormattedMessage = true;
                options.IncludeScopes = true;
                options.ParseStateValues = true;
                options.SetResourceBuilder(this.resourceBuilder!);

                if (string.IsNullOrWhiteSpace(this.config.ResolvedLogsEndpoint))
                {
                    options.AddConsoleExporter();
                }
                else
                {
                    options.AddOtlpExporter(otlp => ConfigureOtlp(
                        otlp,
                        this.config.ResolvedLogsEndpoint,
                        this.config.ResolvedLogsProtocol,
                        this.config.ResolvedLogsHeaders));
                }
            });
        });

        this.Logger = this.LoggerFactory.CreateLogger("EcoTelemetry");
    }

    private void StartMetrics(string version)
    {
        this.Meter = new Meter(MeterName, version);

        var builder = Sdk.CreateMeterProviderBuilder()
            .SetResourceBuilder(this.resourceBuilder!)
            .AddMeter(MeterName)
            .AddMeter("OpenTelemetry.Instrumentation.Runtime")
            .AddRuntimeInstrumentation();

        // Diagnostic prints while #5 is open. See docs/internals.md.
        Console.Error.WriteLine($"[EcoTelemetry] StartMetrics: ResolvedMetricsEndpoint=[{this.config.ResolvedMetricsEndpoint}] OtlpMetricsEndpoint=[{this.config.OtlpMetricsEndpoint}] OtlpEndpoint=[{this.config.OtlpEndpoint}] EmitConsoleAlongsideOtlp={this.config.EmitConsoleAlongsideOtlp}");

        if (string.IsNullOrWhiteSpace(this.config.ResolvedMetricsEndpoint))
        {
            Console.Error.WriteLine("[EcoTelemetry] StartMetrics: empty endpoint -> Console-only exporter");
            builder.AddConsoleExporter();
        }
        else
        {
            Console.Error.WriteLine($"[EcoTelemetry] StartMetrics: attaching OTLP exporter to {this.config.ResolvedMetricsEndpoint}");
            // Manual exporter + reader: AddOtlpExporter added no reader. Refs #5.
            var otlpOptions = new OtlpExporterOptions();
            ConfigureOtlp(
                otlpOptions,
                this.config.ResolvedMetricsEndpoint,
                this.config.ResolvedMetricsProtocol,
                this.config.ResolvedMetricsHeaders);
            var otlpExporter = new OtlpMetricExporter(otlpOptions);
            var otlpReader = new PeriodicExportingMetricReader(
                otlpExporter,
                exportIntervalMilliseconds: this.config.MetricsIntervalSeconds * 1000)
            {
                TemporalityPreference = MetricReaderTemporalityPreference.Cumulative,
            };
            builder.AddReader(otlpReader);
            Console.Error.WriteLine("[EcoTelemetry] StartMetrics: manual OTLP reader added");

            // Synchronous smoke probe, persisted to a file. Refs #5.
            var smokePath = "Logs/EcoTelemetry/smoke-probe.txt";
            try
            {
                System.IO.Directory.CreateDirectory("Logs/EcoTelemetry");
                using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(5) };
                using var req = new System.Net.Http.HttpRequestMessage(
                    System.Net.Http.HttpMethod.Post, this.config.ResolvedMetricsEndpoint);
                req.Content = new System.Net.Http.ByteArrayContent(Array.Empty<byte>());
                req.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/x-protobuf");
                var resp = http.Send(req);
                var msg = $"{DateTime.UtcNow:O} smoke probe to {this.config.ResolvedMetricsEndpoint} -> HTTP {(int)resp.StatusCode}";
                Console.Error.WriteLine($"[EcoTelemetry] {msg}");
                System.IO.File.WriteAllText(smokePath, msg + Environment.NewLine);
            }
            catch (Exception ex)
            {
                var msg = $"{DateTime.UtcNow:O} smoke probe FAILED: {ex.GetType().Name}: {ex.Message}";
                Console.Error.WriteLine($"[EcoTelemetry] {msg}");
                try { System.IO.File.WriteAllText(smokePath, msg + Environment.NewLine); } catch { }
            }

            // Diagnostic console export alongside OTLP. Refs #5.
            if (this.config.EmitConsoleAlongsideOtlp)
            {
                Console.Error.WriteLine("[EcoTelemetry] StartMetrics: also attaching Console exporter (EmitConsoleAlongsideOtlp=true)");
                builder.AddConsoleExporter();
            }
        }

        try
        {
            this.MeterProvider = builder.Build();
            Console.Error.WriteLine("[EcoTelemetry] StartMetrics: MeterProvider built OK");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[EcoTelemetry] StartMetrics: MeterProvider build FAILED: {ex}");
            throw;
        }
    }

    private static void ConfigureOtlp(OtlpExporterOptions otlp, string endpoint, string protocol, string headers)
    {
        otlp.Endpoint = new Uri(endpoint);
        otlp.Protocol = string.Equals(protocol, "Grpc", StringComparison.OrdinalIgnoreCase)
            ? OtlpExportProtocol.Grpc
            : OtlpExportProtocol.HttpProtobuf;
        if (!string.IsNullOrWhiteSpace(headers))
        {
            otlp.Headers = headers;
        }
    }

    private IEnumerable<KeyValuePair<string, object>> BuildResourceAttributes()
    {
        foreach (var kv in this.config.ResourceAttributes)
        {
            yield return new KeyValuePair<string, object>(kv.Key, kv.Value);
        }
    }

    public void Dispose()
    {
        this.MeterProvider?.Dispose();
        this.MeterProvider = null;
        this.Meter?.Dispose();
        this.Meter = null;
        this.LoggerFactory?.Dispose();
        this.LoggerFactory = null;
        this.Logger = null;
    }
}
