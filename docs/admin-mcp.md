# The privileged admin MCP

`src/eco_mcp_app/admin/` is a second, inside-out MCP, distinct from the public
server and feature-flagged off in the ordinary app. Its fourteen tools all use
the `admin_*` namespace and are fixed read-only reads plus one enum-only RCON
tool whose commands are all observational.

## Capability groups

- **Save and world** - `admin_save_status`, `admin_backup_list`.
- **Configs** - `admin_config_get`, `admin_config_diff`.
- **Chronicler** - `admin_events_recent`.
- **Logs** - `admin_log_tail`, `admin_log_grep`, over a fixed log set.
- **Mods** - `admin_mods_installed`, inventorying a fixed `Mods/` path.
- **Runtime** - `admin_live_status`, `admin_service_health`, reading
  node-local runtime state.
- **RCON** - `admin_rcon_query` maps one caller enum to one server-owned
  command. Twelve commands, all observational.

## The RCON enum

The caller picks from an enum, never a string. That is the whole boundary: a
free-text RCON tool is a remote shell, and an enum of twelve observational
commands is not. Adding a command is a code change and a review, not a call.

## Disclosure and filesystem boundary

Tools state their disclosure level, and the privileged surface never widens the
public one. Paths are fixed rather than caller-supplied, so no tool takes a
path, a glob, or a traversal. Input is validated before it reaches the
filesystem or the game server.

## Runtime configuration

The surface is present only when `ECO_ADMIN_ENABLED` is set, mounted at
`/admin/*`, and absent from the ordinary app entirely. The deploy that enables
it owns the authentication in front of it.

See also: [dual-route-inventory.md](dual-route-inventory.md), which classifies
these as excluded from the public registry.
