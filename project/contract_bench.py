"""The checks a generated contract test runs (cocotb 2). Every check reads only the contract, never a model or the spec.

:mod:`project.contract_test` writes a small cocotb module per contract that calls these functions with the contract
embedded as data. What is checked:

- ``check_ports``: every contract port exists in the elaborated RTL with the contract's width (parameters applied);
- ``check_reset``: during and just after reset, every AXI4-Stream master's ``tvalid`` is 0, every slave's ``tready``
  is a known value, and every output with a ``reset_value`` has it;
- ``check_axis_slave``: under legal random traffic, ``tready`` is never unknown, and is 1 on every clock when the
  contract says ``backpressure: false``;
- ``check_axis_master``: with a random ``tready`` (when back-pressure is allowed), ``tvalid`` is never unknown, a
  stalled beat holds ``tvalid``, ``tdata``, ``tuser`` and ``tlast`` until it is taken (the AXI4-Stream hold rule), a
  master with ``source_gaps: false`` sends on every clock once it starts, and every packet has ``packet_beats`` beats;
- ``check_latency``: the first output beat comes exactly ``cycles`` (or within ``[lo, hi]``) after the first input
  beat, and nothing comes out before;
- ``check_throughput``: with ``out_per_in``, the number of output beats equals the input beats times the ratio, under
  random ``tready`` when back-pressure is allowed;
- ``check_registers``: over an AXI4-Lite or shell-window bus, every register reads its reset value; an RW register
  reads back what was written (within its fields); an RO register ignores writes; AXI responses are OKAY.

P0 limits: traffic runs on one clock per check (interfaces on other clocks are held idle); registers on ``bus: top``
are checked at integration, not here.
"""

from __future__ import annotations

import random
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from project.expr import evaluate

RESET_CYCLES = 5


# ---- helpers ------------------------------------------------------------------------------------------------------
def _val(h: Any) -> int | None:
    try:
        return int(h.value)
    except ValueError:
        return None


def _ports(c: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in c.get("ports") or []}


def _ifaces(c: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["name"]: f for f in c.get("interfaces") or []}


def _w(x: Any, params: dict[str, int]) -> int:
    return evaluate(x, params)


def _clock_port(c: dict[str, Any], clock: str) -> str:
    return next(k["port"] for k in c["clocks"] if k["name"] == clock)


def _period_ps(k: dict[str, Any]) -> int:
    mhz = float(k.get("max_mhz") or 100.0)
    p = int(round(1e6 / mhz))
    return p + (p % 2)


def _start_clocks(dut: Any, c: dict[str, Any]) -> None:
    """A clock per contract clock, at its max_mhz (cocotb ends the clock tasks with the test)."""
    for k in c["clocks"]:
        Clock(getattr(dut, k["port"]), _period_ps(k), unit="ps").start()


async def setup(dut: Any, c: dict[str, Any], params: dict[str, int]) -> None:
    """Start every clock at its contract rate, set every input to 0 (masters' tready to 1), hold every reset for
    ``RESET_CYCLES`` clocks of its own clock, release, and wait two clocks."""
    _start_clocks(dut, c)
    clk_ports = {k["port"] for k in c["clocks"]}
    rst = {r["port"]: r for r in c.get("resets") or []}
    ready_in = {f"{f['prefix']}_tready" for f in c.get("interfaces") or []
                if f.get("protocol") == "axi4-stream" and f.get("role") == "master"}
    ready_in |= {f"{f['prefix']}_{s}" for f in c.get("interfaces") or [] if f.get("protocol") == "axi4-lite"
                 for s in ("bready", "rready")}
    for n, p in _ports(c).items():
        if p["dir"] != "in" or n in clk_ports:
            continue
        if n in rst:
            getattr(dut, n).value = 1 if rst[n]["polarity"] == "active_high" else 0
        else:
            getattr(dut, n).value = 1 if n in ready_in else 0
    first = c["clocks"][0]["port"]
    for _ in range(RESET_CYCLES):
        await RisingEdge(getattr(dut, first))
    for n, r in rst.items():
        await RisingEdge(getattr(dut, _clock_port(c, r["clock"])))
        getattr(dut, n).value = 0 if r["polarity"] == "active_high" else 1
    for _ in range(2):
        await RisingEdge(getattr(dut, first))


