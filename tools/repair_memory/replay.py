#!/usr/bin/env python3
"""Brief 217: replay the evidence-keyed repair memory on recorded agent runs, before any live A/B (brief 226 proposal 4).

Stage 1 (``extract``): for every recorded run that has a ``snap.git`` (the harness's per-gate snapshots of the design), walk the stage-2 gate
evaluations in order. Each failing evaluation gets its evidence keys ``(gate, finding_id, signature_class)`` (``agent.graph.repair_memory``):
lint is re-run on the snapshot with the agent's own ``lint`` tool; standards, constants, report-gate and verification ids come from the gate
message the harness committed; a failed simulate is **not** keyed (it needs the simulator's output, which the snapshot does not hold) and is
counted as unkeyed. The files changed by the edit that followed (a bounded diff) are kept, so a record can be made from the transition.
Output: ``replay_evals.jsonl``, one line per stage-2 evaluation.

Stage 2 (``analyse``): reads ``replay_evals.jsonl`` only. Leave-one-run-out: a record is made from every transition of every OTHER run (a key
that failed at evaluation i and no longer fails at i+1, with at least one file changed); a failing evaluation is *matched* when some record has
exactly its gate, finding id and signature class. Reports reach, the recurring-failure share, and the ceiling (see ``analyse``).

    python tools/repair_memory/replay.py extract --out results/217_repair_memory/replay_evals.jsonl
    python tools/repair_memory/replay.py analyse results/217_repair_memory/replay_evals.jsonl > results/217_repair_memory/replay_analysis.txt
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

WT = Path.home() / "Claude_sandbox" / "_worktrees"
SOURCES = {"213": WT / "213-repair-feedback" / "runs", "209": WT / "209-kr260-pilot" / "runs", "209a": WT / "209a-pilot-ready" / "runs",
           "224": WT / "224-long-output" / "runs", "215": WT / "215-public-benchmarks" / "runs"}
OSS_BIN = Path.home() / ".local/opt/oss-cad-suite/bin"


def git(g: Path, *a: str) -> str:
    return subprocess.run(["git", "--git-dir", str(g), *a], capture_output=True, text=True).stdout


def stage2_commits(g: Path) -> list[tuple[str, str]]:
    out = []
    for ln in git(g, "log", "--format=%h\t%s", "--reverse").splitlines():
        sha, _, msg = ln.partition("\t")
        if msg.startswith("02 ") and ": not gated" not in msg:             # a visit-limit refusal ran no gate
            out.append((sha, msg.split(": ", 1)[1] if ": " in msg else msg))
    return out


def checkout(g: Path, sha: str, dest: Path) -> None:
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    subprocess.run(["git", "--git-dir", str(g), "--work-tree", str(dest), "checkout", "-q", sha, "--", "."], capture_output=True)


def design_name(d: Path, rid: str) -> str | None:
    try:
        import yaml
        cfg = yaml.safe_load((d / "build.yaml").read_text()) or {}
        for s in cfg.get("sources", []):
            m = re.match(rf"runs/{re.escape(rid)}/([^/]+)/", s)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def board_of(part: str) -> str | None:
    import yaml
    for b in sorted((REPO / "boards").glob("*/board.yaml")):
        try:
            if (yaml.safe_load(b.read_text()) or {}).get("part") == part:
                return b.parent.name
        except Exception:
            pass
    return None


def run_lint(snapshot: Path, rid: str) -> str | None:
    """The agent's own ``lint`` tool over a checked-out snapshot (a throw-away root holding links to boards, flow and shell). None: could not run."""
    import yaml
    name = design_name(snapshot, rid)
    if not name:
        return None
    part = (yaml.safe_load((snapshot / "build.yaml").read_text()) or {}).get("part")
    board = board_of(part) or "nexys_a7_100t"
    root = Path(tempfile.mkdtemp(prefix="rm_lint_"))
    try:
        for d in ("boards", "flow", "shell"):
            (root / d).symlink_to(REPO / d)
        dst = root / "runs" / rid / name
        shutil.copytree(snapshot, dst, symlinks=True)
        os.environ["PATH"] = f"{OSS_BIN}:{os.environ['PATH']}" if str(OSS_BIN) not in os.environ["PATH"] else os.environ["PATH"]
        from agent.core import Session, dispatch
        s = Session(design=dst, root=root, board=board)
        r = dispatch(s, "lint", {})
        return None if r.get("refused") else str(r.get("output", ""))
    except Exception as e:                       # noqa: BLE001
        return None if "refused" in str(e) else f"[replay error {type(e).__name__}]"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def keys_from_message(msg: str, snapshot: Path, rid: str, cache: dict) -> tuple[list[dict], list[str]]:
    from agent.graph import repair_memory as rm
    from agent.graph.repair import SIM_CONSEQUENCES
    keys: list[dict] = []
    unkeyed: list[str] = []
    if "lint not passing" in msg:
        text = run_lint(snapshot, rid)
        if text is None:
            unkeyed.append("lint (could not re-run)")
        else:
            keys += rm.lint_keys(text[-1500:])           # the live evidence holds the last 1500 characters of the lint output
    for gate, pat in (("standards", r"standards (STD-[A-Z0-9]+(?:-\d+)?)"), ("constants", r"constants (CONST-[A-Z0-9-]+)"), ("report_gates", r"report gate (RPT-[A-Z0-9-]+)")):
        for fid in dict.fromkeys(re.findall(pat, msg)):
            keys.append(rm._key(gate, fid, "default", ""))
    sim = "simulate not passing" in msg
    if sim:
        unkeyed.append("simulate (needs the simulator output)")
    for stage, check in dict.fromkeys(re.findall(r"\b(V\d) (\w+):", msg)):
        if not (sim and check in SIM_CONSEQUENCES):
            keys.append(rm._key("verif", check, stage, ""))
    if "model contract" in msg or "contract" in msg.split(";")[0]:
        unkeyed.append("model contract")
    if not keys and not unkeyed:
        unkeyed.append("other: " + msg[:80])
    seen: set = set()
    return [k for k in keys if not (rm.key_tuple(k) in seen or seen.add(rm.key_tuple(k)))], unkeyed


