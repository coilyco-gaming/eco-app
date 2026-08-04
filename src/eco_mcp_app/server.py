"""MCP server for public Eco game servers."""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from cachetools import TTLCache
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    Icon,
    TextContent,
    Tool,
)

from . import climate as climate_mod
from . import currency as currency_mod
from . import ecoregion as ecoregion_mod
from . import fair_price as fair_price_mod
from . import market as market_mod
from . import species as species_mod
from . import wave1_routes, wave2_routes
from .civics import civics_markdown, fetch_civics
from .crafting import atlas_markdown, fetch_atlas
from .dual_routes import DualRouteRegistry
from .logistics import fetch_logistics, logistics_markdown
from .map import build_map_payload, fetch_map_bundle
from .progression import fetch_history, history_markdown
from .social import fetch_social, social_markdown
from .stores import directory_markdown, fetch_directory
from .telemetry import instrument_mcp_server
from .trades import fetch_ledger, ledger_markdown
from .watchers import (
    WatcherError,
    build_query,
    create_watcher,
    evaluate_all,
    evaluate_markdown,
    list_watchers,
    remove_watcher,
    watchers_list_markdown,
)
from .world import fetch_world, world_markdown

PUBLIC_SERVERS_OUTPUT_SCHEMA = wave1_routes.PUBLIC_SERVERS_OUTPUT_SCHEMA

DEFAULT_ECO_INFO_URL = os.environ.get("ECO_INFO_URL", "http://eco.coilysiren.me:3001/info")
DEFAULT_ECO_PORT = int(os.environ.get("ECO_INFO_PORT", "3001"))
# Base URL for non-/info endpoints on the same server. Derived from
# DEFAULT_ECO_INFO_URL at import time so overriding ECO_INFO_URL in tests or
# deploys redirects every endpoint consistently.
DEFAULT_ECO_BASE_URL = DEFAULT_ECO_INFO_URL.rsplit("/info", 1)[0]

# Economy dashboard: datasets pulled from the admin /datasets/get endpoint.
# Listed here so both tool wiring and tests share one source of truth; each
# string must appear in `/datasets/flatlist` on the live server.
ECONOMY_DATASETS: tuple[str, ...] = (
    "OfferedLoanOrBond",
    "AcceptedLoanOrBond",
    "RepaidLoanOrBond",
    "DefaultedOnLoanOrBond",
    "PayWages",
    "PayRentOrMoveInFee",
    "PostedContract",
    "CompletedContract",
    "FailedContract",
    "PropertyTransfer",
    "ReputationTransfer",
    "TransferMoney",
    "PayTax",
    "ReceiveGovernmentFunds",
)

# Admin endpoints (exporter/*) require an API key. We read it from the
# environment (populated by SSM at boot in the homelab deploy, or set by hand
# for local dev / tests). None → the tool will still run but get 401s, which
# surface as per-action warnings on the rendered card.
ADMIN_API_KEY_ENV = "ECO_ADMIN_API_KEY"

# Single source of truth for the public servers surfaced both as "try-others"
# pills on the rendered card and as the `list_public_servers` tool's
# response. Curated from eco-servers.org, chosen for variety in Eco markup
# patterns + ruleset (so the iframe gets exercised against diverse titles).
KNOWN_PUBLIC_SERVERS: list[dict[str, str]] = [
    {
        "label": "Eco via Sirens",
        "host": "eco.coilysiren.me:3001",
        "notes": "Kai's server (default for this MCP). Highly modded, collaborative.",
    },
    {
        "label": "AWLGaming",
        "host": "ecoserver.awlgaming.net:5679",
        "notes": "Hex + named color mix in the TMP title.",
    },
    {
        "label": "GreenLeaf Prime",
        "host": "eco.greenleafserver.com:3021",
        "notes": "<#RRGGBB> shorthand rainbow title.",
    },
    {
        "label": "GreenLeaf Vanilla",
        "host": "eco.greenleafserver.com:3031",
        "notes": "Same host as Prime, vanilla ruleset.",
    },
    {
        "label": "The Dao Kingdom",
        "host": "daokingdom.eu:3001",
        "notes": "Short-form hex + explicit </color> closes.",
    },
    {
        "label": "Peaceful Utopia",
        "host": "eco.bleedcraft.com:3001",
        "notes": "No markup in the title; meteor already passed.",
    },
]


def normalize_server_url(server: str | None) -> str:
    """Turn a user-supplied server string into a full /info URL.

    Accepts any of: a full URL (`http://host:3001/info`), host-only
    (`eco.example.com`, `192.168.1.5`), or host:port (`10.0.0.5:4001`).
    Most public Eco servers advertise as bare IPs, so we don't require a
    scheme — we assume http and the default Eco port when missing.
    """
    if not server:
        return DEFAULT_ECO_INFO_URL
    s = server.strip()
    if not s:
        return DEFAULT_ECO_INFO_URL
    if "://" not in s:
        s = f"http://{s}"
    parsed = urlparse(s)
    host = parsed.hostname or ""
    port = parsed.port or DEFAULT_ECO_PORT
    path = parsed.path if parsed.path and parsed.path != "/" else "/info"
    return urlunparse((parsed.scheme or "http", f"{host}:{port}", path, "", "", ""))


# In-memory cache for /info responses. The /preview route can get hammered by
# refreshes, and each cache miss fans out to a third-party Eco server — without
# this a single tab reloader can DoS a small community server. 30s matches
# Eco's own in-game stats update cadence closely enough that nothing visibly
# stale slips through. Cache key is the normalized URL so the same server
# expressed two ways (`host` vs `host:3001/info`) shares an entry.
_INFO_CACHE_TTL_S = float(os.environ.get("ECO_INFO_CACHE_TTL", "30"))
_info_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=128, ttl=_INFO_CACHE_TTL_S)


async def fetch_eco_info(server: str | None = None) -> dict[str, Any]:
    """Hit the Eco server /info endpoint. Raises on non-200. 30s memoized."""
    url = normalize_server_url(server)
    cached = _info_cache.get(url)
    if cached is not None:
        return dict(cached)
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        data["_sourceUrl"] = url
        _info_cache[url] = dict(data)
        return data


# ---------------------------------------------------------------------------
# Government org-chart tool
# ---------------------------------------------------------------------------
#
# Eco law descriptions are authored in TextMeshPro rich-text markup, but the
# government panel doesn't try to color or style them — we just want a plain
# human-readable preview for the footer. This regex strips the tag families
# we see in practice on the live server (`<link=...>`, `<icon ...>`,
# `<color=...>`, `<style=...>`, plus bare `<i>`, `<u>`, `<linktext>`,
# `<foldout>`, `<title>`) and leaves surrounding text intact. See
# The post-name character class is `[\s=]` because Eco emits attribute forms
# like `<style="Header">` / `<color=#FFF>` with no whitespace before the `=`.
_LAW_MARKUP = re.compile(
    r"</?(?:link|icon|color|style|b|i|u|s|size|sprite|mark|lowercase|uppercase"
    r"|smallcaps|linktext|foldout|title)(?:[\s=][^>]*)?/?>",
    re.IGNORECASE,
)


def strip_law_markup(s: str | None) -> str:
    """Remove Eco rich-text tags from a law description."""
    if not s:
        return ""
    return _LAW_MARKUP.sub("", s).strip()


# Labels inside each title's Table rows that we care about. Keys are the
# normalized attribute name we expose; values are the exact `Property` labels
# the Eco API emits. These are verified live against
# `/api/v1/elections/titles` on Day 3 of Cycle 13; if upstream relabels them
# we'll start rendering "None" and that's fine — the layout still holds.
_TITLE_ROW_KEYS = {
    "election_process": "Election Process",
    "eligible_candidates": "Eligible Candidates",
    "successor": "Successor",
    "who_can_remove": "Who Can Remove From Office",
    "term_days": "Term Limit Days",
}


def _build_eco_url(base: str | None, path: str) -> str:
    """Compose an endpoint URL from a user-supplied server (or the default)."""
    if not base:
        return f"{DEFAULT_ECO_BASE_URL}{path}"
    normalized = normalize_server_url(base)
    # normalize_server_url always appends `/info` (or whatever path the user
    # supplied). Strip any path off — we want just scheme + host:port.
    parsed = urlparse(normalized)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


async def fetch_eco_government(server: str | None = None) -> dict[str, Any]:
    """Hit the three civic endpoints in parallel and return raw JSON.

    Returns a dict with keys `titles`, `elections`, `laws`, each the parsed
    JSON body. `elections` may be `[]` (verified empty on Day 3 of the
    current cycle) and callers must handle that. Raises on the first
    non-200 / connect error encountered.
    """
    titles_url = _build_eco_url(server, "/api/v1/elections/titles")
    elections_url = _build_eco_url(server, "/api/v1/elections")
    laws_url = _build_eco_url(server, "/api/v1/laws?byStates=Active")
    async with httpx.AsyncClient(timeout=8.0) as client:
        titles = await _get_json(client, titles_url)
        elections = await _get_json(client, elections_url)
        laws = await _get_json(client, laws_url)
    return {
        "titles": titles,
        "elections": elections,
        "laws": laws,
        "_sourceUrl": titles_url,
    }


def _row_value(table: list[list[str]], label: str) -> str | None:
    """Pull the value cell from a `[property, description, value]` row."""
    for row in table:
        if row and len(row) >= 3 and row[0] == label:
            return row[2]
    return None


