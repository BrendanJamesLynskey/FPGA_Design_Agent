"""The brief 16 CDC fixture's own cocotb test (random traffic, clk_a 10 ns, clk_b 7 ns) on the VHDL async FIFO."""
import os
from pathlib import Path
from flow import cocotb_run
HERE = Path(__file__).resolve().parent
def test_c10():
    os.environ["CDCFX_NAME"] = "cdcfx_c10"
    cocotb_run.run("b55_mut_c10", "cdcfx_c10", sorted((HERE.parent / "rtl").glob("*.vhd")), "cdcfx_tb", HERE, seed=1)
