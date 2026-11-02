"""Who did what (brief 05d, Taylor addition 6): owner hand edits detected, committed separately, and listed.

While a run is paused for review the agent does nothing, so any change to the design directory between the stage's
snapshot (the agent's last commit) and the reply is a **hand edit by the owner**. :func:`hand_edits` finds them by
comparing the files with the snapshot's manifest (the same SHA-256 manifest the rewind verifies), skipping the
files the graph itself writes during a review (``BUILD_NOTE.md``, everything under ``build/``). The graph then
commits them as their own snapshot, author ``owner`` (``Snapshots.take(..., author="owner")``), and every
contribution goes into a ledger, ``build/who_did_what.json``, and into the build note's "who did what" table, which
the gallery reads. Each row is **owner**, **agent** or **auto** (an approval given by ``--review off``, a defaulted or
oracle-answered question).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent.graph.snapshot import manifest

LEDGER = Path("build") / "who_did_what.json"
START, END = "<!-- who-did-what:start -->", "<!-- who-did-what:end -->"
WHO = ("owner", "agent", "auto")
IGNORED = ("BUILD_NOTE.md",)


def hand_edits(design: Path, last_manifest: dict[str, str]) -> list[str]:
    """Files added, removed or changed since the agent's last snapshot, outside the files the review itself writes."""
    now = manifest(design)
    paths = sorted(p for p in set(now) | set(last_manifest) if now.get(p) != last_manifest.get(p))
    return [p for p in paths if p not in IGNORED and not p.startswith("build/")]


def load(design: Path) -> list[dict[str, Any]]:
    try:
        return json.loads((design / LEDGER).read_text())
    except (OSError, ValueError):
        return []


def record(design: Path, who: str, stage: str, what: str, detail: str = "", n: int | None = None) -> dict[str, Any]:
    """Append one contribution and rewrite the build note's table."""
    assert who in WHO, who
    rows = load(design)
    row = {"seq": len(rows), "who": who, "n": n, "stage": stage, "what": what, "detail": detail[:300],
           "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    rows.append(row)
    (design / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (design / LEDGER).write_text(json.dumps(rows, indent=1) + "\n")
    write_table(design, rows)
    return row


def table_md(rows: list[dict[str, Any]]) -> str:
    lines = ["| # | who | stage | what | detail |", "|---|---|---|---|---|"]
    for r in rows:
        cell = lambda s: str(s).replace("|", "/").replace("\n", " ")        # noqa: E731
        lines.append(f"| {r['seq'] + 1} | {r['who']} | {cell(r['stage'])} | {cell(r['what'])} | {cell(r['detail'])} |")
    tally = {w: sum(1 for r in rows if r["who"] == w) for w in WHO}
    return "## Who did what\n\n" + "\n".join(lines) + "\n\n" + ", ".join(f"{w}: {n}" for w, n in tally.items()) + "\n"


def write_table(design: Path, rows: list[dict[str, Any]]) -> None:
    f = design / "BUILD_NOTE.md"
    text = f.read_text() if f.is_file() else ""
    block = f"{START}\n{table_md(rows)}{END}\n"
    if START in text and END in text:
        a, b = text.index(START), text.index(END) + len(END)
        text = text[:a] + block.rstrip("\n") + text[b:]
    else:
        text = text.rstrip("\n") + ("\n\n" if text else "") + block
    f.write_text(text)
