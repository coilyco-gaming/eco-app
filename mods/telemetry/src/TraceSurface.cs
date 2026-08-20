// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.Collections.Generic;
using System.Diagnostics;

/// <summary>Owns the trace ActivitySource and the span helpers. See ../docs/internals.md.</summary>
internal static class TraceSurface
{
    public const string ActivitySourceName = "EcoTelemetry";

    public static readonly ActivitySource Source = new(ActivitySourceName);

    // Handlers faster than this are not worth a span. Set from config by the pipeline
    // when traces start; a sensible default keeps direct callers safe before then.
    private static long slowHandlerThresholdMs = 100;

    public static void Configure(int thresholdMs)
    {
        slowHandlerThresholdMs = Math.Max(0, thresholdMs);
    }

    /// <summary>
    /// Starts a span for a named unit of work. Returns null when no tracer is
    /// listening (traces disabled), so callers pattern-match with `?.`. Dispose to end.
    /// </summary>
    public static Activity? Start(string name, ActivityKind kind = ActivityKind.Internal)
    {
        return Source.StartActivity(name, kind);
    }

    /// <summary>
    /// Runs <paramref name="work"/> and, only if it takes at least the configured
    /// slow-handler threshold, emits a retroactive span covering that window. The
    /// threshold gate keeps the fast path free of span allocation on hot handlers.
    /// </summary>
    public static void TrackHandler(string name, Action work, params (string Key, object? Value)[] tags)
    {
        var startedAt = DateTimeOffset.UtcNow;
        var sw = Stopwatch.StartNew();
        try
        {
            work();
        }
        finally
        {
            sw.Stop();
            EmitIfSlow(name, startedAt, sw.Elapsed, error: null, tags);
        }
    }

    /// <summary>Result-returning overload of <see cref="TrackHandler(string, Action, ValueTuple{string, object}[])"/>.</summary>
    public static T TrackHandler<T>(string name, Func<T> work, params (string Key, object? Value)[] tags)
    {
        var startedAt = DateTimeOffset.UtcNow;
        var sw = Stopwatch.StartNew();
        Exception? error = null;
        try
        {
            return work();
        }
        catch (Exception ex)
        {
            error = ex;
            throw;
        }
        finally
        {
            sw.Stop();
            EmitIfSlow(name, startedAt, sw.Elapsed, error, tags);
        }
    }

    private static void EmitIfSlow(
        string name,
        DateTimeOffset startedAt,
        TimeSpan elapsed,
        Exception? error,
        IReadOnlyList<(string Key, object? Value)> tags)
    {
        if (elapsed.TotalMilliseconds < slowHandlerThresholdMs)
        {
            return;
        }

        // Backdate the span to the real start so its duration reflects the handler,
        // not the time spent building it after the fact.
        using var activity = Source.StartActivity(name, ActivityKind.Internal, default(ActivityContext), startTime: startedAt);
        if (activity is null)
        {
            return;
        }

        activity.SetTag("eco.handler", name);
        activity.SetTag("eco.duration_ms", elapsed.TotalMilliseconds);
        activity.SetTag("eco.slow_threshold_ms", slowHandlerThresholdMs);
        foreach (var (key, value) in tags)
        {
            activity.SetTag(key, value);
        }

        if (error is not null)
        {
            activity.SetStatus(ActivityStatusCode.Error, error.Message);
            activity.SetTag("exception.type", error.GetType().FullName);
        }

        activity.SetEndTime((startedAt + elapsed).UtcDateTime);
    }
}
