"""pytest entry: the generated custom-instruction wrapper (hwsw/cfu.py) around ip_lib/crc32_step, on its own under
cocotb + Icarus, in both variants and both integration styles: the EX-stall style (hwsw/tests/cfu_wrapper_cocotb.py:
kill then a quick retry, hold, stale operands after the first clock in EX, a random soak) and the MEM-completion style
(hwsw/tests/cfu_mem_wrapper_cocotb.py: back to back, other MEM stalls, operands only in the issue clock, a soak). Then
seeded faults in each wrapper, each of which its bench must catch."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from flow import cocotb_run
from hwsw import cfu

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build" / "64a" / "cfu_wrapper"
UNIT = ROOT / "ip_lib" / "crc32_step" / "rtl" / "crc32_step.sv"


def _prepare(variant: str, tag: str, old: str | None = None, new: str | None = None, style: str = "ex") -> list[Path]:
    out = BUILD / tag
    if out.exists():
        shutil.rmtree(out)
    files = cfu.generate("crc32_step", variant, out, style=style)
    if old is not None:                                         # a fault seeded in the generated wrapper
        sv = files["sv"].read_text()
        assert sv.count(old) == 1, f"{tag}: the text to replace is not in the generated wrapper exactly once"
        files["sv"].write_text(sv.replace(old, new))
    return [UNIT, files["sv"]]


@pytest.mark.parametrize("variant", ["word", "byte"])
def test_wrapper(variant: str) -> None:
    src = _prepare(variant, variant)
    cocotb_run.run(f"cfu_wrapper_64a_{variant}", "cfu_crc32_step", src, "cfu_wrapper_cocotb", HERE, seed=1,
                   extra_env={"CFU_LATENCY": str(cfu.latency("crc32_step", variant))})


# (id, variant, text to replace, replacement): each must make the bench fail.
FAULTS = [
    ("operands_not_kept", "byte", "assign a_in     = held ? a_q : a;", "assign a_in     = a;"),
    ("no_wait_for_killed_op", "byte", "assign go       = start && !active && !inflight && !kill;",
     "assign go       = start && !active && !kill;"),
    ("kill_leaves_active", "word", "            if (kill) begin\n                active <= 1'b0;\n",
     "            if (kill) begin\n"),
]


@pytest.mark.parametrize("fid,variant,old,new", FAULTS, ids=[f[0] for f in FAULTS])
def test_wrapper_fault_is_caught(fid: str, variant: str, old: str, new: str) -> None:
    src = _prepare(variant, f"fault_{fid}", old, new)
    with pytest.raises(AssertionError):
        cocotb_run.run(f"cfu_wrapper_64a_fault_{fid}", "cfu_crc32_step", src, "cfu_wrapper_cocotb", HERE, seed=1,
                       extra_env={"CFU_LATENCY": str(cfu.latency("crc32_step", variant)), "CFU_OPS": "1500"})


@pytest.mark.parametrize("variant", ["word", "byte"])
def test_mem_style_wrapper(variant: str) -> None:
    src = _prepare(variant, f"mem_{variant}", style="mem")
    cocotb_run.run(f"cfu_mem_wrapper_64a_{variant}", "cfu_crc32_step", src, "cfu_mem_wrapper_cocotb", HERE, seed=1,
                   extra_env={"CFU_LATENCY": str(cfu.latency("crc32_step", variant))})


# MEM style: (id, variant, text to replace, replacement): each must make its bench fail.
MEM_FAULTS = [
    ("mem_never_stalls", "byte", "assign stall  = in_mem && !have && !unit_valid;", "assign stall  = 1'b0;"),
    ("mem_kept_result_not_cleared", "byte",
     "        end else if (in_mem && !stall && !hold) begin       // the instruction leaves MEM with its result\n"
     "            have <= 1'b0;\n",
     "        end else if (in_mem && !stall && !hold) begin       // the instruction leaves MEM with its result\n"),
]
# Not seeded: dropping the kept copy (result = unit_out) is not observable with crc32_step, whose output register holds
# its value until the next issue; the copy is there for units whose result is valid only with the done pulse (the
# function_unit contract promises no more).


@pytest.mark.parametrize("fid,variant,old,new", MEM_FAULTS, ids=[f[0] for f in MEM_FAULTS])
def test_mem_style_fault_is_caught(fid: str, variant: str, old: str, new: str) -> None:
    src = _prepare(variant, f"fault_{fid}", old, new, style="mem")
    with pytest.raises(AssertionError):
        cocotb_run.run(f"cfu_mem_wrapper_64a_fault_{fid}", "cfu_crc32_step", src, "cfu_mem_wrapper_cocotb", HERE, seed=1,
                       extra_env={"CFU_LATENCY": str(cfu.latency("crc32_step", variant)), "CFU_OPS": "1500"})
