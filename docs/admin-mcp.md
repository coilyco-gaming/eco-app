# Privileged Eco admin MCP

The `/admin` MCP is the inside-out companion to the public Eco MCP. The public
surface reads exported HTTP data. The admin surface runs beside the Eco host
and combines fixed read-only disk mounts, node-local `/info`, and a deliberately
small RCON query enum.

The surface is feature-flagged with `ECO_ADMIN_ENABLED`. The ordinary public app
deployment leaves that flag off. A separate node-pinned deployment owns the
privileged mount and network boundary.

## Capability groups

* **Save and world** - `eco_save_status`, `eco_backup_list`, and
  `eco_world_meta` read the fixed save, backup, and world-generator locations.
* **Configs** - `eco_config_get`, `eco_config_diff`, and `eco_mod_configs` read
  fixed enums covering core Eco configs and the DiscordLink, MightyMoose,
  NidToolbox, and StrangeWorlds config families.
* **Chronicler** - `eco_events_recent` and `eco_player_activity` stream the fixed
  append-only `Storage/EcoReplay.jsonl` store. Reads retain only their bounded
  newest-event window in memory and skip malformed or partial rows. The legacy
  `Storage/EcoReplay.db` remains an untouched historical archive and is not
  silently imported.
* **Logs** - `eco_log_tail` and `eco_log_grep` select a fixed subsystem enum.
  Search is a bounded case-insensitive literal. The caller cannot supply a
  path or regex.
* **Mods** - `eco_mods_installed` inventories fixed `Mods/` and
  `Mods/UserCode/` roots, reads bounded manifest versions, and reports
  configured mod names that are not installed.
* **Runtime** - `eco_live_status` and `eco_service_health` read the fixed
  node-local `/info` route with timeout and response-size budgets.
  `eco_service_health` reports reachability. It does not run `systemctl`, enter
  a workload, or need a host root mount.
* **RCON** - `eco_rcon_query` maps one caller enum to one server-owned command.
  There is no free-form command argument.

## RCON v1 enum

The command core is intentionally limited to twelve read-only observations:

* `online_players` - `manage players`
* `meteor_status` - `meteor status`
* `world_time` - `time now`
* `climate_status` - `climate status`
* `sea_level` - `sim sealevel`
* `population_changes` - `sim showpopulationchanges`
* `active_elections` - `civics elections`
* `government` - `civics showgovernment`
* `civics_tick` - `civics showtick`
* `currencies` - `money currencies`
* `weather_status` - `weather status`
* `initial_spawn_positions` - `initialspawn list`

Eco exposes both read and mutation commands through the same RCON protocol. The
enum is therefore the authorization boundary. The client serializes requests
because Eco supports one active RCON client, bounds packet and response sizes,
and audits the query name, outcome, and latency without logging credentials or
response bodies.

`online_players`, `active_elections`, and `government` are operator-only because
their unstructured output can identify people. The other nine queries may use
the public redaction level.

## Disclosure levels

Every tool defaults to `operator`.

* `public` hashes names in structured results and strips secret-valued fields.
  Unstructured logs are denied because reliable name redaction is not possible.
* `operator` shows names and strips structured secrets plus secret-looking
  assignments in log and RCON text.
* `raw` is default-deny. The server refuses it unless
  `ECO_ADMIN_ALLOW_RAW` is explicitly set. The deploy contract leaves this
  variable unset.

## Filesystem and input boundary

The deployment mounts only `Storage`, `Configs`, `Logs`, and `Mods`, all
read-only beneath `ECO_STATE_DIR`. The code owns every relative path and checks
that resolution remains under that root, including through symlinks.

Caller-controlled values are limited to fixed enums, bounded counts, the
bounded literal log search string, and the disclosure level. The surface has no
arbitrary path, save edit, mod edit, workload execution, free-form RCON, or
mutating RCON capability.

## Runtime configuration

* `ECO_STATE_DIR` - root containing the four named mounts.
* `ECO_ADMIN_BASE_URL` - node-local Eco HTTP base, default
  `http://127.0.0.1:3001`.
* `ECO_RCON_HOST` and `ECO_RCON_PORT` - fixed node-local RCON endpoint,
  defaulting to `127.0.0.1:3002`.
* `ECO_RCON_PASSWORD` - required RCON credential, supplied by the deployment
  secret boundary.
* `ECO_ADMIN_HTTP_TIMEOUT_SECONDS` and `ECO_RCON_TIMEOUT_SECONDS` - bounded
  optional timeouts.
* `ECO_ADMIN_ALLOW_RAW` - emergency disclosure opt-in. It is absent from the
  deployment.

Live rollout, secret provisioning, and the first command-path smoke remain
operator work. The first smoke must validate each exact command against the
running Eco release because Eco's published command inventory can lag a beta
server.
