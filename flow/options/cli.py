"""``python -m agent improve`` (brief 104): analyse a loaded design, print two to four strategies, run the one the user picks.

    agent improve <design> "<request>"            analysis (read-only) and options; saved to <design>/build/managed/strategy.json
    agent improve <design> --analyse-only         the analysis alone, no model call
    agent improve <design> --more                 different options for the same request
    agent improve <design> --edit N "<change>"    option N rewritten with your change
    agent improve <design> --choose N [--dry-run] start the ordinary scoped run (``agent resume <design> ... --scope ...``) with option N

A request that is ambiguous or unsupported prints a question and no options. A choice whose option changes an interface contract
is refused until the owner has listed the components in ``approved_contract_changes`` of ``project.yaml`` (the agent cannot write that file).
The saved record (analysis hash and sources, the options offered, what was rejected, the choice) goes into the run's ``summary.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from agent.core import managed
from flow.options import analysis as A
from flow.options import combine as C
from flow.options import generate as G

STATE = "strategy.json"


def state_path(design: Path) -> Path:
    return Path(design) / "build" / "managed" / STATE


def add_parser(sub) -> None:
    p = sub.add_parser("improve", help="brief 104: analyse a loaded design and offer strategies to improve it (nothing is changed until --choose)")
    p.add_argument("design", type=Path, help="a design directory (with or without project.yaml)")
    p.add_argument("request", nargs="?", help='what should improve, e.g. "lower latency"; with --edit, your change to the option')
    p.add_argument("--analyse-only", action="store_true", help="print the read-only analysis; no model call")
    p.add_argument("--more", action="store_true", help="offer options different from the last ones")
    p.add_argument("--edit", type=int, metavar="N", help="rewrite option N with the change given as the request text")
    p.add_argument("--choose", type=int, metavar="N", help="run option N: the ordinary scoped run (agent resume) with its scope")
    p.add_argument("--dry-run", action="store_true", help="with --choose: print what would run and stop")
    p.add_argument("--build-dir", type=Path, help="the build reports to read (default <design>/build/base, else <design>/evidence)")
    p.add_argument("--blind", action="store_true", help="withhold the stage file's technique and removable-clocks hints from the model (an ablation; see docs/strategy_options.md)")
    p.add_argument("--latency-path", help="which latency chain of the stage file (default: its first)")
    p.add_argument("--out", type=Path, help="where the record and the model-call log go (default <design>/build/managed)")
    p.add_argument("--json", action="store_true", help="print the record as JSON instead of text")
    p.add_argument("--models-file", type=Path, help="the project's model table (the purpose is 'options')")
    p.add_argument("--model-config", help="JSON command-line layer of the model table")
    p.add_argument("--replay", help="LLM replay fixture (no network)")
    p.add_argument("--record", help="record the model calls to this fixture")
    p.add_argument("--board", help="--choose: passed to resume")
    p.add_argument("--verif-level", choices=["V1", "V2", "V3"], help="--choose: passed to resume")
    p.add_argument("--stop-after", type=int, help="--choose: passed to resume")
    p.add_argument("--max-usd", type=float, help="--choose: passed to resume")


# --- text rendering ---------------------------------------------------------------------------------------------------

def _range(g: dict[str, Any]) -> str:
    lo, hi = g["low"], g["high"]
    fmt = (lambda v: f"{v:g}")
    return f"{fmt(lo)} to {fmt(hi)} {g['unit']}" if lo != hi else f"{fmt(lo)} {g['unit']}"


def render(rec: dict[str, Any], analysis: dict[str, Any] | None = None) -> str:
    out = [f"request: {rec['request']}"]
    if rec["status"] == "question":
        out += ["", "No options yet. A question first:", f"  {rec['question']}"]
        if rec.get("reason"):
            out.append(f"  ({rec['reason']}; nothing was guessed and no model was called)" if not rec.get("attempts") else f"  ({rec['reason']})")
        return "\n".join(out)
    if rec["status"] == "failed":
        out += ["", "The generator did not produce options that pass the checks; nothing is offered.", *[f"  - {p}" for p in rec.get("unresolved", [])]]
        return "\n".join(out)
    out.append(f"goal: {rec['goal']}; analysis {rec['analysis_hash'][:12]} from {len(rec['analysis_sources'])} file(s); model {rec['model'].get('model')} on {rec['model'].get('endpoint')}"
               + ("; BLIND (no technique hints)" if rec.get("blind") else ""))
    for g in (analysis or {}).get("gaps", []):
        out.append(f"gap: {g}")
    for o in rec["options"]:
        out += ["", f"Option {o['n']} ({o['id']}): {o['title']}   [{o['scope']['kind'].replace('_', ' ')}]" +
                (f"   [COMBINED by code from {' + '.join(o['combined_from'])}]" if o.get("origin") == "combiner" else ""),
                f"  scope: {', '.join(o['scope']['components'])}   ({o['scope']['cli']})",
                f"  approach: {o['approach']}"]
        g = o["gain"]
        tag = {"model": "model", "measurement": "measured earlier", "guess": "GUESS, no basis"}[g["basis"]]
        out.append(f"  expected gain: {_range(g)} ({tag}); {g['basis_note']}")
        if g["cites"]:
            out.append(f"    cites: {', '.join(g['cites'])}  [{'; '.join(g['sources'])}]")
        if g.get("ceiling") is not None:
            out.append(f"    upper bound from the analysis: {g['ceiling']:g} {g['unit']} ({g['ceiling_basis']})")
        c = o["cost"]
        wm = c.get("wall_minutes")
        out.append(f"  cost: {c['iterations']['low']} to {c['iterations']['high']} build-and-check round(s) = {c['vivado_runs']['low']} to {c['vivado_runs']['high']} Vivado run(s)"
                   + (f", about {wm['low']:g} to {wm['high']:g} min of Vivado ({wm['basis']}; {wm['cite']})" if wm else ", wall time unknown (no recorded build)")
                   + "; model spend not estimated")
        r = o["risk"]
        out.append(f"  risk: {r['summary']}")
        out.append(f"    gates: {'; '.join(r['gates'])}")
        out.append(f"    eqy needed: {'yes' if r['needs_eqy'] else 'no'}; board evidence needed: {'yes' if r['needs_board'] else 'no'}")
        if r["contract_change"]:
            out.append("    CONTRACT CHANGE: " + ("; ".join(r["contract_flags"]) or r["contract_note"] or "the option says it changes an interface") +
                       ("  [flag raised by the checker]" if r["contract_flag_added_by_checker"] else "") +
                       ("  Needs the owner's approval before it can run." if r["needs_owner_approval"] else "  Approved in project.yaml."))
        out.append("  not touched: " + (", ".join(f"{n['component']} ({n['why']})" for n in o["not_touched"]) or "nothing else is in the project")
                   + (f"; {o['hidden_components']} excluded component(s) are not shown" if o.get("hidden_components") else ""))
    cb = rec.get("combiner")
    if cb and cb.get("not_composable"):
        out += ["", "combinations not offered (the combiner, code):"] + [f"  {' + '.join(x['from'])}: {x['reason']}" for x in cb["not_composable"][:8]]
    if rec.get("rejected"):
        out += ["", f"{len(rec['rejected'])} proposed option(s) failed the checks and are not offered: " +
                "; ".join(f"{r['id']}: {r['problems'][0]}" for r in rec["rejected"] if r["problems"])]
    for n in rec.get("notes", []):
        out.append(f"note: {n}")
    out += ["", "Pick one with --choose N, change one with --edit N \"<your change>\", or ask for others with --more."]
    return "\n".join(out)


# --- the command ------------------------------------------------------------------------------------------------------

def _load_state(design: Path) -> dict[str, Any]:
    f = state_path(design)
    return json.loads(f.read_text()) if f.is_file() else {}


def _save(design: Path, state: dict[str, Any], out: Path | None) -> Path:
    f = (Path(out) / STATE) if out else state_path(design)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, indent=1, default=str) + "\n")
    return f


def _resolver(a, design: Path, out_dir: Path):
    from agent.models.resolver import resolver_for
    extra = json.loads(a.model_config) if a.model_config else None
    return resolver_for("options", project_file=a.models_file, replay=a.replay, record=a.record, run_dir=out_dir, extra=extra)


def improve_cmd(a, main_fn) -> int:
    design = Path(a.design).resolve()
    if not design.is_dir():
        print(f"improve: {design} is not a directory", file=sys.stderr)
        return 2
    out_dir = Path(a.out) if a.out else design / "build" / "managed"
    if a.choose is not None:
        return _choose(a, design, main_fn)
    try:
        an = A.analyse(design, build_dir=a.build_dir, path=a.latency_path)
        project = managed.load(design)
        if project is None:
            project = managed.Project(**A._converted(design))
    except (ValueError, OSError, KeyError) as e:
        print(f"improve: {e}", file=sys.stderr)
        return 2
    if a.analyse_only:
        print(json.dumps(an, indent=1, default=str) if a.json else _render_analysis(an))
        return 0
    state = _load_state(design)
    mode, previous, edit = "new", None, None
    request = a.request
    if a.more or a.edit is not None:
        cur = state.get("current")
        if not cur or not cur.get("options"):
            print("improve: no earlier options for this design: ask for options first", file=sys.stderr)
            return 2
        if cur["analysis_hash"] != an["hash"]:
            print("improve: the design or its reports changed since those options were made: ask again", file=sys.stderr)
            return 2
        previous = cur["options"]
        request = cur["request"] if a.more else cur["request"]
        if a.edit is not None:
            tgt = next((o for o in previous if o["n"] == a.edit), None)
            if tgt is None or not a.request:
                print(f"improve: --edit N \"<your change>\": option {a.edit} not found, or no change given", file=sys.stderr)
                return 2
            if tgt.get("origin") == "combiner":
                print(f"improve: option {a.edit} was built by the combiner from options {' + '.join(tgt['combined_from'])}: edit one of those (the combined options are rebuilt), or ask with --more", file=sys.stderr)
                return 2
            mode, edit = "edit", {"id": tgt["id"], "instruction": a.request}
        else:
            mode = "more"
    if request is None:
        request = ""
    resolver = _resolver(a, design, out_dir)
    e = resolver.entry("options")
    info = {"purpose": "options", "endpoint": e.endpoint, "kind": e.kind, "model": e.model, "effort": e.options.get("effort"), "entry_hash": e.hash, "table_hash": resolver.table.hash}
    pre = G.schema.classify_request(request, project, an)
    llm = resolver.text("options") if pre["status"] == "ok" else None
    rec = G.improve(an, request, project, llm, blind=a.blind, mode=mode, previous=previous, edit=edit, model_info=info)
    history = state.get("history", [])
    if state.get("current"):
        history.append({k: state["current"][k] for k in ("created", "request", "mode", "status", "analysis_hash", "options_hash") if k in state["current"]})
    if mode == "edit" and rec["status"] == "options" and rec["options"] and previous:        # the edited option replaces its original; the others stay
        new = rec["options"][0]
        rec["options"] = [new if o["id"] == edit["id"] else o for o in previous if o.get("origin") != "combiner"]
        C.apply(rec, an, project, goal=rec["goal"], pinned=G.schema.classify_request(request, project, an)["pinned"], blind=a.blind)      # a combined option built from the old option is rebuilt
        rec["options_hash"] = G._sha(json.dumps(rec["options"], sort_keys=True))
    if mode == "more" and rec["status"] == "options" and previous:
        used = {o["id"] for o in previous}
        fresh = []
        for o in rec["options"]:
            k = len(previous) + len(fresh) + 1
            while f"O{k}" in used:
                k += 1
            used.add(f"O{k}")
            fresh.append(dict(o, id=f"O{k}"))
        rec["options"] = [o for o in previous if o.get("origin") != "combiner"] + fresh
        C.apply(rec, an, project, goal=rec["goal"], pinned=G.schema.classify_request(request, project, an)["pinned"], blind=a.blind)      # the combined options are rebuilt from every single option now offered
        rec["options_hash"] = G._sha(json.dumps(rec["options"], sort_keys=True))
    f = _save(design, {"current": rec, "history": history, "analysis": {k: an[k] for k in ("schema", "design", "hash", "sources", "gaps")}, "choice": None,
                       "inputs": {"build_dir": str(Path(a.build_dir).resolve()) if a.build_dir else None, "latency_path": a.latency_path}}, a.out)
    print(json.dumps(rec, indent=1, default=str) if a.json else render(rec, an))
    print(f"\nrecord: {f}", file=sys.stderr)
    return 0 if rec["status"] in ("options", "question") else 1


def _render_analysis(an: dict[str, Any]) -> str:
    out = [f"design {an['design']} (top {an['top']}); analysis {an['hash'][:12]}; {len(an['sources'])} source file(s), {len(an['facts'])} citable facts"]
    out += ["", "components:"] + [f"  {c['name']:<16} {c['ownership']:<8} {c['level']:<10} {c['instance']:<22} trust {c['trust']}" for c in an["components"]]
    if an.get("hidden_components"):
        out.append(f"  ({an['hidden_components']} excluded component(s) not shown)")
    lat = an.get("latency")
    if lat:
        out += ["", f"latency: {lat['title']}", f"  {lat['total_clocks']} clocks = {lat['total_ns']} ns (period {lat['period_ns']} ns; reconciled {lat['reconciled']})"]
        out += [f"  {s['id']:<16} {s['clocks']} clk  {s['domain']:<6} {s['kind']:<8} component {s['component']}  slack {s['setup_slack_ns']}" for s in lat["stages"]]
    t = an.get("timing")
    if t:
        out += ["", f"timing: WNS {t.get('wns_ns')} ns, WHS {t.get('whs_ns')} ns, failing endpoints {t.get('failing_endpoints')}"]
        w = t.get("worst_path")
        if w:
            out.append(f"  worst path: {w['source']} -> {w['destination']}: {w.get('logic_levels')} levels, {w.get('data_path_ns')} ns, in {w.get('source_component')}")
    rs = an.get("resources")
    if rs and rs.get("by_component"):
        out += ["", "resources per component (own LUT / FF):"] + [f"  {r['component']:<16} {r['lut_own']:>6} {r['ff_own']:>6}" for r in rs["by_component"]]
    elif rs:
        out += ["", f"resources: {rs['total']} ({rs['note']})"]
    cd = (an.get("cdc") or {}).get("rows") or []
    if cd:
        out += ["", "clock crossings (report_cdc):"] + [f"  {r['source_clock']} -> {r['dest_clock']}: {r['endpoints']} endpoints, unsafe {r['unsafe']} ({r['exceptions']})" for r in cd if r["source_clock"] != r["dest_clock"]]
    if an.get("prior_runs"):
        out += ["", "earlier measured changes (prior runs, citable as a measurement):"] + [f"  {r['name']}: stages {', '.join(r['stages'])}, cut {r['gain']:g} clock(s)  [{r['fact']}]" for r in an["prior_runs"]]
    out += [""] + [f"gap: {g}" for g in an["gaps"]] + [f"note: {n}" for n in an["notes"]]
    return "\n".join(out)


def _choose(a, design: Path, main_fn) -> int:
    st = _load_state(design)
    cur = st.get("current")
    if not cur or cur.get("status") != "options":
        print("improve --choose: there are no saved options for this design; run `agent improve <design> \"<request>\"` first", file=sys.stderr)
        return 2
    opt = next((o for o in cur["options"] if o["n"] == a.choose), None)
    if opt is None:
        print(f"improve --choose: no option {a.choose}; options are 1 to {len(cur['options'])}", file=sys.stderr)
        return 2
    try:
        inp = st.get("inputs") or {}
        an = A.analyse(design, build_dir=a.build_dir or inp.get("build_dir"), path=inp.get("latency_path"))
    except (ValueError, OSError, KeyError) as e:
        print(f"improve --choose: {e}", file=sys.stderr)
        return 2
    if an["hash"] != cur["analysis_hash"]:
        print("improve --choose: the design or its reports changed since these options were made; ask again so the analysis matches the design", file=sys.stderr)
        return 2
    cur_project = managed.load(design)
    if cur_project is not None:                   # the manifest as it is now: every component of the scope is still owned (the checks ran when the options were made)
        bad = [c for c in opt["scope"]["components"] if not cur_project.component(c) or cur_project.component(c).ownership != "owned"]
        if bad:
            print(f"improve --choose: {', '.join(bad)} is no longer an owned component of this project; ask again", file=sys.stderr)
            return 2
    approved = set(cur_project.approved_contract_changes) if cur_project else set()
    affected = opt["risk"].get("contract_affected") or opt["scope"]["components"]
    if opt["risk"]["contract_change"] and not set(affected) <= approved:      # the manifest as it is now: the owner may have approved since
        names = sorted(set(affected))
        print("improve --choose: this option changes an interface contract "
              f"({'; '.join(opt['risk']['contract_flags']) or 'see the option'}). The owner must list {', '.join(names)} under approved_contract_changes in project.yaml "
              "(the agent cannot write that file); then choose again, or pick another option.", file=sys.stderr)
        return 3
    choice = {"chosen": opt["id"], "n": opt["n"], "scope": opt["scope"]["components"], "time": time.strftime("%Y-%m-%d %H:%M:%S"), "options_hash": cur["options_hash"],
              "analysis_hash": cur["analysis_hash"]}
    st["choice"] = choice
    f = _save(design, st, None)
    change = f"{cur['request']}. Strategy ({opt['title']}): {opt['approach']}"
    argv = ["resume", str(design), change, "--scope", ",".join(opt["scope"]["components"]), "--strategy-file", str(f)]
    for flag, val in (("--board", a.board), ("--verif-level", a.verif_level), ("--stop-after", a.stop_after), ("--max-usd", a.max_usd), ("--models-file", a.models_file),
                      ("--model-config", a.model_config), ("--replay", a.replay), ("--record", a.record)):
        if val is not None:
            argv += [flag, str(val)]
    if a.dry_run:
        argv += ["--dry-run"]
    print("running: python -m agent " + " ".join(json.dumps(x) if " " in x else x for x in argv), file=sys.stderr)
    return main_fn(argv)


def strategy_for_run(design: Path) -> dict[str, Any] | None:
    """What the run record keeps (``summary.json`` ``strategy``): the chosen option, the options offered (hashes and the options themselves),
    the analysis hash and sources, and the model's identity. None when the run did not come from ``agent improve``."""
    f = state_path(design)
    if not f.is_file():
        return None
    st = json.loads(f.read_text())
    cur, ch = st.get("current"), st.get("choice")
    if not cur or not ch:
        return None
    opt = next((o for o in cur["options"] if o["id"] == ch["chosen"]), None)
    return {"chosen": ch["chosen"], "scope": ch["scope"], "request": cur["request"], "goal": cur.get("goal"), "analysis_hash": cur["analysis_hash"],
            "options_hash": cur["options_hash"], "options_offered": [{"id": o["id"], "title": o["title"], "scope": o["scope"]["components"], "origin": o.get("origin", "model"),
                                                  **({"combined_from": o["combined_from"]} if o.get("origin") == "combiner" else {})} for o in cur["options"]],
            "chosen_option": opt, "model": cur.get("model"), "prompts": cur.get("prompts"), "analysis_sources": cur.get("analysis_sources"), "time": ch["time"]}
