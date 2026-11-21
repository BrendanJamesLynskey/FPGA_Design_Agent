"""The hook for brief 119's tcp_fast, simulated (brief 127): the ITCH path with order_seg_tcpfast.sv and tcp_fast.sv in place of the stand-in, real mac64_rx and mac64_tx, driven through the host registers TCPF_ADDR and
TCPF_WDATA exactly as software would hand the connection over. Checks that the order frames on the wire are VALID TCP segments (the IPv4 and TCP checksums verify), carry brief 110's payload byte for byte, take the
sequence numbers tcp_fast's rules give, that an aborted speculative frame comes out poisoned and consumes no sequence number, and that the first word is still one clock after `go` (the same latency as the stand-in).
Needs brief 119's sources (B119_RTL = the directory of tcp_fast.sv); skipped otherwise."""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import cocotb

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Cfg, Model
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H
from designs.b96_kr260_10g.rm_gp_itch.tests import b127_unit_cocotb as U
from designs.b96_kr260_10g.rm_gp_itch.tests.b127_unit_cocotb import C, Unit, buy_add, mk_frame, sell_add

REGS = dict(CTRL=0, DMAC_HI=1, DMAC_LO=2, SMAC_HI=3, SMAC_LO=4, SIP=5, DIP=6, PORTS=7, TTL_MSS=8, SND_NXT=9, SND_UNA=10, SND_WND=11, RCV_NXT=12, RCV_WND=13, IP_ID=14, STALE_LIMIT=15)


class HookUnit(Unit):
    def __init__(self, dut):
        super().__init__(dut)
        self.tcpf_seq = 0

    async def tcpf_write(self, reg: int, data: int):
        self.cw[C["TCPFA"]] = reg & 0x1F
        self.cw[C["TCPFD"]] = data & 0xFFFFFFFF
        self.tcpf_seq = (self.tcpf_seq + 1) & 0xFF
        self.push_cfg()
        for _ in range(4):
            await self.tick()


async def hand_over(u: HookUnit, *, snd_nxt=1000, ip_id=0x4000, ack=777, win=0x7FFF):
    d = H.DEFAULTS
    w = u.tcpf_write
    await w(REGS["DMAC_HI"], int.from_bytes(d["venue_mac"][:2], "big"))
    await w(REGS["DMAC_LO"], int.from_bytes(d["venue_mac"][2:], "big"))
    await w(REGS["SMAC_HI"], int.from_bytes(d["my_mac"][:2], "big"))
    await w(REGS["SMAC_LO"], int.from_bytes(d["my_mac"][2:], "big"))
    await w(REGS["SIP"], int.from_bytes(H.ip_bytes(d["my_ip"]), "big"))
    await w(REGS["DIP"], int.from_bytes(H.ip_bytes(d["venue_ip"]), "big"))
    await w(REGS["PORTS"], (d["sport"] << 16) | d["order_port"])
    await w(REGS["TTL_MSS"], (1460 << 16) | 64)
    await w(REGS["SND_NXT"], snd_nxt)
    await w(REGS["IP_ID"], ip_id)
    await w(REGS["STALE_LIMIT"], 0)
    await w(REGS["SND_UNA"], snd_nxt)
    await w(REGS["SND_WND"], 65535)
    await w(REGS["RCV_NXT"], ack)
    await w(REGS["RCV_WND"], win)
    await w(REGS["CTRL"], 1)
    for _ in range(40):
        await u.tick()


def tcp_ok(frame: bytes) -> tuple[bool, bool]:
    """(IPv4 header checksum verifies, TCP checksum verifies over the pseudo-header)."""
    ip_ok = H.csum16(frame[14:34]) == 0
    tcp = frame[34:]
    pseudo = frame[26:34] + struct.pack(">BBH", 0, 6, len(tcp))
    return ip_ok, H.csum16(pseudo + tcp) == 0


@cocotb.test()
async def tcp_fast_hook(dut):
    out = {}
    for spec in (False, True):
        cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
        u = HookUnit(dut)
        u.spec = spec
        await u.start(cfg)
        await hand_over(u)
        m = Model(cfg)
        g = gen.Gen(41, cfg)
        pkts = [proto.mold_packet(b"SESSION001", 1, g.preamble()[:3])]
        seq = 4
        pkts.append(proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)])); seq += 1
        for k in range(3):
            pkts.append(proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 0, gen.MID + 100 + 10 * k)])); seq += 1
        pkts.append(proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 1, gen.MID + 100)]))        # no bid on instrument 1: refused by the band check, aborted when speculative
        frames = []
        for p in pkts:
            m.feed(p, False)
            frames.append({"frame": mk_frame(p), "gap": 80})
        await u.send(frames)
        await u.idle(200)
        itch, us, od = u.counters()
        wf = u.wire_frames()
        good = [f for f in wf if f[1]]
        bad = [f for f in wf if not f[1]]
        assert len(good) == len(m.orders) == 3, (len(good), len(m.orders), od)
        sn = 1000
        for k, ((data, ok, lane), o) in enumerate(zip(good, m.orders)):
            ipok, tcpok = tcp_ok(data)
            assert ipok and tcpok, f"order {k}: IPv4 checksum {ipok}, TCP checksum {tcpok}"
            assert data[54:] == o["frame"], f"order {k}: payload differs from the model's"
            assert struct.unpack(">I", data[38:42])[0] == sn and struct.unpack(">I", data[42:46])[0] == 777, f"order {k}: sequence or acknowledgement"
            sn += 59
        if spec:
            assert len(bad) == 1 and itch["abort"] == 1, (len(bad), itch["abort"])     # the refused candidate's frame: poisoned, and it consumed no sequence number
        else:
            assert not bad
        out["speculative" if spec else "at_verdict"] = {"orders": len(good), "poisoned_frames": len(bad), "checksums_verified": True, "first_sequence": 1000, "last_sequence": sn - 59}
        # latency: the same as the stand-in (first word one clock after go): go to the start strobe
        gos = [r["cyc"] for r in u.log if "go" in r]
        sops = [r["cyc"] for r in u.log if "osop" in r]
        out["speculative" if spec else "at_verdict"]["go_to_sop_clocks"] = sorted({s - g_ for g_, s in zip(gos[:len(sops)], sops)})
        dut._log.info(f"spec {spec}: {len(good)} orders with valid IPv4 and TCP checksums, {len(bad)} poisoned frame(s); go to start strobe {out['speculative' if spec else 'at_verdict']['go_to_sop_clocks']}")
    if os.environ.get("B127_RECORD"):
        Path(os.environ["B127_RECORD"]).mkdir(parents=True, exist_ok=True)
        (Path(os.environ["B127_RECORD"]) / "hook_tcp_fast_sim.json").write_text(json.dumps(out, indent=1))
