"""The catch-all SPA fallback: client-side routes survive hard refreshes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eco_mcp_app.http_app import create_app


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa-shell</html>")
    (dist / "robots.txt").write_text("crawl away")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    return dist


@pytest.mark.usefixtures("dist")
def test_client_routes_serve_the_spa_shell() -> None:
    client = TestClient(create_app())
    for path in ("/server", "/some/future/page"):
        r = client.get(path)
        assert r.status_code == 200
        assert "spa-shell" in r.text


@pytest.mark.usefixtures("dist")
def test_real_dist_files_serve_themselves() -> None:
    client = TestClient(create_app())
    r = client.get("/robots.txt")
    assert r.text == "crawl away"


@pytest.mark.usefixtures("dist")
def test_explicit_routes_still_win() -> None:
    client = TestClient(create_app())
    r = client.get("/healthz")
    assert r.json() == {"ok": True}


@pytest.mark.usefixtures("dist")
def test_traversal_outside_dist_gets_the_shell() -> None:
    client = TestClient(create_app())
    r = client.get("/%2e%2e/%2e%2e/etc/passwd")
    assert r.status_code == 200
    assert "spa-shell" in r.text


def test_no_build_falls_back_to_preview_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "missing"))
    client = TestClient(create_app(), follow_redirects=False)
    r = client.get("/server")
    assert r.status_code == 302
    assert r.headers["location"] == "/preview"
