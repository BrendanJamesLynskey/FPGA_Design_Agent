#!/usr/bin/env python3
"""The proof driver (brief 125): a model writes the proof of one or more named theorems, the Lean checker gives feedback, the statements stay frozen.

This is brief 124's loop (tools/llm_prove.py) made general: any module of this Lean project, any named theorems, the `proof` purpose of the
108 model table (Claude Code, Sonnet, by default). The human-approved file is the specification. The driver hands the model the module in
which the named theorems are proved by `sorry`, asks for the same file with a proof in each, runs `lake build` on the answer and feeds the
errors back, for at most --rounds rounds. tools/statements.py checks after every round that no definition and no theorem statement changed
(the statements are the specification; a model that edits one is told so and the round does not build). Kernel only: a model never
produces a verdict, the Lean kernel does (`#print axioms` is read from the build and shown by the traceability matrix).

Records under --out: spec_handed_to_model.lean, round<N>_answer.lean, round<N>_build.log, claude_code_calls.jsonl (the plan's cost estimate,
no dollars), proved_<Module>.lean when it builds, and result.json: per round the model seconds, the build seconds, the number and text of the
first errors; the totals; whether the first try built (`first_try_ok`); the rounds needed.

  python3 formal/lean/tools/prove.py --module Gray.Spec --theorem gray_step --theorem gray2bin_bin2gray --out results/125_lean/gray_run1 [--rounds 8]

It does not install the proved file: copy `proved_<Module>.lean` over the module when you accept the run.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEAN = HERE.parent
sys.path.insert(0, str(HERE))
from statements import check  # noqa: E402

SYSTEM = """You are a Lean 4 proof engineer. The toolchain is Lean 4.36.0 with core only (no Mathlib, no Batteries, no Aesop).
You are given a Lean file in which the named theorems are proved by `sorry`. Return the SAME file with every `sorry` replaced by a real
proof. Rules:
- Do not change any `def` and do not change any theorem statement (the statements are the specification, approved by a human; a
  script compares them). You may add helper `theorem`/`lemma` declarations before the theorem that uses them, inside the namespace.
- Do not use `sorry`, `admit`, `native_decide` or new axioms. `omega`, `simp`, `decide`, `bv_omega`, `ext`, `induction`, `bv_decide`
  (add `import Std.Tactic.BVDecide` if you use it; it only works on fixed-width goals, so it cannot prove a statement for all widths)
  are fine. Prefer proofs the kernel checks without a compiled decision procedure; the matrix records which tier each proof is in.
- Answer with the complete file in one ```lean code block and nothing else you need to explain."""


def extract(text: str) -> str:
    m = re.findall(r"```lean\n(.*?)```", text, flags=re.S)
    return (m[-1] if m else text).strip() + "\n"


def namespace_of(src: str) -> str:
    m = re.search(r"^namespace\s+(\S+)", src, flags=re.M)
    return m.group(1) if m else ""


def build(work: Path, rel: Path, ns: str, names: list[str]) -> tuple[int, str]:
    """`lake build` in the working copy, with `#print axioms` for every named theorem appended (to the copy only)."""
    src = work / rel
    keep = src.read_text()
    probe = "\n".join(f"#print axioms {ns + '.' if ns else ''}{n}" for n in names)
    src.write_text(re.sub(r"\nend " + re.escape(ns) + r"\s*$", "\n" + probe + "\nend " + ns + "\n", keep) if ns else keep + "\n" + probe + "\n")
    try:
        p = subprocess.run(["lake", "build"], cwd=work, capture_output=True, text=True, timeout=1800)
    finally:
        src.write_text(keep)
    return p.returncode, p.stdout + p.stderr


