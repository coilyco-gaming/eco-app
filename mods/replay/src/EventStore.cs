using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Channels;

namespace EcoReplay;

public record EventRow
{
    [JsonPropertyName("id")]
    public long Id { get; init; }

    [JsonPropertyName("unixTime")]
    public long UnixTimeSeconds { get; init; }

    [JsonPropertyName("gameTime")]
    public int GameTimeSeconds { get; init; }

    [JsonPropertyName("type")]
    public string ActionType { get; init; } = "";

    [JsonPropertyName("citizen")]
    public string? Citizen { get; init; }

    [JsonPropertyName("body")]
    public string BodyJson { get; init; } = "{}";
}

// Append-only JSONL event log under Eco's Storage directory. Insert only
// touches a bounded channel. A single background writer assigns monotonic ids,
// serializes complete lines, and periodically compacts the file to the newest
// retentionMaxRows. Readers skip malformed lines, including a partial final
// write left by a hard process stop.
public class EventStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    private readonly object queueCountLock = new();
    private Channel<EventRow>? channel;
    private Task? drainTask;
    private CancellationTokenSource? cts;
    private long droppedOnClosed;
    private long writeErrors;
    private long persistedRows;
    private long nextId;
    private int queuedRows;
    private int peakQueuedRows;
    private int rowsSincePrune;
    private int ready;

    public const int ChannelCapacity = 4096;
    public const int DefaultRetentionMaxRows = 2_000_000;
    private const int BatchSize = 100;
    private const int BatchLingerMs = 250;
    private readonly int retentionMaxRows;
    private readonly int retentionPruneEveryRows;

    public bool IsReady => Volatile.Read(ref ready) == 1;
    public string FilePath { get; }

    public EventStore(
        string filePath = "Storage/EcoReplay.jsonl",
        int retentionMaxRows = DefaultRetentionMaxRows)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        ArgumentOutOfRangeException.ThrowIfLessThan(retentionMaxRows, 1);
        FilePath = filePath;
        this.retentionMaxRows = retentionMaxRows;
        retentionPruneEveryRows = Math.Min(retentionMaxRows, 10_000);
    }

    public long DroppedCount => Interlocked.Read(ref droppedOnClosed);
    public long WriteErrorCount => Interlocked.Read(ref writeErrors);
    public int PeakQueuedRows => Volatile.Read(ref peakQueuedRows);
    public int RetentionMaxRows => retentionMaxRows;

    public void Open()
    {
        if (IsReady) return;
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath) ?? ".");
        if (!File.Exists(FilePath)) File.WriteAllText(FilePath, "", new UTF8Encoding(false));
        EnsureAppendBoundary();

        var (count, maxId) = ScanMetadata();
        Interlocked.Exchange(ref persistedRows, count);
        Interlocked.Exchange(ref nextId, Math.Max(maxId, count));
        rowsSincePrune = 0;
        queuedRows = 0;
        peakQueuedRows = 0;

        if (count > retentionMaxRows) CompactRetainedRows();

        channel = Channel.CreateBounded<EventRow>(new BoundedChannelOptions(ChannelCapacity)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = true,
            SingleWriter = false,
        });
        cts = new CancellationTokenSource();
        Volatile.Write(ref ready, 1);
        drainTask = Task.Run(() => DrainLoopAsync(cts.Token));
    }

    public void Close()
    {
        Volatile.Write(ref ready, 0);
        channel?.Writer.TryComplete();
        try
        {
            drainTask?.Wait(TimeSpan.FromSeconds(5));
        }
        catch
        {
            // Best-effort flush on shutdown. A stuck writer must not hang Eco.
        }
        cts?.Cancel();

        if (drainTask?.IsCompleted != false)
        {
            try
            {
                if (Interlocked.Read(ref persistedRows) > retentionMaxRows) CompactRetainedRows();
            }
            catch
            {
                Interlocked.Increment(ref writeErrors);
            }
        }

        cts?.Dispose();
        cts = null;
        channel = null;
        drainTask = null;
    }

    public void Insert(EventRow row)
    {
        var writer = channel?.Writer;
        if (writer == null || !IsReady) return;

        lock (queueCountLock)
        {
            if (!writer.TryWrite(row))
            {
                Interlocked.Increment(ref droppedOnClosed);
                return;
            }

            var queued = ++queuedRows;
            ObservePeakQueue(queued);
        }
    }

    private async Task DrainLoopAsync(CancellationToken ct)
    {
        var reader = channel!.Reader;
        var batch = new List<EventRow>(BatchSize);

        try
        {
            while (await reader.WaitToReadAsync(ct).ConfigureAwait(false))
            {
                batch.Clear();
                while (batch.Count < BatchSize && TryRead(reader, out var row)) batch.Add(row);

                if (batch.Count < BatchSize)
                {
                    using var linger = CancellationTokenSource.CreateLinkedTokenSource(ct);
                    linger.CancelAfter(BatchLingerMs);
                    try
                    {
                        while (batch.Count < BatchSize
                               && await reader.WaitToReadAsync(linger.Token).ConfigureAwait(false))
                        {
                            while (batch.Count < BatchSize && TryRead(reader, out var row))
                                batch.Add(row);
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        // The coalescing window elapsed or the store is closing.
                    }
                }

                if (batch.Count > 0) TryFlushBatch(batch);
            }
        }
        catch (OperationCanceledException)
        {
            // Hard stop. The final drain below still preserves queued rows.
        }

        batch.Clear();
        while (TryRead(reader, out var row))
        {
            batch.Add(row);
            if (batch.Count < BatchSize) continue;
            TryFlushBatch(batch);
            batch.Clear();
        }
        if (batch.Count > 0) TryFlushBatch(batch);
    }

    private void TryFlushBatch(List<EventRow> batch)
    {
        try
        {
            FlushBatch(batch);
        }
        catch
        {
            Interlocked.Increment(ref writeErrors);
        }
    }

    private void FlushBatch(List<EventRow> batch)
    {
        var text = new StringBuilder();
        foreach (var source in batch)
        {
            var row = source with { Id = Interlocked.Increment(ref nextId) };
            text.AppendLine(JsonSerializer.Serialize(row, JsonOptions));
        }

        using (var stream = new FileStream(
                   FilePath,
                   FileMode.Append,
                   FileAccess.Write,
                   FileShare.ReadWrite | FileShare.Delete))
        using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
        {
            writer.Write(text.ToString());
            writer.Flush();
        }

        Interlocked.Add(ref persistedRows, batch.Count);
        rowsSincePrune += batch.Count;
        if (Interlocked.Read(ref persistedRows) > retentionMaxRows
            && rowsSincePrune >= retentionPruneEveryRows)
        {
            CompactRetainedRows();
            rowsSincePrune = 0;
        }
    }

    private bool TryRead(ChannelReader<EventRow> reader, out EventRow row)
    {
        lock (queueCountLock)
        {
            if (reader.TryRead(out row!))
            {
                queuedRows--;
                return true;
            }
        }

        row = default!;
        return false;
    }

    private void ObservePeakQueue(int queued)
    {
        while (queued > Volatile.Read(ref peakQueuedRows))
        {
            var observed = Volatile.Read(ref peakQueuedRows);
            if (Interlocked.CompareExchange(ref peakQueuedRows, queued, observed) == observed) return;
        }
    }

    private (long Count, long MaxId) ScanMetadata()
    {
        long count = 0;
        long maxId = 0;
        foreach (var row in ReadRows())
        {
            count++;
            maxId = Math.Max(maxId, row.Id);
        }
        return (count, maxId);
    }

    private void EnsureAppendBoundary()
    {
        using var stream = new FileStream(
            FilePath,
            FileMode.Open,
            FileAccess.ReadWrite,
            FileShare.ReadWrite | FileShare.Delete);
        if (stream.Length == 0) return;
        stream.Seek(-1, SeekOrigin.End);
        if (stream.ReadByte() == '\n') return;
        stream.Seek(0, SeekOrigin.End);
        stream.WriteByte((byte)'\n');
        stream.Flush();
    }

    private IEnumerable<EventRow> ReadRows(string? path = null)
    {
        var source = path ?? FilePath;
        if (!File.Exists(source)) yield break;

        using var stream = new FileStream(
            source,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete);
        using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        while (reader.ReadLine() is { } line)
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            EventRow? row;
            try
            {
                row = JsonSerializer.Deserialize<EventRow>(line, JsonOptions);
            }
            catch (JsonException)
            {
                continue;
            }
            if (row == null || row.Id <= 0 || string.IsNullOrWhiteSpace(row.ActionType)) continue;
            yield return row;
        }
    }

    private void CompactRetainedRows()
    {
        var validCount = ScanMetadata().Count;
        if (validCount <= retentionMaxRows)
        {
            Interlocked.Exchange(ref persistedRows, validCount);
            return;
        }

        var skip = validCount - retentionMaxRows;
        var tempPath = FilePath + ".compact.tmp";
        using (var stream = new FileStream(tempPath, FileMode.Create, FileAccess.Write, FileShare.None))
        using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
        {
            long seen = 0;
            foreach (var row in ReadRows())
            {
                if (seen++ < skip) continue;
                writer.WriteLine(JsonSerializer.Serialize(row, JsonOptions));
            }
            writer.Flush();
        }

        File.Move(tempPath, FilePath, overwrite: true);
        Interlocked.Exchange(ref persistedRows, retentionMaxRows);
    }

    public long RowCount() => Interlocked.Read(ref persistedRows);

    public IReadOnlyList<EventRow> Query(
        string? citizen, string? actionType, int limit, long? sinceUnix, long? beforeId)
    {
        var capped = Math.Clamp(limit, 1, 1000);
        var newest = new Queue<EventRow>(capped);
        foreach (var row in ReadRows())
        {
            if (citizen != null && row.Citizen != citizen) continue;
            if (actionType != null && row.ActionType != actionType) continue;
            if (sinceUnix != null && row.UnixTimeSeconds < sinceUnix.Value) continue;
            if (beforeId != null && row.Id >= beforeId.Value) continue;
            if (newest.Count == capped) newest.Dequeue();
            newest.Enqueue(row);
        }

        return newest.Reverse().ToList();
    }
}
