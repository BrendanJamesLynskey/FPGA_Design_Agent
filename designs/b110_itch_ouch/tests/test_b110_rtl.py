"""pytest entry: the whole path under cocotb + Icarus against the Python reference (brief 110).

B110_RTL_DIR (a directory with the same file names) swaps in a mutated copy of the RTL: tests/run_mutants.py does that.
B110_RECORD=<absolute dir> writes the measured latencies (latency_sim.json) there."""
from __future__ import annotations

import os
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
RTL = Path(os.environ.get("B110_RTL_DIR") or DESIGN / "rtl")
FILES = ["itch_pkg.sv", "feed_arb_in.sv", "feed_arb.sv", "mold_rx.sv", "itch_dec.sv", "book_core.sv", "ouch_enter.sv", "risk_glue.sv", "itch_ouch_top.sv"]


def run(name: str, testcase=None, params=None, extra=None, module="b110_cocotb") -> None:
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B110_RECORD"):
        env["B110_RECORD"] = os.environ["B110_RECORD"]
    env |= extra or {}
    if int(os.environ.get("B110_PARSE_INPLACE", "0")):          # brief 191: every bench run of a mutant or a session can use the in-place decoder
        params = {"PARSE_INPLACE": 1} | (params or {})
    cocotb_run.run(name, "itch_ouch_top", [RTL / f for f in FILES], module, HERE, parameters=params, testcase=testcase, extra_env=env)


def test_all_benches() -> None:
    """Every cocotb test of the bench in one simulation (the default parameters N_INST 4, LEVELS 8, ORD_AW 8)."""
    run("b110_all")


def test_other_parameters() -> None:
    """The same random session at other N_INST, LEVELS and ORD_AW (the model's configuration follows through B110_NINST, B110_LEVELS, B110_ORDAW)."""
    for n, lv, aw in ((2, 4, 5), (3, 8, 6), (8, 8, 10)):
        run(f"b110_p{n}_{lv}_{aw}", testcase="main_stream_params", params={"N_INST": n, "LEVELS": lv, "ORD_AW": aw},
            extra={"B110_NINST": str(n), "B110_LEVELS": str(lv), "B110_ORDAW": str(aw)})


def test_notional_modes() -> None:
    """Brief 188: the notional check built as a multiply (NOTIONAL_MODE 1) and as a software-written price-band table (2): the notional test of the bench against the model's verdicts."""
    for mode in (1, 2):
        run(f"b110_nt{mode}", testcase="notional", params={"NOTIONAL_MODE": mode}, extra={"B110_NOTIONAL": str(mode)})


def test_notional_latency() -> None:
    """Brief 188: the same latency test (book update and first order word, in clocks from the last byte of the message) for each NOTIONAL_MODE; the records go to B110_RECORD/nt<mode>/ when it is set."""
    top = os.environ.get("B110_RECORD")
    try:
        for mode in (0, 1, 2):
            if top:
                d = Path(top) / f"nt{mode}"
                d.mkdir(parents=True, exist_ok=True)
                os.environ["B110_RECORD"] = str(d)
            run(f"b110_ntlat{mode}", testcase="latency", params={"NOTIONAL_MODE": mode}, extra={"B110_NOTIONAL": str(mode)})
    finally:
        if top:
            os.environ["B110_RECORD"] = top


def test_book_core_queue() -> None:
    """book_core alone, events on consecutive clocks (tests/b110_book_cocotb.py): the queue and the Replace's second slot."""
    srcs = [RTL / "itch_pkg.sv", RTL / "book_core.sv"]
    cocotb_run.run("b110_book", "book_core", srcs, "b110_book_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})


def test_lane_by_type() -> None:
    """Brief 191: every message type starting in each of the eight byte lanes, with the shift decoder and with the in-place decoder."""
    for ip in (0, 1):
        run(f"b110_lane{ip}", testcase="lane_by_type", params={"PARSE_INPLACE": ip})


def test_parse_inplace() -> None:
    """Brief 191: the whole bench (every cocotb test, against the same model) with the decoder that parses in place (PARSE_INPLACE 1), then the start-lane by type test at another size."""
    run("b110_inplace", params={"PARSE_INPLACE": 1})
    run("b110_inplace_p2", testcase="main_stream_params", params={"PARSE_INPLACE": 1, "N_INST": 2, "LEVELS": 4, "ORD_AW": 5},
        extra={"B110_NINST": "2", "B110_LEVELS": "4", "B110_ORDAW": "5"})


def test_reject_bits() -> None:
    """Brief 191: the reject-bit and equal-latency test alone, with and without the in-place decoder (it also runs inside test_all_benches)."""
    for ip in (0, 1):
        run(f"b110_rb{ip}", testcase="reject_bits", params={"PARSE_INPLACE": ip})


def test_dual_feed() -> None:
    """Brief 191: the A/B feed arbiter (DUAL_FEED 1) against the model: both feeds complete with skews, single-feed losses filled, a loss on both feeds, the fill window, heartbeats, a bad frame on the first copy, another session, overlap, bursts, random sessions, and the latency."""
    run("b110_ab", params={"DUAL_FEED": 1}, module="b110_ab_cocotb")
    run("b110_ab_inplace", params={"DUAL_FEED": 1, "PARSE_INPLACE": 1}, module="b110_ab_cocotb", testcase="ab_random")
    run("b110_ab_aw8", params={"DUAL_FEED": 1, "ARB_AW": 8}, module="b110_ab_cocotb", testcase="ab_deep_skew", extra={"B110_ARB_AW": "8"})
