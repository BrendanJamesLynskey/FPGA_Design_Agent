#!/usr/bin/env python3
"""Per-stage verification gates (brief 04f): V0 plan, V1 testplan + traceability, V2 tests/assertions/formal,
V3 coverage closure, V-HW board bring-up. Staged after OpenTitan's V0-V3 (Apache-2.0).

    python3 flow/verif_gates.py designs/t1_dimmer_counter [--runs build/verif/verilator] [--also build/verif/icarus]
        [--formal build/verif/formal] [--mutation results/04f/mutation_t1.json] [--hw results/f0b/..._bringup.json]
        [--json OUT]

Reads designs/<d>/verif/testplan.yaml, the cocotb results.xml of every seed under --runs, the functional-coverage
files, Verilator's coverage.dat, the SymbiYosys status files and the mutation result. Reports, per stage, every
check as {value, threshold, pass}, plus a plain-words `why` on a failure that names its precondition (05j). Exit status 0 only if V0..V3 all pass
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


FLOORS_FILE = Path(__file__).with_name("verif_floors.yaml")
#: the V3 thresholds the testplan cannot lower (brief 05n); the file is the source, this is the fallback shape
THRESHOLD_FLOORS = ("seeds_min", "functional_bins_pct", "cover_properties_pct", "line_pct", "toggle_pct", "mutation_score_pct")


def load_floors() -> dict[str, float]:
    """``flow/verif_floors.yaml``: the harness's fixed V3 floors, read by the gate on every call."""
    return yaml.safe_load(FLOORS_FILE.read_text())


def effective_thresholds(plan_th: dict, floors: dict) -> tuple[dict, dict[str, str]]:
    """``max(floor, plan value)`` for every V3 threshold. Returns the thresholds and, for each one the plan set below
    its floor, the sentence the check's ``why`` carries ("testplan asked 0%, the floor is 100%")."""
    th, ignored = dict(plan_th), {}
    for k in THRESHOLD_FLOORS:
        fl, asked = floors[k], plan_th.get(k)
        try:
            low = asked is None or float(asked) < float(fl)
        except (TypeError, ValueError):
            low = True
        if low:
            th[k] = fl
            unit = "" if k == "seeds_min" else "%"
            ignored[k] = f"testplan asked {asked}{unit if asked is not None else ''}, the floor is {fl}{unit} (flow/verif_floors.yaml)"
    return th, ignored


def formal_installed() -> bool:
    """SymbiYosys is on this process's PATH (the agent's tools run with the local tools file's PATH, so this is the
    answer for the agent's own environment). Overridable in tests."""
    import shutil
    return shutil.which("sby") is not None and shutil.which("yosys") is not None


def replan_entries(plan: dict, spec_reqs: list[dict]) -> tuple[list[dict], list[str]]:
    """Brief 05g. When a requirement's proof method cannot be carried out the test writer re-plans it in the testplan:
    ``replan: [{requirement, method, replaced_by, artefact, why}]``. Only ``formal`` may be re-planned, and only when
    SymbiYosys is not installed; it needs a ``why`` and a replacement artefact of another method. Returns the
    equivalent proof entries (carrying ``replan``) and the problems; a proof is never marked discharged without its
    evidence (the replacement method's evidence is what the sign-off table reads)."""
    ids = {r.get("id") for r in spec_reqs}
    entries: list[dict] = []
    bad: list[str] = []
    for e in (plan.get("replan") or []):
        if not isinstance(e, dict):
            bad.append("replan entry is not a mapping")
            continue
        req, m, to, a = e.get("requirement"), e.get("method"), e.get("replaced_by"), str(e.get("artefact") or "")
        tag = f"{req}:{m}->{to}"
        if req not in ids:
            bad.append(f"{tag}: replan names a requirement that spec.yaml does not have")
        elif m != "formal":
            bad.append(f"{tag}: only the formal method can be re-planned")
        elif to not in PROOF_METHODS or to == "formal":
            bad.append(f"{tag}: replaced_by must be simulation, hardware or analysis")
        elif not a:
            bad.append(f"{tag}: no replacement artefact")
        elif len(str(e.get("why") or "").strip()) < 12:
            bad.append(f"{tag}: say why (at least a sentence in 'why')")
        elif formal_installed():
            bad.append(f"{tag}: SymbiYosys is installed here, so the formal job is written and run, not re-planned")
        else:
            entries.append({"requirement": req, "method": m, "artefact": a,
                            "replan": {"to": to, "why": str(e["why"]).strip()}})
    return entries, bad


class PlanError(Exception):
    """An input the gates read (testplan.yaml, spec.yaml, the files they name) is malformed: reported as a failed
    gate with this message, never as a traceback (brief 05c2, fix 4)."""


