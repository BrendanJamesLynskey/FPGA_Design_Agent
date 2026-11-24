#!/usr/bin/env python3
"""Agent fluency probe (brief 171): three small spec-to-RTL tasks, in Hardcaml and in SystemVerilog, 3 runs each, Sonnet, one model call
per attempt and no agent loop. NOT a scored eval: no pre-registration, three tasks, three runs, one model, one session.

    python3 tools/hardcaml/probe/probe.py run [--runs 3] [--rounds 2]      # writes results/b171/probe/*.json
    python3 tools/hardcaml/probe/probe.py summary

An attempt = the task text plus a one-paragraph language instruction (no example code on either side). It is built (SV: iverilog
-g2012; Hardcaml: dune build, warnings off, then the Verilog the circuit prints) and run under the shared cocotb bench
(tasks/bench_common.py: 3000 random clocks per run against a Python golden model). If it fails, up to --rounds repair attempts get
the previous code and the tool's raw error text. Recorded per run: compiled first time, passed first time, repair rounds needed,
final pass, and the provider-reported cost and tokens. Dev-set tasks only: t1_gray_stepper, t1_bcd_updown, t1_sync_fifo_regs (their cores)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "b171" / "probe"
WORK = ROOT / "build" / "hc_probe"
CWD = Path("/tmp/claude-1000/probe_cwd")     # an empty folder: no CLAUDE.md or project files reach the model
TASKS = ["gray_step", "bcd_updown", "fifo16"]
SYSTEM = "You are a concise FPGA design engineer. Reply only with what is asked, in one code block."
LANG = {
    "sv": ("Write one synthesizable SystemVerilog (IEEE 1800-2012) module for the spec below. Reply with a single ```systemverilog code block "
           "containing only the module (no testbench, no explanation)."),
    "hc": ("Write the design in Hardcaml, the open-source OCaml hardware library (hardcaml.org; OCaml 5.3, hardcaml v0.17.1; "
           "the only library available is `hardcaml`, and no ppx is used). Reply with a single ```ocaml code block that is the complete file "
           "design.ml. It must define `let circuit () : Hardcaml.Circuit.t`, built with Circuit.create_exn ~name:\"<module name from the spec>\" "
           "and the exact port names and widths of the spec (the clock input is named `clk`). It is compiled with dune next to a main that "
           "prints the circuit with Hardcaml.Rtl.print Verilog. Reply with the code block only."),
}


def ask(prompt: str) -> tuple[str, dict]:
    """One tool-less Sonnet call through the 108 model table (agent.models), logged to CWD/claude_code_calls.jsonl."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from agent.models import resolver_for
    log = CWD / "claude_code_calls.jsonl"
    n0 = len(log.read_text().splitlines()) if log.exists() else 0
    rs = resolver_for("rtl", model="sonnet", endpoint="claude_code", options={"timeout_s": 600})
    text = rs.text("rtl", label="hardcaml_probe", claude_log=log)(SYSTEM, prompt)
    rec = json.loads(log.read_text().splitlines()[n0])
    return text, {"cost_usd": rec.get("plan_cost_estimate_usd"), "input_tokens": None, "output_tokens": None, "tokens": rec.get("tokens"),
                  "model": [rec.get("model_requested")]}


def code_of(text: str) -> str:
    m = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
    return (m[0] if m else text).strip() + "\n"


def build(lang: str, task: str, code: str, d: Path) -> tuple[bool, str, Path | None]:
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    if lang == "sv":
        f = d / "design.sv"
        f.write_text(code)
        r = subprocess.run(["iverilog", "-g2012", "-o", str(d / "a.out"), str(f)], capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)[-2500:], f
    for n in ("dune-project", "dune", "emit.ml"):
        shutil.copy(HERE / "scaffold" / n, d / n)
    (d / "design.ml").write_text(code)
    env = dict(os.environ, OPAMROOT=str(Path.home() / ".local/opt/opam"), PATH=f"{Path.home()}/.local/opt/opam-bin:" + os.environ["PATH"])
    sh = f'eval "$(opam env --switch=hardcaml-5.3.0)"; cd {d}; dune build ./emit.exe 2>&1 | head -60 && dune exec ./emit.exe > design.sv'
    r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True, env=env)
    ok = (d / "design.sv").exists() and (d / "design.sv").stat().st_size > 0 and "Error" not in r.stdout and "Error" not in r.stderr
    v = d / "design.sv"
    if ok:
        r2 = subprocess.run(["iverilog", "-g2012", "-o", str(d / "a.out"), str(v)], capture_output=True, text=True)
        ok = r2.returncode == 0
        return ok, (r2.stdout + r2.stderr)[-2500:], v
    return False, (r.stdout + r.stderr)[-2500:], None


