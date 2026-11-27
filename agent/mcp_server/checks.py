"""Brief 217 item 3: the check suite as a read-only MCP server, for other agents and tools.

    python -m agent.mcp_server.checks --design <folder> [--skills <knowledge bank folder>]

Exposes the checks only: ``list_checks`` (what each check stands for), ``check`` (lint, standards, resets, CDC, methodology, constants, the report
checks on a build's reports, ...), ``lint``, ``check_constraints``, ``report_digest``, ``list_files`` and ``read_file``. **No write tools**: not
``write_file``, ``board_constraints``, ``stage_note``, ``build``, ``program`` or anything that starts the board. The server never touches the folder it
is given: it works on a copy (without ``.git`` and checkpoints), so the check outputs (``build/checks``, ``build/lint``) land in the copy, which is
deleted when the server stops.

``--skills <bank>`` (off by default) adds ``skills_markdown``: the knowledge bank's skills as Markdown (the index, or one skill's text). The bank
is private; expose it only to a client the owner trusts.

Protocol and result shape are the core server's (``agent.mcp_server.server``): a refusal is a normal result with ``isError: true``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from agent.core import SCHEMA_VERSION, Session, dispatch, tool_list

SERVER_NAME = "fpga-design-agent-checks"

#: the registry tools this server exposes: all read the design or write only under build/ (never a source file)
READ_ONLY_TOOLS = ("check", "lint", "check_constraints", "report_digest", "list_files", "read_file")

#: what each check stands for (the property it guards), for a client that has not seen the suite
CHECK_PROPERTIES = {
    "lint": "the sources compile and lint clean (Verilator -Wall, Icarus elaboration), with the waivers the design declares",
    "standards": "the design meets the house RTL standards (synchronous resets, no unsynchronised crossings, AXI handshake rules)",
    "resets": "every register that needs a reset has one, and resets are synchronous except in reset synchronisers",
    "cdc": "every clock-domain crossing is a recognised synchroniser or is declared with its reason",
    "methodology": "the synthesised design has no methodology violations the tool reports (timing exceptions, clock gating, unconstrained paths)",
    "drc": "the tool's design-rule checks pass",
    "exceptions": "timing exceptions are scoped and justified",
    "io": "I/O constraints (standards, pins, delays) are complete and agree with the board",
    "clocking": "clocks are created once, on real clock inputs, with periods that match the board and the spec",
    "constants": "derived constants (design ID, clock periods) agree with the spec's quoted values",
    "control_sets": "control sets stay a small share of the device",
    "fsm": "state machines are encoded and reset in a recoverable way",
    "axi": "AXI ports follow the handshake rules",
    "doc": "the design's documentation states what a user could guess wrong",
}


def copy_design(src: Path, dst_parent: Path) -> Path:
    """A working copy of a design folder without VCS data, caches and checkpoints; the server's checks write only into it."""
    src = Path(src).resolve()
    dst = Path(dst_parent) / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.dcp", "sim_build", ".env", "*.bit"))
    return dst


def skills_markdown(bank_root: Path, name: str | None = None, limit: int = 60_000) -> str:
    """The bank's skills as Markdown: with no name, an index table (name, axis, section, description); with a name, that skill's text."""
    root = Path(bank_root)
    rows: list[tuple[str, str, str, str, Path]] = []
    for p in sorted(root.glob("*/**/SKILL.md")):
        rel = p.relative_to(root)
        if rel.parts[0] in ("benchmark_private", "eval1", "results_private", "reports", "docs"):
            continue
        meta: dict[str, str] = {}
        txt = p.read_text(errors="replace")
        if txt.startswith("---"):
            head = txt.split("---", 2)[1] if txt.count("---") >= 2 else ""
            for ln in head.splitlines():
                if ":" in ln:
                    k, _, v = ln.partition(":")
                    meta[k.strip()] = v.strip().strip('"')
        rows.append((meta.get("name", p.parent.name), meta.get("axis", rel.parts[0]), meta.get("section", ""), meta.get("description", ""), p))
    if name:
        hit = [r for r in rows if r[0] == name]
        if not hit:
            return f"no skill named {name!r}; call skills_markdown with no name for the index"
        return hit[0][4].read_text(errors="replace")[:limit]
    out = ["# Skills", "", "| name | axis | section | description |", "|---|---|---|---|"]
    out += [f"| {n} | {a} | {s} | {d[:160].replace('|', '/')} |" for n, a, s, d, _ in rows]
    return "\n".join(out)[:limit]


def build_checks_server(session: Session, bank_root: Path | None = None) -> Server:
    descs = {t["name"]: t for t in tool_list() if t["name"] in READ_ONLY_TOOLS}
    extra: list[types.Tool] = [types.Tool(
        name="list_checks", description="The checks this server can run, each with the property it stands for. No arguments.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False}, meta={"fda/schemaVersion": SCHEMA_VERSION})]
    if bank_root is not None:
        extra.append(types.Tool(
            name="skills_markdown", description="The knowledge bank's skills as Markdown: no name returns the index, a name returns that skill's text. Read-only.",
            input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}, meta={"fda/schemaVersion": SCHEMA_VERSION}))

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[
            types.Tool(name=t["name"], description=t["description"], input_schema=t["inputSchema"], meta={"fda/schemaVersion": t["version"]})
            for t in descs.values()] + extra)

    def text_result(text: str, structured: dict[str, Any], error: bool = False) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structured_content=structured, is_error=error)

    async def call_tool(ctx, params):
        args = dict(params.arguments or {})
        if params.name == "list_checks":
            body = "\n".join(f"{k}: {v}" for k, v in CHECK_PROPERTIES.items())
            return text_result(body, {"ok": True, "output": body, "checks": CHECK_PROPERTIES})
        if params.name == "skills_markdown" and bank_root is not None:
            body = await anyio.to_thread.run_sync(skills_markdown, bank_root, args.get("name"))
            return text_result(body, {"ok": True, "output": body})
        if params.name not in descs:
            return text_result(f"no tool named {params.name!r} (this server is read-only: it has no write tools)",
                               {"ok": False, "refused": True, "rule": "unknown-tool"}, True)
        res = await anyio.to_thread.run_sync(dispatch, session, params.name, args)
        return text_result(res["output"], dict(res), not res["ok"])

    return Server(SERVER_NAME, version=SCHEMA_VERSION, on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(session: Session, bank_root: Path | None = None) -> None:
    server = build_checks_server(session, bank_root)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    from agent.access import require_or_exit
    require_or_exit("agent.mcp_server.checks")
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--board", default="nexys_a7_100t")
    ap.add_argument("--skills", type=Path, help="knowledge bank folder: adds the skills_markdown tool (private content; off by default)")
    a = ap.parse_args(argv)
    tmp = Path(tempfile.mkdtemp(prefix="fda_checks_"))
    try:
        session = Session(design=copy_design(a.design, tmp), board=a.board)
        anyio.run(serve, session, a.skills)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
