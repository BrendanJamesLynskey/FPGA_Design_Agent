"""pytest entry: the generated custom-instruction wrapper (hwsw/cfu.py) around ip_lib/crc32_step, on its own under
cocotb + Icarus, in both variants (hwsw/tests/cfu_wrapper_cocotb.py: kill then a quick retry, hold, stale operands
after the first clock in EX, a random soak). Then seeded faults in the wrapper, each of which the bench must catch."""
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


def _prepare(variant: str, tag: str, old: str | None = None, new: str | None = None) -> list[Path]:
    out = BUILD / tag
    if out.exists():
        shutil.rmtree(out)
    files = cfu.generate("crc32_step", variant, out)
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
