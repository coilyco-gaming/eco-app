using System.Reflection;
using System.Runtime.InteropServices;
using Eco.Core.Plugins.Interfaces;
using Eco.Core.Utils;
using Eco.Gameplay.GameActions;
using Eco.Gameplay.Aliases;
using Eco.Gameplay.Property;
using Newtonsoft.Json;

namespace EcoReplay;

// Entry point. Eco's PluginManager scans mod assemblies for classes
// implementing IServerPlugin and instantiates them at server start.
//
// IInitializablePlugin.Initialize is where we hook ActionUtil. By then
// the world has loaded but action traffic hasn't started yet.
// IModKitPlugin is the marker interface Eco's PluginManager scans for to
// auto-register mod plugins (Eco.Server/PluginManager.cs:346). Without it
// the assembly loads but the plugin is never instantiated, never
// initialized, and never receives game actions.
public class EcoReplayPlugin : IModKitPlugin, IInitializablePlugin, IShutdownablePlugin, IGameActionAware
{
    public static EcoReplayPlugin? Instance { get; private set; }

    public EventStore Store { get; } = new EventStore();

    public string GetCategory() => "Mods";
    public string GetStatus() => Store.IsReady
        ? $"recording (total events: {Store.RowCount()})"
        : "not initialized";

    public void Initialize(TimedTask timer)
    {
        Instance = this;
        InstallNativeLibraryResolver();
        Store.Open();
        ActionUtil.AddListener(this);
    }

    // Eco loads mods via AssemblyLoadContext.Default.LoadFromStream, which
    // doesn't add the mod folder to the native-library search path. So when
    // SQLitePCLRaw's static init tries to dlopen libe_sqlite3.so, .NET only
    // looks in Eco's apphost directory (e.g. ~/.net/EcoServer/<hash>/) and
    // fails. Teach .NET to look in this assembly's own directory.
    private static int resolverInstalled;
    private static void InstallNativeLibraryResolver()
    {
        if (Interlocked.Exchange(ref resolverInstalled, 1) == 1) return;

        var modAssembly = typeof(EcoReplayPlugin).Assembly;
        var modDir = Path.GetDirectoryName(modAssembly.Location);
        if (string.IsNullOrEmpty(modDir)) return;

        // Apply the resolver to every assembly that might P/Invoke the
        // bundled native libs. SQLitePCLRaw.provider.e_sqlite3 is the one
        // that DllImport's "e_sqlite3" directly.
        var targets = new[]
        {
            modAssembly,
            typeof(Microsoft.Data.Sqlite.SqliteConnection).Assembly,
            typeof(SQLitePCL.raw).Assembly,
        };

        foreach (var asm in targets.Distinct())
        {
            try
            {
                NativeLibrary.SetDllImportResolver(asm, (name, requesting, search) =>
                {
                    var candidates = new[]
                    {
                        Path.Combine(modDir, $"lib{name}.so"),
                        Path.Combine(modDir, $"{name}.so"),
                        Path.Combine(modDir, name),
                    };
                    foreach (var path in candidates)
                    {
                        if (File.Exists(path) && NativeLibrary.TryLoad(path, out var handle))
                            return handle;
                    }
                    return IntPtr.Zero; // fall through to default resolution
                });
            }
            catch (InvalidOperationException)
            {
                // SetDllImportResolver throws if a resolver is already set
                // for this assembly. Safe to ignore — first install wins.
            }
        }

        // Also probe SQLitePCLRaw.provider.e_sqlite3 specifically. It lives
        // in its own assembly that isn't reachable via a typeof() above
        // without a hard PackageReference (already present), but the public
        // type SQLitePCL.raw is in SQLitePCLRaw.core — its sister provider
        // assembly may be loaded separately.
        var providerAsm = AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(a => a.GetName().Name == "SQLitePCLRaw.provider.e_sqlite3");
        if (providerAsm != null)
        {
            try
            {
                NativeLibrary.SetDllImportResolver(providerAsm, (name, requesting, search) =>
                {
                    var candidates = new[]
                    {
                        Path.Combine(modDir, $"lib{name}.so"),
                        Path.Combine(modDir, $"{name}.so"),
                        Path.Combine(modDir, name),
                    };
                    foreach (var path in candidates)
                        if (File.Exists(path) && NativeLibrary.TryLoad(path, out var handle))
                            return handle;
                    return IntPtr.Zero;
                });
            }
            catch (InvalidOperationException) { }
        }
    }

    public Task ShutdownAsync()
    {
        ActionUtil.RemoveListener(this);
        Store.Close();
        return Task.CompletedTask;
    }

    // IGameActionAware: we never want to influence auth, only observe.
    public LazyResult ShouldOverrideAuth(IAlias? alias, IOwned? property, GameAction? action)
        => LazyResult.FailedNoMessage;

    public void ActionPerformed(GameAction action)
    {
        try
        {
            var row = ActionMapper.ToRow(action);
            if (row != null) Store.Insert(row);
        }
        catch (Exception ex)
        {
            // Never let a recorder bug propagate into the game loop.
            Eco.Shared.Logging.Log.WriteErrorLineLocStr(
                Eco.Shared.Localization.Localizer.DoStr(
                    $"[EcoReplay] failed to record action {action?.GetType().Name}: {ex.Message}"));
        }
    }
}
