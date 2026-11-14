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
              ("spec.yaml", "the specification the Clarifier wrote, accepted automatically by a model (no human review)"),
              ("ARCHITECTURE.md", "the architecture note, accepted automatically before any RTL (no human review)"),
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
- Answer from the files before you ask: the build reads the sources listed under SOURCES THE BUILD READS, shared shell files
  included (shown below as far as they fit). Never write that a source was not found or not reviewed when it is shown, and do
  not put in open_questions what the RTL, the XDC, those sources or the spec settle. When the spec promises a latency, a
  rate or a width, count it from the RTL (pipeline stages, counter periods), state the count and the file, and say so when it
  differs from the promise. State any masking, gating or priority between control signals that a user could guess wrong.
  State the rates the spec gives for the parameters (its timing section) in the parameter notes.
- If cover properties are unhit while functional bins are hit, the draft says the two disagree: say so too, and put "compare
  the cover results with the functional coverage" before any new stimulus in next_steps.
- The first next_steps entry addresses the earliest stage that failed or did not reach its level (for example verification,
  before any rebuild). If a build was made under an earlier Vivado release, one later step re-measures it with python -m agent
  resume when the flow reaches the build again; publish no number from that build and never name the earlier release.
- Approval: the draft says the specification and architecture were approved automatically by a model with no human review. Never
  write "signed off" or "approved" without saying that. If the draft says no debug build was attempted or recorded, do not write
  that it failed or did not complete.
- For a seven-segment or other multi-pin output, check the RTL's bit order against design.xdc (which pin each bit drives). If
  they disagree, or the files cannot settle it, say so as a gap or an open question with the file and line.
- gaps: keep every gap listed. Add a gap (about: a short key) for each behaviour a user could guess wrong that spec.yaml or the
  RTL settles and the draft does not state: reset values, unmapped or reserved register accesses, read side effects, partial
  writes, same-cycle priorities, latency. Also add any assumption the run made.
- next_steps: what the next engineer should do first, in order (the first one from the earliest gap). open_questions: what is
  still undecided.
Say each fact once, in the field where it belongs (a reset in resets, a pin or port in interfaces, a behaviour a user could guess
wrong in one gap) and do not repeat it in the summary or in another note; a note is one or two sentences. The summary is a short
paragraph.
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


#: stage name -> the flat ``gates`` of build/base/gates.json that stage's exit check reads (agent/graph/stages.py); stages
#: that read per-flow-stage structure (constraints, synthesis, implementation) are not listed
STAGE_BASE_GATES = {"timing-closure": ("setup", "hold", "pulse_width"), "power-closure": ("power_junction_ok",),
                    "drc-closure": ("post_synth_drc_clean", "drc_clean", "cdc_no_critical", "methodology_no_critical")}
RECON = "Build records:"          # a gap that quotes a gate detail the records contradict carries this reconciliation


def records_verdict(design: Path, stage: str) -> bool | None:
    """True when the base build's record shows every gate this stage reads passing, False when one fails, None when the
    record does not say (no record, or a stage that reads per-flow-stage structure)."""
    keys = STAGE_BASE_GATES.get(stage)
    g = (_json(design / "build" / "base" / "gates.json") or {}).get("gates")
    if not keys or not isinstance(g, dict) or not all(k in g for k in keys):
        return None
    return all(bool(g[k]) for k in keys)


def build_state(design: Path, variant: str) -> dict:
    """What a variant's records say: whether gates.json exists, an error stub (and its message), the flow stages that ran,
    whether run.json exists, and the pass and bitstream flags."""
    g = _json(design / "build" / variant / "gates.json")
    return {"present": isinstance(g, dict), "error": (g or {}).get("error") if isinstance(g, dict) else None,
            "ran": [k for k, v in ((g or {}).get("stages") or {}).items() if (v or {}).get("ran")],
            "run_json": (design / "build" / variant / "run.json").is_file(),
            "pass": (g or {}).get("pass") if isinstance(g, dict) else None,
            "bitstream": ((g or {}).get("gates") or {}).get("bitstream_present") if isinstance(g, dict) else None}


