import pytest

from eco_discord.worker import build_bot


def test_worker_uses_only_non_privileged_intents(monkeypatch) -> None:
    monkeypatch.setenv("ECO_DISCORD_ECO_APP_URL", "https://eco-app.test")
    monkeypatch.setenv("ECO_DISCORD_PUBLIC_URL", "https://eco.example")
    monkeypatch.setenv("ECO_DISCORD_INFO_CHANNEL_ID", "42")
    bot = build_bot()
    assert not bot.intents.message_content
    assert not bot.intents.members
    assert not bot.intents.presences


def test_worker_requires_an_info_channel_id(monkeypatch) -> None:
    monkeypatch.setenv("ECO_DISCORD_ECO_APP_URL", "https://eco-app.test")
    monkeypatch.setenv("ECO_DISCORD_PUBLIC_URL", "https://eco.example")
    monkeypatch.delenv("ECO_DISCORD_INFO_CHANNEL_ID", raising=False)
    with pytest.raises(RuntimeError, match="ECO_DISCORD_INFO_CHANNEL_ID is required"):
        build_bot()


def test_worker_requires_a_valid_info_channel_id(monkeypatch) -> None:
    monkeypatch.setenv("ECO_DISCORD_ECO_APP_URL", "https://eco-app.test")
    monkeypatch.setenv("ECO_DISCORD_PUBLIC_URL", "https://eco.example")
    monkeypatch.setenv("ECO_DISCORD_INFO_CHANNEL_ID", "not-a-channel")
    with pytest.raises(
        RuntimeError, match="ECO_DISCORD_INFO_CHANNEL_ID must be a Discord channel id"
    ):
        build_bot()