# ---- ports and reset ----------------------------------------------------------------------------------------------
async def check_ports(dut: Any, c: dict[str, Any], params: dict[str, int]) -> None:
    bad = []
    for n, p in _ports(c).items():
        try:
            h = getattr(dut, n)
        except AttributeError:
            bad.append(f"port {n} does not exist in {c['module']}")
            continue
        want = _w(p.get("width", 1), params)
        if len(h) != want:
            bad.append(f"port {n} is {len(h)} bits; the contract says {want}")
    assert not bad, "; ".join(bad)


async def check_reset(dut: Any, c: dict[str, Any], params: dict[str, int]) -> None:
    bad: list[str] = []
    rst = {r["port"]: r for r in c.get("resets") or []}
    first = c["clocks"][0]["port"]
    # look inside reset: start the clocks and hold every reset
    _start_clocks(dut, c)
    for n, r in rst.items():
        getattr(dut, n).value = 1 if r["polarity"] == "active_high" else 0
    for n, p in _ports(c).items():
        if p["dir"] == "in" and n not in rst and n not in {k["port"] for k in c["clocks"]}:
            getattr(dut, n).value = 0
    for _ in range(RESET_CYCLES):
        await RisingEdge(getattr(dut, first))
    _reset_values(dut, c, "during reset", bad)
    for n, r in rst.items():
        getattr(dut, n).value = 0 if r["polarity"] == "active_high" else 1
    await RisingEdge(getattr(dut, first))
    _reset_values(dut, c, "on the first clock after reset", bad)
    assert not bad, "; ".join(dict.fromkeys(bad))


def _reset_values(dut: Any, c: dict[str, Any], when: str, bad: list[str]) -> None:
    for f in c.get("interfaces") or []:
        if f.get("protocol") != "axi4-stream":
            continue
        if f["role"] == "master":
            v = _val(getattr(dut, f"{f['prefix']}_tvalid"))
            if v != 0:
                bad.append(f"{f['name']}: {f['prefix']}_tvalid is {'unknown' if v is None else v} {when} (must be 0)")
        else:
            if _val(getattr(dut, f"{f['prefix']}_tready")) is None:
                bad.append(f"{f['name']}: {f['prefix']}_tready is unknown {when}")
    for n, p in _ports(c).items():
        if p["dir"] == "out" and p.get("reset_value") is not None:
            v = _val(getattr(dut, n))
            if v != p["reset_value"]:
                bad.append(f"{n} is {'unknown' if v is None else hex(v)} {when}; reset_value {p['reset_value']:#x}")


# ---- AXI4-Stream traffic ------------------------------------------------------------------------------------------
async def traffic(dut: Any, c: dict[str, Any], params: dict[str, int], clock: str, cycles: int, *,
                  gaps: bool | None = None, ready_random: bool = False, stop_after: int | None = None,
                  seed: int = 1) -> dict[str, list[dict[str, Any]]]:
    """Drive every AXI4-Stream slave on ``clock`` with legal traffic and every master's ``tready``; return, per
    interface, one sample per clock: {valid, ready, data, user, last} (``None`` for an unknown value).

    ``gaps`` None follows each slave's ``source_gaps``; ``stop_after`` stops each slave after that many beats;
    ``ready_random`` drives a random ``tready`` on masters whose contract allows back-pressure."""
    rnd = random.Random(seed)
    clk = getattr(dut, _clock_port(c, clock))
    ifs = [f for f in c.get("interfaces") or [] if f.get("protocol") == "axi4-stream" and f.get("clock") == clock]
    st: dict[str, dict[str, Any]] = {}
    for f in ifs:
        h = lambda s, f=f: getattr(dut, f"{f['prefix']}_{s}")       # noqa: E731
        st[f["name"]] = {"f": f, "h": h, "sent": 0, "pending": False, "beat": 0,
                         "dw": _w(f["tdata"]["width"], params),
                         "uw": len(h("tuser")) if f.get("tuser") else 0,
                         "pb": _w(f["packet_beats"], params) if f.get("packet_beats") else None}
    trace: dict[str, list[dict[str, Any]]] = {f["name"]: [] for f in ifs}

    def drive_slave(s: dict[str, Any]) -> None:
        f, h = s["f"], s["h"]
        g = f.get("source_gaps") if gaps is None else gaps
        if s["pending"]:
            return                                   # hold the beat until it is taken
        if stop_after is not None and s["sent"] >= stop_after:
            h("tvalid").value = 0
            return
        if g and rnd.random() < 0.3:
            h("tvalid").value = 0
            return
        h("tvalid").value = 1
        h("tdata").value = rnd.getrandbits(s["dw"])
        if s["uw"]:
            h("tuser").value = rnd.getrandbits(s["uw"])
        if f.get("tlast"):
            last = (s["beat"] % s["pb"] == s["pb"] - 1) if s["pb"] else rnd.random() < 0.125
            h("tlast").value = int(last)
        s["pending"] = True

    for s in st.values():
        if s["f"]["role"] == "slave":
            drive_slave(s)
        else:
            s["h"]("tready").value = 1
    for _ in range(cycles):
        await RisingEdge(clk)
        for name, s in st.items():
            f, h = s["f"], s["h"]
            smp = {"valid": _val(h("tvalid")), "ready": _val(h("tready")), "data": _val(h("tdata")),
                   "user": _val(h("tuser")) if f.get("tuser") else 0,
                   "last": _val(h("tlast")) if f.get("tlast") else 0}
            trace[name].append(smp)
            if f["role"] == "slave":
                if s["pending"] and smp["valid"] == 1 and smp["ready"] == 1:
                    s["pending"] = False
                    s["sent"] += 1
                    s["beat"] += 1
                drive_slave(s)
            else:
                rr = ready_random and f.get("backpressure")
                h("tready").value = int(rnd.random() < 0.6) if rr else 1
    return trace


