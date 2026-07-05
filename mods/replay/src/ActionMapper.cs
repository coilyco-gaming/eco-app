using Eco.Gameplay.GameActions;
using Eco.Gameplay.Players;

namespace EcoReplay;

// Flatten a GameAction into the (citizen, action_type, time, body_json)
// columns of the event store. The body is a best-effort JSON snapshot of
// public properties — opaque to the recorder, useful for the viewer.
//
// The body snapshot is bounded in both breadth and depth by BodySerializer,
// which never deep-walks into Eco entities (Users, WorldObjects, ItemStacks,
// inventories) because Newtonsoft.Json on those pulls in serializable graphs
// that are huge and self-referential (issue #28, bug 1).
public static class ActionMapper
{
    public static EventRow? ToRow(GameAction action)
    {
        if (action == null) return null;

        var actionType = action.GetType().Name;
        var citizen = TryGetCitizenName(action);
        var nowUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var gameTime = action.Time;
        var body = BodySerializer.Serialize(action);

        return new EventRow
        {
            UnixTimeSeconds = nowUnix,
            GameTimeSeconds = gameTime,
            ActionType = actionType,
            Citizen = citizen,
            BodyJson = body,
        };
    }

    private static string? TryGetCitizenName(GameAction action)
    {
        // Every GameAction subclass has its own field naming; the most common
        // is `Citizen` of type User. Use reflection so we don't have to know
        // every subclass shape.
        var prop = action.GetType().GetProperty("Citizen");
        if (prop?.GetValue(action) is User user)
            return user.Name;

        var field = action.GetType().GetField("Citizen");
        if (field?.GetValue(action) is User user2)
            return user2.Name;

        return null;
    }
}
