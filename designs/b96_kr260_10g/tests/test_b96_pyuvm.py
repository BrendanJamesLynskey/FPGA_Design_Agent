"""The pyuvm bench of the PCS and MAC (brief 123, designs/b96_kr260_10g/verif/pyuvm): what CI can check, and a smoke run and one mutant kill where pyuvm is installed.

Without pyuvm (it is not a dependency of the repo): the bench's files are present, brief 112's mutants (which this bench reuses) still apply, and the reference
models and the Python channel agree with `model/pcs.py` and with one another (pure Python, no simulator). With pyuvm, cocotb-coverage and Icarus: the bench builds,
`t_smoke` passes with every scoreboard check non-trivial, and the seeded bug M01 is killed."""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from designs.b96_kr260_10g.model import pcs
from designs.b96_kr260_10g.verif.pyuvm.pcs_mac_pyuvm import channel, refmodels as ref

HERE = Path(__file__).parent
DESIGN = HERE.parent
PY = DESIGN / "verif" / "pyuvm"
UVM = DESIGN / "verif" / "uvm"
RTL = DESIGN / "rtl"
ROOT = DESIGN.parents[1]

needs_pyuvm = pytest.mark.skipif(importlib.util.find_spec("pyuvm") is None or importlib.util.find_spec("cocotb_coverage") is None,
                                 reason="pyuvm or cocotb-coverage not installed (pip install pyuvm cocotb-coverage)")


def test_bench_files_present() -> None:
    for rel in ("README.md", "tb/tb_pyuvm_top.sv", "pcs_mac_pyuvm/refmodels.py", "pcs_mac_pyuvm/channel.py", "pcs_mac_pyuvm/items.py", "pcs_mac_pyuvm/agents.py",
                "pcs_mac_pyuvm/scoreboard.py", "pcs_mac_pyuvm/cov.py", "pcs_mac_pyuvm/seqs.py", "pcs_mac_pyuvm/env.py", "pcs_mac_pyuvm/checker.py",
                "tests/pcs_mac_pyuvm_cocotb.py", "scripts/pyuvm_run.py", "scripts/run_regress.py"):
        assert (PY / rel).is_file(), rel
    assert (UVM / "mutants" / "mutants.tsv").is_file(), "the bench reuses brief 112's mutant list"


def test_tx_reference_is_the_rtl_encoder_not_the_python_model() -> None:
    """pcs_tx turns a lane-4 start into the all-error block; model/pcs.py encodes S4. The reference of this bench follows the RTL, the line agent can ask for S4."""
    d = int.from_bytes(bytes([pcs.IDLE] * 4 + [pcs.START, 0x55, 0x55, 0x55]), "little")
    assert ref.encode_rtl(d, 0x1F) == ref.err_block()
    assert ref.encode_rtl(d, 0x1F, with_s4=True) == pcs.encode_block(d, 0x1F) != ref.err_block()


def test_reftx_matches_pcs_model_on_frames() -> None:
    rng = random.Random(3)
    a, b = ref.RefTxPcs(), pcs.TxPcs()
    words = [pcs.IDLE_WORD] * 5
    for n in (60, 61, 99, 150):
        words += ref.frame_words(rng.randbytes(n)) + [pcs.IDLE_WORD] * 2
    for w in words * 3:
        assert a.step(*w) == b.step(*w)


def test_rx_reference_locks_and_frames_a_loopback_stream() -> None:
    """Transmit model -> channel (offset 5) -> RefRxPcs -> RefMacRx: the frames come back, FCS good, and the lock arrives."""
    rng = random.Random(4)
    frames = [rng.randbytes(n) for n in (60, 77, 200)]
    words = [pcs.IDLE_WORD] * 400
    for f in frames:
        words += ref.frame_words(f) + [pcs.IDLE_WORD] * 3
    words += [pcs.IDLE_WORD] * 40
    tx = ref.RefTxPcs()
    stream = []                                  # one GT word per clock; on the pause clock the offered word is not taken
    i = 0
    while i < len(words):
        a = tx.adv
        stream.append(tx.step(*words[i]) if a else tx.step(0, 0))
        i += 1 if a else 0
    ch, ctl, rx, mac, got = channel.LineChannel(), channel.Controls(), ref.RefRxPcs(), ref.RefMacRx(), []
    ctl.init_off = 5
    ch.step(True, 0, ctl)
    ch.step(False, 0, ctl)                     # the clock after reset: TXDATA still holds its reset value, which the channel skips
    for w in stream:
        word = ch.step(False, w, ctl)
        mac.step(rx.lock, rx.x_v, rx.x_d, rx.x_c)
        rx.step(word)
        got += [f for f in mac.done]
        mac.done.clear()
    assert rx.lock
    assert [f.data[:-4] for f in got if not f.aborted] == frames
    assert all(f.fcs_ok for f in got)


def test_channel_header_corruption_loses_lock() -> None:
    """Sixteen consecutive corrupted headers (the loss threshold) lose the lock of the reference receiver; the channel is the port of 112's line_channel.sv."""
    tx = ref.RefTxPcs()
    ch, ctl, rx = channel.LineChannel(), channel.Controls(), ref.RefRxPcs()
    ch.step(True, 0, ctl)
    ch.step(False, 0, ctl)
    losses = locks = 0
    for n in range(2500):
        ctl.hdr_load, ctl.hdr_cnt, ctl.hdr_skip = (n == 1500), (20 if n == 1500 else 0), 0
        w = ch.step(False, tx.step(*pcs.IDLE_WORD) if tx.adv else tx.step(0, 0), ctl)
        rx.step(w)
        losses += rx.ev["loss"]; locks += rx.ev["lock"]
    assert locks >= 1 and losses >= 1


def test_mutant_list_applies(tmp_path: Path) -> None:
    out = subprocess.run([sys.executable, str(UVM / "scripts" / "mutate.py"), "list"], capture_output=True, text=True, check=True).stdout
    ids = [line.split("\t")[0] for line in out.splitlines()]
    assert len(ids) == 17
    for m in ids:
        r = subprocess.run([sys.executable, str(UVM / "scripts" / "mutate.py"), "make", m, str(RTL), str(tmp_path / m)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


@needs_pyuvm
def test_pyuvm_smoke_and_a_mutant_kill(tmp_path: Path) -> None:
    """Build the bench in Icarus, run t_smoke (every check non-trivial, none failing), then build mutant M01 (poison polarity inverted) and require t_smoke to fail."""
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("pyuvm_run", PY / "scripts" / "pyuvm_run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    run.build(tmp_path / "clean")
    ok, _wall, _xml = run.run(tmp_path / "clean", "t_smoke", 1, tmp_path / "out")
    rec = json.loads((tmp_path / "out" / "t_smoke_seed1.json").read_text())
    assert ok and rec["errors"] == 0, rec
    assert all(rec["compared"][k] > 0 for k in ("TXMAC", "TXPCS", "RXPCS", "RXMAC", "E2E")), rec["compared"]
    subprocess.run([sys.executable, str(UVM / "scripts" / "mutate.py"), "make", "M01", str(RTL), str(tmp_path / "m01" / "rtl")], check=True)
    run.build(tmp_path / "m01" / "build", tmp_path / "m01" / "rtl")
    ok2, _w, _x = run.run(tmp_path / "m01" / "build", "t_smoke", 1, tmp_path / "out_m01", tmp_path / "m01" / "rtl")
    assert not ok2, "mutant M01 must be killed by t_smoke"
