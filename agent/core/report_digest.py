"""Brief 42 H9: typed, deterministic digests of the reports and logs the agent reads. No model inside.

``digest(name, text, level, focus)`` returns ``{"kind", "verdict", "numbers", "rows", "output"}``. ``level``:

- ``summary``: the verdict and key numbers (a seeded fault shows here);
- ``standard``: plus the top 5 paths and one example per rule ID;
- ``detail``: plus the top 20 paths and every rule instance, as rows.

``focus`` is a path index (``3``), a rule ID (``TIMING-16``), a clock pair (``clk_a,clk_b``) or a test name. The text ends
with the report's path. The parsers are the ones the gates use (``flow/gates.py``); a type with no parser (simulation
output, lint, vivado.log) has a regular-expression digester here; anything else gets a head and tail.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from flow import gates

LEVELS = ("summary", "standard", "detail")
TOP = {"summary": 0, "standard": 5, "detail": 20}


def kind_of(name: str, text: str) -> str:
    n = name.lower()
    if "timing_summary" in n or "Design Timing Summary" in text:
        return "timing"
    if "utilization" in n or "Slice LUTs" in text and "Utilization" in text:
        return "utilization"
    if "methodology" in n or "Report Methodology" in text:
        return "methodology"
    if "drc" in n or "Report DRC" in text:
        return "drc"
    if "cdc" in n or "CDC Report" in text:
        return "cdc"
    if "exception" in n:
        return "exceptions"
    if "power" in n or "Total On-Chip Power" in text:
        return "power"
    if n.endswith("vivado.log") or "vivado.log" in n or "# Vivado" in text[:400]:
        return "vivado_log"
    if "lint" in n or re.search(r"^%(Warning|Error)", text, re.M):
        return "lint"
    if re.search(r"\b\d+ (passed|failed)\b|cocotb\.regression|FDA_HANG|\[first failure\]", text):
        return "simulation"
    return "generic"


def _rule_instances(text: str) -> list[dict[str, Any]]:
    """The REPORT DETAILS blocks of report_methodology / report_drc: ``RULE#n Severity`` then the description."""
    out = []
    for m in re.finditer(r"^([A-Z][A-Z0-9_]*-\d+)#(\d+)\s+([A-Za-z ]+?)\s*\n(.*?)(?=\n\n|\Z)", text, re.M | re.S):
        body = " ".join(x.strip() for x in m.group(4).splitlines() if x.strip())
        out.append({"rule": m.group(1), "n": int(m.group(2)), "severity": m.group(3), "text": body[:400]})
    return out


def _paths(text: str) -> list[dict[str, Any]]:
    out = []
    for m in re.finditer(r"Slack \((MET|VIOLATED)\)\s*:\s*(-?[0-9.]+)ns[^\n]*\n(.*?)(?=\n\s*Slack \(|\Z)", text, re.S):
        blk = m.group(3)
        g = lambda k: (re.search(rf"^\s*{k}:\s*(\S+)", blk, re.M) or [None, None])[1]    # noqa: E731
        out.append({"slack_ns": float(m.group(2)), "met": m.group(1) == "MET", "source": g("Source"),
                    "destination": g("Destination"), "path_group": g("Path Group")})
    return sorted(out, key=lambda p: p["slack_ns"])


def _timing(text, level, focus):
    t = gates.parse_timing_summary(text)
    verdict = "timing met" if t["timing_met"] else "TIMING NOT MET"
    nums = {k: t[k] for k in ("wns_ns", "tns_ns", "tns_failing_endpoints", "whs_ns", "ths_failing_endpoints", "wpws_ns")}
    rows = _paths(text)
    if focus and focus.isdigit():
        rows = rows[int(focus) - 1:int(focus)]
    elif level != "summary":
        rows = rows[:TOP[level]]
    else:
        rows = []
    return verdict, nums, rows


