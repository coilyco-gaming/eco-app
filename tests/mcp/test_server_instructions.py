"""The handshake tells a client what this server is for.

A roster carries several servers and the model has to pick one. Instructions
are how this server says which questions it answers. See
coilyco-gaming/sirens-echo#647.
"""

from eco_mcp_app.server import (
    SERVER_INSTRUCTIONS,
    build_initialization_options,
    build_server,
)


def test_both_transports_send_the_same_instructions() -> None:
    """HTTP reads the Server object and stdio builds its own options.

    They are separate code paths, so parity is asserted rather than assumed.
    """
    server = build_server()
    assert server.instructions == SERVER_INSTRUCTIONS

    options = build_initialization_options(server)
    assert options.instructions == SERVER_INSTRUCTIONS


def test_instructions_say_what_this_server_answers() -> None:
    """Selection needs distinguishing detail, not a generic policy sentence."""
    text = SERVER_INSTRUCTIONS.lower()
    for subject in ("eco", "market", "recipes", "players"):
        assert subject in text, f"instructions never mention {subject}"


def test_instructions_stay_short_enough_to_carry_every_turn() -> None:
    """A consumer inlines this into its prompt, so it is a per-turn cost."""
    assert 0 < len(SERVER_INSTRUCTIONS) <= 1024
