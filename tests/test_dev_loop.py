"""Regression coverage for the local Eco target resolver and key wiring."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
RESOLVER = ROOT / "scripts" / "resolve-eco-target.sh"


def _command(tmp_path: Path, name: str, body: str) -> None:
    command = tmp_path / name
    command.write_text(f"#!/bin/sh\nset -eu\n{body}\n")
    command.chmod(0o755)


def _resolve(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "AWS_ARGS": str(tmp_path / "AWS_ARGS"),
        "ECO_INFO_PORT": "3001",
        "PATH": str(tmp_path),
    }
    return subprocess.run(
        [str(RESOLVER)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_resolver_uses_ssm_tailnet_target_without_retired_coily_cli(tmp_path: Path) -> None:
    _command(
        tmp_path,
        "aws",
        'printf "%s\\n" "$*" > "$AWS_ARGS"\nprintf "%s\\n" "tailnet.example.test"',
    )
    _command(tmp_path, "curl", 'case "$*" in *tailnet.example.test*) exit 0 ;; *) exit 1 ;; esac')

    result = _resolve(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "http://tailnet.example.test:3001\n"
    assert "SSM-resolved FQDN, not echoed" in result.stderr
    assert "tailnet.example.test" not in result.stderr
    assert (tmp_path / "AWS_ARGS").read_text() == (
        "ssm get-parameter --name /coilysiren/kai-server/tailnet-fqdn "
        "--with-decryption --query Parameter.Value --output text\n"
    )


def test_resolver_falls_back_to_public_host_when_ssm_is_unavailable(tmp_path: Path) -> None:
    _command(tmp_path, "aws", "exit 1")
    _command(tmp_path, "curl", "exit 1")

    result = _resolve(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "http://eco.coilysiren.me:3001\n"
    assert result.stderr == "eco target: public (eco.coilysiren.me:3001)\n"


def test_http_key_fetch_uses_aws_not_the_retired_coily_cli() -> None:
    makefile = (ROOT / "Makefile").read_text()

    http_recipe = makefile.split("http:", maxsplit=1)[1].split("http-offline:", maxsplit=1)[0]
    assert "aws ssm get-parameter --name /eco-mcp-app/api-admin-token" in http_recipe
    assert "coily" not in http_recipe
