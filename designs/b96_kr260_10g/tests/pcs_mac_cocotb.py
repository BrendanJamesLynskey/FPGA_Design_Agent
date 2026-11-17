"""cocotb bench of the PCS and MAC (rtl/pcs_tx.sv, pcs_rx.sv, mac64_tx.sv, mac64_rx.sv) against model/pcs.py (brief 96).

The transmit chain is run first and its 64-bit GT words recorded; the words then go through a bit-level channel model (any bit
offset, bit errors) in Python and into the receive chain. Every comparison is against the Python reference, which is bit-serial."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b96_kr260_10g.model import pcs

IDLE_W = pcs.IDLE_WORD
LAT: dict = {}
PERIOD_PS = 6206


async def clocks(dut):
    cocotb.start_soon(Clock(dut.clk_tx, PERIOD_PS, unit="ps").start())
    cocotb.start_soon(Clock(dut.clk_rx, PERIOD_PS, unit="ps").start())


def idle_inputs(dut):
    dut.direct.value = 0; dut.dx_d.value = IDLE_W[0]; dut.dx_c.value = IDLE_W[1]
    dut.s_valid.value = 0; dut.s_data.value = 0; dut.s_last.value = 0; dut.s_nb1.value = 0; dut.s_poison.value = 0
    dut.gt_rx_d.value = 0


async def reset(dut, direct=0):
    idle_inputs(dut)
    dut.direct.value = direct
    dut.rst_tx.value = 1; dut.rst_rx.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk_tx)
    dut.rst_tx.value = 0; dut.rst_rx.value = 0
    await RisingEdge(dut.clk_tx)


async def tick(dut, clk=None):
    await RisingEdge(clk if clk is not None else dut.clk_tx)
    await Timer(500, unit="ps")


async def send_direct(dut, words, extra_idles=4):
    """Offer XGMII words directly to the PCS (taken only when adv is high); returns (GT words one per clock, the clock index at
    which each offered word was taken)."""
    dut.direct.value = 1
    out, taken = [], []
    seq = list(words) + [IDLE_W] * extra_idles
    i = 0
    k = 0
    while i < len(seq):
        await tick(dut)
        out.append(int(dut.gt_tx_d.value))
        d, c = seq[i]
        dut.dx_d.value = d; dut.dx_c.value = c
        if int(dut.adv.value):
            taken.append(k)
            i += 1
        k += 1
    await tick(dut)
    out.append(int(dut.gt_tx_d.value))
    dut.direct.value = 0
    return out, taken


async def send_frames(dut, frames, poison=None, tail_clocks=40, lead_clocks=0):
    """Drive the MAC with the frames; returns (GT words one per clock, sop clock indices, eop clock indices, adv list)."""
    gt, sops, eops, advs = [], [], [], []
    pend = list(frames)
    cur = None
    wi = 0
    fi = -1
    poison = poison or {}
    k = 0
    idle_after = 0
    while pend or cur is not None or idle_after < tail_clocks:
        await tick(dut)
        gt.append(int(dut.gt_tx_d.value)); advs.append(int(dut.adv.value))
        if int(dut.sop.value): sops.append(k)
        if int(dut.eop.value): eops.append(k)
        assert not int(dut.underrun.value), "MAC TX underrun"
        ready = int(dut.s_ready.value)
        if cur is None and pend and k >= lead_clocks:
            cur = pend.pop(0); wi = 0; fi += 1
            assert len(cur) >= 60
        if cur is not None:
            n = len(cur)
            lastw = wi * 8 + 8 >= n
            dut.s_valid.value = 1
            dut.s_data.value = int.from_bytes(cur[wi * 8: wi * 8 + 8].ljust(8, b"\0"), "little")
            dut.s_last.value = int(lastw)
            dut.s_nb1.value = (n - wi * 8 - 1) if lastw else 7
            dut.s_poison.value = int(poison.get(fi, False))
            if ready:
                wi += 1
                if wi * 8 >= n:
                    cur = None
        else:
            dut.s_valid.value = 0; dut.s_last.value = 0
            idle_after += 1 if not pend else 0
        k += 1
    dut.s_valid.value = 0
    return gt, sops, eops, advs


async def receive(dut, words, reset_first=True):
    """Drive the receive chain with the GT words, one per clock; returns the events (indices are the clock at which the word was captured)
    and, per clock, the receive PCS's registered output (x_v, x_d, x_c) for comparison with the model."""
    ev = {"frames": [], "ends": [], "errs": 0, "lock_at": None, "slips": 0, "losses": 0, "sh": 0, "type": 0, "os": 0,
          "sop_idx": [], "word_idx": [], "end_idx": [], "xs": [], "lens": []}
    accs, queue, cur = [], [], None
    if reset_first:
        dut.rst_rx.value = 1
        dut.gt_rx_d.value = 0
        for _ in range(3):
            await tick(dut, dut.clk_rx)
        dut.rst_rx.value = 0
    for i, w in enumerate(words):
        dut.gt_rx_d.value = w
        await tick(dut, dut.clk_rx)
        xv = int(dut.x_v.value)
        ev["xs"].append((xv, int(dut.x_d.value) if xv else None, int(dut.x_c.value) if xv else None))
        if int(dut.ev_lock.value) and ev["lock_at"] is None:
            ev["lock_at"] = i
        ev["slips"] += int(dut.ev_slip.value); ev["losses"] += int(dut.ev_loss.value)
        ev["sh"] += int(dut.ev_sh_err.value); ev["type"] += int(dut.ev_type_err.value); ev["os"] += int(dut.ev_os.value)
        if int(dut.rx_sop.value):
            cur = bytearray(); accs.append(cur); queue.append(len(accs) - 1); ev["sop_idx"].append(i)
        if int(dut.m_v.value):
            nb = int(dut.m_nb.value)
            if cur is None:
                cur = bytearray(); accs.append(cur); queue.append(len(accs) - 1)
            if int(dut.m_sof.value):
                ev["word_idx"].append(i)
            cur += int(dut.m_d.value).to_bytes(8, "little")[:nb]
        if int(dut.m_err.value):
            ev["errs"] += 1
            if queue:
                queue.pop()                                   # the frame in progress is abandoned
            cur = None
        if int(dut.m_end.value):                              # m_end can arrive after the next frame has started: pair ends with frames in order
            ev["ends"].append((int(dut.m_fcs_ok.value), int(dut.m_len.value)))
            ev["frames"].append(bytes(accs[queue.pop(0)]) if queue else b""); ev["end_idx"].append(i)
    return ev


