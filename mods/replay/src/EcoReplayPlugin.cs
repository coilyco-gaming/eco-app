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
        status += $", retention: newest {Store.RetentionMaxRows:N0} rows";
        if (Store.DroppedCount > 0) status += $", dropped: {Store.DroppedCount}";
        if (Store.WriteErrorCount > 0) status += $", write errors: {Store.WriteErrorCount}";
        return status;
    }

    public void Initialize(TimedTask timer)
    {
        Instance = this;
        Store.Open();
        ActionUtil.AddListener(this);
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
