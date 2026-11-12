#!/usr/bin/env python3
"""Migrate an existing design to requirement tags (brief 53): propose, and with ``--write`` insert, a ``req:`` comment
for every untagged test, property and formal job, from what its testplan already says.

    python3 flow/trace_tag.py <design> [--write]

The mapping comes only from ``verif/testplan.yaml``: the ``proof:`` list (artefact -> requirement) and, where a testplan
requirement's ``id`` is a ``spec.yaml`` requirement id, its ``tests``, ``assertions``, ``cover_props`` and ``formal``.
Inserted comments say ``(from testplan)`` so a reviewer can tell a migrated tag from one a person or the tests role
wrote. Anything the testplan does not map is listed and left untagged: the gate then names it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from flow import traceability as tr
    from flow import verif_gates as vg
except ImportError:
    import traceability as tr                                  # type: ignore[no-redef]
    import verif_gates as vg                            # type: ignore[no-redef]


def mapping(plan: dict, known: set[str]) -> dict[tuple[str, str], list[str]]:
    """``(kind, name) -> [requirement ids]`` from the testplan."""
    out: dict[tuple[str, str], list[str]] = {}

    def add(kind: str, name: str, rid: str) -> None:
        ids = out.setdefault((kind, str(name)), [])
        if rid not in ids:
            ids.append(rid)
    for e in plan.get("proof") or []:
        if isinstance(e, dict) and e.get("requirement") in known:
            if e.get("method") == "simulation":
                add("test", e.get("artefact"), e["requirement"])
            elif e.get("method") == "formal":
                add("formal", e.get("artefact"), e["requirement"])
    for e in plan.get("replan") or []:
        if isinstance(e, dict) and e.get("requirement") in known and e.get("replaced_by") == "simulation":
            add("test", e.get("artefact"), e["requirement"])
    for r in plan.get("requirements") or []:
        if not isinstance(r, dict) or r.get("id") not in known:
            continue
        for t in r.get("tests") or []:
            add("test", t, r["id"])
        for a in r.get("assertions") or []:
            add("assertion", a, r["id"])
        for c in r.get("cover_props") or []:
            add("cover", c, r["id"])
        for f in r.get("formal") or []:
            add("formal", f, r["id"])
    return out


def propose(design: Path) -> tuple[list[dict], list[dict]]:
    """``(tags to insert, artefacts left untagged)``."""
    plan, spec = vg.load_inputs(design, design / "verif" / "testplan.yaml")
    known = {str(r["id"]) for r in spec.get("requirements") or [] if isinstance(r, dict) and r.get("id")}
    t = tr.build(design, None)
    mp = mapping(plan, known)
    todo, left = [], []
    for a in t["artefacts"]:
        if a["cites"] or a["class"]:
            continue
        ids = mp.get((a["kind"], a["name"]))
        (todo if ids else left).append({**a, "ids": ids or []})
    return todo, left


def insert(design: Path, todo: list[dict]) -> int:
    """Write the comments; bottom-up per file so line numbers stay valid. Returns the number inserted."""
    root = vg.ROOT
    by_file: dict[str, list[dict]] = {}
    for a in todo:
        by_file.setdefault(a["file"], []).append(a)
    n = 0
    for rel, items in by_file.items():
        p = Path(rel) if Path(rel).is_absolute() else root / rel
        lines = p.read_text().splitlines(keepends=True)
        for a in sorted(items, key=lambda x: -x["line"]):
            ids = ", ".join(a["ids"])
            if a["kind"] == "test":
                i = a["line"] - 1
                while i > 0 and lines[i - 1].lstrip().startswith("@"):
                    i -= 1
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                lines.insert(i, f"{indent}# req: {ids} (from testplan)\n")
            elif a["kind"] in ("assertion", "cover"):
                i = a["line"] - 1
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                lines.insert(i, f"{indent}// req: {ids} (from testplan)\n")
            else:                                         # formal job: a comment at the top of the .sby file
                lines.insert(0, f"# req: {ids} (from testplan)\n")
            n += 1
        p.write_text("".join(lines))
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    d = Path(a.design) if Path(a.design).is_absolute() else vg.ROOT / a.design
    todo, left = propose(d)
    for x in todo:
        print(f"tag   {x['kind']:9} {x['name']:55} -> {', '.join(x['ids'])}")
    for x in left:
        print(f"left  {x['kind']:9} {x['name']:55} (the testplan does not map it)")
    if a.write:
        print(f"inserted {insert(d, todo)} tag comment(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
