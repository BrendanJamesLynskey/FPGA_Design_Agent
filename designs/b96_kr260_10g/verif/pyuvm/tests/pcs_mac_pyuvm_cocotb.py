"""cocotb entry of the pyuvm bench (brief 123): one cocotb test per UVM test; the runner picks one with testcase= and sets SEED (and PYUVM_OUT, the record directory).
Each simulator process runs one UVM test with one seed, so coverage (a process-global in cocotb-coverage) is per run and merged afterwards."""
from __future__ import annotations

import os

import cocotb
from cocotb.clock import Clock
from pyuvm import uvm_root

from designs.b96_kr260_10g.verif.pyuvm.pcs_mac_pyuvm import env


async def _run(dut, name: str) -> None:
    env.CTX.update(dut=dut, seed=int(os.environ.get("SEED", "1")), out_dir=os.environ.get("PYUVM_OUT"))
    dut.rst_tx.value = 1; dut.rst_rx.value = 1; dut.direct.value = 0
    for sig in (dut.dx_d, dut.dx_c, dut.s_valid, dut.s_last, dut.s_poison, dut.s_data, dut.s_nb1, dut.gt_rx_d):
        sig.value = 0
    cocotb.start_soon(Clock(dut.clk, 6206, unit="ps").start())
    if os.environ.get("PYUVM_PROFILE"):
        import cProfile, pstats
        pr = cProfile.Profile(); pr.enable()
        await uvm_root().run_test(name)
        pr.disable(); pstats.Stats(pr).sort_stats("cumtime").print_stats(35)
    else:
        await uvm_root().run_test(name)
    test = uvm_root().uvm_test_top
    assert test.errors == 0, f"{name} seed {env.CTX['seed']}: {test.errors} errors"


def _make(name: str):
    async def t(dut):
        await _run(dut, name)
    t.__name__ = t.__qualname__ = name
    t.__doc__ = f"pyuvm test {name}"
    return cocotb.test()(t)


for _n in env.TESTS:
    globals()[_n] = _make(_n)
