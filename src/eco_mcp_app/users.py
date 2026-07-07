"""Per-user dossier — every field the exporters carry about one player.

Backs the hidden ``/users/<hex>`` SPA page (eco-app#80): given a username,
pivot every per-user surface the app can reach into a single dossier — jobs
skills + lastSeen, trades as buyer/seller/owner, crafting output, civics
(votes/office/demographics/settlements), currency holdings, progression
trajectory, and world shaping/pollution. Pure over the already-fetched tool
payloads (each surface's ``to_dict()`` shape, or ``None`` when that fetch
failed), so it unit-tests without a live server; the concurrent fan-out and
the fetch itself live in ``http_app.py``.

The all-users listing that once sat alongside this (``build_roster`` +
``/preview/users.json`` + the SPA ``/users`` index) was removed in eco-app#93;
only the single-user dossier remains.

General rule (eco-app#80): a list pivoted by user lists **every** user, never a
truncated top-N. The aggregate lists this reads — trades ``topBuyers`` /
``topSellers``, crafting ``byCitizen``, civics ``topVoters``, world
``byCitizen`` / ``byPolluter`` — are built complete server-side. The one
source that capped its per-user list, world's ``byCitizen`` / ``byPolluter``
(was top-25), was de-capped in ``world.finalize`` for this feature. Where an
upstream surface still caps a per-user slice — currency top-holders (15 per
currency) and progression citizen cards (busiest 80) — the dossier records a
warning rather than silently implying completeness. Fully de-capping those two
is tracked as a follow-up.
"""

from __future__ import annotations

from typing import Any

# Which fetched surfaces feed the dossier. Keys match the `sources` dict the
# endpoint hands in; each value is that surface's `to_dict()` payload or None.
SOURCE_KEYS: tuple[str, ...] = (
    "jobs",
    "trades",
    "crafting",
    "civics",
    "currency",
    "progression",
    "world",
)


def _pair_value(pairs: Any, name: str) -> float | int | None:
    """Return the value of the ``[name, value]`` entry matching ``name``.

    The aggregate leaderboards (topBuyers, byCitizen, topVoters, ...) are all
    lists of two-element ``[name, value]`` pairs. None when the user is absent.
    """
    for entry in pairs or []:
        if entry and len(entry) >= 2 and entry[0] == name:
            return entry[1]
    return None


def _jobs_section(jobs: Any, name: str) -> dict[str, Any] | None:
    """The player's current skills + lastSeen from the jobs surface.

    ``jobs`` is the pre-shaped list of ``{name, active, lastSeenISO,
    specialties}`` the endpoint builds from the jobs API rows.
    """
    for player in jobs or []:
        if player.get("name") == name:
            return {
                "active": bool(player.get("active")),
                "lastSeenISO": player.get("lastSeenISO"),
                "specialties": list(player.get("specialties") or []),
            }
    return None


