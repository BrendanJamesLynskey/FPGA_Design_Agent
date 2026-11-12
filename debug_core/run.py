"""Request -> plan -> build -> capture -> answer, end to end (brief 50A).

Each step can run on its own (``python -m debug_core plan|build|capture|answer|view|query``); ``run`` does them in order and
stops after the plan if the plan has errors. Outputs go to ``<design>/build/debug/runs/<time>_<probeset>/``: ``plan.json``,
``plan.txt``, ``capture.json``, ``capture.vcd``, ``answer.txt``, ``view.html`` and the instrument's raw files.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from debug_core import answer as A
from debug_core import build as B
from debug_core import capture as C
from debug_core.plan import make_plan, render
from debug_core.rtl_index import ROOT


def run_dir(plan: dict[str, Any], root: Path | None = None) -> Path:
    d = (root or B.design_dir(plan) / "build" / "debug" / "runs") / f"{time.strftime('%Y%m%d_%H%M%S')}_{plan['probeset']}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plan_request(design: Path, request: str | None = None, intent: dict[str, Any] | None = None,
                 client: Any = None, model: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (plan, parse meta). ``intent`` skips the language model (an agent can give the structured request)."""
    meta: dict[str, Any] = {"parser": "given intent"}
    if intent is None:
        if not request:
            raise ValueError("give a request or an intent")
        from debug_core.request import DEFAULT_MODEL, parse
        intent, meta = parse(request, design, client=client, model=model or DEFAULT_MODEL)
        meta = {k: v for k, v in meta.items() if k != "replies"} | {"parser": "llm"}
    plan = make_plan(design, intent, request)
    plan["intent"] = intent
    return plan, meta


def ensure_build(plan: dict[str, Any], allow_build: bool) -> tuple[Path, dict[str, str], dict[str, Any]]:
    """(overlay, plan label -> build label, info). Reuses a finished build that holds the plan's probes; otherwise builds
    when allowed (the caller holds a heavy slot)."""
    hit = B.find_build(plan)
    if hit:
        ov, labels = hit
        return ov, labels, {"reused": True, "probeset": ov.name, "rebuild": False}
    if not allow_build:
        raise RuntimeError(f"no debug build holds these probes yet; build probe set {plan['probeset']} first "
                           "(python -m debug_core build <plan.json>, under a heavy slot)")
    st = B.run_build(plan)
    if not st.get("built"):
        raise RuntimeError(f"the debug build failed (exit {st.get('returncode')}); see {st.get('log')}")
    return B.overlay_dir(plan), {p["label"]: p["label"] for p in plan["probes"]}, {"reused": False, "rebuild": True, **st}


def hardware_capture(plan: dict[str, Any], ov: Path, labels: dict[str, str], out: Path, board: str | None = None,
                     lock_text: str | None = None, program: bool = True) -> dict[str, Any]:
    """Program the debug build into SRAM (board.lock held), capture, and return the capture dict."""
    from flow import hw
    from flow import program as prog
    from hil.instruments.board_lock import BoardLock
    from debug_core.instruments import VendorIla
    text = lock_text or f"FDA debug: capture {plan['probeset']}, {time.strftime('%H:%M')}, expected end " \
                        f"{time.strftime('%H:%M', time.localtime(time.time() + 600))}"
    with BoardLock(text):
        with hw.HwServer(out):
            pr = None
            if program:
                pr = prog.program(ov, "ila", board, out / "program")
                (out / "program.json").write_text(json.dumps(pr, indent=1, default=str) + "\n")
                if not pr.get("pass"):
                    raise RuntimeError(f"programming failed: {pr}")
            inst = VendorIla(ov / "build" / "ila", board=board, work=out / "ila", labels=labels)
            try:
                inst.configure(plan)
                inst.arm()
                cap = inst.capture()
            finally:
                inst.close()
            if pr:
                cap["conditions"]["programmed"] = pr.get("conditions")
                cap["build"]["program_seconds"] = pr.get("seconds")
                cap["build"]["power_ok"] = {k: (pr.get("power_ok") or {}).get(k) for k in ("pass", "total_w", "junction_c", "source")}
    return cap


def finish(cap: dict[str, Any], plan: dict[str, Any], out: Path) -> dict[str, Any]:
    from debug_core.view import write_view
    C.save(cap, out / "capture.json")
    (out / "capture.vcd").write_text(C.to_vcd(cap))
    ans = A.answer(cap, plan.get("question"))
    (out / "answer.txt").write_text(ans["text"] + "\n")
    write_view(cap, out / "view.html", answer_text=ans["text"])
    return ans
