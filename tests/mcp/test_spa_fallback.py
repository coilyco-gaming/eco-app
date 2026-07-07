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
def test_info_hard_load_renders_the_spa_not_json() -> None:
    # eco-app#96: `/info` used to be the service-discovery JSON route, so a hard
    # refresh returned JSON instead of the React Info page. It now falls through
    # to the SPA catch-all and serves the shell as HTML.
    client = TestClient(create_app())
    r = client.get("/info")
    assert r.status_code == 200
    assert "spa-shell" in r.text
    assert "application/json" not in r.headers.get("content-type", "")


@pytest.mark.usefixtures("dist")
def test_service_discovery_json_lives_under_api() -> None:
    # The service-discovery blob relocated to the `/api`-style path (eco-app#96).
    client = TestClient(create_app())
    r = client.get("/api/service")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "eco-app"
    assert body["self"] == "/api/service"
    assert body["mcp"] == "/mcp/"
    # `/info` no longer serves this blob.
    assert "service" not in client.get("/info").text


@pytest.mark.usefixtures("dist")
def test_traversal_outside_dist_gets_the_shell() -> None:
    client = TestClient(create_app())
    r = client.get("/%2e%2e/%2e%2e/etc/passwd")
    assert r.status_code == 200
    assert "spa-shell" in r.text


@pytest.mark.usefixtures("dist")
def test_jobs_page_is_spa_and_api_keeps_public_paths() -> None:
    client = TestClient(create_app())
    r = client.get("/jobs")
    assert "spa-shell" in r.text
    r = client.get("/jobs/api/v1/professions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/jobs/api/v1/meta")
    assert r.json() == {"mockData": True}


@pytest.mark.usefixtures("dist")
def test_frame_ancestors_csp_is_site_wide() -> None:
    client = TestClient(create_app())
    for path in ("/jobs", "/healthz"):
        r = client.get(path)
        assert "frame-ancestors" in r.headers.get("content-security-policy", "")


def test_no_build_returns_build_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No frontend build → no HTML surface (the old /preview redirect is gone).
    # Client routes return a 404 build hint instead.
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "missing"))
    client = TestClient(create_app(), follow_redirects=False)
    r = client.get("/server")
    assert r.status_code == 404
    assert "frontend-build" in r.text
