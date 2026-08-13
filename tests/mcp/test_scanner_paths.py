"""Credential-probe paths 404 instead of collecting the SPA shell (eco-app#215).

The traced operation list showed a long tail of `/.env`, `/.git/config`,
`/.aws/credentials`, `/wp-login.php` and friends against the public host —
ordinary opportunistic scanning, with `errorRate: 0` and `num4XX: 0`.

That last number was the tell. The SPA catch-all answered every one of those
with 200 and `index.html`, so nothing registered as a 4XX. Nothing sensitive
was ever served — it is the app shell, not the file — but "200 for /.env" and
"404 for /.env" read as very different postures, and the first one hides the
probes from the metrics that would show them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from eco_mcp_app.http_app import create_app


@pytest.fixture
def client(dist: Path) -> TestClient:
    """A client over an app that has a shell to serve.

    The `dist` fixture (tests/mcp/conftest.py) is load-bearing, not decoration.
    Without a build the catch-all 404s everything as the no-build hint, which
    turns the probe assertions below into tautologies and fails the SPA ones.
    """
    return TestClient(create_app())


# Exactly the paths recorded in the 24h trace sample on eco-app#215.
_PROBE_PATHS = [
    "/.env",
    "/.env.production",
    "/.env.local",
    "/.env.bak",
    "/.aws/credentials",
    "/aws-ses.json",
    "/.env.aws",
    "/.git/config",
    "/.git/HEAD",
    "/config.php",
    "/wp-config.php",
    "/stripe/.env",
    "/backend/.env",
    "/api/.env",
    "/phpinfo.php",
    "/wp-login.php",
]


@pytest.mark.parametrize("path", _PROBE_PATHS)
def test_credential_probe_paths_return_404(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404, f"{path} answered {response.status_code}"
    # And never the app shell, which is what made these look like hits.
    assert "<!doctype html>" not in response.text.lower()


@pytest.mark.parametrize("path", _PROBE_PATHS)
def test_no_probe_path_leaks_file_contents(client: TestClient, path: str) -> None:
    """The reason this stayed low severity: nothing real was ever reachable."""
    body = client.get(path).text
    for secret_marker in ("aws_access_key_id", "[core]", "ref:", "API_KEY", "password"):
        assert secret_marker not in body


@pytest.mark.parametrize("path", ["/trade", "/items", "/civics", "/map", "/some/deep/route"])
def test_real_spa_routes_still_serve_the_app(client: TestClient, path: str) -> None:
    """The 404 rule must not catch a client-side route."""
    response = client.get(path)
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


def test_well_known_is_not_treated_as_a_dotfile_probe(client: TestClient) -> None:
    # ACME challenges and security.txt are legitimate dotted paths.
    assert client.get("/.well-known/security.txt").status_code == 200
