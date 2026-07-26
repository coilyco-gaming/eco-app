"""Regression coverage for the local Eco target resolver and key wiring."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
RESOLVER = ROOT / "scripts" / "resolve-eco-target.sh"


def _command(tmp_path: Path, name: str, body: str) -> None:
    command = tmp_path / name
    command.write_text(f"#!/bin/sh\nset -eu\n{body}\n", newline="\n")
    command.chmod(0o755)


def _shell_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"


def _bash_executable() -> str:
    if os.name != "nt":
        return "bash"
    git = shutil.which("git")
    if git is not None:
        for parent in Path(git).resolve().parents:
            candidate = parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError("Git Bash is required to test the shell resolver on Windows")


def _resolve(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    stub_dir = shlex.quote(_shell_path(tmp_path))
    operator_args = shlex.quote(_shell_path(tmp_path / "AWS_OPERATOR_ARGS"))
    command = (
        f"PATH={stub_dir}:$PATH; export PATH; "
        f"AWS_OPERATOR_ARGS={operator_args}; export AWS_OPERATOR_ARGS; "
        "exec sh scripts/resolve-eco-target.sh"
    )
    return subprocess.run(
        [_bash_executable(), "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"ECO_INFO_PORT": "3001"},
        cwd=ROOT,
    )


def test_resolver_uses_guarded_ssm_tailnet_target(tmp_path: Path) -> None:
    _command(
        tmp_path,
        "ward-kdl",
        'printf "%s\\n" "$*" > "$AWS_OPERATOR_ARGS"\nprintf "%s\\n" "tailnet.example.test"',
    )
    _command(tmp_path, "curl", 'case "$*" in *tailnet.example.test*) exit 0 ;; *) exit 1 ;; esac')

    result = _resolve(tmp_path)

    assert result.returncode == 0, result
    assert result.stdout == "http://tailnet.example.test:3001\n", result
    assert "SSM-resolved FQDN, not echoed" in result.stderr
    assert "tailnet.example.test" not in result.stderr
    operator_args = (tmp_path / "AWS_OPERATOR_ARGS").read_text()
    assert operator_args.startswith("ops aws ssm get-parameter ")
    assert "--with-decryption --query Parameter.Value --output text" in operator_args


def test_resolver_falls_back_to_public_host_when_ssm_is_unavailable(tmp_path: Path) -> None:
    _command(tmp_path, "ward-kdl", "exit 1")
    _command(tmp_path, "curl", "exit 1")

    result = _resolve(tmp_path)

    assert result.returncode == 0, result
    assert result.stdout == "http://eco.coilysiren.me:3001\n"
    assert result.stderr == "eco target: public (eco.coilysiren.me:3001)\n"


def test_http_key_fetch_uses_guarded_aws_operator() -> None:
    dispatcher = (ROOT / "scripts" / "ward-command.sh").read_text()

    http_action = dispatcher.split("run_http() {", maxsplit=1)[1].split(
        "snapshot_temp_dir=", maxsplit=1
    )[0]
    assert "ward-kdl ops aws ssm get-parameter" in http_action
    assert "coily" not in http_action
