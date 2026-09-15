#!/usr/bin/env python3
"""Watch an Eco server's player list and report whether one join actually held.

The assertion for "a client joined and did not crash" does not belong on the
client. A Unity process that dies mid-join reports nothing, and its own log is
the first thing the crash takes with it. The server always knows, so this polls
`/info` and watches a single player name.

Appearing once is not the answer. A client that loads the world and dies ten
seconds later appears and then vanishes, so a name has to appear *and stay* for
a hold window before this reports success.

This deliberately does not call `server.fetch_eco_info`, which memoizes `/info`
for 30s so a tab-reloader cannot fan out onto a small community server. A poller
wants the opposite. The URL handling is still shared, because that is the part
that must not drift.

teable:coilyco-gaming/eco-mods#7750
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from eco_mcp_app.server import normalize_server_url

# The resolved target can be the SSM-sourced tailnet FQDN, which
# scripts/resolve-eco-target.sh deliberately keeps out of terminal output. The
# port and path are the parts worth seeing, so only the host is masked.
_PUBLIC_HOSTS = frozenset({"localhost", "127.0.0.1", "eco.coilysiren.me", "kai-server.local"})


def display_url(url: str, reveal: bool = False) -> str:
    if reveal:
        return url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host in _PUBLIC_HOSTS:
        return url
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse((parsed.scheme, f"<host>{port}", parsed.path, "", "", ""))


class Verdict(StrEnum):
    JOINED = "joined"
    NEVER_APPEARED = "never-appeared"
    DROPPED = "dropped"
    ALREADY_ONLINE = "already-online"
    UNREACHABLE = "unreachable"


EXIT_CODES: dict[Verdict, int] = {
    Verdict.JOINED: 0,
    Verdict.NEVER_APPEARED: 1,
    Verdict.UNREACHABLE: 2,
    Verdict.DROPPED: 3,
    Verdict.ALREADY_ONLINE: 4,
}

HEADLINES: dict[Verdict, str] = {
    Verdict.JOINED: "joined and held",
    Verdict.NEVER_APPEARED: "never appeared",
    Verdict.DROPPED: "appeared, then dropped",
    Verdict.ALREADY_ONLINE: "already online before the watch started",
    Verdict.UNREACHABLE: "server did not answer",
}


@dataclass(frozen=True)
class Observation:
    """One poll. ``online is None`` means the fetch failed, which is not the
    same as an empty player list and must never be read as one."""

    at: float
    online: frozenset[str] | None
    version: str | None = None
    error: str | None = None


@dataclass
class Outcome:
    verdict: Verdict
    detail: str
    joined_after_s: float | None = None
    held_for_s: float | None = None
    server_version: str | None = None
    others_online: tuple[str, ...] = ()
    polls: int = 0


@dataclass
class JoinWatch:
    """Decide a verdict from a stream of observations.

    Pure, so every failure mode below is reachable in a test without a server.
    """

    player: str
    started_at: float
    timeout_s: float = 300.0
    hold_s: float = 60.0
    max_consecutive_errors: int = 3
    allow_already_online: bool = False

    polls: int = 0
    joined_at: float | None = None
    server_version: str | None = None
    last_seen_others: tuple[str, ...] = ()
    _consecutive_errors: int = 0
    _saw_absent: bool = False
    _errors: list[str] = field(default_factory=list)

    @property
    def _needle(self) -> str:
        return self.player.strip().casefold()

    def _present(self, online: frozenset[str]) -> bool:
        return any(name.strip().casefold() == self._needle for name in online)

    def observe(self, obs: Observation) -> Outcome | None:
        """Fold one poll in. Returns an Outcome once decided, else None."""
        self.polls += 1
        elapsed = obs.at - self.started_at

        if obs.online is None:
            # A failed fetch carries no information about presence. It must not
            # advance drop detection, or one dropped packet mid-hold reports a
            # crash that never happened.
            self._consecutive_errors += 1
            if obs.error:
                self._errors.append(obs.error)
            if self._consecutive_errors >= self.max_consecutive_errors:
                return Outcome(
                    verdict=Verdict.UNREACHABLE,
                    detail=(
                        f"{self._consecutive_errors} consecutive failed polls: "
                        f"{self._errors[-1] if self._errors else 'no detail'}"
                    ),
                    server_version=self.server_version,
                    polls=self.polls,
                )
            return self._timed_out(elapsed)

        self._consecutive_errors = 0
        if obs.version:
            self.server_version = obs.version
        present = self._present(obs.online)
        self.last_seen_others = tuple(
            sorted(n for n in obs.online if n.strip().casefold() != self._needle)
        )

        if present and not self._saw_absent and self.joined_at is None:
            # Present on the first look. Whatever this is, it is not a join we
            # watched happen, and calling it one would pass a test that never ran.
            if not self.allow_already_online:
                return Outcome(
                    verdict=Verdict.ALREADY_ONLINE,
                    detail=(
                        f"{self.player} was already online at the first poll, so this watch "
                        "cannot tell a fresh join from a session that never ended. Log out, "
                        "then start the watch before joining."
                    ),
                    server_version=self.server_version,
                    others_online=self.last_seen_others,
                    polls=self.polls,
                )
            self.joined_at = obs.at

        if not present:
            self._saw_absent = True
            if self.joined_at is not None:
                held = obs.at - self.joined_at
                return Outcome(
                    verdict=Verdict.DROPPED,
                    detail=(
                        f"{self.player} appeared, then left the player list after "
                        f"{held:.0f}s, short of the {self.hold_s:.0f}s hold. That is what a "
                        "client crashing after world load looks like from here."
                    ),
                    joined_after_s=self.joined_at - self.started_at,
                    held_for_s=held,
                    server_version=self.server_version,
                    others_online=self.last_seen_others,
                    polls=self.polls,
                )
            return self._timed_out(elapsed)

        if self.joined_at is None:
            self.joined_at = obs.at

        held = obs.at - self.joined_at
        if held >= self.hold_s:
            return Outcome(
                verdict=Verdict.JOINED,
                detail=(
                    f"{self.player} reached the player list after "
                    f"{self.joined_at - self.started_at:.0f}s and stayed for {held:.0f}s."
                ),
                joined_after_s=self.joined_at - self.started_at,
                held_for_s=held,
                server_version=self.server_version,
                others_online=self.last_seen_others,
                polls=self.polls,
            )
        return None

    def _timed_out(self, elapsed: float) -> Outcome | None:
        if elapsed < self.timeout_s:
            return None
        return Outcome(
            verdict=Verdict.NEVER_APPEARED,
            detail=(
                f"{self.player} never reached the player list in {elapsed:.0f}s "
                f"across {self.polls} polls."
            ),
            server_version=self.server_version,
            others_online=self.last_seen_others,
            polls=self.polls,
        )


async def poll_once(client: httpx.AsyncClient, url: str, at: float) -> Observation:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        info: dict[str, Any] = resp.json()
    except Exception as exc:
        return Observation(at=at, online=None, error=f"{type(exc).__name__}: {exc}")
    # Field reads match to_payload() in eco_mcp_app.server.
    names = info.get("OnlinePlayersNames") or []
    return Observation(
        at=at,
        online=frozenset(str(n) for n in names if str(n).strip()),
        version=str(info["Version"]) if info.get("Version") else None,
    )


async def watch(
    url: str,
    watcher: JoinWatch,
    interval_s: float,
    expect_version: str | None,
    quiet: bool,
) -> Outcome:
    warned_version = False
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            obs = await poll_once(client, url, time.monotonic())

            if not warned_version and obs.version and expect_version:
                warned_version = True
                if obs.version.strip() != expect_version.strip():
                    print(
                        f"! server is {obs.version}, you expected {expect_version}. A client on "
                        "a different version is refused at the handshake, before anything can "
                        "crash, and this watch will report never-appeared.",
                        file=sys.stderr,
                    )

            if not quiet:
                if obs.online is None:
                    state = f"unreachable ({obs.error})"
                elif watcher._present(obs.online):
                    state = "present"
                else:
                    state = f"absent ({len(obs.online)} others online)"
                print(
                    f"  {obs.at - watcher.started_at:6.0f}s  {state}",
                    file=sys.stderr,
                )

            outcome = watcher.observe(obs)
            if outcome is not None:
                return outcome
            await asyncio.sleep(interval_s)


def render(outcome: Outcome, player: str, url: str, as_json: bool, reveal: bool = False) -> str:
    if as_json:
        return json.dumps(
            {
                "verdict": str(outcome.verdict),
                "player": player,
                "sourceUrl": display_url(url, reveal),
                "detail": outcome.detail,
                "joinedAfterSeconds": outcome.joined_after_s,
                "heldForSeconds": outcome.held_for_s,
                "serverVersion": outcome.server_version,
                "othersOnline": list(outcome.others_online),
                "polls": outcome.polls,
            },
            indent=2,
        )
    lines = [f"{HEADLINES[outcome.verdict]}: {outcome.detail}"]
    if outcome.server_version:
        lines.append(f"server version: {outcome.server_version}")
    if outcome.others_online:
        lines.append(f"others online: {', '.join(outcome.others_online)}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="join_watch",
        description="Watch an Eco server's player list and report whether one join held.",
        epilog=(
            "exit codes:\n"
            "  0  joined          reached the player list and stayed for the hold window\n"
            "  1  never-appeared  the timeout elapsed with the name absent. The outcome\n"
            "                     names who was online instead, which is usually faster\n"
            "                     to read than the trace\n"
            "  2  unreachable     three consecutive polls failed. A server that is down\n"
            "                     is not a client that failed, so it gets its own code\n"
            "  3  dropped         appeared, then left before the hold completed. This is\n"
            "                     what a client crashing after world load looks like\n"
            "  4  already-online  the player was online at the first poll, so the watch\n"
            "                     cannot tell a fresh join from a session that never\n"
            "                     ended. Log out, start the watch, then join\n"
            "\n"
            "A failed poll means absence of information, never absence of the player, so\n"
            "one dropped packet mid-hold cannot manufacture a `dropped`.\n"
            "\n"
            "Version skew is the failure you hit first: a client and server on different\n"
            "versions refuse each other at the handshake, before anything can crash, and\n"
            "from here that is indistinguishable from never-appeared. Pass\n"
            "--expect-version and the watch says so on the first poll instead of letting\n"
            "you spend the whole timeout on it.\n"
            "\n"
            "The target comes from scripts/resolve-eco-target.sh, the same resolver\n"
            "`just http` uses. Its host is masked in output because it may be the\n"
            "SSM-sourced tailnet FQDN; --show-target prints it in full.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("player", help="in-game player name to watch for")
    parser.add_argument(
        "--server",
        default=None,
        help="host, host:port, or full /info URL. Defaults to $ECO_INFO_URL.",
    )
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for a join")
    parser.add_argument(
        "--hold",
        type=float,
        default=60.0,
        help="seconds the name must stay online before this counts as a join",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    parser.add_argument(
        "--expect-version",
        default=None,
        help="warn loudly if the server reports a different version",
    )
    parser.add_argument(
        "--allow-already-online",
        action="store_true",
        help="do not refuse when the player is online at the first poll",
    )
    parser.add_argument(
        "--show-target",
        action="store_true",
        help="print the resolved host instead of masking it",
    )
    parser.add_argument("--json", action="store_true", help="emit the outcome as JSON")
    parser.add_argument("--quiet", action="store_true", help="suppress the per-poll trace")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    url = normalize_server_url(args.server)
    if not args.quiet:
        print(
            f"watching {args.player} on {display_url(url, args.show_target)}",
            file=sys.stderr,
        )
    watcher = JoinWatch(
        player=args.player,
        started_at=time.monotonic(),
        timeout_s=args.timeout,
        hold_s=args.hold,
        allow_already_online=args.allow_already_online,
    )
    try:
        outcome = asyncio.run(watch(url, watcher, args.interval, args.expect_version, args.quiet))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    print(render(outcome, args.player, url, args.json, args.show_target))
    return EXIT_CODES[outcome.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
