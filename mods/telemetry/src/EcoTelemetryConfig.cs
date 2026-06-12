// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>Runtime config. Fields documented in docs/internals.md.</summary>
public sealed class EcoTelemetryConfig
{
    public string ServiceName { get; set; } = "eco-server";

    public Dictionary<string, string> ResourceAttributes { get; set; } = new();

    public string OtlpEndpoint { get; set; } = "";

    public string OtlpProtocol { get; set; } = "HttpProtobuf";

    public string OtlpHeaders { get; set; } = "";

    public string OtlpLogsEndpoint { get; set; } = "";
    public string OtlpLogsProtocol { get; set; } = "";
    public string OtlpLogsHeaders { get; set; } = "";

    public string OtlpMetricsEndpoint { get; set; } = "";
    public string OtlpMetricsProtocol { get; set; } = "";
    public string OtlpMetricsHeaders { get; set; } = "";

    public string ResolvedLogsEndpoint => Pick(this.OtlpLogsEndpoint, this.OtlpEndpoint);
    public string ResolvedLogsProtocol => Pick(this.OtlpLogsProtocol, this.OtlpProtocol);
    public string ResolvedLogsHeaders => Pick(this.OtlpLogsHeaders, this.OtlpHeaders);
    public string ResolvedMetricsEndpoint => Pick(this.OtlpMetricsEndpoint, this.OtlpEndpoint);
    public string ResolvedMetricsProtocol => Pick(this.OtlpMetricsProtocol, this.OtlpProtocol);
    public string ResolvedMetricsHeaders => Pick(this.OtlpMetricsHeaders, this.OtlpHeaders);

    private static string Pick(string specific, string fallback) => string.IsNullOrWhiteSpace(specific) ? fallback : specific;

    public bool EnableLogs { get; set; } = true;
    public bool EnableMetrics { get; set; } = false;
    public bool EnableTraces { get; set; } = false;

    public int MetricsIntervalSeconds { get; set; } = 15;

    /// <summary>Diagnostic dual export. See docs/internals.md.</summary>
    public bool EmitConsoleAlongsideOtlp { get; set; } = false;

    /// <summary>High-volume first-chance hook. See docs/internals.md.</summary>
    public bool FirstChanceExceptionsEnabled { get; set; } = false;

    /// <summary>Wrap Eco's ILogWriter. See docs/internals.md.</summary>
    public bool InterceptLogWriter { get; set; } = true;

    public static EcoTelemetryConfig Load(string path)
    {
        if (!File.Exists(path)) return new EcoTelemetryConfig();
        var json = File.ReadAllText(path);
        var opts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            ReadCommentHandling = JsonCommentHandling.Skip,
            AllowTrailingCommas = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        };
        return JsonSerializer.Deserialize<EcoTelemetryConfig>(json, opts) ?? new EcoTelemetryConfig();
    }
}
