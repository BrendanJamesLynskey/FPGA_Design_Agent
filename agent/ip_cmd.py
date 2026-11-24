"""``python -m agent ip``: the IP-library retriever on the command line (brief 150, review 147 F2). The same functions as the
agent's ``ip_lookup`` tool (flow/iplookup.py), plus ``use``, which only the owner runs (the agent's tool never copies files).

    python -m agent ip search <words> [--part P] [--clock-ns N] [--budget dsp=0] [--need-ii N] [--objective area] [--language sv] [--json]
    python -m agent ip rank <entry> [--params K=V,..] [--part P] [--clock-ns N] [--budget dsp=0] [--need-ii N] [--objective area]
    python -m agent ip show <entry> [--params K=V,..] [--variant V] [--language sv]
    python -m agent ip use <entry> <design-dir> [--params K=V,..] [--variant V] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

HELP = """\
Look in the IP library (ip_lib/, 24 entries) before writing a block. Needs the access key like every `python -m agent` command;
runs no model, no Vivado and no simulator, and changes nothing except `use`.

What you could guess wrong:
  * search finds by meaning, not by exact words: it scores your words against each entry's name, summary, variants, interface
    and README opening (rare words count more; "ping", "TCAM", "low-pass" are understood). It needs two matching words, or the
    entry's name. When nothing reaches that, it says "nothing fits" and lists near misses: a near miss is NOT a recommendation.
  * `fits` (the entry answers the request) and a variant's `fits` (it meets your budget, clock and II) are different answers.
    A variant only fits a clock when its Fmax was MEASURED at that parameter point; otherwise the reason says "not measured".
  * costs and Fmax are Artix-7 (xc7a100tcsg324-1) measurements from ip_lib/<entry>/char/. Another part gets "no characterisation",
    not an estimate. Latency and II are the ip.yaml predictions.
  * the library is SystemVerilog only, and has no FIFO or clock-crossing block (use AMD's XPM macros). --language vhdl finds
    entries and marks them not available in VHDL.
  * the "verified" label is read from ip_lib/<entry>/verified.json (brief 144) and is "unknown" where that record is absent.
    The entry's own `declared_status` is its author's words, not a verification.
  * `use` copies the entry's rtl/ into <design>/ip/<entry>/ and adds a FROZEN component to the design's project.yaml, which
    must already exist (it never creates a managed project, never edits build.yaml: it prints the sources line to add).
    The agent cannot do this; the manifest is the owner's.
"""


def _kv(text: str) -> dict:
    from flow import ipvariants as iv
    return iv._kv(text)


def use(block: str, design: Path, params: dict, variant: str | None, dry_run: bool) -> tuple[int, str]:
    from flow import ipvariants as iv, iplookup as il
    from agent.core import managed
    y = iv._yaml(block)
    design = Path(design).resolve()
    manifest = design / managed.MANIFEST
    if not manifest.is_file():
        return 2, (f"ip use: {design} has no project.yaml. `use` adds a frozen component to an existing managed project "
                   f"(agent/core/managed.py); it does not create one. Copy ip_lib/{block}/rtl by hand, or make the project first "
                   f"(python -m agent project ...).")
    raw = yaml.safe_load(manifest.read_text())
    if any(c.get("name") == block for c in raw.get("components", [])):
        return 2, f"ip use: project.yaml already has a component named {block}"
    if "sv" not in il.languages(block):
        return 2, f"ip use: {block} has no SystemVerilog source"
    rtl = [Path(p) for p in y.get("rtl") or []]
    dest = design / "ip" / block
    if dest.exists():
        return 2, f"ip use: {dest} exists already; nothing copied"
    try:
        rel_design = design.relative_to(Path(managed.__file__).resolve().parents[2]).as_posix()
    except ValueError:
        rel_design = None
    srcs = [f"{rel_design}/ip/{block}/{p.as_posix()}" if rel_design else f"ip/{block}/{p.as_posix()}" for p in rtl]
    comp = {"name": block, "ownership": "frozen", "level": "rtl", "module": y.get("top", block), "instance": f"u_{block}",
            "paths": [f"ip/{block}/**"], "build_sources": srcs, "aliases": [block.replace("_", " ")],
            "description": f"library entry ip_lib/{block} {y.get('version')}: " + " ".join(str(y.get("summary", "")).split())[:160],
            "interface": {"ports": [{"name": n, "dir": d} for d, n in il._ports(block)]},
            "provenance": {"origin": f"ip_lib/{block} in this repository (copied by python -m agent ip use)",
                           "version": str(y.get("version")), "licence": "this repository's licence (LICENSE): the entry is the project's own"}}
    note = [f"component {block}: frozen, rtl, paths ip/{block}/**",
            "add to the design's build.yaml sources (not done for you): " + ", ".join(srcs),
            "instantiate with:", il.snippet(block, {**params, **({y["variant_param"]: variant} if variant and y.get("variant_param") else {})})]
    if dry_run:
        return 0, "dry run: nothing written\n" + "\n".join(note)
    new = {**raw, "components": [*raw["components"], comp]}
    errs = managed.validate(new)
    if errs:
        return 2, "ip use: the new manifest would be invalid: " + "; ".join(errs)
    for p in rtl:
        (dest / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(IPDIR(block) / p, dest / p)
    manifest.write_text(yaml.safe_dump(new, sort_keys=False))
    return 0, "copied " + ", ".join(str(dest / p) for p in rtl) + "\n" + "\n".join(note)


def IPDIR(block: str) -> Path:
    from flow import ipvariants as iv
    return iv.IP / block


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent ip", description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="action", required=True)
    s = sub.add_parser("search", help="find entries for a request in plain words")
    s.add_argument("words", nargs="+")
    s.add_argument("--part", help="device part whose measurements to use (default xc7a100tcsg324-1, the only one measured)")
    s.add_argument("--clock-ns", type=float, help="target clock period; a variant fits only if its Fmax was measured at this point and reaches it")
    s.add_argument("--budget", default="", help="what the plan has left, e.g. dsp=0,bram_tiles=2 (keys: lut, ff, lutram, bram_tiles, dsp)")
    s.add_argument("--need-ii", type=int, help="largest acceptable initiation interval in clocks")
    s.add_argument("--objective", default="area", choices=["area", "fabric", "throughput", "fmax"], help="how to order the variants that fit (default area)")
    s.add_argument("--language", default="sv", choices=["sv", "v", "vhdl"], help="the language you need (the library has sv only)")
    s.add_argument("--params", default="", help="parameter point, e.g. TAPS=32 (other parameters keep their defaults)")
    s.add_argument("-k", type=int, default=3, help="entries to show (default 3)")
    s.add_argument("--json", action="store_true")
    r = sub.add_parser("rank", help="rank one entry's variants against a budget, clock and II (flow.ipvariants.choose)")
    r.add_argument("entry")
    r.add_argument("--params", default=""), r.add_argument("--part"), r.add_argument("--clock-ns", type=float)
    r.add_argument("--budget", default=""), r.add_argument("--need-ii", type=int)
    r.add_argument("--objective", default="area", choices=["area", "fabric", "throughput", "fmax"])
    w = sub.add_parser("show", help="the contract, variants, measured costs and an instantiation snippet of one entry")
    w.add_argument("entry")
    w.add_argument("--params", default=""), w.add_argument("--variant"), w.add_argument("--part")
    w.add_argument("--language", default="sv", choices=["sv", "v", "vhdl"])
    u = sub.add_parser("use", help="copy an entry into a managed design as a frozen component (owner's command)")
    u.add_argument("entry"), u.add_argument("design", type=Path)
    u.add_argument("--params", default=""), u.add_argument("--variant")
    u.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    a = ap.parse_args(argv)
    from flow import ipvariants as iv, iplookup as il
    try:
        if a.action == "search":
            res = il.lookup(" ".join(a.words), a.part, a.clock_ns, _kv(a.budget), a.need_ii, a.objective, a.language, _kv(a.params), a.k)
            print(json.dumps(res, indent=1) if a.json else il.render(res))
        elif a.action == "rank":
            print(json.dumps(iv.choose(a.entry, _kv(a.params), a.part, _kv(a.budget), a.clock_ns, a.need_ii, a.objective), indent=1))
        elif a.action == "show":
            print(json.dumps(il.show(a.entry, _kv(a.params), a.variant, a.language, a.part), indent=1))
        else:
            code, text = use(a.entry, a.design, _kv(a.params), a.variant, a.dry_run)
            print(text, file=sys.stderr if code else sys.stdout)
            return code
    except ValueError as e:
        print(f"ip: {e}", file=sys.stderr)
        return 2
    return 0
