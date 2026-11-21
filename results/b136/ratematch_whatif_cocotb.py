"""Brief 136, scenario 1: the rate-matcher bench of brief 96C/96E at chosen ppm points, with a FUNCTIONAL verdict that does not depend on the Python twin.

Imports run_case from designs/b96_kr260_10g/tests/ratematch_cocotb.py. run_case compares the RTL with the twin and asserts; a seeded bug (a mutant of rate_match_gp.sv)
differs from the twin by construction, so here the assertion is caught and recorded as `twin_mismatch`, and the verdict a human's test would use is the functional one:
every frame offered comes out intact and in order (`frames_equal`) and the overflow counter is 0.

Environment: B136_POINTS (comma list of ppm), B136_FRAMES, B136_OUT (a JSON file that collects the results)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb

from designs.b96_kr260_10g.tests import ratematch_cocotb as rc

POINTS = [float(x) for x in os.environ.get("B136_POINTS", "0,100,-100,300,-300").split(",")]
FRAMES = int(os.environ.get("B136_FRAMES", "2500"))
OUT = os.environ.get("B136_OUT")
ALL: dict = {}


@cocotb.test(timeout_time=200, timeout_unit="ms")
@cocotb.parametrize(ppm=POINTS)
async def ppm_point(dut, ppm):
    name = f"ppm{ppm:+g}"
    twin_mismatch = False
    try:
        res = await rc.run_case(dut, name, ppm, n_frames=FRAMES, gaps=(2, 3, 1, 4), seed=11)
    except AssertionError:
        twin_mismatch = True
        res = rc.RESULTS[name]
    except ValueError as e:      # an X or Z on the buffer's output (cocotb cannot read it as a number): the bug corrupts the output, which a human's test also sees
        out = dict(ppm=ppm, x_on_output=True, error=str(e)[:120], functional_fail=True, twin_mismatch=True)
        ALL[name] = out
        dut._log.info("B136 " + json.dumps(out))
        if OUT:
            Path(OUT).write_text(json.dumps(ALL, indent=1) + "\n")
        return
    r = res["rtl"]
    out = dict(ppm=ppm, frames_in=res["frames_in"], frames_out=res["frames_out"], frames_equal=bool(res["frames_equal"]), n_ovf=r["n_ovf"], n_ins=r["n_ins"], n_del=r["n_del"],
               n_stall=r["n_stall"], fill_min=r["fill_min"], fill_max=r["fill_max"], twin_mismatch=twin_mismatch, twin_mismatch_cycles=res["mismatch"],
               functional_fail=(not res["frames_equal"]) or r["n_ovf"] > 0)
    ALL[name] = out
    dut._log.info("B136 " + json.dumps(out))
    if OUT:
        Path(OUT).write_text(json.dumps(ALL, indent=1) + "\n")
