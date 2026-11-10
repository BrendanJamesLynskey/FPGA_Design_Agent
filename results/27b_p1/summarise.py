"""Brief 27B P1: summarise the phase 0 runs into results/27b_p1/results.md and results.json.

    python results/27b_p1/summarise.py

Every number comes from the run's own files (``<spec>/phase0/*.json``, the replay fixture's provider-reported usage).
The reference checks compare the written files with facts fixed before the runs: the owner's three accepted pilot 1
contract choices, and the two c12 failures recorded in docs/design_environment.md section 3 (the LED port, the
open-drain AUD_PWM pin). No model judges anything here.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
SPECS = ("pilot1_run1", "pilot1_run2", "c12_pwm_audio_run1", "pilot1_run3", "c12_pwm_audio", "pilot1")   # the order run


def _load(p: Path) -> Any:
    return json.loads(p.read_text()) if p.suffix == ".json" else yaml.safe_load(p.read_text())


def _area(path: str) -> str:
    """The contract or design field kind a path names (``median3x3.contract.latency.a.b`` -> ``contract.latency``)."""
    parts = path.split(".")
    if parts[0] == "design":
        return "design." + parts[1]
    if len(parts) > 3 and parts[2] == "interfaces":
        return "contract.interfaces." + parts[-1]
    return "contract." + parts[2] if len(parts) > 2 else path


def _links(d: dict[str, Any], contracts: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for x in d.get("connections") or []:
        a, b = x["from"].split("."), x["to"].split(".")
        fa = next(f for f in contracts[a[0]]["interfaces"] if f["name"] == a[1])
        fb = next(f for f in contracts[b[0]]["interfaces"] if f["name"] == b[1])
        out.append({"link": f"{x['from']} -> {x['to']}", "protocol": fa.get("protocol"),
                    "backpressure": [fa.get("backpressure"), fb.get("backpressure")],
                    "source_gaps": [fa.get("source_gaps"), fb.get("source_gaps")]})
    return out


def checks(spec: str, root: Path) -> list[dict[str, Any]]:
    d = _load(root / "design.yaml")
    cs = {m["name"]: _load(root / "modules" / m["name"] / "contract.yaml") for m in d["modules"]
          if (root / "modules" / m["name"] / "contract.yaml").is_file()}
    out = []
    if spec.startswith("pilot1"):  # noqa: SIM102
        links = _links(d, cs)
        stream = [l for l in links if l["protocol"] == "axi4-stream"]
        out.append({"fact": "owner choice 1: a full-raster video stream with no back-pressure (every stream link: no back-pressure, no gaps)",
                    "found": stream or links,
                    "holds": bool(stream) and all(l["backpressure"] == [False, False] and l["source_gaps"] == [False, False]
                                                    for l in stream)})
        lat = [(m, x) for m, c in cs.items() for x in c.get("latency") or []]
        out.append({"fact": "owner choice 2: median latency H_TOTAL + 2", "found": [f"{m}: {x}" for m, x in lat],
                    "holds": any("median" in m and str(x.get("cycles")).replace(" ", "") == "H_TOTAL+2" for m, x in lat)})
        wb = {m["name"]: m.get("window_base") for m in d["modules"] if m.get("window_base") is not None}
        out.append({"fact": "owner choice 3: shell registers at window base 0x00", "found": wb,
                    "holds": bool(wb) and min(wb.values()) == 0})
    if spec.startswith("c12_pwm_audio"):
        bp = {p["name"]: p for p in d.get("board_ports") or []}
        aud = bp.get("AUD_PWM", {})
        out.append({"fact": "recorded c12 failure: AUD_PWM is open-drain (pulled low or released, never driven high)",
                    "found": aud, "holds": aud.get("drive") == "open-drain"})
        led = [p for n, p in bp.items() if n.startswith("LED")]
        out.append({"fact": "recorded c12 failure: the top has the 16-bit LED output (left off)",
                    "found": led, "holds": any(p["name"] in ("LED[15:0]", "LED") for p in led)})
        # the register map against the hidden spec's own map (offset, name, access): the oracle's ground truth
        hidden = yaml.safe_load((HERE.parents[1] / "benchmark" / "course" / "tasks" / "c12_nexys_pwm_audio" / "hidden"
                                 / "spec.yaml").read_text())
        want = sorted((int(str(r["offset"]), 0), r["name"], r["access"]) for r in hidden["registers"]["map"])
        have = sorted((int(str(r.get("offset")), 0), r.get("name"), r.get("access")) for c in cs.values()
                      for r in ((c.get("registers") or {}).get("map") or []))
        out.append({"fact": "register map = the hidden spec's map (offset, name, access)", "found": have,
                    "holds": have == want})
    return out


def summarise(spec: str) -> dict[str, Any]:
    root = HERE / spec
    p1 = _load(root / "phase0" / "pass1_requirements.json")
    p2 = _load(root / "phase0" / "pass2_contracts.json")
    s = _load(root / "phase0" / "session.json")
    calls = _load(root / "phase0" / "llm_calls.json")["calls"]
    by_area: Counter = Counter()
    settled: dict[str, list[str]] = {"answered": [], "assumption": []}
    for q in p2["questions"]:
        k = "answered" if q["status"] == "answered" else "assumption"
        settled[k] += q["fields"]
        by_area[(_area(q["fields"][0]), k)] += 1
    who = Counter(c["who"] for c in calls)
    return {"spec": spec, "valid": s["valid"], "errors": s["errors"], "modules": s["modules"],
            "pass1": {k: p1[k] for k in ("requirements", "asked", "answered", "defaulted", "drafter_repairs")},
            "pass2": {k: p2[k] for k in ("fields", "stated_in_spec", "asked", "answered", "defaulted", "drafter_repairs")},
            "pass2_by_limit": sum(q["by"] == "limit" for q in p2["questions"]),
            "bad_quotes": len(p2["bad_quotes"]), "unasked_changes": p2["unasked_changes"],
            "assumptions": s["assumptions"], "fields_settled_by_answer": settled["answered"],
            "fields_left_as_assumption": settled["assumption"],
            "by_area": sorted([[a, k, n] for (a, k), n in by_area.items()]),
            "questions_pass1": [{"q": q["text"], "status": q["status"], "settles": q["settles"]} for q in p1["questions"]],
            "questions_pass2": [{"fields": q["fields"], "status": q["status"], "by": q["by"],
                                 "draft": q["draft_value"], "final": q["final_value"], "answer": q["answer"]}
                                for q in p2["questions"]],
            "llm": s["llm"], "calls_by_role": dict(who), "checks": checks(spec, root)}


def _short(v: Any, n: int = 70) -> str:
    t = " ".join(str(v).split())
    return (t[: n - 3] + "...") if len(t) > n else t


def markdown(rs: list[dict[str, Any]]) -> str:
    L = ["# Brief 27B P1: phase 0 on two specs (development subjects only)", "",
         "Written by `results/27b_p1/summarise.py` from the runs' own files. Drafter and oracle: `openai/gpt-6-luna`",
         "(the agent's default), OpenRouter, `data_collection: deny`. Cost is the provider-reported figure per call.",
         "Runs in the order made. The harness was changed twice after reading a run (never during one):",
         "- after `pilot1_run1`: a stream latency or throughput the drafter left out is asked too; a contract for a",
         "  module not in the design is a repair note;",
         "- after `pilot1_run2` and `c12_pwm_audio_run1`: a field the apply step changes without an answer naming it is",
         "  sent back as a repair note (it was only logged); a quote of fewer than three words no longer states a field.",
         "- after `pilot1_run3` (it stopped: the unasked-change notes used up the apply step's repairs and a checker",
         "  error remained): the last repair is kept for checker errors, and an apply step that never passes keeps the",
         "  valid draft and writes every answer it could not apply as an open assumption carrying the answer.",
         "`pilot1` (run 4) ran with the final harness. `c12_pwm_audio` (run 2) ran before the third change; its apply",
         "step needed no repair, so that change would not have altered it. Each row is a single run.", "",
         "| Spec | Modules | Pass 1 asked / answered / assumptions | Contract and design fields | Stated by a spec quote | "
         "Pass 2 asked / answered / assumptions | Assumptions written | Files valid | Calls | Tokens (in / out) | USD |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rs:
        a, b, l = r["pass1"], r["pass2"], r["llm"]
        L.append(f"| {r['spec']} | {', '.join(r['modules'])} | {a['asked']} / {a['answered']} / {a['defaulted']} | "
                 f"{b['fields']} | {b['stated_in_spec']} | {b['asked']} / {b['answered']} / {b['defaulted']} | "
                 f"{r['assumptions']} | {'yes' if r['valid'] else 'NO'} | {l['calls']} | {l['prompt_tokens']} / "
                 f"{l['completion_tokens']} | {l['usd_provider_reported']:.4f} |")
    for r in rs:
        L += ["", f"## {r['spec']}", "",
              f"Drafter repairs: pass 1 {r['pass1']['drafter_repairs']}, pass 2 {r['pass2']['drafter_repairs']}. "
              f"Quotes that were not in the spec (so the field was asked): {r['bad_quotes']}. Questions over the "
              f"pass 2 budget: {r['pass2_by_limit']}. Fields the drafter changed without being asked: "
              f"{len(r['unasked_changes'])}. Calls by role: {r['calls_by_role']}.", "",
              "Checks against facts fixed before the run:", "", "| Fact | Holds | Found |", "|---|---|---|"]
        for c in r["checks"]:
            L.append(f"| {c['fact']} | {'yes' if c['holds'] else 'no'} | {_short(c['found'], 110)} |")
        L += ["", "Pass 1 questions:", "", "| Question | Result | Settles |", "|---|---|---|"]
        for q in r["questions_pass1"]:
            L.append(f"| {_short(q['q'], 110)} | {q['status']} | {', '.join(q['settles'])} |")
        L += ["", "Pass 2 questions (one per field the spec does not state; the fields each one settles):", "",
              "| Fields | Result | Draft value | Final value |", "|---|---|---|---|"]
        for q in r["questions_pass2"]:
            res = "answered" if q["status"] == "answered" else f"assumption ({q['by']})"
            L.append(f"| {'<br>'.join(q['fields'])} | {res} | {_short(q['draft'], 50)} | {_short(q['final'], 50)} |")
        if r["unasked_changes"]:
            L += ["", "Unasked changes:", ""] + [f"- `{x['field']}`: {_short(x['draft'], 50)} -> {_short(x['final'], 50)}"
                                                   for x in r["unasked_changes"]]
    return "\n".join(L) + "\n"


def main() -> None:
    rs = [summarise(s) for s in SPECS if (HERE / s / "phase0" / "session.json").is_file()]
    failed = [s for s in SPECS if (HERE / s).is_dir() and not (HERE / s / "phase0" / "session.json").is_file()]
    md = markdown(rs)
    for s in failed:
        out = (HERE / s / "stdout.txt").read_text().strip().splitlines()
        calls = json.loads((HERE / s / "phase0" / "replay.json").read_text())
        usd = sum(c.get("cost") or 0 for c in calls)
        md += (f"\n## {s} (stopped, no files written)\n\n{len(calls)} model calls, {usd:.4f} USD provider-reported. "
               f"Last line: `{out[-1][:300]}`\n")
    (HERE / "results.json").write_text(json.dumps(rs, indent=1, default=str) + "\n")
    (HERE / "results.md").write_text(md)
    print(markdown(rs)[:3000])


if __name__ == "__main__":
    main()
