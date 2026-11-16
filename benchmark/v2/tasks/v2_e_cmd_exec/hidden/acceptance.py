"""Hidden bench of the command executor: commands staged and run through the shell, the bank and the results compared with the model."""

from __future__ import annotations

import cocotb
from benchmark.lib.net_bench import RegEnv, seeded_rng
from model import CODE, DESIGN_ID, GO, P0, P1, RDATA, REFUSED, TICK, TLM, TYP, VIEW, Model

BANK = tuple(range(VIEW, VIEW + 8))


class Exec(RegEnv):
    def __init__(self, dut) -> None:
        super().__init__(dut, Model())

    async def run(self, typ: int, p0: int = 0, p1: int = 0, what: str = "", full: bool = False) -> None:
        await self.wr(TYP, typ)
        await self.wr(P0, p0)
        await self.wr(P1, p1)
        await self.wr(GO, 1)
        await self.regs((CODE, RDATA) + (BANK if full else (VIEW + 4, VIEW + 5)) + (TLM,), what)
        await self.led(self.m.led(), what)


@cocotb.test()
async def test_exec_identity_reset_state_and_the_view(dut):
    e = Exec(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs(tuple(range(9)) + BANK, "at reset")
    assert e.m.bank(6) == 100 and e.m.bank(0) == 0x55445031
    await e.run(2, 1, 5)
    await e.b.reset()
    e.m = Model()
    await e.regs(tuple(range(9)) + BANK, "after reset")


@cocotb.test()
async def test_exec_read_and_write_the_scratch_registers(dut):
    e = Exec(dut)
    await e.b.start()
    await e.run(2, 1, 0xDEADBEEF, "write 1")
    await e.run(2, 2, 0x00000001, "write 2")
    await e.run(2, 3, 0xFFFFFFFF, "write 3", full=True)
    for a in (0, 1, 2, 3):
        await e.run(1, a, 0x12345678, f"read {a}")
        assert e.m.rdata == (0x55445031 if a == 0 else e.m.reg[a])
    await e.run(2, 1, 0x80000000, "high bit", full=True)
    await e.run(1, 1, 0, "read it", full=True)
    assert e.m.rdata == 0x80000000


@cocotb.test()
async def test_exec_refusals_and_what_they_change(dut):
    e = Exec(dut)
    await e.b.start()
    await e.run(2, 1, 7, "good write")
    await e.run(1, 8, 0, "read 8", full=True)
    assert e.m.code == 3 and e.m.errs == 1 and e.m.rdata == 0
    await e.run(2, 8, 9, "write 8")
    await e.run(2, 0xFFFF, 9, "write 0xFFFF")
    await e.run(1, 0x0100, 9, "read 256: not register 0", full=True)
    assert e.m.code == 3
    for a in (0, 4, 5, 6, 7):
        await e.run(2, a, 0x11111111, f"write read-only {a}", full=True)
        assert e.m.code == 5
    for t in (0, 6, 7, 0x80, 0xFF, 0x100 - 1):
        await e.run(t, 1, 2, f"type {t}", full=True)
        assert e.m.code == 1
    await e.run(1, 1, 0, "scratch intact", full=True)
    assert e.m.rdata == 7 and e.m.cmds == 2 and e.m.errs == 15  # 4 refused accesses, 5 read-only writes, 6 unknown types


@cocotb.test()
async def test_exec_counters_read_before_counting_themselves(dut):
    e = Exec(dut)
    await e.b.start()
    await e.run(3, 0, 0, "status")
    await e.run(1, 4, 0, "read CMDS")
    assert e.m.rdata == 1 and e.m.cmds == 2
    await e.run(1, 8, 0, "read refused")
    await e.run(1, 5, 0, "read ERRS")
    assert e.m.rdata == 1 and e.m.cmds == 3
    await e.run(2, 4, 99, "write CMDS refused")
    await e.run(1, 5, 0, "ERRS now")
    assert e.m.rdata == 2
    await e.run(1, 7, 0, "read UPTIME")
    assert e.m.rdata == 0


@cocotb.test()
async def test_exec_telemetry_commands_and_period(dut):
    e = Exec(dut)
    await e.b.start()
    await e.run(4, 0, 0, "start, keep period", full=True)
    assert e.m.tlm == 1 and e.m.period == 100
    await e.run(5, 0, 0, "stop")
    assert e.m.tlm == 0
    await e.run(4, 2, 0, "start with 2: raised to 4", full=True)
    assert e.m.period == 4
    await e.run(4, 500, 0, "start with 500", full=True)
    assert e.m.period == 500
    await e.run(4, 0, 0, "start with 0 keeps 500, it does not fall back to the default", full=True)
    assert e.m.period == 500 and e.m.tlm == 1
    await e.run(4, 3, 0)
    await e.run(4, 4, 0)
    await e.run(4, 5, 0)
    await e.run(4, 0xFFFF, 0, "largest", full=True)
    assert e.m.period == 0xFFFF
    await e.run(5, 0x1234, 0x5678, "stop ignores its parameters")
    await e.run(1, 6, 0, "read PERIOD")
    assert e.m.rdata == 0xFFFF
    await e.run(2, 6, 7, "PERIOD is read only")
    await e.b.expect(TLM, 0, "still stopped")


@cocotb.test()
async def test_exec_ticks_refused_and_register_rules(dut):
    e = Exec(dut)
    await e.b.start()
    await e.wr(TICK, 200)
    await e.wr(TICK, 255)
    await e.wr(TICK, 0)
    await e.wr(TICK, 0x1234_5601)
    await e.regs(BANK, "uptime")
    assert e.m.uptime == 200 + 255 + 1
    await e.wr(REFUSED, 0)
    await e.wr(REFUSED, 77)
    await e.regs(BANK + (CODE,), "refused upstream")
    assert e.m.errs == 2
    await e.led(e.m.led(), "led")
    await e.wr(TYP, 0x1FF)
    await e.b.expect(TYP, 0xFF, "type keeps 8 bits")
    await e.wr(P0, 0xABCD_1234)
    await e.b.expect(P0, 0x1234, "first parameter keeps 16 bits")
    await e.wr(P1, 0xFFFF_FFFF)
    await e.b.expect(P1, 0xFFFF_FFFF, "second parameter keeps 32 bits")
    await e.poke_read_only((CODE, RDATA, TLM) + BANK, 0x7777)
    await e.regs(tuple(range(9)) + BANK, "read-only writes")
    await e.unmapped((0x09, 0x0F, 0x18, 0x40, 0x7F))


@cocotb.test()
async def test_exec_a_failed_command_leaves_the_result_of_the_last_one_visible_only_as_a_code(dut):
    e = Exec(dut)
    await e.b.start()
    await e.run(1, 1, 0, "read scratch zero")
    await e.wr(P1, 0xA5A5A5A5)
    await e.run(2, 2, 0x600D, "write 2")
    await e.run(1, 2, 0, "read 2", full=True)
    assert e.m.rdata == 0x600D
    await e.run(2, 9, 1, "refused: value cleared", full=True)
    assert e.m.rdata == 0 and e.m.code == 3
    await e.run(3, 0, 0, "status clears the read value", full=True)
    assert e.m.rdata == 0


@cocotb.test()
async def test_exec_random_mix(dut):
    e = Exec(dut)
    await e.b.start()
    rng = seeded_rng()
    for k in range(22):
        c = rng.randrange(8)
        if c == 0:
            await e.wr(TICK, rng.randrange(256))
        elif c == 1:
            await e.wr(REFUSED, 0)
        else:
            t = rng.choice([1, 1, 2, 2, 3, 4, 5, rng.randrange(256)])
            await e.run(t, rng.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, rng.randrange(65536)]), rng.getrandbits(32), f"random {k}", full=(k % 4 == 0))


@cocotb.test()
async def test_exec_reset_clears_every_register_and_unmapped_writes_do_nothing(dut):
    e = Exec(dut)
    await e.b.start()
    for a in (1, 2, 3):
        await e.run(2, a, 0x11 * a)
    await e.run(4, 9, 0)
    await e.run(1, 8, 0)
    await e.run(2, 0, 5)
    await e.run(9, 0, 0)
    await e.wr(TICK, 77)
    await e.wr(REFUSED, 0)
    await e.poke_unmapped((0x09, 0x0F, 0x18, 0x20, 0x40, 0x7F))
    await e.regs(tuple(range(9)) + BANK, "after unmapped writes")
    await e.b.reset()
    e.m = Model()
    await e.regs(tuple(range(9)) + BANK, "after reset")


@cocotb.test()
async def test_exec_register_number_is_checked_only_for_read_and_write(dut):
    e = Exec(dut)
    await e.b.start()
    for t in (3, 4, 5):
        await e.run(t, 0x0100 + t, 0, f"type {t} with a large first parameter", full=True)
        assert e.m.code == 0
    await e.run(9, 0x0100, 0, "unknown type, large parameter", full=True)
    assert e.m.code == 1
