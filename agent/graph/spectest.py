"""Independent spec-only test generation (brief 08f, `eval-2`).

Every escape found so far has one cause: the agent's tests are written in the same context that wrote the design, so
they repeat its misreading (c10 DDS run 1: the DATA word packed wrongly in the model, the RTL and the bench alike; tiny
CNN: eight-bit weights sign-extended from bit 31 in the model and the RTL, and every internal gate passed). This module adds a
second, separate pair of eyes.

- **The spec-test role** is one headless Claude Code call of its own (no tools, no MCP, no design directory). It is
  given only: ``spec.md``, the interview's answered and defaulted questions (``resolved_questions`` of ``spec.yaml``,
  nothing else of ``spec.yaml``), the board pack (``board.yaml`` and the master XDC's port names), the task's ``data/``
  files, and, for a design with the test shell, the shell's protocol and UART bus model. Never the RTL, the agent's
  ``model.py``, its tests or its architecture notes. It returns its own reference model (``spectest/spec_ref.py``) and a
  cocotb acceptance bench (``spectest/spec_bench.py``).
- **The gate** runs after V2/V3 pass. The harness (not any model) writes the pytest entry and runs the bench against the
  design's RTL. A pass is recorded. A failure goes to a short **triage** step that sees both benches' checks and the spec
  text, never the RTL, and decides ``design_wrong`` (back to the RTL role with the evidence) or ``bench_wrong`` (the
  spec-test role repairs its bench once). ``max_loops`` limits the design_wrong round trips per run; past it the result is
  recorded as ``unresolved`` and does not block.
- **The record** is ``build/spectest/state.json`` in the design directory (fired / passed / caught a bug / bench repaired),
  read by ``tools/run_record.py``.

The model calls are plain callables ``llm(system, user) -> text``, so the unit tests and the offline replay drive the same
code with stubs or the real thing. Nothing here runs unless ``Config.spec_tests`` is set, and no other request path changes
(``agent/tests/test_08f_golden_requests.py``)."""

from __future__ import annotations

import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = "spectest"
STATE_REL = ("build", "spectest", "state.json")
FILES_OK = re.compile(r"^spectest/[A-Za-z0-9_]+\.(py|md)$")
ENTRY = "test_spec_entry.py"            # written by the harness, never by a model
DEFAULT_MAX_LOOPS = 2                    # design_wrong round trips per run (provisional; see docs/verification.md)
DATA_INLINE_BYTES = 40_000
SIM_TIMEOUT_S = 1800

LLM = Callable[[str, str], str]

# --- what the role is given -----------------------------------------------------------------------------------------


