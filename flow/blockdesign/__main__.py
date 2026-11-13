"""Block designs (brief 65A): validate, generate, check, view.

    python3 -m flow.blockdesign validate designs/<name>          # IP Integrator's validate, and more; exit 1 on an error
    python3 -m flow.blockdesign generate designs/<name>          # gen/: RTL, wrappers, address map, graph, manifest; build.yaml
    python3 -m flow.blockdesign check designs/<name>             # exit 1 if gen/ or build.yaml differ from the generator
    python3 -m flow.blockdesign view designs/<name> [--out F]    # the stand-alone viewer page (gen/viewer.html)
    python3 -m flow.blockdesign annotate designs/<name> --build build/<variant>   # add the build's cost per block
    python3 -m flow.blockdesign hiercheck designs/<name> --hier F # compare the graph with a synthesised hierarchy

A design directory holds ``blockdesign.yaml``; a path to a .yaml file is accepted too.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flow.blockdesign import model as M


def _design(p: str) -> tuple[Path, Path]:
    p = Path(p)
    if p.suffix in (".yaml", ".yml"):
        return p.parent, p
    return p, p / "blockdesign.yaml"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m flow.blockdesign", description=__doc__.split("\n", 1)[0])
    ap.add_argument("cmd", choices=["validate", "generate", "check", "view", "annotate", "hiercheck"])
    ap.add_argument("design")
    ap.add_argument("--json", type=Path, help="validate: write the diagnostics here")
    ap.add_argument("--out", type=Path, help="view: the page to write (default gen/viewer.html)")
    ap.add_argument("--build", type=Path, help="annotate: the build directory (gates.json and reports)")
    ap.add_argument("--hier", type=Path, help="hiercheck: the synthesised hierarchy (JSON from annotate.tcl)")
    a = ap.parse_args(argv)
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
        res = hiercheck.check_files(ddir / "gen" / "graph.json", a.hier)
        for m in res["mismatches"]:
            print(f"hiercheck: {m}")
        print(f"hiercheck: {res['matched']} of {res['expected']} blocks found in the synthesised hierarchy; "
              + ("match" if res["pass"] else "MISMATCH"))
        return 0 if res["pass"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
