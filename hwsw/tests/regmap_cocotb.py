"""cocotb bench for any generated register block (brief 64A). The bench reads the YAML (through hwsw.regmap) and talks
to the RTL only through the *generated* Python driver over an AXI4-Lite master with random VALID delays, random
AW/W order and random BREADY/RREADY back-pressure. The brief 59A AXI4-Lite checker watches the same wires; any rule
that fires fails the test.

Environment: REGMAP_YAML (the map), REGMAP_OUT (folder of the generated driver), REGMAP_LAYOUT (hw_in/hw_out
positions from regmap_tb.py), REGMAP_OPS (random operations in the soak, default 400), REGMAP_CDRV (optional: a C
driver program to co-simulate, see c_cosim_harness.c)."""
from __future__ import annotations

import importlib.util
import json
import os
import random
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

from hwsw import regmap

M = regmap.load(os.environ["REGMAP_YAML"])
LAY = json.loads(Path(os.environ["REGMAP_LAYOUT"]).read_text())
_spec = importlib.util.spec_from_file_location("drv", Path(os.environ["REGMAP_OUT"]) / f"{M.name}_regs.py")
DRV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DRV)
CLS = getattr(DRV, "Async" + "".join(w.capitalize() for w in M.name.split("_")) + "Regs")
OKAY, SLVERR = 0, 2
UNMAPPED_RESP = SLVERR if M.unmapped == "slverr" else OKAY


# ---- the bus ---------------------------------------------------------------------------------------------------------
class AxilMaster:
    """AXI4-Lite master: drives at falling edges, sees a handshake at the rising edge where VALID and READY are high.
    order: 'random' | 'together' | 'aw_first' | 'w_first'. p_ready: chance BREADY/RREADY is high in a cycle."""

    def __init__(self, dut, rng: random.Random, p_ready: float = 0.6, max_gap: int = 3):
        self.d, self.rng, self.p_ready, self.max_gap = dut, rng, p_ready, max_gap
        self.order = "random"
        self.strb = 0xF
        self.last_bresp = self.last_rresp = None
        self.log: list[tuple] = []

    async def _gap(self):
        for _ in range(self.rng.randint(0, self.max_gap)):
            await FallingEdge(self.d.aclk)

    async def _send(self, valid, payload: dict, ready):
        for k, v in payload.items():
            getattr(self.d, k).value = v
        valid.value = 1
        while True:
            await RisingEdge(self.d.aclk)
            if ready.value == 1:
                break
        await FallingEdge(self.d.aclk)
        valid.value = 0

    async def _resp(self, valid, ready, sample):
        while True:
            ready.value = 1 if self.rng.random() < self.p_ready else 0
            await RisingEdge(self.d.aclk)
            if valid.value == 1 and ready.value == 1:
                v = sample()
                await FallingEdge(self.d.aclk)
                ready.value = 0
                return v
            await FallingEdge(self.d.aclk)

    async def write32(self, offset: int, value: int, strb: int | None = None) -> int:
        d = self.d
        await FallingEdge(d.aclk)
        order = self.order if self.order != "random" else self.rng.choice(["together", "aw_first", "w_first"])
        aw = self._send(d.s_axil_awvalid, {"s_axil_awaddr": offset & (M.window_bytes - 1)}, d.s_axil_awready)
        w = self._send(d.s_axil_wvalid, {"s_axil_wdata": value & 0xFFFFFFFF,
                                         "s_axil_wstrb": self.strb if strb is None else strb}, d.s_axil_wready)
        if order == "together":
            t1, t2 = cocotb.start_soon(aw), cocotb.start_soon(w)
            await t1
            await t2
        else:
            first, second = (aw, w) if order == "aw_first" else (w, aw)
            await first
            await self._gap()
            await second
        resp = await self._resp(d.s_axil_bvalid, d.s_axil_bready, lambda: int(d.s_axil_bresp.value))
        self.last_bresp = resp
        self.log.append(("W", offset, value, resp))
        return resp

    async def read32(self, offset: int) -> int:
        d = self.d
        await FallingEdge(d.aclk)
        await self._gap()
        await self._send(d.s_axil_arvalid, {"s_axil_araddr": offset & (M.window_bytes - 1)}, d.s_axil_arready)
        v, resp = await self._resp(d.s_axil_rvalid, d.s_axil_rready,
                                   lambda: (int(d.s_axil_rdata.value), int(d.s_axil_rresp.value)))
        self.last_rresp = resp
        self.log.append(("R", offset, v, resp))
        return v


