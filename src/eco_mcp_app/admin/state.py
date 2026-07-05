"""Read-only access to a local checkout of an Eco server's state directory.

Every read here is against ``ECO_STATE_DIR`` - a *local* copy of the server's
Storage/Configs tree. Phase 1 never touches a live server. Config and save
files are addressed by a fixed enum (``KNOWN_CONFIGS`` / ``SAVE_FILES``), never
a caller-supplied path, so a tool cannot be walked into ``../../.ssh``.
"""

from __future__ import annotations

import itertools
import json
import os
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Env var pointing at the local state checkout the tools read from.
STATE_DIR_ENV = "ECO_STATE_DIR"

# The world save files, by stable label -> path relative to the state root.
# Eco writes both the save graph (Game.eco) and its SQLite sidecar (Game.db).
SAVE_FILES: dict[str, str] = {
    "Game.eco": "Storage/Game.eco",
    "Game.db": "Storage/Game.db",
}

# Where Eco rotates timestamped world backups.
BACKUP_DIR = "Storage/Backup"

# Named configs the /admin MCP will read, by enum key -> path relative to the
# state root. Enum-only on purpose: the tool exposes exactly these keys and
# never joins a caller string onto the filesystem. Both `.eco` (JSON despite
# the extension) and `.diff.json` shapes are represented.
KNOWN_CONFIGS: dict[str, str] = {
    "network": "Configs/Network.eco",
    "difficulty": "Configs/Difficulty.eco",
    "users": "Configs/Users.eco",
    "discord": "Configs/DiscordLink.eco",
    "mods": "Configs/Mods.diff.json",
}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


@dataclass(frozen=True)
class FileStat:
    """Size and age of one on-disk file, or a not-present marker."""

    label: str
    path: str
    present: bool
    size_bytes: int | None = None
    modified_iso: str | None = None
    age_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "path": self.path,
            "present": self.present,
            "sizeBytes": self.size_bytes,
            "modifiedISO": self.modified_iso,
            "ageSeconds": self.age_seconds,
        }


class StateStore:
    """Filesystem reads against a local Eco state checkout.

    Construct with an explicit root in tests. In the running service the root
    comes from ``ECO_STATE_DIR`` via ``from_env``. ``now`` is injectable so age
    math is deterministic under test.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @classmethod
    def from_env(cls) -> StateStore:
        raw = os.environ.get(STATE_DIR_ENV)
        if not raw:
            raise RuntimeError(
                f"{STATE_DIR_ENV} is unset. The /admin MCP reads a local Eco state "
                "checkout and needs its path (phase 1 is local-files-only)."
            )
        return cls(raw)

    def _stat_file(self, label: str, rel: str, now: float) -> FileStat:
        path = self.root / rel
        if not path.is_file():
            return FileStat(label=label, path=rel, present=False)
        st = path.stat()
        return FileStat(
            label=label,
            path=rel,
            present=True,
            size_bytes=st.st_size,
            modified_iso=_iso(st.st_mtime),
            age_seconds=max(0.0, round(now - st.st_mtime, 3)),
        )

    def save_status(self, now: float | None = None) -> dict[str, Any]:
        """Size and age of each world save file."""
        clock = time.time() if now is None else now
        files = [self._stat_file(label, rel, clock) for label, rel in SAVE_FILES.items()]
        return {
            "checkedAtISO": _iso(clock),
            "files": [f.to_dict() for f in files],
        }

    def backup_list(self, now: float | None = None) -> dict[str, Any]:
        """Count, cadence, and newest/oldest of the rotated world backups.

        Cadence is the median gap between consecutive backup mtimes - robust to
        an occasional missed or manual backup in a way a mean is not.
        """
        clock = time.time() if now is None else now
        backup_dir = self.root / BACKUP_DIR
        # (mtime, FileStat) pairs so cadence math and ordering share one stat().
        pairs: list[tuple[float, FileStat]] = []
        if backup_dir.is_dir():
            for path in backup_dir.iterdir():
                if not path.is_file():
                    continue
                st = path.stat()
                pairs.append(
                    (
                        st.st_mtime,
                        FileStat(
                            label=path.name,
                            path=f"{BACKUP_DIR}/{path.name}",
                            present=True,
                            size_bytes=st.st_size,
                            modified_iso=_iso(st.st_mtime),
                            age_seconds=max(0.0, round(clock - st.st_mtime, 3)),
                        ),
                    )
                )
        pairs.sort(key=lambda p: p[0])
        mtimes = [mtime for mtime, _ in pairs]
        gaps = [b - a for a, b in itertools.pairwise(mtimes)]
        cadence = round(statistics.median(gaps), 3) if gaps else None
        ordered = [stat for _, stat in pairs]
        return {
            "checkedAtISO": _iso(clock),
            "dir": BACKUP_DIR,
            "count": len(ordered),
            "cadenceSeconds": cadence,
            "newest": ordered[-1].to_dict() if ordered else None,
            "oldest": ordered[0].to_dict() if ordered else None,
            "backups": [f.to_dict() for f in reversed(ordered)],
        }

    def read_config(self, name: str) -> dict[str, Any]:
        """Read one named config by enum key.

        Rejects any name not in ``KNOWN_CONFIGS`` - the enum is the whole
        allow-list, so there is no path to traverse out of. Returns the parsed
        JSON when the file parses, else the raw text (still redactable, but
        line-by-line rather than structurally).
        """
        if name not in KNOWN_CONFIGS:
            allowed = ", ".join(sorted(KNOWN_CONFIGS))
            raise KeyError(f"unknown config {name!r}; known configs: {allowed}")
        rel = KNOWN_CONFIGS[name]
        path = self.root / rel
        if not path.is_file():
            return {"name": name, "path": rel, "present": False}
        text = path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return {"name": name, "path": rel, "present": True, "format": "text", "content": text}
        return {"name": name, "path": rel, "present": True, "format": "json", "content": parsed}
