#!/usr/bin/env python3
"""Mutation testing of a design's RTL (brief 04f): the independent measure of a bench's quality.

    python3 flow/mutate.py designs/t1_dimmer_counter [--json OUT] [--only name,name]

Each mutant in <design>/verif/mutants.yaml replaces one exact string in a copy of rtl/ (operator, constant,
condition and reset mutations); the real RTL is never touched. Each mutant is run twice, one seed:
  tests    the cocotb bench under Icarus (no assertions exist there): the bench's own score
  checkers the bench under Verilator with the bound checkers: tests plus assertions
A mutant is killed when the run fails; it is invalid (and excluded) when the copy does not build. Reports
score_pct = killed / valid for the bench alone, score_with_checkers_pct, and the surviving mutants by name.
Local-only by default (about 25 s a run, 2 runs a mutant); CI runs it on a schedule or manually.
Needs the simulators of flow/portability.py's environment: iverilog, and Verilator 5.036+ for cocotb 2 (SIM=verilator).

Generic mode (brief 05k), for any design directory, including the ones the agent writes:

    python3 flow/mutate.py designs/<d> --generic [--json designs/<d>/build/verif/mutation.json]
            [--max-mutants 20] [--seed 1] [--wall-s 1500] [--mutant-timeout-s N] [--lock-wait-s 60]
            [--sandbox auto|container|host]

It runs the design's own tests/test_*_rtl.py (what the `simulate` tool runs, Icarus, the bench's own seeds) against a
mutated copy of rtl/ (flow.cocotb_run swaps the sources through $FDA_MUTANT_ORIG / $FDA_MUTANT_DIR). The mutants are
the design's verif/mutants.yaml when it has one, else generated from the RTL (comparison, logic, arithmetic, negation
and bit-constant operators), sampled with a recorded RNG seed up to --max-mutants. The unmutated RTL must pass first.
A mutant is killed only when its run fails; invalid (the copy does not compile, excluded), timed out (counted as NOT
killed) and skipped (the wall-time cap came first, excluded and listed) are never counted as killed. The result,
build/verif/mutation.json, is what flow/verif_gates.py --mutation reads. Takes the heavy-slot lock (exit 75: busy).
Brief 05m: the baseline and every mutant run (and the compile check) go through agent.core.runner.ContainerRunner, the same
container as `simulate` (no network, no capabilities, read-only root), whenever the sandbox image exists (--sandbox auto);
the mutated copies sit under <design>/build/mutants, inside the design mount.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PY = os.environ.get("MUTATE_PYTHON", sys.executable)

from flow import srcorder  # noqa: E402


EX_BUSY = 75                                       # exit status: the heavy-slot lock is held (retry later)
DEFAULT_MAX_MUTANTS, DEFAULT_WALL_S, DEFAULT_SEED = 20, 1500, 1
#: 05n. With no explicit --wall-s the cap scales with the baseline so that a normal run evaluates its whole sample:
#: wall = baseline * (sample + 2), at least DEFAULT_WALL_S and at most MAX_WALL_S (2 h, under the heavy slot). When even that
#: is too short the sample is reduced (never below MIN_EVALUATED) rather than leaving the sampled mutants unevaluated.
MAX_WALL_S, MIN_EVALUATED = 7200, 10
#: 07a2 fix 5 E. The sample is also capped by the baseline: the mutants may use about one hour in all, so a bench whose
#: baseline run takes B seconds gets floor(3600 / B) - 2 mutants, never fewer than MIN_EVALUATED (the V3 floor) and never
#: more than asked. A 30 s Verilator bench keeps all 20; a 312 s Icarus bench gets the minimum 10.
MUTATION_BUDGET_S = 3600


def plan_caps(baseline_s: float, max_mutants: int, pool: int, wall_s: int | None) -> tuple[int, int]:
    """(sample size, wall cap in seconds). An explicit ``wall_s`` is honoured as given (the sample is unchanged)."""
    if wall_s is not None:
        return max_mutants, wall_s
    n = min(max_mutants, pool)
    floor_n = min(MIN_EVALUATED, pool)
    base = max(1.0, float(baseline_s))
    if base * (n + 2) > MUTATION_BUDGET_S:
        n = max(floor_n, min(n, int(MUTATION_BUDGET_S // base) - 2))
    return n, int(min(MAX_WALL_S, max(DEFAULT_WALL_S, base * (n + 2))))


# ---- the heavy-slot lock (one heavy local job at a time on this PC) -------------------------------------------------

def lock_path() -> Path | None:
    """$FDA_HEAVY_LOCK, else the owner's shared _handoff/heavy_slot.lock when that directory exists, else None (CI)."""
    env = os.environ.get("FDA_HEAVY_LOCK")
    if env:
        return Path(env)
    d = Path.home() / "Claude_sandbox" / "_handoff"
    return d / "heavy_slot.lock" if d.is_dir() else None