def extract(out: Path, sources: list[str], limit: int | None = None) -> None:
    from agent.graph import repair_memory as rm
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="rm_replay_"))
    n_runs = 0
    for src in sources:
        for run in sorted(SOURCES[src].glob("2026*")):
            g = run / "snap.git"
            if not g.is_dir():
                continue
            seq = stage2_commits(g)
            if not seq:
                continue
            n_runs += 1
            if limit and n_runs > limit:
                break
            rid = run.name
            prev_snap: Path | None = None
            for i, (sha, msg) in enumerate(seq):
                passed = msg == "pass"
                snap = tmp / f"{rid}_{i}"
                checkout(g, sha, snap)
                keys, unkeyed = ([], []) if passed else keys_from_message(msg, snap, rid, {})
                fix = None
                if prev_snap is not None:
                    fix = rm.diff_summary(prev_snap, snap)
                    shutil.rmtree(prev_snap, ignore_errors=True)
                rows.append({"source": src, "run": rid, "i": i, "sha": sha, "passed": passed, "msg": msg[:200], "keys": keys, "unkeyed": unkeyed,
                             "fix_from_previous": fix, "n_evals": len(seq), "design": design_name(snap, rid) or ""})
                prev_snap = snap if not passed else (shutil.rmtree(snap, ignore_errors=True), None)[1]
            if prev_snap:
                shutil.rmtree(prev_snap, ignore_errors=True)
            print(f"{src} {rid}: {len(seq)} evaluations", file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    shutil.rmtree(tmp, ignore_errors=True)


# --- analysis -------------------------------------------------------------------------------------------------------------------------------

def analyse(path: Path, pool_sources: tuple[str, ...] = ("213", "209", "209a", "224"), holdout: str = "run") -> str:
    from agent.graph import repair_memory as rm
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    by_run: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_run[r["run"]].append(r)
    for v in by_run.values():
        v.sort(key=lambda r: r["i"])
    kt = lambda k: rm.key_tuple(k)  # noqa: E731
    # records: a key failing at evaluation i and not at i+1, with a changed file (the diff made by the visit between them)
    records: list[dict] = []
    design_of = {run: (ev[0].get("design") or run) for run, ev in by_run.items()}
    for run, ev in by_run.items():
        if ev[0]["source"] not in pool_sources:        # benchmark runs (215) are never knowledge: they are evaluated on, never recorded from
            continue
        for a, b in zip(ev, ev[1:]):
            if a["passed"] or not b.get("fix_from_previous") or not b["fix_from_previous"]["files"]:
                continue
            nowb = {kt(k) for k in b["keys"]}
            for k in a["keys"]:
                if kt(k) not in nowb:
                    records.append({"run": run, "key": kt(k), "files": b["fix_from_previous"]["files"], "source": a["source"]})
    pool_by_key: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in records:
        pool_by_key[r["key"]].append(r)

    failing = [(run, i, e) for run, ev in by_run.items() for i, e in enumerate(ev) if not e["passed"]]
    L: list[str] = []
    n_runs = len(by_run)
    L.append(f"HOLD-OUT: leave-one-{holdout} (records come from sources {', '.join(pool_sources)} only; the 215 benchmark runs are evaluated on, never recorded from).")
    L.append(f"Replay of the repair memory on {n_runs} recorded runs, {len(rows)} stage-2 evaluations, {len(failing)} failing ones "
             f"({sum(1 for _, _, e in failing if e['keys'])} with at least one evidence key, "
             f"{sum(1 for _, _, e in failing if not e['keys'])} with none: unkeyed).")
    src_runs = collections.Counter(next(iter({r['source'] for r in ev})) for ev in by_run.values())
    L.append("Runs by source: " + ", ".join(f"{k} {v}" for k, v in sorted(src_runs.items())))
    L.append(f"Records made from transitions (key failing at an evaluation, gone at the next, a file changed): {len(records)} over {len(pool_by_key)} distinct keys, "
             f"from {len({r['run'] for r in records})} runs.")
    gates = collections.Counter(k[0] for k in pool_by_key)
    L.append("Distinct record keys by gate: " + ", ".join(f"{g} {n}" for g, n in sorted(gates.items())))
    unk = collections.Counter(u.split(" (")[0].split(":")[0] for _, _, e in failing for u in e["unkeyed"])
    L.append("Unkeyed components of failing evaluations: " + (", ".join(f"{k} {v}" for k, v in sorted(unk.items())) or "none"))

    # leave-one-run-out matching
    n_key_evals = n_matched = 0
    recurring_inst = recurring_matched = 0
    visits_saved_ceiling = 0
    per_gate = collections.defaultdict(lambda: [0, 0, 0, 0])      # evals, matched, recurring, recurring matched
    rescuable_runs: set[str] = set()
    saved_by_run: dict[str, int] = collections.defaultdict(int)
    lint_loop: dict[str, list[int]] = {}
    fix_agree = [0, 0]
    ex: list[str] = []
    for run, ev in by_run.items():
        last_failing_unrecovered = (not ev[-1]["passed"]) if ev else False
        for i, e in enumerate(ev):
            if e["passed"] or not e["keys"]:
                continue
            nxt = ev[i + 1] if i + 1 < len(ev) else None
            nxt_keys = {kt(k) for k in nxt["keys"]} if nxt else set()
            n_key_evals += 1
            hit_any = rec_any = False
            for k in e["keys"]:
                t = kt(k)
                others = [r for r in pool_by_key.get(t, []) if r["run"] != run and (holdout == "run" or design_of[r["run"]] != design_of[run])]
                persists = nxt is not None and not nxt["passed"] and t in nxt_keys or (nxt is None)        # still failing at the next evaluation, or the run ended on it
                g = per_gate[t[0]]
                g[0] += 1
                if others:
                    g[1] += 1
                    hit_any = True
                if persists:
                    g[2] += 1
                    if others:
                        g[3] += 1
                        rec_any = True
                        # fix agreement: do the files the matching records changed overlap the files the next successful repair of this run changed?
                        fut = [x for x in ev[i + 1:] if x.get("fix_from_previous") and x["fix_from_previous"]["files"]]
                        if fut:
                            fix_agree[1] += 1
                            want = {Path(f).name for f in fut[0]["fix_from_previous"]["files"]}
                            if any(want & {Path(f).name for f in r["files"]} for r in others):
                                fix_agree[0] += 1
                        if len(ex) < 6:
                            ex.append(f"{run} eval {i}: {t} matched {len(others)} record(s) from other runs; the key still failed at the next evaluation")
            n_matched += hit_any
            recurring_inst += any(kt(k) in nxt_keys for k in e["keys"]) if nxt and not nxt["passed"] else (1 if nxt is None else 0)
            if rec_any:
                recurring_matched += 1
                visits_saved_ceiling += 1
                saved_by_run[run] += 1
                if last_failing_unrecovered:
                    rescuable_runs.add(run)
    L.append("")
    L.append("Leave-one-run-out matching (a record from another run with exactly the same gate, finding id and signature class):")
    L.append(f"  keyed failing evaluations: {n_key_evals}; with a match: {n_matched} ({100 * n_matched / max(1, n_key_evals):.0f} %) = REACH")
    L.append(f"  recurring (a key still failing at the next evaluation, or the run ended on it): {recurring_inst} evaluations; "
             f"of those with a match: {recurring_matched} ({100 * recurring_matched / max(1, recurring_inst):.0f} %)")
    for g, (n, m, rc, rm_) in sorted(per_gate.items()):
        L.append(f"    gate {g}: key instances {n}, matched {m}; recurring {rc}, recurring and matched {rm_}")
    L.append(f"  fix agreement on matched recurring cases: the files a matching record changed overlap the files this run's next repair changed in {fix_agree[0]} of {fix_agree[1]}")
    L.append("")
    L.append("CEILING (upper bound: every matched recurring evaluation is saved by its record, nothing else changes):")
    L.append(f"  stage-2 visits that could be saved: {visits_saved_ceiling} over {n_runs} runs = {visits_saved_ceiling / max(1, n_runs):.2f} visits per run")
    runs_unrec = sum(1 for ev in by_run.values() if ev and not ev[-1]["passed"])
    L.append(f"  runs whose stage 2 never passed in the record: {runs_unrec} of {n_runs}; of those, runs with a matched recurring key: {len(rescuable_runs)} "
             f"= at most {100 * len(rescuable_runs) / max(1, n_runs):.0f} points of pass rate")
    L.append("  by source (visits per run; runs that never passed stage 2 and have a matched recurring key / runs):")
    for src in sorted(src_runs):
        rs = [r for r, ev in by_run.items() if ev[0]["source"] == src]
        unrec = [r for r in rs if not by_run[r][-1]["passed"]]
        L.append(f"    {src}: {sum(saved_by_run.get(r, 0) for r in rs)} saved over {len(rs)} runs = {sum(saved_by_run.get(r, 0) for r in rs) / len(rs):.2f}; "
                 f"{len([r for r in unrec if r in rescuable_runs])} of {len(rs)} runs = {100 * len([r for r in unrec if r in rescuable_runs]) / len(rs):.0f} points")
    ours = [r for r, ev in by_run.items() if ev[0]["source"] != "215"]
    L.append(f"    pilot designs only (all sources except 215): {sum(saved_by_run.get(r, 0) for r in ours) / max(1, len(ours)):.2f} visits per run over {len(ours)} runs")
    # the identical lint loops of brief 213 (runs 2, 4, 15)
    loops = {}
    for d in sorted((WT / "213-repair-feedback" / "results" / "213_repair_feedback" / "runs").glob("*_treatment")):
        n = d.name.split("_")[0]
        if n in ("2", "4", "15") and (d / "RUN_ID.txt").is_file():
            loops[n] = (d / "RUN_ID.txt").read_text().strip()
    for n, rid in loops.items():
        ev = by_run.get(rid, [])
        fails = [e for e in ev if not e["passed"]]
        matched = [e for e in fails if any([r for r in pool_by_key.get(kt(k), []) if r["run"] != rid] for k in e["keys"])]
        L.append(f"  213 run {n} ({rid}): {len(fails)} failing evaluations, keys {sorted({k['finding_id'] for e in fails for k in e['keys']})}; "
                 f"{len(matched)} had a matching record from another run")
    L.append("")
    L.append("Examples: " + " | ".join(ex[:6]))
    return "\n".join(L)


def main() -> int:
    from agent.access import require_or_exit      # brief 94: the replay builds sessions; the seed reads the agent's records
    require_or_exit("tools.repair_memory.replay")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--sources", default="213,209,209a,224,215")
    e.add_argument("--limit", type=int)
    a_ = sub.add_parser("analyse")
    a_.add_argument("path", type=Path)
    a_.add_argument("--holdout", choices=["run", "design"], default="run")
    a = ap.parse_args()
    if a.cmd == "extract":
        extract(a.out, a.sources.split(","), a.limit)
    else:
        print(analyse(a.path, holdout=a.holdout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
