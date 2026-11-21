#!/usr/bin/env python3
"""Mutation score as a headline bench metric, with formal filtering of equivalent mutants and blind mutants (brief 143b).

    python3 -m flow.mutation_score run TARGET [--seed 1] [--count 40] [--json results/143b_mutation/TARGET.json] [--no-filter]
    python3 -m flow.mutation_score show RECORD.json
    python3 -m flow.mutation_score targets

What it measures. A bench is good when it fails on a design that is wrong. Mutation testing makes wrong designs on purpose (one small change to the
RTL) and counts how many the bench catches. Three rules decide whether that number can be believed, and this module applies them:

1. Blind mutants. ``flow/mutation_blind.py`` makes the mutants from the RTL text and an integer seed only (no test, model or bench is an input).
2. Equivalent mutants are decided by a formal miter (``flow/mutation_equiv.py``, the method of YosysHQ MCY, AppNote 400), not by hand. A surviving mutant is
   ``equivalent`` (no input sequence shows a difference: dropped from the denominator and listed), ``not_equivalent`` (a real survivor: a behaviour the bench
   does not check), or ``undecided`` (the proof did not finish: reported separately).
3. Reporting after GateTruth (arXiv 2608.12635, a single-author preprint whose lessons are concrete): the record states the operator set, the mutant count,
   kills by simulation and kills by formal checks separately, the timeout policy, and lists every survivor with its verdict.

    mutation score          = killed / (killed + real survivors)                 the headline
    score, worst case       = killed / (killed + real survivors + undecided)     what the score is if every undecided mutant were a real survivor
    score before the filter = killed / (killed + every survivor + bench timeouts)   what flow/mutate.py reports (equivalents count as survivors)

A bench timeout is a mutant that is neither killed nor survived (the run was cut): listed, in no numerator, and in the worst case's denominator.
An invalid mutant (the copy does not compile) is excluded and listed. Mutants run one after another by default (GateTruth: parallel sweeps can silently
inflate kill rates through timeouts); ``--jobs`` is there for a machine with headroom and is recorded in the record.

The record (``fpga-design-agent/mutation-score/v1``) is read by flow/trace_v1.py as an evidence file (``reader: mutation``): a requirement can bind a
mutation floor, ``mutation_floor: {score_pct: 90, min_mutants: 20, max_undecided: 0}``, see ``judge`` below and docs/mutation_score.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow import mutation_blind, mutation_equiv  # noqa: E402

SCHEMA = "fpga-design-agent/mutation-score/v1"
TIMEOUT_POLICY = ("A bench run that exceeds its time limit is `timed_out`: it is not counted as killed and not as a survivor; it is listed, and the worst-case "
                  "score counts it as a survivor. A formal run that exceeds its limit is `undecided`, handled the same way. Neither is ever counted as a kill.")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- running one target ---------------------------------------------------------------------------------------------------

def evaluate(target: dict, mutants: list[dict], jobs: int, mutant_timeout_s: int, work: Path, log=print) -> list[dict]:
    """Run the bench on every mutant. Returns one row per mutant with status killed | survived | timed_out | invalid."""
    rtl_dir = target["rtl_dir"]
    def one(m: dict) -> dict:
        row = {k: m[k] for k in ("name", "file", "line", "class", "why") if k in m} | {"change": f"{m['file']} line {m['line']}: `{m['old_line']}` became `{m['new_line']}` ({m['why']})"}
        d = work / m["name"]
        d.mkdir(parents=True, exist_ok=True)
        for n in target.get("copy_files") or target["rtl_files"]:
            shutil.copy(rtl_dir / n, d / n)
        src = (d / m["file"]).read_text()
        new = mutation_blind.apply(m, src)
        if new is None or new == src:
            return row | {"status": "invalid", "note": "the text to change was not found exactly once"}
        (d / m["file"]).write_text(new)
        t0 = time.monotonic()
        st = target["bench"](d, mutant_timeout_s)
        row |= {"status": {"fail": "killed", "pass": "survived", "timeout": "timed_out", "invalid": "invalid"}[st], "seconds": round(time.monotonic() - t0, 1)}
        if st == "invalid":
            row["note"] = "the mutated RTL does not build"
        if target.get("stage_of"):
            row["bench_stage"] = target["stage_of"](d)         # which stage of a staged bench decided the mutant (b96: reduced | long | none)
        log(f"  {m['name']:46s} {row['status']:9s} {row['seconds']:6.1f} s", flush=True)
        if st != "pass":
            shutil.rmtree(d, ignore_errors=True)
        return row

    if jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            return list(ex.map(one, mutants))
    return [one(m) for m in mutants]


def filter_survivors(target: dict, rows: list[dict], work: Path, bmc_depth: int, bmc_s: int, prove_s: int, log=print) -> None:
    """Decide every survivor by formal miter under every configuration of the target; the verdict goes into the row (``formal``)."""
    rtl_dir = target["rtl_dir"]
    orig = [rtl_dir / n for n in target["rtl_files"]]
    for r in rows:
        if r["status"] != "survived":
            continue
        d = work / r["name"]
        mut = [d / n for n in target["rtl_files"]]
        per = []
        for cfg in target["configs"]:
            v = mutation_equiv.classify(orig, mut, target, cfg, bmc_depth=bmc_depth, bmc_s=bmc_s, prove_s=prove_s)
            per.append({"config": cfg.get("label") or cfg.get("params"), **v})
            if v["verdict"] == "not_equivalent":
                break                                     # one counterexample decides it
        verdicts = [p["verdict"] for p in per]
        if "not_equivalent" in verdicts:
            verdict = "not_equivalent"
        elif all(v == "equivalent" for v in verdicts):
            verdict = "equivalent"
        elif "error" in verdicts:
            verdict = "error"
        elif "skipped" in verdicts:
            verdict = "skipped"
        else:
            verdict = "undecided"
        r["formal"] = {"verdict": verdict, "per_config": per, "seconds": round(sum(p.get("seconds", 0) for p in per), 1)}
        log(f"  filter {r['name']:40s} {verdict}  ({r['formal']['seconds']} s)", flush=True)


def formal_bench_kills(target: dict, rows: list[dict], work: Path, log=print) -> None:
    """Optional: a survivor that the design's own formal property bench kills (``target['formal_bench']``) is a formal kill, reported apart from simulation kills."""
    fb = target.get("formal_bench")
    if not fb:
        return
    for r in rows:
        if r["status"] != "survived" or (r.get("formal") or {}).get("verdict") == "equivalent":
            continue
        d = work / r["name"]
        if not d.is_dir():
            continue
        st = fb(d)
        r["formal_bench"] = st
        log(f"  formal bench {r['name']:36s} {st}", flush=True)


