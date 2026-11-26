#!/usr/bin/env python3
"""The board catalogue (brief 95): which boards the agent can target, how far each has been checked, and the table.

    python3 flow/board_catalogue.py table [--write]     # the trust table (docs/board_catalogue.md)
    python3 flow/board_catalogue.py resolve "<request text>"   # the board a request names
    python3 flow/board_catalogue.py check               # the catalogue's own consistency checks; exit 1 on a problem

``boards/catalogue.yaml`` lists every board with its aliases, whether the agent can write constraints for it
(``targetable``), what the installed Vivado licence allows (``licence_tier``) and the **declared** trust label with
the evidence paths behind it. The label is computed from the evidence on disk; a declared label above the computed one
is a failure, so a label never rises without its evidence:

* ``documented``: the board file exists and every fact in it names a source (or says it is unconfirmed, and why);
* ``built``: ``results/95_boards/<board>/smoke.json`` records a smoke design that went through post-route and the
  bitstream with the board's constraints, DRC and methodology clean, and its XDC hash is the hash of the committed
  smoke XDC, which is itself regenerated from the board file (``tools/board_smoke.py``);
* ``hardware``: the catalogue lists run records of that board on the owner's real board, and they exist.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOARDS = ROOT / "boards"
LABELS = ("documented", "built", "hardware")
TABLE = ROOT / "docs" / "board_catalogue.md"
V2 = "fpga-design-agent/board/v2"


def load() -> dict[str, dict[str, Any]]:
    return yaml.safe_load((BOARDS / "catalogue.yaml").read_text())["boards"]


def board_yaml(board: str) -> dict[str, Any]:
    return yaml.safe_load((BOARDS / board / "board.yaml").read_text())


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def resolve(text: str) -> tuple[str | None, list[str]]:
    """The board a request names: ``(board, [])`` when exactly one board is named, ``(None, candidates)`` when several are
    (the request is ambiguous: say which) and ``(None, [])`` when none is. Matching is on whole words of the board id, its
    display name and its aliases; a shorter alias inside a longer matched one ("arty a7" inside "arty a7 100t") does not count."""
    t = " " + _norm(text) + " "
    found: list[tuple[str, str, bool]] = []
    for b, e in load().items():
        keys = {_norm(b), _norm(e.get("display", ""))} | {_norm(a) for a in e.get("aliases", [])}
        for k in filter(None, keys):
            m = re.search(rf" {re.escape(k)} (\S*)", t)
            if m:
                found.append((b, k, bool(re.match(r"\d", m.group(1))) or m.group(1) in {_norm(w) for w in e.get("other_models_after", [])}))
    # a shorter alias inside a longer matched one does not count; then a digit-led word after an alias ("arty s7 25",
    # "nexys a7 50t") names another model the catalogue does not have, so that alias does not count either; so does a word the entry lists
    # under other_models_after (brief 225: "stemlab 125 14 gen 2" is another board than the original generation)
    live = [(b, k, d) for b, k, d in found if not any(k != k2 and f" {k} " in f" {k2} " for _, k2, _ in found)]
    keep = {b for b, k, d in live if not d}
    if not keep:
        return None, []
    return (next(iter(keep)), []) if len(keep) == 1 else (None, sorted(keep))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smoke_evidence(board: str) -> tuple[bool, str]:
    """Does the board's smoke record prove ``built``? ``(ok, why not)``."""
    rec = ROOT / "results" / "95_boards" / board / "smoke.json"
    if not rec.is_file():
        return False, "no smoke record"
    import json
    r = json.loads(rec.read_text())
    xdc = BOARDS / board / "smoke" / "design.xdc"
    if r.get("board") != board:
        return False, "the record names another board"
    top = BOARDS / board / "smoke" / "top.sv"
    if not xdc.is_file() or r.get("xdc_sha256") != sha256(xdc):
        return False, "the record's XDC hash is not the committed smoke XDC's"
    if not top.is_file() or r.get("top_sha256") != sha256(top):
        return False, "the record's top.sv hash is not the committed smoke top's"
    if r.get("part") != board_yaml(board)["part"]:
        return False, "the record's part is not the board's part"
    if not str(r.get("vivado_version", "")).startswith("2026.1"):
        return False, "the record is not a Vivado 2026.1 build"
    g = r.get("gates", {})
    need = ("post_route_timing", "drc", "methodology", "bitstream")
    bad = [k for k in need if g.get(k) is not True]
    if bad or r.get("passed") is not True:
        return False, "gate(s) not passed: " + ", ".join(bad or ["passed"])
    return True, ""


def built_records_ok(entry: dict[str, Any], board_part: str = "") -> tuple[bool, str]:
    """A board with no smoke design can still be ``built`` by listed earlier builds (``evidence.built``: paths of
    ``gates.json`` files made with the board's constraints): each must exist, pass every gate and be a 2026.1 build."""
    import json
    paths = (entry.get("evidence") or {}).get("built") or []
    if not paths:
        return False, "no build record listed"
    for p in paths:
        f = ROOT / p
        if not f.is_file():
            return False, f"{p} does not exist"
        g = json.loads(f.read_text())
        if g.get("pass") is not True or not g.get("gates", {}).get("bitstream_present") or not str(g.get("vivado_version", "")).startswith("2026.1"):
            return False, f"{p} is not a passing 2026.1 build with a bitstream"
        man = f.parent / "manifest.json"
        if man.is_file() and board_part and board_part not in man.read_text():
            return False, f"{p}: its manifest does not name the board's part {board_part}"
    return True, ""


