# eco-jobs-tracker — C# side

Two projects share one solution (`eco-jobs-tracker.sln`):

* **`src/EcoJobsTracker.csproj`** - The real mod. It exposes `GET /api/v1/skills` (learned specialties) and `GET /api/v1/citizens` (numeric user id to name, for the crafting atlas's citizen join, [eco-app#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)) from inside the Eco server process by declaring `[ApiController]`s that Eco's ASP.NET Core host picks up via `AddApplicationPart`. The Eco dedicated server runs the compiled DLL from `Server/Mods/<Name>/`.
* **`shell/EcoJobsTracker.Shell.csproj`** - Standalone ASP.NET mock with the same routes, DTOs, and mock data. It runs on `localhost:5100` through `just run-shell-jobs`, so the Python tracker can iterate without booting Eco.

DTOs (`src/Dtos.cs`) are shared — the shell project `<Compile Include>`s the file, so any change to the shape propagates to both.

## Local harness

```sh
just run-shell-jobs
```

## Building the real mod

```sh
just build-mod-jobs
```

The output is `mods/jobs/src/bin/Release/net10.0/EcoJobsTracker.dll`.

Copy the DLL into the Eco server's `Server/Mods/EcoJobsTracker/` directory and restart the server. Eco's `ModKitPlugin` discovers mod DLLs on boot and registers their MVC application parts automatically.

## Why not UserCode?

Eco does auto-compile `.cs` files dropped into `Server/Mods/UserCode/`, but pre-compiling via `dotnet build` gives us:

- Real IDE support (IntelliSense, nullable annotations, refactors).
- A standalone build that Eco doesn't have to recompile on every server restart.
- Shared type definitions with the shell harness.

Both approaches are supported by Eco; we're choosing the compiled path.
