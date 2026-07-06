"""Tests for the progression / skills-history aggregator + tool wiring (eco-app#64).

Covers:
  - Folding each progression action CSV into events with the right fields
    (citizen id, skill/profession/class name, level, in-game day).
  - Time → in-game-day conversion (seconds / 86400, species convention).
  - Per-citizen trajectory rollup: professions gained, currently-held
    specialties (gains minus losses), highest character level, level-up count.
  - Server-wide per-day trends per event kind + the leaderboards.
  - Numeric citizen ids joined to names via /api/v1/citizens, `Citizen #<id>`
    fallback for a missing id (eco-app#5).
  - Defensive realignment of a row carrying an undeclared extra column.
  - Best-effort daily-series discovery via /datasets/flatlist.
  - Missing-endpoint (401 / connect error) becomes a non-fatal warning.
  - Empty CSVs produce a clean "no progression" history.
  - The in-memory TTL cache is per (base, api-key) and hits within TTL.
  - Tool wiring returns two TextContent blocks and no widget (just-data per eco-app#87).
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import mcp.types as mt
import pytest
import respx

from eco_mcp_app import progression as prog_mod
from eco_mcp_app.progression import (
    SECONDS_PER_DAY,
    ProgressionHistory,
    _ParsedEvent,
    build_history,
    fetch_history,
    history_markdown,
    history_template_context,
    parse_progression_rows,
)
from eco_mcp_app.server import build_server

BASE = "http://eco.example.com:3001"


def _url(action: str) -> str:
    return f"{BASE}/api/v1/exporter/actions?actionName={action}"


CITIZENS_URL = f"{BASE}/api/v1/citizens"
FLATLIST_URL = f"{BASE}/datasets/flatlist"

_CITIZENS_JSON = [
    {"id": 129312, "name": "coilysiren"},
    {"id": 130409, "name": "ekans"},
]

# Column shapes below are the best-effort candidate names from progression.py's
# SKILL_COLUMNS / LEVEL_COLUMNS (the live exporter header wasn't capturable — see
# the module docstring). The parser keys off the header, so these exercise the
# real pick path.
_GAIN_SPECIALTY_CSV = (
    "Citizen,Specialty,Level,ActionLocation,Count,Time\n"
    '129312,BlacksmithSkill,1,"1,2,3",1,100000\n'
    '130409,FarmingSkill,1,"4,5,6",1,150000\n'
    '129312,MiningSkill,1,"1,2,3",1,200000\n'
)
_SPECIALTY_LEVELUP_CSV = (
    "Citizen,Specialty,Level,Time\n"
    "129312,BlacksmithSkill,2,120000\n"
    "129312,BlacksmithSkill,3,300000\n"
    "130409,FarmingSkill,2,160000\n"
)
_LOSE_SPECIALTY_CSV = "Citizen,Specialty,Time\n129312,MiningSkill,250000\n"
_GAIN_PROFESSION_CSV = "Citizen,Profession,Time\n129312,Engineer,90000\n130409,Farmer,140000\n"
_CHARACTER_LEVELUP_CSV = "Citizen,Level,Time\n129312,2,130000\n129312,3,310000\n"
_COMPLETE_CLASS_CSV = "Citizen,Class,Time\n129312,SmithingClass,110000\n"
_ENROLL_CSV = "Citizen,Specialty,Time\n130409,FarmingSkill,135000\n"

_EMPTY_HEADER = "Citizen,Time\n"


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    prog_mod._progression_cache.clear()
    yield
    prog_mod._progression_cache.clear()


def _rows(csv_text: str) -> list[list[str]]:
    import csv

    return list(csv.reader(csv_text.splitlines()))


def _mock_all_actions(respx_router: respx.Router) -> respx.Route:
    """Wire every progression action + the citizens/flatlist joins for a fetch.

    Returns the GainSpecialty route so a caller can assert its call count.
    """
    respx_router.get(_url("GainProfession")).mock(
        return_value=httpx.Response(200, text=_GAIN_PROFESSION_CSV)
    )
    gain_specialty = respx_router.get(_url("GainSpecialty")).mock(
        return_value=httpx.Response(200, text=_GAIN_SPECIALTY_CSV)
    )
    respx_router.get(_url("LoseSpecialty")).mock(
        return_value=httpx.Response(200, text=_LOSE_SPECIALTY_CSV)
    )
    respx_router.get(_url("SpecialtyLevelUp")).mock(
        return_value=httpx.Response(200, text=_SPECIALTY_LEVELUP_CSV)
    )
    respx_router.get(_url("CharacterLevelUp")).mock(
        return_value=httpx.Response(200, text=_CHARACTER_LEVELUP_CSV)
    )
    respx_router.get(_url("CompleteClass")).mock(
        return_value=httpx.Response(200, text=_COMPLETE_CLASS_CSV)
    )
    respx_router.get(_url("EnrollAction")).mock(return_value=httpx.Response(200, text=_ENROLL_CSV))
    respx_router.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))
    # Flatlist discovery defaults to empty (no daily series) unless overridden.
    respx_router.get(FLATLIST_URL).mock(return_value=httpx.Response(200, json=[]))
    return gain_specialty


def test_parse_progression_rows_folds_gain_specialty() -> None:
    history = ProgressionHistory(fetched_at_iso="t", source_base_url="b")
    parsed: list[_ParsedEvent] = []
    n = parse_progression_rows("GainSpecialty", _rows(_GAIN_SPECIALTY_CSV), history, parsed)
    assert n == 3
    assert history.per_action_counts["GainSpecialty"] == 3
    first = parsed[0]
    assert first.citizen_id == "129312"
    assert first.skill == "BlacksmithSkill"
    assert first.level == pytest.approx(1.0)
    assert first.kind == "specialty"
    # Time → in-game day via the species /86400 convention.
    assert first.day == pytest.approx(100000 / SECONDS_PER_DAY)


def test_build_history_rolls_up_trajectory_and_resolves_names() -> None:
    history = ProgressionHistory(fetched_at_iso="t", source_base_url="b")
    parsed: list[_ParsedEvent] = []
    parse_progression_rows("GainProfession", _rows(_GAIN_PROFESSION_CSV), history, parsed)
    parse_progression_rows("GainSpecialty", _rows(_GAIN_SPECIALTY_CSV), history, parsed)
    parse_progression_rows("LoseSpecialty", _rows(_LOSE_SPECIALTY_CSV), history, parsed)
    parse_progression_rows("SpecialtyLevelUp", _rows(_SPECIALTY_LEVELUP_CSV), history, parsed)
    parse_progression_rows("CharacterLevelUp", _rows(_CHARACTER_LEVELUP_CSV), history, parsed)
    parse_progression_rows("CompleteClass", _rows(_COMPLETE_CLASS_CSV), history, parsed)
    parse_progression_rows("EnrollAction", _rows(_ENROLL_CSV), history, parsed)

    build_history(parsed, history, {"129312": "coilysiren", "130409": "ekans"})

    assert history.total_events == 13
    cards = {c["name"]: c for c in history.citizens}
    coily = cards["coilysiren"]
    # Engineer profession gained.
    assert [p["name"] for p in coily["professions"]] == ["Engineer"]
    # Blacksmith held (leveled to 3); Mining gained then LOST → not current.
    held = {s["name"]: s["level"] for s in coily["specialties"]}
    assert held == {"BlacksmithSkill": pytest.approx(3.0)}
    # Character level-ups (2) + specialty level-ups (2) = 4.
    assert coily["levelUpCount"] == 4
    assert coily["characterLevel"] == pytest.approx(3.0)
    # Leaderboards.
    by_spec = dict(history.by_specialty)
    assert by_spec["BlacksmithSkill"] == 1
    assert by_spec["MiningSkill"] == 1
    assert history.top_levelers[0][0] == "coilysiren"
    assert dict(history.class_completions)["SmithingClass"] == 1
    # Trends: specialty gains bucketed by day (100000/86400≈1, 150000≈1, 200000≈2).
    spec_trend = dict(history.trends["specialty"])
    assert spec_trend[1.0] == 2.0
    assert spec_trend[2.0] == 1.0


def test_specialty_regained_after_loss_is_current() -> None:
    """A gain that post-dates a loss leaves the specialty held again."""
    history = ProgressionHistory(fetched_at_iso="t", source_base_url="b")
    parsed: list[_ParsedEvent] = []
    csv_text = (
        "Citizen,Specialty,Level,Time\n"
        "1,SmithSkill,1,1000\n"  # gain
    )
    parse_progression_rows("GainSpecialty", _rows(csv_text), history, parsed)
    parse_progression_rows(
        "LoseSpecialty", _rows("Citizen,Specialty,Time\n1,SmithSkill,2000\n"), history, parsed
    )
    parse_progression_rows(
        "GainSpecialty",
        _rows("Citizen,Specialty,Level,Time\n1,SmithSkill,1,3000\n"),
        history,
        parsed,
    )
    build_history(parsed, history, {})
    held = {s["name"] for s in history.citizens[0]["specialties"]}
    assert held == {"SmithSkill"}


def test_parse_progression_realigns_shifted_row() -> None:
    """A row with an undeclared extra column still folds with correct fields."""
    history = ProgressionHistory(fetched_at_iso="t", source_base_url="b")
    parsed: list[_ParsedEvent] = []
    # Extra "HandsItem" column before ActionLocation shifts later fields; the
    # ActionLocation position triple anchors the realignment (crafting._corrected_index).
    csv_text = (
        "Citizen,Specialty,Level,ActionLocation,Count,Time\n"
        '129312,BlacksmithSkill,2,HandsItem,"1,2,3",1,200000\n'
    )
    parse_progression_rows("GainSpecialty", _rows(csv_text), history, parsed)
    e = parsed[0]
    assert e.citizen_id == "129312"
    assert e.skill == "BlacksmithSkill"
    assert e.level == pytest.approx(2.0)
    assert e.day == pytest.approx(200000 / SECONDS_PER_DAY)


def test_parse_progression_respects_max_rows_cap() -> None:
    history = ProgressionHistory(fetched_at_iso="t", source_base_url="b")
    parsed: list[_ParsedEvent] = []
    n = parse_progression_rows(
        "GainSpecialty", _rows(_GAIN_SPECIALTY_CSV), history, parsed, max_rows=2
    )
    assert n == 2
    assert any("truncated" in w for w in history.warnings)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_history_merges_actions_and_joins_names() -> None:
    _mock_all_actions(respx.mock)
    history = await fetch_history(base_url=BASE, api_key="secret", cache_ttl_s=0)
    assert history.total_events == 13
    assert history.per_action_counts["GainSpecialty"] == 3
    assert history.per_action_counts["EnrollAction"] == 1
    names = {c["name"] for c in history.citizens}
    assert names == {"coilysiren", "ekans"}
    assert history.warnings == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_history_citizen_fallback_on_missing_name() -> None:
    _mock_all_actions(respx.mock)
    # Drop ekans from the citizens join → id 130409 falls back to Citizen #<id>.
    respx.get(CITIZENS_URL).mock(
        return_value=httpx.Response(200, json=[{"id": 129312, "name": "coilysiren"}])
    )
    history = await fetch_history(base_url=BASE, api_key="k", cache_ttl_s=0)
    names = {c["name"] for c in history.citizens}
    assert "Citizen #130409" in names


@pytest.mark.asyncio
@respx.mock
async def test_fetch_history_discovers_daily_series() -> None:
    _mock_all_actions(respx.mock)
    respx.get(FLATLIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"Name": "AverageSpecialtyLevel"},
                {"Name": "SeaLevel"},  # decoy — must NOT be picked
            ],
        )
    )
    respx.get(f"{BASE}/datasets/get").mock(
        return_value=httpx.Response(200, json={"Times": [0, 86400], "Values": [1.0, 2.5]})
    )
    history = await fetch_history(base_url=BASE, api_key="k", cache_ttl_s=0)
    assert "AverageSpecialtyLevel" in history.daily_series
    assert "SeaLevel" not in history.daily_series
    assert history.daily_series["AverageSpecialtyLevel"] == [
        (pytest.approx(0.0), pytest.approx(1.0)),
        (pytest.approx(86400.0), pytest.approx(2.5)),
    ]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_history_tolerates_partial_failure() -> None:
    _mock_all_actions(respx.mock)
    respx.get(_url("EnrollAction")).mock(return_value=httpx.Response(401))
    history = await fetch_history(base_url=BASE, api_key=None, cache_ttl_s=0)
    assert history.total_events == 12  # everything but the enroll row
    assert any("EnrollAction" in w and "401" in w for w in history.warnings)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_history_empty_is_clean() -> None:
    for action in prog_mod.PROGRESSION_ACTION_TYPES:
        respx.get(_url(action)).mock(return_value=httpx.Response(200, text=_EMPTY_HEADER))
    history = await fetch_history(base_url=BASE, api_key=None, cache_ttl_s=0)
    assert history.total_events == 0
    assert history.citizens == []
    assert history_template_context(history)["empty"] is True
    assert "no progression" in history_markdown(history).lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_history_cache_hits_within_ttl() -> None:
    route = _mock_all_actions(respx.mock)
    a1 = await fetch_history(base_url=BASE, api_key="k", cache_ttl_s=60)
    a2 = await fetch_history(base_url=BASE, api_key="k", cache_ttl_s=60)
    assert a1.total_events == a2.total_events == 13
    assert route.call_count == 1


def test_history_template_context_summarizes() -> None:
    history = ProgressionHistory(fetched_at_iso="t", source_base_url="b")
    parsed: list[_ParsedEvent] = []
    parse_progression_rows("GainSpecialty", _rows(_GAIN_SPECIALTY_CSV), history, parsed)
    build_history(parsed, history, {"129312": "coilysiren", "130409": "ekans"})
    ctx = history_template_context(history)
    assert ctx["empty"] is False
    # Ties (all count 1) sort by name desc → MiningSkill first; prettify splits
    # camelCase but keeps the "Skill" token (not a stripped Item/Species suffix).
    assert ctx["top_specialties"][0]["pretty"] == "Mining Skill"
    labels = {label for label, _ in ctx["kind_totals"]}
    assert "specialties gained" in labels


@pytest.mark.asyncio
@respx.mock
async def test_tool_call_returns_text_blocks_and_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    _mock_all_actions(respx.mock)
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(
            name="get_eco_progression",
            arguments={"server": "eco.example.com:3001"},
        ),
    )
    result = await handler(req)
    blocks = result.root.content
    assert len(blocks) == 2
    assert isinstance(blocks[0], mt.TextContent)
    assert "Progression history" in blocks[0].text
    # Just-data per eco-app#87: get_eco_progression no longer emits a widget.
    assert result.root.meta is None


@pytest.mark.asyncio
async def test_list_tools_includes_get_eco_progression() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {tool.name for tool in result.root.tools}
    assert "get_eco_progression" in names
