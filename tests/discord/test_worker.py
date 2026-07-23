from eco_discord.worker import build_bot


def test_worker_uses_only_non_privileged_intents(monkeypatch) -> None:
    monkeypatch.setenv("ECO_DISCORD_ECO_APP_URL", "https://eco-app.test")
    monkeypatch.setenv("ECO_DISCORD_PUBLIC_URL", "https://eco.example")
    bot = build_bot()
    assert not bot.intents.message_content
    assert not bot.intents.members
    assert not bot.intents.presences
