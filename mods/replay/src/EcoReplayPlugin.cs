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
    public string GetStatus()
    {
        if (!Store.IsReady) return "not initialized";
        var status = $"recording (total events: {Store.RowCount()})";
        if (Store.DroppedCount > 0) status += $", dropped: {Store.DroppedCount}";
        if (Store.WriteErrorCount > 0) status += $", write errors: {Store.WriteErrorCount}";
        return status;
    }

    public void Initialize(TimedTask timer)
    {
        Instance = this;
        InstallNativeLibraryResolver();
        Store.Open();
        ActionUtil.AddListener(this);
    }

    // Eco loads mods via AssemblyLoadContext.Default.LoadFromStream, which
    // doesn't add the mod folder to the native-library search path. On top of
    // that the Eco server ships as a .NET single-file bundle, so the default
    // native resolver searches only the bundle extraction dir
    // (~/.net/EcoServer/<hash>/), never the mod folder or its
    // runtimes/linux-x64/native/ path. When SQLitePCLRaw's static init tries to
    // dlopen libe_sqlite3.so it fails (issue #71). Teach .NET to look in this
    // assembly's own directory instead.
    //
    // The DllImport("e_sqlite3") that triggers the load lives in the
    // SQLitePCLRaw.provider.e_sqlite3 assembly, and a DllImport resolver only
    // fires for P/Invokes originating from the assembly it was registered on.
    // So the resolver MUST be registered on the provider assembly, and it must
    // be registered before Batteries_V2.Init() runs the first P/Invoke. We
    // reach the provider assembly through a hard typeof() reference
    // (SQLite3Provider_e_sqlite3), which both forces the assembly to load now
    // and gives us the exact Assembly to target — a runtime
    // AppDomain.GetAssemblies() scan would come up empty here because the
    // provider assembly isn't loaded yet at plugin-init time.
    private static int resolverInstalled;
    private static void InstallNativeLibraryResolver()
    {
        if (Interlocked.Exchange(ref resolverInstalled, 1) == 1) return;

        var modAssembly = typeof(EcoReplayPlugin).Assembly;
        var modDir = Path.GetDirectoryName(modAssembly.Location);
        if (string.IsNullOrEmpty(modDir)) return;

        DllImportResolver resolver = (name, requesting, search) =>
        {
            if (name != "e_sqlite3") return IntPtr.Zero; // fall through to default
            // Cover both staging layouts: the .so flattened next to the DLL,
            // and the canonical NuGet runtimes/<rid>/native/ subpath.
            var nativeDir = Path.Combine(modDir, "runtimes", "linux-x64", "native");
            var candidates = new[]
            {
                Path.Combine(modDir, $"lib{name}.so"),
                Path.Combine(modDir, $"{name}.so"),
                Path.Combine(modDir, name),
                Path.Combine(nativeDir, $"lib{name}.so"),
                Path.Combine(nativeDir, $"{name}.so"),
                Path.Combine(nativeDir, name),
            };
            foreach (var path in candidates)
            {
                if (File.Exists(path) && NativeLibrary.TryLoad(path, out var handle))
                    return handle;
            }
            return IntPtr.Zero; // fall through to default resolution
        };

        // Register on every assembly that might P/Invoke the bundled native lib.
        // The provider assembly (reached via the hard SQLite3Provider_e_sqlite3
        // typeof) is the one that actually declares DllImport("e_sqlite3") and
        // is therefore load-bearing; the others are belt-and-suspenders.
        var targets = new[]
        {
            typeof(SQLitePCL.SQLite3Provider_e_sqlite3).Assembly,
            typeof(Microsoft.Data.Sqlite.SqliteConnection).Assembly,
            typeof(SQLitePCL.raw).Assembly,
            modAssembly,
        };

        foreach (var asm in targets.Distinct())
        {
            try
            {
                NativeLibrary.SetDllImportResolver(asm, resolver);
            }
            catch (InvalidOperationException)
            {
                // SetDllImportResolver throws if a resolver is already set
                // for this assembly. Safe to ignore — first install wins.
            }
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
