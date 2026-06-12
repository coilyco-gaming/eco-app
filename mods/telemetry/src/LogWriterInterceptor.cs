// Copyright (c) Kai Siren. Licensed under the MIT License.

namespace EcoTelemetry;

using System;
using System.Reflection;
using Eco.Shared.Logging;
using Microsoft.Extensions.Logging;

/// <summary>Wraps Eco's ILogWriter to mirror logs into OTel.</summary>
internal sealed class LogWriterInterceptor : IDisposable
{
    private readonly ILogger logger;
    private ILogWriter? originalWriter;
    private FieldInfo? writerField;

    public LogWriterInterceptor(ILogger logger)
    {
        this.logger = logger;
    }

    public bool TryInstall()
    {
        try
        {
            this.writerField = typeof(Log).GetField("writer", BindingFlags.Static | BindingFlags.NonPublic);
            if (this.writerField is null) return false;

            var current = this.writerField.GetValue(null) as ILogWriter;
            if (current is null) return false;
            if (current is DecoratedLogWriter) return true; // already wrapped (e.g. plugin re-init)

            this.originalWriter = current;
            var wrapped = new DecoratedLogWriter(current, this.logger);
            this.writerField.SetValue(null, wrapped);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public void Dispose()
    {
        if (this.writerField is null || this.originalWriter is null) return;
        try
        {
            var current = this.writerField.GetValue(null) as ILogWriter;
            if (current is DecoratedLogWriter)
            {
                this.writerField.SetValue(null, this.originalWriter);
            }
        }
        catch
        {
            // best-effort cleanup
        }
    }

    private sealed class DecoratedLogWriter : ILogWriter
    {
        private readonly ILogWriter inner;
        private readonly ILogger sink;

        public DecoratedLogWriter(ILogWriter inner, ILogger sink)
        {
            this.inner = inner;
            this.sink = sink;
        }

        public void Write(string message)
        {
            this.inner.Write(message);
            this.SafeLog(LogLevel.Information, message, null);
        }

        public void WriteWarning(string message)
        {
            this.inner.WriteWarning(message);
            this.SafeLog(LogLevel.Warning, message, null);
        }

        public void WriteError(ref ILogWriter.ErrorInfo errorInfo, bool stripTagsForConsole = false)
        {
            this.inner.WriteError(ref errorInfo, stripTagsForConsole);
            this.SafeLog(LogLevel.Error, errorInfo.Message ?? "", errorInfo.Exception);
        }

        public void Debug(string message)
        {
            this.inner.Debug(message);
            this.SafeLog(LogLevel.Debug, message, null);
        }

        private void SafeLog(LogLevel level, string message, Exception? ex)
        {
            try
            {
                if (ex is not null) this.sink.Log(level, ex, "{Message}", message);
                else this.sink.Log(level, "{Message}", message);
            }
            catch
            {
                // never let telemetry interception break game logging
            }
        }
    }
}
