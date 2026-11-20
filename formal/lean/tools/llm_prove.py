#!/usr/bin/env python3
"""Let a model write the proofs of Cksum/Spec.lean, with the Lean checker's feedback (brief 124).

The human-approved file is the spec: this script gives the model the file, asks for the same file with every ``sorry``
replaced by a proof, runs ``lake build`` on the answer and feeds the errors back, for at most --rounds rounds. Statement
integrity is checked by tools/statements.py (the model may not change a def or a statement). Every round's answer, build
log and timing are kept under --out. The model call goes through the 108 table (``agent.models.resolver_for``): one
tool-less headless Claude Code call per round on the Max plan, no dollars reported.

  python3 formal/lean/tools/llm_prove.py --out results/124_lean/run1 [--model claude-sonnet-5-5] [--rounds 8]
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
You are given a Lean file in which every theorem is proved by `sorry`. Return the SAME file with every `sorry` replaced by a real
proof. Rules:
- Do not change any `def` and do not change any theorem statement (the statements are the specification, approved by a human; a
  script compares them). You may add helper `theorem`/`lemma` declarations before the theorem that uses them, inside the namespace.
- Do not use `sorry`, `admit`, `native_decide` or new axioms (the user message may add further bans). `bv_decide`, `omega`, `simp`, `decide`, `bv_omega`, `ext`, `induction`
  are fine. (`bv_decide` is a SAT-solver tactic for BitVec goals; it works on goals over fixed-width bit vectors after the
  definitions are unfolded with `simp only [...]`, and is limited by problem size.)
- Answer with the complete file in one ```lean code block and nothing else you need to explain."""


def extract(text: str) -> str:
    m = re.findall(r"```lean\n(.*?)```", text, flags=re.S)
    return (m[-1] if m else text).strip() + "\n"


def build(work: Path, names: list[str]) -> tuple[int, str]:
    src = work / "Cksum" / "Spec.lean"
    keep = src.read_text()
    src.write_text(keep.replace("\nend Cksum", "\n" + "\n".join(f"#print axioms Cksum.{n}" for n in names) + "\nend Cksum"))
    p = subprocess.run(["lake", "build"], cwd=work, capture_output=True, text=True, timeout=1800)
    src.write_text(keep)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--spec", default=str(LEAN / "Cksum" / "Spec.lean"))
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--kernel-only-from", help="a proved file that uses bv_decide: start from it and ask for the same proofs without bv_decide "
                    "(bv_decide's SAT certificate is checked by compiled code, not by the kernel alone; see the README)")
    ap.add_argument("--seed-from", help="an earlier --out directory: its round 1 answer and build log count as this run's round 1 (used once, "
                    "after a checker bug in tools/statements.py made round 2 of that run unfair; see the README's Records)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(LEAN, work, ignore=shutil.ignore_patterns(".lake", "tools", "lake-manifest.json"))
    spec = Path(a.spec).read_text()
    (out / "spec_handed_to_model.lean").write_text(spec)
    names = re.findall(r"^theorem (\S+)", spec, flags=re.M)
    root = LEAN.parents[1]
    sys.path.insert(0, str(root))
    from agent.models import resolver_for
    rs = resolver_for("rtl", model=a.model, endpoint="claude_code", options={"effort": a.effort, "timeout_s": 1500})
    llm = rs.text("rtl", label="lean_prove", claude_log=out / "claude_code_calls.jsonl")
    t0 = time.time()
    rows, cur, feedback = [], spec, None
    first = 1
    forbid = r"\b(sorry|admit|native_decide|axiom)\b"
    if a.kernel_only_from:
        forbid = r"\b(sorry|admit|native_decide|axiom|bv_decide|ofReduceBool)\b"
        cur = Path(a.kernel_only_from).read_text()
        feedback = ("The file builds, but three lemmas use `bv_decide`, whose SAT certificate is checked by compiled code and adds the axiom "
                    "`<name>._native.bv_decide.ax_*`. Policy for this round: no `bv_decide`, no `native_decide`, no new axioms. Prove the same "
                    "theorems with kernel-checked tactics only (`omega`, `bv_omega`, `simp`, `decide` on small goals, `BitVec.toNat` rewriting). "
                    "Keep every statement unchanged.")
        first = 1
    if a.seed_from:
        sd = Path(a.seed_from).resolve()
        cur = (sd / "round1_answer.lean").read_text()
        feedback = (sd / "round1_build.log").read_text()
        for f in ("round1_answer.lean", "round1_build.log"):
            shutil.copy2(sd / f, out / f)
        rows.append({"round": 1, "seeded_from": str(sd.name), "note": "round 1 of an earlier run; its model time is in that run's log"})
        first = 2
    for rnd in range(first, a.rounds + 1):
        user = "Here is the file:\n```lean\n" + spec + "```\n"
        if feedback is not None:
            user += ("\nYour previous attempt:\n```lean\n" + cur + "```\nLean reported:\n```\n" + feedback[-6000:] + "\n```\nFix it and return the full file.\n")
        t1 = time.time()
        reply = llm(SYSTEM, user)
        t_model = time.time() - t1
        cur = extract(reply)
        (out / f"round{rnd}_answer.lean").write_text(cur)
        errs = check(spec, cur)
        row = {"round": rnd, "model_s": round(t_model, 1), "statement_errors": errs}
        if errs or re.search(forbid, re.sub(r"--[^\n]*", "", cur)):
            feedback = "statement/rules check failed: " + "; ".join(errs) + ("; the file still contains a forbidden word (sorry, admit, native_decide, axiom" + (", bv_decide" if a.kernel_only_from else "") + ")" if not errs else "")
            row.update(build_ok=False, note=feedback)
        else:
            (work / "Cksum" / "Spec.lean").write_text(cur)
            t2 = time.time()
            rc, log = build(work, names)
            (out / f"round{rnd}_build.log").write_text(log)
            row.update(build_ok=(rc == 0 and "error" not in log.lower()), build_s=round(time.time() - t2, 1),
                       errors=len(re.findall(r"error", log)))
            feedback = log
        rows.append(row)
        print(json.dumps(row), flush=True)
        if row.get("build_ok"):
            shutil.copy2(out / f"round{rnd}_answer.lean", out / "proved_Spec.lean")
            break
    res = {"model": a.model, "effort": a.effort, "rounds": rows, "solved": bool(rows and rows[-1].get("build_ok")),
           "wall_s": round(time.time() - t0, 1), "axioms_expected": "propext, Classical.choice, Quot.sound, Lean.ofReduceBool (bv_decide)"}
    (out / "result.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0 if res["solved"] else 1


if __name__ == "__main__":
    sys.exit(main())