def chk(value: Any, threshold: Any, ok: bool, why: str | None = None) -> dict[str, Any]:
    """One check. ``why`` (05j) is the plain-words reason for a failure; it is carried only on a failed check, and
    always says the hidden precondition when the value alone looks fine (a value that meets its threshold but fails)."""
    c = {"value": value, "threshold": threshold, "pass": bool(ok)}
    if why and not ok:
        c["why"] = why
    return c


NOT_EVALUATED = "not evaluated (no seeded results)"
NOT_MEASURED = "not measured"
#: what the tests role can do about each kind of V3 evidence (05l: only actions the role has; the coverage run and the
#: mutation run are made by the flow itself once V2 passes, so these texts name no tool the role cannot call)
HOW_CODE_COV = ("the flow records line, toggle and cover-property coverage itself, in a Verilator run of your bench, once "
                "V0 to V2 pass (the bench must run through flow.cocotb_run.run, which writes seed<N>/coverage.dat)")
HOW_FUNC_COV = ("name cover points in the `bins:` of the testplan requirements, sample them in the bench, and export them "
                "in the bench's last test with `coverage_db.export_to_yaml(os.environ[\"FDA_COV_OUT\"])` "
                "(cocotb-coverage); the flow keeps the file as seed<N>/coverage_func.yml")
HOW_MUTATION = ("the flow runs the mutation step itself once V2 passes (a capped, seeded sample of changes to the RTL, each run "
                "against your tests); no result exists yet")