def _cycles_for(c: dict[str, Any], params: dict[str, int]) -> int:
    n = 400
    for f in c.get("interfaces") or []:
        if f.get("packet_beats"):
            n = max(n, 2 * _w(f["packet_beats"], params) + 100)
    for L in c.get("latency") or []:
        hi = L["cycles"][1] if isinstance(L["cycles"], list) else L["cycles"]
        n = max(n, 2 * _w(hi, params) + 100)
    return min(n, 40000)


async def check_axis_slave(dut: Any, c: dict[str, Any], params: dict[str, int], iface: str) -> None:
    f = _ifaces(c)[iface]
    await setup(dut, c, params)
    tr = (await traffic(dut, c, params, f["clock"], _cycles_for(c, params), ready_random=True, seed=11))[iface]
    bad = []
    for i, s in enumerate(tr):
        if s["ready"] is None:
            bad.append(f"{iface}: tready unknown on clock {i}")
        elif not f.get("backpressure") and s["ready"] != 1:
            bad.append(f"{iface}: tready is 0 on clock {i}, but the contract says backpressure: false")
        if len(bad) >= 5:
            break
    assert not bad, "; ".join(bad)


async def check_axis_master(dut: Any, c: dict[str, Any], params: dict[str, int], iface: str) -> None:
    f = _ifaces(c)[iface]
    await setup(dut, c, params)
    tr = (await traffic(dut, c, params, f["clock"], _cycles_for(c, params), gaps=False, ready_random=True,
                        seed=12))[iface]
    bad: list[str] = []
    started = False
    beats_in_packet = 0
    packets = 0
    pb = _w(f["packet_beats"], params) if f.get("packet_beats") else None
    for i, s in enumerate(tr):
        if s["valid"] is None:
            bad.append(f"{iface}: tvalid unknown on clock {i}")
            break
        if i and tr[i - 1]["valid"] == 1 and tr[i - 1]["ready"] == 0:
            p = tr[i - 1]
            if s["valid"] != 1:
                bad.append(f"{iface}: tvalid dropped on clock {i} before the stalled beat was taken (AXI4-Stream hold rule)")
            elif (s["data"], s["user"], s["last"]) != (p["data"], p["user"], p["last"]):
                bad.append(f"{iface}: tdata/tuser/tlast changed on clock {i} while the beat was stalled "
                           f"(AXI4-Stream hold rule)")
        if s["valid"] == 1:
            started = True
        elif started and not f.get("source_gaps"):
            bad.append(f"{iface}: tvalid is 0 on clock {i} after the stream started, but the contract says "
                       "source_gaps: false")
        if s["valid"] == 1 and s["ready"] == 1:
            beats_in_packet += 1
            if s["last"] == 1:
                if pb and packets and beats_in_packet != pb:
                    bad.append(f"{iface}: a packet of {beats_in_packet} beats ending on clock {i}; packet_beats is {pb}")
                elif pb and not packets and beats_in_packet > pb:
                    bad.append(f"{iface}: the first packet has {beats_in_packet} beats, more than packet_beats {pb}")
                packets += 1
                beats_in_packet = 0
            elif pb and beats_in_packet > pb:
                bad.append(f"{iface}: no tlast after {pb} beats (packet_beats) on clock {i}")
                beats_in_packet = 0
        if len(bad) >= 5:
            break
    if not started:
        bad.append(f"{iface}: no beat came out in {len(tr)} clocks")
    if pb and not bad and packets < 2:
        bad.append(f"{iface}: fewer than two tlast beats in {len(tr)} clocks (packet_beats {pb})")
    assert not bad, "; ".join(bad)


