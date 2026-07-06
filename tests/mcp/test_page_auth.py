"""The soft page-password gate for the URL-only surfaces (eco-app#73)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eco_mcp_app import page_auth
from eco_mcp_app.http_app import create_app


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    # The SSM lookup memoizes on module globals; reset them per test and pin
    # the fallback to "nothing configured" so a stray `aws` CLI can't leak in.
    monkeypatch.setattr(page_auth, "_PASSWORD_CACHE", None)
    monkeypatch.setattr(page_auth, "_LOOKED_UP", False)
    monkeypatch.setattr(page_auth, "_fetch_from_ssm", lambda: None)
    monkeypatch.delenv("ECO_PAGE_PASSWORD", raising=False)


def test_status_reports_required_when_password_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECO_PAGE_PASSWORD", "hunter2")
    client = TestClient(create_app())
    r = client.get("/page-auth")
    assert r.status_code == 200
    assert r.json() == {"required": True}


def test_status_reports_not_required_when_unset() -> None:
    client = TestClient(create_app())
    r = client.get("/page-auth")
    assert r.status_code == 200
    assert r.json() == {"required": False}


def test_verify_accepts_the_right_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECO_PAGE_PASSWORD", "correct-horse")
    client = TestClient(create_app())
    r = client.post("/page-auth", json={"password": "correct-horse"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_verify_rejects_the_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECO_PAGE_PASSWORD", "correct-horse")
    client = TestClient(create_app())
    r = client.post("/page-auth", json={"password": "battery-staple"})
    assert r.status_code == 200
    assert r.json() == {"ok": False}


def test_verify_is_false_when_no_password_configured() -> None:
    # Nothing set anywhere: the gate stays open on the frontend, and a POST
    # never matches (there's nothing to match against).
    client = TestClient(create_app())
    r = client.post("/page-auth", json={"password": "whatever"})
    assert r.json() == {"ok": False}


def test_verify_tolerates_a_missing_or_junk_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECO_PAGE_PASSWORD", "secret")
    client = TestClient(create_app())
    r = client.post("/page-auth", content=b"not json")
    assert r.status_code == 200
    assert r.json() == {"ok": False}
    r = client.post("/page-auth", json={})
    assert r.json() == {"ok": False}
