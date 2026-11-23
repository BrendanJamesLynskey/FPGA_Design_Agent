"""Brief 189 item 4: the conservation invariant (frames in = out + counted drops + held) and a planted silent-drop mutant.
Advisory: the helper is a bench aid, not a gate (enforced: false in results/189_verification_rules/conservation.json)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from flow.verif_lib.conservation import Conservation

FX = Path(__file__).parent / "fixtures" / "conservation"
LIB = Path(__file__).resolve().parents[1] / "verif_lib" / "fda_conservation.sv"
pytestmark = pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs Icarus Verilog")


def _sim(tmp: Path, srcs: list[Path], top: str, plus: list[str]) -> str:
    vvp = tmp / f"{top}.vvp"
    r = subprocess.run(["iverilog", "-g2012", "-s", top, "-o", str(vvp), *map(str, srcs)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run(["vvp", str(vvp), *plus], capture_output=True, text=True, timeout=120)
    return r.stdout + r.stderr


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_correct_filter_conserves_every_frame(seed: int, tmp_path: Path) -> None:
    out = _sim(tmp_path, [LIB, FX / "cons_filter.sv", FX / "cons_tb.sv"], "cons_tb", ["+MUTANT=0", f"+SEED={seed}"])
    m = re.search(r"CONS_PASS in=(\d+) out=(\d+) dropped=(\d+)", out)
    assert m, out
    assert int(m[3]) > 100, "the stimulus must make the block drop frames, or the check proves nothing"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_silent_drop_mutant_is_caught_at_the_first_lost_frame(seed: int, tmp_path: Path) -> None:
    out = _sim(tmp_path, [LIB, FX / "cons_filter.sv", FX / "cons_tb.sv"], "cons_tb", ["+MUTANT=1", f"+SEED={seed}"])
    assert "CONS_FAIL" in out and "fda_conservation" in out, out
    # the first failure is early: the FIFO first fills within a few dozen frames
    assert int(re.search(r"first_bad_in=(\d+)", out)[1]) < 100


def test_unresolved_counter_fails_not_passes(tmp_path: Path) -> None:
    tb = tmp_path / "x_tb.sv"
    tb.write_text("""module x_tb; logic clk = 0, rst = 1; always #5 clk = ~clk; logic fi = 0, fo = 0; logic [31:0] dc = 'x, inf = 0;
      wire v; wire [31:0] a, b, c;
      fda_conservation chk (.clk, .rst, .frame_in(fi), .frame_out(fo), .drop_count(dc), .in_flight(inf), .violation(v), .n_in(a), .n_out(b), .first_bad_in(c));
      initial begin repeat (3) @(posedge clk); rst <= 0; repeat (3) @(posedge clk); #1 $display(v ? "X_FAILS" : "X_PASSES"); $finish; end endmodule""")
    out = _sim(tmp_path, [LIB, tb], "x_tb", [])
    assert "fda_conservation" in out and "dropped=x" in out, out


def test_python_twin() -> None:
    c = Conservation()
    held = 0
    for i in range(12):                  # a one-register pipeline: a frame entering on this edge leaves on the next
        fi, fo = i < 10, held > 0
        assert c.step(fi, fo, 0, held)   # the counts and the block's occupancy are the values before this edge
        held += int(fi) - int(fo)
    assert c.ok and c.n_in == 10 == c.n_out
    d = Conservation()
    held = 0
    for i in range(4):                   # the same pipeline, but the frame entering at edge 2 is lost
        fi, fo = i < 3, held > 0
        d.step(fi, fo, 0, held)
        held += int(fi) - int(fo) - (1 if i == 2 else 0)
    assert not d.ok
    assert not Conservation().step(False, False, None, 0)
