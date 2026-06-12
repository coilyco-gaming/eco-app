using Eco.Gameplay.GameActions;
using Eco.Gameplay.Players;
using Newtonsoft.Json;

namespace EcoReplay;

// Flatten a GameAction into the (citizen, action_type, time, body_json)
// columns of the event store. The body is a best-effort JSON snapshot
// of public properties — opaque to the recorder, useful for the viewer.
//
// We never deep-walk into Eco entities (Users, WorldObjects, ItemStacks)
// because Newtonsoft.Json on those will pull in serializable graphs
// that are huge and self-referential. Just record their display names
// and ids and stop.
public static class ActionMapper
{
    private static readonly JsonSerializerSettings BodySettings = new()
    {
        ReferenceLoopHandling = ReferenceLoopHandling.Ignore,
        NullValueHandling = NullValueHandling.Ignore,
        MaxDepth = 2,
        Error = (sender, args) => args.ErrorContext.Handled = true,
        ContractResolver = new ShallowResolver(),
    };

    public static EventRow? ToRow(GameAction action)
    {
        if (action == null) return null;

        var actionType = action.GetType().Name;
        var citizen = TryGetCitizenName(action);
        var nowUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var gameTime = action.Time;

        string body;
        try
        {
            body = JsonConvert.SerializeObject(action, BodySettings);
        }
        catch
        {
            body = "{}";
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

// Newtonsoft contract resolver that prunes properties Eco's serializer
// pipeline would otherwise traverse infinitely. We only want a flat
// snapshot for human-readable inspection.
internal class ShallowResolver : Newtonsoft.Json.Serialization.DefaultContractResolver
{
    private static readonly HashSet<string> SkipTypes = new(StringComparer.Ordinal)
    {
        "Eco.Gameplay.Players.User",
        "Eco.Gameplay.Items.ItemStack",
        "Eco.Gameplay.Objects.WorldObject",
        "Eco.Gameplay.Property.Deed",
    };

    protected override Newtonsoft.Json.Serialization.JsonProperty CreateProperty(
        System.Reflection.MemberInfo member, MemberSerialization memberSerialization)
    {
        var prop = base.CreateProperty(member, memberSerialization);
        if (prop.PropertyType != null && SkipTypes.Contains(prop.PropertyType.FullName ?? ""))
        {
            // Replace User/ItemStack/etc. with their string representation.
            prop.ValueProvider = new NameOnlyValueProvider(prop.ValueProvider!);
        }
        return prop;
    }
}

internal class NameOnlyValueProvider : Newtonsoft.Json.Serialization.IValueProvider
{
    private readonly Newtonsoft.Json.Serialization.IValueProvider inner;
    public NameOnlyValueProvider(Newtonsoft.Json.Serialization.IValueProvider inner) { this.inner = inner; }
    public object? GetValue(object target)
    {
        var v = inner.GetValue(target);
        if (v == null) return null;
        // Best-effort string label.
        var nameProp = v.GetType().GetProperty("Name");
        if (nameProp?.GetValue(v) is string s) return s;
        return v.ToString();
    }
    public void SetValue(object target, object? value) => inner.SetValue(target, value!);
}
