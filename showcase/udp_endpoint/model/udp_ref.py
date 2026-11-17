"""Bit-exact reference model of the UDP command and telemetry endpoint (brief 82, ladder project 3).

Integers and bytes only. The model is the specification in executable form: ``Endpoint`` is what the logic behind the
Ethernet blocks must do with the payload of each UDP datagram, and ``protocol.md`` (generated from the constants below by
``protocol_text``) is the datasheet a host programmer reads. The hardware sees a datagram payload as a byte stream whose last
byte carries a ``last`` flag; that is the interface of ``ip_lib/ipv4_udp_rx`` (``m_axis``) and ``ip_lib/ipv4_udp_tx``.

Wire format (all multi-byte numbers big-endian except the CRC, which is little-endian like the Ethernet FCS):

    command   TYPE(1) LEN(1) SEQ(2) PAYLOAD(LEN) CRC32(4)         CRC over everything before it
    response  TYPE|0x80(1) STATUS(1) SEQ(2) LEN(1) PAYLOAD(LEN) CRC32(4)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- constants (every one is stated in protocol.md) ----------------------------------------------------------------------
READ, WRITE, STATUS, TLM_START, TLM_STOP = 1, 2, 3, 4, 5
TLM_TYPE = 0x40                      # telemetry frames carry type 0x40 | 0x80
RESP_FLAG = 0x80
OK, BAD_TYPE, BAD_LEN, BAD_ADDR, BAD_SEQ, READ_ONLY = range(6)
ERROR_NAMES = {OK: "OK", BAD_TYPE: "BAD_TYPE", BAD_LEN: "BAD_LEN", BAD_ADDR: "BAD_ADDR", BAD_SEQ: "BAD_SEQ", READ_ONLY: "READ_ONLY"}
MAX_PAYLOAD = 8                      # commands carry at most this many payload bytes; a larger LEN field is an oversize packet
HEADER = 4
CRC_BYTES = 4
EXPECT_LEN = {READ: 2, WRITE: 6, STATUS: 0, TLM_START: 2, TLM_STOP: 0}
N_REGS = 8
REG_ID, REG_S0, REG_S1, REG_S2, REG_CMDS, REG_ERRS, REG_PERIOD, REG_UPTIME = range(8)
READ_ONLY_REGS = {REG_ID, REG_CMDS, REG_ERRS, REG_PERIOD, REG_UPTIME}
ID_VALUE = 0x55445031                # "UDP1"
PERIOD_DEFAULT, PERIOD_MIN = 100, 4  # telemetry period in ticks
SEQ_SPAN = 0x8000                    # a sequence number is newer when (seq - last) mod 65536 is in 1 .. 0x7FFF
COUNTERS = ("ok", "bad_crc", "truncated", "oversize", "replay", "out_of_order", "protocol")


def crc32(data: bytes, crc: int = 0) -> int:
    """IEEE 802.3 CRC-32 (reflected, polynomial 0xEDB88320, init and final xor 0xFFFFFFFF); ``crc`` continues a message."""
    c = crc ^ 0xFFFFFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ (0xEDB88320 if c & 1 else 0)
    return c ^ 0xFFFFFFFF


def build_command(typ: int, seq: int, payload: bytes = b"") -> bytes:
    body = bytes([typ, len(payload), seq >> 8 & 0xFF, seq & 0xFF]) + payload
    return body + crc32(body).to_bytes(4, "little")


def build_response(typ: int, status: int, seq: int, payload: bytes = b"") -> bytes:
    body = bytes([typ | RESP_FLAG, status, seq >> 8 & 0xFF, seq & 0xFF, len(payload)]) + payload
    return body + crc32(body).to_bytes(4, "little")


def parse_response(frame: bytes) -> dict:
    """Decode a response or telemetry frame; raises ValueError on a bad length or CRC."""
    if len(frame) < 9 or len(frame) != 9 + frame[4]:
        raise ValueError("bad response length")
    if int.from_bytes(frame[-4:], "little") != crc32(frame[:-4]):
        raise ValueError("bad response CRC")
    return {"type": frame[0] & 0x7F, "status": frame[1], "seq": frame[2] << 8 | frame[3], "payload": bytes(frame[5:-4])}


# ---- the endpoint --------------------------------------------------------------------------------------------------------
@dataclass
class Endpoint:
    """State and behaviour of the logic behind the UDP blocks. ``datagram(payload)`` is a whole payload at once; ``push`` is the
    byte-serial form the hardware uses (a packet ends with ``last``); both give the same result."""

    regs: list = field(default_factory=lambda: [ID_VALUE, 0, 0, 0, 0, 0, PERIOD_DEFAULT, 0])
    last_seq: int = 0
    have_seq: bool = False                   # no command accepted since reset: the first may carry any number
    counters: dict = field(default_factory=lambda: {k: 0 for k in COUNTERS})
    period: int = PERIOD_DEFAULT
    tlm_on: bool = False
    tlm_ticks: int = 0
    tlm_seq: int = 0
    tlm_frames: int = 0
    tlm_overruns: int = 0
    tlm_pending: bytes | None = None
    ticks: int = 0
    _buf: bytearray = field(default_factory=bytearray)
    _need: int | None = None                 # total length once the header is in
    _overflow: bool = False

    # -- receive path --
    def push(self, byte: int, last: bool) -> bytes | None:
        """One payload byte. Returns the response frame when this byte ends a packet that earns one."""
        if not self._overflow:
            self._buf.append(byte & 0xFF)
            if len(self._buf) == HEADER:
                if self._buf[1] > MAX_PAYLOAD:
                    self._overflow = True
                else:
                    self._need = HEADER + self._buf[1] + CRC_BYTES
            elif self._need is not None and len(self._buf) > self._need:
                self._overflow = True
        if not last:
            return None
        pkt, self._buf, need, over = bytes(self._buf), bytearray(), self._need, self._overflow
        self._need, self._overflow = None, False
        return self._finish(pkt, need, over)

    def datagram(self, payload: bytes) -> bytes | None:
        out = None
        for i, b in enumerate(payload):
            out = self.push(b, i == len(payload) - 1)
        if not payload:                       # an empty datagram is a truncated packet
            self.counters["truncated"] += 1
        return out

    def _finish(self, pkt: bytes, need: int | None, over: bool) -> bytes | None:
        c = self.counters
        if over:
            c["oversize"] += 1
            return None
        if need is None or len(pkt) < need:
            c["truncated"] += 1
            return None
        if int.from_bytes(pkt[-4:], "little") != crc32(pkt[:-4]):
            c["bad_crc"] += 1
            return None
        typ, ln, seq, payload = pkt[0], pkt[1], pkt[2] << 8 | pkt[3], pkt[HEADER:-4]
        if typ not in EXPECT_LEN:
            return self._reject(typ, BAD_TYPE, seq)
        if ln != EXPECT_LEN[typ]:
            return self._reject(typ, BAD_LEN, seq)
        delta = (seq - self.last_seq) & 0xFFFF if self.have_seq else 1
        if delta == 0:
            c["replay"] += 1
            return build_response(typ, BAD_SEQ, seq)
        if delta >= SEQ_SPAN:
            c["out_of_order"] += 1
            return build_response(typ, BAD_SEQ, seq)
        self.last_seq, self.have_seq = seq, True   # the command is authentic and in order: it consumes its number even if it then fails
        return self._execute(typ, seq, payload)

    def _reject(self, typ: int, status: int, seq: int) -> bytes:
        self.counters["protocol"] += 1
        return build_response(typ, status, seq)

    def _execute(self, typ: int, seq: int, p: bytes) -> bytes:
        c = self.counters
        if typ in (READ, WRITE):
            addr = p[0] << 8 | p[1]
            if addr >= N_REGS:
                return self._reject(typ, BAD_ADDR, seq)
            if typ == READ:
                value = self.read_reg(addr)              # a read of CMDS or ERRS shows the counts before this command
                c["ok"] += 1
                return build_response(typ, OK, seq, value.to_bytes(4, "big"))
            if addr in READ_ONLY_REGS:
                return self._reject(typ, READ_ONLY, seq)
            self.regs[addr] = int.from_bytes(p[2:6], "big")
            c["ok"] += 1
            return build_response(typ, OK, seq)
        if typ == STATUS:                          # the reply shows the counters before this command is counted
            body = b"".join(c[k].to_bytes(2, "big") for k in COUNTERS) + (self.tlm_frames & 0xFFFF).to_bytes(2, "big") + bytes([int(self.tlm_on)])
            c["ok"] += 1
            return build_response(typ, OK, seq, body)
        c["ok"] += 1
        if typ == TLM_START:
            req = p[0] << 8 | p[1]
            if req:
                self.period = max(PERIOD_MIN, req)
            self.tlm_on, self.tlm_ticks = True, 0
        else:
            self.tlm_on, self.tlm_pending = False, None
        return build_response(typ, OK, seq)

    def read_reg(self, a: int) -> int:
        if a == REG_CMDS:
            return self.counters["ok"] & 0xFFFFFFFF
        if a == REG_ERRS:
            return sum(v for k, v in self.counters.items() if k != "ok") & 0xFFFFFFFF
        if a == REG_PERIOD:
            return self.period
        if a == REG_UPTIME:
            return self.ticks & 0xFFFFFFFF
        return self.regs[a]

    # -- telemetry --
    def tick(self, n: int = 1) -> None:
        """Advance n ticks. At most one frame is held for the transmitter; a frame that falls due while the previous one is still
        held is dropped and counted (no queue), which bounds the rate."""
        for _ in range(n):
            self.ticks += 1
            if not self.tlm_on:
                continue
            self.tlm_ticks += 1
            if self.tlm_ticks >= self.period:
                self.tlm_ticks = 0
                if self.tlm_pending is not None:
                    self.tlm_overruns += 1
                else:
                    self.tlm_pending = self._telemetry_frame()

    def take_telemetry(self) -> bytes | None:
        """The transmit side accepts the held frame (called when the UDP transmitter is free)."""
        f, self.tlm_pending = self.tlm_pending, None
        return f

    def _telemetry_frame(self) -> bytes:
        body = (self.ticks & 0xFFFFFFFF).to_bytes(4, "big") + (self.counters["ok"] & 0xFFFF).to_bytes(2, "big") \
            + (self.read_reg(REG_ERRS) & 0xFFFF).to_bytes(2, "big")
        f = build_response(TLM_TYPE, OK, self.tlm_seq & 0xFFFF, body)
        self.tlm_seq += 1
        self.tlm_frames += 1
        return f


def cycles_per_command(n_bytes: int, resp_bytes: int) -> int:
    """Design target, in clocks of the 100 MHz system clock: one byte per clock in, a fixed 3 clocks to decide, one byte per clock out.
    Not measured: phase 3 measures it."""
    return n_bytes + 3 + resp_bytes


def max_command_rate(clk_hz: float = 100e6) -> dict:
    """Target command rates for the smallest and largest command (READ and WRITE), limited by the serial datapath, not by the
    100 Mbit/s link (a READ frame of 64 bytes on the wire takes 5.1 us)."""
    out = {}
    for name, n, r in (("READ", 4 + 2 + 4, 5 + 4 + 4), ("WRITE", 4 + 6 + 4, 5 + 4)):
        c = cycles_per_command(n, r)
        out[name] = {"cycles": c, "commands_per_s": clk_hz / c}
    return out


def protocol_text() -> str:
    """The datasheet text, generated from the constants above (tests compare it with protocol.md)."""
    rows = "\n".join(f"| {k} | {n} |" for k, n in ((READ, "READ: payload ADDR(2); reply payload DATA(4)"),
                                                  (WRITE, "WRITE: payload ADDR(2) DATA(4)"), (STATUS, "STATUS: no payload; reply 16 counter bytes + TLM_ON"),
                                                  (TLM_START, f"TLM_START: payload PERIOD(2) ticks, 0 keeps the current one; minimum {PERIOD_MIN}"),
                                                  (TLM_STOP, "TLM_STOP: no payload")))
    errs = "\n".join(f"| {k} | {v} |" for k, v in ERROR_NAMES.items())
    ctr = ", ".join(COUNTERS)
    regs = "\n".join(f"| {i} | {n} | {'read only' if i in READ_ONLY_REGS else 'read/write'} |" for i, n in enumerate(
        ("ID (0x55445031)", "SCRATCH0", "SCRATCH1", "SCRATCH2", "CMDS (accepted commands)", "ERRS (all rejected packets)", "PERIOD (ticks)", "UPTIME (ticks)")))
    return f"""# UDP endpoint protocol (generated from showcase/udp_endpoint/model/udp_ref.py; do not edit by hand)

