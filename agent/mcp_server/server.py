"""The core's tools as an MCP server (stdio): the same functions the Deep Agents agent (05b) calls in-process.

    python -m agent.mcp_server --design designs/<name> [--board nexys_a7_100t] [--hw-budget 6]

Claude Code (05c) and anyone else's MCP client get exactly the core's tool list, schemas and refusals: a
refusal is a normal tool result with ``isError: true`` and the rule in ``structuredContent``.

Protocol: the Python MCP SDK ``mcp==2.3.0`` (pinned in pyproject.toml), whose ``LATEST_PROTOCOL_VERSION`` is
``2026-07-28``; the server speaks both that era and the legacy handshake (the SDK's dual-era loop).
Tool schemas carry ``_meta["fda/schemaVersion"]`` (``agent.core.registry.SCHEMA_VERSION``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from agent.core import SCHEMA_VERSION, Session, dispatch, tool_list
from agent.core.registry import TOOLS

SERVER_NAME = "fpga-design-agent-core"


def build_server(session: Session, only: set[str] | None = None) -> Server:
    """``only``: expose just these tools (05c: the stage machine's per-stage tool list); others are not listed and
    a call to one is refused like an unknown tool."""
    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[
            types.Tool(name=t["name"], description=t["description"], input_schema=t["inputSchema"],
                       meta={"fda/schemaVersion": t["version"]}) for t in tool_list()
            if only is None or t["name"] in only])

    async def call_tool(ctx, params):
        if only is not None and params.name not in only:
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"no tool named {params.name!r}")],
                                        structured_content={"ok": False, "refused": True, "rule": "unknown-tool"},
                                        is_error=True)
        res = await anyio.to_thread.run_sync(dispatch, session, params.name, dict(params.arguments or {}))
        # Claude Code shows the model structuredContent INSTEAD of the text when there is some (a real stream shows
        # {"ok":true,...,"bytes":10424}), so the output text goes in the structured result too: without it, a
        # successful read_file, report or search_docs returned only its size (f2-stage3-io).
        structured = dict(res)
        return types.CallToolResult(content=[types.TextContent(type="text", text=res["output"])],
                                    structured_content=structured, is_error=not res["ok"])

    return Server(SERVER_NAME, version=SCHEMA_VERSION, on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(session: Session, only: set[str] | None = None) -> None:
    server = build_server(session, only)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--board", default="nexys_a7_100t")
    ap.add_argument("--hw-budget", type=int, default=6)
    ap.add_argument("--knowledge", type=Path, help="knowledge bank folder (default: FDA_KNOWLEDGE or the sibling checkout)")
    ap.add_argument("--role", choices=["clarify", "model", "tests", "rtl"],
                    help="05c: narrow the jail to a sub-agent role (agent.graph.roles), as the Deep Agents arm does")
    ap.add_argument("--stage", help="the stage name the session is in (policy and audit)")
    ap.add_argument("--tools", help="comma-separated tool names to expose (default: all)")
    a = ap.parse_args(argv)
    bank = None
    try:
        from agent.core.bank import DEFAULT_BANK, LocalBank
        bank = LocalBank(a.knowledge or DEFAULT_BANK)
    except Exception as e:                       # no bank: the docs tools say so
        print(f"fda mcp server: no knowledge bank ({type(e).__name__})", file=sys.stderr)
    session = Session(design=a.design, board=a.board, bank=bank, hw_budget=a.hw_budget)
    if a.stage:
        session.stage = a.stage
    if a.role:
        from agent.graph.roles import role_session
        session = role_session(session, a.role)
    anyio.run(serve, session, set(a.tools.split(",")) if a.tools else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