async def check_latency(dut: Any, c: dict[str, Any], params: dict[str, int], index: int) -> None:
    L = c["latency"][index]
    fi, fo = _ifaces(c)[L["from"]], _ifaces(c)[L["to"]]
    lo, hi = (L["cycles"] if isinstance(L["cycles"], list) else [L["cycles"], L["cycles"]])
    lo, hi = _w(lo, params), _w(hi, params)
    await setup(dut, c, params)
    n_in = 1 if fi.get("source_gaps") else 4
    tr = await traffic(dut, c, params, fi["clock"], hi + n_in + 40, stop_after=n_in, seed=13)
    tin = next((i for i, s in enumerate(tr[L["from"]]) if s["valid"] == 1 and s["ready"] == 1), None)
    tout = next((i for i, s in enumerate(tr[L["to"]]) if s["valid"] == 1 and s["ready"] == 1), None)
    assert tin is not None, f"{L['from']}: no input beat was accepted"
    assert tout is not None, f"{L['to']}: no output beat within {hi + 40} clocks of the input (latency {lo}..{hi})"
    assert tout >= tin, f"{L['to']}: an output beat came {tin - tout} clocks before any input beat"
    assert lo <= tout - tin <= hi, (f"latency {L['from']} -> {L['to']} is {tout - tin} clocks; the contract says "
                                    f"{lo if lo == hi else f'{lo}..{hi}'}")


async def check_throughput(dut: Any, c: dict[str, Any], params: dict[str, int], index: int) -> None:
    t = c["throughput"][index]
    fi, fo = _ifaces(c)[t["from"]], _ifaces(c)[t["interface"]]
    hi = max([_w(L["cycles"][1] if isinstance(L["cycles"], list) else L["cycles"], params)
              for L in c.get("latency") or [] if L["from"] == t["from"] and L["to"] == t["interface"]] or [16])
    n_in = 200
    await setup(dut, c, params)
    tr = await traffic(dut, c, params, fo["clock"], n_in * 4 + hi + 60, ready_random=True, stop_after=n_in, seed=14)
    got_in = sum(1 for s in tr[t["from"]] if s["valid"] == 1 and s["ready"] == 1)
    got_out = sum(1 for s in tr[t["interface"]] if s["valid"] == 1 and s["ready"] == 1)
    want = got_in * t["out_per_in"]
    assert got_in == n_in, f"{t['from']}: only {got_in} of {n_in} input beats were accepted"
    assert got_out == want, (f"{t['interface']}: {got_out} output beats for {got_in} input beats; out_per_in "
                             f"{t['out_per_in']} means {want}")


