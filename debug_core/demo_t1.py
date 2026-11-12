"""Known-answer board demo of the debug front end on T1 (brief 50A): plain English in, answer out, checked.

    python -m debug_core.demo_t1 [--only name ...] [--results results/50a_nl_debug] [--replay]

For each request in debug_core/tests/fixtures/requests.json that has a known answer below: parse it with the model
(``--replay`` uses the recorded replies instead), plan, reuse the debug build that holds the probes (the builds are made
beforehand under a heavy slot), program SRAM and capture inside board.lock, answer, and check the answer's facts against
the known answer and against what the shell reads back. Writes ``<results>/<name>/`` (plan, capture JSON, VCD, answer,
view, the model's replies, the check) and ``<results>/demo.json``. The known answers come from the T1 spec
(designs/t1_dimmer_counter/spec.yaml): a write lands on the clock after the window strobe; LEDs are lit for DUTY x
PWM_PRESCALE clocks of each 1024-clock period; every shell request frame starts with the sync byte 0xA5.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

from debug_core import answer as A
from debug_core import run as R
from debug_core.plan import render
from debug_core.rtl_index import ROOT

FIX = Path(__file__).parent / "tests" / "fixtures"
PRESCALE = 4


def _ch(F: dict[str, Any], n: str) -> dict[str, Any]:
    return F["channels"][n]


def check_count_write(cap: dict[str, Any], F: dict[str, Any]) -> dict[str, Any]:
    c = _ch(F, "count")
    rb = cap["readback"].get("COUNT")
    want = {"count_at_trigger": 0x0003, "count_after": 0x1234, "win_wr_high_runs": [(0, 1)], "readback_COUNT": 0x1234}
    got = {"count_at_trigger": c["at_trigger"], "count_after": c["after_trigger"],
           "win_wr_high_runs": [tuple(r) for r in _ch(F, "win_wr")["high_runs"]], "readback_COUNT": rb}
    return {"want": want, "got": got, "pass": want == got and F["trigger"]["holds"] is True}


def check_pwm_period(cap: dict[str, Any], F: dict[str, Any]) -> dict[str, Any]:
    led = next(c for c in cap["channels"] if c["name"] == "led")["samples"]
    phase = next(c for c in cap["channels"] if c["name"] == "phase")["samples"]
    t0 = cap["timebase"]["trigger_sample"]
    duty, count = cap["readback"].get("DUTY"), cap["readback"].get("COUNT")
    window = led[t0:t0 + 256 * PRESCALE]
    lit = sum(1 for v in window if v)
    want = {"phase_at_trigger": 0, "lit_clocks": (duty or 0) * PRESCALE, "lit_value": count,
            "readback_DUTY": 0x40, "readback_COUNT": 0x8421}
    got = {"phase_at_trigger": phase[t0], "lit_clocks": lit, "lit_value": sorted({v for v in window if v}) == [count] and count,
           "readback_DUTY": duty, "readback_COUNT": count}
    return {"want": want, "got": got, "pass": want == got and F["trigger"]["holds"] is True}


def check_sync_byte(cap: dict[str, Any], F: dict[str, Any]) -> dict[str, Any]:
    want = {"rx_data_at_trigger": 0xA5, "rx_valid_at_trigger": 1, "rx_valid_before": 0}
    got = {"rx_data_at_trigger": _ch(F, "rx_data")["at_trigger"], "rx_valid_at_trigger": _ch(F, "rx_valid")["at_trigger"],
           "rx_valid_before": _ch(F, "rx_valid")["before_trigger"]}
    return {"want": want, "got": got, "pass": want == got and F["trigger"]["holds"] is True}


def check_or_flags(cap: dict[str, Any], F: dict[str, Any]) -> dict[str, Any]:
    """OR of two 1-bit rising edges; only the DUTY write happens (no button is pressed), 300 ms after arming."""
    d = _ch(F, "duty")
    want = {"trigger_holds": True, "win_wr_at_trigger": 1, "press_clear_at_trigger": 0, "duty_after": 0x22}
    got = {"trigger_holds": F["trigger"]["holds"], "win_wr_at_trigger": _ch(F, "win_wr")["at_trigger"],
           "press_clear_at_trigger": _ch(F, "press_clear")["at_trigger"], "duty_after": d["last"]}
    return {"want": want, "got": got, "pass": want == got}


def check_reuse_rise(cap: dict[str, Any], F: dict[str, Any]) -> dict[str, Any]:
    c = _ch(F, "count")
    want = {"count_after": 0x0042, "readback_COUNT": 0x0042, "reused_build": True}
    got = {"count_after": c["after_trigger"], "readback_COUNT": cap["readback"].get("COUNT"),
           "reused_build": bool(cap["build"].get("reused"))}
    return {"want": want, "got": got, "pass": want == got and F["trigger"]["holds"] is True}


CHECKS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "t1_count_write": check_count_write, "t1_pwm_period": check_pwm_period, "t1_sync_byte": check_sync_byte,
    "t1_or_flags": check_or_flags, "t1_reuse_rise": check_reuse_rise}


def scrub_tree(d: Path, secrets: list[str]) -> None:
    for f in d.rglob("*"):
        if f.is_file() and f.suffix in (".txt", ".log", ".json", ".tcl", ".csv", ".html", ".vcd"):
            t = f.read_text(errors="replace")
            for s in secrets:
                if s and s in t:
                    t = t.replace(s, "..." + s[-4:])
            f.write_text(t)


def clean_outputs(out: Path, secrets: list[str]) -> None:
    """Keep the raw files a capture came from, without the Vivado and hw_server logs and the programming transcript (they
    name the cable), and with any other mention of the cable serial shortened to its last 4 characters."""
    for f in (list(out.rglob("*.log")) + list(out.glob("program/*.stdout.txt"))
              + [out / "ila" / x for x in ("cap.go", "cap.armed", "cap.done")]):
        if f.is_file():
            f.unlink()
    scrub_tree(out, secrets)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--results", type=Path, default=ROOT / "results" / "50a_nl_debug")
    ap.add_argument("--replay", action="store_true", help="use the recorded model replies (no model call)")
    ap.add_argument("--board")
    a = ap.parse_args(argv)
    from agent.graph.llm import OpenRouterClient, Recorder, Replay
    from flow import hw
    reqs = json.loads((FIX / "requests.json").read_text())
    names = [n for n in (a.only or CHECKS) if n in CHECKS]
    board = hw.load_board(a.board or "nexys_a7_100t")
    secrets = [board.get("cable_serial") or ""]
    try:
        from flow import hw_discover
        secrets.append(hw_discover.usb_serial(board["cable_serial"]) or "")
    except Exception:
        pass
    summary = json.loads((a.results / "demo.json").read_text()) if (a.results / "demo.json").is_file() else {}
    rc = 0
    for name in names:
        r = reqs[name]
        out = a.results / name
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        t0 = time.monotonic()
        client = Replay(FIX / "llm" / f"{name}.json") if a.replay else Recorder(OpenRouterClient(), out / "llm_replies.json")
        plan, meta = R.plan_request(ROOT / r["design"], r["request"], client=client)
        (out / "plan.json").write_text(json.dumps(plan | {"parse": meta}, indent=1) + "\n")
        (out / "plan.txt").write_text(render(plan) + "\n")
        print(render(plan), flush=True)
        if plan["errors"]:
            summary[name] = {"request": r["request"], "plan_errors": plan["errors"], "pass": False}
            rc = 1
            continue
        ov, labels, info = R.ensure_build(plan, allow_build=False)
        t_cap = time.monotonic()
        try:
            cap = R.hardware_capture(plan, ov, labels, out, a.board,
                                     lock_text=f"FPGA b50a: debug demo {name}, {time.strftime('%H:%M')}, expected end "
                                               f"{time.strftime('%H:%M', time.localtime(time.time() + 300))}")
        except Exception:
            clean_outputs(out, secrets)          # a failed run's files are kept as evidence, never with the cable named
            raise
        cap["build"]["reused"] = info["reused"] and ov.name != plan["probeset"]
        cap["build"]["build_probeset"] = ov.name
        ans = R.finish(cap, plan, out)
        chk = CHECKS[name](cap, ans["facts"])
        chk["answer_numbers_unquoted"] = ans["check"]
        chk["pass"] = chk["pass"] and not ans["check"]
        (out / "check.json").write_text(json.dumps(chk, indent=1, default=str) + "\n")
        print(ans["text"], "\nCHECK", json.dumps(chk, default=str), flush=True)
        summary[name] = {"request": r["request"], "probeset": plan["probeset"], "build_probeset": ov.name,
                         "reused_build": cap["build"]["reused"], "parse": {k: meta.get(k) for k in ("parser", "model", "cost",
                                                                                                  "prompt_tokens", "completion_tokens")},
                         "answer": ans["text"], "check": chk, "conditions_verdict": cap["conditions"].get("verdict"),
                         "seconds_total": round(time.monotonic() - t0, 1), "seconds_program_capture": round(time.monotonic() - t_cap, 1),
                         "pass": chk["pass"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        rc |= 0 if chk["pass"] else 1
        clean_outputs(out, secrets)
        (a.results / "demo.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