def interview_text(design: Path) -> str:
    """The interview as the requester answered it: ``resolved_questions`` of spec.yaml only (never the rest of the agent's
    spec.yaml, which is its own reading of the request). A defaulted question is the agent's proposal, so it is labelled
    as not confirmed."""
    try:
        spec = yaml.safe_load((design / "spec.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return "(no interview record)"
    rows = []
    for i, q in enumerate(spec.get("resolved_questions") or [], 1):
        if not isinstance(q, dict):
            continue
        status = str(q.get("status") or "")
        tag = ("ANSWERED by the requester" if status == "answered"
               else "NOT CONFIRMED: the requester gave no answer, this is the agent's own proposal, not a requirement")
        rows.append(f"Q{i}. {str(q.get('question', '')).strip()}\n    [{tag}]\n    {str(q.get('answer', '')).strip()}")
    return "\n\n".join(rows) or "(the interview asked no questions)"


_XDC_PORT = re.compile(r"get_ports\s*\{\s*([A-Za-z_0-9\[\]]+)\s*\}")


def board_pack_text(board: str, boards_root: Path | None = None) -> str:
    """board.yaml plus the top-level port names of the board's master XDC (the names a bench drives)."""
    d = (boards_root or ROOT / "boards") / board
    parts = []
    try:
        parts.append("board.yaml:\n" + (d / "board.yaml").read_text())
    except OSError:
        pass
    xdc = next(iter(sorted(d.glob("*Master.xdc"))), None)
    if xdc is not None:
        names: list[str] = []
        for line in xdc.read_text().splitlines():
            m = _XDC_PORT.search(line)
            if m and m.group(1) not in names:
                names.append(m.group(1))
        parts.append("Top-level port names of the board's master XDC (a request's port names follow these; a bus is "
                     "declared once, as NAME[n:0]):\n" + ", ".join(names))
    return "\n\n".join(parts) or "(no board pack)"


def shell_ref_text(root: Path | None = None) -> str:
    """For a design with the test shell: the frame protocol and the UART bus model a bench uses to reach its registers."""
    r = root or ROOT
    out = []
    for rel in ("shell/PROTOCOL.md", "shell/host/protocol.py", "shell/tests/uart_bfm.py"):
        try:
            out.append(f"--- {rel} ---\n{(r / rel).read_text()}")
        except OSError:
            pass
    return "\n".join(out)


def data_text(design: Path) -> str:
    d = design / "data"
    if not d.is_dir():
        return "(no data files)"
    out = []
    for p in sorted(x for x in d.rglob("*") if x.is_file()):
        rel = p.relative_to(design)
        size = p.stat().st_size
        if size <= DATA_INLINE_BYTES:
            out.append(f"--- {rel} ({size} bytes) ---\n{p.read_text(errors='replace')}")
        else:
            head = "\n".join(p.read_text(errors="replace").splitlines()[:20])
            out.append(f"--- {rel} ({size} bytes, first 20 lines; read the whole file at run time) ---\n{head}")
    return "\n".join(out) or "(no data files)"


ROLE_SYSTEM = """You write the independent spec tests for an FPGA design on a Xilinx board. You work from the request alone.
You have not seen, and must not ask for, the design's RTL, the Modeller's reference model or the Verifier's tests: those
may share a misreading of the request, and your job is to be the second reading.

Write two Python files:
1. spectest/spec_ref.py: your own reference model of the design's externally observable behaviour, from the request. Pure Python.
2. spectest/spec_bench.py: a cocotb acceptance bench that drives the top module's ports and compares with spec_ref.py.

Aim at what the Designer can misread and a self-written test would repeat: bit encodings and field positions, widths,
signedness (two's complement against unsigned, which bit is the sign, sign extension, truncation), rounding and saturation
rules, register offsets, reset values and access, byte and bit order on serial lines, and timing promises (latency, periods) in
clock cycles. Work every expected value out from the request's own rules, and from the data files read at run time; never
paste numbers you cannot justify from the request.

Rules.
- Test only what the request or an ANSWERED question states. A question marked NOT CONFIRMED is the Clarifier's guess: do not
  test it unless the request says the same. If the request is silent on a point, do not test it.
- Read an ambiguous sentence the way a careful engineer reading the request cold would, and say in a comment which sentence
  each check comes from.
- Top-level ports are the board's master-XDC names (list below); the top-level module name and parameters are in the request
  (the harness builds the top it names). Put the parameters your bench overrides (for example a baud divider or a debounce
  count, shrunk for simulation) in a module-level dict `PARAMS = {...}`; optional `SEEDS = (1, 2)` (default one seed).
- spec_bench.py: `import cocotb`, `from cocotb.clock import Clock`, the cocotb triggers; tests are `@cocotb.test()` async
  functions. Import your model with `import spec_ref` (the same directory). The task's data files are at
  `Path(__file__).resolve().parents[1] / "data" / "<name>"`. Drive the clock named in the request (CLK100MHZ unless it says
  otherwise) and the reset (CPU_RESETN is active low) yourself. Keep the simulation short: at most a few thousand clock cycles per
  check where you can shrink a divider, and no more than ten checks in all.
- Give each test a name that says what observable behaviour it checks, and make each assertion message say what was expected, in
  the request's own terms, and what the design did.

Reply with the two files and nothing else, in exactly this form:
=== FILE: spectest/spec_ref.py ===
<file text>
=== END FILE ===
=== FILE: spectest/spec_bench.py ===
<file text>
=== END FILE ===
"""


def role_prompt(design: Path, board: str, root: Path | None = None) -> str:
    """The first user message of the spec-test role: only the inputs listed in the module docstring."""
    from flow import srcorder
    shell = "" if srcorder.no_shell(design) else (
        "\n\nThis design embeds the test shell (a UART register window). Reach its registers as a host does, through the shell's "
        "UART; the protocol and the UART bus model (`from shell.tests.uart_bfm import UartBfm`, `from shell.host import "
        "protocol as p`) are:\n" + shell_ref_text(root))
    nos = ("\n\nThis design does NOT embed the test shell: its pins are the board's, and your bench drives them directly "
           "(a serial line is bit-banged at the clocks-per-bit you set in PARAMS).") if srcorder.no_shell(design) else ""
    spec_md = (design / "spec.md").read_text() if (design / "spec.md").is_file() else "(no spec.md)"
    return (f"REQUEST (spec.md):\n{spec_md}\n\nTHE REQUESTER'S ANSWERS TO THE CLARIFYING QUESTIONS:\n{interview_text(design)}\n\n"
            f"BOARD PACK:\n{board_pack_text(board)}\n\nDATA FILES:\n{data_text(design)}{shell}{nos}\n")


def repair_prompt(design: Path, board: str, reason: str, evidence: str, root: Path | None = None) -> str:
    """The bench repair: the same inputs, the bench's own earlier output, and what the triage found wrong with it."""
    cur = "\n".join(f"=== FILE: spectest/{n} ===\n{(design / SPEC_DIR / n).read_text()}\n=== END FILE ==="
                    for n in ("spec_ref.py", "spec_bench.py") if (design / SPEC_DIR / n).is_file())
    return (role_prompt(design, board, root) + f"\n\nYOUR EARLIER BENCH:\n{cur}\n\nIt failed against the design, and a "
            f"reviewer who read the request judged the bench wrong: {reason}\nThe failing checks:\n{evidence[:3000]}\n"
            "Correct only what the request does not support, keep the rest, and reply with both files in the same form.")


def parse_files(text: str) -> dict[str, str]:
    """The ``=== FILE: path ===`` blocks of a reply; paths outside ``spectest/`` (or not .py/.md) are dropped."""
    out: dict[str, str] = {}
    for m in re.finditer(r"=== FILE: (\S+) ===\n(.*?)\n=== END FILE ===", text, re.S):
        rel = m.group(1).strip()
        if FILES_OK.match(rel):
            body = re.sub(r"^```[a-z]*\n|\n```$", "", m.group(2).strip("\n"))
            out[rel] = body + "\n"
    return out


def static_problems(design: Path) -> list[str]:
    """Cheap checks before the bench ever sees the RTL: the files exist, compile, and the bench has tests and no import of the
    Designer's, Modeller's or Verifier's files."""
    d = design / SPEC_DIR
    bad = []
    for n in ("spec_ref.py", "spec_bench.py"):
        if not (d / n).is_file():
            bad.append(f"spectest/{n} is missing")
            continue
        try:
            py_compile.compile(str(d / n), doraise=True, cfile=str(Path(tempfile.gettempdir()) / f"_spectest_{n}c"))
        except py_compile.PyCompileError as e:
            bad.append(f"spectest/{n} does not compile: {str(e)[-400:]}")
    b = d / "spec_bench.py"
    if b.is_file():
        t = b.read_text()
        if "@cocotb.test" not in t:
            bad.append("spec_bench.py has no @cocotb.test() function")
        if re.search(r"^\s*(import|from)\s+model\b", t, re.M):
            bad.append("spec_bench.py imports `model`: use your own spec_ref.py")
        if "PARAMS" not in t:
            bad.append("spec_bench.py has no module-level PARAMS dict (use {} if you override nothing)")
    return bad


def write_files(design: Path, files: dict[str, str]) -> list[str]:
    d = design / SPEC_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text("")
    for rel, body in files.items():
        (design / rel).write_text(body)
    return sorted(files)


# --- running the bench ----------------------------------------------------------------------------------------------

ENTRY_TEMPLATE = '''"""Harness-written entry for the independent spec-test bench (spectest/spec_bench.py). No model wrote this file."""
import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
for _p in [DESIGN_DIR, *DESIGN_DIR.parents]:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(Path(__file__).resolve().parent))        # spec_bench, spec_ref: this directory only, never the design's model.py

import yaml  # noqa: E402
from flow import cocotb_run, srcorder  # noqa: E402

import spec_bench  # noqa: E402


def test_spec_bench():
    top = yaml.safe_load((DESIGN_DIR / "build.yaml").read_text())["top"]
    own = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    sources = own if srcorder.no_shell(DESIGN_DIR) else cocotb_run.SHELL_RTL + own
    for seed in getattr(spec_bench, "SEEDS", (1,)):
        cocotb_run.run("spectest", top, sources, "spec_bench", DESIGN_DIR / "spectest",
                       parameters=dict(getattr(spec_bench, "PARAMS", {}) or {}), seed=seed,
                       build_root=DESIGN_DIR / "build" / "spectest" / "sim")
'''


def parse_results(design: Path) -> dict[str, Any]:
    """Per-test pass/fail and failure messages from cocotb's results.xml (never from a model's words)."""
    xml = design / "build" / "spectest" / "sim" / "spectest" / "results.xml"
    passed, failing = [], []
    if xml.is_file():
        for tc in ET.parse(xml).getroot().iter("testcase"):
            f = tc.find("failure")
            if f is None:
                f = tc.find("error")
            if f is None:
                passed.append(tc.get("name", "?"))
            else:
                failing.append({"test": tc.get("name", "?"), "message": (f.get("message") or f.text or "").strip()[:600]})
    return {"passed": passed, "failing": failing}


def run_bench(design: Path, runner: Any, sim: str = "icarus", timeout: float = SIM_TIMEOUT_S, py: str | None = None) -> dict[str, Any]:
    """Run ``spectest/spec_bench.py`` against the design's RTL. ``runner`` has the Runner interface of ``agent.core.runner``."""
    import sys
    entry = design / SPEC_DIR / ENTRY
    entry.write_text(ENTRY_TEMPLATE)
    shutil.rmtree(design / "build" / "spectest" / "sim", ignore_errors=True)
    rel = entry.relative_to(ROOT) if entry.is_relative_to(ROOT) else entry
    r = runner.run("spectest", [py or sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(rel)], ROOT,
                   {"SIM": sim}, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    res = parse_results(design)
    if res["failing"] and not any(f["message"] for f in res["failing"]):       # cocotb puts the assertion text in the simulator log
        from flow.cocotb_run import failure_excerpt
        ex = failure_excerpt(design / "build" / "spectest" / "sim" / "spectest" / "sim.log", 1800)
        for f in res["failing"]:
            f["message"] = ex
    elaborated = bool(res["passed"] or res["failing"])
    return {"ok": r.returncode == 0 and elaborated and not res["failing"], "returncode": r.returncode, "seconds": r.seconds,
            "built": elaborated, "passed": res["passed"], "failing": res["failing"], "text": out[-3500:]}


def failing_checks_text(res: dict[str, Any]) -> str:
    if res.get("failing"):
        seen: set[str] = set()      # the simulator log excerpt is shared by every failing test: show it once
        return "\n".join(f"- {f['test']}: " + ("(same log excerpt as above)" if f["message"] in seen else f["message"])
                         + (seen.add(f["message"]) or "") for f in res["failing"])
    return "the bench did not run to a result (build or elaboration error):\n" + str(res.get("text", ""))[-1800:]


# --- the triage step --------------------------------------------------------------------------------------------------

TRIAGE_SYSTEM = """You settle a disagreement between two test benches for an FPGA design, from the written request alone. Bench A
(the Verifier's, the agent's own) passes against the design. Bench B (written independently from the request) fails. You see the request,
the requester's answers, and both benches; you never see the RTL.

Decide who misread the request. Reply with one JSON object and nothing else:
{"verdict": "design_wrong" | "bench_wrong", "reason": "<two sentences at most: which sentence of the request settles it, and what each bench assumed>"}
- design_wrong: the failing check of bench B is what the request (or an ANSWERED question) says, and bench A did not check it or
  checked something else. The design must change.
- bench_wrong: the failing check of bench B asserts something the request does not say (a guess, a mistaken reading, a timing it
  did not promise), or a NOT CONFIRMED answer. Bench B must change.
When the request is genuinely ambiguous between the two readings, answer bench_wrong: the request must be clear to hold a design to it."""


def triage_prompt(design: Path, failing: str, limit: int = 20_000) -> str:
    a = ""
    for p in sorted((design / "tests").glob("*.py")):
        if p.name.startswith("test_") and p.name.endswith("_rtl.py"):
            continue                                            # the pytest entry, not the checks
        if p.name.endswith("_hw.py") or p.name == "__init__.py":
            continue
        a += f"--- {p.relative_to(design)} ---\n{p.read_text(errors='replace')}\n"
    b = "".join(f"--- {n} ---\n{(design / SPEC_DIR / n).read_text()}\n" for n in ("spec_bench.py",) if (design / SPEC_DIR / n).is_file())
    spec_md = (design / "spec.md").read_text() if (design / "spec.md").is_file() else ""
    return (f"REQUEST (spec.md):\n{spec_md}\n\nTHE REQUESTER'S ANSWERS:\n{interview_text(design)}\n\n"
            f"BENCH A (the Verifier's; all of its checks pass):\n{a[:limit]}\n\nBENCH B (independent):\n{b[:limit]}\n"
            f"BENCH B'S FAILING CHECKS:\n{failing[:3500]}\n")


def parse_verdict(text: str) -> dict[str, str]:
    t = text.strip()
    for cand in (t, re.sub(r"^```(?:json)?\s*|\s*```$", "", t)):
        try:
            d = json.loads(cand)
            break
        except ValueError:
            d = None
    if d is None:
        m = re.search(r"\{.*\}", t, re.S)
        try:
            d = json.loads(m.group()) if m else None
        except ValueError:
            d = None
    if not isinstance(d, dict) or d.get("verdict") not in ("design_wrong", "bench_wrong"):
        return {"verdict": "bench_wrong", "reason": "triage reply not understood; treated as bench_wrong (a design is not failed on an unreadable verdict)"}
    return {"verdict": d["verdict"], "reason": str(d.get("reason", ""))[:600]}


# --- the state and the gate -------------------------------------------------------------------------------------------


def _state_file(design: Path) -> Path:
    return design.joinpath(*STATE_REL)


def load_state(design: Path) -> dict[str, Any]:
    try:
        return json.loads(_state_file(design).read_text())
    except (OSError, ValueError):
        return {"enabled": True, "fired": False, "runs": 0, "outcome": None, "passed": None, "caught_bug": False,
                "bench_repaired": False, "design_wrong": 0, "bench_wrong": 0, "bench_writes": 0, "passed_hash": None,
                "history": []}


def save_state(design: Path, st: dict[str, Any]) -> None:
    f = _state_file(design)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(st, indent=1))


def rtl_hash(design: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((design / "rtl").glob("*.sv")):
        h.update(p.name.encode() + b"\0" + p.read_bytes())
    for n in ("build.yaml",):
        if (design / n).is_file():
            h.update((design / n).read_bytes())
    return h.hexdigest()[:16]


def _note(st: dict[str, Any], **kw: Any) -> None:
    st["history"].append({"t": round(time.time()), **kw})


def write_bench(design: Path, board: str, llm: LLM, st: dict[str, Any], prompt: str | None = None) -> list[str]:
    """One role call, then (if the files do not even compile) one repair call. Returns the problems left."""
    prompt = prompt or role_prompt(design, board)
    for attempt in (0, 1):
        files = parse_files(llm(ROLE_SYSTEM, prompt))
        st["bench_writes"] += 1
        if files:
            write_files(design, files)
        problems = static_problems(design) if files else ["the reply held no spectest/ files in the required form"]
        _note(st, step="write" if attempt == 0 else "write_static_repair", files=sorted(files), problems=problems)
        if not problems:
            return []
        prompt = prompt + "\n\nYour previous reply had these problems, fix them and reply with both files again:\n" + "\n".join(problems)
    return problems


def gate(design: Path, board: str, runner: Any, role_llm: LLM, triage_llm: LLM, *, max_loops: int = DEFAULT_MAX_LOOPS,
         sim: str = "icarus", timeout: float = SIM_TIMEOUT_S) -> dict[str, Any]:
    """The spec-test gate for the design in its current state. Returns ``{"verdict": pass | design_wrong | unresolved | error,
    "blocks": bool, "evidence": str, "sig": str}``; the counters are in ``build/spectest/state.json``."""
    st = load_state(design)
    st["fired"] = True
    h = rtl_hash(design)
    if st.get("passed_hash") == h and st.get("outcome") == "pass":
        return {"verdict": "pass", "blocks": False, "evidence": "", "sig": "pass", "cached": True}
    try:
        if not (design / SPEC_DIR / "spec_bench.py").is_file():
            left = write_bench(design, board, role_llm, st)
            if left:
                st["outcome"] = "error"
                _note(st, step="error", why="the bench could not be written: " + "; ".join(left))
                return _finish(design, st, "error", False, "the spec-test bench could not be written: " + "; ".join(left), "error")
        repaired_this_episode = False
        for _ in range(4):                                       # run, triage, at most one bench repair, run, triage
            res = run_bench(design, runner, sim, timeout)
            st["runs"] += 1
            _note(st, step="run", rtl=h, ok=res["ok"], failing=[f["test"] for f in res["failing"]], built=res["built"])
            if res["ok"]:
                st.update(outcome="pass", passed=True, passed_hash=h)
                st["caught_bug"] = st["design_wrong"] > 0
                return _finish(design, st, "pass", False, "", "pass")
            if st["design_wrong"] >= max_loops:
                st.update(outcome="unresolved", passed=False)
                _note(st, step="limit", why=f"{st['design_wrong']} design_wrong round trips already used (limit {max_loops})")
                return _finish(design, st, "unresolved", False, failing_checks_text(res), "limit")
            failing = failing_checks_text(res)
            v = parse_verdict(triage_llm(TRIAGE_SYSTEM, triage_prompt(design, failing)))
            _note(st, step="triage", **v)
            if v["verdict"] == "design_wrong":
                st["design_wrong"] += 1
                st.update(outcome="design_wrong", passed=False)
                sig = "spectest:" + "|".join(sorted(f["test"] for f in res["failing"])) if res["failing"] else "spectest:build"
                ev = (f"[spec test] An independent bench written from the request alone fails against your design, and a reviewer who "
                      f"read the request judged the design wrong: {v['reason']}\nFailing checks of the independent bench:\n{failing}\n"
                      f"The bench (spectest/spec_bench.py) is yours to read; fix the RTL to match the request.")
                return _finish(design, st, "design_wrong", True, ev, sig)
            st["bench_wrong"] += 1
            if repaired_this_episode:                            # the bench was repaired once and is still judged wrong
                st.update(outcome="unresolved", passed=False)
                _note(st, step="unresolved", why="bench_wrong again after one repair")
                return _finish(design, st, "unresolved", False, failing, "bench_wrong_twice")
            repaired_this_episode = True
            st["bench_repaired"] = True
            left = write_bench(design, board, role_llm, st, repair_prompt(design, board, v["reason"], failing))
            if left:
                st.update(outcome="unresolved", passed=False)
                return _finish(design, st, "unresolved", False, "bench repair did not compile: " + "; ".join(left), "repair_failed")
        st.update(outcome="unresolved", passed=False)
        return _finish(design, st, "unresolved", False, "loop bound reached", "bound")
    except Exception as e:                                       # an infrastructure fault must never stop a run or fail a design
        st["outcome"] = "error"
        _note(st, step="error", why=f"{type(e).__name__}: {str(e)[:300]}")
        return _finish(design, st, "error", False, f"{type(e).__name__}: {str(e)[:300]}", "error")


def _finish(design: Path, st: dict[str, Any], verdict: str, blocks: bool, evidence: str, sig: str) -> dict[str, Any]:
    save_state(design, st)
    return {"verdict": verdict, "blocks": blocks, "evidence": evidence, "sig": sig}


def record(design: Path) -> dict[str, Any]:
    """The run record's fields (tools/run_record.py): fired / passed / caught a bug / bench repaired, and the counters."""
    f = _state_file(design)
    if not f.is_file():
        return {"fired": False}
    st = load_state(design)
    return {"fired": bool(st.get("fired")), "passed": st.get("passed"), "outcome": st.get("outcome"),
            "caught_bug": bool(st.get("caught_bug")), "bench_repaired": bool(st.get("bench_repaired")),
            "design_wrong_verdicts": st.get("design_wrong", 0), "bench_wrong_verdicts": st.get("bench_wrong", 0),
            "bench_writes": st.get("bench_writes", 0), "bench_runs": st.get("runs", 0)}


# --- the real model calls (a headless `claude -p`, no tools, like the Claude Code interview oracle) ---------------------


def cc_llm(model: str, effort: str | None, log: Path | None = None, label: str = "spectest", timeout_s: float = 900) -> LLM:
    """``llm(system, user) -> text`` through one headless Claude Code call with no tools, no MCP, no settings, an empty HOME and
    a temporary working directory (the isolation of ``agent.claude_code_arm.oracle``). Each call is logged to ``log``
    (``claude_code_calls.jsonl`` of the run) so the run's plan-cost estimate counts it."""
    from agent.claude_code_arm import arm

    def llm(system: str, user: str) -> str:
        from agent.graph.run import ArmBlocked
        if shutil.which("claude") is None:
            raise ArmBlocked("the claude CLI is not on PATH")
        token = arm.oauth_token()
        if not token:
            raise ArmBlocked("CLAUDE_CODE_OAUTH_TOKEN is not set and the token file is missing")
        argv = ["claude", "-p", user, "--output-format", "json", "--system-prompt", system, "--tools", "",
                "--strict-mcp-config", "--permission-mode", "dontAsk", "--setting-sources", "", "--disable-slash-commands",
                "--no-session-persistence", "--model", model, *(["--effort", effort] if effort else []), "--max-turns", "1"]
        work = Path(tempfile.mkdtemp(prefix="fda_spectest_"))
        t0 = time.time()
        try:
            p = subprocess.run(argv, cwd=work, env=arm.isolated_env(work, token), capture_output=True, text=True,
                               timeout=timeout_s, stdin=subprocess.DEVNULL)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        try:
            res = json.loads(p.stdout)
        except ValueError:
            res = {}
        if log is not None:
            u = res.get("usage") or {}
            tok = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
            with log.open("a") as f:
                f.write(json.dumps({"tag": f"{label}", "role": label, "stage": "rtl-design-creation", "model_requested": model,
                                    "effort": effort or "cli-default", "claude_code_version": None, "turns": res.get("num_turns"),
                                    "wall_s": round(time.time() - t0, 1), "is_error": res.get("is_error"), "tokens": tok,
                                    "cost_usd": "unreported", "plan_cost_estimate_usd": res.get("total_cost_usd")}) + "\n")
        if res.get("is_error") and any(k in str(res.get("result", "")).lower() for k in ("login", "authenticat", "oauth", "401")):
            raise ArmBlocked("Claude Code could not authenticate: " + str(res.get("result", ""))[:200])
        return str(res.get("result", ""))
    return llm
