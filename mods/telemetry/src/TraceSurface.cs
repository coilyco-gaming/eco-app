// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System.Diagnostics;

/// <summary>v1 traces stub. Planned surface in docs/internals.md.</summary>
internal static class TraceSurface
{
    public const string ActivitySourceName = "EcoTelemetry";

    public static readonly ActivitySource Source = new(ActivitySourceName);

    // TODO(traces): see docs/internals.md for the planned span surface.
}
