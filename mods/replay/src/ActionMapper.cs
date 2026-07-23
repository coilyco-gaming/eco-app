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
        var nowUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var gameTime = action.Time;
        string? citizen;
        string body;

        // A craft completion is the one high-volume action we intentionally do
        // not send through the generic reflection snapshot. ItemCraftedAction
        // fires once for WorkOrder.CompleteIteration, so one row is one output
        // iteration (not the order's requested quantity). Keep its body fixed
        // and scalar-only: this path runs hundreds of thousands of times per
        // cycle and must never walk a station, item, or inventory graph.
        if (action is ItemCraftedAction crafted)
        {
            citizen = crafted.Citizen?.Name;
            body = CraftedIterationBody.Serialize(
                item: crafted.ItemUsed?.Name,
                station: crafted.WorldObjectItem?.Name,
                byproduct: crafted.Byproduct?.Name,
                position: crafted.ActionLocation.ToString());
        }
        else
        {
            citizen = TryGetCitizenName(action);
            body = BodySerializer.Serialize(action);
        }

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
