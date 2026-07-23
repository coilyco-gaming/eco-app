using System.Threading.Channels;
using Microsoft.Data.Sqlite;

namespace EcoReplay;

public record EventRow
{
    public long Id { get; init; }
    public long UnixTimeSeconds { get; init; }
    public int GameTimeSeconds { get; init; }
    public string ActionType { get; init; } = "";
    public string? Citizen { get; init; }
    public string BodyJson { get; init; } = "{}";
}

// SQLite-backed append-only event log. WAL mode for cheap concurrent reads
// while the writer appends. One file under Storage/EcoReplay.db so it rides
// Eco's existing backup loop (which snapshots the Storage/ folder).
//
// Writes never happen on the game thread. Insert() hands the row to a bounded
// channel and returns immediately; a single background Task drains the channel
// and batches inserts in transactions. This decouples the game tick from disk
// latency and serializes all connection access through one writer instead of
// blocking every action on a shared mutex + ExecuteNonQuery (issue #28, bug 2).
public class EventStore
{
    private SqliteConnection? conn;

    // Guards every use of `conn` — the background writer, the reads served from
    // the ASP.NET request thread, and teardown. SqliteConnection is not safe
    // for concurrent commands, so all access is serialized here.
    private readonly object connLock = new();
    private readonly object queueCountLock = new();

    // Bounded hand-off between the game thread (Insert) and the background
    // writer. Under sustained overload we shed the newest un-written row
    // rather than stall gameplay or grow memory. Keeping older rows preserves
    // chronology for the historical log and makes the overload count exact.
    private Channel<EventRow>? channel;
    private Task? drainTask;
    private CancellationTokenSource? cts;
    private long droppedOnClosed;
    private long writeErrors;
    private int queuedRows;
    private int peakQueuedRows;
    private int rowsSincePrune;

    public const int ChannelCapacity = 4096;
    public const int DefaultRetentionMaxRows = 2_000_000;
    private const int BatchSize = 100;
    private const int BatchLingerMs = 250;
    private readonly int retentionMaxRows;
    private readonly int retentionPruneEveryRows;

    public bool IsReady => conn != null;

    public string DatabasePath { get; }

