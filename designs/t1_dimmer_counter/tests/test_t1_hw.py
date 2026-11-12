"""T1 on the board, over the USB-UART, against the shell and T1 models (marked ``hw``).

Every response is compared byte for byte with ShellModel wrapped round
DimmerCounterModel, as the cocotb tests do with the RTL. Run by flow/bringup.py
right after programming the base build, so the design starts from reset; nobody
should press buttons or move switches while it runs (switch positions are read
once and given to the model).

USB power (owner rule): the random register test keeps DUTY at or below 0x80, and
the board is left with COUNT 0 (LEDs off).
"""

from __future__ import annotations

import random
import time

import pytest

from designs.t1_dimmer_counter import model as m
from shell.host import protocol as p
from shell.host.fpga_shell import FpgaShell
from shell.model.shell_model import ShellModel

pytestmark = pytest.mark.hw
LOOPBACK_VALUES = 1000


class Board:
    """The serial port, plus the models that predict every byte it should send."""

    def __init__(self, port_name: str, stamp: int) -> None:
        self.sh = FpgaShell.open(port_name, timeout_s=0.2)
        self.port = self.sh.port
        self.t1 = m.DimmerCounterModel()
        self.model = ShellModel(m.DESIGN_ID, stamp, self.t1)

    def raw(self, data: bytes, expect_len: int) -> bytes:
        self.port.reset_input_buffer()
        self.port.write(data)
        return self.port.read(expect_len) if expect_len else b""

    def check(self, req: bytes) -> bytes:
        """Send bytes, compare the board's response with the model's, return it."""
        want = self.model.feed(req)
        got = self.raw(req, len(want))
        assert got == want, f"{req.hex(' ')}: board {got.hex(' ')} model {want.hex(' ')}"
        return got

    def silent(self, data: bytes) -> None:
        """Bytes that must get no answer at all."""
        self.port.reset_input_buffer()
        self.port.write(data)
        extra = self.port.read(p.RESP_LEN)
        assert extra == b"", f"{data.hex(' ')}: unexpected answer {extra.hex(' ')}"

    def wr(self, addr: int, v: int) -> bytes:
        return self.check(p.encode_request(p.CMD_WRITE, addr, v))

    def rd(self, addr: int) -> int:
        return p.decode_response(self.check(p.encode_request(p.CMD_READ, addr))).data


@pytest.fixture(scope="module")
def board(request: pytest.FixtureRequest):
    port = request.config.getoption("--hw-port")
    stamp = request.config.getoption("--hw-stamp")
    b = Board(port, int(stamp, 16) if stamp else 0)
    b.stamp_given = stamp is not None
    time.sleep(0.05)
    b.port.reset_input_buffer()
    # the board's switches are whatever the owner left: read them once for the model
    sw = b.sh.read(p.WINDOW_BASE + m.INPUTS) & 0xFFFF
    b.t1.set_switches(sw)
    b.sh.write(p.REG_STATUS, 0)                 # start from clean error counters
    yield b
    b.sh.write(p.WINDOW_BASE + m.COUNT, 0)      # leave the LEDs off
    b.sh.write(p.WINDOW_BASE + m.DUTY, 0x40)
    b.sh.write(p.WINDOW_BASE + m.CTRL, m.CTRL_DISPLAY_EN)
    b.port.close()


def test_identity_and_build_stamp(board: Board) -> None:
    assert board.stamp_given, "--hw-stamp is required: the bitstream's build_stamp"
    assert board.rd(p.REG_DESIGN_ID) == m.DESIGN_ID              # "T1DC"
    assert board.rd(p.REG_SHELL_VERSION) == p.SHELL_VERSION      # 1.0
    board.rd(p.REG_BUILD_STAMP)                                  # equals --hw-stamp (via the model)


def test_worked_bytes_from_protocol_md(board: Board) -> None:
    """The byte strings written out by hand in shell/PROTOCOL.md."""
    assert board.check(bytes.fromhex("A5 01 00 00 00 00 00 01")) == bytes.fromhex("5A 00 43 44 31 54 62")
    assert board.check(bytes.fromhex("A5 02 03 78 56 34 12 09")) == bytes.fromhex("5A 00 78 56 34 12 08")
    assert board.check(bytes.fromhex("A5 02 00 00 00 00 00 02")) == bytes.fromhex("5A 04 00 00 00 00 04")
    assert board.check(bytes.fromhex("A5 01 00 00 00 00 00 FF")) == bytes.fromhex("5A 01 00 00 00 00 01")


def test_scratch_loopback_random(board: Board, request: pytest.FixtureRequest) -> None:
    board.wr(p.REG_STATUS, 0)
    rng = random.Random(request.config.getoption("--hw-seed"))
    values = [0, 0xFFFF_FFFF, 0xA5A5_5A5A, 0x5A5A_A5A5] + [rng.getrandbits(32) for _ in range(LOOPBACK_VALUES)]
    for v in values:
        assert board.sh.transact(p.CMD_WRITE, p.REG_SCRATCH, v).data == v
        assert board.sh.read(p.REG_SCRATCH) == v, f"scratch 0x{v:08X}"
        board.model.feed(p.encode_request(p.CMD_WRITE, p.REG_SCRATCH, v))
    assert board.sh.status() == {"checksum_errors": 0, "request_errors": 0, "uart_framing_errors": 0, "timeouts": 0}