def _rules(text, level, focus, kind):
    table = gates.parse_rule_table(text)
    sev = {}
    for r in table:
        sev[r["severity"]] = sev.get(r["severity"], 0) + r["count"]
    crit = sum(c for s, c in sev.items() if s.lower().startswith("critical") or s.lower() == "error")
    verdict = f"{kind}: {crit} critical or error, {sum(sev.values())} checks in {len(table)} rules"
    nums = {"by_severity": sev, "rules": [{k: r[k] for k in ("rule", "severity", "count")} for r in table]}
    inst = _rule_instances(text)
    if focus:
        rows = [i for i in inst if i["rule"] == focus]
    elif level == "standard":
        seen, rows = set(), []
        for i in inst:
            if i["rule"] not in seen:
                seen.add(i["rule"])
                rows.append(i)
    elif level == "detail":
        rows = inst
    else:
        rows = []
    return verdict, nums, rows


def _cdc(text, level, focus):
    c = gates.parse_cdc(text)
    n_crit = sum(r["count"] for r in c["rules"] if r["severity"] == "Critical")
    verdict = "all CDC paths safely timed" if c["safely_timed"] else f"CDC: {n_crit} critical crossings"
    rows = c["rules"] if level != "summary" or focus else []
    if focus:
        want = {x.strip() for x in focus.split(",")}
        rows = [r for r in c["rules"] if r["rule"] in want] or [
            {"line": ln.strip()} for ln in text.splitlines() if all(w in ln for w in want)][:TOP["detail"]]
    return verdict, {"critical": n_crit, "rules": len(c["rules"])}, rows


def _power(text, level, focus):
    p = gates.parse_report_power(text)
    env = gates.parse_power_environment(text)
    return (f"{p['total_w']} W total on chip, junction {env.get('junction_c')} C",
            {**{k: p.get(k) for k in ("total_w", "dynamic_w", "static_w", "confidence")}, "junction_c": env.get("junction_c")}, [])


def _utilization(text, level, focus):
    u = gates.parse_utilization(text)
    pct = {k: round(100 * u[k] / u[f"{k}_available"], 1) for k in u if f"{k}_available" in u and u[f"{k}_available"]}
    top = max(pct.items(), key=lambda kv: kv[1]) if pct else None
    return (f"highest use {top[0]} {top[1]}%" if top else "utilization"), {**u, "percent": pct}, []


def _vivado_log(text, level, focus):
    lines = text.splitlines()
    sev = {k: [ln for ln in lines if ln.startswith(k)] for k in ("ERROR:", "CRITICAL WARNING:", "WARNING:")}
    nums = {k.rstrip(":").lower().replace(" ", "_") + "s": len(v) for k, v in sev.items()}
    n = TOP[level] if level != "summary" else 3
    rows = [{"line": ln[:300]} for ln in (sev["ERROR:"][:n] + sev["CRITICAL WARNING:"][:n])]
    if level == "detail":
        rows += [{"line": ln[:300]} for ln in sev["WARNING:"][:20]]
    return ("vivado.log: " + (f"{nums['errors']} errors" if nums["errors"] else "no errors")
            + f", {nums['critical_warnings']} critical warnings"), nums, rows


def _simulation(text, level, focus):
    m = re.findall(r"(\d+) (passed|failed|error)", text)
    counts = {k: int(v) for v, k in m} if m else {}
    hung = re.search(r"\[simulation hung\][^\n]*", text)
    ff = re.search(r"\[first failure\][^\n]*\n(.*?)\[end first failure\]", text, re.S)
    fails = sorted(set(re.findall(r"^FAILED (\S+)", text, re.M)) | set(re.findall(r"\*\* (\S+)\s+FAIL\b", text)))
    verdict = (hung.group(0) if hung else
               "simulation passed" if counts.get("passed") and not counts.get("failed") and not counts.get("error")
               else "simulation FAILED" if counts.get("failed") or counts.get("error") or ff else "simulation: no verdict found")
    nums = {**counts, "failing_tests": fails[:20]}
    rows = []
    if ff:
        rows.append({"first_failure": ff.group(1).strip()[:1500 if level != "summary" else 600]})
    if focus:
        rows = [{"line": ln[:300]} for ln in text.splitlines() if focus in ln][:TOP["detail"]]
    elif level == "detail":
        rows += [{"line": ln[:300]} for ln in text.splitlines() if re.search(r"\b(ERROR|FAIL|Assertion)", ln)][:40]
    return verdict, nums, rows


