using Xunit;

namespace EcoReplay.Tests;

public class EventStoreTests
{
    [Fact]
    public void HighVolumeBurst_NeverExceedsTheBoundedWriterQueue()
    {
        var databasePath = TemporaryDatabasePath();
        var store = new EventStore(databasePath);
        try
        {
            store.Open();
            var row = new EventRow
            {
                UnixTimeSeconds = 1,
                GameTimeSeconds = 2,
                ActionType = "ItemCraftedAction",
                Citizen = "settler",
                BodyJson = CraftedIterationBody.Serialize("StumpLatrineItem", "CarpentryTableItem", null, "(0, 0, 0)"),
            };

            // Representative of a busy cycle's craft stream. Insert is
            // deliberately non-blocking; the bounded writer may shed rows but
            // it cannot retain more than ChannelCapacity in process memory.
            for (var i = 0; i < 100_000; i++) store.Insert(row);

            Assert.InRange(store.PeakQueuedRows, 1, EventStore.ChannelCapacity);
        }
        finally
        {
            store.Close();
            DeleteDatabase(databasePath);
        }
    }

    [Fact]
    public void RetentionCap_KeepsOnlyTheNewestRows()
    {
        var databasePath = TemporaryDatabasePath();
        var store = new EventStore(databasePath, retentionMaxRows: 100);
        try
        {
            store.Open();
            for (var i = 0; i < 250; i++)
            {
                store.Insert(new EventRow
                {
                    UnixTimeSeconds = i,
                    GameTimeSeconds = i,
                    ActionType = "ItemCraftedAction",
                    BodyJson = "{}",
                });
            }
            store.Close();
            store.Open();

            var rows = store.Query(null, null, limit: 1000, sinceUnix: null, beforeId: null);
            Assert.InRange(rows.Count, 1, 100);
            Assert.Equal(249, rows[0].UnixTimeSeconds);
        }
        finally
        {
            store.Close();
            DeleteDatabase(databasePath);
        }
    }

    private static string TemporaryDatabasePath()
        => Path.Combine(Path.GetTempPath(), $"eco-replay-{Guid.NewGuid():N}.db");

    private static void DeleteDatabase(string path)
    {
        foreach (var suffix in new[] { "", "-wal", "-shm" })
        {
            var candidate = path + suffix;
            if (File.Exists(candidate)) File.Delete(candidate);
        }
    }
}