def drop_mutant_dirs(rows: list[dict], work: Path) -> None:
    """Brief 152: the survivors' copies are kept until the filter and the formal bench have both used them. (Brief 143b deleted each copy at the end of the filter, so
    formal_bench_kills found no directory and never ran: its b96 record's ``killed_by_formal_bench`` 0 was not a result.)"""
    for r in rows:
        shutil.rmtree(work / r["name"], ignore_errors=True)


def summarise(rows: list[dict], has_formal_bench: bool) -> dict:
    by = lambda s: [r for r in rows if r["status"] == s]
    killed_sim, surv, tmo, inv = by("killed"), by("survived"), by("timed_out"), by("invalid")
    killed_formal = [r for r in surv if r.get("formal_bench") == "killed"]
    surv = [r for r in surv if r.get("formal_bench") != "killed"]
    ver = lambda r: (r.get("formal") or {}).get("verdict", "not_run")
    equiv = [r for r in surv if ver(r) == "equivalent"]
    real = [r for r in surv if ver(r) == "not_equivalent"]
    und = [r for r in surv if ver(r) in ("undecided", "error", "skipped", "not_run")]
    k_all = len(killed_sim) + len(killed_formal)
    pct = lambda a, b: round(100.0 * a / b, 2) if b else None
    return {"evaluated": len(killed_sim) + len(by("survived")) + len(tmo), "invalid": len(inv), "bench_timed_out": len(tmo),
            "killed_by_simulation": len(killed_sim), "killed_by_formal_bench": len(killed_formal), "killed": k_all,
            "survived_after_bench": len(by("survived")) - len(killed_formal),
            "equivalent": len(equiv), "real_survivors": len(real), "undecided": len(und),
            "score_pct": pct(k_all, k_all + len(real)),
            "score_simulation_only_pct": pct(len(killed_sim), k_all + len(real)),
            "score_worst_case_pct": pct(k_all, k_all + len(real) + len(und) + len(tmo)),
            "score_before_filter_pct": pct(k_all, k_all + len(surv) + len(tmo)),
            "formal_bench_bound": has_formal_bench,
            "invalid_listed": [r["name"] for r in inv], "timed_out_listed": [r["name"] for r in tmo]}