# ---- hardware side ---------------------------------------------------------------------------------------------------
def hw_out(dut, port: str) -> int:
    lsb, w = LAY["out"][port]
    return (int(dut.hw_out.value) >> lsb) & ((1 << w) - 1)


class HwIn:
    def __init__(self, dut):
        self.d, self.v = dut, 0

    def set(self, port: str, value: int):
        lsb, w = LAY["in"][port]
        m = ((1 << w) - 1) << lsb
        self.v = (self.v & ~m) | ((value << lsb) & m)
        self.d.hw_in.value = self.v

    async def pulse(self, port: str, value: int):
        await FallingEdge(self.d.aclk)
        self.set(port, value)
        await FallingEdge(self.d.aclk)
        self.set(port, 0)


class Pulses:
    """Counts, per W1P port bit, the clocks it is high."""

    def __init__(self, dut):
        self.d = dut
        self.ports = [p for p in LAY["out"] if p.endswith("_pulse_o")]
        self.count = {p: [0] * LAY["out"][p][1] for p in self.ports}
        cocotb.start_soon(self._run())

    async def _run(self):
        while True:
            await RisingEdge(self.d.aclk)
            if not self.ports:
                continue
            for p in self.ports:
                v = hw_out(self.d, p)
                for b in range(len(self.count[p])):
                    self.count[p][b] += (v >> b) & 1


class Checker:
    def __init__(self, dut):
        self.d, self.fired = dut, []
        cocotb.start_soon(self._run())

    async def _run(self):
        while True:
            await RisingEdge(self.d.aclk)
            v = int(self.d.viol.value)
            if v:
                self.fired.append((int(self.d.now.value), v))
                raise AssertionError(f"AXI4-Lite checker fired at cycle {int(self.d.now.value)}: rule bits {v:#05x} "
                                     "(axi_tx/rtl/axil_rules.sv: 0-4 hold, 5 B early, 6 R early, 7 reset, 8 EXOKAY, 9 in reset)")

    def assert_quiet(self):
        assert not self.fired, f"AXI4-Lite checker fired (cycle, rule bits): {self.fired[:5]}"
        assert int(self.d.chk_any.value) == 0, "AXI4-Lite checker latched a violation"


async def boot(dut, seed: int):
    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    dut.aresetn.value = 0
    dut.hw_in.value = 0
    for _ in range(4):
        await RisingEdge(dut.aclk)
    await FallingEdge(dut.aclk)
    dut.aresetn.value = 1
    rng = random.Random(seed)
    bus = AxilMaster(dut, rng)
    return rng, bus, CLS(bus), HwIn(dut), Pulses(dut), Checker(dut)


