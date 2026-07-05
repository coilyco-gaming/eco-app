"""Social / chat surface — activity, chat volume, reputation, redacted samples.

The action exporter ships the *social* actions alongside the economic ones, so
no new C# mod is needed (eco-app#63, survey #7). This module streams four of
them and folds them into one card:

    - ChatSent           full chat log (author, channel/tag, message body, time)
    - Play               play / activity ticks (who was active, when)
    - FirstLogin         new arrivals (a citizen's first-ever login)
    - ReputationTransfer  who reps whom, and by how much

Chat is **player-authored content**, so redaction is load-bearing here, not a
nicety. The public path treats names the way the outside-in public MCP does:

    * Player names are replaced by a stable, non-reversible **handle**
      (``player-<hash>``) — same identity → same handle within a run, so the
      reputation graph and top-chatter ranks stay correlatable without
      disclosing who anyone is.
    * Message bodies are **scrubbed** of every known player name (each replaced
      by that player's handle), so a real name never leaks inside chat text
      either.

Names-in-the-clear is an **operator-gated** mode, default-deny: a caller must
both pass ``reveal_names=true`` *and* the deploy must set
``ECO_SOCIAL_ALLOW_NAMES`` (mirrors the /admin redaction's ``raw`` deny in
``admin/redaction.py``). The public web data plane (``/preview/social.json``)
never opts in, so it is always redacted.

Design cribs the trades ledger (eco-app#6): streamed CSV via
``crafting._stream_csv_rows``, defensive header-keyed parsing with
``crafting._corrected_index`` absorbing the undeclared extra column (#5),
numeric ids joined to names via the jobs mod's ``/api/v1/citizens`` surface,
and ``Time`` → in-game day via the species ``seconds / 86400`` convention.

Column names for the social actions were not capturable live from this
container (the exporter is admin-gated and no key is mounted here), so every
field is picked from a **candidate list** of plausible header names and the
parser degrades gracefully when a column is absent — a warning is recorded
rather than a crash. The live column shapes want confirming against a real
capture; see the follow-up issue referenced in ``docs/FEATURES.md``.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx
from cachetools import TTLCache

from .crafting import (
    _INT_RE,
    _NONSENSE_KEY_RE,
    _corrected_index,
    _normalize_admin_base,
    _now_iso,
    _stream_csv_rows,
    fetch_citizen_name_map,
)

# All four actions share the `/api/v1/exporter/actions` endpoint shape.
CHAT_ACTION = "ChatSent"
PLAY_ACTION = "Play"
FIRST_LOGIN_ACTION = "FirstLogin"
REPUTATION_ACTION = "ReputationTransfer"
SOCIAL_ACTION_TYPES = (CHAT_ACTION, PLAY_ACTION, FIRST_LOGIN_ACTION, REPUTATION_ACTION)

DEFAULT_CACHE_TTL_S = float(os.environ.get("ECO_SOCIAL_CACHE_TTL", "60"))

# Per-action safety valve, same rationale as crafting / trades: 500k rows is
# ~50 MB of CSV, well past the late-cycle estimate and still sub-second to fold.
MAX_ROWS_PER_ACTION = int(os.environ.get("ECO_SOCIAL_MAX_ROWS", "500000"))

# How many recent chat messages ship as redacted samples. The card + SPA want a
# feel for the room, not the whole log; newest wins the cap.
MAX_CHAT_SAMPLES = int(os.environ.get("ECO_SOCIAL_CHAT_SAMPLES", "40"))

# How many new arrivals (FirstLogin) ship in the payload, newest first.
MAX_NEW_ARRIVALS = int(os.environ.get("ECO_SOCIAL_ARRIVALS", "60"))

# In-game day length in real seconds — the species population CSV convention
# (`Time / 86400`), matching the trades ledger's day index.
SECONDS_PER_DAY = 86400.0

# Env flag that lifts the names-in-the-clear DENY. Absent/false → redacted even
# when a caller asks for names (mirrors admin/redaction.RAW_ALLOW_ENV).
NAMES_ALLOW_ENV = "ECO_SOCIAL_ALLOW_NAMES"

# --- Column candidate lists ------------------------------------------------
# The exporter's exact headers for the social actions were not capturable from
# this container. We pick each field from a candidate list so a header drift
# (or a differently-named column across Eco versions) still lands. `pick` tries
# them left-to-right and takes the first non-empty cell.
_CHAT_AUTHOR = ("Citizen", "Player", "Sender", "User", "AuthorCitizen")
_CHAT_MESSAGE = ("Message", "Text", "ChatText", "Content", "Body")
_CHAT_CHANNEL = ("Tag", "Channel", "ChatTag", "Category", "ChannelName")
_ACTIVITY_CITIZEN = ("Citizen", "Player", "User")
_REP_GIVER = ("Citizen", "Giver", "GiverCitizen", "FromCitizen", "Sender", "Player")
_REP_RECEIVER = (
    "ReceiverCitizen",
    "Receiver",
    "TargetCitizen",
    "Target",
    "ToCitizen",
    "ReceiverPlayer",
)
_REP_AMOUNT = ("Amount", "Reputation", "ReputationAmount", "Value", "Delta")

_social_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=64, ttl=DEFAULT_CACHE_TTL_S)


def names_allowed() -> bool:
    """True when the operator has explicitly opted into names-in-the-clear."""
    return (os.environ.get(NAMES_ALLOW_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def effective_show_names(reveal_names: bool) -> bool:
    """Names show only when the caller asks *and* the deploy allows it.

    Default-deny: a public caller (or a caller on a deploy that hasn't set
    ``ECO_SOCIAL_ALLOW_NAMES``) always gets the redacted surface.
    """
    return bool(reveal_names) and names_allowed()


def hash_handle(identity: str) -> str:
    """Stable, non-reversible handle for a player identity at the public level.

    Same input → same handle within (and across) runs, so two references to one
    player stay correlatable without disclosing who they are. Deliberately short
    and ASCII (public-safe, grep-friendly), mirroring ``admin/redaction.hash_name``.
    """
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return f"player-{digest}"


def _cache_key(base_url: str, api_key: str | None, show_names: bool) -> str:
    token = hashlib.sha256((api_key or "").encode()).hexdigest()[:12]
    return f"{base_url}|{token}|{int(show_names)}"


@dataclass
class _ChatMsg:
    """One chat line before id→label resolution. Author stays a numeric id."""

    time_s: float
    day: float
    author_id: str
    channel: str
    message: str


@dataclass
class _RepEdge:
    """One reputation transfer before id→label resolution."""

    time_s: float
    day: float
    giver_id: str
    receiver_id: str
    amount: float


@dataclass
class _ActivityEvent:
    """One Play / FirstLogin tick before id→label resolution."""

    time_s: float
    day: float
    citizen_id: str
    kind: str  # "play" | "firstlogin"


@dataclass
class SocialSurface:
    """Redaction-aware social surface + derived aggregates. JSON-serializable.

    ``redacted`` is True whenever names are hashed (the public default). When an
    operator lifts the gate, names/messages are in the clear and ``redacted`` is
    False — the flag is the honest label the UI reads, never a guess.
    """

    fetched_at_iso: str
    source_base_url: str
    redacted: bool = True
    per_type_counts: dict[str, int] = field(default_factory=dict)
    total_chat: int = 0
    total_reputation_transfers: int = 0
    total_first_logins: int = 0
    total_play_events: int = 0
    # Per in-game day series (day, count), ascending by day.
    chat_by_day: list[tuple[int, int]] = field(default_factory=list)
    play_by_day: list[tuple[int, int]] = field(default_factory=list)
    first_logins_by_day: list[tuple[int, int]] = field(default_factory=list)
    # (channel, message_count), heaviest first.
    chat_by_channel: list[tuple[str, int]] = field(default_factory=list)
    # (label, message_count), heaviest first — labels already redacted/resolved.
    top_chatters: list[tuple[str, int]] = field(default_factory=list)
    # New arrivals, newest first: {"label", "day"}.
    new_arrivals: list[dict[str, Any]] = field(default_factory=list)
    # Reputation graph edges: {"source", "target", "amount", "count"}.
    reputation_edges: list[dict[str, Any]] = field(default_factory=list)
    # (label, amount) heaviest first — reputation given / received.
    top_reputation_givers: list[tuple[str, float]] = field(default_factory=list)
    top_reputation_receivers: list[tuple[str, float]] = field(default_factory=list)
    # Redacted recent chat samples, newest first: {"day","author","channel","message"}.
    recent_chat: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetchedAtISO": self.fetched_at_iso,
            "sourceBaseUrl": self.source_base_url,
            "redacted": self.redacted,
            "perTypeCounts": dict(self.per_type_counts),
            "totalChat": self.total_chat,
            "totalReputationTransfers": self.total_reputation_transfers,
            "totalFirstLogins": self.total_first_logins,
            "totalPlayEvents": self.total_play_events,
            "chatByDay": [[d, c] for d, c in self.chat_by_day],
            "playByDay": [[d, c] for d, c in self.play_by_day],
            "firstLoginsByDay": [[d, c] for d, c in self.first_logins_by_day],
            "chatByChannel": [[n, c] for n, c in self.chat_by_channel],
            "topChatters": [[n, c] for n, c in self.top_chatters],
            "newArrivals": list(self.new_arrivals),
            "reputationEdges": list(self.reputation_edges),
            "topReputationGivers": [[n, a] for n, a in self.top_reputation_givers],
            "topReputationReceivers": [[n, a] for n, a in self.top_reputation_receivers],
            "recentChat": list(self.recent_chat),
            "warnings": list(self.warnings),
        }


def _mk_pick(header: list[str]) -> Any:
    """Build a header-keyed `pick(row, idx, *candidates)` closure.

    Same shape as the trades / crafting picker: try each candidate column, take
    the first non-empty cell after `_corrected_index` realignment.
    """
    col = {name: i for i, name in enumerate(header)}

    def pick(row: list[str], idx: list[int], *candidates: str) -> str:
        for c in candidates:
            j = col.get(c)
            if j is not None and idx[j] < len(row):
                v = row[idx[j]].strip()
                if v:
                    return v
        return ""

    return pick


def _clean_id(value: str) -> str:
    """Keep only cells that are plausible party columns (bare ids or names).

    Misaligned rows sometimes push a position triple / bare number where a party
    belongs; those are dropped rather than rendered (crafting's fold-time guard,
    #5). A numeric id passes (it's resolved later); a real name passes; a
    position/float artifact is blanked.
    """
    v = (value or "").strip()
    if not v:
        return ""
    if _INT_RE.match(v):
        return v
    if _NONSENSE_KEY_RE.match(v):
        return ""
    return v


def parse_chat_rows(
    rows: Iterable[list[str]],
    surface: SocialSurface,
    chat: list[_ChatMsg],
    max_rows: int = MAX_ROWS_PER_ACTION,
) -> int:
    """Fold ChatSent CSV rows into `chat` (raw author ids). Returns rows consumed."""
    it = iter(rows)
    try:
        header = next(it)
    except StopIteration:
        return 0
    pick = _mk_pick(header)
    have_message = any(c in header for c in _CHAT_MESSAGE)
    if not have_message and CHAT_ACTION not in {w.split(":")[0] for w in surface.warnings}:
        surface.warnings.append(
            f"{CHAT_ACTION}: no recognized message column "
            f"(tried {', '.join(_CHAT_MESSAGE)}); chat bodies unavailable"
        )

    consumed = 0
    for row in it:
        if not row:
            continue
        if consumed >= max_rows:
            surface.warnings.append(
                f"{CHAT_ACTION}: truncated at {max_rows} rows (late-cycle size cap)"
            )
            break
        idx = _corrected_index(header, row)
        try:
            time_s = float(pick(row, idx, "Time") or "0")
        except ValueError:
            time_s = 0.0
        chat.append(
            _ChatMsg(
                time_s=time_s,
                day=time_s / SECONDS_PER_DAY,
                author_id=_clean_id(pick(row, idx, *_CHAT_AUTHOR)),
                channel=pick(row, idx, *_CHAT_CHANNEL) or "(general)",
                message=pick(row, idx, *_CHAT_MESSAGE),
            )
        )
        consumed += 1

    surface.per_type_counts[CHAT_ACTION] = surface.per_type_counts.get(CHAT_ACTION, 0) + consumed
    return consumed


def parse_reputation_rows(
    rows: Iterable[list[str]],
    surface: SocialSurface,
    edges: list[_RepEdge],
    max_rows: int = MAX_ROWS_PER_ACTION,
) -> int:
    """Fold ReputationTransfer rows into `edges` (raw ids). Returns rows consumed."""
    it = iter(rows)
    try:
        header = next(it)
    except StopIteration:
        return 0
    pick = _mk_pick(header)

    consumed = 0
    for row in it:
        if not row:
            continue
        if consumed >= max_rows:
            surface.warnings.append(
                f"{REPUTATION_ACTION}: truncated at {max_rows} rows (late-cycle size cap)"
            )
            break
        idx = _corrected_index(header, row)
        try:
            time_s = float(pick(row, idx, "Time") or "0")
        except ValueError:
            time_s = 0.0
        try:
            amount = float(pick(row, idx, *_REP_AMOUNT) or "0")
        except ValueError:
            amount = 0.0
        edges.append(
            _RepEdge(
                time_s=time_s,
                day=time_s / SECONDS_PER_DAY,
                giver_id=_clean_id(pick(row, idx, *_REP_GIVER)),
                receiver_id=_clean_id(pick(row, idx, *_REP_RECEIVER)),
                amount=amount,
            )
        )
        consumed += 1

    surface.per_type_counts[REPUTATION_ACTION] = (
        surface.per_type_counts.get(REPUTATION_ACTION, 0) + consumed
    )
    return consumed


def parse_activity_rows(
    action_name: str,
    rows: Iterable[list[str]],
    surface: SocialSurface,
    events: list[_ActivityEvent],
    max_rows: int = MAX_ROWS_PER_ACTION,
) -> int:
    """Fold Play / FirstLogin rows into `events` (raw ids). Returns rows consumed."""
    it = iter(rows)
    try:
        header = next(it)
    except StopIteration:
        return 0
    pick = _mk_pick(header)
    kind = "firstlogin" if action_name == FIRST_LOGIN_ACTION else "play"

    consumed = 0
    for row in it:
        if not row:
            continue
        if consumed >= max_rows:
            surface.warnings.append(
                f"{action_name}: truncated at {max_rows} rows (late-cycle size cap)"
            )
            break
        idx = _corrected_index(header, row)
        try:
            time_s = float(pick(row, idx, "Time") or "0")
        except ValueError:
            time_s = 0.0
        events.append(
            _ActivityEvent(
                time_s=time_s,
                day=time_s / SECONDS_PER_DAY,
                citizen_id=_clean_id(pick(row, idx, *_ACTIVITY_CITIZEN)),
                kind=kind,
            )
        )
        consumed += 1

    surface.per_type_counts[action_name] = surface.per_type_counts.get(action_name, 0) + consumed
    return consumed


class _Redactor:
    """Turns numeric ids and message bodies into their public-safe form.

    In redacted mode every party label is a ``player-<hash>`` handle and every
    known player name inside a message is swapped for that player's handle, so
    neither a raw name nor a raw body escapes. In names-shown mode it is a
    pass-through (real names, unscrubbed bodies).
    """

    def __init__(self, name_map: dict[str, str], show_names: bool) -> None:
        self.name_map = name_map
        self.show_names = show_names
        # Build the message-scrub table once: known player name → handle, longest
        # names first so a name that contains a shorter one is replaced whole.
        self._scrub: list[tuple[re.Pattern[str], str]] = []
        if not show_names:
            names = sorted({n for n in name_map.values() if n}, key=len, reverse=True)
            for name in names:
                self._scrub.append((re.compile(re.escape(name), re.IGNORECASE), hash_handle(name)))

    def label(self, cid: str) -> str:
        """Resolve a numeric id to a display label, redacted unless names shown."""
        if not cid:
            return ""
        if not _INT_RE.match(cid):
            # Already a name / artifact left verbatim — redact it too when hiding.
            return cid if self.show_names else hash_handle(cid)
        identity = self.name_map.get(cid) or f"Citizen #{cid}"
        return identity if self.show_names else hash_handle(identity)

    def message(self, body: str) -> str:
        """Return a message body with known player names scrubbed to handles."""
        if self.show_names or not body:
            return body
        out = body
        for pat, handle in self._scrub:
            out = pat.sub(handle, out)
        return out


def build_surface(
    surface: SocialSurface,
    chat: list[_ChatMsg],
    edges: list[_RepEdge],
    activity: list[_ActivityEvent],
    name_map: dict[str, str],
    show_names: bool,
) -> None:
    """Resolve ids, apply redaction, and roll the parsed rows into aggregates."""
    red = _Redactor(name_map, show_names)
    surface.redacted = not show_names

    # --- Chat ---
    surface.total_chat = len(chat)
    chat_day: dict[int, int] = defaultdict(int)
    chat_channel: dict[str, int] = defaultdict(int)
    chatter: dict[str, int] = defaultdict(int)
    for m in chat:
        chat_day[int(m.day)] += 1
        chat_channel[m.channel] += 1
        if m.author_id:
            chatter[red.label(m.author_id)] += 1
    surface.chat_by_day = sorted(chat_day.items())
    surface.chat_by_channel = sorted(chat_channel.items(), key=lambda kv: kv[1], reverse=True)
    surface.top_chatters = sorted(chatter.items(), key=lambda kv: kv[1], reverse=True)
    # Newest chat first for the sample feed; body scrubbed, author handled.
    newest_chat = sorted(chat, key=lambda m: m.time_s, reverse=True)[:MAX_CHAT_SAMPLES]
    surface.recent_chat = [
        {
            "day": int(m.day),
            "author": red.label(m.author_id) or "—",
            "channel": m.channel,
            "message": red.message(m.message),
        }
        for m in newest_chat
    ]

    # --- Activity: play + first logins ---
    play_day: dict[int, int] = defaultdict(int)
    login_day: dict[int, int] = defaultdict(int)
    for e in activity:
        if e.kind == "firstlogin":
            login_day[int(e.day)] += 1
        else:
            play_day[int(e.day)] += 1
    surface.total_play_events = sum(1 for e in activity if e.kind == "play")
    surface.total_first_logins = sum(1 for e in activity if e.kind == "firstlogin")
    surface.play_by_day = sorted(play_day.items())
    surface.first_logins_by_day = sorted(login_day.items())
    arrivals = sorted(
        (e for e in activity if e.kind == "firstlogin"),
        key=lambda e: e.time_s,
        reverse=True,
    )[:MAX_NEW_ARRIVALS]
    surface.new_arrivals = [
        {"label": red.label(e.citizen_id) or "—", "day": int(e.day)} for e in arrivals
    ]

    # --- Reputation graph ---
    surface.total_reputation_transfers = len(edges)
    edge_amt: dict[tuple[str, str], float] = defaultdict(float)
    edge_cnt: dict[tuple[str, str], int] = defaultdict(int)
    given: dict[str, float] = defaultdict(float)
    received: dict[str, float] = defaultdict(float)
    for r in edges:
        g = red.label(r.giver_id)
        t = red.label(r.receiver_id)
        if not g or not t:
            continue
        edge_amt[(g, t)] += r.amount
        edge_cnt[(g, t)] += 1
        given[g] += r.amount
        received[t] += r.amount
    surface.reputation_edges = sorted(
        (
            {"source": s, "target": tgt, "amount": edge_amt[(s, tgt)], "count": edge_cnt[(s, tgt)]}
            for (s, tgt) in edge_amt
        ),
        key=lambda e: abs(e["amount"]),
        reverse=True,
    )
    surface.top_reputation_givers = sorted(given.items(), key=lambda kv: kv[1], reverse=True)
    surface.top_reputation_receivers = sorted(received.items(), key=lambda kv: kv[1], reverse=True)


async def fetch_social(
    base_url: str | None = None,
    api_key: str | None = None,
    reveal_names: bool = False,
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
    client: httpx.AsyncClient | None = None,
) -> SocialSurface:
    """Stream the four social action CSVs and fold them into one surface.

    ``reveal_names`` only takes effect when the deploy has set
    ``ECO_SOCIAL_ALLOW_NAMES`` (default-deny) — otherwise the surface is
    redacted regardless. ``client`` is injectable so tests can hand in a
    pre-stubbed httpx client; when omitted we build one with a 30 s timeout
    (late-cycle CSVs take a beat).
    """
    show_names = effective_show_names(reveal_names)
    normalized = _normalize_admin_base(base_url)
    key = _cache_key(normalized, api_key, show_names)
    if cache_ttl_s > 0:
        cached = _social_cache.get(key)
        if cached is not None:
            return _surface_from_dict(cached)

    surface = SocialSurface(fetched_at_iso=_now_iso(), source_base_url=normalized)
    headers = {"X-API-Key": api_key} if api_key else {}
    chat: list[_ChatMsg] = []
    edges: list[_RepEdge] = []
    activity: list[_ActivityEvent] = []

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    try:
        for action in SOCIAL_ACTION_TYPES:
            url = f"{normalized}/api/v1/exporter/actions?actionName={action}"
            try:
                await _stream_one_action(http, url, headers, action, surface, chat, edges, activity)
                surface.per_type_counts.setdefault(action, 0)
            except httpx.HTTPStatusError as e:
                surface.warnings.append(f"{action}: HTTP {e.response.status_code}")
            except httpx.HTTPError as e:
                surface.warnings.append(f"{action}: {type(e).__name__}: {e}")

        # Join numeric ids to names once every action has folded. Skipped when
        # nothing referenced a party (keeps a keyless / empty server cheap).
        name_map: dict[str, str] = {}
        if chat or edges or activity:
            name_map = await fetch_citizen_name_map(http, normalized, headers, surface.warnings)
    finally:
        if owns_client:
            await http.aclose()

    build_surface(surface, chat, edges, activity, name_map, show_names)

    if cache_ttl_s > 0:
        _social_cache[key] = surface.to_dict()
    return surface


async def _stream_one_action(
    http: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    action: str,
    surface: SocialSurface,
    chat: list[_ChatMsg],
    edges: list[_RepEdge],
    activity: list[_ActivityEvent],
) -> None:
    """Stream one action CSV in batches and dispatch to its parser.

    Batched so we never hold more than ~1k rows in Python-land at once, passing a
    shrinking `remaining` budget so the per-action cap holds across batches
    (identical spine to crafting.fetch_atlas / trades.fetch_parsed_trades).
    """
    remaining = MAX_ROWS_PER_ACTION
    header: list[str] | None = None
    batch: list[list[str]] = []

    def _fold(rows: list[list[str]], budget: int) -> int:
        if action == CHAT_ACTION:
            return parse_chat_rows(rows, surface, chat, max_rows=budget)
        if action == REPUTATION_ACTION:
            return parse_reputation_rows(rows, surface, edges, max_rows=budget)
        return parse_activity_rows(action, rows, surface, activity, max_rows=budget)

    async for row in _stream_csv_rows(http, url, headers):
        if header is None:
            header = row
            batch = [row]
            continue
        batch.append(row)
        if len(batch) >= 1024:
            consumed = _fold(batch, remaining)
            remaining -= consumed
            if remaining <= 0:
                return
            batch = [header]
    if header is not None and len(batch) > 1 and remaining > 0:
        _fold(batch, remaining)


def _surface_from_dict(data: dict[str, Any]) -> SocialSurface:
    """Rehydrate a cached surface dict back into a SocialSurface."""
    return SocialSurface(
        fetched_at_iso=data["fetchedAtISO"],
        source_base_url=data["sourceBaseUrl"],
        redacted=bool(data.get("redacted", True)),
        per_type_counts=dict(data.get("perTypeCounts", {})),
        total_chat=int(data.get("totalChat", 0)),
        total_reputation_transfers=int(data.get("totalReputationTransfers", 0)),
        total_first_logins=int(data.get("totalFirstLogins", 0)),
        total_play_events=int(data.get("totalPlayEvents", 0)),
        chat_by_day=[(int(d), int(c)) for d, c in data.get("chatByDay", [])],
        play_by_day=[(int(d), int(c)) for d, c in data.get("playByDay", [])],
        first_logins_by_day=[(int(d), int(c)) for d, c in data.get("firstLoginsByDay", [])],
        chat_by_channel=[(n, int(c)) for n, c in data.get("chatByChannel", [])],
        top_chatters=[(n, int(c)) for n, c in data.get("topChatters", [])],
        new_arrivals=list(data.get("newArrivals", [])),
        reputation_edges=list(data.get("reputationEdges", [])),
        top_reputation_givers=[(n, float(a)) for n, a in data.get("topReputationGivers", [])],
        top_reputation_receivers=[(n, float(a)) for n, a in data.get("topReputationReceivers", [])],
        recent_chat=list(data.get("recentChat", [])),
        warnings=list(data.get("warnings", [])),
    )


def social_template_context(
    surface: SocialSurface,
    top_channels: int = 8,
    top_chatters: int = 8,
    top_rep: int = 8,
    top_edges: int = 12,
    recent: int = 12,
) -> dict[str, Any]:
    """Shape for the MCP `_meta.ui` Jinja card. Product UX is the SPA — this
    card stays a compact, redaction-aware summary."""
    channels = surface.chat_by_channel[:top_channels]
    max_channel = max((c for _, c in channels), default=0) or 1
    chatters = surface.top_chatters[:top_chatters]
    max_chatter = max((c for _, c in chatters), default=0) or 1

    def _rep_rows(rows: list[tuple[str, float]]) -> list[dict[str, Any]]:
        top = rows[:top_rep]
        max_amt = max((abs(a) for _, a in top), default=0.0) or 1.0
        return [{"name": n, "amount": a, "pct": (abs(a) / max_amt) * 100.0} for n, a in top]

    empty = (
        surface.total_chat == 0
        and surface.total_reputation_transfers == 0
        and surface.total_first_logins == 0
        and surface.total_play_events == 0
    )
    return {
        "empty": empty,
        "redacted": surface.redacted,
        "fetched_at_iso": surface.fetched_at_iso,
        "source_base_url": surface.source_base_url,
        "total_chat": surface.total_chat,
        "total_reputation_transfers": surface.total_reputation_transfers,
        "total_first_logins": surface.total_first_logins,
        "total_play_events": surface.total_play_events,
        "per_type_counts": [(n, c) for n, c in surface.per_type_counts.items() if c],
        "channels": [
            {"name": n, "count": c, "pct": (c / max_channel) * 100.0} for n, c in channels
        ],
        "chatters": [
            {"name": n, "count": c, "pct": (c / max_chatter) * 100.0} for n, c in chatters
        ],
        "rep_givers": _rep_rows(surface.top_reputation_givers),
        "rep_receivers": _rep_rows(surface.top_reputation_receivers),
        "rep_edges": surface.reputation_edges[:top_edges],
        "new_arrivals": surface.new_arrivals[:recent],
        "recent_chat": surface.recent_chat[:recent],
        "warnings": list(surface.warnings),
    }


def social_markdown(surface: SocialSurface) -> str:
    """Compact markdown summary for MCP hosts without the SPA / card."""
    if (
        surface.total_chat == 0
        and surface.total_reputation_transfers == 0
        and surface.total_first_logins == 0
        and surface.total_play_events == 0
    ):
        return f"**Social** — no social activity recorded yet ({surface.source_base_url})."
    posture = "names redacted" if surface.redacted else "names shown (operator)"
    lines = [
        f"**Social** — {surface.total_chat:,} chat messages · "
        f"{surface.total_reputation_transfers:,} reputation transfers · "
        f"{surface.total_first_logins:,} new arrivals · _{posture}_ "
        f"(`{surface.source_base_url}`)",
        "",
    ]
    if surface.chat_by_channel:
        top = ", ".join(f"{c} ({n:,})" for c, n in surface.chat_by_channel[:5])
        lines.append(f"- Busiest channels: {top}")
    if surface.top_chatters:
        top = ", ".join(f"{name} ({n:,})" for name, n in surface.top_chatters[:5])
        lines.append(f"- Top chatters: {top}")
    if surface.top_reputation_receivers:
        top = ", ".join(
            f"{name} ({amt:,.0f})" for name, amt in surface.top_reputation_receivers[:5]
        )
        lines.append(f"- Most-repped: {top}")
    if surface.new_arrivals:
        lines.append(f"- New arrivals: {len(surface.new_arrivals)} recent (from FirstLogin)")
    for w in surface.warnings:
        lines.append(f"- ⚠ {w}")
    return "\n".join(lines)