def run_target(target: dict, seed: int, count: int | None, jobs: int = 1, mutant_timeout_s: int = 0, do_filter: bool = True, bmc_depth: int = 30,
               bmc_s: int = 60, prove_s: int = 180, llm_file: Path | None = None, log=print) -> dict:
    t0 = time.monotonic()
    files = [target["rtl_dir"] / n for n in target["rtl_files"]]
    work = Path(tempfile.mkdtemp(prefix=f"mt_{target['name']}_"))
    try:
        log(f"{target['name']}: baseline ...", flush=True)
        b0 = time.monotonic()
        st = target["bench"](target["rtl_dir"], 3600)
        base_s = round(time.monotonic() - b0, 1)
        if st != "pass":
            raise RuntimeError(f"{target['name']}: the bench does not pass on the unmutated RTL ({st}); no result written")
        gen = mutation_blind.generate(files, seed, count)
        mutants, dropped = list(gen["mutants"]), []
        if llm_file:
            ok, dropped = mutation_blind.load_llm_proposals(llm_file.read_text(), files)
            mutants += ok
        per_mutant = mutant_timeout_s or int(min(900, max(60, 6 * base_s)))
        log(f"{target['name']}: baseline {base_s} s, {gen['candidates']} candidates, {len(mutants)} mutants, limit {per_mutant} s each", flush=True)
        rows = evaluate(target, mutants, jobs, per_mutant, work, log)
        if do_filter:
            filter_survivors(target, rows, work, bmc_depth, bmc_s, prove_s, log)
        formal_bench_kills(target, rows, work, log)
        drop_mutant_dirs(rows, work)
        S = summarise(rows, bool(target.get("formal_bench")))
        rec = {"schema": SCHEMA, "target": target["name"], "design": target["design"], "what": target["what"], "date": time.strftime("%Y-%m-%d"),
               "generator": {"name": "flow/mutation_blind.py", "blind_to_tests": True, "seed": seed, "requested": count, "candidates": gen["candidates"],
                             "sampled": gen["sampled"], "operators": gen["operators"], "llm_proposals_valid": len(mutants) - len(gen["mutants"]),
                             "llm_proposals_dropped": len(dropped), "rtl_sha256": gen["rtl_sha256"]},
               "rtl": {n: sha(target["rtl_dir"] / n) for n in target["rtl_files"]},
               "rtl_source": target.get("rtl_source"),
               "bench": {"description": target["bench_text"], "baseline_seconds": base_s, "mutant_timeout_s": per_mutant, "jobs": jobs},
               "timeout_policy": TIMEOUT_POLICY,
               "filter": ({"method": "miter: BMC, then register-matched induction (yosys equiv_induct), then an unbounded proof (sby)", "bmc_depth": bmc_depth,
                           "bmc_limit_s": bmc_s, "prove_limit_s": prove_s, "configs": [c.get("label") or c.get("params") for c in target["configs"]],
                           "assumptions": target.get("assume") or [], "compared": target.get("compared_text", "every output, every clock"), "reset": target.get("reset"),
                           "start_state": "registers without an initial value start at 0 in both versions"} if do_filter else {"method": "none"}),
               **S, "survivors": [{"name": r["name"], "change": r["change"], "verdict": (r.get("formal") or {}).get("verdict", "not_run"),
                                   "note": "; ".join(p.get("note", "") for p in (r.get("formal") or {}).get("per_config", []) if p.get("note"))[:300]}
                                  for r in rows if r["status"] == "survived" and r.get("formal_bench") != "killed"],
               "rows": rows, "wall_seconds": round(time.monotonic() - t0, 1),
               "tools": tool_versions()}
        return rec
    finally:
        shutil.rmtree(work, ignore_errors=True)