def reconcile(design: Path, stage: str, why: str) -> str:
    """The build records set beside a failing gate's detail (68F). Where the detail says a flow stage "did not run" and the
    records contradict it (or place it in another build), the reconciliation says what the records show; else ''."""
    if "did not run" not in why:
        return ""
    base, ila = build_state(design, "base"), build_state(design, "ila")
    base_ok = "bitstream" in base["ran"] and base["bitstream"] is True
    if stage == "configuration-and-debug":
        if not base_ok:
            return ""
        out = [f"{RECON} build/base/gates.json shows the base build's bitstream stage ran and its bitstream_present gate is true"]
        if not ila["present"]:
            out.append("there is no build/ila record" + (" and no probes.yaml" if not (design / "probes.yaml").is_file() else "")
                       + ", so the records show no debug build with the ILA was attempted or recorded")
        elif ila["error"] and not ila["ran"]:
            out.append(f"build/ila/gates.json is an error stub ({str(ila['error'])[:120]}) with no flow stages"
                       + (" and there is no build/ila/run.json" if not ila["run_json"] else ""))
        elif "bitstream" not in ila["ran"]:
            out.append("the debug build with the ILA did not reach its bitstream stage")
        else:
            return ""
        return "; ".join(out) + ". " + ("The base build is not the one that failed." if not ila["present"] else "The failing build is the debug build with the ILA, not the base build.")
    if STAGE_BASE_GATES.get(stage) and records_verdict(design, stage) is True:
        return (f"{RECON} the detail names a bitstream gate, which stage {stage} does not check; build/base/gates.json shows "
                f"the gates of this stage ({', '.join(STAGE_BASE_GATES[stage])}) passing. The detail is a stale copy of "
                "another stage's failure.")
    return ""


def approval_text(S: dict, design: Path | None = None) -> str:
    """What approved the spec and the architecture, from the run summary (68F): never just "signed off"."""
    ap = [a for a in S.get("approvals") or [] if isinstance(a, dict)]
    q = S.get("questions") if isinstance(S.get("questions"), dict) else {}
    auto = S.get("review") == "off" and all(a.get("by") == "auto" for a in ap)
    oracle = S.get("oracle_model")
    if not oracle and design is not None:
        try:
            m = re.search(r"Interview oracle: ([^\s(.]+(?:/[^\s(.]+)?)", (design / "BUILD_NOTE.md").read_text(errors="replace"))
            oracle = f"{m.group(1)}, per BUILD_NOTE.md" if m else None
        except OSError:
            pass
    who = (f"approved automatically by a model, with no human review (review off; interview oracle "
           f"{oracle or 'not recorded'})" if auto else "reviewed by a person (see the run summary)")
    return (f"the specification and the architecture were {who}; the interview asked {q.get('asked')} questions, "
            f"{q.get('answered')} answered and {q.get('defaulted')} defaulted") if auto else \
        f"spec.yaml was {who}; the questions asked, answered and defaulted are in the run summary"


def oracle_conflict(design: Path, run_dir: Path, S: dict) -> str:
    """The interview oracle named differently by BUILD_NOTE.md and summary.json: '' or the sentence saying so."""
    try:
        note = (design / "BUILD_NOTE.md").read_text(errors="replace")
    except OSError:
        return ""
    m = re.search(r"Interview oracle: ([^\s(.]+(?:/[^\s(.]+)?)", note)
    if m and S.get("oracle_model") and m.group(1).strip() != str(S["oracle_model"]).strip():
        return (f"BUILD_NOTE.md names the interview oracle as {m.group(1)}, while summary.json names {S['oracle_model']}; the two "
                "records disagree and neither is confirmed, so the specification's provenance is uncertain")
    return ""


