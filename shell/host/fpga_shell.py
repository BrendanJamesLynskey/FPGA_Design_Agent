"""Host driver for the on-board test shell, over the board's USB-UART (pyserial).

    from shell.host.fpga_shell import FpgaShell
    with FpgaShell.open("/dev/ttyUSB1") as sh:
        print(sh.identify())
        sh.write(0x80, 0x1234)          # the design's first window register
        assert sh.read(0x80) == 0x1234

Command line (``python -m shell.host.fpga_shell --port /dev/ttyUSB1 <cmd>``):
``id``, ``scratch``, ``read ADDR``, ``write ADDR VALUE``, ``status``, ``clear-status``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Protocol

from shell.host import protocol as p

DEFAULT_BAUD = 115200


class SerialLike(Protocol):
    def write(self, data: bytes) -> int | None: ...
    def read(self, size: int = 1) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def close(self) -> None: ...


class ShellError(Exception):
    """The shell answered with an error status, or did not answer."""


class FpgaShell:
    def __init__(self, port: SerialLike, retries: int = 1) -> None:
        self.port = port
        self.retries = retries

    @classmethod
    def open(cls, device: str, baud: int = DEFAULT_BAUD, timeout_s: float = 0.5) -> "FpgaShell":
        import serial  # pyserial; imported here so the tests and the model need no port

        return cls(serial.Serial(device, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=timeout_s))

    def __enter__(self) -> "FpgaShell":
        return self

    def __exit__(self, *exc: object) -> None:
        self.port.close()

    def transact(self, cmd: int, addr: int, data: int = 0) -> p.Response:
        """Send one request and return the decoded response (no status check)."""
        req = p.encode_request(cmd, addr, data)
        last: Exception | None = None
        for _ in range(self.retries + 1):
            self.port.reset_input_buffer()
            self.port.write(req)
            raw = self.port.read(p.RESP_LEN)
            try:
                return p.decode_response(raw)
            except p.ProtocolError as e:
                # A short read means no answer: the shell may have dropped the frame
                # (timeout, framing error). Waiting > 1 ms resynchronises it.
                last = e
        raise ShellError(f"no valid response to {req.hex(' ')}: {last}")

    def read(self, addr: int) -> int:
        r = self.transact(p.CMD_READ, addr)
        if not r.ok:
            raise ShellError(f"read 0x{addr:02X}: {r.status_name}")
        return r.data

    def write(self, addr: int, value: int) -> None:
        r = self.transact(p.CMD_WRITE, addr, value)
        if not r.ok:
            raise ShellError(f"write 0x{addr:02X}: {r.status_name}")

    def identify(self) -> dict[str, int]:
        return {"design_id": self.read(p.REG_DESIGN_ID),
                "shell_version": self.read(p.REG_SHELL_VERSION),
                "build_stamp": self.read(p.REG_BUILD_STAMP)}

    def status(self) -> dict[str, int]:
        v = self.read(p.REG_STATUS)
        return {"checksum_errors": v & 0xFF, "request_errors": (v >> 8) & 0xFF,
                "uart_framing_errors": (v >> 16) & 0xFF, "timeouts": (v >> 24) & 0xFF}

    def scratch_test(self, patterns: tuple[int, ...] = (0x0000_0000, 0xFFFF_FFFF, 0xA5A5_5A5A, 0x1234_5678)) -> bool:
        """Write and read back the scratch register; True if every pattern survives."""
        for v in patterns:
            self.write(p.REG_SCRATCH, v)
            if self.read(p.REG_SCRATCH) != v:
                return False
        return True


def design_id_text(v: int) -> str:
    """Design IDs are four ASCII characters, most significant byte first ('T1DC')."""
    raw = v.to_bytes(4, "big")
    return raw.decode("ascii") if all(0x20 <= b < 0x7F for b in raw) else f"0x{v:08X}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--port", required=True, help="serial device, e.g. /dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("cmd", choices=["id", "scratch", "read", "write", "status", "clear-status"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    with FpgaShell.open(a.port, a.baud) as sh:
        if a.cmd == "id":
            i = sh.identify()
            print(f"design_id     {design_id_text(i['design_id'])} (0x{i['design_id']:08X})")
            print(f"shell_version {i['shell_version'] >> 16}.{i['shell_version'] & 0xFFFF}")
            print(f"build_stamp   {i['build_stamp']:08x}")
        elif a.cmd == "scratch":
            ok = sh.scratch_test()
            print("scratch PASS" if ok else "scratch FAIL")
            return 0 if ok else 1
        elif a.cmd == "read":
            print(f"0x{sh.read(int(a.args[0], 0)):08X}")
        elif a.cmd == "write":
            sh.write(int(a.args[0], 0), int(a.args[1], 0))
        elif a.cmd == "status":
            for k, v in sh.status().items():
                print(f"{k:20s}{v}")
        elif a.cmd == "clear-status":
            sh.write(p.REG_STATUS, 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
