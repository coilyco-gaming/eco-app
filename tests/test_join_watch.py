from __future__ import annotations

import httpx
import pytest
import respx

from scripts.join_watch import (
    EXIT_CODES,
    JoinWatch,
    Observation,
    Outcome,
    Verdict,
    display_url,
    main,
    poll_once,
)


def watcher(**kwargs: object) -> JoinWatch:
    defaults: dict[str, object] = {
        "player": "Kai",
        "started_at": 0.0,
        "timeout_s": 100.0,
        "hold_s": 30.0,
    }
    defaults.update(kwargs)
    return JoinWatch(**defaults)  # type: ignore[arg-type]


def seen(at: float, *names: str, version: str | None = "0.13.0.4") -> Observation:
    return Observation(at=at, online=frozenset(names), version=version)


def failed(at: float, error: str = "ConnectError: refused") -> Observation:
    return Observation(at=at, online=None, error=error)


def drive(w: JoinWatch, observations: list[Observation]) -> Outcome | None:
    outcome: Outcome | None = None
    for obs in observations:
        outcome = w.observe(obs)
        if outcome is not None:
            return outcome
    return None


def test_absent_then_present_for_the_hold_window_is_a_join() -> None:
    w = watcher()
    outcome = drive(w, [seen(0, "Bel"), seen(10, "Bel", "Kai"), seen(45, "Bel", "Kai")])
    assert outcome is not None
    assert outcome.verdict is Verdict.JOINED
    assert outcome.joined_after_s == 10
    assert outcome.held_for_s == 35
    assert outcome.others_online == ("Bel",)


def test_present_for_less_than_the_hold_window_is_not_yet_a_join() -> None:
    w = watcher()
    assert drive(w, [seen(0), seen(10, "Kai"), seen(20, "Kai")]) is None


def test_appearing_then_vanishing_inside_the_hold_window_is_a_drop() -> None:
    w = watcher()
    outcome = drive(w, [seen(0), seen(10, "Kai"), seen(25, "Bel")])
    assert outcome is not None
    assert outcome.verdict is Verdict.DROPPED
    assert outcome.held_for_s == 15
    assert "crashing after world load" in outcome.detail


def test_never_appearing_before_the_timeout_is_undecided() -> None:
    w = watcher()
    assert drive(w, [seen(0), seen(50, "Bel"), seen(99, "Bel")]) is None


def test_never_appearing_past_the_timeout_reports_who_was_there_instead() -> None:
    w = watcher()
    outcome = drive(w, [seen(0), seen(100, "Bel", "Ash")])
    assert outcome is not None
    assert outcome.verdict is Verdict.NEVER_APPEARED
    assert outcome.others_online == ("Ash", "Bel")


def test_present_at_the_first_poll_refuses_rather_than_passing() -> None:
    w = watcher()
    outcome = drive(w, [seen(0, "Kai")])
    assert outcome is not None
    assert outcome.verdict is Verdict.ALREADY_ONLINE
    assert "Log out" in outcome.detail


def test_present_at_the_first_poll_is_allowed_when_asked_for() -> None:
    w = watcher(allow_already_online=True)
    outcome = drive(w, [seen(0, "Kai"), seen(40, "Kai")])
    assert outcome is not None
    assert outcome.verdict is Verdict.JOINED
    assert outcome.joined_after_s == 0


def test_a_transient_failure_mid_hold_does_not_report_a_drop() -> None:
    # One dropped poll is not a crash. This is the reason a failed fetch is
    # modelled as absence of information rather than absence of the player.
    w = watcher()
    outcome = drive(w, [seen(0), seen(10, "Kai"), failed(15), seen(45, "Kai")])
    assert outcome is not None
    assert outcome.verdict is Verdict.JOINED
    assert outcome.held_for_s == 35


def test_consecutive_failures_report_unreachable_not_never_appeared() -> None:
    w = watcher(max_consecutive_errors=3)
    outcome = drive(w, [seen(0), failed(5), failed(10), failed(15, "ReadTimeout: eof")])
    assert outcome is not None
    assert outcome.verdict is Verdict.UNREACHABLE
    assert "ReadTimeout" in outcome.detail


def test_failures_reset_once_the_server_answers_again() -> None:
    w = watcher(max_consecutive_errors=3)
    outcome = drive(w, [seen(0), failed(5), failed(10), seen(15), failed(20), failed(25)])
    assert outcome is None


def test_player_name_matching_ignores_case_and_surrounding_space() -> None:
    w = watcher(player="  kai  ")
    outcome = drive(w, [seen(0), seen(10, "KAI"), seen(45, "Kai")])
    assert outcome is not None
    assert outcome.verdict is Verdict.JOINED


