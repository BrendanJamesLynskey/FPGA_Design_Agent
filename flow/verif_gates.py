#!/usr/bin/env python3
"""Per-stage verification gates (brief 04f): V0 plan, V1 testplan + traceability, V2 tests/assertions/formal,
V3 coverage closure, V-HW board bring-up. Staged after OpenTitan's V0-V3 (Apache-2.0).

    python3 flow/verif_gates.py designs/t1_dimmer_counter [--runs build/verif/verilator] [--also build/verif/icarus]
        [--formal build/verif/formal] [--mutation results/04f/mutation_t1.json] [--hw results/f0b/..._bringup.json]
        [--json OUT]

Reads designs/<d>/verif/testplan.yaml, the cocotb results.xml of every seed under --runs, the functional-coverage
files, Verilator's coverage.dat, the SymbiYosys status files and the mutation result. Reports, per stage, every
check as {value, threshold, pass}: raw numbers only, no hints. Exit status 0 only if V0..V3 all pass
(V-HW is reported but needs the board; pass --require-hw to gate on it).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
#: a proof method per requirement (brief 05d, Taylor addition 1; FPGA Horizons issue 5)
PROOF_METHODS = ("simulation", "formal", "hardware", "analysis")


class PlanError(Exception):
    """An input the gates read (testplan.yaml, spec.yaml, the files they name) is malformed: reported as a failed
    gate with this message, never as a traceback (brief 05c2, fix 4)."""


def chk(value: Any, threshold: Any, ok: bool) -> dict[str, Any]:
    return {"value": value, "threshold": threshold, "pass": bool(ok)}


# ---- spec items -------------------------------------------------------------------------------------------
def spec_items(spec: dict) -> list[str]:
    """Every checkable statement of spec.yaml, by path: behaviour bullets, registers, reset, latencies."""
    items = [f"behaviour.{g}[{i}]" for g, v in spec["behaviour"].items() for i in range(len(v))]
    items += [f"registers.map.{r['name']}" for r in spec["registers"]["map"]]
    items += ["registers.unmapped", "reset"]
    items += [f"timing.latency.{k}" for k in spec.get("timing", {}).get("latency", {})]
    return items


# ---- evidence readers -------------------------------------------------------------------------------------
def read_results(run_dirs: list[Path]) -> dict[int, dict[str, bool]]:
    """seed -> {module.test: passed} from every seed*/results.xml."""
    out: dict[int, dict[str, bool]] = {}
    for rd in run_dirs:
        for x in sorted(rd.glob("seed*/results.xml")):
            seed = int(x.parent.name.removeprefix("seed"))
            tests = {}
            for tc in ET.parse(x).getroot().iter("testcase"):
                bad = any(c.tag in ("failure", "error") for c in tc)
                tests[f"{tc.get('classname', '').split('.')[-1]}.{tc.get('name')}"] = not bad
            out[seed] = tests
    return out


def merge_func_cov(run_dir: Path) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = {}
    for f in sorted(run_dir.glob("seed*/coverage_t1.yml")):
        for name, d in (yaml.safe_load(f.read_text()) or {}).items():
            hits = d.get("bins:_hits") if isinstance(d, dict) else None
            if hits:
                m = merged.setdefault(name, {})
                for b, n in hits.items():
                    m[str(b)] = m.get(str(b), 0) + int(n)
    return merged


def parse_cov_dat(path: Path) -> list[tuple[dict[str, str], int]]:
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("C '"):
            continue
        body, cnt = line[3:].rsplit("' ", 1)
        kv = {}
        for part in body.split("\x01")[1:]:
            k, _, v = part.partition("\x02")
            kv[k] = v
        rows.append((kv, int(cnt)))
    return rows


def merge_code_cov(run_dir: Path, rtl_dir: str) -> dict[str, Any]:
    """Merge coverage.dat of every seed: point key -> total hits; summarise line/toggle/branch in the design RTL
    and user (cover property) points."""
    pts: dict[tuple, int] = {}
    meta: dict[tuple, dict[str, str]] = {}
    for f in sorted(run_dir.glob("seed*/coverage.dat")):
        for kv, n in parse_cov_dat(f):
            key = tuple(sorted(kv.items()))
            pts[key] = pts.get(key, 0) + n
            meta[key] = kv
    summ: dict[str, Any] = {}
    for typ in ("line", "toggle", "branch"):
        sel = [k for k, kv in meta.items() if kv.get("t") == typ and rtl_dir in kv.get("f", "")]
        hit = sum(1 for k in sel if pts[k] > 0)
        summ[typ] = {"points": len(sel), "hit": hit, "pct": round(100 * hit / len(sel), 2) if sel else None,
                     "unhit": sorted(f"{Path(meta[k]['f']).name}:{meta[k].get('l')} {meta[k].get('o', '')}" for k in sel if pts[k] == 0)}
    user = {}
    for k, kv in meta.items():
        if kv.get("t") == "user" or "cover" in kv.get("page", ""):
            user[kv.get("o") or kv.get("h", "")] = user.get(kv.get("o") or kv.get("h", ""), 0) + pts[k]
    summ["user"] = user
    return summ


def read_formal(formal_dir: Path) -> dict[str, str]:
    out = {}
    for st in sorted(formal_dir.glob("*/status")):
        out[st.parent.name] = (st.read_text().split() or ["?"])[0]
    return out


def bench_tests(bench_dir: Path, modules: list[str]) -> set[str]:
    names = set()
    for m in modules:
        src = (bench_dir / f"{m}.py").read_text()
        for mm in re.finditer(r"@cocotb\.test\(.*?\)\s*\nasync def (\w+)", src):
            names.add(f"{m}.{mm.group(1)}")
    return names


def checker_names(chk_dir: Path, prefix: str) -> set[str]:
    return set(re.findall(rf"`V_\w+\(({prefix}\w+),", "".join(p.read_text() for p in chk_dir.glob("*.sv"))))


# ---- stages -----------------------------------------------------------------------------------------------
def _yaml_file(path: Path, what: str) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        mk = getattr(e, "problem_mark", None)
        pos = f"line {mk.line + 1}, column {mk.column + 1}" if mk else "unknown position"
        raise PlanError(f"{what} is not valid YAML at {pos}: {' '.join(str(getattr(e, 'problem', None) or e).split())}")
    except OSError as e:
        raise PlanError(f"{what} cannot be read: {e.strerror or e}")


def load_inputs(design: Path, plan_path: Path) -> tuple[dict, dict]:
    """The testplan and the spec it names, checked for the shape the gates read. Raises :class:`PlanError`."""
    rel = plan_path.relative_to(ROOT).as_posix() if plan_path.is_relative_to(ROOT) else plan_path.name
    plan = _yaml_file(plan_path, rel)
    if not isinstance(plan, dict):
        raise PlanError(f"{rel} must be a YAML mapping, not {type(plan).__name__}")
    need = ("spec", "model", "bench", "checkers", "formal_dir", "thresholds", "requirements")
    miss = [k for k in need if k not in plan]
    if miss:
        raise PlanError(f"{rel} has no {', '.join(repr(k) for k in miss)}")
    if not (isinstance(plan["bench"], dict) and isinstance(plan["bench"].get("modules"), list) and plan["bench"].get("dir")):
        raise PlanError(f"{rel}: 'bench' must be a mapping with 'modules' (a list) and 'dir'")
    if not isinstance(plan["thresholds"], dict):
        raise PlanError(f"{rel}: 'thresholds' must be a mapping")
    absent = [k for k in ("seeds_min", "functional_bins_pct", "cover_properties_pct", "line_pct", "toggle_pct",
                          "mutation_score_pct") if k not in plan["thresholds"]]
    if absent:
        raise PlanError(f"{rel}: thresholds has no {', '.join(repr(k) for k in absent)}")
    reqs = plan["requirements"]
    if not isinstance(reqs, list) or not reqs or not all(
            isinstance(r, dict) and r.get("id") and isinstance(r.get("spec"), list) for r in reqs):
        raise PlanError(f"{rel}: 'requirements' must be a non-empty list of mappings, each with an 'id' and a 'spec' list")
    spec_file = ROOT / str(plan["spec"])
    spec = _yaml_file(spec_file, str(plan["spec"]))
    try:
        spec_items(spec)
    except (TypeError, KeyError, AttributeError):
        raise PlanError(f"{plan['spec']} does not have the shape the gates read: 'behaviour' a mapping of lists, "
                        f"'registers' a mapping with a 'map' list of entries with a 'name', 'timing' a mapping") from None
    return plan, spec


def trace_table(reqs: list[dict], entries: list[dict], res: dict[int, dict[str, bool]], formal_res: dict[str, str],
                gates_json: dict | None, hw_json: dict | None) -> list[dict[str, Any]]:
    """The sign-off traceability table (brief 05d): requirement -> method -> artefact -> result. ``result`` is
    ``pass``, ``fail`` or ``pending`` (the evidence source does not exist yet, for example no board result): only
    ``pass`` counts at sign-off. Hardware artefacts are bring-up step names (``uart_tests``) or ``step:case``
    (``uart_tests:test_t1_registers_against_the_model``); analysis artefacts are flow gate names (``setup`` or
    ``post_route:setup``)."""
    rows: list[dict[str, Any]] = []
    flat_gates = (gates_json or {}).get("gates") or {}
    for r in reqs:
        for m in r.get("proof") or []:
            es = [e for e in entries if e.get("requirement") == r.get("id") and e.get("method") == m and e.get("artefact")]
            if not es:
                rows.append({"requirement": r.get("id"), "text": r.get("text", ""), "method": m, "artefact": "-",
                             "result": "fail", "detail": "no artefact declared in the testplan proof list"})
            for e in es:
                a = str(e["artefact"])
                result, detail = "pending", ""
                if m == "simulation":
                    if not res:
                        detail = "no simulation results"
                    else:
                        bad = [f"seed{s}" for s, tt in sorted(res.items()) if not tt.get(a, False)]
                        result, detail = ("pass", f"passed on {len(res)} seed(s)") if not bad else ("fail", "failed or missing on " + ", ".join(bad))
                elif m == "formal":
                    if not formal_res:
                        detail = "no formal results"
                    else:
                        got = {k: formal_res.get(f"{a}_{k}", "absent") for k in ("bmc", "cover")}
                        result = "pass" if all(v == "PASS" for v in got.values()) else "fail"
                        detail = ", ".join(f"{k}={v}" for k, v in got.items())
                elif m == "hardware":
                    if not hw_json:
                        detail = "no bring-up result"
                    else:
                        step, _, case = a.partition(":")
                        st = (hw_json.get("steps") or {}).get(step)
                        ok = bool(st) and st.get("pass") is True and (not case or case in (st.get("cases") or {}))
                        result, detail = ("pass", "bring-up step passed") if ok else ("fail", f"bring-up step {a} absent or failed")
                elif m == "analysis":
                    if not gates_json:
                        detail = "no flow gates result"
                    else:
                        stage, _, g = a.rpartition(":")
                        val = ((gates_json.get("stages") or {}).get(stage, {}).get("gates") or {}).get(g) if stage else flat_gates.get(g)
                        result = "pass" if val is True else "fail"
                        detail = f"gate {a} = {val}"
                rows.append({"requirement": r.get("id"), "text": r.get("text", ""), "method": m, "artefact": a,
                             "result": result, "detail": detail})
    return rows


def evaluate(design: Path, runs: Path, also: list[Path], formal: Path, mutation: Path | None, hw: Path | None,
             gates: Path | None = None) -> dict:
    plan_path = design / "verif" / "testplan.yaml"
    out: dict[str, Any] = {"design": design.name, "stages": {}}
    v0 = {"testplan_present": chk(plan_path.exists(), True, plan_path.exists())}
    out["stages"]["V0"] = {"checks": v0}
    if not plan_path.exists():
        return finish(out)
    try:
        plan, spec = load_inputs(design, plan_path)
    except PlanError as e:
        v0["testplan_valid"] = chk(str(e), "valid testplan and spec", False)
        return finish(out)
    reqs = plan["requirements"]
    th = plan["thresholds"]
    bench_dir, chk_dir, formal_src = ROOT / plan["bench"]["dir"], ROOT / plan["checkers"], ROOT / plan["formal_dir"]
    modules = plan["bench"]["modules"]
    v0["model_present"] = chk((ROOT / plan["model"]).exists(), True, (ROOT / plan["model"]).exists())
    v0["bench_modules_present"] = chk(modules, "all files exist", all((bench_dir / f"{m}.py").exists() for m in modules))
    if not v0["bench_modules_present"]["pass"]:          # the V1 readers below open the bench files
        return finish(out)
    # ---- V1: traceability
    items = spec_items(spec)
    traced = {s for r in reqs for s in r["spec"]}
    untraced = [i for i in items if i not in traced]
    unknown = sorted(traced - set(items))
    tests_all, a_all, c_all = bench_tests(bench_dir, modules), checker_names(chk_dir, "A_"), checker_names(chk_dir, "C_")
    formal_tasks = {p.stem for p in formal_src.glob("*.sby")}
    bad_refs = []
    for r in reqs:
        bad_refs += [f"{r['id']}:{t}" for t in r.get("tests", []) if t not in tests_all]
        bad_refs += [f"{r['id']}:{t}" for t in r.get("assertions", []) if t not in a_all]
        bad_refs += [f"{r['id']}:{t}" for t in r.get("cover_props", []) if t not in c_all]
        bad_refs += [f"{r['id']}:{t}" for t in r.get("formal", []) if t not in formal_tasks]
    no_check = [r["id"] for r in reqs if not (r.get("tests") or r.get("assertions") or r.get("formal"))]
    bench_src = "".join((bench_dir / f"{m}.py").read_text() for m in modules)
    uses_model = bool(re.search(r"(?m)^\s*(import\s+[\w.]*\bmodel\b|from\s+[\w.]*\bmodel\b\s+import|"
                                r"from\s+[\w.]+\s+import\s+[^\n]*\bmodel\b)", bench_src))
    spec_reqs = [r for r in (spec.get("requirements") or []) if isinstance(r, dict)]
    no_method = [str(r.get("id", f"#{i}")) for i, r in enumerate(spec_reqs)
                 if not (isinstance(r.get("proof"), list) and r["proof"] and all(m in PROOF_METHODS for m in r["proof"]))]
    if not spec_reqs:
        no_method = ["spec.yaml has no requirements"]
    entries = [e for e in (plan.get("proof") or []) if isinstance(e, dict)]
    undischarged = [f"{r.get('id')}:{m}" for r in spec_reqs for m in (r.get("proof") or [])
                    if m in PROOF_METHODS and not any(e.get("requirement") == r.get("id") and e.get("method") == m
                                                      and e.get("artefact") for e in entries)]
    ids = {r.get("id") for r in spec_reqs}
    bad_proof = []
    for e in entries:
        a, m = str(e.get("artefact", "")), e.get("method")
        if e.get("requirement") not in ids:
            bad_proof.append(f"{e.get('requirement')}: not a requirement of spec.yaml")
        elif m not in PROOF_METHODS:
            bad_proof.append(f"{e.get('requirement')}:{m}: not a proof method")
        elif m == "simulation" and a not in tests_all:
            bad_proof.append(f"{e['requirement']}:simulation:{a}: not a test in the bench")
        elif m == "formal" and a not in formal_tasks:
            bad_proof.append(f"{e['requirement']}:formal:{a}: not a formal job in {plan['formal_dir']}")
        elif not a:
            bad_proof.append(f"{e['requirement']}:{m}: no artefact")
    v1 = {
        "requirements_have_proof_method": chk(no_method, [], not no_method),
        "proof_methods_discharged": chk(undischarged, [], not undischarged and not no_method),
        "proof_references_resolve": chk(bad_proof, [], not bad_proof),
        "spec_items_traced": chk(f"{len(items) - len(untraced)}/{len(items)}", "all", not untraced),
        "untraced_items": chk(untraced, [], not untraced),
        "unknown_spec_refs": chk(unknown, [], not unknown),
        "requirements_without_a_check": chk(no_check, [], not no_check),
        "unresolved_references": chk(bad_refs, [], not bad_refs),
        "bench_uses_blind_model": chk(uses_model, True, uses_model),
    }
    out["stages"]["V1"] = {"checks": v1}
    # ---- V2: tests, assertions, formal
    res = read_results([runs])
    seeds = sorted(res)
    planned = {t for r in reqs for t in r.get("tests", [])}
    failing = sorted({f"seed{s}:{t}" for s in seeds for t, ok in res[s].items() if not ok})
    missing = sorted({f"seed{s}:{t}" for s in seeds for t in planned if t not in res[s]})
    also_bad = []
    for d in also:
        r2 = read_results([d])
        also_bad += [f"{d.name}/seed{s}:{t}" for s, tt in r2.items() for t, ok in tt.items() if not ok]
        if not r2:
            also_bad.append(f"{d.name}: no results")
    fr = read_formal(formal)
    wanted_formal = {f"{t}_{k}" for r in reqs for t in r.get("formal", []) for k in ("bmc", "cover")}
    formal_bad = sorted(f"{n}={fr.get(n, 'absent')}" for n in wanted_formal if fr.get(n) != "PASS")
    rand_ran = bool(seeds) and any("random" in t.lower() and ok for t, ok in res[seeds[0]].items())
    v2 = {
        "seeds_run": chk(seeds, f">=1", bool(seeds)),
        "planned_tests_missing": chk(missing, [], not missing and bool(seeds)),
        "failing_tests": chk(failing, [], not failing and bool(seeds)),
        "constrained_random_test_ran": chk(rand_ran, True, rand_ran),
        "assertions_bound_zero_failures": chk(sorted(a_all), "bound in the run; no failure", bool(seeds) and not failing),
        "other_simulators_failing": chk(also_bad, [], not also_bad),
        "formal_tasks_not_passing": chk(formal_bad, [], not formal_bad and bool(wanted_formal)),
    }
    out["stages"]["V2"] = {"checks": v2}
    # ---- V3: coverage closure
    waive = plan.get("waivers", {})
    bad_waive = [w for k in waive.values() for w in (k or []) if not str(w.get("reason", "")).strip()]
    func = merge_func_cov(runs)
    wb = {w["item"] for w in (waive.get("functional_bins") or [])}
    # count only the cover points and crosses the plan names, with every bin of each
    planned_bins = sorted({b for r in reqs for b in r.get("bins", [])})
    tot = hit = 0
    unhit = []
    for n in planned_bins:
        for b, h in (func.get(n) or {}).items():
            if f"{n}:{b}" in wb:
                continue
            tot += 1
            hit += h > 0
            if h == 0:
                unhit.append(f"{n}:{b}")
    pct = round(100 * hit / tot, 2) if tot else 0.0
    code = merge_code_cov(runs, plan["design_rtl"] if "design_rtl" in plan else f"{design.relative_to(ROOT).as_posix()}/rtl/") if list(runs.glob("seed*/coverage.dat")) else {}
    cp = {c for r in reqs for c in r.get("cover_props", [])}
    cpw = {w["item"] for w in (waive.get("cover_properties") or [])}
    cp_unhit = sorted(c for c in cp if c not in cpw and not any(c in k and v > 0 for k, v in code.get("user", {}).items()))
    cp_pct = round(100 * (len(cp - cpw) - len(cp_unhit)) / max(1, len(cp - cpw)), 2)
    line, tog = (code.get("line") or {}).get("pct"), (code.get("toggle") or {}).get("pct")
    mut = json.loads(mutation.read_text()) if mutation and mutation.exists() else None
    v3 = {
        "seeds_run": chk(len(seeds), f">={th['seeds_min']}", len(seeds) >= th["seeds_min"]),
        "all_seeds_pass": chk(failing, [], not failing and bool(seeds)),
        "functional_bins_pct": chk(f"{pct} ({hit}/{tot})", th["functional_bins_pct"], tot > 0 and pct >= th["functional_bins_pct"]),
        "functional_bins_unhit": chk(unhit, [], pct >= th["functional_bins_pct"]),
        "cover_properties_pct": chk(f"{cp_pct}", th["cover_properties_pct"], cp_pct >= th["cover_properties_pct"] and bool(code)),
        "cover_properties_unhit": chk(cp_unhit, [], not cp_unhit and bool(code)),
        "line_pct": chk(line, th["line_pct"], line is not None and line >= th["line_pct"]),
        "toggle_pct": chk(tog, th["toggle_pct"], tog is not None and tog >= th["toggle_pct"]),
        "waivers_without_reason": chk(len(bad_waive), 0, not bad_waive),
        "mutation_score_pct": chk(mut and mut["score_pct"], th["mutation_score_pct"],
                                  bool(mut) and mut["score_pct"] >= th["mutation_score_pct"]),
    }
    out["stages"]["V3"] = {"checks": v3}
    out["code_coverage"] = {k: {kk: vv for kk, vv in v.items() if kk != "unhit"} for k, v in code.items() if k != "user"}
    out["code_coverage_unhit"] = {k: v.get("unhit", []) for k, v in code.items() if k in ("line", "toggle", "branch")}
    out["mutation"] = mut
    # ---- sign-off: every proof method has passing evidence (brief 05d)
    gates_json = json.loads(gates.read_text()) if gates and gates.exists() else None
    hw_json = json.loads(hw.read_text()) if hw and hw.exists() else None
    table = trace_table(spec_reqs, entries, res, read_formal(formal), gates_json, hw_json)
    not_pass = [f"{r['requirement']}:{r['method']}={r['result']}" for r in table if r["result"] != "pass"]
    out["traceability"] = table
    out["stages"]["SIGNOFF"] = {"checks": {"every_method_has_passing_evidence": chk(not_pass, [], not not_pass and bool(table))}}
    out["coverage_detail"] = {"bins": func, "requirements": [
        {"id": r["id"], "spec": r["spec"], "tests": r.get("tests", []),
         "bins": {n: {"hit": sum(1 for h in (func.get(n) or {}).values() if h > 0), "total": len(func.get(n) or {})}
                  for n in r.get("bins", [])}} for r in reqs]}
    # ---- V-HW
    if hw and hw.exists():
        j = json.loads(hw.read_text())
        out["stages"]["V-HW"] = {"checks": {"bringup_pass": chk(j.get("pass"), True, j.get("pass") is True),
                                            "build_stamp": chk(j.get("build_stamp"), "recorded", bool(j.get("build_stamp")))}}
    else:
        out["stages"]["V-HW"] = {"checks": {"bringup_result_present": chk(False, True, False)}}
    return finish(out)


def finish(out: dict) -> dict:
    reached = None
    for s in ("V0", "V1", "V2", "V3"):
        st = out["stages"].get(s)
        if not st:
            break
        st["pass"] = all(c["pass"] for c in st["checks"].values())
        if not st["pass"]:
            break
        reached = s
    for extra in ("V-HW", "SIGNOFF"):
        if extra in out["stages"]:
            out["stages"][extra]["pass"] = all(c["pass"] for c in out["stages"][extra]["checks"].values())
    out["reached"] = reached
    out["first_failed"] = next((s for s in ("V0", "V1", "V2", "V3") if s in out["stages"] and not out["stages"][s].get("pass")), None)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--runs", default="build/verif/verilator")
    ap.add_argument("--also", action="append", default=[])
    ap.add_argument("--formal", default="build/verif/formal")
    ap.add_argument("--mutation")
    ap.add_argument("--hw")
    ap.add_argument("--gates", help="gates.json of the build (flow/gates.py): evidence for analysis proofs")
    ap.add_argument("--json")
    ap.add_argument("--require-hw", action="store_true")
    ap.add_argument("--require-signoff", action="store_true", help="exit 1 unless every proof method has passing evidence")
    a = ap.parse_args(argv)
    rel = lambda p: (ROOT / p) if not Path(p).is_absolute() else Path(p)
    try:
        rep = evaluate(rel(a.design), rel(a.runs), [rel(x) for x in a.also], rel(a.formal),
                       rel(a.mutation) if a.mutation else None, rel(a.hw) if a.hw else None,
                       rel(a.gates) if a.gates else None)
    except (PlanError, OSError, KeyError, TypeError, ValueError, AttributeError, SyntaxError) as e:
        # whatever else a gate input throws, the answer is a failed gate with the message, not a traceback
        msg = e.args[0] if isinstance(e, PlanError) and e.args else f"{type(e).__name__}: {e}"
        rep = finish({"design": Path(a.design).name, "stages": {"V0": {"checks": {
            "gate_inputs_readable": chk(str(msg)[:600], "readable", False)}}}})
    for s, st in rep["stages"].items():
        print(f"{s}: {'PASS' if st.get('pass') else 'FAIL'}")
        for n, c in st["checks"].items():
            print(f"    {'ok ' if c['pass'] else 'BAD'} {n}: {c['value']}  (threshold {c['threshold']})")
    for r in rep.get("traceability") or []:
        print(f"    trace {r['requirement']:8} {r['method']:10} {r['artefact']:55} {r['result']:8} {r['detail']}")
    print(f"reached: {rep['reached']}  first failed: {rep['first_failed']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2, default=str) + "\n")
    ok = (rep["first_failed"] is None and (not a.require_hw or rep["stages"].get("V-HW", {}).get("pass"))
          and (not a.require_signoff or rep["stages"].get("SIGNOFF", {}).get("pass")))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
