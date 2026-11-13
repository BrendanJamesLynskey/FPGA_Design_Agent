"""cocotb bench for the fabric PRBS generator and checker (rtl/prbs64.sv) against model/prbs.py."""

from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from designs.b56a_gth_serdes.model import prbs as m


_clock = {}


async def reset(dut, sel):
    if "task" not in _clock or _clock["task"].done():                          # one clock per test (cocotb ends a test's tasks with it): a second driver would double the rate
        _clock["task"] = cocotb.start_soon(Clock(dut.clk, 6, unit="ns").start())
    dut.rst.value = 1; dut.sel.value = sel; dut.gen_en.value = 1; dut.chk_en.value = 1
    dut.force_err.value = 0; dut.flip.value = 0; dut.clr.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst.value = 0


async def run_words(dut, n):
    out = []
    for _ in range(n):
        await RisingEdge(dut.clk)
        out.append(int(dut.gen_data.value))
    return out


@cocotb.test()
async def generator_matches_model(dut):
    """Every polynomial: the words sent after reset equal the reference model's."""
    for sel in range(4):
        await reset(dut, sel)
        got = await run_words(dut, 44)
        want = m.words(sel, 40)
        offs = [o for o in range(4) if got[o:o + 39] == want[:39]]
        assert offs, f"{m.NAME[sel]}: the sent words do not start with the model's: {got[:3]} vs {want[:3]}"
        assert offs[0] >= 1, "the register shows its cleared value first"


def test_model_is_maximal_length():
    for sel in range(4):
        n = m.POLY[sel][0]
        if n <= 23:
            assert m.period(sel) == (1 << n) - 1, m.NAME[sel]


@cocotb.test()
async def locks_and_counts_clean(dut):
    """No errors: locks within 4+1 words, then counts words and no errors, for every polynomial."""
    for sel in range(4):
        await reset(dut, sel)
        await run_words(dut, 12)
        assert int(dut.locked.value) == 1, f"{m.NAME[sel]} not locked"
        w0 = int(dut.words.value)
        await run_words(dut, 100)
        assert int(dut.words.value) - w0 == 100
        assert int(dut.err_bits.value) == 0 and int(dut.err_words.value) == 0


@cocotb.test()
async def counts_exact_bit_errors(dut):
    """Injected flips are counted bit for bit (no tap multiplication), by the flip mask and by force_err."""
    await reset(dut, 3)
    await run_words(dut, 12)
    rnd = random.Random(7)
    expect_bits = expect_words = 0
    for _ in range(300):
        mask = 0
        if rnd.random() < 0.3:
            k = rnd.randint(1, 5)
            for b in rnd.sample(range(64), k):
                mask |= 1 << b
        dut.flip.value = mask
        expect_bits += bin(mask).count("1"); expect_words += mask != 0
        await RisingEdge(dut.clk)
    dut.flip.value = 0
    await run_words(dut, 4)
    assert int(dut.err_bits.value) == expect_bits, (int(dut.err_bits.value), expect_bits)
    assert int(dut.err_words.value) == expect_words
    assert int(dut.locked.value) == 1 and int(dut.lock_losses.value) == 0
    before = int(dut.err_bits.value)
    dut.force_err.value = 1
    await RisingEdge(dut.clk)
    dut.force_err.value = 0
    await run_words(dut, 6)
    assert int(dut.err_bits.value) == before + 1, "force_err flips exactly one bit of one word"
    dut.clr.value = 1
    await RisingEdge(dut.clk)
    dut.clr.value = 0
    await RisingEdge(dut.clk)
    assert int(dut.err_bits.value) == 0 and int(dut.words.value) <= 2 and int(dut.locked.value) == 1, "clr keeps the lock"


@cocotb.test()
async def loses_and_regains_lock(dut):
    """A burst of heavily corrupted words drops the lock (LOSS_WORDS words with LOSS_ERRS or more bits); clean data relocks."""
    await reset(dut, 2)
    await run_words(dut, 12)
    assert int(dut.locked.value) == 1
    dut.flip.value = 0x5555_5555_5555_5555             # 32 bad bits a word
    await run_words(dut, 8)
    assert int(dut.locked.value) == 0 and int(dut.lock_losses.value) == 1
    dut.flip.value = 0
    await run_words(dut, 16)
    assert int(dut.locked.value) == 1, "relocks on clean data"


@cocotb.test()
async def bit_slip_is_a_loss_of_lock(dut):
    """Data shifted by one bit (a slipped alignment) is not the sequence: the checker does not lock."""
    await reset(dut, 3)
    await run_words(dut, 12)
    assert int(dut.locked.value) == 1
    dut.chk_en.value = 0                               # drop one word at the checker: the sequence jumps 64 bits
    await RisingEdge(dut.clk)
    dut.chk_en.value = 1
    await run_words(dut, 12)
    assert int(dut.lock_losses.value) >= 1
