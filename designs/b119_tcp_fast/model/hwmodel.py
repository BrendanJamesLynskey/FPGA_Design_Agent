"""A Python stand-in for rtl/tcp_fast.sv at the level of its register file and decisions, used to test the software side without a simulator (brief 119).

It has the block's bus (`write`, `read`) and an order input (`order`). It is untimed: a segment is complete the moment the order is presented, the template
is valid the moment it is armed, and the block is never busy. The RTL bench uses the real block instead and the same `Owner`.
"""
from __future__ import annotations

from designs.b119_tcp_fast.model import regs, tcpref
from designs.b119_tcp_fast.model.tcpref import Conn, FastModel


class ModelHw:
    def __init__(self, owner_records, send_frame):
        self.fast = FastModel()
        self.records, self.send_frame = owner_records, send_frame
        self.clk = 0
        self.dst_pending = {}

    async def write(self, addr: int, val: int) -> None:
        m, c = self.fast, self.fast.conn
        if addr == regs.CTRL:
            m.arm_req = bool(val & 1)
            if val & 1:
                m.valid = True
                m.refreshed_at = self.clk
        elif addr == regs.DMAC_HI:
            c.dmac = (val & 0xFFFF).to_bytes(2, "big") + c.dmac[2:]; m.valid = False
        elif addr == regs.DMAC_LO:
            c.dmac = c.dmac[:2] + val.to_bytes(4, "big"); m.valid = False
        elif addr == regs.SMAC_HI:
            c.smac = (val & 0xFFFF).to_bytes(2, "big") + c.smac[2:]; m.valid = False
        elif addr == regs.SMAC_LO:
            c.smac = c.smac[:2] + val.to_bytes(4, "big"); m.valid = False
        elif addr == regs.SIP:
            c.sip = val; m.valid = False
        elif addr == regs.DIP:
            c.dip = val; m.valid = False
        elif addr == regs.PORTS:
            c.sport, c.dport = val >> 16, val & 0xFFFF; m.valid = False
        elif addr == regs.TTL_MSS:
            c.mss, c.ttl = val >> 16, val & 0xFF; m.valid = False
        elif addr == regs.SND_NXT:
            m.snd_nxt = val
        elif addr == regs.SND_UNA:
            m.snd_una = val; m.refreshed_at = self.clk
        elif addr == regs.SND_WND:
            m.snd_wnd = val; m.refreshed_at = self.clk
        elif addr == regs.RCV_NXT:
            m.rcv_nxt = val; m.refreshed_at = self.clk
        elif addr == regs.RCV_WND:
            m.rcv_wnd = val & 0xFFFF; m.refreshed_at = self.clk
        elif addr == regs.IP_ID:
            m.ip_id = val & 0xFFFF
        elif addr == regs.STALE_LIMIT:
            m.stale_limit = val

    async def read(self, addr: int) -> int:
        m = self.fast
        if addr == regs.CTRL:
            return (regs.CTRL_ARM if m.arm_req else 0) | (regs.CTRL_VALID if m.valid else 0)
        return {regs.SND_NXT: m.snd_nxt, regs.SND_UNA: m.snd_una, regs.SND_WND: m.snd_wnd, regs.RCV_NXT: m.rcv_nxt, regs.RCV_WND: m.rcv_wnd,
                regs.IP_ID: m.ip_id}.get(addr, 0)

    def order(self, payload: bytes, now: int, abort: bool = False):
        """Present an order. Returns the frame sent, or None (refused, or aborted before it left)."""
        m = self.fast
        self.clk = now
        if abort:
            return None
        why = m.refusal(now)
        if why:
            m.counters[{1: "ref_arm", 2: "ref_stale", 3: "ref_win", 4: "ref_mss"}[why]] += 1
            return None
        fr = m.segment(payload)
        rec = m.complete(payload)
        self.records.append(rec)
        self.send_frame(fr)
        return fr
