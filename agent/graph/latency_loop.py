"""The latency loop (brief 97): the agent finds the latency-critical path of a design and shortens it, one measured change at a time.

    python -m agent latency <checkout> --arm A1|A0 [--design designs/b96_kr260_10g] [--model M] [--max-iter 3] [--max-usd 2.0] [--out DIR]

``<checkout>`` is a frozen copy of the repository (a git worktree at a fixed commit) that holds the design; the loop edits only
``<design>/rtl/*.sv`` there. Each iteration is one agent visit, then the flow decides:

1. the Designer (a tool-using model) reads the RTL and proposes and applies ONE change, with the tools of its arm;
2. the flow runs the independent bench and the model twin (the design's pytest files, which the agent cannot edit) and reads the
   measured clocks of the wire-to-wire path from the whole-core bench (no model ever produces a number);
3. kept if the bench and twin pass AND the path's clocks fell AND no other measured path got worse; otherwise the files are restored.
   Each iteration is recorded: hypothesis, change (diff), clocks before and after, tests, kept or reverted and why.

Arms: ``A1`` has the new tools (``latency_path``, ``latency_budget``) and the skill text; ``A0`` is the agent as it was (file tools and the
``measure`` gate only; it finds the path from the RTL). Both have ``measure`` and see the same RTL and the same prompt skeleton.
The system prompts and the skill text are private knowledge-bank files (``prompts/latency/``, see ``kb_text``).

Post-route timing and slack are NOT part of this loop's keep rule: a kept change is built afterwards by the flow (``flow/run_vivado.sh``,
under the heavy-slot rule) and the build's slack and utilisation are recorded in the iteration row by ``record_build``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.graph.closure import Workspace, unified_diff
from flow.latency import model as lm

KB_DIR = Path(os.environ.get("FDA_KB_DIR", Path.home() / "Claude_sandbox" / "FPGA_Design_Agent_Knowledge"))
UNREPORTED_COST = 0.05
GATE_TESTS = ["tests/test_b96_pcs_rtl.py", "tests/test_b96_model.py"]       # relative to the design: the independent bench and the twin
READ_DENY = ("latency_stages.yaml",)                                        # the tools' own data: only the tools read it, in both arms


def kb_text(name: str) -> str:
    """A prompt or skill text from the private knowledge-bank checkout (``prompts/<name>``). A missing file is a refusal: the loop never
    runs on invented text (brief 94: new prompts go private by default)."""
    p = KB_DIR / "prompts" / name
    if not p.is_file():
        raise FileNotFoundError(f"private prompt {name!r} not found under {KB_DIR / 'prompts'} (set FDA_KB_DIR to the knowledge-bank checkout)")
    return p.read_text()


# --- the gate: independent bench + twin, and the measured clocks --------------------------------------------------------

def measure(root: Path, design: Path, timeout: int = 1500) -> dict[str, Any]:
    """Run the design's bench and twin in ``root``; returns {tests_pass, failure, ttt, echo, trace}. The clocks come from the
    whole-core bench's own JSON (``flow.latency.model.run_trace``), never from a model."""
    st = lm.load_stages(design)
    out = root / "build" / "latency" / "core_sim.json"
    t0 = time.monotonic()
    try:
        rel = design.relative_to(root)
        lm.run_trace(design, st, out=out, root=root, timeout=timeout, entry=str(rel / GATE_TESTS[0]),
                     extra=[str(rel / t) for t in GATE_TESTS[1:]])
    except lm.LatencyError as e:
        return {"tests_pass": False, "failure": str(e)[-1800:], "seconds": round(time.monotonic() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"tests_pass": False, "failure": "the bench timed out", "seconds": round(time.monotonic() - t0, 1)}
    core = json.loads(out.read_text())
    lp = lm.latency_path(design, core, None, "tick_to_trade", st)
    ec = lm.latency_path(design, core, None, "echo", st)
    return {"tests_pass": True, "ttt_clocks": lp["total_clocks"], "echo_clocks": ec["total_clocks"], "reconciled_before_edit": lp["reconciled"],
            "core": core.get("tick_to_trade_digital_sim", {}), "seconds": round(time.monotonic() - t0, 1)}


def judge(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, str]:
    """Keep rule (the flow's, not a model's): the bench and twin pass, the path got shorter, the echo did not get longer."""
    if not after.get("tests_pass"):
        return False, "the independent bench or the model twin failed"
    if after["ttt_clocks"] >= before["ttt_clocks"]:
        return False, f"tick-to-trade did not fall ({before['ttt_clocks']} -> {after['ttt_clocks']} clocks)"
    if after["echo_clocks"] > before["echo_clocks"]:
        return False, f"the echo path got longer ({before['echo_clocks']} -> {after['echo_clocks']} clocks)"
    return True, f"tick-to-trade {before['ttt_clocks']} -> {after['ttt_clocks']} clocks, bench and twin pass"


# --- the Designer's tools --------------------------------------------------------------------------------------------

def _oai(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}


REG_TOOLS = ("read_file", "list_files", "write_file")
LAT_TOOLS = ("latency_path", "latency_budget")
MEASURE_SPEC = _oai("measure", "Run the independent bench and the model twin on the current RTL and return pass/fail and the measured clocks "
                    "of the tick-to-trade path and the echo path. Takes a few minutes; at most three calls per visit.",
                    {"type": "object", "properties": {}, "additionalProperties": False})


def tool_specs(arm: str) -> list[dict[str, Any]]:
    from agent.core import tools as _t  # noqa: F401  (registers)
    from agent.core.registry import TOOLS
    names = list(REG_TOOLS) + (list(LAT_TOOLS) if arm == "A1" else [])
    return [_oai(n, TOOLS[n].describe(), TOOLS[n].schema()) for n in names] + [MEASURE_SPEC]


@dataclass
class Visit:
    arm: str
    client: Callable
    session: Any
    root: Path
    design: Path
    max_turns: int = 16
    max_measures: int = 3
    log: list = field(default_factory=list)
    usd: float = 0.0
    tokens: int = 0
    measures: int = 0
    tool_counts: dict = field(default_factory=dict)

    def _dispatch(self, name: str, args: dict[str, Any], current: dict[str, Any]) -> str:
        from agent.core.registry import dispatch
        self.tool_counts[name] = self.tool_counts.get(name, 0) + 1
        if name == "measure":
            if self.measures >= self.max_measures:
                return "refused: measure was already used three times this visit"
            self.measures += 1
            m = measure(self.root, self.design)
            return json.dumps({k: v for k, v in m.items() if k != "core"})
        if name == "write_file":
            p = str(args.get("path", ""))
            if not (p.startswith("rtl/") and p.endswith(".sv") and "/" not in p[4:]):
                return "refused: only rtl/*.sv may be written in this loop"
        if name in ("read_file", "list_files") and any(d in str(args.get("path", "")) for d in READ_DENY):
            return "refused: that file is the tools' own data"
        if name in ("latency_path", "latency_budget") and self.arm != "A1":
            return "refused: no such tool"
        r = dispatch(self.session, name, args)
        out = str(r.get("output", ""))
        if name == "list_files":
            out = "\n".join(l for l in out.splitlines() if not any(d in l for d in READ_DENY))
        return out[:12000]

    def run(self, system: str, user: str, current: dict[str, Any]) -> dict[str, Any]:
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tools = tool_specs(self.arm)
        note, ended = "", "turns"
        for turn in range(self.max_turns):
            rep = self.client(msgs, tools)
            self.usd += rep.cost if rep.cost is not None else UNREPORTED_COST
            self.tokens += rep.prompt_tokens + rep.completion_tokens
            self.log.append({"turn": turn, "cost": rep.cost, "tokens": rep.prompt_tokens + rep.completion_tokens,
                             "tools": [c["name"] for c in rep.tool_calls]})
            am: dict[str, Any] = {"role": "assistant", "content": rep.text or ""}
            if rep.tool_calls:
                am["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                    for c in rep.tool_calls]
            msgs.append(am)
            for line in (rep.text or "").splitlines():
                if line.startswith("NOTE:"):
                    note = line[5:].strip()
            if not rep.tool_calls:
                ended = "done"
                break
            for c in rep.tool_calls:
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": self._dispatch(c["name"], c["args"], current)})
        return {"note": note, "ended": ended, "turns": len(self.log), "messages": msgs}


def task_text(history: list[str], current: dict[str, Any]) -> str:
    t = ("Design: designs/b96_kr260_10g (a 10GBASE-R PCS and MAC with a mock trading path on a Kria KR260). The clocks of the design's "
         f"wire-to-wire path today (measured by the bench): tick-to-trade {current['ttt_clocks']} clocks (price word captured on the receive GT "
         f"port to the order's start block on the transmit GT port), echo {current['echo_clocks']} clocks. The user clocks are 161.1328125 MHz "
         "(6.2058 ns). Reduce the tick-to-trade clocks. The GT's own latency is not in the simulation and not yours to change here.")
    if history:
        t += "\n\nEarlier visits (do not repeat a reverted change):\n" + "\n".join(history[-6:])
    return t


# --- the loop --------------------------------------------------------------------------------------------------------

@dataclass
class LatencyLoop:
    root: Path
    design: Path
    arm: str
    client: Callable
    out: Path
    max_iter: int = 3
    max_usd: float = 2.0
    max_turns: int = 16
    rows: list[dict[str, Any]] = field(default_factory=list)
    usd: float = 0.0

    def _rec(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        self.out.mkdir(parents=True, exist_ok=True)
        with (self.out / "history.jsonl").open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def run(self) -> dict[str, Any]:
        from agent.core.session import Session
        from agent.graph.roles import role_session
        ws = Workspace(self.design)
        sys_prompt = kb_text("latency/loop_system_a1.md" if self.arm == "A1" else "latency/loop_system_a0.md")
        s = role_session(Session(design=self.design, root=self.root, board="kr260", stage="rtl"), "rtl")
        base = measure(self.root, self.design)
        self._rec({"iteration": 0, "event": "baseline", **{k: v for k, v in base.items() if k != "core"}})
        if not base.get("tests_pass"):
            return {"arm": self.arm, "stopped": "the baseline fails its own bench", "baseline": base}
        best, history, stall = base, [], 0
        for it in range(1, self.max_iter + 1):
            if self.usd >= self.max_usd:
                self._rec({"iteration": it, "event": "stop", "reason": "cost cap"})
                break
            snap = ws.read()
            v = Visit(self.arm, self.client, s, self.root, self.design, self.max_turns)
            t0 = time.monotonic()
            try:
                res = v.run(sys_prompt, task_text(history, best), best)
            except Exception as e:                                   # a model or tool failure ends the visit, never the record
                res = {"note": "", "ended": f"error:{type(e).__name__}: {str(e)[:200]}", "turns": len(v.log), "messages": []}
            self.usd += v.usd
            after_files = ws.read()
            diff = unified_diff(snap, after_files)
            (self.out / f"iter{it:02d}.diff").write_text(diff)
            (self.out / f"iter{it:02d}.messages.json").write_text(json.dumps(res["messages"], indent=1))
            row = {"iteration": it, "event": "visit", "arm": self.arm, "hypothesis_note": res["note"], "ended": res["ended"],
                   "turns": res["turns"], "tools": v.tool_counts, "usd": round(v.usd, 6), "tokens": v.tokens,
                   "wall_s": round(time.monotonic() - t0, 1), "clocks_before": best["ttt_clocks"], "echo_before": best["echo_clocks"],
                   "files_changed": sorted(k for k in after_files if after_files.get(k) != snap.get(k)),
                   "diff_sha": hashlib.sha256(diff.encode()).hexdigest()[:12]}
            if not diff:
                row.update(kept=False, reason="no change made")
                stall += 1
            else:
                after = measure(self.root, self.design)
                ok, why = judge(best, after)
                row.update(kept=ok, reason=why, clocks_after=after.get("ttt_clocks"), echo_after=after.get("echo_clocks"),
                           tests_pass=after.get("tests_pass"), failure=(after.get("failure") or "")[-600:] or None)
                if ok:
                    best, stall = after, 0
                    (self.out / f"iter{it:02d}.kept.sv.tar").write_bytes(subprocess.run(
                        ["tar", "-C", str(self.design), "-cf", "-", "rtl"], capture_output=True).stdout)
                else:
                    ws.restore(snap)
                    stall += 1
            history.append(f"visit {it}: {res['note'] or '(no note)'} -> {'KEPT' if row.get('kept') else 'REVERTED'}: {row['reason']}")
            self._rec(row)
            if stall >= 2:
                break
        summary = {"arm": self.arm, "baseline_clocks": base["ttt_clocks"], "final_clocks": best["ttt_clocks"], "usd": round(self.usd, 6),
                   "kept": sum(1 for r in self.rows if r.get("kept")), "visits": sum(1 for r in self.rows if r.get("event") == "visit"),
                   "final_rtl_sha": rtl_sha(self.design)}
        (self.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
        return summary


def rtl_sha(design: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((design / "rtl").glob("*.sv")):
        h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()[:16]


def latency_cmd(a: argparse.Namespace) -> int:
    from agent.access import require_or_exit
    from agent.graph.llm import OpenRouterClient, Recorder, Replay
    require_or_exit("latency")
    root = a.checkout.resolve()
    design = (root / a.design).resolve()
    out = (a.out or root / "results" / "b97" / "runs" / f"{a.arm}_{int(time.time())}").resolve()
    if a.replay:
        client = Replay(Path(a.replay))
    else:
        client = Recorder(OpenRouterClient(a.model), out / "llm_calls.json")
    loop = LatencyLoop(root, design, a.arm, client, out, a.max_iter, a.max_usd, a.max_turns)
    print(json.dumps(loop.run(), indent=1))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("latency", help="brief 97: the latency loop on a frozen checkout (arm A1 = latency tools and skill text, A0 = as before)")
    p.add_argument("checkout", type=Path, help="a git worktree of the repo at a fixed commit; only <design>/rtl/*.sv is edited")
    p.add_argument("--arm", choices=["A0", "A1"], required=True)
    p.add_argument("--design", default="designs/b96_kr260_10g")
    p.add_argument("--model", default="openai/gpt-6-luna")
    p.add_argument("--max-iter", type=int, default=3)
    p.add_argument("--max-turns", type=int, default=16)
    p.add_argument("--max-usd", type=float, default=2.0)
    p.add_argument("--out", type=Path)
    p.add_argument("--replay", help="LLM replay fixture (no network)")