def _extract_scope(titles: list[dict[str, Any]]) -> str:
    """Derive the settlement/federation name from title scopes.

    Title names are shaped like `"<Scope> Mayor"` / `"<Scope> Governor"` /
    `"<Scope> Sheriff"`. We take the first title and strip the trailing role
    word. Returns `"Unknown settlement"` if we can't parse it — callers
    render that string directly in the header.
    """
    if not titles:
        return "Unknown settlement"
    first = titles[0].get("Name", "") or ""
    # Strip the last token (role word) — "Foo Bar Mayor" → "Foo Bar".
    parts = first.rsplit(" ", 1)
    if len(parts) == 2 and parts[1]:
        return parts[0]
    return first or "Unknown settlement"


def to_government_payload(
    data: dict[str, Any],
    *,
    fetched_at_iso: str | None = None,
) -> dict[str, Any]:
    """Shape the raw endpoint blob into the view dict the template consumes."""
    titles_raw: list[dict[str, Any]] = data.get("titles") or []
    elections_raw: list[dict[str, Any]] = data.get("elections") or []
    laws_raw: list[dict[str, Any]] = data.get("laws") or []

    titles: list[dict[str, Any]] = []
    for t in titles_raw:
        table = t.get("Table") or []
        titles.append(
            {
                "id": t.get("Id"),
                "name": t.get("Name") or "?",
                "state": t.get("State"),
                "occupants": list(t.get("OccupantNames") or []),
                "successor": _row_value(table, _TITLE_ROW_KEYS["successor"]),
                "who_can_remove": _row_value(table, _TITLE_ROW_KEYS["who_can_remove"]),
                "term_days": _row_value(table, _TITLE_ROW_KEYS["term_days"]),
                "eligible_candidates": _row_value(table, _TITLE_ROW_KEYS["eligible_candidates"]),
            }
        )

    # Elections — server claims to filter `byStates=Active` on laws but
    # doesn't always honour the filter. We don't pass a filter for elections
    # (endpoint accepts no args) — just defensively keep only ones that look
    # open. `EndTime` / `TimeLeft` field naming drifts across Eco versions,
    # so we check a few likely shapes.
    elections: list[dict[str, Any]] = []
    for e in elections_raw:
        ends_in_hours: float | None = None
        if isinstance(e.get("TimeLeft"), int | float):
            ends_in_hours = float(e["TimeLeft"]) / 3600.0
        elif isinstance(e.get("HoursLeft"), int | float):
            ends_in_hours = float(e["HoursLeft"])
        elections.append(
            {
                "id": e.get("Id"),
                "name": e.get("Name") or e.get("TitleName") or "Election",
                "ends_in_hours": ends_in_hours,
                "state": e.get("State"),
            }
        )

    # Client-side filter: the `byStates=Active` query param is advisory —
    # verified upstream returns mixed states anyway.
    active_laws = [law for law in laws_raw if (law.get("State") or "") == "Active"]
    active_laws_count = len(active_laws)

    cleaned_laws = [
        {
            "name": law.get("Name") or "?",
            "clean": strip_law_markup(law.get("Description") or ""),
        }
        for law in active_laws
    ]
    cleaned_laws = [law for law in cleaned_laws if law["clean"]]

    shortest_law: dict[str, Any] | None = None
    longest_law: dict[str, Any] | None = None
    if cleaned_laws:
        shortest = min(cleaned_laws, key=lambda law: len(law["clean"]))
        longest = max(cleaned_laws, key=lambda law: len(law["clean"]))
        shortest_preview = _law_preview(shortest["clean"])
        longest_preview = _law_preview(longest["clean"])
        shortest_law = {
            "name": shortest["name"],
            "preview": shortest_preview,
            "preview_lines": _law_preview_lines(shortest_preview),
        }
        longest_law = {
            "name": longest["name"],
            "preview": longest_preview,
            "preview_lines": _law_preview_lines(longest_preview),
        }

    return {
        "view": "eco_government",
        "fetchedAtISO": fetched_at_iso,
        "sourceUrl": data.get("_sourceUrl"),
        "scope": _extract_scope(titles_raw),
        "titles": titles,
        "elections": elections,
        "active_laws_count": active_laws_count,
        "shortest_law": shortest_law,
        "longest_law": longest_law,
    }


