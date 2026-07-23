import ast
from pathlib import Path

from eco_discord.register import COMMAND_SCHEMA


def test_registration_schema_nests_the_five_commands_under_rich() -> None:
    rich = COMMAND_SCHEMA[0]["options"]
    assert [(option["name"], option["type"]) for option in rich] == [("rich", 2)]
    assert [option["name"] for option in rich[0]["options"]] == [
        "status",
        "world",
        "economy",
        "player",
        "help",
    ]


def test_worker_and_schema_have_matching_rich_command_names() -> None:
    tree = ast.parse(Path("src/eco_discord/worker.py").read_text())
    worker_commands = {
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "command"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "rich"
        for keyword in node.keywords
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant)
    }
    schema_commands = {option["name"] for option in COMMAND_SCHEMA[0]["options"][0]["options"]}
    assert worker_commands == schema_commands


def test_worker_registers_the_rich_subcommand_group() -> None:
    tree = ast.parse(Path("src/eco_discord/worker.py").read_text())
    rich_groups = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "eco"
        and node.func.attr == "create_subgroup"
    ]
    assert len(rich_groups) == 1
    worker_rich = rich_groups[0]
    schema_rich = COMMAND_SCHEMA[0]["options"][0]
    assert isinstance(worker_rich.args[0], ast.Constant)
    assert isinstance(worker_rich.args[1], ast.Constant)
    assert worker_rich.args[0].value == schema_rich["name"] == "rich"
    assert worker_rich.args[1].value == schema_rich["description"] == "Rich previews in #eco-app"


def test_worker_does_not_register_commands_during_startup() -> None:
    tree = ast.parse(Path("src/eco_discord/worker.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Attribute) and node.func.attr == "sync_commands" for node in calls
    )
