"""The slow path (brief 58A additions, "tick-to-config"): a strategy loop in software that recomputes rule parameters
from the board's book and writes them into the rule table. The FPGA keeps judging every message on whatever table is
committed; a message that arrives between a book change and the commit that follows it is judged on the old values.

The same code runs in the cocotb tests (against the RTL's register bus, with a modelled software delay) and later on
the bench (against the JTAG register bus, host/regs.py) or the KR260's PS. The strategy itself is a toy: it tracks an
exponentially weighted mid price of one instrument and asks for a buy when the ask falls `edge` below it. It is
stimulus for the timing, not a trading idea.
"""

from __future__ import annotations

from dataclasses import dataclass

from designs.b58a_trigger.model import rules as rl

REG_CTRL2 = 0x003
COMMIT = 1 << 5
REG_RULES = 0x040
REG_BOOK_INST, REG_BOOK = 0x030, 0x031
REG_VERSION, REG_COMMIT_TS, REG_TS = 0x006, 0x007, 0x005


@dataclass
class MidTracker:
    inst: int = 3
    edge: int = 25            # hundredths
    qty: int = 5
    alpha_num: int = 1        # EWMA weight alpha = alpha_num / alpha_den
    alpha_den: int = 4
    mid: int | None = None

    def update(self, bid_px: int, bid_sz: int, ask_px: int, ask_sz: int) -> dict | None:
        """New rule for this book entry, or None when the threshold does not change (nothing to write)."""
        if bid_sz == 0 or ask_sz == 0:
            return None
        m = (bid_px + ask_px) // 2
        new = m if self.mid is None else self.mid + (m - self.mid) * self.alpha_num // self.alpha_den
        if new == self.mid:
            return None
        self.mid = new
        th = new - self.edge
        return {"name": f"buy inst {self.inst} below mid-{self.edge / 100:.2f}", "match": {
                    "types": ["ADD", "MODIFY"], "side": "ask", "instrument": self.inst,
                    "price": {"op": "<", "value": f"{th / 100:.2f}"}},
                "action": {"order": {"side": "buy", "qty": self.qty, "price": {"mode": "message"}}, "log": True}}


def rule_writes(slot: int, rule: dict, limits: rl.Limits | None = None) -> list[tuple[int, int]]:
    """The register writes that load one rule into the shadow table, then commit."""
    w = rl.words(rl.validate(rule, limits))
    return [(REG_RULES + slot * 8 + i, v) for i, v in enumerate(w)] + [(REG_CTRL2, COMMIT)]


def book_entry(read) -> tuple[int, int, int, int]:
    """(bid_px, bid_sz, ask_px, ask_sz) of the instrument selected in REG_BOOK_INST, through a read(addr) callable."""
    return read(REG_BOOK), read(REG_BOOK + 1), read(REG_BOOK + 2), read(REG_BOOK + 3)