def built_ok(board: str, entry: dict[str, Any]) -> tuple[bool, str]:
    ok, why = smoke_evidence(board)
    if ok:
        return True, ""
    ok2, why2 = built_records_ok(entry, board_yaml(board)["part"])
    return ok2, (why if not (entry.get("evidence") or {}).get("built") else why2)


def computed_trust(board: str, entry: dict[str, Any]) -> str:
    hw = (entry.get("evidence") or {}).get("hardware") or []
    if hw and all((ROOT / p).exists() for p in hw) and (board_yaml(board).get("hardware_use") or {}).get("owned", entry.get("legacy", False)):
        return "hardware"          # only a board the owner has; a legacy board file has no hardware_use, its catalogue entry says so
    if built_ok(board, entry)[0]:
        return "built"
    return "documented"


def problems() -> list[str]:
    out: list[str] = []
    cat = load()
    dirs = {p.parent.name for p in BOARDS.glob("*/board.yaml")}
    for b in sorted(dirs - set(cat)):
        out.append(f"{b}: has a board.yaml but is not in boards/catalogue.yaml")
    for b in sorted(set(cat) - dirs):
        out.append(f"{b}: is in the catalogue but has no boards/{b}/board.yaml")
    defaults: dict[str, list[str]] = {}
    for b, e in cat.items():
        if b not in dirs:
            continue
        got, want = computed_trust(b, e), e.get("trust")
        if want not in LABELS:
            out.append(f"{b}: trust {want!r} is not one of {LABELS}")
        elif LABELS.index(want) > LABELS.index(got):
            out.append(f"{b}: declared trust {want!r} is above the evidence ({got!r}: {built_ok(b, e)[1]})")
        elif want != got:
            out.append(f"{b}: declared {want!r} but the evidence supports {got!r}: raise the label (or keep the evidence)")
        for p in (e.get("evidence") or {}).get("hardware") or []:
            if not (ROOT / p).exists():
                out.append(f"{b}: hardware evidence {p} does not exist")
        if e.get("default_for_part"):
            defaults.setdefault(board_yaml(b)["part"], []).append(b)
    by_part: dict[str, list[str]] = {}
    for b in dirs & set(cat):
        by_part.setdefault(board_yaml(b)["part"], []).append(b)
    for part, bs in by_part.items():
        if len(bs) > 1 and len(defaults.get(part, [])) != 1 and part in {board_yaml(b)["part"] for b in bs if cat[b].get("legacy")}:
            out.append(f"part {part}: boards {sorted(bs)} share it and no single board is default_for_part (designs without a "
                       f"build.yaml board would lose the board's thermal environment)")
    return out


def _scope(e: dict[str, Any]) -> str:
    return e.get("scope", "")


def table() -> str:
    cat = load()
    rows = []
    for b, e in cat.items():
        y = board_yaml(b)
        smoke = "yes" if smoke_evidence(b)[0] else ("earlier build (not a smoke design)" if built_records_ok(e, y["part"])[0] else None) or ("not built: " + e["smoke_note"] if e.get("smoke_note") else "no")
        rows.append(f"| `{b}` | {e['display']} | `{y['part']}` | {y.get('family', '')} | {computed_trust(b, e)} | "
                    f"{e.get('licence_tier', '')} | {'yes' if e.get('targetable') else 'no'} | {smoke} | {_scope(e)} |")
    head = ["# Board catalogue and trust labels", "",
            "Generated by `python3 flow/board_catalogue.py table --write`; do not edit by hand. A test fails if this file is stale.", "",
            "What each label means (computed from evidence on disk, never declared above it):", "",
            "- **documented**: the board file exists in `boards/<board>/` and every fact in it cites a source or says it is unconfirmed and why. Nothing was built or run.",
            "- **built**: a generated smoke design (clock, LEDs, a button or switch, the UART where the board has a PL UART) went through post-route and the bitstream on that part with the board's own constraints, "
            "with DRC and methodology clean. The record is `results/95_boards/<board>/smoke.json`. Nothing was run on a board.",
            "- **hardware**: run on a real board that the owner has, with run records in the repository. The scope column says what those runs covered.", "",
            "Licence tier: `free` means the installed Vivado licence (Basic tier, 2026.1) implements the part, as the probe or a build shows; "
            "`unverified` means the probe took the part through synthesis, placement and routing but no bitstream was tried. `paid` would mean the licence refuses the part (no board is in that state: the probe and the smoke builds took every part tried, including the Artix-7 200T and Kintex-7 325T, through the bitstream where a smoke design exists). Targetable: the agent can write the board's constraints "
            "from its resource names; `no` means the board has no PL clock or no usable pin list yet (see the board's known gaps).", "",
            "| Board id | Board | Part | Family | Trust | Licence tier | Targetable | Smoke build | Scope of the evidence |",
            "|---|---|---|---|---|---|---|---|---|"]
    cfg = yaml.safe_load((BOARDS / "catalogue.yaml").read_text())
    tail = ["", "## How the boards were chosen", "", cfg["selection"].strip(), "", "## Considered and left out", ""]
    tail += [f"- **{n['board']}**: {n['reason']}." for n in cfg["not_included"]]
    return "\n".join(head + rows + tail) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["table", "resolve", "check"])
    ap.add_argument("text", nargs="?")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "table":
        t = table()
        if a.write:
            TABLE.write_text(t)
        else:
            sys.stdout.write(t)
        return 0
    if a.cmd == "resolve":
        b, cands = resolve(a.text or "")
        print(b or ("ambiguous: " + ", ".join(cands) if cands else "no board named"))
        return 0 if b else 1
    p = problems()
    for x in p:
        print(x, file=sys.stderr)
    return 1 if p else 0


if __name__ == "__main__":
    raise SystemExit(main())