def test_error_responses_and_counters(board: Board) -> None:
    board.wr(p.REG_STATUS, 0)
    board.check(p.encode_request(p.CMD_READ, p.REG_SCRATCH)[:-1] + b"\x00")     # bad checksum
    board.check(p.encode_request(0x03, p.REG_SCRATCH))                          # bad command
    board.check(p.encode_request(0x00, p.REG_DESIGN_ID))                        # bad command
    for addr in (0x05, 0x40, 0x7F):                                             # reserved addresses
        board.check(p.encode_request(p.CMD_READ, addr))
    for addr in (p.REG_DESIGN_ID, p.REG_SHELL_VERSION, p.REG_BUILD_STAMP):     # read-only
        board.check(p.encode_request(p.CMD_WRITE, addr, 0x1234))
    assert board.rd(p.REG_STATUS) == 1 | 8 << 8                                 # 1 checksum, 8 request errors
    board.wr(p.REG_STATUS, 0)
    assert board.rd(p.REG_STATUS) == 0


def test_sync_hunting(board: Board) -> None:
    """Bytes before the sync byte are discarded; the request after them is answered."""
    junk = bytes([0x00, 0xFF, 0x5A, 0x12, 0x01])
    board.check(junk + p.encode_request(p.CMD_READ, p.REG_DESIGN_ID))


def test_part_frame_times_out(board: Board) -> None:
    board.wr(p.REG_STATUS, 0)
    part = p.encode_request(p.CMD_WRITE, p.REG_SCRATCH, 0xDEAD_BEEF)[:5]
    board.silent(part)                       # the read timeout (0.2 s) is far beyond the 1 ms frame timeout
    board.model.feed(part)
    board.model.idle(0.2)
    assert board.rd(p.REG_STATUS) == 1 << 24
    board.check(p.encode_request(p.CMD_READ, p.REG_SCRATCH))                    # SCRATCH was not written
    board.wr(p.REG_STATUS, 0)


def test_framing_error_drops_the_part_frame(board: Board) -> None:
    """A byte with a low stop bit abandons a part frame (no answer) and counts one framing error.

    The UART is switched to odd parity for one write: a 9-bit character whose parity
    bit is 0 puts a 0 where the shell (8N1) samples its stop bit. A5, 03, 03 have an
    even number of 1s (odd parity bit 1, a good stop bit); 01 has one 1 (parity bit 0).
    Sending all four in one write keeps the gaps far below the 1 ms frame timeout
    (a break sent after the bytes was not: it raced the timeout on this host).
    """
    import serial

    board.wr(p.REG_STATUS, 0)
    data = bytes([p.SYNC_REQ, 0x03, 0x03, 0x01])
    board.port.reset_input_buffer()
    board.port.parity = serial.PARITY_ODD
    try:
        board.port.write(data)
        board.port.flush()
        time.sleep(0.01)
    finally:
        board.port.parity = serial.PARITY_NONE
    board.model.feed(data[:3])
    board.model.framing_error()
    assert board.port.read(p.RESP_LEN) == b""
    assert board.rd(p.REG_STATUS) == 1 << 16
    board.check(p.encode_request(p.CMD_READ, p.REG_SCRATCH))
    board.wr(p.REG_STATUS, 0)


def test_t1_registers_against_the_model(board: Board) -> None:
    """Reset values, then directed and random window accesses, every response byte-exact."""
    for off in (m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x05, 0x7F):
        board.rd(p.WINDOW_BASE + off)
    assert board.rd(p.WINDOW_BASE + m.DUTY) == 0x40 and board.rd(p.WINDOW_BASE + m.CTRL) == 0x2
    board.wr(p.WINDOW_BASE + m.COUNT, 0xA5A5)
    assert board.rd(p.WINDOW_BASE + m.COUNT) == 0xA5A5
    board.wr(p.WINDOW_BASE + m.COUNT, 0x1_2345)                                  # [31:16] dropped
    assert board.rd(p.WINDOW_BASE + m.COUNT) == 0x2345
    board.wr(p.WINDOW_BASE + m.DUTY, 0x120)                                     # [31:8] dropped: 0x20
    board.wr(p.WINDOW_BASE + m.CTRL, 0xFFFF_FFFC | m.CTRL_DISPLAY_EN)            # only [1:0] kept
    assert board.rd(p.WINDOW_BASE + m.CTRL) == m.CTRL_DISPLAY_EN
    board.wr(p.WINDOW_BASE + m.INPUTS, 0x1234)                                   # read-only: ignored
    board.wr(p.WINDOW_BASE + m.PRESSES, 0x1234)
    board.rd(p.WINDOW_BASE + m.INPUTS)
    board.rd(p.WINDOW_BASE + m.PRESSES)
    rng = random.Random(7)
    for _ in range(300):
        if rng.random() < 0.5:
            off = rng.choice([m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x11, 0x7F])
            v = rng.getrandbits(32)
            if off == m.DUTY:
                v &= 0x7F                       # USB power: at most half brightness
            if off == m.CTRL:
                v &= ~m.CTRL_DUTY_SRC & 0xFFFF_FFFF   # brightness from the register, not the switches
            board.wr(p.WINDOW_BASE + off, v)
        else:
            board.rd(p.WINDOW_BASE + rng.choice([m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x05, 0x7F]))
    board.wr(p.WINDOW_BASE + m.COUNT, 0)
    assert board.rd(p.REG_STATUS) == 0
