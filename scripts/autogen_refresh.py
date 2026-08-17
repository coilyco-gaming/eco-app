#!/usr/bin/env python3
"""Regenerate `data/eco_autogen_data.json` from a dedicated-server AutoGen tree.

This is a **maintenance** script, not a build step. Per the eco-app#105 finding
the app never fetches its datasets at build time, so the parsed index is vendored
in `data/` exactly like `eco_gnome_data.json`, and this script is what a human
runs when Eco ships a new version.

Two modes:

    just autogen-refresh                  # download the server, then parse
    just autogen-refresh --root PATH   # parse a server tree already on disk

The download is `steamcmd +login anonymous +app_update 739590`. No Steam account
and no game ownership are involved — SLG publishes the dedicated server as an
anonymous-login depot. It is ~514 MB, so `--root` exists for reruns.

The Steam build id from `steamapps/appmanifest_739590.acf` is recorded in the
index's `source` string, so a reader can tell exactly which server build a
recipe graph came from, and a stale vendored file is obvious rather than silent.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eco_mcp_app.autogen import AUTOGEN_SOURCE_TEMPLATE, build_index_from_autogen

ECO_SERVER_APP_ID = "739590"
# Relative to the server install root. The Linux depot nests AutoGen under
# `Mods/__core__/`, unlike the Windows layout documented on the wiki
# (`Eco_Data/Server/Mods/AutoGen`), so this path is not interchangeable.
AUTOGEN_RELATIVE = Path("Mods/__core__/AutoGen")
REPO_ROOT = Path(__file__).resolve().parent.parent
# Gzipped: the index is ~1.6 MB of generated data nobody reads by hand, and it is
# regenerable from this script. Compressing keeps it out of grep results and out
# of diffs, where 73k lines of machine output drowns real review.
OUTPUT = REPO_ROOT / "data" / "eco_autogen_data.json.gz"

_BUILD_ID_RE = re.compile(r'"buildid"\s*"(?P<value>\d+)"')


def download_server(destination: Path) -> None:
    """Fetch the dedicated server into `destination` with anonymous steamcmd."""
    if shutil.which("steamcmd") is None:
        raise SystemExit("steamcmd not found on PATH; install it or pass --root")
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "steamcmd",
            # The server we run is Linux; forcing the platform keeps a macOS or
            # Windows workstation from silently parsing a different depot.
            "+@sSteamCmdForcePlatformType",
            "linux",
            "+force_install_dir",
            str(destination),
            "+login",
            "anonymous",
            "+app_update",
            ECO_SERVER_APP_ID,
            "validate",
            "+quit",
        ],
        check=True,
    )


def read_build_id(root: Path) -> str:
    """Read the Steam build id out of the install's app manifest."""
    manifest = root / "steamapps" / f"appmanifest_{ECO_SERVER_APP_ID}.acf"
    if not manifest.is_file():
        return "unknown"
    match = _BUILD_ID_RE.search(manifest.read_text(encoding="utf-8", errors="replace"))
    return match.group("value") if match else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        help="An existing dedicated-server install root. Downloads one when omitted.",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path("/tmp/eco-dedicated-server"),
        help="Where to install the server when --root is not given.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    root = args.root
    if root is None:
        root = args.download_dir
        download_server(root)

    index = build_index_from_autogen(
        root / AUTOGEN_RELATIVE,
        source=AUTOGEN_SOURCE_TEMPLATE.format(build_id=read_build_id(root)),
    )
    payload = index.to_dict()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys so an unrelated Eco patch produces a stable ordering rather than a
    # reshuffled 1,500-recipe file, and mtime=0 so the gzip header contributes no
    # nondeterminism. The payload's own `fetchedAtISO` still changes per run, so
    # two refreshes of the same Eco build differ; compare the `source` build id
    # and the counts to tell a real content change from a re-run.
    text = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.write_bytes(gzip.compress(text.encode("utf-8"), mtime=0))

    counts = index.counts()
    print(f"wrote {args.output.relative_to(REPO_ROOT)} from {index.source}")
    print(
        "  {recipes} recipes, {skills} skills, {tags} tags, "
        "{products} products, {stations} stations".format(**counts)
    )
    for warning in index.warnings[:20]:
        print(f"  warning: {warning}")
    if len(index.warnings) > 20:
        print(f"  ... and {len(index.warnings) - 20} more warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
