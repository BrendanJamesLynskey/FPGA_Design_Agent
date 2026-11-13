"""Block designs: validate, generate, check, view, annotate and compare with the netlist.

    python3 -m flow.blockdesign validate designs/<name>          # IP Integrator's validate, and more; exit 1 on an error
    python3 -m flow.blockdesign generate designs/<name>          # gen/: RTL, wrappers, address map, graph, manifest; build.yaml
    python3 -m flow.blockdesign check designs/<name>             # exit 1 if gen/ or build.yaml differ from the generator
    python3 -m flow.blockdesign view designs/<name> [--out F]    # the stand-alone viewer page (gen/viewer.html)
    python3 -m flow.blockdesign annotate designs/<name> --build designs/<name>/build/base   # Vivado: cost per block
    python3 -m flow.blockdesign hiercheck designs/<name> --record results/blockdesign/<name>/build.json

A design directory holds ``blockdesign.yaml``; a path to a .yaml file is accepted too. ``<command> --help`` describes
each command.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flow.blockdesign import model as M

HELP = {
    "validate": ("check the design and print every diagnostic (code, place, message, hint); exit 1 on an error",
                 "python3 -m flow.blockdesign validate designs/b65a_axil_soc --json /tmp/diag.json"),
    "generate": ("validate, then write gen/ (top and hierarchy RTL, AXI4-Lite wrappers, address map as C header, Markdown "
                 "and JSON, graph.json, manifest.json), build.yaml and the stand-alone viewer gen/viewer.html",
                 "python3 -m flow.blockdesign generate designs/b65a_axil_soc"),
    "check": ("the drift check: exit 1 if gen/ or build.yaml differ from what the generator writes now",
              "python3 -m flow.blockdesign check designs/b65a_axil_soc"),
    "view": ("write the stand-alone viewer page (default gen/viewer.html), merged with the build record if it was made "
             "for this graph", "python3 -m flow.blockdesign view designs/b65a_axil_soc --out /tmp/b65a.html"),
    "annotate": ("run Vivado on a routed build (about a minute) and write results/blockdesign/<name>/build.json: cost and "
                 "worst slack per block, the synthesised hierarchy, the connectivity, and the graph check; exit 1 if the "
                 "check fails", "python3 -m flow.blockdesign annotate designs/b65a_axil_soc --build designs/b65a_axil_soc/build/base"),
    "hiercheck": ("compare gen/graph.json with a build record (no Vivado): instances and modules, links as nets, the "
                  "crossbar's address map; exit 1 on a mismatch",
                  "python3 -m flow.blockdesign hiercheck designs/b65a_axil_soc --record results/blockdesign/b65a_axil_soc/build.json"),
}


def _design(p: str) -> tuple[Path, Path]:
    p = Path(p)
    if p.suffix in (".yaml", ".yml"):
        return p.parent, p
    return p, p / "blockdesign.yaml"


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m flow.blockdesign", description=__doc__.split("\n", 1)[0],
                                 epilog="Run '<command> --help' for one command.")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")
    sp = {}
    for name, (text, example) in HELP.items():
        sp[name] = sub.add_parser(name, help=text, description=text[0].upper() + text[1:] + ".", epilog=f"Example: {example}")
        sp[name].add_argument("design", help="a design directory (holding blockdesign.yaml) or a .yaml file")
    sp["validate"].add_argument("--json", type=Path, help="also write the diagnostics to this file as JSON")
    sp["view"].add_argument("--out", type=Path, help="the page to write (default gen/viewer.html)")
    sp["annotate"].add_argument("--build", type=Path, help="the build directory with post_route.dcp, gates.json and "
                                "manifest.json (default <design>/build/base)")
    sp["hiercheck"].add_argument("--record", "--hier", dest="record", type=Path, required=True,
                                 help="the build record (results/blockdesign/<name>/build.json)")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    ddir, dfile = _design(a.design)
    if not dfile.is_file():
        print(f"blockdesign: {dfile} does not exist")
        return 2
    if a.cmd == "validate":
        E = M.elaborate(dfile)
        ds = E.all_diags()
        for d in ds:
            print(d.text())
        s = M.summary(E)
        print(f"blockdesign: {E.name}: {s['errors']} errors, {s['warnings']} warnings, {s['info']} notes")
        if a.json:
            a.json.write_text(json.dumps({"summary": s, "diagnostics": [d.__dict__ for d in ds]}, indent=1) + "\n")
        return 1 if s["errors"] else 0
    from flow.blockdesign import generate
    if a.cmd == "generate":
        try:
            files = generate.write(ddir)
        except ValueError as e:
            print(e)
            return 1
        from flow.blockdesign import viewer
        out = viewer.write(ddir)
        print("\n".join(files + [str(out)]))
        return 0
    if a.cmd == "check":
        bad = generate.check(ddir)
        for b in bad:
            print(f"blockdesign: stale or unexpected: {b}")
        print("blockdesign: generated files " + ("differ from the generator" if bad else "match the generator"))
        return 1 if bad else 0
    if a.cmd == "view":
        from flow.blockdesign import viewer
        print(viewer.write(ddir, a.out))
        return 0
    if a.cmd == "annotate":
        from flow.blockdesign import annotate
        return annotate.main(ddir, a.build)
    if a.cmd == "hiercheck":
        from flow.blockdesign import hiercheck
        res = hiercheck.check_files(ddir, a.record)
        for m in res["mismatches"]:
            print(f"hiercheck: {m}")
        for m in res.get("edges_not_visible") or []:
            print(f"hiercheck: not compared: {m}")
        print(f"hiercheck: {res['matched']} of {res['expected']} RTL instances found with the module named; "
              f"{res.get('edges_matched', 0)} of {res.get('edges_expected', 0)} links found as nets; "
              f"{res.get('ranges_checked', 0)} address ranges checked; " + ("match" if res["pass"] else "MISMATCH"))
        return 0 if res["pass"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
