"""Bounded, read-only access to Eco server state mounted from the host.

Every path is owned by this module. Tool callers choose fixed enum values and
bounded scalar arguments, never filesystem paths. The deployment mounts only
``Storage``, ``Configs``, ``Logs``, and ``Mods`` beneath ``ECO_STATE_DIR``.
"""

from __future__ import annotations

import itertools
import json
import os
import sqlite3
import statistics
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

STATE_DIR_ENV = "ECO_STATE_DIR"
SAVE_FILES: dict[str, str] = {
    "Game.eco": "Storage/Game.eco",
    "Game.db": "Storage/Game.db",
}
BACKUP_DIR = "Storage/Backup"
EVENT_DB = "Storage/EcoReplay.db"
EVENT_JSONL = "Storage/EcoReplay.jsonl"

KNOWN_CONFIGS: dict[str, str] = {
    "network": "Configs/Network.eco",
    "difficulty": "Configs/Difficulty.eco",
    "users": "Configs/Users.eco",
    "discord": "Configs/DiscordLink.eco",
    "mods": "Configs/Mods.diff.json",
    "world": "Configs/WorldGenerator.eco",
}

# A config diff has a fixed current/full file and a fixed diff file. Some Eco
# installations only retain one side. The result reports each side separately.
CONFIG_DIFFS: dict[str, tuple[str, str]] = {
    "network": ("Configs/Network.eco", "Configs/Network.diff.json"),
    "difficulty": ("Configs/Difficulty.eco", "Configs/Difficulty.diff.json"),
    "mods": ("Configs/Mods.original.json", "Configs/Mods.diff.json"),
    "world": ("Configs/WorldGenerator.eco", "Configs/WorldGenerator.diff.json"),
}

MOD_CONFIGS: dict[str, tuple[str, ...]] = {
    "discord_link": ("Configs/DiscordLink.eco",),
    "mighty_moose": (
        "Configs/MightyMooseCore.eco",
        "Configs/MightyMooseCore.diff.json",
    ),
    "nid_toolbox": ("Configs/NidToolbox.eco", "Configs/NidToolbox.diff.json"),
    "strange_worlds": (
        "Configs/StrangeWorlds.eco",
        "Configs/StrangeWorlds.diff.json",
    ),
}

# Each log stream is a fixed list of files/directories used by known Eco
# subsystems. Directory reads select the newest regular *.log/*.txt file.
LOG_STREAMS: dict[str, tuple[str, ...]] = {
    "server": ("Logs",),
    "mighty_moose": ("Logs/MightyMooseCore", "Logs/MightyMooseCore.log"),
    "nid_toolbox": ("Logs/NidToolbox", "Logs/NidToolbox.log"),
    "web": ("Logs/Web", "Logs/Web.log"),
    "migrations": ("Logs/Migrations", "Logs/Migrations.log"),
}

WORLD_META_KEYS = {
    "seed",
    "dimensions",
    "width",
    "height",
    "worldsize",
    "worlddimensions",
    "worldgenerator",
    "worldgeneratorversion",
    "sealevel",
    "climate",
    "meteor",
    "meteorimpactdays",
}