# ---- registers ----------------------------------------------------------------------------------------------------
class _Bus:
    def __init__(self, dut: Any, c: dict[str, Any], f: dict[str, Any]):
        self.dut, self.f, self.pre = dut, f, f["prefix"]
        self.clk = getattr(dut, _clock_port(c, f["clock"]))
        self.errors: list[str] = []

    def h(self, s: str) -> Any:
        return getattr(self.dut, f"{self.pre}_{s}")

    async def write(self, addr: int, data: int) -> None:
        if self.f["protocol"] == "axi4-lite":
            dw = self.f.get("data_width", 32)
            self.h("awaddr").value, self.h("awvalid").value = addr, 1
            self.h("wdata").value, self.h("wstrb").value, self.h("wvalid").value = data, (1 << (dw // 8)) - 1, 1
            self.h("bready").value = 1
            aw = w = False
            for _ in range(100):
                await RisingEdge(self.clk)
                aw = aw or (_val(self.h("awready")) == 1)
                w = w or (_val(self.h("wready")) == 1)
                if aw:
                    self.h("awvalid").value = 0
                if w:
                    self.h("wvalid").value = 0
                if aw and w and _val(self.h("bvalid")) == 1:
                    break
            else:
                self.errors.append(f"write {addr:#x}: no write response in 100 clocks")
                return
            if not (aw and w and _val(self.h("bvalid")) == 1):
                for _ in range(100):
                    await RisingEdge(self.clk)
                    if _val(self.h("bvalid")) == 1:
                        break
            r = _val(self.h("bresp"))
            if r != 0:
                self.errors.append(f"write {addr:#x}: bresp {r} (not OKAY)")
            await RisingEdge(self.clk)
        else:
            self.h("addr").value, self.h("wdata").value, self.h("wr").value = addr, data, 1
            await RisingEdge(self.clk)
            self.h("wr").value = 0
            await RisingEdge(self.clk)

    async def read(self, addr: int) -> int | None:
        if self.f["protocol"] == "axi4-lite":
            self.h("araddr").value, self.h("arvalid").value, self.h("rready").value = addr, 1, 1
            ar = False
            for _ in range(100):
                await RisingEdge(self.clk)
                if not ar and _val(self.h("arready")) == 1:
                    ar = True
                    self.h("arvalid").value = 0
                if _val(self.h("rvalid")) == 1:
                    v, r = _val(self.h("rdata")), _val(self.h("rresp"))
                    if r != 0:
                        self.errors.append(f"read {addr:#x}: rresp {r} (not OKAY)")
                    if not ar:
                        self.h("arvalid").value = 0
                    await RisingEdge(self.clk)
                    return v
            self.errors.append(f"read {addr:#x}: no read data in 100 clocks")
            return None
        self.h("addr").value, self.h("rd").value = addr, 1
        await RisingEdge(self.clk)
        self.h("rd").value = 0
        await RisingEdge(self.clk)
        return _val(self.h("rdata"))


def _mask(r: dict[str, Any], width: int) -> int:
    if not r.get("fields"):
        return (1 << width) - 1
    m = 0
    for fl in r["fields"]:
        hi, lo = (fl["bits"], fl["bits"]) if isinstance(fl["bits"], int) else fl["bits"]
        m |= ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
    return m


async def check_registers(dut: Any, c: dict[str, Any], params: dict[str, int]) -> None:
    regs = c["registers"]
    f = _ifaces(c)[regs["bus"]]
    await setup(dut, c, params)
    bus = _Bus(dut, c, f)
    rnd = random.Random(15)
    dw = f.get("data_width", 32)
    bad: list[str] = []
    for r in regs["map"]:
        width = r.get("width", dw)
        if r["access"] == "WO" or r.get("volatile"):
            continue
        v = await bus.read(r["offset"])
        if v is None or (v & _mask(r, width)) != r.get("reset", 0) & _mask(r, width):
            bad.append(f"{r['name']} reads {'unknown' if v is None else hex(v)} after reset; reset {r.get('reset', 0):#x}")
    for r in regs["map"]:
        width = r.get("width", dw)
        m = _mask(r, width)
        if r["access"] == "RW":
            for pat in (rnd.getrandbits(width) & m, ~r.get("reset", 0) & m):
                await bus.write(r["offset"], pat)
                v = await bus.read(r["offset"])
                if v is None or (v & m) != pat:
                    bad.append(f"{r['name']} (RW): wrote {pat:#x}, read {'unknown' if v is None else hex(v & m)}")
        elif r["access"] == "RO" and not r.get("volatile"):
            await bus.write(r["offset"], ~r.get("reset", 0) & m)
            v = await bus.read(r["offset"])
            if v is None or (v & m) != r.get("reset", 0) & m:
                bad.append(f"{r['name']} (RO): changed to {'unknown' if v is None else hex(v & m)} after a write")
    bad += bus.errors
    assert not bad, "; ".join(bad)


__all__ = ["check_axis_master", "check_axis_slave", "check_latency", "check_ports", "check_registers", "check_reset",
           "check_throughput", "cocotb", "setup", "traffic"]
