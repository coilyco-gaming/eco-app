import ast
from pathlib import Path

from eco_discord.register import COMMAND_SCHEMA


def test_registration_schema_contains_the_five_initial_commands() -> None:
    assert [option["name"] for option in COMMAND_SCHEMA[0]["options"]] == [
        "status",
        "world",
        "economy",
        "player",
        "help",
    ]


def test_worker_does_not_register_commands_during_startup() -> None:
    tree = ast.parse(Path("src/eco_discord/worker.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Attribute) and node.func.attr == "sync_commands" for node in calls
    )
