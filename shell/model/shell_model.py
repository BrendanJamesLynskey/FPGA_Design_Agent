"""Pure-Python model of the test shell (shell/PROTOCOL.md), byte in, byte out.

The model is transaction-level: it sees the byte stream the host sends and
returns the bytes the shell sends back. Timing (UART bit time, the 1 ms frame
timeout) is a separate rule the cocotb tests check against the RTL; here an
explicit ``idle(seconds)`` call stands for a gap on the line.

The design under test is any object with ``window_read(offset) -> int`` and
``window_write(offset, value)``; ``offset`` is ADDR - 0x80 (0..127).
"""

from __future__ import annotations

from typing import Protocol

from shell.host import protocol as p


class Window(Protocol):
    def window_read(self, offset: int) -> int: ...
    def window_write(self, offset: int, value: int) -> None: ...


class RamWindow:
    """A plain read/write window (the shell's own testbench maps 16 of these)."""

    def __init__(self, size: int = 16) -> None:
        self.regs = [0] * size

    def window_read(self, offset: int) -> int:
        return self.regs[offset] if offset < len(self.regs) else 0

    def window_write(self, offset: int, value: int) -> None:
        if offset < len(self.regs):
            self.regs[offset] = value


class ShellModel:
    def __init__(self, design_id: int = 0, build_stamp: int = 0, window: Window | None = None,
                 timeout_s: float = 1e-3) -> None:
        self.timeout_s = timeout_s   # TIMEOUT_CYCLES = 100_000 at 100 MHz
        self.design_id = design_id
        self.build_stamp = build_stamp
        self.window = window if window is not None else RamWindow()
        self.reset()

    def reset(self) -> None:
        self.scratch = 0
        self.cnt = {"chk": 0, "req": 0, "frame": 0, "timeout": 0}
        self._buf: list[int] | None = None   # None = hunting for 0xA5

    @property
    def status_reg(self) -> int:
        c = self.cnt
        return c["chk"] | c["req"] << 8 | c["frame"] << 16 | c["timeout"] << 24

    def _inc(self, k: str) -> None:
        self.cnt[k] = min(self.cnt[k] + 1, 0xFF)

    def idle(self, seconds: float) -> None:
        """The line was idle this long: a part frame older than the timeout is dropped."""
        if self._buf is not None and seconds > self.timeout_s:
            self._inc("timeout")
            self._buf = None

    def framing_error(self) -> None:
        """A byte arrived with a low stop bit: it is lost and any part frame is dropped."""
        self._inc("frame")
        self._buf = None

    def feed(self, data: bytes) -> bytes:
        """Bytes arriving back to back (no gaps); returns every response produced.

        The host waits for each response, so bytes that would arrive while the shell
        is still answering are not modelled here.
        """
        out = b""
        for b in data:
            if self._buf is None:
                if b == p.SYNC_REQ:
                    self._buf = []
                continue
            self._buf.append(b)
            if len(self._buf) == p.REQ_LEN - 1:
                out += self._execute(bytes(self._buf))
                self._buf = None
        return out

    def _execute(self, f: bytes) -> bytes:
        cmd, addr, chk = f[0], f[1], f[6]
        data = int.from_bytes(f[2:6], "little")
        if p.xor8(f[:6]) != chk:
            self._inc("chk")
            return p.encode_response(p.ST_BAD_CHK)
        if cmd not in (p.CMD_READ, p.CMD_WRITE):
            self._inc("req")
            return p.encode_response(p.ST_BAD_CMD)
        write = cmd == p.CMD_WRITE
        if addr >= p.WINDOW_BASE:
            if write:
                self.window.window_write(addr - p.WINDOW_BASE, data)
                return p.encode_response(p.ST_OK, data)
            return p.encode_response(p.ST_OK, self.window.window_read(addr - p.WINDOW_BASE) & 0xFFFF_FFFF)
        ro = {p.REG_DESIGN_ID: self.design_id, p.REG_SHELL_VERSION: p.SHELL_VERSION,
              p.REG_BUILD_STAMP: self.build_stamp}
        if addr in ro:
            if write:
                self._inc("req")
                return p.encode_response(p.ST_READ_ONLY)
            return p.encode_response(p.ST_OK, ro[addr])
        if addr == p.REG_SCRATCH:
            if write:
                self.scratch = data
                return p.encode_response(p.ST_OK, data)
            return p.encode_response(p.ST_OK, self.scratch)
        if addr == p.REG_STATUS:
            if write:
                self.cnt = dict.fromkeys(self.cnt, 0)
                return p.encode_response(p.ST_OK, 0)
            return p.encode_response(p.ST_OK, self.status_reg)
        self._inc("req")
        return p.encode_response(p.ST_BAD_ADDR)
