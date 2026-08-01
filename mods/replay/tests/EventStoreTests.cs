using Xunit;

namespace EcoReplay.Tests;

public class EventStoreTests
{
    [Fact]
    public void HighVolumeBurst_NeverExceedsTheBoundedWriterQueue()
    {
        var eventPath = TemporaryEventPath();
        var store = new EventStore(eventPath);
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
            DeleteEventFile(eventPath);
        }
    }

    [Fact]
    public void RetentionCap_KeepsOnlyTheNewestRows()
    {
        var eventPath = TemporaryEventPath();
        var store = new EventStore(eventPath, retentionMaxRows: 100);
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
            DeleteEventFile(eventPath);
        }
    }

    [Fact]
    public void AppendQueryAndRestart_PreserveSchemaFiltersAndMonotonicIds()
    {
        var eventPath = TemporaryEventPath();
        var store = new EventStore(eventPath);
        try
        {
            store.Open();
            store.Insert(Row(100, "Craft", "Ava"));
            store.Insert(Row(200, "Vote", "Bo"));
            store.Close();

            store.Open();
            store.Insert(Row(300, "Craft", "Ava"));
            store.Close();
            store.Open();

            var all = store.Query(null, null, limit: 10, sinceUnix: null, beforeId: null);
            Assert.Equal(new long[] { 3, 2, 1 }, all.Select(row => row.Id));
            Assert.Equal(new long[] { 300, 200, 100 }, all.Select(row => row.UnixTimeSeconds));

            var filtered = store.Query("Ava", "Craft", limit: 10, sinceUnix: 150, beforeId: 4);
            Assert.Single(filtered);
            Assert.Equal(3, filtered[0].Id);
            Assert.Equal("{}", filtered[0].BodyJson);
        }
        finally
        {
            store.Close();
            DeleteEventFile(eventPath);
        }
    }

    [Fact]
    public void Reader_SkipsMalformedLinesAndPartialFinalWrite()
    {
        var eventPath = TemporaryEventPath();
        var store = new EventStore(eventPath);
        try
        {
            store.Open();
            store.Insert(Row(100, "Craft", "Ava"));
            store.Close();
            File.AppendAllText(eventPath, "not-json\n{\"id\":999,\"unixTime\":200");

            store.Open();
            Assert.Equal(1, store.RowCount());
            Assert.Single(store.Query(null, null, 10, null, null));

            store.Insert(Row(200, "Vote", "Bo"));
            store.Close();
            store.Open();

            var rows = store.Query(null, null, 10, null, null);
            Assert.Equal(new long[] { 2, 1 }, rows.Select(row => row.Id));
            Assert.Equal(new long[] { 200, 100 }, rows.Select(row => row.UnixTimeSeconds));
        }
        finally
        {
            store.Close();
            DeleteEventFile(eventPath);
        }
    }

    private static EventRow Row(long unixTime, string type, string citizen) => new()
    {
        UnixTimeSeconds = unixTime,
        GameTimeSeconds = (int)unixTime,
        ActionType = type,
        Citizen = citizen,
        BodyJson = "{}",
    };

    private static string TemporaryEventPath()
        => Path.Combine(Path.GetTempPath(), $"eco-replay-{Guid.NewGuid():N}.jsonl");

    private static void DeleteEventFile(string path)
    {
        foreach (var suffix in new[] { "", ".compact.tmp" })
        {
            var candidate = path + suffix;
            if (File.Exists(candidate)) File.Delete(candidate);
        }
    }
}
