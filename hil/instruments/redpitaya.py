"""Red Pitaya STEMlab over SCPI (TCP port 5000), documented commands only (brief 30). Acquire and generate; this module
cannot write the SD card, flash or load FPGA images: it sends only the commands in ALLOWED. Not run on 2026-11-11 (the
Red Pitaya was not on the network); the client is tested against a fake SCPI server. Input range: the fast analogue
inputs take +-1 V (LV jumper) or +-20 V (HV jumper): check the jumper before connecting anything above 1 V; Nexys
3.3 V LVCMOS needs the HV setting or a divider. Outputs are +-1 V into 50 ohm."""
from __future__ import annotations

import socket

ALLOWED_PREFIXES = ("*IDN?", "*RST", "ACQ:", "SOUR1:", "SOUR2:", "OUTPUT1:", "OUTPUT2:", "DIG:", "ANALOG:")
FORBIDDEN = ("FPGA", "FLASH", "SD", "OVERLAY", "SYSTEM")


class ScpiError(RuntimeError):
    pass


class RedPitaya:
    def __init__(self, host: str, port: int = 5000, timeout_s: float = 5.0, sock: socket.socket | None = None) -> None:
        self.s = sock or socket.create_connection((host, port), timeout=timeout_s)
        self.s.settimeout(timeout_s)

    def send(self, cmd: str) -> None:
        up = cmd.strip().upper()
        if not up.startswith(ALLOWED_PREFIXES) or any(w in up for w in FORBIDDEN):
            raise ScpiError(f"command not allowed by this driver: {cmd!r}")
        self.s.sendall(cmd.strip().encode() + b"\r\n")

    def ask(self, cmd: str) -> str:
        self.send(cmd)
        buf = b""
        while not buf.endswith(b"\r\n"):
            chunk = self.s.recv(65536)
            if not chunk:
                raise ScpiError("connection closed")
            buf += chunk
        return buf.decode().strip()

    def idn(self) -> str:
        return self.ask("*IDN?")

    def generate(self, ch: int, shape: str, freq_hz: float, amp_v: float, offset_v: float = 0.0) -> None:
        """Fast-output signal generator. Amplitude is limited to 1 V here."""
        if abs(amp_v) + abs(offset_v) > 1.0:
            raise ScpiError("output limited to 1 V peak (offset included)")
        for c in (f"SOUR{ch}:FUNC {shape.upper()}", f"SOUR{ch}:FREQ:FIX {freq_hz}", f"SOUR{ch}:VOLT {amp_v}",
                  f"SOUR{ch}:VOLT:OFFS {offset_v}", f"OUTPUT{ch}:STATE ON"):
            self.send(c)

    def stop(self, ch: int) -> None:
        self.send(f"OUTPUT{ch}:STATE OFF")

    def acquire(self, ch: int = 1, decimation: int = 1, trig_level_v: float = 0.0) -> list[float]:
        """One 16384-sample capture at 125 MS/s / decimation, triggered on the channel's rising edge."""
        self.send("ACQ:RST")
        self.send(f"ACQ:DEC {decimation}")
        self.send(f"ACQ:TRIG:LEV {trig_level_v}")
        self.send("ACQ:START")
        self.send(f"ACQ:TRIG CH{ch}_PE")
        while self.ask("ACQ:TRIG:STAT?") != "TD":
            pass
        txt = self.ask(f"ACQ:SOUR{ch}:DATA?")
        return [float(v) for v in txt.strip("{}").split(",")]

    def close(self) -> None:
        self.s.close()
