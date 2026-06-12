// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Eco.Core.Plugins.Interfaces;
using Eco.Core.Utils;
using Microsoft.Extensions.Logging;

/// <summary>Plugin entry point. Lifecycle in docs/internals.md.</summary>
public sealed class EcoTelemetryPlugin : IModKitPlugin, IInitializablePlugin, IShutdownablePlugin, IWorkerPlugin
{
    private const string ConfigPath = "Configs/EcoTelemetry.json";

    private EcoTelemetryConfig config = new();
    private TelemetryPipeline? pipeline;
    private ExceptionCapture? exceptionCapture;
    private LogWriterInterceptor? logInterceptor;
    private MetricsWorker? metricsWorker;

    public string GetCategory() => "Observability";

    public string GetStatus()
    {
        if (this.pipeline?.Logger is null) return "disabled";
        var dest = string.IsNullOrWhiteSpace(this.config.OtlpEndpoint) ? "console" : this.config.OtlpEndpoint;
        return $"exporting to {dest}";
    }

    public void Initialize(TimedTask timer)
    {
        try
        {
            this.config = EcoTelemetryConfig.Load(ConfigPath);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[EcoTelemetry] Failed to load {ConfigPath}: {ex.Message}. Continuing with defaults.");
            this.config = new EcoTelemetryConfig();
        }

        this.pipeline = new TelemetryPipeline(this.config);
        this.pipeline.Start();

        if (this.pipeline.Logger is { } logger)
        {
            this.exceptionCapture = new ExceptionCapture(logger, this.config.FirstChanceExceptionsEnabled);
            this.exceptionCapture.Install();

            if (this.config.InterceptLogWriter)
            {
                this.logInterceptor = new LogWriterInterceptor(logger);
                if (!this.logInterceptor.TryInstall())
                {
                    logger.LogWarning("EcoTelemetry: could not install log writer interceptor (reflection failed). Logs from Eco's Log.* will not be forwarded; exceptions still are.");
                }
            }

            logger.LogInformation("EcoTelemetry initialized: service={ServiceName} endpoint={Endpoint}",
                this.config.ServiceName,
                string.IsNullOrWhiteSpace(this.config.OtlpEndpoint) ? "console" : this.config.OtlpEndpoint);
        }

        this.metricsWorker = new MetricsWorker(this.config, this.pipeline.Logger);
        if (this.pipeline.Meter is { } meter)
        {
            this.metricsWorker.Install(meter);
        }
    }

    public Task DoWork(CancellationToken token)
    {
        return this.metricsWorker?.TickAsync(token) ?? Task.Delay(TimeSpan.FromMinutes(5), token);
    }

    public Task ShutdownAsync()
    {
        this.logInterceptor?.Dispose();
        this.exceptionCapture?.Dispose();
        this.pipeline?.Dispose();
        return Task.CompletedTask;
    }
}