def channel(words, offset, flips=()):
    bits = pcs.words_to_bits(words)[offset:]
    for f in flips:
        bits[f] ^= 1
    return pcs.bits_to_words(bits)


def model_tx(words, extra=4):
    """The reference model fed the same XGMII words (taken when adv): returns (output words, the model step index of each take)."""
    tx = pcs.TxPcs()
    out, taken = [], []
    seq = list(words) + [IDLE_W] * extra
    i = 0
    while i < len(seq):
        a = tx.adv
        out.append(tx.step(*seq[i]) if a else tx.step(0, 0))
        if a:
            taken.append(len(out) - 1)
            i += 1
    return out, taken


@cocotb.test()
async def pcs_tx_matches_model(dut):
    """The transmit PCS emits the reference model's words, clock for clock, for random XGMII streams (frames, idles, errors)."""
    await clocks(dut)
    rng = random.Random(21)
    await reset(dut, direct=1)
    words = [IDLE_W] * 40
    for _ in range(30):
        f = bytes(rng.getrandbits(8) for _ in range(rng.randrange(60, 120)))
        words += pcs.frame_words(f) + [IDLE_W] * rng.randrange(1, 4)
    words += [(sum(pcs.ERR << (8 * i) for i in range(8)), 0xFF)] * 3 + [IDLE_W] * 10
    got, taken = await send_direct(dut, words)
    want, _ = model_tx([IDLE_W] * 2 + words)     # the DUT took two idle words between reset and the first offered word
    dut._log.info('first mismatch ' + str(next((i for i in range(min(len(got), len(want) - 1)) if got[i] != want[i + 1]), None)) + ' of ' + str(len(got)))
    pairs = [(g, w) for g in range(0, 4) for w in range(0, 4) if got[g:g + 400] == want[w:w + 400]]
    assert pairs, f"differ: got {[hex(x) for x in got[:5]]} want {[hex(x) for x in want[:5]]}"
    assert pairs[0] == (0, 1), f"the RTL output must equal the model's output one step later, not a searched offset: {pairs[:4]}"
    g, w = pairs[0]
    m = min(len(got) - g, len(want) - w) - 5
    assert got[g:g + m] == want[w:w + m], "the words differ somewhere after the start"
    # the pause: adv low exactly once in 33 clocks
    gaps = [b - a for a, b in zip(taken, taken[1:])]
    assert gaps.count(2) >= len(gaps) // 33 - 1 and set(gaps) <= {1, 2}


def lead(n_idle_words):
    return [IDLE_W] * n_idle_words


