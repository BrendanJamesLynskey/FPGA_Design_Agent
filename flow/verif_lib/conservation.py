"""Conservation invariant for cocotb benches (brief 189 item 4; idea from Edwards 2026, ch 18). The SystemVerilog twin is
fda_conservation.sv. frames in == frames out + frames the block counted as dropped + frames still inside it."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Conservation:
    """Count frames at the block's ports and check against the block's own drop counter and occupancy, once per clock.

    ``step(frame_in, frame_out, drop_count, in_flight)`` is called once per clock with the values sampled on the same edge. A None
    drop_count or in_flight (an unresolved X or Z read from the DUT) is a violation, not a pass."""
    n_in: int = 0
    n_out: int = 0
    violations: list[str] = field(default_factory=list)

    def step(self, frame_in: bool, frame_out: bool, drop_count: int | None, in_flight: int | None) -> bool:
        ok = True
        if drop_count is None or in_flight is None:
            ok = False
            msg = f"counter unresolved (drop_count={drop_count}, in_flight={in_flight}) after {self.n_in} frames in"
        else:
            ok = self.n_in == self.n_out + drop_count + in_flight
            msg = f"in={self.n_in} out={self.n_out} dropped={drop_count} in_flight={in_flight}"
        if not ok:
            self.violations.append(msg)
        self.n_in += bool(frame_in)
        self.n_out += bool(frame_out)
        return ok

    @property
    def ok(self) -> bool:
        return not self.violations
