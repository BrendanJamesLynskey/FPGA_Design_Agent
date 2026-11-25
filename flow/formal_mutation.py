#!/usr/bin/env python3
"""Mutation score of a SymbiYosys proof (brief 143c), in the style of MCY (Mutation Cover with Yosys).

The proofs of a design say "no assertion fails". How many bugs would they have noticed? This tool seeds netlist-level bugs with
Yosys's own ``mutate`` (the engine MCY drives) into the elaborated design of one sby task and re-runs that task on every mutant:

    killed     the task fails (a counterexample is found): the properties notice this bug
    survived   the task passes: either the bug cannot be seen at the properties' signals (an equivalent mutant, or logic nothing
               asserts on: a gap in the properties) or it needs more depth than the task has

    python -m flow.formal_mutation designs/b96_kr260_10g/verif/formal/rm_gp.sby --task safety_bmc --depth 24 --n 60 --seed 1 \\
        --select 'a:src=*rate_match_gp.sv* a:src=*xpm_formal.sv* %u' --json results/143c/mutation/rm_gp_safety_bmc.json

Mutations land only in the cells ``--select`` names, a Yosys selection (the property monitor and the harness must not be mutated; the front
end flattens the design, so cells are picked by the ``src`` attribute of the file they came from), at the cells ``mutate -list`` samples evenly
(cell inversions, stuck-at-0/1 of a port bit and similar). The list is
reproducible from the seed. Each mutant is a copy of the elaborated design (``model/design.il`` of the task's work directory) with one
mutation applied; the task's options (multiclock, engine) are kept and ``mode``/``depth`` are fixed by the flags, so the score
is a statement about *that task at that depth*, not about the whole proof. Survivors are reported with the RTL line they sit on.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from flow import formal_rigour as fr


def yosys(script: str, cwd: Path, env: dict) -> str:
    (cwd / "step.ys").write_text(script.replace("; ", "\n") + "\n")       # a script file: names like $paramod$..\mac_rx must not meet a shell
    r = subprocess.run(["yosys", "-q", "step.ys"], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"yosys failed: {script[:120]}\n{r.stdout[-600:]}{r.stderr[-600:]}")
    return r.stdout


def cell_wires(il_text: str, cell: str) -> list[str]:
    """The source-level names of the wires a cell connects, read from the comments of its ``connect`` lines (the model is renamed by ``rename -witness``,
    which keeps the original name in a comment). Tells which instance a flattened cell belongs to."""
    # `rename -witness` writes `cell $type $priv@N  # <the name mutate lists>`: the comment is the name
    m = re.search(r"^\s*cell \S+ \S+\s+#\s*" + re.escape(cell) + r"\s*\n(.*?)^\s*end$", il_text, re.M | re.S)
    names: list[str] = []
    for c in re.findall(r"#\s*\\\w+\s+\\(\S+)", m.group(1)) if m else []:
        if c not in names:
            names.append(c)
    return names


def annotate(rec: dict, il_text: str) -> dict:
    """Add to every mutant the wires its cell connects (``wires``, first four) and, where the mutation names one, the bit of that wire (``wirebit``)."""
    for m in rec["mutants"]:
        cm = re.search(r"-cell\s+(\S+)", m["mutation"])
        wb = re.search(r"-wirebit\s+(\d+)", m["mutation"])
        m["wires"] = cell_wires(il_text, cm.group(1))[:4] if cm else []
        m["wirebit"] = int(wb.group(1)) if wb else None
    return rec


def derive_sby(sby: Path, task: str, mode: str, depth: int, il_name: str) -> str:
    """A one-task sby file: the options and engines of ``task`` with mode and depth fixed, reading ``il_name``."""
    text = sby.read_text()
    groups = {task} | set(next((l.split()[1:] for l in fr.sby_section(text, "tasks") if l.split()[0] == task), []))
    opts = []
    for l in fr.sby_section(text, "options"):
        m = re.match(r"(\w+):\s*(.*)", l.strip())
        if m and m.group(1) in groups:
            k = m.group(2).split()[0]
            if k not in ("mode", "depth"):
                opts.append(m.group(2))
        elif not m:
            opts.append(l.strip())
    eng = "\n".join(fr.sby_section(text, "engines"))
    return f"[options]\nmode {mode}\ndepth {depth}\n" + "\n".join(opts) + f"\n\n[engines]\n{eng}\n\n[script]\nread_rtlil {il_name}\n\n[files]\n{il_name}\n"


def run(sby: Path, task: str, mode: str, depth: int, n: int, seed: int, select: str, out_dir: Path, timeout: int) -> dict:
    sby = sby.resolve()
    bindir = fr.oss_bin()
    env = dict(os.environ, PATH=(bindir + ":" if bindir else "") + os.environ.get("PATH", ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    base = fr.run_task(sby, task, out_dir / "base", bindir)         # the unmutated task: elaborated design and the control result
    il = out_dir / "base" / "model" / "design.il"
    top = re.search(r"-top\s+(\S+)", sby.read_text()).group(1)
    sel = select
    db = out_dir / "db.txt"
    yosys(f"read_rtlil {il}; mutate -list {n} -seed {seed} -o {db} {sel}", out_dir, env)
    muts = [l.strip() for l in db.read_text().splitlines() if l.strip()]
    srcdir = out_dir / "base" / "src"
    res: list[dict] = []
    for i, line in enumerate(muts, 1):
        args = re.sub(r"^(\d+\s+)?(mutate\s+)?", "", line)
        d = out_dir / f"m{i}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
        yosys(f"read_rtlil {il}; mutate {args}; write_rtlil {d / 'mutated.il'}", d, env)
        (d / "m.sby").write_text(derive_sby(sby, task, mode, depth, "mutated.il"))
        t0 = time.time()
        cmd = ["sby", "-f", "-d", "w", "m.sby"]
        if shutil.which("systemd-run"):
            cmd = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice", "-n", "10"] + cmd
        try:
            subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=timeout)
            st = (d / "w" / "status").read_text().split()[0] if (d / "w" / "status").exists() else "ABSENT"
        except subprocess.TimeoutExpired:
            st = "TIMEOUT"
        log = (d / "w" / "logfile.txt").read_text(errors="replace") if (d / "w" / "logfile.txt").exists() else ""
        failed = sorted({f.split(".")[-1] for f in re.findall(r"Assert failed in \S+: (\S+)", log)})
        mm: dict[str, str] = {}
        for k, v in (m.groups() for m in re.finditer(r"-(mode|module|cell|port|portbit|wire|src)\s+(\S+)", args)):
            mm.setdefault(k, v)                                     # the first -src is the cell's own line, the second its enclosing process
        src = mm.get("src", "")
        sm = re.match(r"([^:|]+):(\d+)", src)
        rtl_line = ""
        if sm:
            f = srcdir / Path(sm.group(1)).name
            if f.exists():
                rtl_line = f.read_text(errors="replace").splitlines()[int(sm.group(2)) - 1].strip()
        res.append({"n": i, "mutation": args.strip(), "mode": mm.get("mode"), "module": mm.get("module"), "wire": mm.get("wire"), "src": src, "rtl": rtl_line[:120],
                    "status": st, "result": "killed" if st == "FAIL" else "survived" if st == "PASS" else st.lower(), "caught_by": failed[:6],
                    "seconds": round(time.time() - t0, 1)})
        print(f"{i:>3} {res[-1]['result']:<9} {mm.get('mode', ''):<7} {mm.get('module', ''):<22} {(mm.get('wire') or '')[:28]:<28} {src[:40]}", flush=True)
        shutil.rmtree(d, ignore_errors=True)
    kinds = {k: sum(1 for r in res if r["result"] == k) for k in sorted({r["result"] for r in res})}
    rec = {"sby": fr.rel(sby), "task": task, "mode": mode, "depth": depth, "n": n, "seed": seed, "select": select, "control": base["status"],
            "tool": fr.tool_version(bindir), "summary": {"mutants": len(res), **kinds, "score": round(100 * kinds.get("killed", 0) / max(1, len(res)), 1)}, "mutants": res}
    return annotate(rec, il.read_text(errors="replace"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sby")
    ap.add_argument("--task", required=True)
    ap.add_argument("--mode", default="bmc")
    ap.add_argument("--depth", type=int, default=24)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--select", default="", help="Yosys selection of the cells to mutate (default: every cell)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per mutant")
    ap.add_argument("--work", help="work directory (default: a temporary one)")
    ap.add_argument("--json", help="write the result here")
    a = ap.parse_args(argv)
    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="mut_"))
    r = run(Path(a.sby), a.task, a.mode, a.depth, a.n, a.seed, a.select, work, a.timeout)
    print(json.dumps(r["summary"]))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(r, indent=1) + "\n")
    return 0 if r["control"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