def first_errors(log: str, k: int = 3) -> list[str]:
    return [ln.strip()[:240] for ln in log.splitlines() if re.search(r"\berror\b", ln)][:k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True, help="a module of this project, for example Gray.Spec")
    ap.add_argument("--theorem", action="append", required=True, help="a theorem to prove (repeatable); the others in the file are left as they are")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--model", help="override the proof purpose's model (default: the 108 table)")
    ap.add_argument("--effort", help="override the proof purpose's effort")
    ap.add_argument("--timeout", type=float, help="seconds per model call (default: the table's)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rel = Path(*a.module.split(".")).with_suffix(".lean")
    spec = (LEAN / rel).read_text()
    ns = namespace_of(spec)
    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(LEAN, work, ignore=shutil.ignore_patterns(".lake", "tools", "records"))
    (out / "spec_handed_to_model.lean").write_text(spec)
    missing = [t for t in a.theorem if not re.search(rf"^theorem {re.escape(t)}\b", spec, flags=re.M)]
    if missing:
        sys.exit(f"no such theorem in {rel}: {', '.join(missing)}")
    all_names = re.findall(r"^theorem (\S+)", spec, flags=re.M)
    root = LEAN.parents[1]
    sys.path.insert(0, str(root))
    from agent.access import require_or_exit
    require_or_exit("formal/lean/tools/prove.py")
    from agent.models import resolver_for
    opts = {"effort": a.effort} if a.effort else None
    rs = resolver_for("proof", model=a.model, timeout_s=a.timeout, options=opts)
    ent = rs.entry("proof")
    llm = rs.text("proof", label="lean_prove", claude_log=out / "claude_code_calls.jsonl")
    t0 = time.time()
    rows, cur, feedback = [], spec, None
    forbid = r"\b(sorry|admit|native_decide|axiom)\b"
    for rnd in range(1, a.rounds + 1):
        user = ("Prove these theorems: " + ", ".join(a.theorem) + ". The file (each named theorem is `sorry`):\n```lean\n" + spec + "```\n")
        if feedback is not None:
            user += ("\nYour previous attempt:\n```lean\n" + cur + "```\nLean reported:\n```\n" + feedback[-6000:] + "\n```\nFix it and return the full file.\n")
        t1 = time.time()
        reply = llm(SYSTEM, user)
        t_model = time.time() - t1
        cur = extract(reply)
        (out / f"round{rnd}_answer.lean").write_text(cur)
        errs = check(spec, cur)
        row = {"round": rnd, "model_s": round(t_model, 1), "statement_errors": errs}
        if errs or re.search(forbid, re.sub(r"--[^\n]*", "", re.sub(r"/-.*?-/", "", cur, flags=re.S))):
            feedback = "statement/rules check failed: " + "; ".join(errs) + ("" if errs else "; the file still contains a forbidden word (sorry, admit, native_decide, axiom)")
            row.update(build_ok=False, build_s=0.0, errors=len(errs) or 1, first_errors=[feedback[:240]])
        else:
            (work / rel).write_text(cur)
            t2 = time.time()
            rc, log = build(work, rel, ns, all_names)
            (out / f"round{rnd}_build.log").write_text(log)
            row.update(build_ok=(rc == 0 and not re.search(r"\berror\b", log)), build_s=round(time.time() - t2, 1),
                       errors=len(re.findall(r"\berror\b", log)), first_errors=first_errors(log))
            feedback = log
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "first_errors"}), flush=True)
        if row["build_ok"]:
            shutil.copy2(out / f"round{rnd}_answer.lean", out / f"proved_{a.module}.lean")
            break
    solved = bool(rows and rows[-1]["build_ok"])
    res = {"module": a.module, "theorems": a.theorem, "purpose": "proof", "endpoint": ent.endpoint, "model": ent.model, "options": ent.options,
           "toolchain": (LEAN / "lean-toolchain").read_text().strip(), "rounds": rows, "solved": solved, "first_try_ok": bool(rows and rows[0]["build_ok"]),
           "rounds_used": len(rows), "model_s": round(sum(r["model_s"] for r in rows), 1), "build_s": round(sum(r["build_s"] for r in rows), 1),
           "wall_s": round(time.time() - t0, 1), "note": "statements frozen: tools/statements.py compared every answer with spec_handed_to_model.lean"}
    (out / "result.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0 if solved else 1


if __name__ == "__main__":
    sys.exit(main())