MAX_EVENT_LIMIT = 200
MAX_LOG_LINES = 500
MAX_LOG_MATCHES = 100
MAX_LOG_QUERY = 120
MAX_LOG_FILE_BYTES = 16 * 1024 * 1024
MAX_MODS = 500


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _bounded_int(value: int, *, low: int, high: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} must be an integer from {low} to {high}.")
    return value


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
    """Filesystem reads against a fixed Eco state root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @classmethod
    def from_env(cls) -> StateStore:
        raw = os.environ.get(STATE_DIR_ENV)
        if not raw:
            raise RuntimeError(
                f"{STATE_DIR_ENV} is unset. The /admin MCP needs its read-only Eco state root."
            )
        return cls(raw)

    def _fixed_path(self, rel: str) -> Path:
        """Resolve a module-owned path and refuse a symlink escape."""
        root = self.root.resolve()
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise RuntimeError(f"fixed Eco state path escaped {STATE_DIR_ENV}: {rel}")
        return path

    def _stat_file(self, label: str, rel: str, now: float) -> FileStat:
        path = self._fixed_path(rel)
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
        clock = time.time() if now is None else now
        files = [self._stat_file(label, rel, clock) for label, rel in SAVE_FILES.items()]
        return {"checkedAtISO": _iso(clock), "files": [item.to_dict() for item in files]}

    def backup_list(self, now: float | None = None) -> dict[str, Any]:
        clock = time.time() if now is None else now
        backup_dir = self._fixed_path(BACKUP_DIR)
        pairs: list[tuple[float, FileStat]] = []
        if backup_dir.is_dir():
            for path in backup_dir.iterdir():
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(self.root.resolve()):
                    continue
                st = resolved.stat()
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
        pairs.sort(key=lambda pair: pair[0])
        mtimes = [mtime for mtime, _ in pairs]
        gaps = [later - earlier for earlier, later in itertools.pairwise(mtimes)]
        cadence = round(statistics.median(gaps), 3) if gaps else None
        ordered = [item for _, item in pairs]
        return {
            "checkedAtISO": _iso(clock),
            "dir": BACKUP_DIR,
            "count": len(ordered),
            "cadenceSeconds": cadence,
            "newest": ordered[-1].to_dict() if ordered else None,
            "oldest": ordered[0].to_dict() if ordered else None,
            "backups": [item.to_dict() for item in reversed(ordered)],
        }

    def _read_json_or_text(self, rel: str) -> dict[str, Any]:
        path = self._fixed_path(rel)
        if not path.is_file():
            return {"path": rel, "present": False}
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            content: Any = json.loads(text)
            file_format = "json"
        except (ValueError, TypeError):
            content = text
            file_format = "text"
        return {
            "path": rel,
            "present": True,
            "format": file_format,
            "content": content,
        }

    def read_config(self, name: str) -> dict[str, Any]:
        if name not in KNOWN_CONFIGS:
            allowed = ", ".join(sorted(KNOWN_CONFIGS))
            raise KeyError(f"unknown config {name!r}; known configs: {allowed}")
        return {"name": name, **self._read_json_or_text(KNOWN_CONFIGS[name])}

    def config_diff(self, name: str) -> dict[str, Any]:
        if name not in CONFIG_DIFFS:
            allowed = ", ".join(sorted(CONFIG_DIFFS))
            raise KeyError(f"unknown config diff {name!r}; known diffs: {allowed}")
        current_rel, diff_rel = CONFIG_DIFFS[name]
        return {
            "name": name,
            "current": self._read_json_or_text(current_rel),
            "diff": self._read_json_or_text(diff_rel),
        }

    def mod_configs(self) -> dict[str, Any]:
        configs: list[dict[str, Any]] = []
        for name, candidates in MOD_CONFIGS.items():
            reads = [self._read_json_or_text(rel) for rel in candidates]
            present = next((item for item in reads if item["present"]), None)
            configs.append(
                present
                if present is not None
                else {"name": name, "path": candidates[0], "present": False}
            )
            configs[-1]["name"] = name
        return {"configs": configs}

    def world_meta(self) -> dict[str, Any]:
        result = self._read_json_or_text(KNOWN_CONFIGS["world"])
        if not result["present"] or result.get("format") != "json":
            return result
        selected: dict[str, Any] = {}

        def walk(value: Any) -> None:
            if len(selected) >= 50:
                return
            if isinstance(value, dict):
                for key, child in value.items():
                    if str(key).replace("_", "").casefold() in WORLD_META_KEYS:
                        selected[str(key)] = child
                    walk(child)
            elif isinstance(value, list):
                for child in value[:20]:
                    walk(child)

        walk(result["content"])
        result["metadata"] = selected
        result.pop("content", None)
        return result

    def _sqlite_events(self, path: Path, limit: int) -> list[dict[str, Any]]:
        uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT id, unix_time, game_time, action_type, citizen, body_json
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                body: Any = json.loads(row["body_json"])
            except (ValueError, TypeError):
                body = row["body_json"]
            events.append(
                {
                    "id": row["id"],
                    "unixTime": row["unix_time"],
                    "gameTime": row["game_time"],
                    "actionType": row["action_type"],
                    "citizen": row["citizen"],
                    "body": body,
                }
            )
        return events

    def _jsonl_events(self, path: Path, limit: int) -> list[dict[str, Any]]:
        # The migration format is append-only JSONL. A bounded deque would
        # still read the whole file, so cap the supported mirror size here.
        if path.stat().st_size > MAX_LOG_FILE_BYTES:
            raise RuntimeError(f"{EVENT_JSONL} exceeds the {MAX_LOG_FILE_BYTES}-byte read budget.")
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                events.append(value)
        return list(reversed(events[-limit:]))

    def events_recent(self, limit: int = 50) -> dict[str, Any]:
        limit = _bounded_int(limit, low=1, high=MAX_EVENT_LIMIT, label="limit")
        db_path = self._fixed_path(EVENT_DB)
        jsonl_path = self._fixed_path(EVENT_JSONL)
        if db_path.is_file():
            events = self._sqlite_events(db_path, limit)
            source = EVENT_DB
        elif jsonl_path.is_file():
            events = self._jsonl_events(jsonl_path, limit)
            source = EVENT_JSONL
        else:
            events = []
            source = None
        return {"source": source, "count": len(events), "events": events}

    def player_activity(self, limit: int = 200) -> dict[str, Any]:
        recent = self.events_recent(limit)
        counts: Counter[str] = Counter()
        actions: dict[str, Counter[str]] = {}
        for event in recent["events"]:
            citizen = str(event.get("citizen") or "unknown")
            action = str(event.get("actionType") or "unknown")
            counts[citizen] += 1
            actions.setdefault(citizen, Counter())[action] += 1
        activity = [
            {
                "citizen": citizen,
                "eventCount": count,
                "actions": dict(actions[citizen].most_common(10)),
            }
            for citizen, count in counts.most_common()
        ]
        return {
            "source": recent["source"],
            "sampleEvents": recent["count"],
            "players": activity,
        }

    def _log_file(self, stream: str) -> tuple[Path | None, str | None]:
        if stream not in LOG_STREAMS:
            allowed = ", ".join(sorted(LOG_STREAMS))
            raise KeyError(f"unknown log stream {stream!r}; known streams: {allowed}")
        candidates: list[tuple[float, Path, str]] = []
        for rel in LOG_STREAMS[stream]:
            path = self._fixed_path(rel)
            if path.is_file():
                candidates.append((path.stat().st_mtime, path, rel))
            elif path.is_dir():
                for child in path.rglob("*"):
                    if (
                        child.is_file()
                        and child.suffix.casefold() in {".log", ".txt"}
                        and child.resolve().is_relative_to(self.root.resolve())
                    ):
                        child_rel = child.resolve().relative_to(self.root.resolve()).as_posix()
                        candidates.append((child.stat().st_mtime, child, child_rel))
        if not candidates:
            return None, None
        _, path, rel = max(candidates, key=lambda item: item[0])
        return path, rel

    def _bounded_log_lines(self, stream: str) -> tuple[list[str], str | None]:
        path, rel = self._log_file(stream)
        if path is None:
            return [], None
        if path.stat().st_size > MAX_LOG_FILE_BYTES:
            raise RuntimeError(f"{rel} exceeds the {MAX_LOG_FILE_BYTES}-byte per-file read budget.")
        return path.read_text(encoding="utf-8", errors="replace").splitlines(), rel

    def log_tail(self, stream: str, lines: int = 100) -> dict[str, Any]:
        lines = _bounded_int(lines, low=1, high=MAX_LOG_LINES, label="lines")
        content, rel = self._bounded_log_lines(stream)
        selected = content[-lines:]
        return {
            "stream": stream,
            "source": rel,
            "requestedLines": lines,
            "lineCount": len(selected),
            "lines": selected,
        }

    def log_grep(self, stream: str, query: str, matches: int = 50) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty literal string.")
        if len(query) > MAX_LOG_QUERY:
            raise ValueError(f"query must be at most {MAX_LOG_QUERY} characters.")
        matches = _bounded_int(matches, low=1, high=MAX_LOG_MATCHES, label="matches")
        content, rel = self._bounded_log_lines(stream)
        needle = query.casefold()
        found = [
            {"lineNumber": number, "text": line}
            for number, line in enumerate(content, start=1)
            if needle in line.casefold()
        ][-matches:]
        return {
            "stream": stream,
            "source": rel,
            "query": query,
            "matchCount": len(found),
            "matches": found,
        }

    def _configured_mod_names(self) -> set[str]:
        result = self._read_json_or_text(KNOWN_CONFIGS["mods"])
        content = result.get("content")
        names: set[str] = set()

        def walk(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for child_key, child in value.items():
                    walk(child, str(child_key))
            elif isinstance(value, list):
                for child in value:
                    walk(child, key)
            elif isinstance(value, str) and any(
                marker in key.casefold() for marker in ("mod", "plugin", "package")
            ):
                names.add(value)

        walk(content)
        return names

    @staticmethod
    def _first_version(paths: Iterable[Path]) -> str | None:
        for path in paths:
            if not path.is_file() or path.stat().st_size > 256 * 1024:
                continue
            if path.suffix.casefold() == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                except ValueError:
                    continue
                if isinstance(data, dict):
                    for key in ("version", "Version", "modVersion", "ModVersion"):
                        if key in data and isinstance(data[key], (str, int, float)):
                            return str(data[key])
        return None

    def mods_installed(self) -> dict[str, Any]:
        root = self._fixed_path("Mods")
        if not root.is_dir():
            return {"root": "Mods", "count": 0, "mods": [], "configuredMissing": []}
        user_code = root / "UserCode"
        directories = [child for child in root.iterdir() if child.is_dir() and child != user_code]
        if user_code.is_dir():
            directories.extend(child for child in user_code.iterdir() if child.is_dir())
        unique = {child.resolve(): child for child in directories}
        mods: list[dict[str, Any]] = []
        for resolved, path in sorted(unique.items(), key=lambda item: item[1].name.casefold())[
            :MAX_MODS
        ]:
            if not resolved.is_relative_to(root.resolve()):
                continue
            manifests = [
                path / "mod.json",
                path / "manifest.json",
                path / "package.json",
            ]
            mods.append(
                {
                    "name": path.name,
                    "path": resolved.relative_to(self.root.resolve()).as_posix(),
                    "version": self._first_version(manifests),
                }
            )
        installed_names = {item["name"].casefold() for item in mods}
        configured_missing = sorted(
            name for name in self._configured_mod_names() if name.casefold() not in installed_names
        )
        return {
            "root": "Mods",
            "count": len(mods),
            "mods": mods,
            "configuredMissing": configured_missing,
        }


__all__ = [
    "CONFIG_DIFFS",
    "KNOWN_CONFIGS",
    "LOG_STREAMS",
    "MAX_EVENT_LIMIT",
    "MAX_LOG_LINES",
    "MAX_LOG_MATCHES",
    "MOD_CONFIGS",
    "StateStore",
]
