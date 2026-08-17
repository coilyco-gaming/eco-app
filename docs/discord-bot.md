# The Discord rich-preview bot

`src/eco_discord/` is a separate Pycord gateway worker, not part of the web
process. Guild-only `/eco rich` subcommands (`status`, `world`, `economy`,
`player`, `help`) are dedicated to `#eco-app`: `ECO_DISCORD_INFO_CHANNEL_ID` is
required, and outside that channel they send a concise ephemeral redirect
without fetching data.

## The shared embed contract

One embed factory owns presentation. Handlers supply typed content and never
construct raw Discord embeds. Every embed carries a stable Eco brand color, a
title naming the result, a canonical eco-app HTTPS URL on that title, the Eco
icon, a short description that stays useful when optional fields are absent, at
most 25 fields with the important facts first, a UTC timestamp for the fetch,
and a footer naming the Eco server.

The factory provides `success`, `degraded`, `empty`, and `error` variants. The
degraded variant names unavailable sections without exposing internal handles.

The renderer enforces Discord's limits before delivery: one embed per response,
title 256 characters, description 4,096, field name 256, field value 1,024.

## Lifecycle and architecture

A command defers, fetches through the public preview planes only, renders, and
edits the deferred response. The bot reads no privileged surface and holds no
game credential: everything it shows is already public through eco-app.

Configuration and ownership sit with the worker's own environment rather than
the web process, so the two deploy and fail independently.

**Reliability.** A plane that is slow or down yields the degraded variant
rather than a failed interaction, because a Discord command that times out
reads as a broken bot. Traces and metrics ride the shared OTLP init. Tests
cover each command's happy path, the degraded path, the out-of-channel
redirect, and the renderer's limit enforcement.

Out of scope: writes of any kind, direct messages, and any surface not already
public. See [discord-parity.md](discord-parity.md) for the DiscordLink gap.
