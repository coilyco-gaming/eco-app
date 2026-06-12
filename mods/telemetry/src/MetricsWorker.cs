// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.Diagnostics.Metrics;
using System.Threading;
using System.Threading.Tasks;
using Eco.Gameplay.Players;
using Microsoft.Extensions.Logging;

/// <summary>Registers pull-based Eco metric instruments. See docs/internals.md.</summary>
internal sealed class MetricsWorker
{
    private readonly EcoTelemetryConfig config;
    private readonly ILogger? logger;

    public MetricsWorker(EcoTelemetryConfig config, ILogger? logger)
    {
        this.config = config;
        this.logger = logger;
    }

    public void Install(Meter meter)
    {
        if (!this.config.EnableMetrics) return;

        meter.CreateObservableGauge(
            name: "eco.players.online",
            observeValue: SafeOnlineUserCount,
            unit: "{players}",
            description: "Currently logged-in players.");

        this.logger?.LogInformation("EcoTelemetry: registered metrics (eco.players.online + runtime).");
    }

    private static int SafeOnlineUserCount()
    {
        try
        {
            return UserManager.Obj?.OnlineUserCount ?? 0;
        }
        catch
        {
            // UserManager may not be ready during early init. See docs/internals.md.
            return 0;
        }
    }

    public Task TickAsync(CancellationToken token)
    {
        // OTel polls observable instruments itself. Block until shutdown.
        return Task.Delay(Timeout.Infinite, token);
    }
}
