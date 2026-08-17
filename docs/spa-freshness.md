# SPA freshness

How the frontend says how old a number is, without conflating three different
ages.

## Three different ages

- **Browser load age** - when this tab last received data.
- **Backend fetch age** - when the service last called the game server.
- **Source observation age** - when the game server itself sampled the value.

They are never merged into one "last updated". A value can be seconds old in
the browser, minutes old at the backend, and an hour old at the source, and a
reader deciding whether to trust it needs the one that binds.

## The three modes

A plane reports fresh, stale, or unavailable. Stale still renders its last
value with its age, because a stale number a reader can date beats an empty
panel. Unavailable renders the panel's frame with the reason.

## Where the values live

Each plane carries its own timestamps on the payload, so freshness is data
rather than a wrapper. The shared hook reads them and derives the three ages.

## Adding a plane

Return the timestamps on the payload and register the plane with the hook.
Composite planes (`trade`, `shopCheck`, `resolve`) belong to a page that reads
several, and report the oldest of their parts. Parameterised pages pass their
URL key in the hook's `deps`, so a changed parameter refetches rather than
showing the previous item's numbers under the new item's name.

See also: [uses.md](uses.md), [world.md](world.md).
