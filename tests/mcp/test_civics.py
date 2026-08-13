"""Tests for the civics & governance aggregator + tool wiring (eco-app#61).

Covers:
  - Folding civic action CSVs into events with the right actor / subject /
    day fields (header-keyed, seconds -> in-game day via /86400).
  - Turnout: Vote vs DidntVote counts, participation rate, most-active voters.
  - Demographics: citizens gained / lost, net, residency moves.
  - Settlements: founded + homesteads, founder resolved to a name.
  - Numeric actor ids joined to names via /api/v1/citizens; an id the join
    misses is reported as an id, never as a `Citizen #<id>` person, because
    some of those ids are election titles rather than people (eco-app#223).
  - Daily-count series folded into the trend map (seconds -> day x-axis).
  - Defensive realignment of a row carrying an undeclared extra column.
  - Missing-endpoint (401 / connect error) becomes a non-fatal warning.
  - Empty exporters produce a clean "no civic events" report.
  - The in-memory TTL cache is per (base, api-key) and hits within TTL.
  - Tool wiring returns two TextContent blocks and no widget (just-data per eco-app#87).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator

import httpx
import mcp.types as mt
import pytest
import respx

from eco_mcp_app import civics as civics_mod
from eco_mcp_app.civics import (
    SECONDS_PER_DAY,
    CivicsReport,
    _CivicEvent,
    build_report,
    civics_markdown,
    civics_template_context,
    fetch_civics,
    parse_civic_rows,
)
from eco_mcp_app.server import build_server

BASE = "http://eco.example.com:3001"
CITIZENS_URL = f"{BASE}/api/v1/citizens"


def _exporter_url(action: str) -> str:
    return f"{BASE}/api/v1/exporter/actions?actionName={action}"


def _series_url(name: str) -> str:
    end = max(civics_mod.SERIES_DAY_END, 1)
    return f"{BASE}/datasets/get?dataset={name}&dayStart=0&dayEnd={end}"


_CITIZENS_JSON = [
    {"id": 101, "name": "alice"},
    {"id": 102, "name": "bob"},
    {"id": 103, "name": "carol"},
]

# Aligned civic CSVs. The exact civic headers weren't captured live this cycle,
# so the module parses a generous candidate set header-keyed; these fixtures use
# the columns it looks for (Citizen, an election/settlement subject,
# ActionLocation, Count, Time).
_VOTE_CSV = (
    "Citizen,ElectionName,ActionLocation,Count,Time\n"
    '101,MayorRace,"1,2,3",1,300000\n'
    '101,SheriffRace,"1,2,3",1,290000\n'
    '102,MayorRace,"4,5,6",1,280000\n'
)
_DIDNTVOTE_CSV = 'Citizen,ElectionName,ActionLocation,Count,Time\n103,MayorRace,"7,8,9",1,270000\n'
_START_ELECTION_CSV = (
    'Citizen,ElectionName,ActionLocation,Count,Time\n101,MayorRace,"1,2,3",1,260000\n'
)
_WON_ELECTION_CSV = (
    'Citizen,ElectionName,ActionLocation,Count,Time\n101,MayorRace,"1,2,3",1,250000\n'
)
_BECOME_CITIZEN_CSV = (
    "Citizen,SettlementName,ActionLocation,Count,Time\n"
    '102,Rivertown,"4,5,6",1,240000\n'
    '103,Rivertown,"7,8,9",1,230000\n'
)
_LEAVE_CITIZENSHIP_CSV = (
    'Citizen,SettlementName,ActionLocation,Count,Time\n104,Rivertown,"1,1,1",1,220000\n'
)
_RESIDENCY_CSV = (
    'Citizen,SettlementName,ActionLocation,Count,Time\n102,Rivertown,"4,5,6",1,210000\n'
)
_SETTLEMENT_FOUNDED_CSV = (
    'Citizen,SettlementName,ActionLocation,Count,Time\n101,Rivertown,"1,2,3",1,200000\n'
)
_HOMESTEAD_CSV = 'Citizen,SettlementName,ActionLocation,Count,Time\n102,BobsFarm,"4,5,6",1,190000\n'

_CSV_BY_ACTION = {
    "Vote": _VOTE_CSV,
    "DidntVote": _DIDNTVOTE_CSV,
    "StartElection": _START_ELECTION_CSV,
    "WonElection": _WON_ELECTION_CSV,
    "BecomeCitizen": _BECOME_CITIZEN_CSV,
    "LeaveCitizenship": _LEAVE_CITIZENSHIP_CSV,
    "ResidencyChanged": _RESIDENCY_CSV,
    "SettlementFounded": _SETTLEMENT_FOUNDED_CSV,
    "StartHomestead": _HOMESTEAD_CSV,
}
_EMPTY_CSV = "Citizen,Name,ActionLocation,Count,Time\n"

_SERIES_BY_NAME = {
    "Vote": [
        {"Time": 0, "Value": 0},
        {"Time": 86400, "Value": 1},
        {"Time": 172800, "Value": 3},
    ],
    "BecomeCitizen": [
        {"Time": 86400, "Value": 1},
        {"Time": 172800, "Value": 2},
    ],
}


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    civics_mod._civics_cache.clear()
    yield
    civics_mod._civics_cache.clear()


def _rows(csv_text: str) -> list[list[str]]:
    return list(csv.reader(csv_text.splitlines()))


def _mock_full_server(
    router: respx.Router,
    csv_by_action: dict[str, str] | None = None,
    series_by_name: dict[str, list[dict[str, int]]] | None = None,
    status_by_action: dict[str, int] | None = None,
) -> None:
    """Register an exact-URL route for every civic exporter / series / citizens.

    respx's regex URL matching didn't fire in this env, so we enumerate the
    module's own action + series names and register one route each on the
    injected `router` (the configured `@respx.mock(...)` decorator hands the
    test its router as an argument — the module-level `respx.get` targets a
    different one). Any action not in `csv_by_action` serves the empty CSV; any
    series not in `series_by_name` serves `[]`.
    """
    csv_by_action = _CSV_BY_ACTION if csv_by_action is None else csv_by_action
    series_by_name = _SERIES_BY_NAME if series_by_name is None else series_by_name
    status_by_action = status_by_action or {}
    for action in civics_mod.CIVICS_ACTION_TYPES:
        status = status_by_action.get(action, 200)
        if status != 200:
            router.get(_exporter_url(action)).mock(return_value=httpx.Response(status))
        else:
            router.get(_exporter_url(action)).mock(
                return_value=httpx.Response(200, text=csv_by_action.get(action, _EMPTY_CSV))
            )
    for name in civics_mod.CIVICS_SERIES:
        router.get(_series_url(name)).mock(
            return_value=httpx.Response(200, json=series_by_name.get(name, []))
        )
    router.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))


# --- Unit: parse + aggregate ------------------------------------------------


def test_parse_civic_rows_folds_vote_csv() -> None:
    parsed: list[_CivicEvent] = []
    counts: dict[str, int] = {}
    warnings: list[str] = []
    n = parse_civic_rows("Vote", _rows(_VOTE_CSV), parsed, counts, warnings)
    assert n == 3
    assert counts["Vote"] == 3
    first = parsed[0]
    assert first.citizen_id == "101"
    assert first.subject == "MayorRace"
    assert first.day == pytest.approx(300000 / SECONDS_PER_DAY)


def test_parse_civic_rows_realigns_shifted_row() -> None:
    """A row with an undeclared extra column still folds with correct fields."""
    parsed: list[_CivicEvent] = []
    csv_text = (
        'Citizen,ElectionName,ActionLocation,Count,Time\n101,MayorRace,HandsItem,"1,2,3",1,300000\n'
    )
    parse_civic_rows("Vote", _rows(csv_text), parsed, {}, [])
    e = parsed[0]
    assert e.citizen_id == "101"
    assert e.subject == "MayorRace"
    assert e.location == "1,2,3"
    assert e.day == pytest.approx(300000 / SECONDS_PER_DAY)


def test_parse_civic_rows_respects_max_rows_cap() -> None:
    parsed: list[_CivicEvent] = []
    warnings: list[str] = []
    n = parse_civic_rows("Vote", _rows(_VOTE_CSV), parsed, {}, warnings, max_rows=2)
    assert n == 2
    assert any("truncated" in w for w in warnings)


def _fold_all(name_map: dict[str, str]) -> CivicsReport:
    parsed: list[_CivicEvent] = []
    counts: dict[str, int] = {}
    for action, text in _CSV_BY_ACTION.items():
        parse_civic_rows(action, _rows(text), parsed, counts, [])
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    report.per_action_counts = counts
    build_report(parsed, report, name_map)
    return report


def test_build_report_turnout_and_voters() -> None:
    report = _fold_all({"101": "alice", "102": "bob", "103": "carol"})
    assert report.votes_cast == 3
    assert report.abstentions == 1
    assert report.turnout_rate == pytest.approx(0.75)
    # alice voted twice, bob once.
    top = dict(report.top_voters)
    assert top["alice"] == 2
    assert top["bob"] == 1
    assert report.top_voters[0][0] == "alice"


def test_build_report_elections() -> None:
    report = _fold_all({"101": "alice"})
    assert report.elections_started == 1
    assert report.elections_won == 1
    assert report.recent_elections[0]["subject"] == "MayorRace"
    assert report.recent_elections[0]["proposer"] == "alice"
    assert report.recent_outcomes[0]["winner"] == "alice"


def test_build_report_demographics_and_fallback() -> None:
    report = _fold_all({"101": "alice", "102": "bob", "103": "carol"})
    assert report.citizens_gained == 2
    assert report.citizens_lost == 1
    assert report.net_citizens == 1
    assert report.residency_moves == 1
    # Unmapped id 104 is kept rather than dropped, but reported as an id
    # rather than as a "Citizen #104" person (eco-app#223).
    left = [d for d in report.recent_demographics if d["kind"] == "left"]
    assert left[0]["name"] is None
    assert left[0]["nameId"] == "104"


def test_build_report_settlements() -> None:
    report = _fold_all({"101": "alice", "102": "bob"})
    assert report.settlements_founded == 1
    assert report.homesteads_started == 1
    kinds = {s["kind"] for s in report.recent_settlements}
    assert kinds == {"settlement", "homestead"}
    settlement = next(s for s in report.recent_settlements if s["kind"] == "settlement")
    assert settlement["founder"] == "alice"
    assert settlement["subject"] == "Rivertown"


def test_foundation_placements_are_counted_apart_from_foundings() -> None:
    """A staked foundation is not a settlement (#225).

    Both actions incremented `settlementsFounded`, so Sirens reported 17 on a
    server with 5 — and the `SettlementFounded` trend series, which sums to 5,
    contradicted the headline inside the same response.
    """

    def event(action: str, citizen_id: str, subject: str, day: float) -> _CivicEvent:
        return _CivicEvent(
            action=action,
            time_s=day * SECONDS_PER_DAY,
            day=day,
            citizen_id=citizen_id,
            subject=subject,
            location="",
        )

    parsed = [
        event("SettlementFounded", "101", "Rivertown", 1.0),
        event("PlaceNewSettlementFoundation", "101", "Stakeville", 2.0),
        event("PlaceNewSettlementFoundation", "102", "Postville", 3.0),
    ]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice", "102": "bob"})

    assert report.settlements_founded == 1
    assert report.settlement_foundations_placed == 2
    payload = report.to_dict()
    assert payload["settlementsFounded"] == 1
    assert payload["settlementFoundationsPlaced"] == 2
    # The two kinds stay distinguishable in the event list too.
    kinds = [s["kind"] for s in report.recent_settlements]
    assert kinds.count("settlement") == 1
    assert kinds.count("foundation") == 2


def test_settlements_markdown_separates_the_two_counts() -> None:
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    report.total_events = 17
    report.settlements_founded = 5
    report.settlement_foundations_placed = 12
    settlements_line = next(
        line for line in civics_markdown(report).splitlines() if line.startswith("- Settlements:")
    )
    assert "5 founded" in settlements_line
    assert "12 foundations staked" in settlements_line
    # The old line summed the two into "17 founded".
    assert "17" not in settlements_line


# --- Integration: fetch_civics ---------------------------------------------


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_fetch_civics_merges_actions_series_and_names(respx_mock: respx.Router) -> None:
    _mock_full_server(respx_mock)
    report = await fetch_civics(base_url=BASE, api_key="secret", cache_ttl_s=0)

    assert report.total_events == 12
    assert report.votes_cast == 3
    assert report.turnout_rate == pytest.approx(0.75)
    assert report.net_citizens == 1
    assert report.settlements_founded == 1
    # Actor names resolved from the citizens join.
    assert report.recent_elections[0]["proposer"] == "alice"
    # Daily-count series folded into the trend, seconds -> day on the x-axis.
    assert report.trend["Vote"] == [(0.0, 0.0), (1.0, 1.0), (2.0, 3.0)]
    assert "BecomeCitizen" in report.trend
    assert report.warnings == []


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_fetch_civics_tolerates_partial_failure(respx_mock: respx.Router) -> None:
    _mock_full_server(respx_mock, status_by_action={"Vote": 401})

    report = await fetch_civics(base_url=BASE, api_key=None, cache_ttl_s=0)
    # The other civic actions still fold; only Vote is missing.
    assert report.votes_cast == 0
    assert report.citizens_gained == 2
    assert any("Vote" in w and "401" in w for w in report.warnings)
    # The unread action reports null, its measured neighbours report real counts.
    payload = report.to_dict()
    assert payload["votesCast"] is None
    assert payload["citizensGained"] == 2
    assert payload["unavailableActions"] == ["Vote"]
    assert payload["adminAvailable"] is True


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_every_exporter_401_reports_null_not_zero(respx_mock: respx.Router) -> None:
    """A rejected admin key must not read as a quiet server (#259).

    The scalars came back as 0 while `trend` — sourced separately — still
    carried real data, so the same response said both "no votes were cast" and
    "here is the vote-over-time series".
    """
    _mock_full_server(
        respx_mock,
        status_by_action=dict.fromkeys(civics_mod.CIVICS_ACTION_TYPES, 401),
        series_by_name={"Vote": [{"Time": 0, "Value": 4}, {"Time": 86400, "Value": 6}]},
    )

    report = await fetch_civics(base_url=BASE, api_key=None, cache_ttl_s=0)
    payload = report.to_dict()

    assert payload["adminAvailable"] is False
    assert sorted(payload["unavailableActions"]) == sorted(civics_mod.CIVICS_ACTION_TYPES)
    for key in (
        "totalEvents",
        "votesCast",
        "abstentions",
        "electionsStarted",
        "citizensGained",
        "settlementsFounded",
        "homesteadsStarted",
        "turnoutRate",
    ):
        assert payload[key] is None, key
    # The separately-sourced trend still carries its data, and the payload now
    # explains why it can disagree with the (null) scalars.
    assert payload["trend"]["Vote"]
    assert "trend" in payload["measurementNote"]
    # The prose must not call an auth failure "no civic events recorded yet".
    markdown = civics_markdown(report)
    assert "no civic events recorded yet" not in markdown
    assert "nothing here was measured" in markdown


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_measured_zero_stays_zero(respx_mock: respx.Router) -> None:
    """A server that answered and had no civic activity reports 0, not null."""
    _mock_full_server(respx_mock, csv_by_action={}, series_by_name={})

    payload = (await fetch_civics(base_url=BASE, api_key=None, cache_ttl_s=0)).to_dict()
    assert payload["adminAvailable"] is True
    assert payload["votesCast"] == 0
    assert payload["citizensGained"] == 0
    assert payload["unavailableActions"] == []
    assert payload["measurementNote"] == ""


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_fetch_civics_empty_is_clean(respx_mock: respx.Router) -> None:
    _mock_full_server(respx_mock, csv_by_action={}, series_by_name={})

    report = await fetch_civics(base_url=BASE, api_key=None, cache_ttl_s=0)
    assert report.total_events == 0
    assert civics_template_context(report)["empty"] is True
    assert "no civic events" in civics_markdown(report).lower()


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_fetch_civics_cache_hits_within_ttl(respx_mock: respx.Router) -> None:
    _mock_full_server(respx_mock)

    a1 = await fetch_civics(base_url=BASE, api_key="k", cache_ttl_s=60)
    after_first = respx_mock.calls.call_count
    a2 = await fetch_civics(base_url=BASE, api_key="k", cache_ttl_s=60)
    assert a1.total_events == a2.total_events == 12
    # Second call served entirely from cache — no new upstream hits.
    assert respx_mock.calls.call_count == after_first


# --- Tool wiring ------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_tool_call_returns_text_blocks_and_fragment(
    respx_mock: respx.Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    _mock_full_server(respx_mock)

    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(
            name="get_civics",
            arguments={"server": "eco.example.com:3001"},
        ),
    )
    result = await handler(req)
    blocks = result.root.content
    assert len(blocks) == 2
    assert isinstance(blocks[0], mt.TextContent)
    assert "Civics" in blocks[0].text
    assert result.root.meta is None


@pytest.mark.asyncio
async def test_list_tools_includes_get_civics() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {tool.name for tool in result.root.tools}
    assert "get_civics" in names


# ---------------------------------------------------------------------------
# Entity resolution (eco-app#223)
# ---------------------------------------------------------------------------


def _civic(action: str, citizen_id: str, subject: str, day: float = 1.0) -> _CivicEvent:
    return _CivicEvent(
        action=action,
        time_s=day * SECONDS_PER_DAY,
        day=day,
        citizen_id=citizen_id,
        subject=subject,
        location="",
    )


def test_an_unresolved_id_is_never_rendered_as_a_person() -> None:
    """456767 is an election *title* id, not a citizen (eco-app#223).

    Formatting it as "Citizen #456767" invented a player who does not exist
    and put them on the proposer list and the voter roll.
    """
    parsed = [
        _civic("StartElection", "456767", "1298404"),
        _civic("Vote", "60", "1298404"),
        _civic("Vote", "101", "1298404"),
    ]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice"})

    election = report.recent_elections[0]
    assert election["proposer"] is None
    assert election["proposerId"] == "456767"
    # No invented person anywhere in the data. The warning prose is allowed to
    # name the old format, so it is excluded from the sweep.
    data_only = {k: v for k, v in report.to_dict().items() if k != "warnings"}
    assert "Citizen #" not in json.dumps(data_only)

    # The unresolved voter is counted but not ranked as a player.
    assert report.votes_cast == 2
    assert dict(report.top_voters) == {"alice": 1}
    assert report.unresolved_voter_ids == 1
    assert any("eco-app#223" in w for w in report.warnings)


def test_a_numeric_subject_is_reported_as_an_id_not_blanked() -> None:
    """Every subject / settlement field came back as an empty string.

    `_clean_name` blanks a bare number, and these columns key by id, so blank
    told the reader "no subject" when the truth was "an id we did not resolve".
    """
    parsed = [_civic("BecomeCitizen", "101", "1298404")]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice", "1298404": "Costa Del Sol"})
    joined = report.recent_demographics[0]
    assert joined["settlement"] == "Costa Del Sol"
    assert joined["settlementId"] is None

    # And when the id cannot be resolved, it surfaces as an id.
    report2 = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report2, {"101": "alice"})
    joined2 = report2.recent_demographics[0]
    assert joined2["settlement"] is None
    assert joined2["settlementId"] == "1298404"


def test_a_position_triple_subject_is_still_dropped() -> None:
    parsed = [_civic("SettlementFounded", "101", "419,75,458")]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice"})
    entry = report.recent_settlements[0]
    assert entry["subject"] is None
    assert entry["subjectId"] is None


# ---------------------------------------------------------------------------
# Duplicate demographic events (eco-app#224)
# ---------------------------------------------------------------------------


def test_repeated_demographic_rows_are_counted_once_as_people() -> None:
    """The exporter repeats whole runs of identical rows (eco-app#224).

    A day-19 joined block appeared three times verbatim, so `citizensGained`
    reached 371 on a server that has seen 165 distinct players ever — roughly
    2x reality presented as a headcount.
    """
    parsed = [
        _civic("BecomeCitizen", "101", "Rivertown", day=19.0),
        _civic("BecomeCitizen", "101", "Rivertown", day=19.0),
        _civic("BecomeCitizen", "101", "Rivertown", day=19.0),
        _civic("BecomeCitizen", "102", "Rivertown", day=19.0),
        _civic("LeaveCitizenship", "102", "Rivertown", day=20.0),
    ]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice", "102": "bob"})

    # Event counts still reconcile with perActionCounts.
    assert report.citizens_gained == 4
    assert report.citizens_lost == 1
    # Headcount is the truth about people.
    assert report.distinct_citizens_gained == 2
    assert report.distinct_citizens_lost == 1
    assert report.net_distinct_citizens == 1
    # The browsable list shows each event once.
    joined = [d for d in report.recent_demographics if d["kind"] == "joined"]
    assert len(joined) == 2
    assert report.duplicate_demographic_events == 2
    assert any("eco-app#224" in w for w in report.warnings)


def test_the_payload_labels_events_against_people() -> None:
    parsed = [
        _civic("BecomeCitizen", "101", "Rivertown", day=19.0),
        _civic("BecomeCitizen", "101", "Rivertown", day=19.0),
    ]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice"})
    payload = report.to_dict()
    assert payload["citizensGained"] == 2
    assert payload["distinctCitizensGained"] == 1
    assert "count exporter events" in payload["demographicsNote"]


def test_the_same_person_rejoining_on_a_later_day_is_not_a_duplicate() -> None:
    parsed = [
        _civic("BecomeCitizen", "101", "Rivertown", day=19.0),
        _civic("BecomeCitizen", "101", "Rivertown", day=27.0),
    ]
    report = CivicsReport(fetched_at_iso="t", source_base_url="b")
    build_report(parsed, report, {"101": "alice"})
    assert report.duplicate_demographic_events == 0
    assert len(report.recent_demographics) == 2
    # One person, two arrivals.
    assert report.distinct_citizens_gained == 1
