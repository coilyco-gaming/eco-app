# eco-store-exporter — C# side

The live store-shelf exporter. DiscordLink reads store shelves in-process to
answer `Trades <item>`; eco-app's server exports only historical trade *events*,
not the current shelf. This mod closes that gap: it walks every live
`StoreComponent` and exposes the current offers over HTTP, so the Python
store-directory, logistics-engine, and watcher siblings move from
history-derived to shelf-accurate. Parent epic:
[eco-app#37](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/37).
Built here: [eco-app#55](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/55).

Two projects share one solution (`eco-store-exporter.sln`):

| Project | Purpose | Runs where |
|---|---|---|
| `src/EcoStoreExporter.csproj` | The real mod. Exposes `GET /api/v1/stores` (every live store's current shelf) from inside the Eco server process by declaring an `[ApiController]` that Eco's ASP.NET Core host picks up via `AddApplicationPart`. | Eco dedicated server, after `dotnet build -c Release` and dropping the resulting DLL into `Server/Mods/<Name>/`. |
| `shell/EcoStoreExporter.Shell.csproj` | Standalone ASP.NET Core harness. Same route, same DTOs, mock data. Lets the Python side iterate against a real C# HTTP server without booting Eco. | `localhost:5101`, launched by `ward exec run-shell-stores` from the repo root. |

DTOs (`src/Dtos.cs`) are shared — the shell project `<Compile Include>`s the
file, so any change to the shape propagates to both. The contract is documented
in [docs/dto.md](docs/dto.md).

## Local harness

```sh
ward exec run-shell-stores   # -> http://localhost:5101/api/v1/stores
```

## Building the real mod

```sh
ward exec build-mod-stores
# -> mods/stores/src/bin/Release/net10.0/EcoStoreExporter.dll
```

Copy the DLL into the Eco server's `Server/Mods/EcoStoreExporter/` directory and
restart the server. Eco's `ModKitPlugin` discovers mod DLLs on boot and
registers their MVC application parts automatically. **Deploy is out of band**:
the DLL lands at the next natural server restart, never as part of building or
testing this mod (loading a new plugin requires a restart, which #55 is
explicitly built to avoid).

## Auth

`/api/v1/stores` sits under Eco's existing admin-token surface, so the same
`X-API-Key` header the other admin routes use guards it. The mod adds no auth of
its own — same as `mods/jobs`.

## Why reflection in `StoreScanner`?

The real mod reads the store/offer/stack/currency members by name, guarded,
rather than through the typed Store API. This is deliberate: the
gaming-eco-investigation case library records a reproducible NRE in Eco's own
trade path from orphaned stores and removed items surviving a save migration, so
the walk assumes any referent can be null and skips-and-continues. Reading by
name also keeps the exporter building across Eco reference-assembly versions
that rename members. A partial shelf is the right answer; a 500 is not. Full
rationale is in the header comment of `src/StoreScanner.cs`.
