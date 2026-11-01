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


def build_server(session: Session) -> Server:
    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[
            types.Tool(name=t["name"], description=t["description"], input_schema=t["inputSchema"],
                       meta={"fda/schemaVersion": t["version"]}) for t in tool_list()])

    async def call_tool(ctx, params):
        res = await anyio.to_thread.run_sync(dispatch, session, params.name, dict(params.arguments or {}))
        structured = {k: v for k, v in res.items() if k != "output"}
        return types.CallToolResult(content=[types.TextContent(type="text", text=res["output"])],
                                    structured_content=structured, is_error=not res["ok"])

    return Server(SERVER_NAME, version=SCHEMA_VERSION, on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(session: Session) -> None:
    server = build_server(session)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--board", default="nexys_a7_100t")
    ap.add_argument("--hw-budget", type=int, default=6)
    ap.add_argument("--knowledge", type=Path, help="knowledge bank folder (default: FDA_KNOWLEDGE or the sibling checkout)")
    a = ap.parse_args(argv)
    bank = None
    try:
        from agent.core.bank import DEFAULT_BANK, LocalBank
        bank = LocalBank(a.knowledge or DEFAULT_BANK)
    except Exception as e:                       # no bank: the docs tools say so
        print(f"fda mcp server: no knowledge bank ({type(e).__name__})", file=sys.stderr)
    session = Session(design=a.design, board=a.board, bank=bank, hw_budget=a.hw_budget)
    anyio.run(serve, session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