def _trades_section(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """The player's trade footprint: spent as a buyer, earned as a seller, and
    every individual trade row they appear in (as buyer, seller, or owner)."""
    if not payload:
        return None
    spent = _pair_value(payload.get("topBuyers"), name)
    earned = _pair_value(payload.get("topSellers"), name)
    rows = [
        t
        for t in payload.get("trades") or []
        if name in (t.get("buyer"), t.get("seller"), t.get("shopOwner"))
    ]
    if spent is None and earned is None and not rows:
        return None
    return {
        "currencySpent": spent or 0,
        "currencyEarned": earned or 0,
        "trades": rows,
    }


def _crafting_section(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """The player's crafting output count (produced items observed)."""
    if not payload:
        return None
    events = _pair_value(payload.get("byCitizen"), name)
    if events is None:
        return None
    return {"events": events}


def _civics_section(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """The player's civic footprint: votes cast, elections proposed/won,
    demographic events, and settlements/homesteads founded."""
    if not payload:
        return None
    votes = _pair_value(payload.get("topVoters"), name) or 0
    elections = [
        {"subject": e.get("subject"), "day": e.get("day"), "role": "proposed"}
        for e in payload.get("recentElections") or []
        if e.get("proposer") == name
    ] + [
        {"subject": e.get("subject"), "day": e.get("day"), "role": "won"}
        for e in payload.get("recentOutcomes") or []
        if e.get("winner") == name
    ]
    demographics = [
        {"kind": e.get("kind"), "day": e.get("day"), "settlement": e.get("settlement")}
        for e in payload.get("recentDemographics") or []
        if e.get("name") == name
    ]
    settlements = [
        {"subject": e.get("subject"), "day": e.get("day"), "kind": e.get("kind")}
        for e in payload.get("recentSettlements") or []
        if e.get("founder") == name
    ]
    if not votes and not elections and not demographics and not settlements:
        return None
    return {
        "votesCast": votes,
        "elections": elections,
        "demographics": demographics,
        "settlements": settlements,
    }


def _currency_section(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """The player's currency holdings — balance per currency they hold.

    Reads the raw ``CurrencySnapshot.to_dict()`` shape (every currency carries
    its ``topHolders``), joining on the resolved ``holder`` name. Capped at
    ``ECO_CURRENCY_MAX_HOLDERS`` (default 15) per currency upstream.
    """
    if not payload:
        return None
    holdings = [
        {
            "currency": cur.get("name"),
            "balance": holder.get("balance"),
            "account": holder.get("account"),
        }
        for cur in payload.get("currencies") or []
        for holder in cur.get("topHolders") or []
        if holder.get("holder") == name
    ]
    if not holdings:
        return None
    return {"holdings": holdings}


def _progression_section(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """The player's skill-history trajectory (professions/specialties gained,
    level-up cadence, event timeline), plus their total level-ups."""
    if not payload:
        return None
    trajectory = next(
        (c for c in payload.get("citizens") or [] if c.get("name") == name),
        None,
    )
    level_ups = _pair_value(payload.get("topLevelers"), name)
    if trajectory is None and level_ups is None:
        return None
    section: dict[str, Any] = {"levelUpCount": level_ups or 0}
    if trajectory is not None:
        section["trajectory"] = trajectory
    return section


def _world_section(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """The player's world footprint: world-shaping events and pollution events."""
    if not payload:
        return None
    shaper = _pair_value(payload.get("byCitizen"), name)
    polluter = _pair_value(payload.get("byPolluter"), name)
    if shaper is None and polluter is None:
        return None
    return {"shaperEvents": shaper or 0, "pollutionEvents": polluter or 0}


# Per-source caps that survive upstream, so the dossier can flag when a user
# might be hidden by one rather than implying it saw everything.
_CAP_NOTES: dict[str, str] = {
    "currency": (
        "currency holdings list the top holders per currency "
        "(ECO_CURRENCY_MAX_HOLDERS, default 15); a lower-ranked holding may be omitted"
    ),
    "progression": (
        "progression keeps skill trajectories for the busiest citizens "
        "(ECO_PROGRESSION_MAX_CITIZENS, default 80); a quieter player shows level-up "
        "totals without a full timeline"
    ),
}


def build_user_dossier(username: str, sources: dict[str, Any]) -> dict[str, Any]:
    """Pivot every per-user surface for ``username`` into one dossier.

    ``sources`` maps each surface key in ``SOURCE_KEYS`` to its ``to_dict()``
    payload (``None`` when that fetch failed). Every section is best-effort:
    a section is ``None`` when the surface was unreachable or carries nothing
    for this user, so the page degrades panel-by-panel. ``available`` records
    which surfaces responded; ``warnings`` carries per-source cap notes.
    """
    sections = {
        "jobs": _jobs_section(sources.get("jobs"), username),
        "trades": _trades_section(sources.get("trades"), username),
        "crafting": _crafting_section(sources.get("crafting"), username),
        "civics": _civics_section(sources.get("civics"), username),
        "currency": _currency_section(sources.get("currency"), username),
        "progression": _progression_section(sources.get("progression"), username),
        "world": _world_section(sources.get("world"), username),
    }
    available = {key: sources.get(key) is not None for key in SOURCE_KEYS}
    warnings = [note for key, note in _CAP_NOTES.items() if sections.get(key) is not None]
    return {
        "username": username,
        "found": any(section is not None for section in sections.values()),
        "available": available,
        **sections,
        "warnings": warnings,
    }
