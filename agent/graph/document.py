"""Brief 68 part C: the agent documents its own work (the DOC step at the end of a run, and its DOC gate).

At the end of a run the graph's ``document`` node:

1. drafts ``handover.yaml`` from the run's records with code (:func:`draft`): identity, target, clocks (from the XDC),
   files, commands, evidence (from ``summary.json``, ``verif_gates.json``, ``mutation.json``, ``gates.json``, the
   bring-up record), measurements as record + field (never a value), the gates of every stage, and the gaps the run
   requires (every stage that did not pass, every evidence entry that did not pass, every requirement without passing
   evidence, every quantity not measured);
2. asks the Designer (record key ``rtl``) for the prose (:data:`DOC_SYSTEM`): title, summary, scope, interfaces,
   resets, parameter ranges and notes, extra gaps, next steps, open questions. The reply is merged by
   :func:`merge`: fields the code owns are kept from the draft whatever the reply says, and no required gap can be
   removed or reworded;
3. fills values and hashes from the records (``flow.handover.fill``), renders README.md and AGENT.md
   (``flow.handover.write``), and runs the DOC gate (:func:`doc_gate`: ``flow.handover.problems`` returns nothing).
   A failing gate goes back to the Designer with the problems, at most :data:`DOC_PASSES` passes.

The run is signed off only when stage 9 passed and the DOC gate passed (``summary.json`` ``signed_off``).

Build numbers from a Vivado release other than the one the flow pins (``flow.handover.VIVADO``) are not published:
the evidence entry is ``partial``, the timing, resource and power numbers are withdrawn and a gap says why.

``python -m agent document <run-dir>`` runs the same step on a finished run (``--replay`` replays recorded replies).
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from flow import handover as H

ROOT = H.ROOT
LLM = Callable[[str, str], str]
DOC_PASSES = 3
STAGE_NAMES = ("clarify", "board-and-device-planning", "rtl-design-creation", "constraints", "synthesis",
               "implementation", "timing-closure", "power-closure", "drc-closure", "configuration-and-debug")
#: handover fields the Designer writes; every other field is the code's (kept from the draft whatever the reply says)
MODEL_KEYS = ("title", "summary", "scope_not", "resets", "interfaces", "next_steps", "open_questions")
#: design files listed in the handover, with what each is (globs relative to the design directory)
FILE_KINDS = (("spec.md", "the request the run started from"),
              ("spec.yaml", "the signed-off specification written by the Clarifier"),
              ("ARCHITECTURE.md", "the architecture note approved before any RTL"),
              ("architecture.yaml", "the machine-checked architecture: blocks, clocks, predicted resources"),
              ("rtl/*", "RTL written by the Designer"),
              ("design.xdc", "pin, I/O standard and timing constraints"),
              ("build.yaml", "the build description read by the flow"),
              ("model.py", "the Modeller's reference model of the visible behaviour"),
              ("tests/*.py", "the Verifier's cocotb benches and pytest entries"),
              ("verif/*.yaml", "the test plan and mutant list read by the verification gates"),
              ("verif/checkers/*", "bound assertion and cover checkers"),
              ("verif/formal/*", "formal property jobs"),
              ("probes.yaml", "the ILA probe list of the debug build"),
              ("hw_checks.py", "the ILA capture checks for bring-up"),
              ("BRINGUP.md", "the bring-up procedure for a tester"))

DOC_SYSTEM = """You are the Designer. The run has ended: write the documentation for the next engineer who picks up this design.
You are given handover.yaml as drafted by the flow. The facts in it (target, clocks, files, commands, evidence, measurements, the
gates of every stage, history and the gaps already listed) were filled from the run's records by code. They are not yours to change:
the flow keeps its own copy of them whatever you write. You write the prose fields:
- title: a short name for the design.
- summary: what the design does, for an engineer who has never seen it (at least two sentences), and how far the run got.
- scope_not: what the design is not, or does not do.
- resets: a list of {name, active: high or low, note}; interfaces: a list of {name, type, note} with an optional doc (a
  datasheet path in the repo or a URL), one entry per port group of the top level. Copy names from spec.yaml.
- parameters: a list of {name, value, legal, note}: keep each name and value; write the legal range and a note.
- Where spec.yaml, the interview answers and ARCHITECTURE.md disagree with the RTL or design.xdc (pins, widths, reset
  style, reset values, periods, unmapped accesses, priorities), the RTL and XDC are what was built: state what they do and
  name the file, and add a gap saying the spec disagrees. Do not leave as an open question what the RTL answers.