def tool_versions() -> dict:
    out = {}
    for name, argv in (("yosys", ["yosys", "-V"]), ("sby", ["sby", "--version"]), ("iverilog", ["iverilog", "-V"])):
        try:
            out[name] = subprocess.run(argv, capture_output=True, text=True, env=mutation_equiv._env(), timeout=20).stdout.splitlines()[0][:80]
        except (OSError, IndexError, subprocess.SubprocessError):
            out[name] = "not found"
    return out


# ---- the trace_v1 evidence reader ------------------------------------------------------------------------------------------

def judge(item: dict, req_by_id: dict, path: Path, res: dict, root: Path = ROOT) -> dict:
    """flow/trace_v1.py reader ``mutation``: pass when the record meets the floor of the item or of one of its requirements.

    floor = {score_pct: 90, worst_case_pct: 90, min_mutants: 30, max_undecided: 0}, put on the item as ``mutation_floor`` or on a requirement as ``mutation_floor`` (the item's wins).
    The headline score judged is ``score_pct`` (killed / (killed + real survivors)); the record must have been filtered (a record made with ``--no-filter`` fails, its
    equivalents are unknown), at least ``min_mutants`` evaluated, at most ``max_undecided`` undecided, no bench timeouts beyond ``max_timed_out`` (default 0), and
    its recorded RTL hashes must match the RTL now (a record for other RTL is not evidence about this RTL). Detail text names every count."""
    floor = item.get("mutation_floor")
    if floor is None:
        for q in item.get("requirements", []):
            if q in req_by_id and req_by_id[q].get("mutation_floor"):
                floor = req_by_id[q]["mutation_floor"]
                break
    if not floor or "score_pct" not in floor:
        res.update(status="fail", detail="a mutation item needs a `mutation_floor: {score_pct: N}` on the item or on one of its requirements")
        return res
    try:
        rec = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        res.update(status="not_run", detail=f"mutation record not readable ({type(e).__name__})")
        return res
    if rec.get("schema") != SCHEMA:
        res.update(status="fail", detail=f"not a {SCHEMA} record")
        return res
    res["value"] = rec.get("score_pct")
    res["mutation"] = {k: rec.get(k) for k in ("score_pct", "score_worst_case_pct", "score_before_filter_pct", "killed", "real_survivors", "equivalent", "undecided",
                                                 "bench_timed_out", "invalid", "killed_by_simulation", "killed_by_formal_bench")} | {"seed": (rec.get("generator") or {}).get("seed")}
    problems = []
    if (rec.get("filter") or {}).get("method") in (None, "none"):
        problems.append("survivors were not filtered by formal equivalence")
    stale = [n for n, h in (rec.get("rtl") or {}).items() if (root / rec.get("rtl_dir", "") / n).is_file() and sha(root / rec["rtl_dir"] / n) != h]
    if stale:
        problems.append(f"the RTL changed since the record ({', '.join(stale[:3])})")
    score = rec.get("score_pct")
    if score is None or float(score) < float(floor["score_pct"]):
        problems.append(f"score {score}% is below the floor {floor['score_pct']}%")
    if "worst_case_pct" in floor:                       # brief 152: a floor on the worst case (every undecided mutant and bench timeout counted as a survivor)
        wc = rec.get("score_worst_case_pct")
        if wc is None or float(wc) < float(floor["worst_case_pct"]):
            problems.append(f"worst-case score {wc}% is below the floor {floor['worst_case_pct']}%")
    if rec.get("evaluated", 0) < floor.get("min_mutants", 0):
        problems.append(f"{rec.get('evaluated', 0)} mutants evaluated, fewer than {floor['min_mutants']}")
    if rec.get("undecided", 0) > floor.get("max_undecided", 0):
        problems.append(f"{rec.get('undecided')} undecided (limit {floor.get('max_undecided', 0)})")
    if rec.get("bench_timed_out", 0) > floor.get("max_timed_out", 0):
        problems.append(f"{rec.get('bench_timed_out')} bench timeouts (limit {floor.get('max_timed_out', 0)})")
    detail = (f"mutation score {score}% (floor {floor['score_pct']}%): {rec.get('killed')} killed, {rec.get('real_survivors')} real survivors, "
              f"{rec.get('equivalent')} equivalent dropped, {rec.get('undecided')} undecided; worst case {rec.get('score_worst_case_pct')}%; "
              f"seed {(rec.get('generator') or {}).get('seed')}")
    res.update(status="fail" if problems else "pass", detail=detail + ("; " + "; ".join(problems) if problems else ""))
    return res


