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


def test_build_bot_works_with_no_current_event_loop(monkeypatch) -> None:
    """`main()` builds the bot before `bot.run()`, outside any loop (eco-app#248).

    Pycord resolves the ambient loop while constructing `discord.Bot`, and its
    own fallback for a missing one only covers Python 3.14+. On 3.13 — what
    this repo targets and deploys — the bare `asyncio.get_event_loop()` raised,
    so the worker died at startup instead of connecting.
    """
    import asyncio

    monkeypatch.setenv("ECO_DISCORD_ECO_APP_URL", "https://eco-app.test")
    monkeypatch.setenv("ECO_DISCORD_PUBLIC_URL", "https://eco.example")
    monkeypatch.setenv("ECO_DISCORD_INFO_CHANNEL_ID", "42")

    # Exactly the state main() runs in: a main thread with no loop set.
    previous = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(None)
    try:
        bot = build_bot()
        assert bot is not None
        # A loop is now current, which is what bot.run() will drive.
        assert asyncio.get_event_loop() is not None
    finally:
        loop = asyncio.get_event_loop()
        if loop is not previous and not loop.is_closed():
            loop.close()
        previous.close()
        asyncio.set_event_loop(None)