# ---- the reference model ---------------------------------------------------------------------------------------------
class Model:
    """What each register should read, from the YAML alone (the stored fields; RO from the bench's inputs)."""

    def __init__(self):
        self.st = {(r.name, f.name): f.reset for r in M.registers for f in r.fields if f.access in ("RW", "W1C", "W1S")}
        self.ro = {(r.name, f.name): 0 for r in M.registers for f in r.fields if f.hw_input}
        self.pulses = {}

    def read(self, rn: str) -> int:
        r = M.reg(rn)
        v = 0
        for f in r.fields:
            if f.access in ("RW", "W1C", "W1S"):
                v |= self.st[(rn, f.name)] << f.lsb
            elif f.access == "RO":
                v |= (f.reset if f.const else self.ro[(rn, f.name)]) << f.lsb
        return v

    def write(self, rn: str, value: int, strb: int):
        bits = 0
        for b in range(4):
            if strb >> b & 1:
                bits |= 0xFF << (8 * b)
        r = M.reg(rn)
        for f in r.fields:
            wv = ((value & bits) >> f.lsb) & ((1 << f.width) - 1)
            wm = (bits >> f.lsb) & ((1 << f.width) - 1)
            k = (rn, f.name)
            if f.access == "RW":
                self.st[k] = (self.st[k] & ~wm) | wv
            elif f.access == "W1C":
                self.st[k] &= ~wv
            elif f.access == "W1S":
                self.st[k] |= wv
            elif f.access == "W1P":
                p = f"{rn}_{f.name}".lower() + "_pulse_o"
                cnt = self.pulses.setdefault(p, [0] * f.width)
                for b in range(f.width):
                    cnt[b] += (wv >> b) & 1

    def irq(self) -> int:
        if not M.interrupt:
            return 0
        return int(self.read(M.interrupt["status"]) & self.read(M.interrupt["enable"]) != 0)


def mapped_offsets():
    return {r.offset for r in M.registers}


def check_outputs(dut, model: Model, where: str):
    for r in M.registers:
        for f in r.fields:
            if f.access in ("RW", "W1C", "W1S"):
                p = f"{r.name}_{f.name}".lower() + "_o"
                got, want = hw_out(dut, p), model.st[(r.name, f.name)]
                assert got == want, f"{where}: port {p} = {got:#x}, model {want:#x}"