- gaps: keep every gap listed. Add a gap (about: a short key) for each behaviour a user could guess wrong that spec.yaml or the
  RTL settles and the draft does not state: reset values, unmapped or reserved register accesses, read side effects, partial
  writes, same-cycle priorities, latency. Also add any assumption the run made.
- next_steps: what the next engineer should do first, in order (the first one from the earliest gap). open_questions: what is
  still undecided.
Rules: write no number that is not in the draft, spec.yaml or a cited record (every number is checked against them); no
placeholder text; plain, measured words; never say a check passed unless its evidence entry says pass; say "the Designer",
"the Modeller", "the Verifier" and "the Clarifier" for the roles. Reply with the complete handover.yaml in one ```yaml block and
nothing else."""


# --- facts from the records ---------------------------------------------------------------------------------------

def _json(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def stage_results(gates_last: dict | None) -> dict[str, str]:
    """{stage name: pass | fail | not-run} for every stage, from ``summary.json``'s ``gates_last``."""
    g = gates_last or {}
    return {s: ("not-run" if s not in g else ("pass" if g[s] else "fail")) for s in STAGE_NAMES}


def build_release(design: Path, variant: str = "base") -> str | None:
    """The Vivado release of the run's last build of ``variant`` (``build/<variant>/run.json``), or None."""
    r = _json(design / "build" / variant / "run.json") or {}
    return r.get("vivado_version")


def _clocks(design: Path) -> list[dict]:
    x = design / "design.xdc"
    if not x.is_file():
        return []
    out = []
    for m in re.finditer(r"create_clock\b[^\n]*?-period\s+([\d.]+)[^\n]*?get_ports\s+\{?\s*(\w+)", x.read_text()):
        out.append({"name": m.group(2), "mhz": round(1000.0 / float(m.group(1)), 6), "source": H.rel(x)})
    return out


def _files(design: Path) -> list[dict]:
    seen, out = set(), []
    for pat, what in FILE_KINDS:
        for p in sorted(design.glob(pat)):
            if p.is_file() and p not in seen and "__pycache__" not in p.parts and p.suffix not in (".pyc",):
                seen.add(p)
                out.append({"path": H.rel(p), "what": what})
    return out


def _failed_review_pages(design: Path, res: dict) -> list[dict]:
    return [{"path": H.rel(p), "what": f"the review page of stage {s}: its exit gates and their failures at the last visit"}
            for s, r in res.items() if r == "fail" and (p := review_page(design, s)) is not None]


def review_page(design: Path, stage: str) -> Path | None:
    p = design / "build" / "review" / f"{STAGE_NAMES.index(stage):02d}_{stage}.html"
    return p if p.is_file() else None


def failing_gates(design: Path, stage: str, limit: int = 400) -> str:
    """The exit-gate failures of a stage's last visit, as its review page (build/review/) shows them, in plain text."""
    p = review_page(design, stage)
    if p is None:
        return ""
    import html as _html
    t = re.sub(r"<style.*?</style>", " ", p.read_text(errors="replace"), flags=re.S)
    t = " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", t)).split())
    i, j = t.find("Exit gates gate result detail"), t.find("Inputs and outputs")
    body = t[i + len("Exit gates gate result detail"):j].strip() if i >= 0 else ""
    return (body[:limit] + (" ...") if len(body) > limit else body)


def _spec(design: Path) -> dict:
    try:
        return yaml.safe_load((design / "spec.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _date(run_id: str) -> str:
    m = re.match(r"(\d{4})(\d{2})(\d{2})-", run_id)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else _dt.date.today().isoformat()


def draft(design: Path, run_dir: Path, *, run_id: str, board: str, gates_last: dict | None, stop: str | None,
          verif_level: str | None = None, resumed_from: str | None = None,
          carried: list[str] | None = None) -> tuple[dict, list[str]]:
    """(the draft handover, the ``about`` keys of the gaps the run requires). Every fact comes from a record.
    ``verif_level`` None: the run's ``config.json``, else V3 (the methodology)."""
    design, run_dir = design.resolve(), run_dir.resolve()
    verif_level = verif_level or (_json(run_dir / "config.json") or {}).get("verif_level") or "V3"
    rd = H.rel(design)
    spec = _spec(design)
    bld = yaml.safe_load((design / "build.yaml").read_text()) if (design / "build.yaml").is_file() else {}
    res = stage_results(gates_last)
    for s in carried or ():                     # resume: stages before the entry that passed in the handover, inputs unchanged
        if res.get(s) == "not-run":
            res[s] = "pass"
    summ = run_dir / "summary.json"
    ev, ms, gaps = [], [], []

    def gap(about: str, text: str) -> None:
        if about not in {g["about"] for g in gaps}:
            gaps.append({"about": about, "text": text})

    def e(activity: str, result: str, what: str, rec: Path, **kw) -> str:
        i = f"E{len(ev) + 1}"
        ev.append({"id": i, "activity": activity, "result": result, "what": what, "record": H.rel(rec), **kw})
        return i

    def m(what: str, category: str, unit: str, rec: Path, field: str, cond: str, key: str | None = None) -> None:
        ms.append({"id": f"M{len(ms) + 1}", "what": what, "category": category, **({"key": key} if key else {}),
                   "unit": unit, "record": H.rel(rec), "field": field, "conditions": cond})

    if summ.is_file():
        e("review", res["clarify"], ("spec.yaml carried from the handover of the earlier run (stage clarify passed there and "
          "its inputs had not changed)") if "clarify" in (carried or ()) else ("spec.yaml was signed off after the "
          "interview; the questions asked, answered and defaulted are in the run summary"), summ)
    vg_p = design / "build" / "verif" / "verif_gates.json"
    vg = _json(vg_p)
    if vg:
        reached = vg.get("reached")
        ok = bool(reached) and reached >= verif_level
        e("simulation", "pass" if ok else ("partial" if reached else "fail"),
          f"verification stages (flow/verif_gates.py) against the Modeller's reference model; reached {reached or 'none'}, "
          f"the run asked for {verif_level}", vg_p)
        open_rows: dict[str, list[str]] = {}
        for row in vg.get("traceability") or []:
            if row.get("result") != "pass":
                det = str(row.get("detail") or "")
                res_r = "not run (the stage that makes this evidence did not run)" if det.endswith("= None") else row.get("result")
                open_rows.setdefault(row["requirement"], []).append(
                    f"{row.get('method')} ({row.get('artefact')}) is {res_r}: {det[:200]}")
        for req, why in open_rows.items():
            gap(req, f"{req} has no passing evidence for every proof method: " + "; ".join(why))
    mu_p = design / "build" / "verif" / "mutation.json"
    mu = _json(mu_p)
    if mu and mu.get("evaluated"):
        e("faults", "pass" if not mu.get("survived") and not mu.get("timed_out") else "partial",
          "generated mutants of the RTL run against the Verifier's benches; each must make a test fail", mu_p)
        m("mutation score of the Verifier's benches", "verification", "%", mu_p, "score_pct",
          "generated mutants sampled from the RTL, run in the simulation sandbox")
    rel_now = H.VIVADO
    for variant, label in (("base", "base build"), ("ila", "debug build with the ILA")):
        gp = design / "build" / variant / "gates.json"
        g = _json(gp)
        if not g:
            continue
        rel_b = build_release(design, variant)
        current = rel_b == rel_now
        result = ("pass" if g.get("pass") else "fail") if current else "partial"
        ran = [k for k, v in (g.get("stages") or {}).items() if (v or {}).get("ran")]
        i = e("build", result, f"Vivado {label}; flow stages that ran: " + (", ".join(ran) or "none")
              + ("" if current else "; built with an earlier Vivado release than the pinned one, so the result is not current"), gp)
        if not current:
            gap(i, f"the {label} was made with an earlier Vivado release than {rel_now}: rebuild it before relying on its "
                "gates or numbers")
        if variant == "base" and current:
            if (g.get("timing") or {}).get("wns_ns") is not None:
                m("worst setup slack after routing", "timing", "ns", gp, "timing.wns_ns",
                  "post-route, the constrained clock of design.xdc", key="wns")
                m("worst hold slack after routing", "timing", "ns", gp, "timing.whs_ns", "post-route", key="whs")
            for k, what in (("lut", "slice LUTs"), ("ff", "flip-flops"), ("bram_tile", "block RAM tiles"), ("dsp", "DSP slices")):
                if (g.get("utilization") or {}).get(k) is not None:
                    m(f"{what} used", "resources", "", gp, f"utilization.{k}", "post-route utilization", key=k)
            if (g.get("power") or {}).get("total_w") is not None:
                m("total on-chip power, vectorless estimate", "power", "W", gp, "power.total_w",
                  "report_power, vectorless (no switching activity file), default environment", key="power")
    br_p = design / "build" / "bringup" / f"{design.name}_bringup.json"
    br = _json(br_p)
    if br is not None:
        e("board", "pass" if br.get("pass") is True else "fail", "bring-up on the board: UART tests against the reference "
          "model and the ILA captures", br_p, conditions="operating conditions (die temperature and supply rails) were not "
          "read by this run's bring-up")
    for x in ev:
        if x["result"] != "pass":
            gap(x["id"], f"{x['activity']} evidence is {x['result']}: {x['what']}")
    for s, r in res.items():
        if r == "fail":
            why = failing_gates(design, s)
            gap(s, f"stage {s} did not pass its gates in this run" + (f"; at its last visit: {why}" if why else
                "; the run summary and the review pages under build/review/ give the failures"))
        elif r == "not-run":
            why = ("the run resumed after this stage; its inputs had not changed since the handover"
                   if resumed_from and STAGE_NAMES.index(s) < _first_visited(gates_last) else
                   "the run stopped before this stage" + (f" ({stop})" if stop else ""))
            gap(s, f"stage {s} was not run: {why}")
    cats = {x["category"] for x in ms}
    for c, why in (("resources", "no current Vivado build of this design has been recorded"),
                   ("timing", "no current Vivado build of this design has been recorded"),
                   ("power", "no current Vivado build of this design has been recorded"),
                   ("latency", "the run measured no latency; the spec's latency promise is checked only by the benches"),
                   ("throughput", "the run measured no throughput")):
        if c not in cats:
            gap(c, f"{c} not measured: {why}")
    if summ.is_file():
        s = _json(summ) or {}
        if isinstance(s.get("cost_usd"), (int, float)) and s.get("harness") == "deepagents":   # plan runs report no USD
            m("model cost of the run, provider-reported", "cost", "USD", summ, "cost_usd",
              "every role and the interview oracle, as the run summary records it")
    required = [g["about"] for g in gaps]
    passed = [s for s, r in res.items() if r == "pass"]
    stage = ("signed-off" if all(r == "pass" for r in res.values()) else
             "built" if res["implementation"] == "pass" else
             "simulated" if res["rtl-design-creation"] == "pass" else
             "rtl" if list(design.glob("rtl/*")) else "spec")
    evv = {build_release(design, v) for v in ("base", "ila") if (design / "build" / v / "run.json").is_file()}
    h = {"schema": "fda-handover/1", "id": design.name, "title": "WRITE", "kind": "agent-run", "produced_by": "agent",
         "summary": "WRITE", "scope_not": ["WRITE"],
         "target": {"part": bld.get("part") or spec.get("part") or "unknown", "board": board, "tool": f"Vivado {rel_now}",
                    "top": bld.get("top") or spec.get("top") or "unknown"},
         "clocks": _clocks(design), "resets": [], "interfaces": [],
         "parameters": [{"name": str(k), "value": v, "legal": "WRITE", "note": "WRITE"}
                        for k, v in (spec.get("parameters") or {}).items()] if isinstance(spec.get("parameters"), dict) else [],
         "files": _files(design) + _failed_review_pages(design, res),
         "commands": [
             {"what": "what changed since this handover (stale records, changed files, tool and knowledge-bank pins)",
              "cmd": f"python -m flow.handover fresh {rd}", "heavy": False, "minutes": None},
             {"what": "pick the work up again from the earliest stage the change or the staleness needs",
              "cmd": f"python -m agent resume {rd} \"<change request>\"", "heavy": True, "minutes": None,
              "needs": "a model (see docs/agent.md); Vivado for any stage from synthesis on"},
             *([{"what": "run the Verifier's simulation tests",
                 "cmd": f"python -m pytest -q {rd}/tests/test_{design.name}_rtl.py", "heavy": False, "minutes": None,
                 "needs": "Icarus Verilog and cocotb, or the simulation container"}]
               if (design / "tests" / f"test_{design.name}_rtl.py").is_file() else []),
             {"what": "rebuild the bitstream with the flow", "cmd": f"flow/run_vivado.sh {rd} base", "heavy": True,
              "minutes": None, "needs": f"Vivado {rel_now} and a heavy slot"}],
         "evidence": ev, "measurements": ms, "gaps": gaps, "next_steps": ["WRITE"], "open_questions": [],
         "history": [{"date": _date(run_id), "brief": "agent run",
                      "note": (f"resumed from the handover of {resumed_from}; " if resumed_from else "")
                      + "produced by the agent graph; stages that passed: " + (", ".join(passed) or "none")
                      + (f"; carried from the handover: {', '.join(carried)}" if carried else "")}],
         "agent_run": {"run_id": run_id, "record": H.rel(summ if summ.is_file() else run_dir / "config.json")},
         "state": {"stage": stage, "gates": res, "vivado": rel_now, "kb_pin": None, "build_id": None,
                   "evidence_vivado": ("none" if not evv else "current" if evv == {rel_now} else "earlier")}}
    return h, required


def _first_visited(gates_last: dict | None) -> int:
    g = gates_last or {}
    return min((STAGE_NAMES.index(s) for s in g if s in STAGE_NAMES), default=0)


# --- the Designer's prose -----------------------------------------------------------------------------------------

def user_prompt(design: Path, h: dict, problems: list[str]) -> str:
    spec = (design / "spec.yaml").read_text(errors="replace")[:12000] if (design / "spec.yaml").is_file() else "(none)"
    arch = (design / "ARCHITECTURE.md").read_text(errors="replace")[:4000] if (design / "ARCHITECTURE.md").is_file() else ""
    out = f"DRAFT handover.yaml (fields marked WRITE are yours):\n```yaml\n{H.dump(h)}```\n\nspec.yaml:\n{spec}\n"
    if arch:
        out += f"\nARCHITECTURE.md (first part):\n{arch}\n"
    src, budget = "", 30000
    for p in [design / "design.xdc", *sorted((design / "rtl").glob("*"))]:
        if p.is_file() and budget > 0:
            body = p.read_text(errors="replace")[:budget]
            budget -= len(body)
            src += f"\n--- {p.relative_to(design)} ---\n{body}\n"
    if src:
        out += "\nWHAT WAS BUILT (design.xdc and the RTL):" + src
    if problems:
        out += ("\nThe documentation check (flow/handover.py) found these problems in your last reply; fix them and reply with "
                "the whole file again:\n" + "\n".join(f"- {p[:400]}" for p in problems[:40]) + "\n")
    return out


def parse_reply(text: str) -> dict:
    m = re.search(r"```ya?ml\s*\n(.*?)```", text, re.S)
    body = m.group(1) if m else text
    y = yaml.safe_load(body)
    if not isinstance(y, dict):
        raise ValueError("the reply is not a YAML mapping")
    return y


def merge(draft_h: dict, reply: dict, required: list[str]) -> dict:
    """The draft with the Designer's prose fields. Code-owned fields come from the draft; parameter names and values come
    from the draft; required gaps keep the draft's text; the Designer may only add gaps with a new ``about``."""
    h = copy.deepcopy(draft_h)
    for k in MODEL_KEYS:
        if k in reply and reply[k] is not None:
            h[k] = reply[k]
    if isinstance(reply.get("target"), dict) and isinstance(reply["target"].get("note"), str):
        h["target"]["note"] = reply["target"]["note"]
    rp = {str(p.get("name")): p for p in reply.get("parameters") or [] if isinstance(p, dict)}
    for p in h["parameters"]:
        q = rp.get(str(p["name"])) or {}
        for k in ("legal", "note"):
            if isinstance(q.get(k), str) and q[k].strip():
                p[k] = q[k]
    have = {g["about"] for g in h["gaps"]}
    for g in reply.get("gaps") or []:
        if isinstance(g, dict) and isinstance(g.get("about"), str) and g["about"] not in have and isinstance(g.get("text"), str):
            h["gaps"].append({"about": g["about"], "text": g["text"]})
            have.add(g["about"])
    missing = [r for r in required if r not in have]
    if missing:
        raise ValueError(f"required gaps lost: {missing}")
    return h


def recheck(ddir: Path) -> list[str]:
    """For doccheck: an agent-produced handover's code-owned facts, re-derived from the run's records now and compared
    (evidence, measurements, gates, stage, clocks, files and the required gaps). Hand edits that drop a required gap, or
    turn a failed gate or evidence entry into a pass, fail here."""
    try:
        h = H.load(ddir)
    except (OSError, yaml.YAMLError) as ex:
        return [f"handover.yaml: {ex}"]
    if h.get("produced_by") != "agent":
        return ["produced_by: a handover with agent_run must say produced_by: agent"] if h.get("agent_run") else []
    if not isinstance(h.get("agent_run"), dict) or not isinstance(h.get("target"), dict):
        return ["agent_run and target must be mappings"]
    run_dir = H.agent_run_dir(h, ddir)
    if run_dir is None:
        return ["agent_run: the design directory is not inside the directory of its agent_run record"]
    s = _json(ROOT / h["agent_run"]["record"]) or {}
    if "gates_last" not in s:
        return [f"agent_run: {h['agent_run']['record']} has no gates_last (not a run summary)"]
    d, required = draft(ddir, run_dir, run_id=h["agent_run"].get("run_id"), board=h["target"].get("board"),
                        gates_last=s["gates_last"], stop=s.get("stop"), resumed_from=s.get("resumed_from"),
                        carried=s.get("gates_carried"))
    errs = []
    key = {"evidence": ("id", "activity", "result", "what", "record", "conditions"),
           "measurements": ("id", "what", "category", "unit", "record", "field", "conditions"),
           "clocks": ("name", "mhz", "source")}
    for k, f in key.items():
        if [tuple(x.get(i) for i in f) for x in h.get(k) or []] != [tuple(x.get(i) for i in f) for x in d[k]]:
            errs.append(f"{k}: not what the run's records give now (re-run the DOC step: python -m agent document <run-dir>)")
    for k in ("gates", "stage", "evidence_vivado"):
        if (h.get("state") or {}).get(k) != d["state"][k]:
            errs.append(f"state.{k}: {(h.get('state') or {}).get(k)!r} is not the run's {d['state'][k]!r}")
    if sorted(f["path"] for f in h.get("files") or []) != sorted(f["path"] for f in d["files"]):
        errs.append("files: not the design's files as the run left them")
    for k in ("part", "top", "tool", "board"):
        if (h.get("target") or {}).get(k) != d["target"][k]:
            errs.append(f"target.{k}: not the run's")
    if h.get("agent_run", {}).get("record") != d["agent_run"]["record"] or h.get("history", [None])[:1] != d["history"]:
        errs.append("agent_run or the first history entry is not the run's")
    texts = {g.get("about"): g.get("text") for g in h.get("gaps") or [] if isinstance(g, dict)}
    for g in d["gaps"]:
        if g["about"] not in texts:
            errs.append(f"gap about {g['about']!r} is required by the run's records and missing")
        elif texts[g["about"]] != g["text"]:
            errs.append(f"gap about {g['about']!r}: its text is not the run's (a required gap is never reworded)")
    return errs + overclaims(h)


SUCCESS = re.compile(r"\b((the |this )?(design|run|project|work) (is|was|has been) signed[ -]off|all (the )?(stages|gates|checks|tests) (passed|pass)|fully verified|timing (is )?(met|closed)|"
                     r"closes timing|meets timing|passed on the board|works on the board|production[- ]ready)\b", re.I)


def overclaims(h: dict) -> list[str]:
    """Prose that claims a success the gates do not show: any success phrase while a gate or evidence entry is not a pass
    (a negated phrase such as "not signed off" is allowed)."""
    if all(r == "pass" for r in (h.get("state") or {}).get("gates", {}).values()) and \
            all(e.get("result") == "pass" for e in h.get("evidence") or []):
        return []
    out = []
    for path, s in H._strings({k: h.get(k) for k in ("title", "summary", "scope_not", "next_steps", "open_questions",
                                                     "interfaces", "resets", "target")}):
        for m in SUCCESS.finditer(s):
            before = s[max(0, m.start() - 24):m.start()].lower()
            if not re.search(r"\b(not|no|never|nor|without|before|until|un)\b|n't", before):
                out.append(f"{path}: claims {m.group(0)!r} while a gate or evidence entry did not pass")
    return out


def unwritten(h: dict) -> list[str]:
    """Fields still holding the draft's WRITE marker."""
    out = []
    for path, s in H._strings(h):
        if s.strip() == "WRITE":
            out.append(f"{path}: not written (still WRITE)")
    return out


def doc_gate(design: Path, required: list[str]) -> list[str]:
    """The DOC gate: flow.handover's problems and stale claims, every required gap present, nothing left unwritten."""
    try:
        h = H.load(design)
    except (OSError, yaml.YAMLError) as ex:
        return [f"handover.yaml: {ex}"]
    errs, stale = H.problems(design, h)
    have = {g.get("about") for g in h.get("gaps") or []}
    errs += [f"gap about {r!r} is required (a stage, evidence entry, requirement or quantity without a pass) and missing"
             for r in required if r not in have]
    return errs + stale + unwritten(h) + overclaims(h)


def write_handover(design: Path, h: dict) -> None:
    """Validate, fill from the records, write handover.yaml and both renderings. Raises ValueError with the reasons."""
    bad = H._validate(h)
    if bad:
        raise ValueError("; ".join(bad))
    h = H.fill(h, design, build_id=False)
    try:
        from flow import manifest
        if (design / "build.yaml").is_file():
            h["state"]["build_id"] = manifest.show(design, "base", H.VIVADO, 2)["build_id"]
    except (Exception, SystemExit):                # noqa: BLE001 (no build ID when the sources do not prepare)
        h["state"]["build_id"] = None
    (design / "handover.yaml").write_text(H.dump(h))
    H.write(design, build_id=False)                 # keeps only marked prose blocks of an existing README


def document(design: Path, run_dir: Path, llm: LLM, *, run_id: str, board: str, gates_last: dict | None,
             stop: str | None, verif_level: str | None = None, resumed_from: str | None = None,
             carried: list[str] | None = None, passes: int = DOC_PASSES, log: Path | None = None) -> dict:
    """The DOC step: draft, the Designer's prose, fill, render, DOC gate; up to ``passes`` Designer passes."""
    h0, required = draft(design, run_dir, run_id=run_id, board=board, gates_last=gates_last, stop=stop,
                         verif_level=verif_level, resumed_from=resumed_from, carried=carried)
    problems: list[str] = []
    for n in range(1, passes + 1):
        user = user_prompt(design, h0 if n == 1 else last, problems)
        text = llm(DOC_SYSTEM, user)
        if log is not None:
            with log.open("a") as f:
                f.write(json.dumps({"pass": n, "user_chars": len(user), "reply": text}) + "\n")
        try:
            last = merge(h0, parse_reply(text), required)
            write_handover(design, last)
            problems = doc_gate(design, required)
        except (ValueError, yaml.YAMLError, SystemExit, KeyError, TypeError, AttributeError) as ex:
            last = h0 if n == 1 else last
            problems = [f"the reply could not be used: {ex}"[:600]]
        if not problems:
            return {"ok": True, "passes": n, "problems": [], "required_gaps": required,
                    "agent_tokens": H.agent_tokens(design)}
    return {"ok": False, "passes": passes, "problems": problems, "required_gaps": required}


# --- model clients ------------------------------------------------------------------------------------------------

def replay_llm(path: Path) -> LLM:
    """Replies recorded in a ``doc_calls.jsonl`` (one per pass), returned in order: no model call."""
    replies = [json.loads(l)["reply"] for l in path.read_text().splitlines() if l.strip()]

    def llm(system: str, user: str) -> str:
        if not replies:
            raise ValueError("replay: more DOC passes than were recorded")
        return replies.pop(0)
    return llm


def designer_llm(rt) -> LLM:
    """The Designer's model for the DOC step: a headless Claude Code call when the Designer runs on Claude Code (the Max
    plan), else one OpenRouter call metered like any role turn."""
    rm = rt.cfg.role_models().get("rtl") or {}
    if rm.get("harness") == "claude_code":
        from agent.graph.spectest import cc_llm
        return cc_llm(rm.get("model") or rt.cfg.cc_model, rm.get("effort"), rt.run_dir / "claude_code_calls.jsonl", "doc")
    from agent.graph.run import role_client

    def llm(system: str, user: str) -> str:
        reply = role_client(rt, rm.get("model") or rt.cfg.model)([{"role": "system", "content": system},
                                                                 {"role": "user", "content": user}])
        rt.meter.add(reply)
        return reply.text
    return llm