# ---- reports --------------------------------------------------------------------------------------------------------------

def show(rec: dict) -> str:
    g = rec["generator"]
    L = [f"{rec['target']}: {rec['what']}", f"  RTL: {', '.join(rec['rtl'])}  (dir {rec.get('rtl_dir', '')}; {rec.get('rtl_source') or 'this tree'})",
         f"  mutants: {g['sampled']} sampled of {g['candidates']} candidates, seed {g['seed']}, blind to the tests, operators {len(g['operators'])}",
         f"  bench: {rec['bench']['description']} (baseline {rec['bench']['baseline_seconds']} s, limit {rec['bench']['mutant_timeout_s']} s a mutant)",
         f"  invalid {rec['invalid']}, bench timeouts {rec['bench_timed_out']}",
         f"  killed {rec['killed']} (simulation {rec['killed_by_simulation']}, formal bench {rec['killed_by_formal_bench']}); survivors {rec['survived_after_bench']}: "
         f"equivalent {rec['equivalent']}, real {rec['real_survivors']}, undecided {rec['undecided']}",
         f"  score before the filter {rec['score_before_filter_pct']}%   after {rec['score_pct']}%   worst case {rec['score_worst_case_pct']}%   (simulation-only {rec['score_simulation_only_pct']}%)"]
    for s in rec["survivors"]:
        L.append(f"    survivor [{s['verdict']}] {s['change']}")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    from flow import mutation_targets as T
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("target")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--count", type=int, default=40)
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--mutant-timeout-s", type=int, default=0)
    r.add_argument("--no-filter", action="store_true")
    r.add_argument("--bmc-depth", type=int, default=30)
    r.add_argument("--bmc-s", type=int, default=60)
    r.add_argument("--prove-s", type=int, default=180)
    r.add_argument("--llm-proposals", default="")
    r.add_argument("--json", default="")
    s = sub.add_parser("show")
    s.add_argument("record")
    sub.add_parser("targets")
    a = ap.parse_args(argv)
    if a.cmd == "targets":
        for n, t in T.TARGETS.items():
            print(f"{n}: {t['what']}")
        return 0
    if a.cmd == "show":
        print(show(json.loads(Path(a.record).read_text())))
        return 0
    t = T.get(a.target)
    rec = run_target(t, a.seed, a.count, a.jobs, a.mutant_timeout_s, not a.no_filter, a.bmc_depth, a.bmc_s, a.prove_s, Path(a.llm_proposals) if a.llm_proposals else None)
    rec["rtl_dir"] = t["rtl_dir_rel"]
    out = Path(a.json) if a.json else ROOT / "results" / "143b_mutation" / f"{a.target}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1) + "\n")
    print(show(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
