"""The test shell's byte protocol (shell/PROTOCOL.md): framing, constants, checks.

Shared by the host driver (``fpga_shell.py``) and the shell model
(``shell/model/shell_model.py``). Its tests pin the encodings to the byte
vectors written out by hand in PROTOCOL.md, so a mistake here cannot hide
behind both users agreeing with each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce

SYNC_REQ = 0xA5
SYNC_RESP = 0x5A
REQ_LEN = 8    # A5 CMD ADDR D0 D1 D2 D3 CHK
RESP_LEN = 7   # 5A STATUS D0 D1 D2 D3 CHK

CMD_READ = 0x01
CMD_WRITE = 0x02

ST_OK = 0x00
ST_BAD_CHK = 0x01
ST_BAD_CMD = 0x02
ST_BAD_ADDR = 0x03
ST_READ_ONLY = 0x04
STATUS_NAMES = {ST_OK: "OK", ST_BAD_CHK: "BAD_CHECKSUM", ST_BAD_CMD: "BAD_COMMAND",
                ST_BAD_ADDR: "BAD_ADDRESS", ST_READ_ONLY: "READ_ONLY"}

# Fixed registers
REG_DESIGN_ID = 0x00
REG_SHELL_VERSION = 0x01
REG_BUILD_STAMP = 0x02
REG_SCRATCH = 0x03
REG_STATUS = 0x04
WINDOW_BASE = 0x80   # 0x80-0xFF belong to the design under test
SHELL_VERSION = 0x0001_0000


def xor8(data: bytes) -> int:
    return reduce(lambda a, b: a ^ b, data, 0)


def encode_request(cmd: int, addr: int, data: int = 0) -> bytes:
    """An 8-byte request frame; ``data`` is sent little-endian (D0 = bits 7:0)."""
    if not 0 <= addr <= 0xFF or not 0 <= cmd <= 0xFF or not 0 <= data <= 0xFFFF_FFFF:
        raise ValueError("cmd/addr are bytes and data is 32 bits")
    body = bytes([cmd, addr]) + data.to_bytes(4, "little")
    return bytes([SYNC_REQ]) + body + bytes([xor8(body)])


def encode_response(status: int, data: int = 0) -> bytes:
    body = bytes([status]) + data.to_bytes(4, "little")
    return bytes([SYNC_RESP]) + body + bytes([xor8(body)])


@dataclass(frozen=True)
class Response:
    status: int
    data: int

    @property
    def ok(self) -> bool:
        return self.status == ST_OK

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, f"0x{self.status:02X}")


class ProtocolError(Exception):
    """A response that is not a well-formed 7-byte frame."""


def decode_response(frame: bytes) -> Response:
    if len(frame) != RESP_LEN:
        raise ProtocolError(f"response is {len(frame)} bytes, expected {RESP_LEN}")
    if frame[0] != SYNC_RESP:
        raise ProtocolError(f"response starts 0x{frame[0]:02X}, expected 0x{SYNC_RESP:02X}")
    if xor8(frame[1:6]) != frame[6]:
        raise ProtocolError("response checksum mismatch")
    return Response(frame[1], int.from_bytes(frame[2:6], "little"))
