from eco_discord.embeds import EmbedFactory, EmbedField


def test_factory_enforces_discord_limits_and_neutralizes_mentions() -> None:
    payload = EmbedFactory("Sirens").success(
        title="T" * 500,
        url="https://eco.example/info",
        description="@everyone " + "x" * 5000,
        fields=[EmbedField("#role " + "n" * 500, "@here " + "v" * 2000) for _ in range(30)],
    )

    assert len(payload.title) <= 256
    assert len(payload.description) <= 4096
    assert len(payload.fields) <= 25
    assert all(len(field.name) <= 256 and len(field.value) <= 1024 for field in payload.fields)
    assert (
        sum(
            len(x)
            for x in [
                payload.title,
                payload.description,
                *(part for field in payload.fields for part in (field.name, field.value)),
            ]
        )
        <= 6000
    )
    assert "@\u200beveryone" in payload.description
    assert all("@\u200bhere" in field.value for field in payload.fields)


def test_factory_keeps_one_useful_embed_when_budget_is_exhausted() -> None:
    payload = EmbedFactory("Sirens").error(
        title="error", url="https://eco.example", description="x" * 9999
    )
    assert payload.title == "error"
    assert payload.description.endswith("…")
