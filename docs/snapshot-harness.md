# The snapshot dev harness

`src/eco_snapshot/` plus the `snapshot-capture`, `snapshot-push`,
`snapshot-pull`, `snapshot-serve`, and `http-offline` ward verbs (#128).

## Why

Every data surface here reads a live Eco server. Developing against one means
the game has to be up, the tailnet has to be reachable, and the world has to
contain the thing being tested. The harness removes all three.

## The loop

`snapshot-capture` records every upstream source the app consumes, `push` and
`pull` move a capture between machines, and `snapshot-serve` plus
`http-offline` replay it as the upstream so the app runs with no game server.

## What gets captured

The catalog-driven fan-out over series, actions, species, and worldlayer
rasters, plus every replay event through the replay mod's log. A capture is a
whole consistent view rather than a per-endpoint recording, so cross-surface
joins still line up when replayed.

## Replay matching

Requests match a capture by method, path, and the query fields that change the
answer, ignoring the ones that do not. An unmatched request fails loudly rather
than falling through to the network, so an offline run cannot silently become a
live one.

## Conventions

Captures are local-only and never committed. They are named by cycle and
capture time, so a capture is attributable to a world state.

See also: [FEATURES.md](FEATURES.md).