# ---- tests -----------------------------------------------------------------------------------------------------------
@cocotb.test(timeout_time=2, timeout_unit="ms")
async def reset_values_and_outputs(dut):
    """Every register reads its YAML reset value through the driver; every stored field's port shows its reset."""
    rng, bus, drv, hw, pulses, chk = await boot(dut, 1)
    model = Model()
    check_outputs(dut, model, "after reset")
    for r in M.registers:
        got = await drv.read(r.name)
        assert got == r.reset, f"{r.name} reads {got:#010x} after reset, YAML says {r.reset:#010x}"
        assert bus.last_rresp == OKAY
    if M.interrupt:
        assert hw_out(dut, "irq_o") == 0
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def field_access_types(dut):
    """Directed: each access type behaves as documented, one field at a time, through the driver's own calls."""
    rng, bus, drv, hw, pulses, chk = await boot(dut, 2)
    model = Model()
    for r in M.registers:
        for f in r.fields:
            for _ in range(3):
                val = rng.getrandbits(f.width)
                if f.access == "RW":
                    await drv.set(r.name, f.name, val)
                    model.write(r.name, (model.read(r.name) & r.mask("RW") & ~f.mask) | (val << f.lsb), 0xF)
                    assert await drv.get(r.name, f.name) == val
                elif f.access == "RO":
                    if not f.const:
                        hw.set(f"{r.name}_{f.name}".lower() + "_i", val)
                        model.ro[(r.name, f.name)] = val
                    await drv.write(r.name, 0xFFFFFFFF ^ (r.mask("W1C") | r.mask("W1S") | r.mask("W1P")) )
                    model.write(r.name, 0xFFFFFFFF ^ (r.mask("W1C") | r.mask("W1S") | r.mask("W1P")), 0xF)
                    want = f.reset if f.const else val
                    assert await drv.get(r.name, f.name) == want, f"{r.name}.{f.name}: a write changed a RO field"
                elif f.access == "W1C":
                    p = f"{r.name}_{f.name}".lower()
                    await hw.pulse(p + "_set_i", val)
                    model.st[(r.name, f.name)] |= val
                    assert await drv.get(r.name, f.name) == model.st[(r.name, f.name)]
                    clr = rng.getrandbits(f.width)
                    await drv.clear(r.name, f.name, clr)
                    model.st[(r.name, f.name)] &= ~clr
                    assert await drv.get(r.name, f.name) == model.st[(r.name, f.name)], f"{p}: W1C clear"
                elif f.access == "W1S":
                    p = f"{r.name}_{f.name}".lower()
                    await drv.ring(r.name, f.name, val)
                    model.st[(r.name, f.name)] |= val
                    assert await drv.get(r.name, f.name) == model.st[(r.name, f.name)], f"{p}: W1S set"
                    clr = rng.getrandbits(f.width)
                    await hw.pulse(p + "_clr_i", clr)
                    model.st[(r.name, f.name)] &= ~clr
                    assert await drv.get(r.name, f.name) == model.st[(r.name, f.name)], f"{p}: W1S hardware clear"
                elif f.access == "W1P":
                    await drv.pulse(r.name, f.name, val)
                    model.write(r.name, (model.read(r.name) & r.mask("RW")) | (val << f.lsb), 0xF)
                    assert await drv.get(r.name, f.name) == 0, f"{r.name}.{f.name}: a W1P field must read 0"
                check_outputs(dut, model, f"{r.name}.{f.name} {f.access}")
    for _ in range(4):
        await RisingEdge(dut.aclk)
    for p, want in model.pulses.items():
        assert pulses.count[p] == want, f"{p}: pulses per bit {pulses.count[p]}, expected {want}"
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def set_beats_clear_in_the_same_clock(dut):
    """A hardware set (W1C) or a software set (W1S) in the clock of a clear leaves the bit set: no event is lost."""
    rng, bus, drv, hw, pulses, chk = await boot(dut, 3)
    for r in M.registers:
        for f in r.fields:
            if f.access not in ("W1C", "W1S"):
                continue
            p = f"{r.name}_{f.name}".lower()
            ones = (1 << f.width) - 1
            if f.access == "W1C":
                await hw.pulse(p + "_set_i", ones)

                async def race():                        # the hardware sets again exactly in the commit clock
                    while True:
                        await FallingEdge(dut.aclk)
                        if int(dut.u_dut.wr_commit.value) == 1:
                            hw.set(p + "_set_i", ones)
                            await FallingEdge(dut.aclk)
                            hw.set(p + "_set_i", 0)
                            return
                t = cocotb.start_soon(race())
                await drv.clear(r.name, f.name)
                await t
                assert await drv.get(r.name, f.name) == ones, f"{p}: a clear in the clock of a set lost the event"
                await drv.clear(r.name, f.name)
                assert await drv.get(r.name, f.name) == 0
            else:
                async def race():                        # the hardware clears exactly in the commit clock of a ring
                    while True:
                        await FallingEdge(dut.aclk)
                        if int(dut.u_dut.wr_commit.value) == 1:
                            hw.set(p + "_clr_i", ones)
                            await FallingEdge(dut.aclk)
                            hw.set(p + "_clr_i", 0)
                            return
                t = cocotb.start_soon(race())
                await drv.ring(r.name, f.name)
                await t
                assert await drv.get(r.name, f.name) == ones, f"{p}: a doorbell rung in the clock of a clear was lost"
                await hw.pulse(p + "_clr_i", ones)
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def byte_strobes(dut):
    """Partial-strobe writes change only the enabled bytes, for every access type that stores or acts."""
    rng, bus, drv, hw, pulses, chk = await boot(dut, 4)
    model = Model()
    for r in M.registers:
        for _ in range(8):
            strb = rng.getrandbits(4)
            v = rng.getrandbits(32)
            await bus.write32(r.offset, v, strb)
            assert bus.last_bresp == OKAY
            model.write(r.name, v, strb)
            got = await drv.read(r.name)
            assert got == model.read(r.name), f"{r.name}: strobe {strb:04b} value {v:#010x}: read {got:#010x}, " \
                                              f"model {model.read(r.name):#010x}"
            check_outputs(dut, model, f"{r.name} strobe {strb:04b}")
            # undo W1C/W1S state so the next strobe pattern sees fresh events
            for f in r.fields:
                if f.access == "W1C":
                    await hw.pulse(f"{r.name}_{f.name}".lower() + "_set_i", (1 << f.width) - 1)
                    model.st[(r.name, f.name)] = (1 << f.width) - 1
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def unmapped_addresses(dut):
    """Every unmapped word answers the map's unmapped response and reads 0; mapped registers are untouched."""
    rng, bus, drv, hw, pulses, chk = await boot(dut, 5)
    model = Model()
    holes = [o for o in range(0, M.window_bytes, 4) if o not in mapped_offsets()]
    sample = holes if len(holes) <= 64 else rng.sample(holes, 64)
    for o in sample:
        assert await bus.read32(o) == 0
        assert bus.last_rresp == UNMAPPED_RESP, f"read 0x{o:x}: resp {bus.last_rresp}"
        await bus.write32(o, 0xFFFFFFFF)
        assert bus.last_bresp == UNMAPPED_RESP, f"write 0x{o:x}: resp {bus.last_bresp}"
    for r in M.registers:
        assert await drv.read(r.name) == model.read(r.name), f"{r.name} changed by a write to an unmapped address"
        assert bus.last_rresp == OKAY
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def interrupt_line(dut):
    """irq_o is high exactly while an enabled status bit is set (registered: one clock after the cause)."""
    if not M.interrupt:
        return
    rng, bus, drv, hw, pulses, chk = await boot(dut, 6)
    st, en = M.reg(M.interrupt["status"]), M.reg(M.interrupt["enable"])
    model = Model()
    for _ in range(30):
        f = rng.choice(st.fields)
        act = rng.choice(["set", "clear", "enable", "disable"])
        if act == "set":
            await hw.pulse(f"{st.name}_{f.name}".lower() + "_set_i", 1)
            model.st[(st.name, f.name)] = 1
        elif act == "clear":
            await drv.clear(st.name, f.name)
            model.st[(st.name, f.name)] = 0
        else:
            ef = next(x for x in en.fields if x.lsb == f.lsb)
            await drv.set(en.name, ef.name, 1 if act == "enable" else 0)
            model.st[(en.name, ef.name)] = 1 if act == "enable" else 0
        await RisingEdge(dut.aclk)
        await FallingEdge(dut.aclk)
        assert hw_out(dut, "irq_o") == model.irq(), f"irq_o {hw_out(dut, 'irq_o')} after {act} {f.name}"
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def driver_rmw_keeps_pending_events(dut):
    """The driver's set() on a register that also holds W1C bits writes them as 0, so a pending event survives;
    a naive read-modify-write (write back what was read) clears it. This is the C header's RMW rule."""
    rng, bus, drv, hw, pulses, chk = await boot(dut, 7)
    mixed = [r for r in M.registers if r.mask("RW") and r.mask("W1C")]
    for r in mixed:
        rw = next(f for f in r.fields if f.access == "RW")
        ev = next(f for f in r.fields if f.access == "W1C")
        p = f"{r.name}_{ev.name}".lower() + "_set_i"
        await hw.pulse(p, 1)
        await drv.set(r.name, rw.name, 1)
        assert (await drv.get(r.name, ev.name)) & 1 == 1, f"{r.name}: driver set() cleared pending {ev.name}"
        v = await drv.read(r.name)
        await drv.write(r.name, v)                       # the naive pattern
        assert (await drv.get(r.name, ev.name)) & 1 == 0, f"{r.name}: the naive write-back should clear {ev.name}"
    chk.assert_quiet()


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def random_soak_against_model(dut):
    """Random mix of whole-word and strobed writes, reads, hardware events and input changes, every order and
    back-pressure, compared on every read with the model built from the YAML."""
    seed = int(os.environ.get("REGMAP_SEED", "11"))
    rng, bus, drv, hw, pulses, chk = await boot(dut, seed)
    model = Model()
    ops = int(os.environ.get("REGMAP_OPS", "400"))
    for i in range(ops):
        bus.p_ready = rng.choice([0.15, 0.5, 1.0])
        r = rng.choice(M.registers)
        k = rng.random()
        if k < 0.35:
            got = await drv.read(r.name)
            assert got == model.read(r.name), f"op {i}: {r.name} read {got:#010x}, model {model.read(r.name):#010x}"
        elif k < 0.7:
            v, strb = rng.getrandbits(32), rng.choice([0xF, 0xF, rng.getrandbits(4)])
            await bus.write32(r.offset, v, strb)
            model.write(r.name, v, strb)
            check_outputs(dut, model, f"op {i} write {r.name}")
        elif k < 0.85:
            ins = [(rr, f) for rr in M.registers for f in rr.fields if f.access in ("W1C", "W1S")]
            if ins:
                rr, f = rng.choice(ins)
                b = rng.getrandbits(f.width)
                pn = f"{rr.name}_{f.name}".lower() + ("_set_i" if f.access == "W1C" else "_clr_i")
                await hw.pulse(pn, b)
                if f.access == "W1C":
                    model.st[(rr.name, f.name)] |= b
                else:
                    model.st[(rr.name, f.name)] &= ~b
        else:
            ins = [(rr, f) for rr in M.registers for f in rr.fields if f.hw_input]
            if ins:
                rr, f = rng.choice(ins)
                b = rng.getrandbits(f.width)
                hw.set(f"{rr.name}_{f.name}".lower() + "_i", b)
                model.ro[(rr.name, f.name)] = b
        if M.interrupt and i % 7 == 0:
            await RisingEdge(dut.aclk)
            await FallingEdge(dut.aclk)
            assert hw_out(dut, "irq_o") == model.irq(), f"op {i}: irq_o"
    for _ in range(4):
        await RisingEdge(dut.aclk)
    for p, want in model.pulses.items():
        assert pulses.count[p] == want, f"{p}: pulses per bit {pulses.count[p]}, expected {want}"
    chk.assert_quiet()
    dut._log.info("soak: %d operations, %d bus transactions", ops, len(bus.log))


