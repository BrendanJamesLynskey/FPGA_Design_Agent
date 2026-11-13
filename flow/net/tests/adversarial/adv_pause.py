"""Independent review: 802.3x pause received in the middle of a transmission, and a zero-quanta pause ending a long pause."""
import struct
import cocotb
from cocotb.triggers import ReadOnly, RisingEdge, SimTimeoutError, Timer, with_timeout
from cocotb.utils import get_sim_time
from flow.net.tests.mac_rgmii_cocotb import setup, send_frame, PRE, OWN, fcs


def pause_wire(q):
    f = bytes.fromhex("0180c2000001") + bytes.fromhex("021111111111") + b"\x88\x08\x00\x01" + struct.pack(">H", q)
    f = f.ljust(60, b"\x00")
    return PRE + f + fcs(f)


@cocotb.test()
async def pause_mid_tx_and_zero(dut):
    phy = await setup(dut, 2)
    txm = cocotb.start_soon(phy.tx_monitor())
    queue = []

    async def rxdrv():
        while True:
            if queue:
                await phy.rx_frame(queue.pop(0))
            else:
                await phy.rx_idle(1)
    cocotb.start_soon(rxdrv())
    ev = {"first": [], "end": [], "paused_rise": [], "paused_fall": []}

    async def mon():
        p = 0
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            t = get_sim_time("ns")
            if int(dut.tx_first_pulse.value):
                ev["first"].append(t)
            if int(dut.rx_end_valid.value):
                ev["end"].append(t)
            q = int(dut.tx_paused.value)
            if q and not p:
                ev["paused_rise"].append(t)
            if p and not q:
                ev["paused_fall"].append(t)
            p = q
    cocotb.start_soon(mon())
    res = []
    big = bytes.fromhex("02990000000a") + OWN + b"\x08\x00" + bytes(i & 0xFF for i in range(1486))
    small = bytes.fromhex("02990000000a") + OWN + b"\x08\x00" + bytes(50)
    # A: start a 1500-byte frame; 200 byte times into it, a pause of 50 quanta (3200 byte times) arrives
    t_send = cocotb.start_soon(send_frame(dut, big))
    while not ev["first"]:
        await RisingEdge(dut.clk)
    for _ in range(200):
        await RisingEdge(dut.clk)
    queue.append(pause_wire(50))
    await t_send
    n_before = len(phy.tx_frames)
    await send_frame(dut, small)                       # offered at once: must wait for the pause
    for _ in range(4000):
        await RisingEdge(dut.clk)
    t_pause_end = ev["end"][-1]
    t_small = ev["first"][-1]
    held = (t_small - t_pause_end) / 8
    big_ok = any(f == PRE + big + fcs(big) for f in phy.tx_frames)
    res.append(("in-flight frame completes intact", big_ok, None))
    res.append(("next frame held >= 3200 byte times after the pause", 3200 <= held <= 3240, held))
    # B: a long pause (0xFFFF quanta), then a pause of 0 quanta 300 byte times later: transmission resumes at once
    queue.append(pause_wire(0xFFFF))
    while len(ev["end"]) < 2:
        await RisingEdge(dut.clk)
    for _ in range(300):
        await RisingEdge(dut.clk)
    await ReadOnly()
    res.append(("paused after 0xFFFF", int(dut.tx_paused.value) == 1, None))
    await RisingEdge(dut.clk)
    queue.append(pause_wire(0))
    while len(ev["end"]) < 3:
        await RisingEdge(dut.clk)
    t0 = ev["end"][-1]
    await Timer(1, unit="ns")
    try:                                    # a pause that is not cancelled would hold this for 4 million byte times
        await with_timeout(send_frame(dut, small), 20000, "ns")
    except SimTimeoutError:
        res.append(("zero quanta resumes at once", False, "still paused"))
        for r in res:
            dut._log.info(f"ADV {r[0]}: {'PASS' if r[1] else 'FAIL'} {r[2]}")
        assert False, "a zero-quanta pause did not end the pause"
    for _ in range(100):
        await RisingEdge(dut.clk)
    dt = (ev["first"][-1] - t0) / 8
    res.append(("zero quanta resumes at once", ev["first"][-1] > t0 and dt < 40, dt))
    for r in res:
        dut._log.info(f"ADV {r[0]}: {'PASS' if r[1] else 'FAIL'} {r[2]}")
    assert all(r[1] for r in res), [r[0] for r in res if not r[1]]
