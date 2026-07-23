"""Typed, bounded Discord embed presentation shared by every command."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

BRAND_COLOR = 0x3B8C6E
ECO_ICON_URL = "https://store.steampowered.com/favicon.ico"
MAX_TOTAL_TEXT = 6000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class EmbedKind(StrEnum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    EMPTY = "empty"
    ERROR = "error"


@dataclass(frozen=True)
class EmbedField:
    name: str
    value: str
    inline: bool = False


@dataclass(frozen=True)
class EmbedPayload:
    """Discord-library-neutral contract, intentionally easy to unit test."""

    title: str
    url: str
    description: str
    fields: tuple[EmbedField, ...] = ()
    kind: EmbedKind = EmbedKind.SUCCESS
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _clean(value: object, limit: int) -> str:
    text = _CONTROL.sub("", str(value or "")).replace("@", "@\u200b").replace("#", "#\u200b")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, max(1, limit - 1))
    return f"{text[: cut if cut > 0 else limit - 1].rstrip()}…"


class EmbedFactory:
    """The only presentation owner; handlers never instantiate Discord embeds."""

    def __init__(self, server_label: str) -> None:
        self.server_label = _clean(server_label, 120) or "Eco"

    def make(
        self,
        kind: EmbedKind,
        *,
        title: str,
        url: str,
        description: str,
        fields: list[EmbedField] | tuple[EmbedField, ...] = (),
        fetched_at: datetime | None = None,
    ) -> EmbedPayload:
        budget = MAX_TOTAL_TEXT
        safe_title = _clean(title, 256)
        budget -= len(safe_title)
        safe_description = _clean(description, min(4096, max(0, budget)))
        budget -= len(safe_description)
        bounded: list[EmbedField] = []
        for candidate in fields[:25]:
            if budget <= 0:
                break
            name = _clean(candidate.name, min(256, budget))
            budget -= len(name)
            if budget <= 0:
                break
            value = _clean(candidate.value, min(1024, budget))
            budget -= len(value)
            if name and value:
                bounded.append(EmbedField(name, value, candidate.inline))
        return EmbedPayload(
            title=safe_title or "Eco",
            url=url,
            description=safe_description or "Open Eco for the full live view.",
            fields=tuple(bounded),
            kind=kind,
            fetched_at=fetched_at or datetime.now(UTC),
        )

    def success(self, **kwargs: object) -> EmbedPayload:
        return self.make(EmbedKind.SUCCESS, **kwargs)  # type: ignore[arg-type]

    def degraded(self, **kwargs: object) -> EmbedPayload:
        return self.make(EmbedKind.DEGRADED, **kwargs)  # type: ignore[arg-type]

    def empty(self, **kwargs: object) -> EmbedPayload:
        return self.make(EmbedKind.EMPTY, **kwargs)  # type: ignore[arg-type]

    def error(self, **kwargs: object) -> EmbedPayload:
        return self.make(EmbedKind.ERROR, **kwargs)  # type: ignore[arg-type]

    def to_discord(self, payload: EmbedPayload) -> object:
        """Convert at the process edge so no handler depends on Pycord types."""
        import discord

        embed = discord.Embed(
            title=payload.title,
            url=payload.url,
            description=payload.description,
            colour=BRAND_COLOR,
            timestamp=payload.fetched_at,
        )
        embed.set_author(name="Eco", icon_url=ECO_ICON_URL)
        embed.set_footer(text=f"{self.server_label} · Live data from eco-app")
        for embed_field in payload.fields:
            embed.add_field(
                name=embed_field.name, value=embed_field.value, inline=embed_field.inline
            )
        return embed
