using System.Collections;
using System.Reflection;
using Eco.Gameplay.Objects;

namespace EcoStoreExporter;

// Walks every live StoreComponent and flattens its shelf into StoreDto/OfferDto.
//
// Why reflection instead of the typed Store API? Two reasons, both grounded in
// how this exact chain breaks:
//
//  1. Dangling references. The gaming-eco-investigation case library records a
//     reproducible NRE inside Eco's own trade path
//     (StoreComponent -> TradeOffer -> Stack.Item, and store.Parent / currency
//     accessors) caused by orphaned stores and items removed by a mod update
//     surviving a save migration. Enumerating live shelves has to assume any
//     referent can be null and skip-and-continue, never throw - one bad offer
//     must not sink the whole export.
//
//  2. API drift. Eco.ReferenceAssemblies member names shift across beta
//     releases. Reading offer/price/stack/currency members by name, guarded,
//     keeps the exporter building and running across versions instead of
//     failing to compile on a renamed property. The StoreComponent TYPE is
//     stable, so we still find it via wo.GetComponent by name.
//
// Everything here swallows exceptions and returns best-effort data. A partial
// shelf is the correct answer; a 500 is not.
public static class StoreScanner
{
    private const BindingFlags Public = BindingFlags.Public | BindingFlags.Instance;

    public static List<StoreDto> Scan()
    {
        var stores = new List<StoreDto>();

        try
        {
            // ForEach is the static, manager-owned iterator - the defensive
            // pattern the telemetry mod uses. No singleton reach, no manual lock.
            WorldObjectManager.ForEach(wo =>
            {
                try
                {
                    var store = FindStoreComponent(wo);
                    if (store is null) return;
                    stores.Add(BuildStore(wo, store));
                }
                catch
                {
                    // Orphaned object or mid-iteration mutation. Skip this store.
                }
            });
        }
        catch
        {
            // WorldObjectManager unready during early init. Return whatever we have.
        }

        return stores;
    }

    // A WorldObject holds its StoreComponent among its components. We match by
    // type name so we never take a compile-time dependency on the type's members.
    private static object? FindStoreComponent(WorldObject wo)
    {
        foreach (var component in EnumerateComponents(wo))
        {
            if (component is not null && component.GetType().Name == "StoreComponent")
            {
                return component;
            }
        }

        return null;
    }

    private static IEnumerable<object> EnumerateComponents(WorldObject wo)
    {
        // WorldObject exposes its components through one of a few accessors
        // across Eco versions. Try each; yield whatever enumerates.
        var raw = GetMember(wo, "Components")
                  ?? Invoke(wo, "GetComponents")
                  ?? Invoke(wo, "GetAllComponents");

        if (raw is IEnumerable seq and not string)
        {
            foreach (var item in seq)
            {
                if (item is not null) yield return item;
            }
        }
    }

    private static StoreDto BuildStore(WorldObject wo, object store)
    {
        var name = AsString(GetMember(wo, "Name", "DisplayName"))
                   ?? AsString(GetMember(store, "Name"))
                   ?? "Unknown Store";

        var owner = AsString(GetMember(store, "Owner", "OwnerName"))
                    ?? AsString(GetMember(GetMember(wo, "Creator", "OwnerUser"), "Name"));

        var currency = AsString(GetMember(store, "CurrencyName"))
                       ?? AsString(GetMember(GetMember(store, "Currency"), "Name", "DisplayName"));

        return new StoreDto(name, owner, currency, ReadLocation(wo), ReadOffers(store));
    }

    private static LocationDto? ReadLocation(WorldObject wo)
    {
        var pos = GetMember(wo, "Position", "Position3i");
        if (pos is null) return null;

        var x = AsInt(GetMember(pos, "X"));
        var y = AsInt(GetMember(pos, "Y"));
        var z = AsInt(GetMember(pos, "Z"));
        if (x is null || y is null || z is null) return null;

        return new LocationDto(x.Value, y.Value, z.Value);
    }

    private static OfferDto[] ReadOffers(object store)
    {
        var offers = new List<OfferDto>();

        var rawOffers = GetMember(store, "AllOffers", "Offers")
                        ?? Invoke(store, "AllOffers");

        if (rawOffers is not (IEnumerable and not string)) return offers.ToArray();

        foreach (var offer in (IEnumerable)rawOffers)
        {
            if (offer is null) continue;
            try
            {
                var built = BuildOffer(offer);
                if (built is not null) offers.Add(built);
            }
            catch
            {
                // A TradeOffer whose Stack.Item was removed by a mod update.
                // Skip it rather than let one dangling item sink the shelf.
            }
        }

        return offers.ToArray();
    }

    private static OfferDto? BuildOffer(object offer)
    {
        // Store slots hold empty offers too; only export the ones with an item.
        var stack = GetMember(offer, "Stack");
        var item = GetMember(stack, "Item") ?? GetMember(offer, "Item");
        if (item is null) return null;

        var itemName = AsString(GetMember(item, "DisplayName", "MarkupName", "Name"))
                       ?? item.GetType().Name;
        var itemTypeName = item.GetType().Name;

        var buying = AsBool(GetMember(offer, "Buying", "IsBuying")) ?? false;
        var price = AsDouble(GetMember(offer, "Price")) ?? 0.0;
        var quantity = AsInt(GetMember(stack, "Quantity"))
                       ?? AsInt(GetMember(offer, "Quantity"))
                       ?? 0;

        return new OfferDto(itemName, itemTypeName, buying, price, quantity);
    }

    // --- reflection primitives, all null- and exception-tolerant ---

    private static object? GetMember(object? target, params string[] names)
    {
        if (target is null) return null;
        var type = target.GetType();

        foreach (var name in names)
        {
            try
            {
                var prop = type.GetProperty(name, Public);
                if (prop is not null && prop.GetIndexParameters().Length == 0)
                {
                    var value = prop.GetValue(target);
                    if (value is not null) return value;
                }

                var field = type.GetField(name, Public);
                if (field is not null)
                {
                    var value = field.GetValue(target);
                    if (value is not null) return value;
                }
            }
            catch
            {
                // Accessor threw (dangling reference). Try the next candidate.
            }
        }

        return null;
    }

    private static object? Invoke(object? target, string name)
    {
        if (target is null) return null;
        try
        {
            var method = target.GetType().GetMethod(name, Public, binder: null, types: Type.EmptyTypes, modifiers: null);
            return method?.Invoke(target, null);
        }
        catch
        {
            return null;
        }
    }

    private static string? AsString(object? value)
    {
        if (value is null) return null;
        var s = value.ToString();
        return string.IsNullOrWhiteSpace(s) ? null : s;
    }

    private static int? AsInt(object? value) =>
        value is null ? null : TryConvert(() => Convert.ToInt32(value));

    private static double? AsDouble(object? value) =>
        value is null ? null : TryConvert(() => Convert.ToDouble(value));

    private static bool? AsBool(object? value) =>
        value is bool b ? b : null;

    private static T? TryConvert<T>(Func<T> convert) where T : struct
    {
        try
        {
            return convert();
        }
        catch
        {
            return null;
        }
    }
}
