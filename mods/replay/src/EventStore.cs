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
// while the game thread writes. One file under Storage/EcoReplay.db so it
// rides Eco's existing backup loop (which snapshots the Storage/ folder).
public class EventStore
{
    private SqliteConnection? conn;
    private readonly object writeLock = new();

    public bool IsReady => conn != null;

    public string DatabasePath { get; private set; } = "Storage/EcoReplay.db";

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
    }

    public void Close()
    {
        conn?.Close();
        conn?.Dispose();
        conn = null;
    }

    public void Insert(EventRow row)
    {
        if (conn == null) return;
        lock (writeLock)
        {
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                INSERT INTO events (unix_time, game_time, action_type, citizen, body_json)
                VALUES ($u, $g, $t, $c, $b);
                """;
            cmd.Parameters.AddWithValue("$u", row.UnixTimeSeconds);
            cmd.Parameters.AddWithValue("$g", row.GameTimeSeconds);
            cmd.Parameters.AddWithValue("$t", row.ActionType);
            cmd.Parameters.AddWithValue("$c", (object?)row.Citizen ?? DBNull.Value);
            cmd.Parameters.AddWithValue("$b", row.BodyJson);
            cmd.ExecuteNonQuery();
        }
    }

    public long RowCount()
    {
        if (conn == null) return 0;
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM events";
        return (long)(cmd.ExecuteScalar() ?? 0L);
    }

    public IEnumerable<EventRow> Query(string? citizen, string? actionType, int limit, long? sinceUnix)
    {
        if (conn == null) yield break;

        using var cmd = conn.CreateCommand();
        var sql = "SELECT id, unix_time, game_time, action_type, citizen, body_json FROM events WHERE 1=1";
        if (citizen != null) { sql += " AND citizen = $c"; cmd.Parameters.AddWithValue("$c", citizen); }
        if (actionType != null) { sql += " AND action_type = $t"; cmd.Parameters.AddWithValue("$t", actionType); }
        if (sinceUnix != null) { sql += " AND unix_time >= $s"; cmd.Parameters.AddWithValue("$s", sinceUnix.Value); }
        sql += " ORDER BY id DESC LIMIT $l";
        cmd.Parameters.AddWithValue("$l", Math.Clamp(limit, 1, 1000));
        cmd.CommandText = sql;

        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            yield return new EventRow
            {
                Id = reader.GetInt64(0),
                UnixTimeSeconds = reader.GetInt64(1),
                GameTimeSeconds = reader.GetInt32(2),
                ActionType = reader.GetString(3),
                Citizen = reader.IsDBNull(4) ? null : reader.GetString(4),
                BodyJson = reader.GetString(5),
            };
        }
    }
}
