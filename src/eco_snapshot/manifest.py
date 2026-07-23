"""Snapshot manifest: a request-keyed index of captured upstream responses.

The capture side records each response under the exact path + query it was
fetched with. The serve side needs looser matching for endpoints whose query
carries volatile parameters (day ranges recomputed from the live clock), so
each path may also declare its *significant* params - the subset that
identifies the resource. `/datasets/get?dataset=X&dayStart=0&dayEnd=57` and
`...&dayEnd=91` are the same series; only `dataset` is significant.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.json"
RESPONSES_DIR = "responses"

# Query params that identify the resource for a path. Anything not listed
# here (day windows, limits) is treated as volatile and ignored by the
# fixture's fallback lookup.
SIGNIFICANT_PARAMS: dict[str, tuple[str, ...]] = {
    "/datasets/get": ("dataset",),
    "/api/v1/exporter/actions": ("actionName",),
    "/api/v1/exporter/species": ("speciesName",),
    # Replay pages are distinct only by their exclusive cursor.  ``limit`` is
    # volatile so an offline app request for 100 rows can replay the captured
    # first page of 1,000 rows.
    "/api/v1/events": ("beforeId",),
}


def canonical_query(query: str | list[tuple[str, str]]) -> str:
    """Sort query pairs so param order never affects a key."""
    pairs = parse_qsl(query, keep_blank_values=True) if isinstance(query, str) else list(query)
    return urlencode(sorted(pairs))


def request_key(path: str, query: str | list[tuple[str, str]] = "") -> str:
    canon = canonical_query(query)
    return f"{path}?{canon}" if canon else path


def resource_key(path: str, query: str | list[tuple[str, str]] = "") -> str | None:
    """Key on the significant params only; None when the path declares none."""
    significant = SIGNIFICANT_PARAMS.get(path)
    if significant is None:
        return None
    pairs = parse_qsl(query, keep_blank_values=True) if isinstance(query, str) else list(query)
    kept = [(k, v) for k, v in pairs if k in significant]
    return f"{path}?{urlencode(sorted(kept))}"


@dataclass
class Entry:
    """One captured response: where it came from and where its bytes live."""

    path: str
    query: str
    file: str
    status: int
    content_type: str

    @property
    def key(self) -> str:
        return request_key(self.path, self.query)


@dataclass
class Manifest:
    version: int = MANIFEST_VERSION
    captured_at: str = ""
    base_url: str = ""
    day_end: int = 0
    entries: list[Entry] = field(default_factory=list)
    # (path, query, reason) triples for endpoints that returned non-200 or
    # errored - recorded, never silently skipped, per the pull-everything rule.
    failures: list[dict[str, str]] = field(default_factory=list)

    def save(self, snapshot_dir: Path) -> None:
        payload = asdict(self)
        (snapshot_dir / MANIFEST_NAME).write_text(json.dumps(payload, indent=2) + "\n")

    @classmethod
    def load(cls, snapshot_dir: Path) -> Manifest:
        raw = json.loads((snapshot_dir / MANIFEST_NAME).read_text())
        entries = [Entry(**e) for e in raw.pop("entries", [])]
        return cls(**{**raw, "entries": entries})
