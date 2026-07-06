using System.Collections;
using System.Reflection;

namespace EcoStoreExporter;

// Shared, null- and exception-tolerant reflection primitives for the live
// exporters in this mod (StoreScanner, CurrencyHoldingsScanner). Both walk live
// Eco game state that is not clean: the gaming-eco-investigation case library
// records reproducible NREs in Eco's own trade/economy paths from orphaned
// objects and items removed by a mod update surviving a save migration. So the
// walks read members by name, guarded, and skip-and-continue rather than throw -
// a partial answer is correct, a 500 is not. Reading by name also keeps the
// exporters building across Eco.ReferenceAssemblies versions that rename or move
// members. See the header of each scanner for the per-surface rationale.
public static class Reflect
{
    public const BindingFlags Public = BindingFlags.Public | BindingFlags.Instance;
    // FlattenHierarchy so inherited statics resolve too - Eco managers reach their
    // instance through a `Singleton<T>.Obj` static declared on the base class.
    private const BindingFlags PublicStatic = BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy;

    // First readable property/field among `names` on an instance. Null when the
    // target is null, none exist, or every accessor threw (dangling reference).
    public static object? GetMember(object? target, params string[] names)
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

    // First readable static property/field among `names` on a type. The economy
    // walk reaches manager entry points (CurrencyManager.Currencies, etc.) this
    // way without a compile-time dependency on the drifting member.
    public static object? GetStaticMember(Type? type, params string[] names)
    {
        if (type is null) return null;

        foreach (var name in names)
        {
            try
            {
                var prop = type.GetProperty(name, PublicStatic);
                if (prop is not null && prop.GetIndexParameters().Length == 0)
                {
                    var value = prop.GetValue(null);
                    if (value is not null) return value;
                }

                var field = type.GetField(name, PublicStatic);
                if (field is not null)
                {
                    var value = field.GetValue(null);
                    if (value is not null) return value;
                }
            }
            catch
            {
                // Static accessor threw (manager unready). Try the next candidate.
            }
        }

        return null;
    }

    // Invoke a parameterless instance method by name. Null on any failure.
    public static object? Invoke(object? target, string name)
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

    // Resolve a type by full name across every loaded assembly. Used to reach
    // the Eco economy types (Currency, BankAccount, their managers) without a
    // compile-time reference, so the mod compiles even if a type moves. Returns
    // the first match among `fullNames`, or null if none is loaded.
    public static Type? FindType(params string[] fullNames)
    {
        var assemblies = AppDomain.CurrentDomain.GetAssemblies();
        foreach (var fullName in fullNames)
        {
            foreach (var asm in assemblies)
            {
                try
                {
                    var t = asm.GetType(fullName, throwOnError: false);
                    if (t is not null) return t;
                }
                catch
                {
                    // A reflection-only or dynamic assembly can throw. Skip it.
                }
            }
        }

        return null;
    }

    // Invoke a static, zero-argument generic method (e.g. Registrars.Get<T>())
    // closed over `typeArg`. Used as one fallback for enumerating bank accounts.
    // Null on any failure.
    public static object? InvokeStaticGeneric(Type? declaring, Type? typeArg, params string[] methodNames)
    {
        if (declaring is null || typeArg is null) return null;
        try
        {
            foreach (var name in methodNames)
            {
                foreach (var method in declaring.GetMethods(PublicStatic))
                {
                    if (method.Name != name) continue;
                    if (!method.IsGenericMethodDefinition) continue;
                    if (method.GetGenericArguments().Length != 1) continue;
                    if (method.GetParameters().Length != 0) continue;
                    try
                    {
                        return method.MakeGenericMethod(typeArg).Invoke(null, null);
                    }
                    catch
                    {
                        // Wrong overload / constraint mismatch. Keep looking.
                    }
                }
            }
        }
        catch
        {
            // Reflection over the type failed. Give up on this strategy.
        }

        return null;
    }

    // Enumerate an object as a non-string IEnumerable, yielding non-null items.
    // Anything that is not enumerable yields nothing.
    public static IEnumerable<object> AsSequence(object? value)
    {
        if (value is IEnumerable seq and not string)
        {
            foreach (var item in seq)
            {
                if (item is not null) yield return item;
            }
        }
    }

    public static string? AsString(object? value)
    {
        if (value is null) return null;
        var s = value.ToString();
        return string.IsNullOrWhiteSpace(s) ? null : s;
    }

    public static int? AsInt(object? value) =>
        value is null ? null : TryConvert(() => Convert.ToInt32(value));

    public static double? AsDouble(object? value) =>
        value is null ? null : TryConvert(() => Convert.ToDouble(value));

    public static bool? AsBool(object? value) =>
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