    public EventStore(
        string databasePath = "Storage/EcoReplay.db",
        int retentionMaxRows = DefaultRetentionMaxRows)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(databasePath);
        ArgumentOutOfRangeException.ThrowIfLessThan(retentionMaxRows, 1);
        DatabasePath = databasePath;
        this.retentionMaxRows = retentionMaxRows;
        retentionPruneEveryRows = Math.Min(retentionMaxRows, 10_000);
    }

    // Rows dropped because the queue was full or closing, plus batches that
    // failed to flush. Surfaced in the plugin status for observability.
    public long DroppedCount => Interlocked.Read(ref droppedOnClosed);
    public long WriteErrorCount => Interlocked.Read(ref writeErrors);
    public int PeakQueuedRows => Volatile.Read(ref peakQueuedRows);
    public int RetentionMaxRows => retentionMaxRows;

    public void Open()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(DatabasePath) ?? ".");
        conn = new SqliteConnection($"Data Source={DatabasePath};");
        conn.Open();

        using (var cmd = conn.CreateCommand())
        {
            cmd.CommandText = """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unix_time INTEGER NOT NULL,
                    game_time INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    citizen TEXT,
                    body_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_unix_time ON events(unix_time);
                CREATE INDEX IF NOT EXISTS idx_events_action_type ON events(action_type);
                CREATE INDEX IF NOT EXISTS idx_events_citizen ON events(citizen);
                """;
            cmd.ExecuteNonQuery();
        }

        channel = Channel.CreateBounded<EventRow>(new BoundedChannelOptions(ChannelCapacity)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = true,
            SingleWriter = false,
        });
        cts = new CancellationTokenSource();
        drainTask = Task.Run(() => DrainLoopAsync(cts.Token));
    }

    public void Close()
    {
        // Stop accepting new rows and let the writer flush what's already queued;
        // TryComplete lets the drain loop's WaitToReadAsync return false cleanly
        // once the channel empties, so no rows are lost on a normal shutdown.
        channel?.Writer.TryComplete();
        try
        {
            drainTask?.Wait(TimeSpan.FromSeconds(5));
        }
        catch
        {
            // Best-effort flush on shutdown; a stuck writer must not hang exit.
        }
        cts?.Cancel();

        lock (connLock)
        {
            // The last batch can be smaller than the normal prune interval.
            // Enforce the row cap on every clean shutdown as well.
            PruneRetainedRows();
            conn?.Close();
            conn?.Dispose();
            conn = null;
        }

        cts?.Dispose();
        cts = null;
        channel = null;
        drainTask = null;
    }

    // Non-blocking enqueue from the game thread. Never touches disk, never takes
    // the connection lock: build row, hand off, return.
    public void Insert(EventRow row)
    {
        var writer = channel?.Writer;
        if (writer == null) return;

        // TryWrite against a Wait-mode bounded channel is non-blocking: it
        // fails when the queue is full, letting the game tick continue.
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
                while (batch.Count < BatchSize && TryRead(reader, out var row))
                    batch.Add(row);

                // Linger briefly to coalesce a burst into one transaction, but
                // never longer than BatchLingerMs and never past BatchSize.
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
                        // Linger elapsed or the store is shutting down.
                    }
                }

                if (batch.Count > 0) TryFlushBatch(batch);
            }
        }
        catch (OperationCanceledException)
        {
            // Hard stop; fall through to a final drain of whatever remains.
        }

        // Final drain: flush anything left after completion or cancellation.
        batch.Clear();
        while (TryRead(reader, out var row))
        {
            batch.Add(row);
            if (batch.Count >= BatchSize)
            {
                TryFlushBatch(batch);
                batch.Clear();
            }
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
            // One bad batch must not kill the writer and stop all recording.
            Interlocked.Increment(ref writeErrors);
        }
    }

    private void FlushBatch(List<EventRow> batch)
    {
        lock (connLock)
        {
            if (conn == null) return;

            using var tx = conn.BeginTransaction();
            using var cmd = conn.CreateCommand();
            cmd.Transaction = tx;
            cmd.CommandText = """
                INSERT INTO events (unix_time, game_time, action_type, citizen, body_json)
                VALUES ($u, $g, $t, $c, $b);
                """;

            // Reuse one parameter set across the whole batch.
            var pu = cmd.CreateParameter(); pu.ParameterName = "$u"; cmd.Parameters.Add(pu);
            var pg = cmd.CreateParameter(); pg.ParameterName = "$g"; cmd.Parameters.Add(pg);
            var pt = cmd.CreateParameter(); pt.ParameterName = "$t"; cmd.Parameters.Add(pt);
            var pc = cmd.CreateParameter(); pc.ParameterName = "$c"; cmd.Parameters.Add(pc);
            var pb = cmd.CreateParameter(); pb.ParameterName = "$b"; cmd.Parameters.Add(pb);

            foreach (var row in batch)
            {
                pu.Value = row.UnixTimeSeconds;
                pg.Value = row.GameTimeSeconds;
                pt.Value = row.ActionType;
                pc.Value = (object?)row.Citizen ?? DBNull.Value;
                pb.Value = row.BodyJson;
                cmd.ExecuteNonQuery();
            }

            tx.Commit();

            rowsSincePrune += batch.Count;
            if (rowsSincePrune >= retentionPruneEveryRows)
            {
                PruneRetainedRows();
                rowsSincePrune = 0;
            }
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
            if (Interlocked.CompareExchange(ref peakQueuedRows, queued, peakQueuedRows) < queued)
                return;
        }
    }

    private void PruneRetainedRows()
    {
        if (conn == null) return;

        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            DELETE FROM events
            WHERE id < COALESCE(
                (SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET $keep),
                0
            );
            """;
        cmd.Parameters.AddWithValue("$keep", retentionMaxRows - 1);
        cmd.ExecuteNonQuery();
    }

    public long RowCount()
    {
        lock (connLock)
        {
            if (conn == null) return 0;
            using var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT COUNT(*) FROM events";
            return (long)(cmd.ExecuteScalar() ?? 0L);
        }
    }

    public IReadOnlyList<EventRow> Query(
        string? citizen, string? actionType, int limit, long? sinceUnix, long? beforeId)
    {
        var results = new List<EventRow>();

        lock (connLock)
        {
            if (conn == null) return results;

            using var cmd = conn.CreateCommand();
            var sql = "SELECT id, unix_time, game_time, action_type, citizen, body_json FROM events WHERE 1=1";
            if (citizen != null) { sql += " AND citizen = $c"; cmd.Parameters.AddWithValue("$c", citizen); }
            if (actionType != null) { sql += " AND action_type = $t"; cmd.Parameters.AddWithValue("$t", actionType); }
            if (sinceUnix != null) { sql += " AND unix_time >= $s"; cmd.Parameters.AddWithValue("$s", sinceUnix.Value); }
            if (beforeId != null) { sql += " AND id < $b"; cmd.Parameters.AddWithValue("$b", beforeId.Value); }
            sql += " ORDER BY id DESC LIMIT $l";
            cmd.Parameters.AddWithValue("$l", Math.Clamp(limit, 1, 1000));
            cmd.CommandText = sql;

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                results.Add(new EventRow
                {
                    Id = reader.GetInt64(0),
                    UnixTimeSeconds = reader.GetInt64(1),
                    GameTimeSeconds = reader.GetInt32(2),
                    ActionType = reader.GetString(3),
                    Citizen = reader.IsDBNull(4) ? null : reader.GetString(4),
                    BodyJson = reader.GetString(5),
                });
            }
        }

        return results;
    }
}