@cocotb.test(timeout_time=2, timeout_unit="ms")
async def c_driver_cosim(dut):
    """The C driver (compiled against the generated header, its bus access routed over a pipe) runs against the RTL;
    a small model of the accelerator answers START with BUSY and then DONE. Skipped when REGMAP_CDRV is not set."""
    exe = os.environ.get("REGMAP_CDRV")
    if not exe:
        return
    rng, bus, drv, hw, pulses, chk = await boot(dut, 8)

    async def accel():                                   # START -> BUSY for a while -> DONE event, LEVEL counts jobs
        jobs = 0
        while True:
            await RisingEdge(dut.aclk)
            if hw_out(dut, "cmd_start_pulse_o"):
                await FallingEdge(dut.aclk)
                hw.set("status_busy_i", 1)
                for _ in range(rng.randint(5, 40)):
                    await RisingEdge(dut.aclk)
                await FallingEdge(dut.aclk)
                hw.set("status_busy_i", 0)
                jobs += 1
                hw.set("status_level_i", jobs & 0xFF)
                await hw.pulse("irq_status_done_set_i", 1)
    cocotb.start_soon(accel())
    p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    served = 0
    while True:
        line = p.stdout.readline()
        if not line:
            break
        t = line.split()
        if t[0] == "R":
            v = await bus.read32(int(t[1], 16))
            p.stdin.write(f"{v:x} {bus.last_rresp}\n")
        elif t[0] == "W":
            await bus.write32(int(t[1], 16), int(t[2], 16))
            p.stdin.write(f"{bus.last_bresp}\n")
        elif t[0] == "I":                                # wait for the interrupt line (a UIO read() on the board)
            for n in range(int(t[1])):
                await RisingEdge(dut.aclk)
                if hw_out(dut, "irq_o"):
                    break
            p.stdin.write(f"{hw_out(dut, 'irq_o')}\n")
        elif t[0] == "DONE":
            rc = int(t[1])
            assert rc == 0, f"the C driver reported failure {rc}: {' '.join(t[2:])}"
            p.stdin.write("bye\n")
            break
        else:
            raise AssertionError(f"C driver protocol: unexpected line {line!r}")
        p.stdin.flush()
        served += 1
    p.wait(timeout=10)
    assert p.returncode == 0, f"C driver exited {p.returncode}"
    assert served > 20, f"only {served} bus requests from the C driver"
    dut._log.info("C driver: %d requests served", served)
    chk.assert_quiet()