def py_stream(items, lead_words=1500, tail=60):
    """The reference transmitter's GT words for: idles, then the XGMII word lists in `items`, then idles."""
    words = lead(lead_words)
    for it in items:
        words += it + [IDLE_W] * 3
    words += lead(tail)
    out, _ = model_tx(words)
    return out, words


@cocotb.test()
async def receive_matches_model_cycle_exact(dut):
    """The receive PCS equals the reference model clock for clock (lock, slips, decoded blocks), with bit errors and a header burst."""
    await clocks(dut)
    rng = random.Random(33)
    frames = [bytes(rng.getrandbits(8) for _ in range(rng.randrange(60, 200))) for _ in range(20)]
    ws, _ = py_stream([pcs.frame_words(f) for f in frames], lead_words=1500)
    bits = pcs.words_to_bits(ws)[7:]
    for k in range(1550, 1580):                 # a burst of invalid headers: loses lock, re-locks
        bits[66 * k - 7] = bits[66 * k - 6] = 0
    bits = bits[:]
    for f in (900, 5000, 9000, 14000, 100000):
        bits[f] ^= 1
    words = pcs.bits_to_words(bits)
    ev = await receive(dut, words)
    rx = pcs.RxPcs()
    for w in words:
        rx.step(w)
    assert ev["xs"] == rx.xs, next((i for i, (a, b) in enumerate(zip(ev["xs"], rx.xs)) if a != b), None)
    assert ev["slips"] == rx.fsm.slips and ev["losses"] == rx.fsm.losses
    assert ev["losses"] >= 1 and rx.fsm.lock
    assert ev["sh"] == rx.sh_err and ev["type"] == rx.type_err


@cocotb.test()
async def lanes_and_starts(dut):
    """Frames of 60..140 bytes (every terminate lane), started in lane 0 and in lane 4, any bit offset, arrive intact with good FCS."""
    await clocks(dut)
    rng = random.Random(8)
    frames, items = [], []
    for n in list(range(60, 76)) + [100, 137, 1500]:      # every length residue mod 8, each with a lane-0 and a lane-4 start
        for lane0 in (True, False):
            f = bytes(rng.getrandbits(8) for _ in range(n))
            frames.append(f); items.append(pcs.frame_words(f, lane0=lane0))
    ws, words = py_stream(items, lead_words=1500)
    for off in (0, 1, 33, 65):
        got = await receive(dut, channel(ws, off))
        good = [f for f, (ok, ln) in zip(got["frames"], got["ends"]) if ok]
        assert got["errs"] == 0
        assert [bytes(f[:-4]) for f in got["frames"][-len(frames):]] == frames, f"offset {off}: {len(got['frames'])} frames"
        assert all(ok == 1 and ln == len(f) + 4 for (ok, ln), f in zip(got["ends"][-len(frames):], frames))
        assert len(good) == len(got["frames"])


@cocotb.test()
async def mac_tx_through_pcs(dut):
    """The MAC transmitter's frames (every length), through the transmit and receive PCS at several offsets, arrive intact; a poisoned frame fails its FCS."""
    await clocks(dut)
    rng = random.Random(5)
    frames = [bytes(rng.getrandbits(8) for _ in range(n)) for n in list(range(60, 82)) + [200, 1514]]
    await reset(dut)
    # lock needs an idle lead: the MAC idles for 1500 clocks (lock takes at most 275 clocks, results/b96/lock_time_model.json) before the frames
    gt, sops, eops, advs = await send_frames(dut, frames, poison={3: True}, lead_clocks=1500)
    # TX latency through the real MAC + PCS, measured by decoding the GT words with the reference receiver: the clock at which the GT
    # word that holds the last bit of the start block is visible, minus the clock at which the preamble is in the MAC's output register
    rxm = pcs.RxPcs()
    for w in gt:
        rxm.step(w)
    start_x = [i for i, (v, d, c) in enumerate(rxm.xs) if v and c == 0x01 and (d & 0xFF) == pcs.START]
    lat_last = [(i - 1) - sp for i, sp in zip(start_x[-len(sops):], sops)]
    LAT["tx_mac_to_gt_last_bit_clocks"] = sorted(set(lat_last))
    assert len(start_x) >= len(sops) and set(lat_last) <= {2, 3}, lat_last
    dut._log.info(f'TX latency over the frames: {sorted(set(lat_last))}')
    dut._log.info(f'TX: {len(sops)} sops {len(eops)} eops of {len(frames)}; sops {sops[:8]} eops {eops[:8]} gt {len(gt)}')
    # idle gaps between frames: the MAC's IFG (eop to the next sop) is at least 12 byte times = 2 words
    for e, s in zip(eops, sops[1:]):
        assert s - e >= 2, (s, e)
    for off in (0, 7, 64):
        got = await receive(dut, channel(gt, off))
        dut._log.info(f'RX off {off}: frames {len(got["frames"])} errs {got["errs"]} lock {got["lock_at"]} ends {got["ends"][:6]}')
        assert got["errs"] == 0
        assert len(got["frames"]) >= len(frames) - 1
        ok = [(f[:-4], o) for f, (o, ln) in zip(got["frames"], got["ends"])]
        want = {f: True for f in frames}
        want[frames[3]] = False
        tail = ok[-len(frames):]
        assert [t[0] for t in tail] == frames
        assert [t[1] for t in tail] == [i != 3 for i in range(len(frames))]