def _law_preview(text: str, max_chars: int = 600) -> str:
    """Trim a sanitized law body to a reasonable preview length."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _law_preview_lines(text: str) -> list[str]:
    """Split a law preview into logical entries for bulleted rendering.

    Eco law descriptions emit one clause per newline, but the clause often
    wraps onto continuation lines that start with whitespace (e.g. the
    `then Prevent (...)` tail of an `On event ...` rule). We fold those
    continuations into the preceding entry so each returned string is a
    single reader-facing bullet.
    """
    entries: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if raw_line[:1].isspace() and entries:
            entries[-1] = f"{entries[-1]} {raw_line.strip()}"
        else:
            entries.append(raw_line.strip())
    return entries


def _format_government_markdown(payload: dict[str, Any]) -> str:
    lines = [f"**{payload['scope']} — Government**", ""]
    if payload["titles"]:
        for t in payload["titles"]:
            occs = ", ".join(t["occupants"]) if t["occupants"] else "_vacant_"
            lines.append(f"- **{t['name']}** — {occs}")
    else:
        lines.append("- No civic titles configured")
    lines.append("")
    if payload["elections"]:
        lines.append("**Active elections:**")
        for e in payload["elections"]:
            if e["ends_in_hours"] is not None:
                lines.append(f"- {e['name']} — ends in {round(e['ends_in_hours'])}h")
            else:
                lines.append(f"- {e['name']}")
    else:
        lines.append("_No active elections._")
    lines.append("")
    lines.append(f"Active laws: **{payload['active_laws_count']}**")
    if payload.get("shortest_law"):
        lines.append(f"- shortest: {payload['shortest_law']['name']}")
    if payload.get("longest_law"):
        lines.append(f"- longest: {payload['longest_law']['name']}")
    return "\n".join(lines)


def to_payload(info: dict[str, Any]) -> dict[str, Any]:
    """Shape the public status payload from a bounded subset of ``/info``."""
    per_day = info.get("ExhaustionHoursGainPerWeekday") or {}
    return {
        "view": "eco_status",
        "fetchedAtISO": info.get("_fetchedAtISO"),
        "sourceUrl": info.get("_sourceUrl"),
        "server": {
            "description": info.get("Description", ""),
            "detailedDescription": info.get("DetailedDescription", ""),
            "category": info.get("Category"),
            "discord": info.get("DiscordAddress"),
            "version": info.get("Version"),
            "language": info.get("Language"),
            "paused": bool(info.get("IsPaused")),
            "hasPassword": bool(info.get("HasPassword")),
            "adminOnline": bool(info.get("AdminOnline")),
        },
        "players": {
            "online": int(info.get("OnlinePlayers") or 0),
            "onlineNames": [
                str(name) for name in (info.get("OnlinePlayersNames") or []) if str(name).strip()
            ],
            "total": int(info.get("TotalPlayers") or 0),
            "activeAndOnline": int(info.get("ActiveAndOnlinePlayers") or 0),
            "peakActive": int(info.get("PeakActivePlayers") or 0),
        },
        "world": {
            "size": info.get("WorldSize"),
            "plants": int(info.get("Plants") or 0),
            "animals": int(info.get("Animals") or 0),
            "laws": int(info.get("Laws") or 0),
            "totalCulture": float(info.get("TotalCulture") or 0.0),
        },
        "cycle": {
            "daysRunning": int(info.get("DaysRunning") or 0),
            "daysUntilMeteor": int(info.get("DaysUntilMeteor") or 0),
            # Raw world clock in seconds since cycle start (1 in-game day = 3600s).
            # The SPA folds this into a day+hour caption via formatDayHour (eco-app#97).
            "timeSinceStartS": float(info.get("TimeSinceStart") or 0.0),
            "hasMeteor": bool(info.get("HasMeteor")),
            "collaboration": info.get("CollaborationLevel"),
            "gameSpeed": info.get("GameSpeed"),
            "simulationLevel": info.get("SimulationLevel"),
        },
        "economy": {
            "description": info.get("EconomyDesc", ""),
        },
        "exhaustion": {
            "active": bool(info.get("ExhaustionActive")),
            "afterHours": float(info.get("ExhaustionAfterHours") or 0.0),
            "hoursPerWeekday": {str(k): float(v) for k, v in per_day.items()},
        },
        "playtimesPattern": info.get("Playtimes", ""),
        "achievements": [
            {"name": k, "text": v} for k, v in (info.get("ServerAchievementsDict") or {}).items()
        ],
    }


# Achievement markup strip — matches the Eco TMP-ish inline tags that show up
# only inside ServerAchievementsDict values. Narrower than _TMP_OTHER_TAG on
# purpose: the task spec calls for exactly these three tag families so the
# parser stays predictable even if Eco adds new tags elsewhere. The real
# payload ships `<style="Culture">` (attribute immediately after the tag
# name, no whitespace), so we broaden the spec's suggested regex to allow
# `=` or whitespace as the separator.
_ACHIEVEMENT_MARKUP = re.compile(r"</?(style|icon|color)(?:[\s=][^>]*)?>", re.IGNORECASE)
# Achievement sentences start with "Create 250 total culture..." — first int
# in the first line is the target.
_FIRST_INT = re.compile(r"\d+")
# Current progress is a decimal inside the <style="Culture"> block, e.g.
# "57.6 Culture". First decimal/integer in the post-strip string is the
# current value (the target is on line 1, the current on line 2).
_FIRST_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def parse_achievement(name: str, raw: str) -> dict[str, Any]:
    """Parse a single ServerAchievementsDict entry into a progress row.

    Returns a dict with `name`, `current`, `target`, `pct`, and `stripped`
    (the human-readable text with Eco's inline markup removed). Resilient to
    missing values — if either number is absent we return ``None`` for it and
    a ``pct`` of 0.0 so the caller can still render an empty-ish bar.
    """
    stripped = _ACHIEVEMENT_MARKUP.sub("", raw or "").strip()
    # The first line carries the target ("Create 250 total culture...").
    lines = stripped.splitlines()
    first_line = lines[0] if lines else stripped
    target_match = _FIRST_INT.search(first_line)
    target = int(target_match.group()) if target_match else None
    # The current value is the first number *after* the first line. Falling
    # back to the whole string means a single-line value still works.
    rest = "\n".join(lines[1:]) if len(lines) > 1 else ""
    current_match = _FIRST_NUMBER.search(rest) or (
        _FIRST_NUMBER.search(stripped[target_match.end() :]) if target_match else None
    )
    current: float | None
    if current_match:
        try:
            current = float(current_match.group())
        except ValueError:
            current = None
    else:
        current = None
    if target and current is not None:
        pct = max(0.0, min(100.0, current / target * 100.0))
    else:
        pct = 0.0
    return {
        "name": name.strip(),
        "current": current,
        "target": target,
        "pct": pct,
        "stripped": stripped,
    }


def build_milestones_payload(info: dict[str, Any]) -> dict[str, Any]:
    """Shape the payload consumed by the milestone card template.

    Sorted by completion % descending (closest to target at top), matching the
    acceptance criterion in #13.
    """
    raw_dict = info.get("ServerAchievementsDict") or {}
    rows = [parse_achievement(name, value) for name, value in raw_dict.items()]
    rows.sort(key=lambda r: r["pct"], reverse=True)
    return {
        "view": "eco_milestones",
        "fetchedAtISO": info.get("_fetchedAtISO"),
        "sourceUrl": info.get("_sourceUrl"),
        "totalCulture": float(info.get("TotalCulture") or 0.0),
        "milestones": rows,
    }


def _format_milestones_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"**Eco milestones** — TotalCulture: **{payload['totalCulture']:.1f}**",
        "",
    ]
    if not payload["milestones"]:
        lines.append("_No achievements recorded yet — it may be very early in the cycle._")
        return "\n".join(lines)
    for row in payload["milestones"]:
        current = "—" if row["current"] is None else f"{row['current']:g}"
        target = "?" if row["target"] is None else str(row["target"])
        lines.append(f"- **{row['name']}**: {current} / {target} Culture ({row['pct']:.0f}%)")
    return "\n".join(lines)


def _format_map_markdown(payload: dict[str, Any]) -> str:
    """Plain-text fallback for hosts without the iframe."""
    dim = payload.get("worldDim") or {}
    lines = [
        f"**Eco world map** — {dim.get('x', '?')} x {dim.get('z', '?')}",
        "",
        f"- Deeds: **{payload['deedCount']}** across "
        f"**{payload['ownerCount']}** owner{'s' if payload['ownerCount'] != 1 else ''}",
    ]
    owners = payload.get("owners") or []
    if owners:
        shown = ", ".join(owners[:10])
        more = f" (+{len(owners) - 10} more)" if len(owners) > 10 else ""
        lines.append(f"- Owners: {shown}{more}")
    if payload.get("sourceUrl"):
        lines.append(f"- Source: `{payload['sourceUrl']}`")
    return "\n".join(lines)


def _resolve_species_id(name: str) -> str:
    """Turn user input into a CamelCase species id.

    Accepts `WheatSpecies` (pass-through), `Wheat` (add suffix), or
    `Snapping Turtle` (CamelCase-join + suffix). The exporter endpoint only
    speaks the raw CamelCase form.
    """
    s = (name or "").strip()
    if not s:
        return ""
    if " " not in s and s.endswith("Species"):
        return s
    if " " not in s and s[:1].isupper() and not s.isupper():
        # Looks like `Wheat` / `Bison` — single-word common name.
        return f"{s}Species"
    # Spaces present or all-lowercase: split, title-case, join.
    parts = [p for p in re.split(r"\s+", s) if p]
    joined = "".join(p[:1].upper() + p[1:].lower() for p in parts)
    if not joined.endswith("Species"):
        joined += "Species"
    return joined


def _format_species_markdown(payload: dict[str, Any]) -> str:
    lines = [f"**{payload.get('name', 'Species')}** — `{payload.get('speciesId', '?')}`"]
    source = payload.get("source") or "none"
    if source == "inat":
        lines.append("- Source: iNaturalist")
    elif source == "wikipedia":
        lines.append("- Source: Wikipedia (no iNat match)")
    else:
        lines.append("- Source: none (modded or fictional species)")
    taxonomy = payload.get("taxonomy") or []
    if taxonomy:
        lines.append("- Taxonomy: " + " > ".join(t["name"] for t in taxonomy))
    if payload.get("conservationStatus"):
        lines.append(f"- Conservation: {payload['conservationStatus']}")
    if payload.get("wikiExtract"):
        lines.append("")
        lines.append(payload["wikiExtract"])
        lines.append("")
    population = payload.get("population") or []
    if population:
        first = payload.get("populationFirst")
        latest = payload.get("populationLatest")
        delta = payload.get("populationDelta")
        lines.append(
            f"- Population: {first} → {latest}"
            f" (Δ {'+' if (delta or 0) > 0 else ''}{delta})"
            f" across {len(population)} samples"
        )
    elif payload.get("error"):
        lines.append(f"- Population: _{payload['error']}_")
    else:
        lines.append("- Population: no samples yet")
    if payload.get("wikiUrl"):
        lines.append(f"- [Wikipedia]({payload['wikiUrl']})")
    return "\n".join(lines)


async def _in_game_reference_for(
    item: str | None, server_arg: str | None
) -> market_mod.InGameReference | None:
    """Best-effort in-game price read for the fair-price cross-reference.

    Gated on an admin key (the trades exporter needs one) so a keyless host —
    and the FRED-only unit tests — never touch the exporter. Any failure
    (unreachable server, no matching in-game market) returns None and the
    advisor falls back to the pure FRED narrative.
    """
    api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
    if not api_key:
        return None
    eco_item = fair_price_mod.eco_item_for(item)
    if not eco_item:
        return None
    try:
        intel = await market_mod.fetch_market(base_url=server_arg, api_key=api_key)
    except Exception:  # the FRED path must survive any exporter fault
        return None
    return market_mod.in_game_reference(intel, eco_item)


def _format_ecoregion_markdown(payload: dict[str, Any]) -> str:
    """Summarize an ecoregion payload for an MCP text result."""
    lines = ["**Biome composition**"]
    for b in payload.get("biomes") or []:
        pct = float(b.get("percent") or 0.0)
        if pct > 0:
            lines.append(f"- {b['display']}: {pct:.0f}%")
    unc = float(payload.get("unclassifiedPercent") or 0.0)
    if unc > 0:
        lines.append(f"- _Unclassified / mixed terrain: {unc:.0f}%_")
    lines += ["", "**Closest real-world ecoregions**"]
    for m in payload.get("ecoregionMatches") or []:
        lines.append(f"- {m['name']} (sim {m['similarity']:.2f}) — {m['description']}")
    drift = payload.get("drift") or {}
    lines += ["", "**Biodiversity drift**"]
    if not payload.get("adminAvailable"):
        lines.append("- Admin endpoints unavailable; configure the API key.")
    elif (drift.get("speciesWithDrift") or 0) == 0:
        lines.append(f"- Drift minimal so far across {drift.get('speciesSeen') or 0} species.")
    else:

        def _delta(d: dict[str, Any]) -> str:
            # A from-zero grower has deltaRel=None (see ecoregion._drift_entry).
            if d.get("fromZero") or d.get("deltaRel") is None:
                return "new"
            return f"{d['deltaRel'] * 100:+.0f}%"

        if drift.get("boom"):
            lines.append("- Boom: " + ", ".join(f"{d['name']} {_delta(d)}" for d in drift["boom"]))
        if drift.get("bust"):
            lines.append("- Bust: " + ", ".join(f"{d['name']} {_delta(d)}" for d in drift["bust"]))
    return "\n".join(lines)


# SSM fetch is lazy + best-effort. If boto3 isn't installed or the param is
# missing we just render without the drift section (public endpoints still
# work). Per CLAUDE.md the param lives in us-east-1 — AWS CLI default is
# us-west-2 so the region must be pinned explicitly.
_ECO_ADMIN_TOKEN_PARAM = "/eco-mcp-app/api-admin-token"
_ECO_ADMIN_TOKEN: str | None = None
_ECO_ADMIN_TOKEN_LOADED = False


def _get_admin_token() -> str | None:
    """Fetch + memoize the Eco admin API key.

    Order of precedence:
    1. ``ECO_ADMIN_TOKEN`` env var — wins for local dev + tests.
    2. SSM ``/eco-mcp-app/api-admin-token`` in us-east-1 (per CLAUDE.md).

    On any failure returns None and the drift strip renders its empty state.
    """
    global _ECO_ADMIN_TOKEN, _ECO_ADMIN_TOKEN_LOADED
    if _ECO_ADMIN_TOKEN_LOADED:
        return _ECO_ADMIN_TOKEN
    _ECO_ADMIN_TOKEN_LOADED = True
    env = os.environ.get("ECO_ADMIN_TOKEN")
    if env:
        _ECO_ADMIN_TOKEN = env
        return env
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        client = boto3.client("ssm", region_name="us-east-1")
        resp = client.get_parameter(Name=_ECO_ADMIN_TOKEN_PARAM, WithDecryption=True)
        _ECO_ADMIN_TOKEN = resp["Parameter"]["Value"]
    except Exception:
        _ECO_ADMIN_TOKEN = None
    return _ECO_ADMIN_TOKEN


def _format_markdown(payload: dict[str, Any]) -> str:
    p = payload["players"]
    w = payload["world"]
    c = payload["cycle"]
    s = payload["server"]
    title = s.get("description") or s.get("category") or "Eco server"
    lines = [
        f"**{title}** — {s.get('category', 'Server')} · cycle day {c['daysRunning']}",
        "",
        f"- Online: **{p['online']} / {p['total']}** players"
        f" (peak {p['peakActive']}, active {p['activeAndOnline']})",
        f"- Days until meteor: **{c['daysUntilMeteor']}**" + (" ☄" if c["hasMeteor"] else ""),
        f"- World: {w['size']} · {w['plants']:,} plants · {w['animals']:,} animals"
        f" · {w['laws']} law{'s' if w['laws'] != 1 else ''}"
        f" · culture {w['totalCulture']:.1f}",
        f"- Version: `{s.get('version', '?')}` · {c['collaboration']}"
        f" · game speed: {c['gameSpeed']}",
    ]
    if s.get("discord"):
        lines.append(f"- [Join Discord]({s['discord']})")
    if payload.get("sourceUrl"):
        lines.append(f"- Source: `{payload['sourceUrl']}`")
    return "\n".join(lines)


##
## Economy dashboard
##
## Separate code path from `/info`: hits the admin /datasets/get endpoint
## (requires X-API-Key header) and /info for cycle-day + EconomyDesc, computes
## KPIs on top, and renders a dedicated card partial with inline SVG sparklines.
##

# Base URL for admin endpoints. We derive the admin base from ECO_INFO_URL so a
# non-default server can be targeted by setting one env var.
_ADMIN_DEFAULT_BASE = os.environ.get(
    "ECO_ADMIN_BASE",
    DEFAULT_ECO_INFO_URL.rsplit("/info", 1)[0],
)

# SSM secret paths. Region is pinned us-east-1: the AWS CLI default is
# us-west-2 and would silently miss these params.
_SSM_REGION = os.environ.get("AWS_REGION", "us-east-1")
_ECO_ADMIN_SSM_PATH = os.environ.get("ECO_ADMIN_TOKEN_SSM", "/eco-mcp-app/api-admin-token")

# Admin token cache — loaded once per process at first-use, not per-request.
# An explicit env var ECO_ADMIN_TOKEN overrides SSM so tests and local dev
# don't need AWS credentials. TTL is effectively infinite (1 hour is plenty;
# the process restarts more often than the SSM value rotates).
_admin_token_cache: TTLCache[str, str | None] = TTLCache(maxsize=1, ttl=3600)


def _load_admin_token() -> str | None:
    """Return the Eco admin API token or None if unavailable.

    Order: `ECO_ADMIN_TOKEN` env var → SSM `/eco-mcp-app/api-admin-token` in
    us-east-1 → None (caller renders the empty-state card). Cached so we
    don't reach for boto3 on every call.
    """
    if "token" in _admin_token_cache:
        return _admin_token_cache["token"]
    token = os.environ.get("ECO_ADMIN_TOKEN")
    if not token:
        try:
            import boto3  # type: ignore[import-not-found]

            ssm = boto3.client("ssm", region_name=_SSM_REGION)
            resp = ssm.get_parameter(Name=_ECO_ADMIN_SSM_PATH, WithDecryption=True)
            token = resp["Parameter"]["Value"]
        except Exception:
            # boto3 missing, no creds, or param not found — all equivalent for
            # our purposes (we'll render the card with no series).
            token = None
    _admin_token_cache["token"] = token
    return token


# Per-process dataset cache. The dashboard is viewed in bursts (user alt-tabs
# between conversation + iframe), and each render fans out 14 admin requests —
# without this we'd hammer the Eco server's admin endpoint.
_ECONOMY_CACHE_TTL_S = float(os.environ.get("ECO_ECONOMY_CACHE_TTL", "45"))
_economy_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=64, ttl=_ECONOMY_CACHE_TTL_S)


async def _fetch_dataset(
    client: httpx.AsyncClient,
    base: str,
    name: str,
    day_end: int,
    headers: dict[str, str],
) -> list[tuple[float, float]]:
    """Fetch a single /datasets/get series. Returns [] on any non-200 or shape surprise.

    Day-3 reality: some series are legitimately empty, and malformed stats
    return 500. We shouldn't let a single bad series blow up the whole card.
    """
    try:
        url = f"{base}/datasets/get"
        r = await client.get(
            url,
            params={"dataset": name, "dayStart": 0, "dayEnd": max(day_end, 1)},
            headers=headers,
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    # /datasets/get returns either a list of {Time, Value} dicts or a list of
    # two-item [time, value] pairs — tolerate both shapes defensively.
    out: list[tuple[float, float]] = []
    if isinstance(data, list):
        for pt in data:
            if isinstance(pt, dict):
                t = pt.get("Time", pt.get("time"))
                v = pt.get("Value", pt.get("value"))
            elif isinstance(pt, list | tuple) and len(pt) >= 2:
                t, v = pt[0], pt[1]
            else:
                continue
            try:
                out.append((float(t), float(v)))
            except (TypeError, ValueError):
                continue
    elif isinstance(data, dict):
        # Sometimes the endpoint wraps points under a "Values" / "Points" key.
        points = data.get("Values") or data.get("Points") or []
        for pt in points:
            try:
                out.append((float(pt["Time"]), float(pt["Value"])))
            except (KeyError, TypeError, ValueError):
                continue
    return out


async def fetch_economy(server: str | None = None) -> dict[str, Any]:
    """Fetch /info + all ECONOMY_DATASETS series for the given Eco server.

    Shape: `{info, days_elapsed, series: {name: [(t,v), ...]}, admin_ok}`.
    Never raises for admin-token problems — we degrade to an empty series map
    and the card renders an "admin token missing" banner.
    """
    info_url = normalize_server_url(server)
    # Derive admin base from the /info URL so the same `server` arg routes both.
    parsed = urlparse(info_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    cache_key = base
    cached = _economy_cache.get(cache_key)
    if cached is not None:
        return dict(cached)

    info = await fetch_eco_info(server)
    # TimeSinceStart is seconds since cycle start; some servers return a float.
    # One in-game "day" = 3600s by default, but the authoritative number is
    # `DaysRunning` on /info — match what the rest of the UI already shows.
    days_elapsed = int(info.get("DaysRunning") or 0)
    if days_elapsed <= 0:
        tss = info.get("TimeSinceStart")
        try:
            days_elapsed = max(1, int(float(tss) / 3600.0))
        except (TypeError, ValueError):
            days_elapsed = 1

    token = _load_admin_token()
    admin_ok = bool(token)
    series: dict[str, list[tuple[float, float]]] = {}
    if token:
        headers = {"X-API-Key": token}
        async with httpx.AsyncClient(timeout=10.0) as client:
            import asyncio

            results = await asyncio.gather(
                *(
                    _fetch_dataset(client, base, name, days_elapsed, headers)
                    for name in ECONOMY_DATASETS
                ),
                return_exceptions=False,
            )
        series = dict(zip(ECONOMY_DATASETS, results, strict=True))
    else:
        series = {name: [] for name in ECONOMY_DATASETS}

    out: dict[str, Any] = {
        "info": info,
        "days_elapsed": days_elapsed,
        "series": series,
        "admin_ok": admin_ok,
    }
    _economy_cache[cache_key] = dict(out)
    return out


def _series_total(points: list[tuple[float, float]]) -> float:
    """Sum of values (count-type stats are already cumulative/per-event)."""
    return float(sum(v for _, v in points))


def _series_last(points: list[tuple[float, float]]) -> float:
    return float(points[-1][1]) if points else 0.0


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 1)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return var**0.5


def _wow_activity_delta(
    series: dict[str, list[tuple[float, float]]], days_elapsed: int
) -> float | None:
    """Week-over-week % change in economic activity: trailing 7 in-game days
    vs the prior 7, summing every dataset's per-day event values.

    Eco exposes a trade *count* only as a scalar in /info's EconomyDesc, never
    as a time-series, so a literal "trades/day WoW" is uncomputable. Total
    transactional activity across the datasets is the closest available
    velocity proxy, and it is what drives the `booming` classification.

    Returns None until there are two full weeks of runtime with activity in the
    prior window — WoW is undefined before then, and a young server should read
    `healthy`, never `booming`. (The previous implementation derived the
    trailing rate from the cumulative average, which is algebraically identical
    to that average, so the delta was always 0.0 and `booming` was unreachable.)
    """
    if days_elapsed < 14:
        return None
    per_day: dict[int, float] = {}
    for points in series.values():
        for t, v in points:
            day = int(t)
            per_day[day] = per_day.get(day, 0.0) + v
    if not per_day:
        return None
    last_day = max(days_elapsed, max(per_day))
    mid = last_day - 7
    prior_start = last_day - 14
    prior = sum(v for d, v in per_day.items() if prior_start < d <= mid)
    trailing = sum(v for d, v in per_day.items() if mid < d <= last_day)
    prior_rate = prior / 7.0
    if prior_rate <= 0:
        return None
    trailing_rate = trailing / 7.0
    return round((trailing_rate / prior_rate - 1.0) * 100.0, 1)


def compute_economy_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn a fetch_economy() result into the dict consumed by the card template.

    Classification thresholds (per task spec):
      booming : default rate < 5% AND activity up ≥20% WoW (needs ≥14d runtime)
      stressed: default rate > 15% OR contract failure rate > 30%
      healthy : otherwise
    """
    info = raw.get("info") or {}
    series: dict[str, list[tuple[float, float]]] = raw.get("series") or {}
    days_elapsed = max(1, int(raw.get("days_elapsed") or 1))

    # KPI primitives.
    offered_loans = _series_total(series.get("OfferedLoanOrBond", []))
    accepted_loans = _series_total(series.get("AcceptedLoanOrBond", []))
    repaid_loans = _series_total(series.get("RepaidLoanOrBond", []))
    defaulted_loans = _series_total(series.get("DefaultedOnLoanOrBond", []))

    posted_contracts = _series_total(series.get("PostedContract", []))
    completed_contracts = _series_total(series.get("CompletedContract", []))
    failed_contracts = _series_total(series.get("FailedContract", []))

    wages = _series_total(series.get("PayWages", []))
    taxes_paid = _series_total(series.get("PayTax", []))
    govt_funds = _series_total(series.get("ReceiveGovernmentFunds", []))
    net_tax_flow = taxes_paid - govt_funds

    # Trades/day: EconomyDesc on /info says "N trades, M contracts" authoritatively.
    # We parse it for the displayed number because /datasets doesn't have a
    # `Trade` series (TransferMoney is money transfers, not goods trades).
    econ_desc = str(info.get("EconomyDesc") or "")
    trades_total = 0
    m = re.search(r"(\d+)\s*trade", econ_desc)
    if m:
        trades_total = int(m.group(1))
    trades_per_day = round(trades_total / days_elapsed, 1) if days_elapsed else 0.0

    # Loan default rate — defaults vs (defaulted + repaid) gives the realized
    # rate; open loans (accepted-but-not-yet-repaid) aren't resolved yet.
    resolved_loans = defaulted_loans + repaid_loans
    default_rate = _pct(defaulted_loans, resolved_loans)

    # Contract completion ratio — completed / (completed + failed). Posted-but-
    # open contracts haven't had a chance to fail yet, so excluding them avoids
    # a cold-start penalty that would wrongly trigger "stressed".
    completion_ratio = _pct(completed_contracts, completed_contracts + failed_contracts)
    failure_rate = _pct(failed_contracts, completed_contracts + failed_contracts)

    # Week-over-week economic-activity delta (a real trailing-vs-prior window,
    # summed across the datasets' per-day events). None until two weeks of
    # runtime with prior-window activity. See _wow_activity_delta for why this
    # can't be a literal trades/day WoW.
    trades_wow_pct = _wow_activity_delta(series, days_elapsed)

    # Classify.
    if default_rate > 15.0 or failure_rate > 30.0:
        health = "stressed"
    elif default_rate < 5.0 and (trades_wow_pct is not None and trades_wow_pct >= 20.0):
        health = "booming"
    else:
        health = "healthy"

    narrative = (
        f"Economy is {health} — {default_rate}% default rate, "
        f"{completion_ratio}% contracts completed"
    )

    # Sparkline candidates: pick up to 4 series with the highest normalized
    # stddev (excluding series that have fewer than 2 points). Normalizing by
    # mean puts small-but-volatile series like DefaultedOnLoanOrBond on equal
    # footing with high-volume series like TransferMoney.
    candidates: list[tuple[str, float, list[tuple[float, float]]]] = []
    for name, pts in series.items():
        if len(pts) < 2:
            continue
        values = [v for _, v in pts]
        mean = sum(values) / len(values) if values else 0.0
        sd = _stddev(values)
        norm = sd / mean if mean > 0 else sd
        candidates.append((name, norm, pts))
    candidates.sort(key=lambda x: x[1], reverse=True)
    sparks = [
        {
            "name": name,
            "label": _HUMAN_STAT_LABELS.get(name, name),
            "last": _series_last(pts),
            "total": _series_total(pts),
        }
        for name, _sd, pts in candidates[:4]
    ]

    total_culture = float(info.get("TotalCulture") or 0.0)

    return {
        "server": {
            "description": info.get("Description", ""),
            "category": info.get("Category"),
            "sourceUrl": info.get("_sourceUrl"),
        },
        "days_elapsed": days_elapsed,
        "admin_ok": bool(raw.get("admin_ok")),
        "kpis": {
            "trades_per_day": trades_per_day,
            "trades_total": trades_total,
            "contract_completion_ratio": completion_ratio,
            "contract_failure_rate": failure_rate,
            "contracts_posted": int(posted_contracts),
            "contracts_completed": int(completed_contracts),
            "contracts_failed": int(failed_contracts),
            "loan_default_rate": default_rate,
            "loans_offered": int(offered_loans),
            "loans_accepted": int(accepted_loans),
            "loans_repaid": int(repaid_loans),
            "loans_defaulted": int(defaulted_loans),
            "wages_total": wages,
            "taxes_paid": taxes_paid,
            "govt_funds": govt_funds,
            "net_tax_flow": net_tax_flow,
            "total_culture": total_culture,
            "trades_wow_pct": trades_wow_pct,
        },
        "sparks": sparks,
        "health": health,
        "narrative": narrative,
        "economy_desc": econ_desc,
    }


# Human-readable labels for the datasets. Keys match ECONOMY_DATASETS.
_HUMAN_STAT_LABELS: dict[str, str] = {
    "OfferedLoanOrBond": "Loans offered",
    "AcceptedLoanOrBond": "Loans accepted",
    "RepaidLoanOrBond": "Loans repaid",
    "DefaultedOnLoanOrBond": "Loans defaulted",
    "PayWages": "Wages paid",
    "PayRentOrMoveInFee": "Rent & move-in",
    "PostedContract": "Contracts posted",
    "CompletedContract": "Contracts completed",
    "FailedContract": "Contracts failed",
    "PropertyTransfer": "Property transfers",
    "ReputationTransfer": "Reputation transfers",
    "TransferMoney": "Money transfers",
    "PayTax": "Taxes paid",
    "ReceiveGovernmentFunds": "Govt. funds paid out",
}


def _format_climate_markdown(payload: dict[str, Any]) -> str:
    """Summarize a climate payload for an MCP text result."""
    server = payload["server"].get("description") or payload["server"].get("category") or "Eco"
    co2 = payload["co2"]
    sea = payload["sea_level"]
    poll = payload["pollution"]
    lines = [f"**{server} — climate: {payload['status']}**", "", payload["narrative"], ""]
    if co2.get("current") is not None:
        delta = (
            f" ({co2['change_pct']:+.2f}% since cycle start)"
            if co2.get("change_pct") is not None
            else ""
        )
        lines.append(f"- CO2: **{co2['current']:.1f} ppm**{delta}")
    if sea.get("current") is not None:
        rate = sea.get("rate_per_day")
        rate_str = f", {rate:+.4f}/day" if rate else ""
        lines.append(f"- Sea level: **{sea['current']:.3f}**{rate_str}")
    if poll.get("current") is not None:
        unit = poll.get("unit") or ""
        unit_suffix = unit if unit == "%" else f" {unit}" if unit else ""
        lines.append(
            f"- Ground pollution: **{poll['current']:.1f}{unit_suffix}** ({poll['source']})"
        )
        observation = poll.get("observation") or {}
        freshness = observation.get("freshness_state")
        latest_day = observation.get("latest_game_day")
        current_day = observation.get("current_game_day")
        if freshness == "stale":
            lines.append(
                "- Pollution source: **stale**. "
                f"Latest sample game day {latest_day:g}, current game day {current_day}."
            )
        elif freshness == "current":
            lines.append(
                f"- Pollution source: current at game day {latest_day:g} "
                f"for current game day {current_day}."
            )
        elif latest_day is not None:
            lines.append(
                f"- Pollution source: sample game day {latest_day:g}, freshness unknown because "
                "the source cadence is unavailable."
            )
    temp = payload.get("temperature") or {}
    if temp.get("current") is not None:
        risen = temp.get("risen")
        risen_str = f" (+{risen:.2f} since cycle start)" if risen else ""
        lines.append(f"- Avg temperature: **{temp['current']:.2f} °C**{risen_str}")
    earth = payload.get("earth_match")
    if earth:
        lines.append(f"- Real-world anchor: {earth['note']} ({earth['ppm']:.0f} ppm).")

    breakdown = payload.get("breakdown") or {}
    if breakdown.get("has_data"):
        lines.append("")
        lines.append("**CO2 sources & sinks (lifetime / per day):**")
        for label, key in (
            ("From pollution", "pollution"),
            ("From animals", "animals"),
            ("From plants", "plants"),
        ):
            b = breakdown[key]
            lines.append(f"- {label}: {b['lifetime']:+,.0f} ppm ({b['per_day']:+,.2f}/day)")
        lines.append(f"- Net: {breakdown['net_per_day']:+,.2f} ppm/day")

    explainer = payload.get("explainer") or []
    if explainer:
        lines.append("")
        lines.append("**What this means:**")
        lines.extend(f"- {sentence}" for sentence in explainer)
    attrib = payload["attribution"]
    if attrib.get("has_data"):
        lines.append("")
        lines.append("**Top polluting citizens:**")
        for entry in attrib.get("top_citizens") or []:
            lines.append(f"- {entry['name']}: {entry['count']:.0f}")
        if attrib.get("top_stations"):
            lines.append("")
            lines.append("**Top polluting stations:**")
            for entry in attrib.get("top_stations") or []:
                lines.append(f"- {entry['name']}: {entry['count']:.0f}")
    if not payload["admin_ok"]:
        lines.extend(["", "_Admin token unavailable — series + attribution data are empty._"])
    return "\n".join(lines)


def _format_economy_markdown(payload: dict[str, Any]) -> str:
    k = payload["kpis"]
    server = payload["server"].get("description") or payload["server"].get("category") or "Eco"
    lines = [
        f"**{server} — economic health: {payload['health']}**",
        "",
        payload["narrative"],
        "",
        f"- Trades/day: **{k['trades_per_day']}** (total {k['trades_total']:,})",
        f"- Contracts: {k['contracts_completed']}/{k['contracts_posted']} completed"
        f" · {k['contract_failure_rate']}% failure rate",
        f"- Loans: {k['loans_accepted']} accepted / {k['loans_defaulted']} defaulted"
        f" · {k['loan_default_rate']}% default rate",
        f"- Wages paid: **{k['wages_total']:,.0f}**",
        f"- Net tax flow: **{k['net_tax_flow']:+,.0f}**"
        f" (taxes in {k['taxes_paid']:,.0f} · govt out {k['govt_funds']:,.0f})",
        f"- Total culture: {k['total_culture']:.1f}",
    ]
    if not payload.get("admin_ok"):
        lines.extend(["", "_Admin token unavailable — series data is empty._"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Currency & money-supply card (meets DiscordLink Currency / Currencies)
# ---------------------------------------------------------------------------


def _format_currency_markdown(payload: dict[str, Any]) -> str:
    """Summarize a currency payload for an MCP text result."""
    server = payload["server"].get("description") or payload["server"].get("category") or "Eco"
    money = payload["money"]
    if payload["mode"] == "report":
        selected = payload.get("selected")
        if not selected:
            lines = [f"**{server} — currency `{payload.get('query')}`**", ""]
            lines.append("No currency by that name was found in the roster.")
            if payload["currencies"]:
                known = ", ".join(c["name"] for c in payload["currencies"][:12])
                lines.append(f"Known currencies: {known}.")
            return "\n".join(lines)
        kind = "minted / backed" if selected["isMinted"] else "personal / credit"
        lines = [
            f"**{selected['name']}** — {kind} currency ({server})",
            "",
            f"- Trades: **{selected['tradeCount']}**"
            + (f" · volume {selected['tradeVolume']:,.0f}" if selected["tradeVolume"] else ""),
        ]
        if selected["mintEvents"]:
            lines.append(
                f"- Minted issuance: **{selected['mintedAmount']:,.0f}**"
                f" across {selected['mintEvents']} mint event"
                f"{'' if selected['mintEvents'] == 1 else 's'}"
            )
        if selected.get("createdBy"):
            lines.append(f"- Created by: {selected['createdBy']}")
        holders = selected["holders"]
        if holders["reachable"] and holders["list"]:
            lines.append(
                f"- Top holders ({holders['accountsCounted']} accounts,"
                f" total {holders['totalHoldings']:,.0f}):"
            )
            for h in holders["list"]:
                who = f" ({h['holder']})" if h.get("holder") else ""
                lines.append(f"  - {h['account']}{who} — {h['balance']:,.0f}")
        elif holders["reachable"]:
            lines.append("- Top holders: _no accounts hold this currency yet_")
        else:
            lines.append(f"- Top holders: _{holders['note']}_")
        return "\n".join(lines)

    lines = [f"**{server} — currency market**", "", payload["narrative"], ""]
    lines.append(f"- Active currencies: **{money['activeCurrencies']}**")
    if money["hasSupplyData"]:
        lines.append(
            f"- Money supply: **{money['totalSupply']:,.0f}**"
            f" (players {money['personalWealth']:,.0f} · gov {money['governmentHoldings']:,.0f})"
        )
    if money["tradeValue7d"]:
        lines.append(f"- Trade value (7d): **{money['tradeValue7d']:,.0f}**")
    if payload["minted"]:
        lines.append("")
        lines.append("**Minted / backed:**")
        for c in payload["minted"][:10]:
            vol = f" · vol {c['tradeVolume']:,.0f}" if c["tradeVolume"] else ""
            mint = f"minted {c['mintedAmount']:,.0f} · " if c["mintedAmount"] else ""
            lines.append(f"- {c['name']} — {mint}{c['tradeCount']} trades{vol}")
    if payload["personal"]:
        lines.append("")
        lines.append("**Personal / credit:**")
        for c in payload["personal"][:10]:
            vol = f" · vol {c['tradeVolume']:,.0f}" if c["tradeVolume"] else ""
            lines.append(f"- {c['name']} — {c['tradeCount']} trades{vol}")
    if not payload["currencies"]:
        lines.append("_No currencies created or traded yet._")
    lines.append("")
    if payload.get("holders_reachable"):
        lines.append("_Open a currency's report for its live top-holder balances._")
    elif payload["currencies"]:
        lines.append(f"_Top holders: {payload['holders_unavailable_note']}_")
    if not payload["admin_ok"]:
        lines.append("")
        lines.append("_Admin token unavailable — roster + money-supply series are empty._")
    return "\n".join(lines)


def _eco_icon() -> Icon:
    """The Eco planet mark, embedded as a self-contained data-URI icon.

    Wired into the server's `initialize` response (`serverInfo.icons`) so clients
    that render server icons - the claude.ai / ChatGPT connector tile - show the
    Eco globe instead of a generic placeholder. Same shape as steam-ops'
    `_steam_icon`: the asset is committed at `assets/eco-icon.png` (the planet
    glyph from the official ECO wordmark, palette-compressed under 10KB for the
    ChatGPT icon cap) and read at import time, base64'd into a `data:` URI rather
    than served over HTTP so the icon rides inside the initialize payload itself.
    """
    png = files("eco_mcp_app.assets").joinpath("eco-icon.png").read_bytes()
    encoded = base64.b64encode(png).decode("ascii")
    return Icon.model_validate(
        {
            "src": f"data:image/png;base64,{encoded}",
            "mimeType": "image/png",
            "sizes": ["192x192"],
        }
    )


def build_server(route_registry: DualRouteRegistry | None = None) -> Server:
    """Construct the MCP Server with all handlers registered.

    Separated from `serve()` so it can be mounted in both the stdio transport
    (Claude Desktop) and the Streamable-HTTP transport (homelab FastAPI deploy).
    The icon + website ride on the Server object because the Streamable-HTTP
    path (StreamableHTTPSessionManager) derives its initialization options from
    the Server itself, not from build_initialization_options below.
    """
    dual_routes = route_registry if route_registry is not None else DualRouteRegistry()
    server: Server = Server(
        "eco-mcp-app",
        website_url="https://eco-app.coilysiren.me",
        icons=[_eco_icon()],
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = [
            Tool(
                name="get_social",
                title="Eco - community activity",
                description=(
                    "Reconstruct the community side of an Eco server from its "
                    "action-log exporter: play activity, new arrivals from "
                    "FirstLogin, and a reputation graph showing who reps whom. "
                    "ChatSent is deliberately not fetched. Player names are "
                    "hashed to stable handles by default. A names-in-the-clear "
                    "mode is operator-gated and needs "
                    "ECO_SOCIAL_ALLOW_NAMES set server-side plus reveal_names, "
                    "never public. Requires an admin API key configured "
                    "server-side (same exporter as get_trades). Returns a "
                    "markdown summary plus structured JSON data (no MCP-app "
                    "widget)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "server": {
                            "type": "string",
                            "description": (
                                "Eco admin base URL (`host`, `host:port`, or "
                                "full URL). Omit to use the configured "
                                "default (`eco.coilysiren.me:3001`)."
                            ),
                        },
                        "reveal_names": {
                            "type": "boolean",
                            "description": (
                                "Show player names instead of redacted handles. "
                                "Operator-gated: only takes "
                                "effect when the deploy sets ECO_SOCIAL_ALLOW_NAMES "
                                "(default-deny), so a public call is always "
                                "redacted regardless. Default false."
                            ),
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="trade_watchers",
                title="Eco — trade watchers",
                description=(
                    "Host-agnostic trade watchers — the website-and-MCP answer to "
                    "DiscordLink's WatchTradeFeed / WatchTradeDisplay / "
                    "UnwatchTradeFeed / ListTradeWatchers, with no Discord "
                    "dependency. Watch an item, a store, a trader, or a price "
                    "threshold (e.g. 'iron ingot under 2.5'), then evaluate against "
                    "the trades the server already exports. `evaluate` returns both "
                    "the feed (matching trades new since the watcher last checked) "
                    "and the display (the current matching state). Watchers persist "
                    "in SQLite and survive restarts; they also show on the SPA "
                    "`/trades` route. Use `action` to pick the verb:\n"
                    "- `create` — new watcher. `kind` + `value`; for `kind=price` "
                    "also `op` (under/over) + `threshold`.\n"
                    "- `list` — every stored watcher.\n"
                    "- `remove` — delete by `id`.\n"
                    "- `evaluate` — run all watchers against the live ledger."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "list", "remove", "evaluate"],
                            "description": "Which watcher verb to run.",
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["item", "store", "trader", "price"],
                            "description": (
                                "For `create`: what to watch. `item` / `store` / "
                                "`trader` are case-insensitive name matches; `price` "
                                "pairs an item with a threshold predicate."
                            ),
                        },
                        "value": {
                            "type": "string",
                            "description": (
                                "For `create`: the item / store / trader name to "
                                "match (the item name, for `kind=price`)."
                            ),
                        },
                        "op": {
                            "type": "string",
                            "enum": ["under", "over"],
                            "description": "For `kind=price`: threshold direction.",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "For `kind=price`: the unit-price cutoff.",
                        },
                        "label": {
                            "type": "string",
                            "description": (
                                "Optional friendly label for the watcher; defaults "
                                "to a description of the query."
                            ),
                        },
                        "id": {
                            "type": "string",
                            "description": "For `remove`: the watcher id to delete.",
                        },
                        "server": {
                            "type": "string",
                            "description": (
                                "For `evaluate` (and stored on `create`): the Eco "
                                "admin base URL to pull the ledger from. Omit to use "
                                "the configured default."
                            ),
                        },
                        "advance": {
                            "type": "boolean",
                            "description": (
                                "For `evaluate`: whether to advance each watcher's "
                                "last-seen mark past its feed hits (default true — "
                                "the feed semantic). Pass false to peek without "
                                "consuming."
                            ),
                        },
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            ),
        ]
        registered_tools = dual_routes.mcp_tools()
        existing_names = {tool.name for tool in tools}
        duplicates = sorted(tool.name for tool in registered_tools if tool.name in existing_names)
        if duplicates:
            raise ValueError(f"dual routes duplicate existing MCP tools: {', '.join(duplicates)}")
        return [*tools, *registered_tools]

    async def _dispatch_call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        if name == "explain_item":
            from .wikidata import build_ecopedia_card

            item_name = (arguments or {}).get("name", "").strip() if arguments else ""
            category = (arguments or {}).get("category") if arguments else None
            if not item_name:
                err = "`name` is required (e.g. 'Iron', 'Oak', 'Bison')."
                return CallToolResult(
                    content=[TextContent(type="text", text=err)],
                    isError=True,
                )
            card = await build_ecopedia_card(item_name, category)
            card_dict = card.to_dict()
            md_lines = [f"**{card.title or card.name}**"]
            if card.category:
                md_lines[0] += f" — _{card.category}_"
            if card.description:
                md_lines.append("")
                md_lines.append(card.description)
            if card.facts:
                md_lines.append("")
                for label, value in card.facts:
                    md_lines.append(f"- **{label}**: {value}")
            if card.source_url:
                md_lines.append("")
                md_lines.append(f"Source: {card.source_url}")
            if card.not_found and not card.description:
                md_lines = [f"No Wikipedia / Wikidata entry found for '{card.name}'."]
            return CallToolResult(
                content=[
                    TextContent(type="text", text="\n".join(md_lines)),
                    TextContent(type="text", text=json.dumps(card_dict)),
                ],
            )

        if name == "get_crafting_atlas":
            server_arg = arguments.get("server") if arguments else None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                atlas = await fetch_atlas(base_url=server_arg, api_key=api_key)
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=atlas_markdown(atlas)),
                    TextContent(type="text", text=json.dumps(atlas.to_dict())),
                ],
            )

        if name == "get_world":
            server_arg = arguments.get("server") if arguments else None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                activity = await fetch_world(base_url=server_arg, api_key=api_key)
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=world_markdown(activity)),
                    TextContent(type="text", text=json.dumps(activity.to_dict())),
                ],
            )

        if name == "get_trades":
            server_arg = arguments.get("server") if arguments else None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                ledger = await fetch_ledger(base_url=server_arg, api_key=api_key)
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=ledger_markdown(ledger)),
                    TextContent(type="text", text=json.dumps(ledger.to_dict())),
                ],
            )

        if name == "get_civics":
            server_arg = arguments.get("server") if arguments else None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                civics_report = await fetch_civics(base_url=server_arg, api_key=api_key)
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=civics_markdown(civics_report)),
                    TextContent(type="text", text=json.dumps(civics_report.to_dict())),
                ],
            )

        if name == "get_progression":
            server_arg = arguments.get("server") if arguments else None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                history = await fetch_history(base_url=server_arg, api_key=api_key)
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=history_markdown(history)),
                    TextContent(type="text", text=json.dumps(history.to_dict())),
                ],
            )

        if name == "trade_watchers":
            args = arguments or {}
            action = (args.get("action") or "").strip().lower()

            def _watchers_result(md: str, payload: dict[str, Any]) -> CallToolResult:
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=md),
                        TextContent(type="text", text=json.dumps(payload)),
                    ],
                )

            if action == "create":
                try:
                    query = build_query(
                        kind=args.get("kind", ""),
                        value=args.get("value", ""),
                        op=args.get("op"),
                        threshold=args.get("threshold"),
                    )
                except WatcherError as e:
                    return CallToolResult(
                        content=[
                            TextContent(type="text", text=f"**Could not create watcher:** {e}"),
                            TextContent(type="text", text=json.dumps({"error": str(e)})),
                        ],
                        isError=True,
                    )
                watcher = create_watcher(query, label=args.get("label"), server=args.get("server"))
                md = f"**Watcher created** — `{watcher.id}` watching {query.describe()}."
                return _watchers_result(
                    md, {"view": "watcher_created", "watcher": watcher.to_dict()}
                )

            if action == "list":
                watchers = list_watchers()
                return _watchers_result(
                    watchers_list_markdown(watchers),
                    {"view": "watchers", "watchers": [w.to_dict() for w in watchers]},
                )

            if action == "remove":
                watcher_id = (args.get("id") or "").strip()
                if not watcher_id:
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text", text="**`id` is required to remove a watcher.**"
                            ),
                            TextContent(type="text", text=json.dumps({"error": "missing id"})),
                        ],
                        isError=True,
                    )
                removed = remove_watcher(watcher_id)
                md = (
                    f"**Watcher `{watcher_id}` removed.**"
                    if removed
                    else f"**No watcher `{watcher_id}` found.**"
                )
                return _watchers_result(
                    md, {"view": "watcher_removed", "id": watcher_id, "removed": removed}
                )

            if action == "evaluate":
                server_arg = args.get("server")
                advance = bool(args.get("advance", True))
                api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
                try:
                    ledger = await fetch_ledger(base_url=server_arg, api_key=api_key)
                except httpx.HTTPError as e:
                    return CallToolResult(
                        content=[
                            TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                            TextContent(
                                type="text",
                                text=json.dumps({"view": "error", "message": str(e)}),
                            ),
                        ],
                        isError=True,
                    )
                hits = evaluate_all(ledger.trades, advance=advance)
                payload = {
                    "view": "watcher_hits",
                    "fetchedAtISO": ledger.fetched_at_iso,
                    "sourceBaseUrl": ledger.source_base_url,
                    "advanced": advance,
                    "hits": [h.to_dict() for h in hits],
                }
                return _watchers_result(evaluate_markdown(hits), payload)

            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=(
                            f"**Unknown watcher action '{action}'** — "
                            "expected create / list / remove / evaluate."
                        ),
                    ),
                    TextContent(type="text", text=json.dumps({"error": "unknown action"})),
                ],
                isError=True,
            )

        if name == "get_stores":
            server_arg = arguments.get("server") if arguments else None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                directory = await fetch_directory(base_url=server_arg, api_key=api_key)
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=directory_markdown(directory)),
                    TextContent(type="text", text=json.dumps(directory.to_dict())),
                ],
            )

        if name == "get_social":
            server_arg = arguments.get("server") if arguments else None
            reveal_names = bool(arguments.get("reveal_names")) if arguments else False
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                surface = await fetch_social(
                    base_url=server_arg, api_key=api_key, reveal_names=reveal_names
                )
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=social_markdown(surface)),
                    TextContent(type="text", text=json.dumps(surface.to_dict())),
                ],
            )

        if name == "list_public_servers":
            lines = ["**Known public Eco servers:**", ""]
            for s in KNOWN_PUBLIC_SERVERS:
                lines.append(f"- **{s['label']}** — `{s['host']}` · {s['notes']}")
            return CallToolResult(
                content=[
                    TextContent(type="text", text="\n".join(lines)),
                    TextContent(
                        type="text",
                        text=json.dumps({"servers": KNOWN_PUBLIC_SERVERS}),
                    ),
                ],
                structuredContent={"servers": KNOWN_PUBLIC_SERVERS},
            )

        if name == "get_economy":
            server_arg = arguments.get("server") if arguments else None
            try:
                raw = await fetch_economy(server_arg)
            except httpx.HTTPError as e:
                err_payload = {"view": "error", "message": f"Could not reach Eco server: {e}"}
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco server unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            payload = compute_economy_payload(raw)
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_economy_markdown(payload)),
                    TextContent(type="text", text=json.dumps(payload, default=str)),
                ],
            )

        if name == "get_map":
            server_arg = arguments.get("server") if arguments else None
            try:
                bundle = await fetch_map_bundle(server_arg)
            except httpx.HTTPError as e:
                err_payload = {"view": "error", "message": f"Could not reach Eco server: {e}"}
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco server unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            payload = build_map_payload(bundle)
            json_payload = {
                k: v for k, v in payload.items() if k not in ("gifDataUri", "pollutionDataUri")
            }
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_map_markdown(payload)),
                    TextContent(type="text", text=json.dumps(json_payload)),
                ],
            )

        if name == "get_region":
            server_arg = arguments.get("server") if arguments else None
            info_url = normalize_server_url(server_arg)
            try:
                payload = await ecoregion_mod.gather_ecoregion_payload(
                    info_url, api_key=_get_admin_token()
                )
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco worldlayers endpoint: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco worldlayers unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_ecoregion_markdown(payload)),
                    TextContent(type="text", text=json.dumps(payload)),
                ],
            )

        if name == "get_species":
            species_arg = (arguments or {}).get("name") or ""
            species_id = _resolve_species_id(species_arg)
            try:
                species_payload_obj = await species_mod.build_species_payload(species_id)
            except httpx.HTTPError as e:
                err_payload = {"view": "error", "message": f"Could not fetch species: {e}"}
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Species fetch failed:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            species_payload = species_payload_obj.to_dict()
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_species_markdown(species_payload)),
                    TextContent(type="text", text=json.dumps(species_payload)),
                ],
            )

        if name == "get_government":
            server_arg = arguments.get("server") if arguments else None
            try:
                raw_gov = await fetch_eco_government(server_arg)
            except httpx.HTTPError as e:
                err_payload = {"view": "error", "message": f"Could not reach Eco server: {e}"}
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco server unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            gov_payload = to_government_payload(
                raw_gov, fetched_at_iso=datetime.now(UTC).isoformat()
            )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_government_markdown(gov_payload)),
                    TextContent(type="text", text=json.dumps(gov_payload)),
                ],
            )

        if name == "get_climate":
            server_arg = arguments.get("server") if arguments else None
            try:
                info = await fetch_eco_info(server_arg)
            except httpx.HTTPError as e:
                err_payload = {"view": "error", "message": f"Could not reach Eco server: {e}"}
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco server unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            # /info already gives DaysRunning; fall back to TimeSinceStart for
            # bootstrap servers that haven't ticked the daily counter yet.
            days_elapsed = int(info.get("DaysRunning") or 0)
            if days_elapsed <= 0:
                tss = info.get("TimeSinceStart")
                try:
                    days_elapsed = max(1, int(float(tss) / 3600.0))
                except (TypeError, ValueError):
                    days_elapsed = 1
            admin_token = os.environ.get("ECO_ADMIN_TOKEN") or _get_admin_token()
            default_admin_base = DEFAULT_ECO_INFO_URL.rsplit("/info", 1)[0]
            snapshot = await climate_mod.fetch_climate(
                server_arg,
                info=info,
                days_elapsed=days_elapsed,
                admin_token=admin_token,
                default_admin_base=default_admin_base,
            )
            payload = climate_mod.compute_climate_payload(snapshot)
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_climate_markdown(payload)),
                    TextContent(type="text", text=json.dumps(payload, default=str)),
                ],
            )

        if name == "get_currency":
            server_arg = arguments.get("server") if arguments else None
            currency_arg = (arguments.get("currency") if arguments else None) or None
            try:
                info = await fetch_eco_info(server_arg)
            except httpx.HTTPError as e:
                err_payload = {"view": "error", "message": f"Could not reach Eco server: {e}"}
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco server unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            days_elapsed = int(info.get("DaysRunning") or 0)
            if days_elapsed <= 0:
                tss = info.get("TimeSinceStart")
                try:
                    days_elapsed = max(1, int(float(tss) / 3600.0))
                except (TypeError, ValueError):
                    days_elapsed = 1
            admin_token = os.environ.get("ECO_ADMIN_TOKEN") or _get_admin_token()
            default_admin_base = DEFAULT_ECO_INFO_URL.rsplit("/info", 1)[0]
            currency_snapshot = await currency_mod.fetch_currency(
                server_arg,
                info=info,
                days_elapsed=days_elapsed,
                admin_token=admin_token,
                default_admin_base=default_admin_base,
            )
            payload = currency_mod.compute_currency_payload(
                currency_snapshot, currency=currency_arg
            )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_currency_markdown(payload)),
                    TextContent(type="text", text=json.dumps(payload, default=str)),
                ],
            )

        if name == "fair_price":
            item = arguments.get("item") if arguments else None
            cycle_id = arguments.get("cycle_id") if arguments else None
            server_arg = arguments.get("server") if arguments else None
            ref = await _in_game_reference_for(item, server_arg)
            result = await fair_price_mod.fetch_fair_price(
                item,
                cycle_id=cycle_id,
                in_game_median=ref.median if ref else None,
                in_game_currency=ref.currency if ref else None,
                in_game_trend=ref.trend if ref else None,
            )
            payload = fair_price_mod.to_payload(result)
            return CallToolResult(
                content=[
                    TextContent(type="text", text=result.narrative),
                    TextContent(type="text", text=json.dumps(payload)),
                ],
                # Fair-price failures are handled empty states carried in the
                # typed payload. They must remain successful at the transport
                # layer so both REST pages and MCP clients can render them.
                isError=False,
            )

        if name == "get_market":
            server_arg = arguments.get("server") if arguments else None
            item_arg = (arguments.get("item") if arguments else None) or None
            currency_arg = (arguments.get("currency") if arguments else None) or None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                intel = await market_mod.fetch_market(
                    base_url=server_arg,
                    api_key=api_key,
                    item=item_arg,
                    currency=currency_arg,
                )
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=market_mod.market_markdown(intel)),
                    TextContent(type="text", text=json.dumps(intel.to_dict(), default=str)),
                ],
            )

        if name == "find_trade":
            server_arg = arguments.get("server") if arguments else None
            item_arg = (arguments.get("item") if arguments else None) or None
            currency_arg = (arguments.get("currency") if arguments else None) or None
            api_key = os.environ.get(ADMIN_API_KEY_ENV) or _get_admin_token()
            try:
                report = await fetch_logistics(
                    base_url=server_arg,
                    api_key=api_key,
                    item=item_arg,
                    currency=currency_arg,
                )
            except httpx.HTTPError as e:
                err_payload = {
                    "view": "error",
                    "message": f"Could not reach Eco exporter: {e}",
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=f"**Eco exporter unreachable:** {e}"),
                        TextContent(type="text", text=json.dumps(err_payload)),
                    ],
                    isError=True,
                )
            return CallToolResult(
                content=[
                    TextContent(type="text", text=logistics_markdown(report)),
                    TextContent(type="text", text=json.dumps(report.to_dict(), default=str)),
                ],
            )

        if name not in ("get_server_status", "get_milestones"):
            raise ValueError(f"Unknown tool: {name}")

        server_arg = arguments.get("server") if arguments else None
        try:
            raw = await fetch_eco_info(server_arg)
        except httpx.HTTPError as e:
            err_payload = {"view": "error", "message": f"Could not reach Eco server: {e}"}
            return CallToolResult(
                content=[
                    TextContent(type="text", text=f"**Eco server unreachable:** {e}"),
                    TextContent(type="text", text=json.dumps(err_payload)),
                ],
                isError=True,
            )

        raw["_fetchedAtISO"] = datetime.now(UTC).isoformat()

        if name == "get_milestones":
            milestones_payload = build_milestones_payload(raw)
            return CallToolResult(
                content=[
                    TextContent(type="text", text=_format_milestones_markdown(milestones_payload)),
                    TextContent(type="text", text=json.dumps(milestones_payload)),
                ],
            )

        payload = to_payload(raw)
        return CallToolResult(
            content=[
                TextContent(type="text", text=_format_markdown(payload)),
                TextContent(type="text", text=json.dumps(payload)),
            ],
        )

    wave1_routes.register_wave1_routes(dual_routes, _dispatch_call_tool)
    wave2_routes.register_wave2_routes(dual_routes, _dispatch_call_tool)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        if dual_routes.has_tool(name):
            return await dual_routes.call_mcp(name, arguments)
        result = await _dispatch_call_tool(name, arguments)
        return result

    return instrument_mcp_server(server)


def build_initialization_options(server: Server) -> InitializationOptions:
    return InitializationOptions(
        server_name="eco-mcp-app",
        server_version="0.1.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
        # Stdio parity with the Server-object values the HTTP transport reads.
        website_url="https://eco-app.coilysiren.me",
        icons=[_eco_icon()],
    )


async def serve() -> None:
    """Stdio transport — the Claude Desktop entry point used by __main__.main()."""
    server = build_server()
    options = build_initialization_options(server)
    async with stdio_server() as (read, write):
        await server.run(read, write, options)
