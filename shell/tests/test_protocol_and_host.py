"""Pure-Python tests: protocol encodings, the shell model, and the host driver against the model."""

from __future__ import annotations

import pytest

from designs.t1_dimmer_counter.model import DESIGN_ID, DimmerCounterModel
from shell.host import protocol as p
from shell.host.fpga_shell import FpgaShell, ShellError, design_id_text, main
from shell.model.shell_model import ShellModel

# The worked bytes in shell/PROTOCOL.md, typed in by hand
WORKED = [
    (p.encode_request(p.CMD_READ, 0x00), "A5 01 00 00 00 00 00 01"),
    (p.encode_request(p.CMD_WRITE, 0x03, 0x1234_5678), "A5 02 03 78 56 34 12 09"),
    (p.encode_request(p.CMD_WRITE, 0x00), "A5 02 00 00 00 00 00 02"),
    (p.encode_response(p.ST_OK, 0x5431_4443), "5A 00 43 44 31 54 62"),
    (p.encode_response(p.ST_OK, 0x1234_5678), "5A 00 78 56 34 12 08"),
    (p.encode_response(p.ST_BAD_CHK), "5A 01 00 00 00 00 01"),
    (p.encode_response(p.ST_READ_ONLY), "5A 04 00 00 00 00 04"),
]


@pytest.mark.parametrize("got,want", WORKED)
def test_worked_bytes(got: bytes, want: str) -> None:
    assert got == bytes.fromhex(want)


def test_decode_rejects_bad_frames() -> None:
    good = p.encode_response(p.ST_OK, 7)
    assert p.decode_response(good) == p.Response(0, 7)
    for bad in (good[:-1], b"\x00" + good[1:], good[:-1] + bytes([good[-1] ^ 1])):
        with pytest.raises(p.ProtocolError):
            p.decode_response(bad)
    with pytest.raises(ValueError):
        p.encode_request(p.CMD_READ, 0x100)


def test_model_hunts_for_sync_and_answers_in_order() -> None:
    sh = ShellModel(design_id=DESIGN_ID)
    out = sh.feed(b"\x00\x5a" + p.encode_request(p.CMD_READ, 0) + p.encode_request(p.CMD_READ, 1))
    assert out == p.encode_response(p.ST_OK, DESIGN_ID) + p.encode_response(p.ST_OK, p.SHELL_VERSION)


def test_model_timeout_and_counters() -> None:
    sh = ShellModel()
    assert sh.feed(p.encode_request(p.CMD_READ, 0)[:5]) == b""
    sh.idle(0.5e-3)                      # shorter than the timeout: the frame survives
    sh.idle(2e-3)                        # longer: dropped and counted
    assert sh.feed(p.encode_request(p.CMD_READ, 0)[5:]) == b""
    sh.framing_error()
    sh.feed(p.encode_request(p.CMD_WRITE, 0x10, 1))      # bad address
    assert p.decode_response(sh.feed(p.encode_request(p.CMD_READ, p.REG_STATUS))).data == 1 << 24 | 1 << 16 | 1 << 8
    for _ in range(300):
        sh.feed(p.encode_request(0x09, 0))
    assert (sh.status_reg >> 8) & 0xFF == 0xFF          # saturates


class LoopbackSerial:
    """A serial port wired to the shell model, with optional dropped answers."""

    def __init__(self, model: ShellModel, drop_first: int = 0) -> None:
        self.model, self.rx, self.drop = model, b"", drop_first
        self.closed = False

    def write(self, data: bytes) -> int:
        out = self.model.feed(data)
        if self.drop:
            self.drop -= 1
            self.model.idle(2e-3)
            out = b""
        self.rx += out
        return len(data)

    def read(self, size: int = 1) -> bytes:
        r, self.rx = self.rx[:size], self.rx[size:]
        return r

    def reset_input_buffer(self) -> None:
        self.rx = b""

    def close(self) -> None:
        self.closed = True


def test_host_driver_against_the_model() -> None:
    t1 = DimmerCounterModel()
    sh = FpgaShell(LoopbackSerial(ShellModel(design_id=DESIGN_ID, build_stamp=0xABCD1234, window=t1)))
    ident = sh.identify()
    assert design_id_text(ident["design_id"]) == "T1DC" and ident["build_stamp"] == 0xABCD1234
    assert sh.scratch_test()
    sh.write(0x80, 0x1_2345)
    assert sh.read(0x80) == 0x2345 == t1.count
    with pytest.raises(ShellError, match="READ_ONLY"):
        sh.write(0x00, 1)
    with pytest.raises(ShellError, match="BAD_ADDRESS"):
        sh.read(0x20)
    assert sh.status() == {"checksum_errors": 0, "request_errors": 2, "uart_framing_errors": 0, "timeouts": 0}


def test_host_driver_retries_once_then_gives_up() -> None:
    port = LoopbackSerial(ShellModel(design_id=DESIGN_ID), drop_first=1)
    assert FpgaShell(port, retries=1).read(0) == DESIGN_ID
    port = LoopbackSerial(ShellModel(design_id=DESIGN_ID), drop_first=2)
    with pytest.raises(ShellError, match="no valid response"):
        FpgaShell(port, retries=1).read(0)


def test_cli_uses_the_driver(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    port = LoopbackSerial(ShellModel(design_id=DESIGN_ID))
    monkeypatch.setattr(FpgaShell, "open", classmethod(lambda cls, dev, baud=115200, timeout_s=0.5: cls(port)))
    assert main(["--port", "/dev/null", "id"]) == 0
    assert "T1DC" in capsys.readouterr().out
    assert main(["--port", "/dev/null", "scratch"]) == 0
    assert port.closed