def formal_gap(design: Path) -> str:
    """Formal checks planned and replaced by simulation (testplan replan), with the recorded reason."""
    try:
        tp = yaml.safe_load((design / "verif" / "testplan.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return ""
    rows = [r for r in tp.get("replan") or [] if isinstance(r, dict) and r.get("method") == "formal"]
    if not rows:
        return ""
    return (f"formal checks were planned for {', '.join(str(r.get('requirement')) for r in rows)} and did not run; each was replaced "
            f"by a simulation check (verif/testplan.yaml replan). Reason recorded: {' '.join(str(rows[0].get('why', '')).split())}")


def tautologies(design: Path) -> list[str]:
    """Assertions in the bound checkers that cannot fail: a signal compared with both of its values ``(x == 1'b0) || (x == 1'b1)``."""
    out = []
    for chk in sorted((design / "verif" / "checkers").glob("*.sv")):
        for n, line in enumerate(chk.read_text(errors="replace").splitlines(), 1):
            m = re.search(r"`V_\w+\((\w+),.*\((\w+)\s*==\s*1'b0\)\s*\|\|\s*\(\2\s*==\s*1'b1\)", line)
            if m:
                out.append(f"{m.group(1)} ({chk.name}:{n}) asserts that {m.group(2)} is 0 or 1, which is always true")
    return out


def registers_from_spec(spec: dict) -> list[dict]:
    reg = spec.get("registers")
    rows = reg.get("map") if isinstance(reg, dict) else reg
    out = []
    for r in rows or []:
        if isinstance(r, dict) and r.get("name") is not None and r.get("offset") is not None:
            out.append({k: r[k] for k in ("offset", "name", "access", "reset", "bits") if r.get(k) is not None}
                       | ({} if r.get("access") is not None else {"access": "-"}))
    return out


def prose_claims(design: Path, h: dict) -> list[str]:
    """Prose that says a stage or the design was approved or signed off with no human, or that a build failed that the
    records show was never attempted (68F)."""
    out = []
    auto = any("approved automatically" in str(e.get("what")) for e in h.get("evidence") or [])
    ila = build_state(design, "ila")
    for path, t in H._strings({k: h.get(k) for k in ("title", "summary", "scope_not", "next_steps", "open_questions",
                                                     "interfaces", "resets", "target")}):
        for sent in re.split(r"(?<=[.;])\s+", t):
            if auto and re.search(r"\b(signed[- ]off|approved)\b", sent, re.I) and not re.search(
                    r"automatic|no human|by a model|\bnot\b|\bnor\b|\bnever\b|before|until", sent, re.I):
                out.append(f"{path}: says approved or signed off without saying it was automatic, by a model, with no human review")
            if (not ila["present"] and not (design / "probes.yaml").is_file()
                    and re.search(r"(debug|ILA)[^.;]{0,80}(did not complete|failed to build|build failed|failed)", sent, re.I)):
                out.append(f"{path}: says the debug build failed or did not complete, but the records show none was attempted or recorded")
    return out


def contradictions(design: Path, h: dict) -> list[str]:
    """For the DOC gate and doccheck: a gap that quotes a "did not run" gate detail the same run's build records contradict,
    without carrying the reconciliation."""
    out = []
    for g in h.get("gaps") or []:
        a, t = g.get("about"), str(g.get("text") or "")
        if a in STAGE_NAMES and "did not run" in t and RECON not in t and (r := reconcile(design, a, t)):
            out.append(f"gap about {a!r} quotes a gate detail that the build records contradict and does not say so: {r[:200]}")
    return out


V_MEANS = {"V0": "the test plan, the model and the benches exist",
           "V1": "every spec item is traced to a check and the benches use the blind model",
           "V2": "simulation: seeded runs, a constrained-random test, bound assertions and formal tasks",
           "V3": "coverage (line, toggle, functional bins, cover properties), three seeds and the mutation score"}


def _vv(v) -> str:
    if v is None:
        return "not measured"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v[:6]) + (" ..." if len(v) > 6 else "") if v else "none"
    return str(v)


def verif_text(vg: dict, level: str) -> str:
    """What the verification record says (68F): the V-stage reached, what it means, and what did not run or pass above it, so
    no entry reads "simulation, pass" for a run that stopped at V1."""
    reached = vg.get("reached")
    st = vg.get("stages") or {}
    out = [f"verification (flow/verif_gates.py) against the Modeller's reference model reached {reached or 'none'} of V3; the "
           f"run asked for {level}"]
    if reached:
        out.append(f"{reached} means {V_MEANS[reached]}")
    for k in ("V2", "V3"):
        if reached and k <= reached and (st.get(k) or {}).get("pass"):
            continue
        shown = [(n, c) for n, c in ((st.get(k) or {}).get("checks") or {}).items()
                 if not c.get("pass") and (c.get("threshold") not in ([], None) or (isinstance(c.get("value"), list) and c["value"]))]
        if shown:
            out.append(f"{k} ({V_MEANS[k]}) did not pass: " + "; ".join(
                f"{n.replace('_', ' ')} {_vv(c.get('value'))}" + (f" (needs {_vv(c.get('threshold'))})" if c.get("threshold") not in ([], None) else "")
                for n, c in shown[:8]))
    if not (st.get("V-HW") or {}).get("pass"):
        out.append("no board result (V-HW) is recorded")
    return "; ".join(out)


def cover_diagnosis(design: Path, vg: dict) -> str:
    """A cover property read at 0 % while the functional bins were all hit: the records show an inconsistency, not a stimulus
    shortfall. Says so (68F), names what was bound, and checks the bound names exist in the top. '' when it does not apply."""
    v3 = ((vg.get("stages") or {}).get("V3") or {}).get("checks") or {}
    unhit = (v3.get("cover_properties_unhit") or {}).get("value") or []
    pct = (v3.get("cover_properties_pct") or {}).get("value")
    bins = v3.get("functional_bins_pct") or {}
    if not unhit or not bins.get("pass") or str(pct) not in ("0", "0.0"):
        return ""
    out = [f"cover properties {', '.join(unhit)} read {pct} % while the functional bins were all hit ({bins.get('value')}) and "
           f"{(v3.get('seeds_run') or {}).get('value')} seeds ran. The benches did drive the design, so a missing stimulus is "
           "unlikely to be the whole cause; the cover results and the functional coverage disagree. Compare the two before "
           "proposing any new stimulus."]
    for chk in sorted((design / "verif" / "checkers").glob("*.sv")):
        t = chk.read_text(errors="replace")
        mb = re.search(r"\bbind\s+(\w+)\s+(\w+)\s+\w+\s*\((.*?)\)\s*;", t, re.S)
        if not mb:
            continue
        top_txt = "".join(q.read_text(errors="replace") for q in sorted((design / "rtl").glob("*.sv")) if mb.group(1) in q.read_text(errors="replace"))
        binds = re.findall(r"\.(\w+)\(\s*!?(\w+)\s*\)", mb.group(3))
        miss = [b for _, b in binds if not re.search(rf"\b{re.escape(b)}\b", top_txt)]
        out.append(f"The checker {chk.name} binds " + ", ".join(f"{a} to {b}" for a, b in binds) + f" into {mb.group(1)}"
                   + (" (outside Icarus only)." if "__ICARUS__" in t else "."))
        out.append("Every bound name is declared in the top RTL, so a misspelt binding is not the cause." if not miss else
                   "These bound names are not declared in the top RTL: " + ", ".join(miss) + " (a wrong binding).")
        break
    out.append("The cause is not settled by the records.")
    return " ".join(out)


def _spec_timing(spec: dict, name: str) -> str:
    """The spec's own timing sentence for a parameter (its ``timing`` section; matched on the first word of the names)."""
    tim = spec.get("timing")
    if not isinstance(tim, dict):
        return ""
    w = name.lower().split("_")[0]
    for k, v in tim.items():
        if isinstance(v, str) and str(k).lower().split("_")[0] == w:
            return " ".join(v.split())
    return ""


def agent_facts(S: dict) -> dict:
    """The run's provenance, from summary.json: model, harness, loops, turns, wall time, tokens and cost."""
    f: dict[str, Any] = {}
    for k in ("model", "harness", "stop"):
        if isinstance(S.get(k), str) and S[k]:
            f[k] = S[k]
    for k in ("loops", "turns", "tokens"):
        if isinstance(S.get(k), int) and not isinstance(S.get(k), bool):
            f[k] = S[k]
    if isinstance(S.get("wall_s"), (int, float)):
        f["wall_s"] = S["wall_s"]
    if isinstance(S.get("cost_usd"), (int, float)) and S.get("harness") == "deepagents":
        f["cost_usd"] = S["cost_usd"]                      # provider-reported (plan runs report none)
    if isinstance(S.get("plan_cost_estimate_usd"), (int, float)):
        f["plan_cost_estimate_usd"] = S["plan_cost_estimate_usd"]
    return f


def _clocks(design: Path) -> list[dict]:
    x = design / "design.xdc"
    if not x.is_file():
        return []
    out = []
    for m in re.finditer(r"create_clock\b[^\n]*?-period\s+([\d.]+)[^\n]*?get_ports\s+\{?\s*(\w+)", x.read_text()):
        out.append({"name": m.group(2), "mhz": round(1000.0 / float(m.group(1)), 6), "source": H.rel(x)})
    return out


def _is_empty(p: Path) -> bool:
    """A source file with no code: blank, or only comments (a placeholder)."""
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return False
    return not any(l.strip() and not l.strip().startswith(("//", "/*", "*", "--", "#")) for l in lines)


def build_sources(design: Path) -> list[Path]:
    """The files build.yaml lists as sources (globs relative to the repo root), existing ones, in order."""
    try:
        bld = yaml.safe_load((design / "build.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return []
    out: list[Path] = []
    for pat in bld.get("sources") or []:
        for q in sorted(ROOT.glob(str(pat))):
            if q.is_file() and q not in out:
                out.append(q)
    return out


def _is_shared(q: Path, design: Path) -> bool:
    """A build source the agent did not write: outside the design directory and outside any run or result tree (a design
    copied to another place still lists its own sources by their old path)."""
    return design not in q.parents and H.rel(q).split("/", 1)[0] not in ("runs", "results")


def _probe_text(p: Path) -> str:
    try:
        y = yaml.safe_load(p.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return ""
    ps = [x for x in y.get("probes") or [] if isinstance(x, dict) and x.get("name")]
    if not ps:
        return ""
    ila = y.get("ila") or {}
    return (f"; ILA {ila.get('name', '')} on {ila.get('clock_net', 'its clock')}"
            + (f", depth {ila['depth']}" if ila.get("depth") else "") + "; probes: "
            + ", ".join(f"{x['name']} ({x['width']} bits)" if x.get("width") else str(x["name"]) for x in ps))


def _files(design: Path) -> list[dict]:
    seen, out = set(), []
    shared = {q.name: q for q in build_sources(design) if _is_shared(q, design) and q.suffix in (".sv", ".v", ".vhd")}
    for pat, what in FILE_KINDS:
        for p in sorted(design.glob(pat)):
            if p.is_file() and p not in seen and "__pycache__" not in p.parts and p.suffix not in (".pyc",):
                seen.add(p)
                w = what
                if p.name == "probes.yaml":
                    w += _probe_text(p)
                if p.name == "build.yaml" and shared:
                    w += ("; its sources also include shared shell files the agent did not write (read from the repository, "
                          "not copied here): " + ", ".join(H.rel(q) for q in shared.values()))
                if p.parent.name == "rtl" and _is_empty(p):
                    w += (" (empty: it holds no code" + (f"; the build reads {H.rel(shared[p.name])} for this module instead"
                                                          if p.name in shared else "") + ")")
                out.append({"path": H.rel(p), "what": w})
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
    S = _json(summ) or {}
    ungated_note, gate_notes = "", {}
    m_stop = re.match(r"stage (\d+) visited more than", str(stop or ""))
    if m_stop and int(m_stop.group(1)) < len(STAGE_NAMES):
        sn = STAGE_NAMES[int(m_stop.group(1))]
        if res.get(sn) == "fail" and "ungated_entries" not in S and records_verdict(design, sn) is True:
            # a run recorded before 68F: the visit limit refused the final entry into this stage before any gate ran, and
            # the old summary wrote that entry as a failure; the build records show this stage's gates passing
            res[sn] = "pass"
            gate_notes[sn] = (f"{RECON} summary.json records this stage as failed only because the visit limit refused its final "
                              "entry before any gate ran; build/base/gates.json shows its gates passing")
            ungated_note = (f"; the final entry into stage {sn} was refused by the visit limit before any gate ran (summary "
                            f"stop), and the build records show its gates passing, so it is counted as passed")
    ev, ms, gaps = [], [], []

    def gap(about: str, text: str) -> None:
        if about not in {g["about"] for g in gaps}:
            gaps.append({"about": about, "text": text})

    short: dict[str, str] = {}              # evidence ID -> a shorter text for its gap (the long text stays in the evidence row)

    def e(activity: str, result: str, what: str, rec: Path, short_gap: str | None = None, **kw) -> str:
        i = f"E{len(ev) + 1}"
        ev.append({"id": i, "activity": activity, "result": result, "what": what, "record": H.rel(rec), **kw})
        if short_gap:
            short[i] = short_gap
        return i

    def m(what: str, category: str, unit: str, rec: Path, field: str, cond: str, key: str | None = None) -> None:
        ms.append({"id": f"M{len(ms) + 1}", "what": what, "category": category, **({"key": key} if key else {}),
                   "unit": unit, "record": H.rel(rec), "field": field, "conditions": cond})

    if summ.is_file():
        auto = "automatically" in approval_text(S, design)
        e("review", "partial" if auto and "clarify" not in (carried or ()) else res["clarify"],
          ("spec.yaml carried from the handover of the earlier run (stage clarify passed there and "
           "its inputs had not changed)") if "clarify" in (carried or ()) else approval_text(S, design), summ)
    vg_p = design / "build" / "verif" / "verif_gates.json"
    vg = _json(vg_p)
    if vg:
        reached = vg.get("reached")
        ok = bool(reached) and reached >= verif_level
        full = bool(reached) and reached >= "V3"
        e("simulation", "pass" if ok and full else ("partial" if reached else "fail"), verif_text(vg, verif_level), vg_p,
          short_gap=f"verification reached {reached or 'no stage'} of V3 (the run asked for {verif_level}); the checks that did "
                    "not pass or did not run are listed in the evidence row")
        open_rows: dict[str, list[str]] = {}
        for row in vg.get("traceability") or []:
            if row.get("result") != "pass":
                det = str(row.get("detail") or "")
                res_r = "not run (the stage that makes this evidence did not run)" if det.endswith("= None") else row.get("result")
                open_rows.setdefault(row["requirement"], []).append(
                    f"{row.get('method')} ({row.get('artefact')}) is {res_r}: {det[:200]}")
        for req, why in open_rows.items():
            gap(req, f"{req} has no passing evidence for every proof method: " + "; ".join(why))
        v3 = ((vg.get("stages") or {}).get("V3") or {}).get("checks") or {}
        if isinstance(v3.get("seeds_run", {}).get("value"), int) and v3["seeds_run"]["value"] > 0:
            for what, k, unit in (("simulation seeds run", "seeds_run", ""), ("line coverage", "line_pct", "%"),
                                  ("toggle coverage", "toggle_pct", "%"), ("functional coverage bins hit", "functional_bins_pct", ""),
                                  ("cover properties hit", "cover_properties_pct", "%")):
                if v3.get(k, {}).get("value") is not None:
                    m(what, "verification", unit, vg_p, f"stages.V3.checks.{k}.value",
                      "Verilator coverage simulation of the RTL against the Modeller's model, every seed the bench ran")
        diag = cover_diagnosis(design, vg)
        if diag:
            gap("cover_properties", diag)
    mu_p = design / "build" / "verif" / "mutation.json"
    mu = _json(mu_p)
    if mu and mu.get("evaluated"):
        e("faults", "pass" if not mu.get("survived") and not mu.get("timed_out") else "partial",
          f"generated mutants of the RTL run against the Verifier's benches, each of which must make a test fail: "
          f"{mu.get('sampled')} sampled of {mu.get('candidates')} candidates, {mu.get('evaluated')} evaluated, "
          f"{mu.get('killed')} killed, {mu.get('survived')} survived, {mu.get('timed_out')} timed out", mu_p)
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
        bs = build_state(design, variant)
        if bs["error"] and not bs["ran"]:               # an error stub: the build did not complete
            i = e("build", "fail", f"Vivado {label}: its gates record is an error stub ({str(bs['error'])[:120]}) with no flow "
                  "stages" + ("" if bs["run_json"] else f", and the build has no run record (build/{variant}/run.json)")
                  + ": the build did not complete", gp)
            gap(i, f"the {label} did not complete: build/{variant}/gates.json is an error stub, so there is no gate result for it")
            continue
        result = ("pass" if g.get("pass") else "fail") if current else "partial"
        ran = bs["ran"]
        if current:
            i = e("build", result, f"Vivado {label}; flow stages that ran: " + (", ".join(ran) or "none"), gp)
        else:
            met = all(((g.get("gates") or {}).get(k) is True) for k in ("setup", "hold", "pulse_width"))
            i = e("build", result, f"Vivado {label} under an earlier Vivado release than the pinned one: it reached "
                  f"{ran[-1] if ran else 'no flow stage'}, the gates of the stages it ran {'all passed' if g.get('pass') else 'did not all pass'}"
                  + (" and its timing was met" if met else "") + "; every number from that build is withdrawn (it cannot be "
                  f"re-measured on Vivado {rel_now} without a rebuild), so none is published", gp)
        if not current:
            gap(i, f"the {label} was made under an earlier Vivado release than {rel_now}: its result is not current and no "
                f"number from it is published. Re-measure it, when the flow reaches the build again, with the resume command in How to build (python -m agent "
                f"resume), and only then rely on its gates")
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
            gap(x["id"], f"{x['activity']} evidence is {x['result']}: {short.get(x['id'], x['what'])}")
    for s, r in res.items():
        if r == "fail":
            why = failing_gates(design, s)
            rec = reconcile(design, s, why)
            gap(s, f"stage {s} did not pass its gates in this run" + (f"; at its last visit: {why}" if why else
                "; the run summary and the review pages under build/review/ give the failures") + (f". {rec}" if rec else ""))
        elif r == "not-run":
            why = ("the run resumed after this stage; its inputs had not changed since the handover"
                   if resumed_from and STAGE_NAMES.index(s) < _first_visited(gates_last) else
                   "the run stopped before this stage" + (f" ({stop})" if stop else ""))
            gap(s, f"stage {s} was not run: {why}")
    if (oc := oracle_conflict(design, run_dir, S)):
        gap("oracle_record", oc)
    if (fg := formal_gap(design)):
        gap("formal", fg)
    if (tl := tautologies(design)):
        gap("assertions", "assertions that cannot fail: " + "; ".join(tl) + ". They show only that the signal exists, not that the design behaves")
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
    rj = _json(design / "build" / "base" / "run.json") or {}      # build time and memory: only a build on the pinned release
    base_min = round(rj["wall_s"] / 60, 1) if rj.get("vivado_version") == rel_now and isinstance(rj.get("wall_s"), (int, float)) else None
    base_mem = (f"; peak memory {rj['scope_anon_peak_mib']} MiB (anonymous, the systemd scope)"
                if rj.get("vivado_version") == rel_now and isinstance(rj.get("scope_anon_peak_mib"), int) else "")
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
         "clocks": _clocks(design), "resets": [], "interfaces": [], **({"registers": registers_from_spec(spec)}
                                                                      if registers_from_spec(spec) else {}),
         "parameters": [{"name": str(k), "value": v, "legal": "WRITE", "note": "WRITE",
                         **({"_spec_timing": t} if (t := _spec_timing(spec, str(k))) else {})}
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
              "minutes": base_min, "needs": f"Vivado {rel_now} and a heavy slot" + base_mem}],
         "evidence": ev, "measurements": ms, "gaps": gaps, "next_steps": ["WRITE"], "open_questions": [],
         "history": [{"date": _date(run_id), "brief": "agent run",
                      "note": ("resumed from an earlier handover (summary.json resumed_from names it); " if resumed_from else "")
                      + "produced by the agent graph; stages that passed: " + (", ".join(passed) or "none")
                      + (f"; carried from the handover: {', '.join(carried)}" if carried else "") + ungated_note}],
         "agent_run": {"run_id": run_id, "record": H.rel(summ if summ.is_file() else run_dir / "config.json"), **agent_facts(S)},
         "state": {"stage": stage, "gates": res, "vivado": rel_now, "kb_pin": None, "build_id": None,
                   "evidence_vivado": ("none" if not evv else "current" if evv == {rel_now} else "earlier"),
                   **({"gate_notes": gate_notes} if gate_notes else {})}}
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
    shared = [q for q in build_sources(design) if _is_shared(q, design)]
    if shared:
        out += ("\nSOURCES THE BUILD READS (build.yaml; shared files the agent did not write):\n"
                + "\n".join(f"- {H.rel(q)}" + (" (empty)" if _is_empty(q) else "") for q in shared) + "\n")
        shown = ""
        for q in sorted(shared, key=lambda q: q.stat().st_size):          # small modules first: the most files fit
            body = q.read_text(errors="replace")
            if len(body) <= 9000 and len(shown) + len(body) <= 24000:
                shown += f"\n--- {H.rel(q)} ---\n{body}\n"
        if shown:
            out += "\nSHARED SOURCES (as far as they fit):" + shown
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
    for p in h["parameters"]:                                   # 68F: the spec's own rate for a parameter, in its note
        t = (p.pop("_spec_timing", None) or "").strip()
        if t and t not in p["note"]:
            p["note"] = f"{p['note'].rstrip()} Spec timing: {t}"
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
    for k in ("model", "harness", "loops", "turns", "wall_s", "tokens", "cost_usd", "plan_cost_estimate_usd", "stop"):
        if (h.get("agent_run") or {}).get(k) != d["agent_run"].get(k):
            errs.append(f"agent_run.{k}: {(h.get('agent_run') or {}).get(k)!r} is not the run record's {d['agent_run'].get(k)!r}")
    errs += [f"state.gate_notes: {(h.get('state') or {}).get('gate_notes')!r} is not the run's {d['state'].get('gate_notes')!r}"] \
        if (h.get('state') or {}).get('gate_notes') != d['state'].get('gate_notes') else []
    if (h.get('registers') or None) != (d.get('registers') or None):
        errs.append('registers: not the spec.yaml register map')
    return errs + overclaims(h) + contradictions(ddir, h) + prose_claims(ddir, h)


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


def registry_doc_gate(design: Path, required: list[str]) -> list[str]:
    """Brief 71: the DOC gate as the check suite's ``doc`` entry (flow/checks), so the gate and the ``check`` tool agree."""
    from flow import checks as C
    return C.doc_gate(design, required)


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
    return errs + stale + unwritten(h) + overclaims(h) + contradictions(design, h) + remeasure_first(h) + prose_claims(design, h)


def remeasure_first(h: dict) -> list[str]:
    """Builds made under an earlier Vivado release: re-measuring (python -m agent resume) is a required next step (68F). It
    comes when the flow reaches the build again, so it need not be first: the first step is the earliest failing stage."""
    if (h.get("state") or {}).get("evidence_vivado") != "earlier":
        return []
    if not any(re.search(r"re-?measur|agent resume", str(x), re.I) for x in h.get("next_steps") or []):
        return ["next_steps: a build was made under an earlier Vivado release, so one next step must re-measure it "
                "(python -m agent resume); it need not be first"]
    return []


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
            problems = registry_doc_gate(design, required)   # brief 71: the registry's doc check (same problems)
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