def take_lock(job: str, wait_s: float, expect_s: float) -> tuple[Path | None, str]:
    """Create the lock file (one line: session, job, start, expected end) or wait up to ``wait_s`` for its holder.
    Returns (path, "") when taken (path None: no lock in use here) or (None, holder line) when still held."""
    p = lock_path()
    if p is None:
        return None, ""
    end = time.monotonic() + wait_s
    while True:
        # built at the moment of acquisition, so the start and expected end are real, not the start of the wait
        line = (f"fda-mutate {job} {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"{time.strftime('%H:%M', time.localtime(time.time() + expect_s))}\n")
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(line)
            return p, ""
        except FileExistsError:
            if time.monotonic() >= end:
                try:
                    return None, p.read_text().strip() or "held"
                except OSError:
                    return None, "held"
            time.sleep(min(5.0, max(0.1, end - time.monotonic())))


# ---- generic mode -----------------------------------------------------------------------------------------------------

#: (name, regex, replacement, plain words); each match of a regex on an RTL code line is one candidate mutant
OPERATORS = [
    ("eq_to_ne", r"(?<![=!<>])==(?!=)", "!=", "'==' replaced by '!='"),
    ("ne_to_eq", r"!=(?!=)", "==", "'!=' replaced by '=='"),
    ("and_to_or", r"&&", "||", "'&&' replaced by '||'"),
    ("or_to_and", r"\|\|", "&&", "'||' replaced by '&&'"),
    ("plus_to_minus", r" \+ ", " - ", "'+' replaced by '-'"),
    ("minus_to_plus", r" - ", " + ", "'-' replaced by '+'"),
    ("ge_to_lt", r" >= ", " < ", "'>=' replaced by '<'"),
    ("lt_to_ge", r" < ", " >= ", "'<' replaced by '>='"),
    ("gt_to_le", r" > ", " <= ", "'>' replaced by '<='"),
    ("not_removed", r"(?<![!=<>&|])!(?![=])", "", "a logical negation '!' removed"),
    ("bit0_to_1", r"\b1'b0\b", "1'b1", "constant 1'b0 replaced by 1'b1"),
    ("bit1_to_0", r"\b1'b1\b", "1'b0", "constant 1'b1 replaced by 1'b0"),
]
_SKIP_LINE = re.compile(r"^\s*(//|/\*|\*|`|import\b|parameter\b|localparam\b|module\b|endmodule\b|input\b|output\b|inout\b)"
                        r"|\bassert\b|\bassume\b|\bV_(SAME|NEXT|RST|COVER)\b|\$(display|error|fatal|info|finish)")


def generate_candidates(rtl: Path) -> list[dict]:
    """Every operator mutation of the design's rtl/*.sv code lines, in a fixed order (file, line, operator, position)."""
    out: list[dict] = []
    for f in sorted(rtl.glob("*.sv")):
        for n, raw in enumerate(f.read_text(errors="replace").splitlines(), 1):
            code = raw.split("//", 1)[0]
            if not code.strip() or _SKIP_LINE.search(code):
                continue
            for name, rx, rep, words in OPERATORS:
                for m in re.finditer(rx, code):
                    new = code[:m.start()] + rep + code[m.end():]
                    out.append({"name": f"{f.stem}_L{n}_{name}_{m.start()}", "file": f.name, "line": n,
                                "class": name, "why": words, "old_line": code.strip(), "new_line": new.strip(),
                                "col": m.start(), "rep": rep, "span": m.end() - m.start()})
    return out


def mutants_from_yaml(design: Path) -> list[dict]:
    """The design's curated mutants.yaml in the generic row shape: exact-text replacements, located by line."""
    rows = []
    for m in yaml.safe_load((design / "verif" / "mutants.yaml").read_text())["mutants"]:
        src = (design / "rtl" / m["file"]).read_text()
        line = src[:src.find(m["old"])].count("\n") + 1 if m["old"] in src else 0
        rows.append({"name": m["name"], "file": m["file"], "line": line, "class": m["class"], "why": m["why"],
                     "old_text": m["old"], "new_text": m["new"], "old_line": m["old"].strip().splitlines()[0],
                     "new_line": m["new"].strip().splitlines()[0]})
    return rows


def apply_mutant(m: dict, src: str) -> str | None:
    """The mutated source, or None when the text to change is not there exactly once (a stale mutant)."""
    if "old_text" in m:
        return src.replace(m["old_text"], m["new_text"]) if src.count(m["old_text"]) == 1 else None
    lines = src.splitlines(keepends=True)
    raw = lines[m["line"] - 1]
    code, tail = raw.split("//", 1) if "//" in raw else (raw.rstrip("\n"), "")
    if code[m["col"]:m["col"] + m["span"]] == "":
        return None
    new = code[:m["col"]] + m["rep"] + code[m["col"] + m["span"]:]
    lines[m["line"] - 1] = new + (("//" + tail) if tail else ("\n" if raw.endswith("\n") else ""))
    return "".join(lines)


def plain_words(m: dict) -> str:
    return f"rtl/{m['file']} line {m['line']}: `{m['old_line']}` became `{m['new_line']}` ({m['why']})"


def make_runner(design: Path, mode: str = "auto"):
    """The sandbox for model-written code (05m): a ContainerRunner (the image `simulate` uses) or None for the host.
    "auto" uses the container whenever the image exists; "container" fails when it does not; "host" is for CI and
    for machines with no image (the unit tests of this file). Model code never runs on the host when an image exists
    and the caller did not ask for "host" explicitly."""
    if mode == "auto":
        mode = os.environ.get("FDA_MUTATE_SANDBOX", "auto")       # the unit tests of this file set it to "host"
    if mode == "host":
        return None
    from agent.core.runner import ContainerRunner, container_available
    if container_available():
        return ContainerRunner(design, ROOT)
    if mode == "container":
        raise RuntimeError("--sandbox container: the sandbox image is not present (docker build -t fda-sim:2 agent/container)")
    return None


def compile_ok_verilator(files: list[Path], top: str | None, runner=None) -> bool | None:
    """07a2 fix 5 E: under Verilator a mutant that does not build would be "killed" by the build error alone, so the mutated
    RTL is linted first (errors only). None when it cannot tell."""
    inc = [f"-I{d}" for d in sorted({str(f.parent) for f in files})]
    argv = ["verilator", "--lint-only", "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-TIMESCALEMOD",
            *(["--top-module", top] if top else []), *inc, *map(str, files)]
    if runner is not None:
        return runner.run("simulate", argv, ROOT, None, 120).returncode == 0
    exe = shutil.which("verilator")
    if not exe:
        return None
    return subprocess.run(argv, capture_output=True, text=True).returncode == 0


def choose_sim(requested: str, runner=None) -> str:
    """The simulator the mutation run uses: Verilator (5.036+) when it is available where the tests run, else Icarus."""
    if requested != "auto":
        return requested
    from agent.core import tools as T
    return "verilator" if "verilator" in T.available_sims() else "icarus"


def compile_ok(files: list[Path], runner=None) -> bool | None:
    """Does Icarus accept these sources? None when it cannot tell (no iverilog), so the caller does not guess.
    With a ``runner`` the compile runs in the sandbox like the tests do."""
    inc = [f"-I{d}" for d in sorted({str(f.parent) for f in files})]
    argv = ["iverilog", "-g2012", "-t", "null", *inc, *map(str, files)]
    if runner is not None:
        return runner.run("simulate", argv, ROOT, None, 120).returncode == 0
    if not shutil.which("iverilog"):
        return None
    r = subprocess.run(argv, capture_output=True, text=True)
    return r.returncode == 0


def run_bench(design: Path, env_extra: dict, timeout: float, runner=None, sim: str = "icarus") -> tuple[str, float]:
    """The design's tests/test_*_rtl.py, as `simulate` runs them. Returns (status, seconds): "pass", "fail" or
    "timeout". With a ``runner`` (05m) the run is the sandbox's, the same container as `simulate` (no network, read-only
    root; a timed-out container is removed); without one it is a host process in its own group, killed on timeout."""
    tests = sorted((design / "tests").glob("test_*_rtl.py"))
    if runner is not None:
        t0 = time.monotonic()
        r = runner.run("simulate", [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *map(str, tests)], ROOT,
                       {"SIM": sim, **env_extra}, timeout)
        return ("timeout" if r.returncode == 124 else "pass" if r.returncode == 0 else "fail"), round(time.monotonic() - t0, 1)
    env = {k: v for k, v in os.environ.items() if k not in ("FDA_SIM_RESULTS_DIR", "FDA_COVERAGE", "FDA_COV_OUT")}
    env.update(SIM=sim, **env_extra)
    t0 = time.monotonic()
    p = subprocess.Popen([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *map(str, tests)], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        return "timeout", round(time.monotonic() - t0, 1)
    return ("pass" if rc == 0 else "fail"), round(time.monotonic() - t0, 1)


def generic(design: Path, a) -> int:
    out_json = Path(a.json) if a.json else design / "build" / "verif" / "mutation.json"
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    rtl = design / "rtl"
    if not list(design.glob("tests/test_*_rtl.py")) or not list(rtl.glob("*.sv")):
        print(f"{design.name}: needs rtl/*.sv and tests/test_*_rtl.py", file=sys.stderr)
        return 2
    try:
        runner = make_runner(design, a.sandbox)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    lock, holder = take_lock(design.name, a.lock_wait_s, (MAX_WALL_S if a.wall_s is None else a.wall_s) + 600)
    if lock is None and holder:
        print(f"BUSY: another heavy job holds the lock ({holder}); retry later")
        return EX_BUSY
    try:
        return _generic_locked(design, a, rtl, out_json, time.monotonic(), runner)      # the wall cap starts once the lock is ours
    finally:
        if lock is not None:
            lock.unlink(missing_ok=True)


def _generic_locked(design: Path, a, rtl: Path, out_json: Path, t_start: float, runner=None) -> int:
    mdir_root = design / "build" / "mutants"
    shell = [] if srcorder.no_shell(design) else sorted((ROOT / "shell" / "rtl").glob("*.sv"))     # 07a2-prep
    env_orig = {"FDA_MUTANT_ORIG": str(rtl.resolve())}
    # 1. the unmutated RTL must pass: a bench that fails on the original has nothing to measure
    sim = choose_sim(getattr(a, "sim", "auto"), runner)
    base, base_s = run_bench(design, env_orig | {"FDA_MUTANT_DIR": str(rtl.resolve())}, a.mutant_timeout_s or 900, runner, sim)
    sim_note = None
    if base != "pass" and sim != "icarus" and getattr(a, "sim", "auto") == "auto":      # the design may not build in Verilator
        sim_note = f"baseline {base} on {sim}: the run used icarus instead"
        sim = "icarus"
        base, base_s = run_bench(design, env_orig | {"FDA_MUTANT_DIR": str(rtl.resolve())}, a.mutant_timeout_s or 900, runner, sim)
    if base != "pass":
        print(f"baseline {base}: the bench does not pass on the unmutated RTL; no mutation result written")
        return 3
    top = None
    try:
        top = (yaml.safe_load((design / "build.yaml").read_text()) or {}).get("top")
    except (OSError, yaml.YAMLError):
        pass
    per_mutant = a.mutant_timeout_s or int(min(600, max(30, 4 * base_s)))
    # 2. the mutants
    source = "verif/mutants.yaml" if (design / "verif" / "mutants.yaml").is_file() else "generated"
    pool = mutants_from_yaml(design) if source == "verif/mutants.yaml" else generate_candidates(rtl)
    rng = random.Random(a.seed)
    sample_n, wall_s = plan_caps(base_s, a.max_mutants, len(pool), a.wall_s)
    chosen = sorted(rng.sample(pool, min(sample_n, len(pool))), key=lambda m: pool.index(m))
    rows, deadline = [], t_start + wall_s
    est = min(per_mutant, max(30.0, 1.5 * base_s))          # a mutant costs about one baseline; do not skip on the worst case
    for m in chosen:
        row = {k: m[k] for k in ("name", "file", "line", "class", "why")} | {"change": plain_words(m)}
        if time.monotonic() + est > deadline:
            rows.append(row | {"status": "skipped", "note": "wall-time cap reached before this mutant ran"})
            continue
        d = mdir_root / m["name"]
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for f in rtl.glob("*.sv"):
            shutil.copy(f, d / f.name)
        new = apply_mutant(m, (d / m["file"]).read_text())
        if new is None or new == (d / m["file"]).read_text():
            rows.append(row | {"status": "invalid", "note": "the text to change was not found exactly once"})
            continue
        (d / m["file"]).write_text(new)
        files = srcorder.order_sv(shell + sorted(d.glob("*.sv")))
        if compile_ok(files, runner) is False or (sim == "verilator" and compile_ok_verilator(files, top, runner) is False):
            rows.append(row | {"status": "invalid", "note": "the mutated RTL does not compile"})
            shutil.rmtree(d, ignore_errors=True)
            continue
        st, secs = run_bench(design, env_orig | {"FDA_MUTANT_DIR": str(d)}, per_mutant, runner, sim)
        row |= {"status": {"fail": "killed", "pass": "survived", "timeout": "timed_out"}[st], "seconds": secs}
        print(f"{m['name']:40s} {row['status']}", flush=True)
        rows.append(row)
        shutil.rmtree(d, ignore_errors=True)
    by = lambda s: [r for r in rows if r["status"] == s]
    killed, surv, tmo = by("killed"), by("survived"), by("timed_out")
    evaluated = len(killed) + len(surv) + len(tmo)
    res = {"design": design.name, "mode": "generic", "mutant_source": source, "rng_seed": a.seed,
           "baseline_seconds": base_s, "sim": sim, "sim_note": sim_note, "sandbox": "container" if runner is not None else "host",
           "caps": {"max_mutants": a.max_mutants, "sample": sample_n, "wall_s": wall_s, "wall_auto": a.wall_s is None,
                    "mutant_timeout_s": per_mutant, "min_evaluated": min(MIN_EVALUATED, len(pool))},
           "candidates": len(pool), "sampled": len(chosen), "evaluated": evaluated, "killed": len(killed),
           "survived": len(surv), "timed_out": len(tmo), "skipped": len(by("skipped")), "invalid": len(by("invalid")),
           "score_pct": round(100 * len(killed) / evaluated, 2) if evaluated else 0.0,
           "survivors": [r["name"] for r in surv], "survivor_text": [r["change"] for r in surv],
           "timed_out_text": [r["change"] for r in tmo], "skipped_text": [r["change"] for r in by("skipped")],
           "note": "score = killed / (killed + survived + timed_out); invalid and skipped mutants are excluded and listed; "
                   "an equivalent mutant (no visible behaviour change) shows as a survivor",
           "wall_seconds": round(time.monotonic() - t_start, 1), "rows": rows}
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(res, indent=2) + "\n")
    print(f"mutation score {res['score_pct']}% ({len(killed)} killed of {evaluated} evaluated; {len(surv)} survived, "
          f"{len(tmo)} timed out, {res['skipped']} skipped, {res['invalid']} invalid; {res['wall_seconds']} s) -> {out_json}")
    for t in res["survivor_text"]:
        print("  survivor:", t)
    return 0


def run(design: Path, mdir: Path, tag: str, sim: str) -> dict:
    env = dict(os.environ, SIM=sim, T1_SEEDS="1", T1_RTL_DIR=str(mdir), T1_RUN_TAG=tag)
    r = subprocess.run([PY, "-m", "pytest", "-q", "-x", str(design / "tests" / "test_t1_verif_rtl.py")],
                       capture_output=True, text=True, cwd=ROOT, env=env, timeout=1800)
    out = ROOT / "build" / "verif" / f"{sim}{tag}" / "seed1"
    built = (out / "results.xml").exists()
    log = (out / "sim.log").read_text(errors="replace") if (out / "sim.log").exists() else ""
    return {"built": built, "killed": r.returncode != 0, "assertion": "Assertion failed" in log}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--json")
    ap.add_argument("--only")
    ap.add_argument("--generic", action="store_true", help="any design: its tests/test_*_rtl.py, capped (brief 05k)")
    ap.add_argument("--max-mutants", type=int, default=DEFAULT_MAX_MUTANTS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--wall-s", type=int, default=None,
                    help="wall cap in seconds; default: baseline x (sample + 2), between 1500 s and 2 h (05n)")
    ap.add_argument("--mutant-timeout-s", type=int, default=0)
    ap.add_argument("--lock-wait-s", type=float, default=0)
    ap.add_argument("--sim", choices=("auto", "icarus", "verilator"), default="auto",
                    help="simulator for the baseline and every mutant (07a2 fix 5 E): auto = Verilator when available "
                         "and the design builds in it, else Icarus")
    ap.add_argument("--sandbox", choices=("auto", "container", "host"), default="auto",
                    help="where the design's tests run (05m): the sandbox image when it exists (auto), or force one")
    a = ap.parse_args()
    design = (ROOT / a.design).resolve()
    if a.generic:
        return generic(design, a)
    muts = yaml.safe_load((design / "verif" / "mutants.yaml").read_text())["mutants"]
    if a.only:
        muts = [m for m in muts if m["name"] in a.only.split(",")]
    rows = []
    for m in muts:
        d = ROOT / "build" / "mutants" / m["name"]
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for f in (design / "rtl").glob("*.sv"):
            shutil.copy(f, d / f.name)
        src = (d / m["file"]).read_text()
        assert src.count(m["old"]) == 1, f"{m['name']}: old text occurs {src.count(m['old'])} times"
        (d / m["file"]).write_text(src.replace(m["old"], m["new"]))
        row = {"name": m["name"], "class": m["class"], "why": m["why"]}
        row["tests"] = run(design, d, f"_mut_{m['name']}", "icarus")
        row["checkers"] = run(design, d, f"_mut_{m['name']}", "verilator")
        valid = row["tests"]["built"] or row["checkers"]["built"]
        row["valid"] = valid
        row["status"] = "invalid" if not valid else ("killed" if row["tests"]["killed"] else
                        ("killed_by_checkers_only" if row["checkers"]["killed"] else "survived"))
        print(f"{m['name']:22s} {m['class']:10s} {row['status']}", flush=True)
        rows.append(row)
    valid = [r for r in rows if r["valid"]]
    bench_killed = [r for r in valid if r["tests"]["killed"]]
    all_killed = [r for r in valid if r["tests"]["killed"] or r["checkers"]["killed"]]
    res = {"design": design.name, "mutants": len(rows), "valid": len(valid),
           "killed_by_bench": len(bench_killed), "score_pct": round(100 * len(bench_killed) / max(1, len(valid)), 2),
           "killed_with_checkers": len(all_killed),
           "score_with_checkers_pct": round(100 * len(all_killed) / max(1, len(valid)), 2),
           "survivors": [r["name"] for r in valid if not r["tests"]["killed"]],
           "survivors_with_checkers": [r["name"] for r in valid if not (r["tests"]["killed"] or r["checkers"]["killed"])],
           "rows": rows}
    print(f"bench score {res['score_pct']}% ({len(bench_killed)}/{len(valid)}); with checkers {res['score_with_checkers_pct']}%")
    print("survivors (bench):", res["survivors"], " survivors (bench+checkers):", res["survivors_with_checkers"])
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
