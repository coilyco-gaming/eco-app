// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.Collections.Generic;
using System.Diagnostics.Metrics;
using System.Threading;
using System.Threading.Tasks;
using Eco.Gameplay.Objects;
using Eco.Gameplay.Players;
using Eco.Gameplay.Systems;
using Eco.Simulation.Time;
using Microsoft.Extensions.Logging;

/// <summary>Registers pull-based Eco metric instruments. See docs/internals.md.</summary>
internal sealed class MetricsWorker
{
    // GlobalStats fields exported under eco.stats.*. Name -> accessor, evaluated on
    // the OTel export thread. Kept curated (population + economy) rather than every
    // field so the metric cardinality stays legible. See docs/internals.md.
    private static readonly (string Name, string Description, Func<Eco.Gameplay.Stats.GlobalStats, double> Read)[] StatGauges =
    {
        ("eco.stats.citizen_population", "Total citizens.", s => s.CitizenPopulation),
        ("eco.stats.active_citizen_population", "Active (non-idle) citizens.", s => s.ActiveCitizenPopulation),
        ("eco.stats.animal_population", "Living animals in the world.", s => s.AnimalPopulation),
        ("eco.stats.tree_population", "Living trees in the world.", s => s.TreePopulation),
        ("eco.stats.plant_population", "Living plants in the world.", s => s.PlantPopulation),
        ("eco.stats.extinct_species", "Species that have gone extinct.", s => s.ExtinctSpecies),
        ("eco.stats.gdp", "Gross domestic product in the default currency.", s => s.GDP),
    };

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

        meter.CreateObservableGauge(
            name: "eco.world_objects.count",
            observeValues: SafeWorldObjectCounts,
            unit: "{objects}",
            description: "Placed world objects, tagged by object type.");

        meter.CreateObservableCounter(
            name: "eco.sim.world_time_seconds",
            observeValue: SafeWorldTimeSeconds,
            unit: "s",
            description: "Cumulative simulated world time.");

        foreach (var gauge in StatGauges)
        {
            var read = gauge.Read;
            meter.CreateObservableGauge(
                name: gauge.Name,
                observeValue: () => SafeStat(read),
                description: gauge.Description);
        }

        this.logger?.LogInformation(
            "EcoTelemetry: registered metrics (players.online, world_objects.count, sim.world_time_seconds, {StatCount} eco.stats.* + runtime).",
            StatGauges.Length);
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

    private static IEnumerable<Measurement<int>> SafeWorldObjectCounts()
    {
        var byType = new Dictionary<string, int>();
        try
        {
            // ForEach is the static, manager-owned iterator, so we do not have to
            // reach for the singleton or lock the collection ourselves.
            WorldObjectManager.ForEach(wo =>
            {
                if (wo is null) return;
                var type = wo.GetType().Name;
                byType[type] = byType.TryGetValue(type, out var n) ? n + 1 : 1;
            });
        }
        catch
        {
            // WorldObjectManager may mutate on the game thread mid-iteration or be
            // unready during early init. Emit whatever we gathered. See docs/internals.md.
        }

        var measurements = new List<Measurement<int>>(byType.Count);
        foreach (var kv in byType)
        {
            measurements.Add(new Measurement<int>(kv.Value, new KeyValuePair<string, object?>("eco.world_object.type", kv.Key)));
        }

        return measurements;
    }

    private static double SafeWorldTimeSeconds()
    {
        try
        {
            return WorldTime.Seconds;
        }
        catch
        {
            // WorldTime is a singleton that may not be initialized during early init.
            return 0d;
        }
    }

    private static double SafeStat(Func<Eco.Gameplay.Stats.GlobalStats, double> read)
    {
        try
        {
            var stats = StatGameplaySettings.LatestGlobalStats;
            return stats is null ? 0d : read(stats);
        }
        catch
        {
            // GlobalStats is populated by the stats plugin's periodic pass and is
            // null until the first tick. See docs/internals.md.
            return 0d;
        }
    }

    public Task TickAsync(CancellationToken token)
    {
        // OTel polls observable instruments itself. Block until shutdown.
        return Task.Delay(Timeout.Infinite, token);
    }
}