def test_blank_name_in_the_player_list_is_not_a_player() -> None:
    w = watcher()
    outcome = drive(w, [seen(0, "Bel"), seen(100, "Bel", "   ")])
    assert outcome is not None
    assert outcome.verdict is Verdict.NEVER_APPEARED
    assert outcome.others_online == ("   ", "Bel")


def test_the_server_version_is_carried_into_the_outcome() -> None:
    w = watcher()
    outcome = drive(w, [seen(0, version="0.13.0.4"), seen(100, "Bel")])
    assert outcome is not None
    assert outcome.server_version == "0.13.0.4"


@pytest.mark.parametrize(
    ("verdict", "code"),
    [
        (Verdict.JOINED, 0),
        (Verdict.NEVER_APPEARED, 1),
        (Verdict.UNREACHABLE, 2),
        (Verdict.DROPPED, 3),
        (Verdict.ALREADY_ONLINE, 4),
    ],
)
def test_every_verdict_has_a_distinct_exit_code(verdict: Verdict, code: int) -> None:
    assert EXIT_CODES[verdict] == code


def test_every_verdict_is_mapped() -> None:
    assert set(EXIT_CODES) == set(Verdict)


INFO_URL = "http://staging.invalid:3001/info"


@respx.mock
async def test_poll_once_reads_the_player_list_and_version() -> None:
    respx.get(INFO_URL).mock(
        return_value=httpx.Response(
            200, json={"OnlinePlayersNames": ["Kai", "", "Bel"], "Version": "0.14.1.0"}
        )
    )
    async with httpx.AsyncClient() as client:
        obs = await poll_once(client, INFO_URL, at=7.0)
    assert obs.online == frozenset({"Kai", "Bel"})
    assert obs.version == "0.14.1.0"
    assert obs.error is None


@respx.mock
async def test_poll_once_turns_a_500_into_absence_of_information() -> None:
    respx.get(INFO_URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        obs = await poll_once(client, INFO_URL, at=1.0)
    # Not an empty player list. The distinction is the whole point of `None`.
    assert obs.online is None
    assert obs.error is not None


@respx.mock
async def test_poll_once_turns_a_refused_connection_into_absence_of_information() -> None:
    respx.get(INFO_URL).mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as client:
        obs = await poll_once(client, INFO_URL, at=1.0)
    assert obs.online is None
    assert "ConnectError" in (obs.error or "")


@respx.mock
def test_a_server_that_never_answers_exits_unreachable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    respx.get(INFO_URL).mock(side_effect=httpx.ConnectError("refused"))
    code = main(
        ["Kai", "--server", INFO_URL, "--interval", "0", "--timeout", "1", "--quiet", "--json"]
    )
    assert code == EXIT_CODES[Verdict.UNREACHABLE]
    assert '"verdict": "unreachable"' in capsys.readouterr().out


@respx.mock
def test_a_held_join_exits_zero_end_to_end(capsys: pytest.CaptureFixture[str]) -> None:
    respx.get(INFO_URL).mock(
        side_effect=[
            httpx.Response(200, json={"OnlinePlayersNames": ["Bel"], "Version": "0.14.1.0"}),
            httpx.Response(200, json={"OnlinePlayersNames": ["Bel", "Kai"], "Version": "0.14.1.0"}),
            httpx.Response(200, json={"OnlinePlayersNames": ["Bel", "Kai"], "Version": "0.14.1.0"}),
        ]
    )
    code = main(
        ["Kai", "--server", INFO_URL, "--interval", "0", "--hold", "0", "--quiet", "--json"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert '"verdict": "joined"' in out
    assert '"serverVersion": "0.14.1.0"' in out


def test_display_url_masks_a_host_that_is_not_a_known_public_one() -> None:
    masked = display_url("http://some-tailnet-host.example.ts.net:3001/info")
    assert masked == "http://<host>:3001/info"
    assert "tailnet" not in masked


def test_display_url_keeps_the_public_host_readable() -> None:
    assert display_url("http://eco.coilysiren.me:3001/info") == "http://eco.coilysiren.me:3001/info"


def test_display_url_reveals_on_request() -> None:
    url = "http://some-tailnet-host.example.ts.net:3001/info"
    assert display_url(url, reveal=True) == url


@respx.mock
def test_json_output_masks_the_source_url_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    url = "http://some-tailnet-host.example.ts.net:3001/info"
    respx.get(url).mock(side_effect=httpx.ConnectError("refused"))
    main(["Kai", "--server", url, "--interval", "0", "--timeout", "1", "--quiet", "--json"])
    out = capsys.readouterr().out
    assert '"sourceUrl": "http://<host>:3001/info"' in out
    assert "some-tailnet-host" not in out
