"""`get_server_status` distinguishes "zero" from "not reported" (eco-app#214).

Eco's `/info` varies by server version and mod set. The mapping used to coerce
every numeric with `or 0`, which republished an absent field as a confident
measurement — `timeSinceStartS: 0` reads as "the server just restarted", and
that cost real triage time when a time skip was suspected on Sirens.
"""

from __future__ import annotations

from typing import Any

from eco_mcp_app.server import _format_markdown, to_payload

# Only the non-numeric keys the payload needs to render. Every numeric field
# is deliberately absent, which is the case under test.
_INFO_WITHOUT_NUMBERS: dict[str, Any] = {
    "Description": "Eco via Sirens",
    "Category": "Test",
    "Version": "0.13.0.4",
    "WorldSize": "0.52 km²",
    "CollaborationLevel": "HighCollaboration",
    "GameSpeed": "Slow",
    "SimulationLevel": "Full",
    "HasMeteor": False,
}

_NUMERIC_FIELDS = (
    ("players", "online"),
    ("players", "total"),
    ("players", "activeAndOnline"),
    ("players", "peakActive"),
    ("world", "plants"),
    ("world", "animals"),
    ("world", "laws"),
    ("world", "totalCulture"),
    ("cycle", "daysRunning"),
    ("cycle", "daysUntilMeteor"),
    ("cycle", "timeSinceStartS"),
    ("exhaustion", "afterHours"),
)


def test_absent_numeric_fields_are_null_not_zero() -> None:
    payload = to_payload(_INFO_WITHOUT_NUMBERS)
    for section, field in _NUMERIC_FIELDS:
        assert payload[section][field] is None, f"{section}.{field} defaulted instead of None"


def test_time_since_start_is_null_when_upstream_omits_it() -> None:
    # Eco 0.13's /info carries no Time* key at all — the field this issue was
    # filed against.
    assert to_payload(_INFO_WITHOUT_NUMBERS)["cycle"]["timeSinceStartS"] is None


def test_reported_zero_survives_as_zero() -> None:
    # The inverse guard: a server that genuinely reports 0 must not be
    # laundered into "unknown".
    info = dict(_INFO_WITHOUT_NUMBERS, OnlinePlayers=0, Animals=0, TotalCulture=0.0)
    payload = to_payload(info)
    assert payload["players"]["online"] == 0
    assert payload["world"]["animals"] == 0
    assert payload["world"]["totalCulture"] == 0.0


def test_unparseable_numeric_reads_as_unreported() -> None:
    payload = to_payload(dict(_INFO_WITHOUT_NUMBERS, Laws="lots", DaysRunning=None))
    assert payload["world"]["laws"] is None
    assert payload["cycle"]["daysRunning"] is None


def test_markdown_names_the_absent_case_instead_of_printing_zero() -> None:
    markdown = _format_markdown(to_payload(_INFO_WITHOUT_NUMBERS))
    assert "not reported" in markdown
    # A bare "0" for an unreported count is exactly the wrong answer.
    assert "**0 / 0**" not in markdown
    assert "culture 0.0" not in markdown


def test_markdown_still_renders_real_numbers() -> None:
    info = dict(
        _INFO_WITHOUT_NUMBERS,
        OnlinePlayers=7,
        TotalPlayers=67,
        PeakActivePlayers=38,
        ActiveAndOnlinePlayers=7,
        Plants=96000,
        Animals=12,
        Laws=1,
        TotalCulture=171.0,
        DaysRunning=40,
        DaysUntilMeteor=20,
    )
    markdown = _format_markdown(to_payload(info))
    assert "**7 / 67**" in markdown
    assert "96,000 plants" in markdown
    assert "1 law " in markdown  # singular, not "1 laws"
    assert "culture 171.0" in markdown
    assert "not reported" not in markdown
