"""Per-user dossier pivot + roster, the world de-cap, and the two endpoints.

The pivot/roster layer (`eco_mcp_app.users`) is pure over already-fetched tool
payloads, so it tests without a live server. The endpoints are exercised with
`_gather_user_sources` monkeypatched to canned sources.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from eco_mcp_app import users
from eco_mcp_app.http_app import create_app
from eco_mcp_app.world import WorldAccumulator, finalize


def sample_sources() -> dict[str, Any]:
    """Canned per-surface payloads spanning every source the dossier reads."""
    return {
        "jobs": [
            {
                "name": "coilysiren",
                "active": True,
                "lastSeenISO": "2026-05-08T12:34:56+00:00",
                "specialties": [{"specialty": "Basic Carpentry", "level": 5, "active": True}],
            },
            {"name": "redwood", "active": False, "lastSeenISO": None, "specialties": []},
        ],
        "trades": {
            "topBuyers": [["coilysiren", 250], ["Citizen #999", 40]],
            "topSellers": [["ekans", 390], ["coilysiren", 225]],
            "trades": [
                {"buyer": "coilysiren", "seller": "ekans", "shopOwner": "ekans", "item": "Iron"},
                {"buyer": "redwood", "seller": "coilysiren", "shopOwner": "coilysiren"},
            ],  # coilysiren appears as buyer in row 1, seller/owner in row 2
        },
        "crafting": {"byCitizen": [["coilysiren", 42], ["redwood", 7]]},
        "civics": {
            "topVoters": [["coilysiren", 3], ["ekans", 1]],
            "recentElections": [{"subject": "Head of State", "proposer": "coilysiren", "day": 4}],
            "recentOutcomes": [
                {"subject": "Head of State", "winner": "ekans", "day": 5},
                {"subject": "Treasurer", "winner": "coilysiren", "day": 6},
            ],
            "recentDemographics": [
                {"name": "redwood", "day": 1, "kind": "joined", "settlement": "Town"}
            ],
            "recentSettlements": [
                {"subject": "Town", "founder": "coilysiren", "day": 2, "kind": "settlement"}
            ],
        },
        "currency": {
            "currencies": [
                {
                    "name": "Credit",
                    "topHolders": [
                        {"account": "coily Account", "holder": "coilysiren", "balance": 1200.0},
                        {"account": "Treasury", "holder": None, "balance": 5000.0},
                    ],
                },
                {"name": "Gold", "topHolders": []},
            ],
        },
        "progression": {
            "citizens": [
                {"name": "coilysiren", "eventCount": 9, "characterLevel": 12, "levelUpCount": 4}
            ],
            "topLevelers": [["coilysiren", 4], ["ekans", 2]],
        },
        "world": {
            "byCitizen": [["coilysiren", 30], ["redwood", 3]],
            "byPolluter": [["coilysiren", 2]],
        },
    }


def test_dossier_pivots_every_source_for_one_user() -> None:
    dossier = users.build_user_dossier("coilysiren", sample_sources())

    assert dossier["username"] == "coilysiren"
    assert dossier["found"] is True
    assert dossier["jobs"]["lastSeenISO"] == "2026-05-08T12:34:56+00:00"
    assert dossier["jobs"]["specialties"][0]["specialty"] == "Basic Carpentry"
    assert dossier["trades"]["currencySpent"] == 250
    assert dossier["trades"]["currencyEarned"] == 225
    assert len(dossier["trades"]["trades"]) == 2  # buyer in one, seller/owner in the other
    assert dossier["crafting"]["events"] == 42
    assert dossier["civics"]["votesCast"] == 3
    assert {e["role"] for e in dossier["civics"]["elections"]} == {"proposed", "won"}
    assert dossier["civics"]["settlements"][0]["subject"] == "Town"
    assert dossier["currency"]["holdings"] == [
        {"currency": "Credit", "balance": 1200.0, "account": "coily Account"}
    ]
    assert dossier["progression"]["levelUpCount"] == 4
    assert dossier["progression"]["trajectory"]["characterLevel"] == 12
    assert dossier["world"] == {"shaperEvents": 30, "pollutionEvents": 2}
    # Cap notes surface only for sources whose per-user list stays capped upstream.
    assert any("currency holdings" in w for w in dossier["warnings"])
    assert any("skill trajectories" in w for w in dossier["warnings"])


def test_dossier_for_a_user_present_in_only_one_source() -> None:
    dossier = users.build_user_dossier("ekans", sample_sources())
    assert dossier["found"] is True
    assert dossier["jobs"] is None  # ekans has no jobs row
    assert dossier["trades"]["currencyEarned"] == 390
    assert dossier["crafting"] is None
    assert dossier["civics"]["votesCast"] == 1
    assert dossier["world"] is None


def test_dossier_for_an_unknown_user_is_empty_but_not_an_error() -> None:
    dossier = users.build_user_dossier("nobody", sample_sources())
    assert dossier["found"] is False
    assert all(dossier[key] is None for key in ("jobs", "trades", "crafting", "world"))
    # The roster still lists everyone — an unknown user does not hide the index.
    assert "coilysiren" in dossier["roster"]


def test_roster_unions_every_user_including_unresolved_ids() -> None:
    roster = users.build_roster(sample_sources())
    # Names from jobs, trades (incl. Citizen #id), crafting, civics, currency,
    # progression, and world — all deduped and sorted.
    assert roster == sorted({"coilysiren", "redwood", "ekans", "Citizen #999"})
    # Government/company holders (holder=None) never leak into the roster.
    assert None not in roster


def test_roster_tolerates_missing_and_none_sources() -> None:
    sources = {"trades": None, "world": {"byCitizen": [["solo", 1]], "byPolluter": []}}
    assert users.build_roster(sources) == ["solo"]


def test_dossier_available_flags_track_source_health() -> None:
    sources = dict(sample_sources())
    sources["currency"] = None  # simulate a dead exporter
    dossier = users.build_user_dossier("coilysiren", sources)
    assert dossier["available"]["currency"] is False
    assert dossier["available"]["trades"] is True
    assert dossier["currency"] is None  # no section, and no cap warning for it
    assert not any("currency holdings" in w for w in dossier["warnings"])


def test_world_finalize_lists_every_shaper_not_a_top_n() -> None:
    # Eco-app#80: user-pivoted lists must not truncate. finalize used to cap
    # by_citizen/by_polluter at 25; the default is now no cap.
    acc = WorldAccumulator()
    acc.by_citizen = {f"citizen-{i}": i for i in range(40)}
    acc.by_polluter = {f"citizen-{i}": i for i in range(30)}
    activity = finalize(acc, "2026-01-01T00:00:00+00:00", "http://x:3001")
    assert len(activity.by_citizen) == 40
    assert len(activity.by_polluter) == 30
    # An explicit bound still works (cards/tests may want one).
    bounded = finalize(acc, "2026-01-01T00:00:00+00:00", "http://x:3001", top_citizens=10)
    assert len(bounded.by_citizen) == 10


@pytest.fixture
def stub_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(_server: str | None) -> dict[str, Any]:
        return sample_sources()

    monkeypatch.setattr("eco_mcp_app.http_app._gather_user_sources", _fake)


@pytest.mark.usefixtures("stub_sources")
def test_user_endpoint_returns_the_dossier() -> None:
    client = TestClient(create_app())
    r = client.get("/preview/user.json", params={"name": "coilysiren"})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "coilysiren"
    assert body["found"] is True
    assert body["crafting"]["events"] == 42
    assert "fetchedAtISO" in body


def test_user_endpoint_requires_a_name() -> None:
    client = TestClient(create_app())
    r = client.get("/preview/user.json")
    assert r.status_code == 400


@pytest.mark.usefixtures("stub_sources")
def test_users_index_lists_every_user() -> None:
    client = TestClient(create_app())
    r = client.get("/preview/users.json")
    assert r.status_code == 200
    body = r.json()
    assert body["users"] == sorted({"coilysiren", "redwood", "ekans", "Citizen #999"})
    assert body["available"]["trades"] is True


def test_sanitize_nonfinite_walks_nested_structures() -> None:
    """`_sanitize_nonfinite` drops inf/-inf/nan leaves to None anywhere in the
    payload while leaving finite values untouched (eco-app#83)."""
    from eco_mcp_app.http_app import _sanitize_nonfinite

    dirty = {
        "price": math.inf,
        "loss": -math.inf,
        "ratio": math.nan,
        "ok": 3.5,
        "count": 7,
        "nested": {"unit": math.inf, "keep": "x"},
        "rows": [1.0, math.inf, {"p": math.nan}],
    }
    clean = _sanitize_nonfinite(dirty)
    assert clean == {
        "price": None,
        "loss": None,
        "ratio": None,
        "ok": 3.5,
        "count": 7,
        "nested": {"unit": None, "keep": "x"},
        "rows": [1.0, None, {"p": None}],
    }
    # And the sanitized payload is JSON-compliant (allow_nan=False, like Starlette).
    json.dumps(clean, allow_nan=False)


def test_user_endpoint_survives_nonfinite_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dossier carrying inf/nan (e.g. a `total/qty` with qty==0 from an
    upstream exporter) must not 500 the endpoint (eco-app#83)."""

    async def _fake(_server: str | None) -> dict[str, Any]:
        return sample_sources()

    def _poisoned(username: str, _sources: dict[str, Any]) -> dict[str, Any]:
        return {
            "username": username,
            "found": True,
            "trades": {"avgUnitPrice": math.inf, "worst": math.nan},
            "currency": [{"balance": -math.inf}],
        }

    monkeypatch.setattr("eco_mcp_app.http_app._gather_user_sources", _fake)
    monkeypatch.setattr("eco_mcp_app.http_app.users_mod.build_user_dossier", _poisoned)

    client = TestClient(create_app())
    r = client.get("/preview/user.json", params={"name": "elizacorn"})
    assert r.status_code == 200
    body = r.json()
    assert body["trades"]["avgUnitPrice"] is None
    assert body["trades"]["worst"] is None
    assert body["currency"][0]["balance"] is None