Command: `TYPE LEN SEQ(2) PAYLOAD CRC32(4)`. Response: `TYPE|0x80 STATUS SEQ(2) LEN PAYLOAD CRC32(4)`. Numbers are big-endian;
the CRC (IEEE 802.3, over every byte before it) is little-endian. `LEN` is at most {MAX_PAYLOAD} in a command.

| Type | Meaning |
|---|---|
{rows}

| Status | Name |
|---|---|
{errs}

## Order of checks (the first that fails decides)

1. Framing. A packet whose `LEN` is above {MAX_PAYLOAD}, or that runs past `4 + LEN + 4` bytes, is oversize: dropped, counted, no reply. A packet
   that ends early (including an empty one) is truncated: dropped, counted, no reply.
2. CRC. A wrong CRC is dropped, counted, no reply (the sequence number cannot be trusted).
3. Type unknown: reply BAD_TYPE. `LEN` not the one the type needs: reply BAD_LEN. Both count as `protocol`.
4. Sequence. A number is newer when `(seq - last) mod 65536` is 1 to 0x7FFF; The first command after reset may carry any number.
   Equal is a replay and older is out of order: both are refused with reply BAD_SEQ, counted separately, and change nothing. A newer number may skip
   ahead (a lost command is not an error).
5. Address and access. An address above {N_REGS - 1} replies BAD_ADDR; a write to a read-only register replies READ_ONLY (both count as `protocol`).
   An accepted command consumes its sequence number even when step 5 then fails.

A command that passes every check is executed once and counted in `ok` (STATUS, and a READ of CMDS or ERRS, show the counts as they were before it). Rejected packets change no register, no sequence state and no telemetry state.

## Registers (ADDR)

| Addr | Name | Access |
|---|---|---|
{regs}

## Counters (STATUS reply, 16 bits each, wrapping, then the telemetry frame count and a TLM_ON byte)

{ctr}.

## Telemetry

While on, one frame is due every PERIOD ticks, counted from the TLM_START command (a period below {PERIOD_MIN} is raised to {PERIOD_MIN}; the new period
applies from the next start). The pacer holds at most one frame: a frame that falls due while the previous one has not been taken by the transmitter is
dropped and counted as an overrun, never queued, so the rate cannot exceed 1 per PERIOD ticks. Frame: type {TLM_TYPE:#04x}|0x80, status 0, its own sequence
number from 0, payload UPTIME(4) OK(2) ERRORS(2), CRC.
"""
