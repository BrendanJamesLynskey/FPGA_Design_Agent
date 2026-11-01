"""The MCP server: its tool list equals the core's, schemas are versioned and snapshot-tested, calls go through dispatch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio
import mcp_types as types
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agent.core import SCHEMA_VERSION, tool_list
from agent.core.session import ROOT
from agent.mcp_server.server import build_server

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_schemas.json"


def test_protocol_revision_is_pinned() -> None:
    assert types.LATEST_PROTOCOL_VERSION == "2026-07-28"


def test_tool_schemas_match_the_committed_snapshot() -> None:
    """Changing a tool's schema is a versioned event: update agent.core.registry.SCHEMA_VERSION and regenerate
    the snapshot with `python -m agent.tests.test_mcp` in the same commit."""
    snap = json.loads(SNAPSHOT.read_text())
    assert snap["schema_version"] == SCHEMA_VERSION
    assert snap["tools"] == tool_list()


def test_mcp_tool_list_equals_core_list(session) -> None:
    async def go():
        async with Client(build_server(session)) as c:
            tools = (await c.list_tools()).tools
            return tools
    tools = anyio.run(go)
    core = tool_list()
    assert [t.name for t in tools] == [t["name"] for t in core]
    for t, c in zip(tools, core):
        assert t.input_schema == c["inputSchema"] and t.description == c["description"]
        assert t.meta["fda/schemaVersion"] == c["version"]


def test_mcp_call_goes_through_the_core(session) -> None:
    async def go():
        async with Client(build_server(session)) as c:
            ok = await c.call_tool("list_files", {})
            bad = await c.call_tool("read_file", {"path": "/etc/passwd"})
            flash = await c.call_tool("program", {"target": "flash"})
            return ok, bad, flash
    ok, bad, flash = anyio.run(go)
    assert not ok.is_error and "spec.yaml" in ok.content[0].text
    assert bad.is_error and bad.structured_content["rule"] == "path-jail"
    assert flash.is_error and flash.structured_content["rule"] == "hardware-flash"
    log = [json.loads(l) for l in (session.design / "build" / "audit.jsonl").read_text().splitlines()]
    assert [r["refused"] for r in log] == [False, True, True]


def test_mcp_over_stdio_subprocess(wd) -> None:
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "agent.mcp_server", "--design", str(wd)],
                                       cwd=str(ROOT))
        async with Client(params) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            r = await c.call_tool("read_file", {"path": "spec.yaml", "max_bytes": 40})
            return names, r
    names, r = anyio.run(go)
    assert names == [t["name"] for t in tool_list()] and "Structured spec" in r.content[0].text


if __name__ == "__main__":
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "tools": tool_list()}, indent=1) + "\n")
    print("wrote", SNAPSHOT)