@cocotb.test()
async def tx_latency_all_phases(dut):
    """Transmit latency over many gearbox phases: frames of 60 bytes sent every few clocks (the one-in-33 pause lands in all positions); the last bit of the
    start block is on TXDATA 2 clocks after the preamble is in the MAC's register, or 3 when the pause falls on that clock."""
    await clocks(dut)
    await reset(dut)
    rng = random.Random(77)
    frames = [bytes(rng.getrandbits(8) for _ in range(60 + (i % 7))) for i in range(120)]
    gt, sops, eops, advs = await send_frames(dut, frames, lead_clocks=600)
    rxm = pcs.RxPcs()
    for w in gt:
        rxm.step(w)
    start_x = [i for i, (v, d, c) in enumerate(rxm.xs) if v and c == 0x01 and (d & 0xFF) == pcs.START]
    assert len(start_x) >= len(sops) - 2
    lat = [(i - 1) - sp for i, sp in zip(start_x[-len(sops):], sops)]
    pause_at_sop = [advs[sp] == 0 for sp in sops]
    LAT["tx_mac_to_gt_last_bit_clocks_all_phases"] = sorted(set(lat))
    dut._log.info(f"TX latency set {sorted(set(lat))}; preamble offered on a pause clock in {sum(pause_at_sop)} of {len(sops)} frames")
    assert set(lat) == {2, 3}, set(lat)
    assert all((l == 3) == p for l, p in zip(lat, pause_at_sop))


@cocotb.test()
async def latency_by_gearbox_phase(dut):
    """Receive latency in clocks, for the start block at each of the 33 gearbox phases: the word that holds the last bit of the start
    block is captured at edge i; the MAC's start strobe is at i+2 and its first data word register holds the first word at i2+2 (i2: capture
    edge of the next block's last bit). Also the lock time in clocks at bit offset 0."""
    await clocks(dut)
    rng = random.Random(11)
    res = {"rx_start_strobe_clocks": set(), "rx_first_word_after_its_block_clocks": set(), "lock_clocks_offset0": []}
    for ph in range(33):
        f = bytes(rng.getrandbits(8) for _ in range(80))
        lead_n = 150 + ph
        ws, words = py_stream([pcs.frame_words(f)], lead_words=lead_n, tail=40)
        j = next(i for i, (d, c) in enumerate(words) if c == 0x01)                  # block index of the start block
        got = await receive(dut, ws)
        assert [x[:-4] for x in got["frames"]] == [f]
        i_last = (66 * j + 65) // 64
        i_next = (66 * (j + 1) + 65) // 64
        res["rx_start_strobe_clocks"].add(got["sop_idx"][0] - i_last)
        res["rx_first_word_after_its_block_clocks"].add(got["word_idx"][0] - i_next)
        res["lock_clocks_offset0"].append(got["lock_at"])
    out = {"rx_start_strobe_clocks_after_last_bit_captured": sorted(res["rx_start_strobe_clocks"]),
           "rx_first_data_word_clocks_after_its_block_captured": sorted(res["rx_first_word_after_its_block_clocks"]),
           "lock_clocks_offset0_min": min(res["lock_clocks_offset0"]), "lock_clocks_offset0_max": max(res["lock_clocks_offset0"]),
           "phases": 33, **{k: v for k, v in LAT.items()}}
    dut._log.info("LATENCY " + json.dumps(out))
    assert out["rx_start_strobe_clocks_after_last_bit_captured"] == [2], out
    assert out["rx_first_data_word_clocks_after_its_block_captured"] == [2], out
    if os.environ.get("B96_WRITE_RESULTS"):
        Path(os.environ["B96_WRITE_RESULTS"]).write_text(json.dumps(out, indent=1) + "\n")
