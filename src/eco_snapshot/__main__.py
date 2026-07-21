"""CLI for the snapshot harness: `python -m eco_snapshot capture|serve`.

The admin key is read from `UPSTREAM_API_KEY` (same env var the rest of the
dev loop uses), never from argv, so it stays out of process listings and
shell history. S3 push/pull live in the Makefile (`snapshot-push` /
`snapshot-pull`) - they are one-line `aws s3 cp` wrappers, not Python.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

DEFAULT_SNAPSHOT_DIR = ".snapshots/current"
DEFAULT_FIXTURE_PORT = 3101


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eco_snapshot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="pull every upstream endpoint into a snapshot dir")
    cap.add_argument("--base-url", required=True, help="eco server base URL (no /info suffix)")
    cap.add_argument("--out", default=DEFAULT_SNAPSHOT_DIR, help="snapshot output dir")

    srv = sub.add_parser("serve", help="replay a snapshot as a local fixture eco server")
    srv.add_argument("--dir", default=DEFAULT_SNAPSHOT_DIR, help="snapshot dir to serve")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=DEFAULT_FIXTURE_PORT)

    args = parser.parse_args(argv)

    if args.command == "capture":
        from eco_snapshot.capture import capture_snapshot

        api_key = os.environ.get("UPSTREAM_API_KEY") or None
        if not api_key:
            print(
                "warning: UPSTREAM_API_KEY unset - admin-gated endpoints will fail",
                file=sys.stderr,
            )
        manifest = asyncio.run(capture_snapshot(args.base_url, Path(args.out), api_key=api_key))
        print(
            f"captured {len(manifest.entries)} responses "
            f"({len(manifest.failures)} failures) into {args.out}"
        )
        for failure in manifest.failures:
            print(f"  failed: {failure['path']}?{failure['query']} - {failure['reason']}")
        # Failures are expected on endpoints a given server does not expose
        # (mod not deployed); a capture with zero successes is the real error.
        return 0 if manifest.entries else 1

    if args.command == "serve":
        import uvicorn

        from eco_snapshot.serve import build_app

        snapshot_dir = Path(args.dir)
        if not (snapshot_dir / "manifest.json").exists():
            print(
                f"no manifest at {snapshot_dir} - run `ward exec snapshot-pull` "
                "or `ward exec snapshot-capture` first",
                file=sys.stderr,
            )
            return 1
        app = build_app(snapshot_dir)
        print(f"fixture eco server: http://{args.host}:{args.port} (from {snapshot_dir})")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