def _lint(text, level, focus):
    rule = {}
    for ln in text.splitlines():
        m = re.match(r"%(Warning|Error)(?:-([A-Z0-9_]+))?:\s*(.*)", ln) or re.match(r"\S+:\d+: (warning|error): (.*)", ln)
        if m:
            sev, key, msg = (m.group(1), m.group(2) or "error", m.group(3)) if len(m.groups()) == 3 else (m.group(1), "iverilog", m.group(2))
            rule.setdefault(key, []).append({"severity": sev, "line": ln[:300]})
    errs = sum(1 for v in rule.values() for x in v if x["severity"].lower() == "error")
    verdict = f"lint: {errs} errors, {sum(len(v) for v in rule.values()) - errs} warnings in {len(rule)} rules"
    nums = {k: len(v) for k, v in rule.items()}
    if focus:
        rows = rule.get(focus, [])
    elif level == "standard":
        rows = [v[0] for v in rule.values()]
    elif level == "detail":
        rows = [x for v in rule.values() for x in v]
    else:
        rows = []
    return verdict, nums, rows


def _generic(text, level, focus):
    lines = text.splitlines()
    n = {"summary": 5, "standard": 15, "detail": 40}[level]
    rows = [{"line": ln[:300]} for ln in lines[:n]] + ([{"line": "..."}] if len(lines) > 2 * n else []) + \
           [{"line": ln[:300]} for ln in lines[-n:] if len(lines) > n]
    return f"{len(lines)} lines, no typed digest for this report", {"lines": len(lines)}, rows


_DIGESTERS = {"timing": _timing, "utilization": _utilization, "cdc": _cdc, "power": _power, "vivado_log": _vivado_log,
              "simulation": _simulation, "lint": _lint, "generic": _generic, "exceptions": _generic}


def digest(name: str, text: str, level: str = "summary", focus: str | None = None, path: str | None = None) -> dict[str, Any]:
    assert level in LEVELS, level
    kind = kind_of(name, text)
    try:
        if kind in ("methodology", "drc"):
            verdict, nums, rows = _rules(text, level, focus, kind)
        else:
            verdict, nums, rows = _DIGESTERS[kind](text, level, focus)
    except ValueError as e:                      # a report the parser does not know: say so and fall back
        kind = "generic"
        verdict, nums, rows = _generic(text, level, focus)
        verdict += f" (typed parser refused: {e})"
    rep = path or name
    out = [f"[{kind} digest, level {level}{', focus ' + focus if focus else ''}] {verdict}", json.dumps(nums)]
    out += [json.dumps(r) for r in rows]
    out.append(f"report: {rep}")
    return {"kind": kind, "verdict": verdict, "numbers": nums, "rows": rows, "report": rep, "output": "\n".join(out)}


COMPACT_CHARS = 4000


def compact_result(res: dict[str, Any], tool: str, design: Path, seq: int, readable: bool, digest_callable: bool = False) -> str:
    """H9: a flow tool's large result as its typed summary digest plus the path of the full result (written to
    ``build/tool_results``; named only when the role can read it). The note names `report_digest` only when this role can call
    it (``digest_callable``): in stage 2 no role can, so the note must not point at it (review fix)."""
    text = json.dumps(res)
    if len(text) <= COMPACT_CHARS:
        return text
    d = Path(design) / "build" / "tool_results"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{seq:03d}_{tool}.json"
    f.write_text(text)
    out = str(res.get("output", ""))
    dg = digest(f"{tool}.txt", out, "summary", None, path=f"/build/tool_results/{f.name}" if readable else f"{tool} output (full text not readable by this role)")
    small = {k: v for k, v in res.items() if k != "output" and len(json.dumps(v)) <= 1500}
    g = res.get("gates")
    if isinstance(g, dict):                                  # the gates result: which gates failed, from the structured data
        gg = g.get("gates") if isinstance(g.get("gates"), dict) else g
        small["gate_summary"] = {"pass": g.get("pass"), "first_failed_stage": g.get("first_failed_stage"),
                                 "failed_gates": [k for k, v in gg.items() if v is False][:40], "n_gates": len(gg)}
        small.pop("gates", None)
    return json.dumps({**small, "digest": dg["output"],
                       "note": ("Typed summary of the result; call report_digest (standard or detail) or read the path for more."
                                if digest_callable else
                                "Typed summary of the result; read the path for the full result." if readable else
                                "Typed summary of the result; the full text is not readable by this role: run the tool again "
                                "with a narrower scope for more.")})