def test(task: str, v: Path) -> tuple[bool, str]:
    from flow import cocotb_run
    try:
        cocotb_run.run(f"probe_{v.parent.name}", task, [v], f"bench_{task}", HERE / "tasks", testcase=None, extra_env={"PYTHONPATH": f"{ROOT}:{HERE / 'tasks'}"})
        return True, ""
    except BaseException as e:  # noqa: BLE001
        log = ROOT / "build" / "sim" / f"probe_{v.parent.name}" / "sim.log"
        try:
            return False, cocotb_run.failure_excerpt(log)[:2500]
        except Exception:  # noqa: BLE001
            return False, str(e)[:1500]


def one(lang: str, task: str, k: int, rounds: int) -> dict:
    spec = (HERE / "tasks" / f"{task}.md").read_text()
    prompt = f"{LANG[lang]}\n\n--- spec ---\n{spec}"
    rec = {"lang": lang, "task": task, "run": k, "attempts": []}
    prev = None
    for a in range(rounds + 1):
        text, usage = ask(prompt if prev is None else
                          f"{prompt}\n\n--- your previous answer ---\n```\n{prev[0]}```\n\n--- the tool's output ---\n{prev[1]}\n\nFix it. Reply with the complete corrected file in one code block.")
        code = code_of(text)
        d = WORK / f"{lang}_{task}_r{k}_a{a}"
        ok, err, v = build(lang, task, code, d)
        passed, terr = (test(task, v) if ok and v else (False, ""))
        rec["attempts"].append({"compiled": ok, "passed": passed, **usage, "error_head": (err if not ok else terr)[:400]})
        if passed:
            break
        prev = (code, err if not ok else terr)
        (OUT / "code").mkdir(parents=True, exist_ok=True)
        (OUT / "code" / f"{lang}_{task}_r{k}_a{a}.txt").write_text(code)
    a0 = rec["attempts"][0]
    rec.update({"compiled_first": a0["compiled"], "passed_first": a0["passed"], "final_pass": rec["attempts"][-1]["passed"],
                "rounds_to_pass": (len(rec["attempts"]) - 1) if rec["attempts"][-1]["passed"] else None,
                "cost_usd": round(sum(x["cost_usd"] or 0 for x in rec["attempts"]), 4)})
    return rec


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
    rounds = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 2
    OUT.mkdir(parents=True, exist_ok=True)
    CWD.mkdir(parents=True, exist_ok=True)
    f = OUT / "runs.jsonl"
    if cmd == "run":
        done = {(json.loads(l)["lang"], json.loads(l)["task"], json.loads(l)["run"]) for l in f.read_text().splitlines()} if f.exists() else set()
        for k in range(1, runs + 1):
            for task in TASKS:
                for lang in ("sv", "hc"):
                    if (lang, task, k) in done:
                        continue
                    rec = one(lang, task, k, rounds)
                    with f.open("a") as fh:
                        fh.write(json.dumps(rec) + "\n")
                    print(lang, task, k, "compiled_first", rec["compiled_first"], "passed_first", rec["passed_first"], "final", rec["final_pass"], "rounds", rec["rounds_to_pass"], flush=True)
    rows = [json.loads(l) for l in f.read_text().splitlines()]
    summ = {}
    for lang in ("sv", "hc"):
        rs = [r for r in rows if r["lang"] == lang]
        summ[lang] = {"runs": len(rs), "compiled_first": sum(r["compiled_first"] for r in rs), "passed_first": sum(r["passed_first"] for r in rs),
                      "final_pass": sum(r["final_pass"] for r in rs), "total_cost_usd": round(sum(r["cost_usd"] for r in rs), 3),
                      "by_task": {t: {"passed_first": sum(r["passed_first"] for r in rs if r["task"] == t), "final_pass": sum(r["final_pass"] for r in rs if r["task"] == t),
                                      "rounds": [r["rounds_to_pass"] for r in rs if r["task"] == t]} for t in TASKS}}
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(summ, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
