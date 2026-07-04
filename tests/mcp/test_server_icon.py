"""The MCP initialize response advertises the Eco game icon.

Kai wants the connector tile in claude.ai (served at eco-app.coilysiren.me/mcp)
to render the Eco world-globe icon instead of a generic placeholder. The MCP
spec carries an `icons` field on the server `Implementation` metadata; the SDK
copies `InitializationOptions.icons` verbatim into `InitializeResult.serverInfo`
(mcp.server.session), so asserting the options here asserts the wire response.

Both transports are checked: the stdio path builds options via
`build_initialization_options`, and the Streamable-HTTP path (the claude.ai
connector) builds them via `Server.create_initialization_options`, which reads
the `icons=` passed to the `Server` constructor in `build_server`.
"""

from __future__ import annotations

import mcp.types as mt

from eco_mcp_app.server import build_initialization_options, build_server


def _only_icon(icons: list[mt.Icon] | None) -> mt.Icon:
    assert icons, "initialize metadata carries no icons"
    assert len(icons) == 1
    return icons[0]


def _assert_eco_icon(icon: mt.Icon) -> None:
    assert icon.mimeType == "image/png"
    assert icon.sizes == ["48x48"]
    assert icon.src.startswith("data:image/png;base64,")
    # A real 48x48 asset, not an empty/placeholder stub.
    assert len(icon.src) > 1000


def test_stdio_initialize_options_carry_eco_icon() -> None:
    icon = _only_icon(build_initialization_options(build_server()).icons)
    _assert_eco_icon(icon)


def test_http_initialize_options_carry_eco_icon() -> None:
    # The Streamable-HTTP manager calls create_initialization_options() on the
    # server, so this is exactly what the claude.ai connector sees.
    icon = _only_icon(build_server().create_initialization_options().icons)
    _assert_eco_icon(icon)


def test_initialize_result_serverinfo_carries_eco_icon() -> None:
    # Mirror the SDK's serverInfo construction (mcp.server.session) to prove the
    # icon reaches the InitializeResult the client actually deserializes.
    opts = build_server().create_initialization_options()
    result = mt.InitializeResult(
        protocolVersion=mt.LATEST_PROTOCOL_VERSION,
        capabilities=opts.capabilities,
        serverInfo=mt.Implementation(
            name=opts.server_name,
            version=opts.server_version,
            icons=opts.icons,
        ),
    )
    _assert_eco_icon(_only_icon(result.serverInfo.icons))