def _more(items: list, n: int = 6) -> str:
    return ", ".join(str(x) for x in items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


def mutation_why(mut: dict | None, reason: str | None = None, enough: int | None = None) -> str:
    """05k/05l: the plain reason the mutation check fails: not measured (and why, from the flow's own step), or the
    surviving mutants as file, line and change, so the tests role can tighten its checks."""
    if not mut:
        return "not measured: " + (reason or HOW_MUTATION)
    if enough is not None and mut.get("evaluated") is not None and 0 < mut["evaluated"] < enough:
        return (f"not enough mutants evaluated: {mut['evaluated']} of {mut.get('candidates', mut.get('sampled', '?'))} "
                f"(skipped {mut.get('skipped', 0)} by the wall cap, {mut.get('invalid', 0)} invalid); at least {enough} must be "
                f"evaluated before the score {mut['score_pct']}% counts. The flow runs the mutation step again at the next "
                f"visit; nothing in the tests can raise the number evaluated")
    if mut.get("evaluated", 1) == 0:
        return ("no mutant was evaluated (" + f"{mut.get('invalid', 0)} invalid, {mut.get('skipped', 0)} skipped by the wall-time cap"
                + "): the score is not measured; the flow runs the mutation step again at the next visit")
    text = mut.get("survivor_text") or mut.get("survivors") or []
    more = f" (+{len(text) - 5} more in build/verif/mutation.json)" if len(text) > 5 else ""
    extra = ""
    if mut.get("timed_out"):
        extra = f"; {mut['timed_out']} timed out and count as not killed"
    return (f"mutation score {mut['score_pct']}% is below the threshold{extra}: your tests still passed when the design was "
            f"changed" + (" as follows (file, line, change): " + " | ".join(text[:5]) + more if text else "")
            + ". Tighten the checks so a test fails for each change (compare more outputs, add a test that exercises the "
              "changed behaviour)")


def no_seeds_hint(runs: Path) -> str:
    """The one actionable line when the gate found no ``seed*/results.xml`` (05h): where it looked, what it expects
    there, and how the tests role produces it."""
    try:
        shown = runs.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(runs)
    return (f"no seeded results: read {shown}/seed*/results.xml and found none. The gate expects "
            f"{shown}/seed<N>/results.xml, one directory per seed. The flow's simulation step writes it when the bench runs "
            f"through flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=N) in "
            f"tests/test_*_rtl.py: call run() once per seed (for example seed=1, 2, 3; a seed left out counts as seed 1) "
            f"with the module(s) listed in bench.modules; the flow runs it and checks again. A bench "
            f"that runs the simulator some other way leaves nothing there.")


def ne(threshold: Any) -> dict[str, Any]:
    """A check that cannot be evaluated; it fails, but says so instead of printing an empty value."""
    return chk(NOT_EVALUATED, threshold, False)


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
                # a skipped test is not a pass (QR1: cocotb writes <skipped/>; `skip=True` satisfied "planned test present")
                bad = any(c.tag in ("failure", "error", "skipped") for c in tc)
                tests[f"{tc.get('classname', '').split('.')[-1]}.{tc.get('name')}"] = not bad
            out[seed] = tests
    return out


def merge_func_cov(run_dir: Path) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = {}
    for f in sorted(run_dir.glob("seed*/coverage*.yml")):
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
    for f in sorted(run_dir.glob("seed*/coverage*.dat")):
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


def plain_sv_names(chk_dir: Path, prefix: str) -> set[str]:
    """Names with ``prefix`` that appear in the checker files in any form (05i): a name here that ``checker_names``
    lacks was declared as plain SystemVerilog (``C_x: cover property (...)``), which the gate does not read."""
    return set(re.findall(rf"\b({prefix}\w+)\b", "".join(p.read_text() for p in chk_dir.glob("*.sv"))))


# ---- the macro file (05i) -------------------------------------------------------------------------------------
MACROS_CANON = Path(__file__).resolve().parent / "v_macros.svh"      # the one canonical copy, owned by the flow
MACROS_REL = "verif/checkers/v_macros.svh"                          # where every design carries it


def seed_macros(design: Path) -> bool:
    """Put the canonical ``v_macros.svh`` in the design's ``verif/checkers`` if it is not there. True if it wrote it."""
    dst = design / MACROS_REL
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(MACROS_CANON.read_text())
    return True


def macros_warning(chk_dir: Path) -> str | None:
    """A warning when the design's ``v_macros.svh`` differs from the canonical copy (or is absent while checkers exist)."""
    f = chk_dir / "v_macros.svh"
    if not f.exists():
        return ("verif/checkers/v_macros.svh is missing: the gate reads A_*/C_* names only from `V_SAME/V_NEXT/V_RST/V_COVER"
                "(name, ...)` of that file; restore it from flow/v_macros.svh") if any(chk_dir.glob("*.sv")) else None
    if f.read_text() != MACROS_CANON.read_text():
        return "verif/checkers/v_macros.svh differs from the flow's canonical copy (flow/v_macros.svh); it is the flow's file, do not edit it"
    return None


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


def plan_file(design: Path, p) -> Path:
    """A path named in the testplan: absolute, repo-relative (the documented form) or, as a fallback, relative to the
    design directory (live run 20261105-001259-e811 wrote ``model: model.py`` and V0 failed on a file that existed)."""
    q = Path(str(p))
    if q.is_absolute():
        return q
    if (ROOT / q).exists() or not (design / q).exists():
        return ROOT / q
    return design / q


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
    spec_file = plan_file(design, plan["spec"])
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
                rp = e.get("replan")
                me = rp["to"] if rp else m          # a re-planned formal method is judged by the replacement's evidence
                if me == "simulation":
                    if not res:
                        detail = "no simulation results"
                    else:
                        bad = [f"seed{s}" for s, tt in sorted(res.items()) if not tt.get(a, False)]
                        result, detail = ("pass", f"passed on {len(res)} seed(s)") if not bad else ("fail", "failed or missing on " + ", ".join(bad))
                elif me == "formal":
                    if not formal_res:
                        detail = "no formal results"
                    else:
                        got = {k: formal_res.get(f"{a}_{k}", "absent") for k in ("bmc", "cover")}
                        result = "pass" if all(v == "PASS" for v in got.values()) else "fail"
                        detail = ", ".join(f"{k}={v}" for k, v in got.items())
                elif me == "hardware":
                    if not hw_json:
                        detail = "no bring-up result"
                    else:
                        step, _, case = a.partition(":")
                        st = (hw_json.get("steps") or {}).get(step)
                        ok = bool(st) and st.get("pass") is True and (not case or case in (st.get("cases") or {}))
                        result, detail = ("pass", "bring-up step passed") if ok else ("fail", f"bring-up step {a} absent or failed")
                elif me == "analysis":
                    if not gates_json:
                        detail = "no flow gates result"
                    else:
                        stage, _, g = a.rpartition(":")
                        val = ((gates_json.get("stages") or {}).get(stage, {}).get("gates") or {}).get(g) if stage else flat_gates.get(g)
                        result = "pass" if val is True else "fail"
                        detail = f"gate {a} = {val}"
                if rp:
                    detail = f"re-planned from formal to {me} ({rp['why']}): {detail}"
                rows.append({"requirement": r.get("id"), "text": r.get("text", ""), "method": m, "artefact": a,
                             "result": result, "detail": detail})
    return rows


def fsm_cov_check(path: Path) -> dict[str, Any]:
    """Brief 24: the evidence file of ``python -m flow.fsm_coverage`` (every state visited, every legal transition of the
    spec's state table taken, none outside it). A missing or unreadable file fails with the command that makes it."""
    how = ("run the bench with FDA_FSM_TRACE=<dir> and then `python -m flow.fsm_coverage <design> --trace <dir>/<run>.fsmtrace "
           "--json <evidence>.json` (design needs verif/fsm.yaml: the state table)")
    try:
        rep = json.loads(path.read_text())
    except (OSError, ValueError):
        return chk("no evidence", "every state and legal transition hit", False, f"{path} is missing or not JSON: {how}")
    if rep.get("error"):
        return chk("no state table", "every state and legal transition hit", False, str(rep["error"]))
    fsms = rep.get("fsms") or []
    val = ", ".join(f"{f['name']}: states {f['states_hit']}/{f['n_states']}, transitions {f['transitions_hit']}/{f['transitions_listed']}"
                    for f in fsms) or "no FSMs listed"
    miss = [f"{f['name']}: " + "; ".join(
        [f"state {s} never visited" for s in f["states_missed"]] + [f"transition {t} never taken" for t in f["transitions_missed"]]
        + [f"transition {t} taken but not in the table" for t in f["unexpected_transitions"]]
        + [f"waiver without a reason: {w}" for w in f["waivers_without_reason"]]) for f in fsms if not f["pass"]]
    return chk(val, "every state and legal transition hit", bool(fsms) and not miss,
               ("; ".join(miss) + ". Add a test that reaches it (a stimulus that drives the machine there), or waive it in "
                "verif/fsm.yaml with a reason; an illegal transition is for formal, not for simulation") if miss else None)


def cdc_checks(design: Path, gates_json: dict | None, cdc_inject_file: Path | None) -> dict[str, Any]:
    """Brief 16: the two CDC checks of V3, for a design that has a clock-domain crossing (an ASYNC_REG register, an XPM CDC macro or
    several declared clock domains; none otherwise). ``cdc_structure_clean`` is the post-synthesis structural check
    (flow/cdc_structure.py, in the flow's gates.json); ``cdc_injection_clean`` is the design's own tests run with synchroniser
    delay injection (flow/cdc_inject_run.py). report_cdc alone passes a bus crossed bit by bit, reconverging synchronisers and a
    pulse into a level synchroniser. A missing report fails its check."""
    try:
        from flow import cdc_inject
    except ImportError:
        import cdc_inject
    if not cdc_inject.design_crosses(design):
        return {}
    how = "run flow/cdc_inject_run.py <design> (the harness does this in v3_evidence) and pass build/verif/cdc_inject.json as --cdc-inject"
    out: dict[str, Any] = {}
    gg = (((gates_json or {}).get("stages") or {}).get("post_synth") or {}).get("gates") or {}
    cs = (((gates_json or {}).get("stages") or {}).get("post_synth") or {}).get("cdc_structure") or {}
    if "post_synth_cdc_structure_clean" in gg:
        bad = [f"{u['rule']} {u['cell']}: {u['why']}" for u in (cs.get("unsafe") or [])]
        out["cdc_structure_clean"] = chk(bad if bad else "no unsafe crossing", "no unsafe crossing",
                                         bool(gg["post_synth_cdc_structure_clean"]),
                                         ("; ".join(bad[:4]) + (f" (+{len(bad) - 4} more in gates.json)" if len(bad) > 4 else "")) if bad
                                         else "the structural CDC check could not read cdc_paths_synth.rpt")
    else:
        out["cdc_structure_clean"] = chk("missing", "no unsafe crossing", False,
                                         "no structural CDC result: build the design through the post-synthesis stage "
                                         "(flow/build.tcl writes cdc_paths_synth.rpt) and pass its gates.json as --gates")
    try:
        ev = json.loads(cdc_inject_file.read_text()) if cdc_inject_file and cdc_inject_file.exists() else None
    except (OSError, ValueError):
        ev = None
    if ev is None:
        out["cdc_injection_clean"] = chk("missing", "pass", False, "no CDC injection result: " + how)
    else:
        out["cdc_injection_clean"] = chk("pass" if ev.get("pass") else "fail", "pass", bool(ev.get("pass")),
                                         ev.get("why") or None)
    return out


def evaluate(design: Path, runs: Path, also: list[Path], formal: Path, mutation: Path | None, hw: Path | None,
             gates: Path | None = None, evidence: Path | None = None, cdc_inject_file: Path | None = None,
             fsm_cov: Path | None = None) -> dict:
    plan_path = design / "verif" / "testplan.yaml"
    out: dict[str, Any] = {"design": design.name, "stages": {}}
    v0 = {"testplan_present": chk(plan_path.exists(), True, plan_path.exists(),
                                  f"{plan_path.relative_to(ROOT).as_posix() if plan_path.is_relative_to(ROOT) else plan_path} "
                                  f"does not exist: write the testplan (verif/testplan.yaml)")}
    out["stages"]["V0"] = {"checks": v0}
    if not plan_path.exists():
        return finish(out)
    try:
        plan, spec = load_inputs(design, plan_path)
    except PlanError as e:
        v0["testplan_valid"] = chk(str(e), "valid testplan and spec", False)
        return finish(out)
    reqs = plan["requirements"]
    floors = load_floors()
    th, below = effective_thresholds(plan["thresholds"], floors)      # 05n: the plan may raise a threshold, never lower it
    bench_dir, chk_dir, formal_src = (plan_file(design, plan["bench"]["dir"]), plan_file(design, plan["checkers"]),
                                      plan_file(design, plan["formal_dir"]))
    modules = plan["bench"]["modules"]
    model_file = plan_file(design, plan["model"])
    want = (design / "model.py").relative_to(ROOT).as_posix() if design.is_relative_to(ROOT) else str(design / "model.py")
    v0["model_present"] = chk(model_file.exists(), True, model_file.exists(),
                              f"the testplan names model {plan['model']}, which does not exist (repo-relative, e.g. {want})")
    absent_mods = [f"{plan['bench']['dir']}/{m}.py" for m in modules if not (bench_dir / f"{m}.py").exists()]
    v0["bench_modules_present"] = chk(modules, "all files exist", not absent_mods,
                                      "bench.modules lists files that do not exist: " + ", ".join(absent_mods))
    if not v0["bench_modules_present"]["pass"]:          # the V1 readers below open the bench files
        return finish(out)
    # ---- V1: traceability
    items = spec_items(spec)
    traced = {s for r in reqs for s in r["spec"]}
    untraced = [i for i in items if i not in traced]
    unknown = sorted(traced - set(items))
    tests_all, a_all, c_all = bench_tests(bench_dir, modules), checker_names(chk_dir, "A_"), checker_names(chk_dir, "C_")
    formal_tasks = {p.stem for p in formal_src.glob("*.sby")}
    plain = plain_sv_names(chk_dir, "A_") | plain_sv_names(chk_dir, "C_")
    plain_note = " (declared as plain SV; the gate reads only `V_*(name, ...)` from v_macros.svh)"      # 05i
    bad_refs = []
    for r in reqs:
        bad_refs += [f"{r['id']}:{t}" for t in r.get("tests", []) if t not in tests_all]
        bad_refs += [f"{r['id']}:{t}" + (plain_note if t in plain else "") for t in r.get("assertions", []) if t not in a_all]
        bad_refs += [f"{r['id']}:{t}" + (plain_note if t in plain else "") for t in r.get("cover_props", []) if t not in c_all]
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
    re_entries, bad_replan = replan_entries(plan, spec_reqs)
    entries += re_entries
    undischarged = [f"{r.get('id')}:{m}" for r in spec_reqs for m in (r.get("proof") or [])
                    if m in PROOF_METHODS and not any(e.get("requirement") == r.get("id") and e.get("method") == m
                                                      and e.get("artefact") for e in entries)]
    ids = {r.get("id") for r in spec_reqs}
    bad_proof = []
    for e in entries:
        a, m = str(e.get("artefact", "")), e.get("method")
        if e.get("replan"):
            to = e["replan"]["to"]
            ok_ref = {"simulation": a in tests_all, "hardware": True, "analysis": True}.get(to, False)
            if not ok_ref:
                bad_proof.append(f"{e['requirement']}:formal->{to}:{a}: not a test in the bench")
        elif e.get("requirement") not in ids:
            bad_proof.append(f"{e.get('requirement')}: not a requirement of spec.yaml")
        elif m not in PROOF_METHODS:
            bad_proof.append(f"{e.get('requirement')}:{m}: not a proof method")
        elif m == "simulation" and a not in tests_all:
            bad_proof.append(f"{e['requirement']}:simulation:{a}: not a test in the bench")
        elif m == "formal" and a not in formal_tasks:
            hint = ("; it is a test in the bench, so its method is `simulation`" if a in tests_all else "")
            bad_proof.append(f"{e['requirement']}:formal:{a}: not a formal job in {plan['formal_dir']}{hint}; "
                             f"valid methods: {', '.join(sorted(PROOF_METHODS))} (a bench test is `simulation`, "
                             "`formal` names a job in the formal directory)")
        elif not a:
            bad_proof.append(f"{e['requirement']}:{m}: no artefact")
    bad_proof += bad_replan
    v1 = {
        "requirements_have_proof_method": chk(no_method, [], not no_method),
        "proof_methods_discharged": chk(undischarged, [], not undischarged and not no_method,
                                        "nothing is undischarged, but the proof methods themselves are not all declared: "
                                        "fix requirements_have_proof_method first" if not undischarged else None),
        "proof_references_resolve": chk(bad_proof, [], not bad_proof),
        "spec_items_traced": chk(f"{len(items) - len(untraced)}/{len(items)}", "all", not untraced),
        "untraced_items": chk(untraced, [], not untraced),
        "unknown_spec_refs": chk(unknown, [], not unknown),
        "requirements_without_a_check": chk(no_check, [], not no_check),
        "unresolved_references": chk(bad_refs, [], not bad_refs),
        "bench_uses_blind_model": chk(uses_model, True, uses_model,
                                      "no bench module imports the model: add `from <package>.model import ...` or "
                                      "`import model` to a module in bench.modules and compare the DUT with it"),
    }
    out["stages"]["V1"] = {"checks": v1}
    mw = macros_warning(chk_dir)                          # 05i: a warning, not a failed check
    if mw:
        out["warnings"] = [mw]
    # ---- V2: tests, assertions, formal
    res = read_results([runs])
    seeds = sorted(res)
    planned = {t for r in reqs for t in r.get("tests", [])}
    failing = sorted({f"seed{s}:{t}" for s in seeds for t, ok in res[s].items() if not ok})
    # cocotb reports a failing `expect_fail=True` / `expect_error` test as a pass, and `skip=True` as skipped: none may stand in for a check
    failing += sorted({f"bench:{m.group(1)}=True" for m in re.finditer(r"@cocotb\.test\s*\([^)]*?\b(expect_fail|expect_error|skip)\s*=\s*(?!False\b)\w", bench_src)})
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
    if seeds:
        v2 = {
            "seeds_run": chk(seeds, f">=1", True),
            "planned_tests_missing": chk(missing, [], not missing),
            "failing_tests": chk(failing, [], not failing),
            "constrained_random_test_ran": chk(rand_ran, True, rand_ran,
                                               "no passing test with 'random' in its name in seed%s: name the constrained-random "
                                               "test so (for example test_random_traffic) and run it" % seeds[0]),
            "assertions_bound_zero_failures": chk(sorted(a_all), "bound in the run; no failure", not failing,
                                                "a test failed in some seed: see failing_tests"),
            "other_simulators_failing": chk(also_bad, [], not also_bad),
            "formal_tasks_not_passing": chk(formal_bad, [], not formal_bad,
                                            "a planned formal job has no PASS: run the `formal` tool, or re-plan the method "
                                            "(replan: in the testplan) when sby is not installed"),
        }
    else:
        v2 = {
            "seeds_run": chk(no_seeds_hint(runs), ">=1 seed", False),
            "planned_tests_missing": ne([]),
            "failing_tests": ne([]),
            "constrained_random_test_ran": ne(True),
            "assertions_bound_zero_failures": ne("bound in the run; no failure"),
            "other_simulators_failing": chk(also_bad, [], not also_bad),
            "formal_tasks_not_passing": chk(formal_bad, [], not formal_bad,
                                            "a planned formal job has no PASS: run the `formal` tool, or re-plan the method "
                                            "(replan: in the testplan) when sby is not installed"),
        }
    if fsm_cov is not None:                              # brief 24, behind --fsm-coverage: state and transition coverage of the FSMs
        v2["fsm_state_transition_coverage"] = fsm_cov_check(fsm_cov)
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
    code = merge_code_cov(runs, plan["design_rtl"] if "design_rtl" in plan else f"{design.relative_to(ROOT).as_posix()}/rtl/") if list(runs.glob("seed*/coverage*.dat")) else {}
    cp = {c for r in reqs for c in r.get("cover_props", [])}
    cpw = {w["item"] for w in (waive.get("cover_properties") or [])}
    cp_unhit = sorted(c for c in cp if c not in cpw and not any(c in k and v > 0 for k, v in code.get("user", {}).items()))
    cp_pct = round(100 * (len(cp - cpw) - len(cp_unhit)) / max(1, len(cp - cpw)), 2)
    line, tog = (code.get("line") or {}).get("pct"), (code.get("toggle") or {}).get("pct")
    mut = json.loads(mutation.read_text()) if mutation and mutation.exists() else None
    try:      # 05l: the flow's own V3 steps say why they did not measure something (busy lock, no Verilator, a failed run)
        ev3 = json.loads(evidence.read_text()) if evidence and evidence.exists() else {}
    except (OSError, ValueError):
        ev3 = {}
    cov_reason, mut_reason = (ev3.get("coverage") or {}).get("why"), (ev3.get("mutation") or {}).get("why")
    rtl_rel = plan["design_rtl"] if "design_rtl" in plan else f"{design.relative_to(ROOT).as_posix()}/rtl/"
    th_bins = th["functional_bins_pct"]
    if not planned_bins:
        bins_why = ("no functional bins planned: put cover-point names in `bins:` of the testplan requirements. " + HOW_FUNC_COV)
    elif not func:
        bins_why = (f"{len(planned_bins)} bin group(s) planned but no functional-coverage data was found "
                    f"(seed*/coverage*.yml): " + HOW_FUNC_COV)
    elif tot == 0:
        bins_why = ("the planned bin names (" + ", ".join(planned_bins[:6]) + ") are not in the functional-coverage data (it has: "
                    + ", ".join(sorted(func)[:6]) + "): use the same names in the testplan and the bench")
    else:
        bins_why = f"{hit} of {tot} planned bins were hit; the threshold needs {th_bins}%: see functional_bins_unhit"
    if not code:
        code_why = "not measured: no code-coverage data: " + (cov_reason or HOW_CODE_COV)
    elif not cp - cpw:
        code_why = "no cover properties planned: name them in `cover_props:` of the requirements (C_*, declared with V_COVER)"
    else:
        code_why = (f"cover properties not hit: {_more(cp_unhit)}: add or extend a test that drives the design into each, "
                    f"or correct the `V_COVER` expression if it can never be true")

    def meas(kind: str, val: Any) -> tuple[Any, str | None]:
        """``(value, why)`` for line/toggle: 'not measured: how' when the evidence never existed."""
        if val is not None:
            gaps = (code.get(kind) or {}).get("unhit") or []
            what = "lines never executed" if kind == "line" else "signal bits that never changed"
            return val, (f"{kind} coverage is {val}%, below the {th[kind + '_pct']}% threshold: {what} (file:line object): "
                         f"{_more(gaps)}: add or extend tests that reach them, or waive them with a reason in the testplan")
        if not code:
            return NOT_MEASURED, f"not measured: no code-coverage data: " + (cov_reason or HOW_CODE_COV)
        return NOT_MEASURED, (f"not measured: coverage.dat has no {kind} points in {rtl_rel}: build the RTL under test in the "
                              f"coverage run and check the plan's design_rtl path")
    line_v, line_why = meas("line", line)
    tog_v, tog_why = meas("toggle", tog)
    # 05n: a score counts only when enough mutants were evaluated: min_evaluated, or every candidate when fewer exist
    need = min(int(floors["mutation_min_evaluated"]), int(mut.get("candidates") or floors["mutation_min_evaluated"])) if mut else None
    enough_ev = not mut or mut.get("evaluated") is None or mut["evaluated"] >= need
    mut_ok = bool(mut) and mut["score_pct"] >= th["mutation_score_pct"] and mut.get("evaluated", 1) > 0 and enough_ev
    v3 = {
        "seeds_run": chk(len(seeds) if seeds else no_seeds_hint(runs), f">={th['seeds_min']}", len(seeds) >= th["seeds_min"],
                         f"{len(seeds)} seed(s) run, the plan needs {th['seeds_min']}: call flow.cocotb_run.run once per seed"),
        "all_seeds_pass": chk(failing, [], not failing and bool(seeds)) if seeds else ne([]),
        "functional_bins_pct": chk(f"{pct} ({hit}/{tot})", th_bins, tot > 0 and pct >= th_bins, bins_why),
        "functional_bins_unhit": chk(unhit, [], pct >= th_bins, bins_why),
        "cover_properties_pct": chk(f"{cp_pct}", th["cover_properties_pct"], cp_pct >= th["cover_properties_pct"] and bool(code),
                                    code_why if (not code or not cp - cpw or cp_unhit) else f"cover properties hit: {cp_pct}%, need {th['cover_properties_pct']}%"),
        "cover_properties_unhit": chk(cp_unhit, [], not cp_unhit and bool(code), code_why),
        "line_pct": chk(line_v, th["line_pct"], line is not None and line >= th["line_pct"], line_why),
        "toggle_pct": chk(tog_v, th["toggle_pct"], tog is not None and tog >= th["toggle_pct"], tog_why),
        "waivers_without_reason": chk(len(bad_waive), 0, not bad_waive, "every waiver needs a non-empty `reason`"),
        "mutation_score_pct": chk(mut["score_pct"] if mut else NOT_MEASURED, th["mutation_score_pct"], mut_ok,
                                  mutation_why(mut, mut_reason, need)),
    }
    gj = json.loads(gates.read_text()) if gates and gates.exists() else None
    v3.update(cdc_checks(design, gj, cdc_inject_file))           # brief 16: only for a design with a crossing
    # 05n: say on every check whose threshold the plan set below the floor that the floor applies
    for key, names in (("seeds_min", ("seeds_run",)), ("functional_bins_pct", ("functional_bins_pct", "functional_bins_unhit")),
                       ("cover_properties_pct", ("cover_properties_pct", "cover_properties_unhit")),
                       ("line_pct", ("line_pct",)), ("toggle_pct", ("toggle_pct",)),
                       ("mutation_score_pct", ("mutation_score_pct",))):
        if key in below:
            for nm in names:
                v3[nm]["floor_note"] = below[key]
                if not v3[nm]["pass"]:
                    v3[nm]["why"] = f"{v3[nm].get('why') or 'below the threshold'} [{below[key]}]"
    if not seeds:       # coverage is read from the seeds' own files: nothing to evaluate without them
        for k in ("functional_bins_pct", "functional_bins_unhit", "cover_properties_pct", "cover_properties_unhit",
                  "line_pct", "toggle_pct"):
            v3[k] = ne(v3[k]["threshold"])
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
    out["stages"]["SIGNOFF"] = {"checks": {"every_method_has_passing_evidence": chk(not_pass, [], not not_pass and bool(table),
                                                                                 "no proof entries: declare a proof list per requirement in the testplan" if not table else None)}}
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
    ap.add_argument("--evidence", help="05l: build/verif/v3_evidence.json, the flow's own V3 steps (why a number is not measured)")
    ap.add_argument("--cdc-inject", help="brief 16: build/verif/cdc_inject.json from flow/cdc_inject_run.py (needed by a design with a crossing)")
    ap.add_argument("--fsm-coverage", help="brief 24 (off unless given): the evidence JSON of flow/fsm_coverage.py; adds the V2 check "
                    "fsm_state_transition_coverage")
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
                       rel(a.gates) if a.gates else None, rel(a.evidence) if a.evidence else None,
                       rel(a.cdc_inject) if a.cdc_inject else None, rel(a.fsm_coverage) if a.fsm_coverage else None)
    except (PlanError, OSError, KeyError, TypeError, ValueError, AttributeError, SyntaxError) as e:
        # whatever else a gate input throws, the answer is a failed gate with the message, not a traceback
        msg = e.args[0] if isinstance(e, PlanError) and e.args else f"{type(e).__name__}: {e}"
        rep = finish({"design": Path(a.design).name, "stages": {"V0": {"checks": {
            "gate_inputs_readable": chk(str(msg)[:600], "readable", False)}}}})
    for s, st in rep["stages"].items():
        print(f"{s}: {'PASS' if st.get('pass') else 'FAIL'}")
        for n, c in st["checks"].items():
            print(f"    {'ok ' if c['pass'] else 'BAD'} {n}: {c['value']}  (threshold {c['threshold']})")
            if c.get("why"):
                print(f"        why: {c['why']}")
    for r in rep.get("traceability") or []:
        print(f"    trace {r['requirement']:8} {r['method']:10} {r['artefact']:55} {r['result']:8} {r['detail']}")
    for w in rep.get("warnings") or []:
        print(f"WARNING: {w}")
    print(f"reached: {rep['reached']}  first failed: {rep['first_failed']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2, default=str) + "\n")
    ok = (rep["first_failed"] is None and (not a.require_hw or rep["stages"].get("V-HW", {}).get("pass"))
          and (not a.require_signoff or rep["stages"].get("SIGNOFF", {}).get("pass")))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


# ---- the tests role's self-check (07a2 fix 7) --------------------------------------------------------------
def static_check(design: Path, level: str = "V3") -> list[str]:
    """The convention checks of V0/V1 (the gate code itself, no simulation) plus the V2/V3 conventions that can be read from
    the files: a bench test with "random" in its name, planned functional bins and planned cover properties. Returns one
    plain-words line per problem (empty list: the tests role may hand over). The harness runs it inside the tests role's turn
    so a convention miss is repaired there and does not cost a stage-2 visit (softmax run 2, c11, tiny CNN)."""
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        rep = evaluate(design, tmp / "runs", [], tmp / "formal", None, None)
    out: list[str] = []
    for st in ("V0", "V1"):
        for name, c in ((rep["stages"].get(st) or {}).get("checks") or {}).items():
            if c.get("pass"):
                continue
            val = c.get("value")
            if isinstance(val, list):
                val = f"[{len(val)}] " + ", ".join(str(x) for x in val[:40])
            out.append(f"{st} {name}: {c.get('why') or str(val)[:800]}")
    if out or (level not in ("V2", "V3")):
        return out
    plan_path = design / "verif" / "testplan.yaml"
    try:
        plan, _spec = load_inputs(design, plan_path)
        names = bench_tests(plan_file(design, plan["bench"]["dir"]), plan["bench"]["modules"])
    except (PlanError, OSError, KeyError):
        return out
    if not any("random" in n.lower() for n in names):
        out.append("V2 constrained_random_test_ran: no bench test has 'random' in its name: name the constrained-random test so "
                   "(for example test_random_traffic), list it in a requirement's `tests:` and run it")
    if level == "V3":
        reqs = plan["requirements"]
        if not {b for r in reqs for b in r.get("bins", [])}:
            out.append("V3 functional_bins_pct: no functional bins planned: " + HOW_FUNC_COV)
        if not {c for r in reqs for c in r.get("cover_props", [])}:
            out.append("V3 cover_properties_pct: no cover properties planned: name them in `cover_props:` of the requirements "
                       "(C_*, declared with V_COVER in verif/checkers, and reached by a test)")
    return out
