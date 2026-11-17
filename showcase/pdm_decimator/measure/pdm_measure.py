"""Measurements of the PDM-microphone audio path on a board, and the simulated rig that runs them without one (brief 79, phase 1).

What is measured (``spec.yaml``, ``measurements``): the microphone's self-noise in a quiet room (M1), the level of loudspeaker tones
relative to 1 kHz (M2) and the tone signal-to-noise ratio (M3). Each capture is the first 64 audio samples after a run start
(1.31 ms at 48.828125 kHz); every capture restarts the chain, so the phase of a tone is random from one capture to the next and a
tone's level is taken per capture (a least-squares sine fit) and averaged.

Limits written into every result: the loudspeaker, the room and the microphone bound the frequency response, so M2 is the response of the
whole measured chain, not of the design; a 64-sample record has a bin spacing of 763 Hz, so a tone level carries the leakage of the noise
in its bin; the XADC cannot see fast supply droop (M4).
"""
from __future__ import annotations

import math
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np

from showcase.pdm_decimator.model import pdm_chain_ref as ref

FS_OUT = ref.FS_OUT
FS_PDM = ref.FS_PDM
CTRL, STATUS, COUNT, CAP0 = 0x00, 0x01, 0x02, 0x40      # window offsets (spec.yaml, registers)
RUN, ARM = 1, 2
DONE, SAT = 1, 4
TONES_HZ = (1000, 2000, 4000, 8000, 12000, 15000)     # a 64-sample capture holds 1.3 cycles of 1 kHz: lower tones cannot be measured with it
RESPONSE_LIMIT_DB = 1.0
SNR_FLOOR_DB = 40.0


class Board:
    """Register access in window offsets. The real one wraps the UART shell; the simulated one is ``SimBoard``."""

    def read(self, off: int) -> int:
        raise NotImplementedError

    def write(self, off: int, value: int) -> None:
        raise NotImplementedError


class ShellBoard(Board):
    """The Nexys A7 over its USB-UART (shell/host/fpga_shell.py). The design's window starts at shell address 0x80."""

    def __init__(self, device: str) -> None:
        from shell.host import fpga_shell, protocol
        self.shell = fpga_shell.FpgaShell.open(device)
        self.base = protocol.WINDOW_BASE

    def read(self, off: int) -> int:
        return self.shell.read(self.base + off)

    def write(self, off: int, value: int) -> None:
        self.shell.write(self.base + off, value)


def delta_sigma(x: Callable[[int], float], n: int) -> list[int]:
    """Second-order delta-sigma bits of the pressure ``x(k)`` (-1..1) at PDM sample k."""
    a = b = 0.0
    fb = -1.0
    out = []
    for k in range(n):
        a += x(k) - fb
        b += a - fb
        fb = 1.0 if b >= 0 else -1.0
        out.append(int(fb > 0))
    return out


class SimBoard(Board):
    """The audio path's registers backed by the reference model, listening to a synthetic room.

    ``room()`` returns a pressure function of the PDM sample index (full scale 1.0); it is called once per run start, as the speaker's
    phase relative to the board's run start is arbitrary."""

    def __init__(self, room: Callable[[], Callable[[int], float]]) -> None:
        self.room = room
        self.run = 0
        self.armed = self.done = False
        self.cap: list[int] = []
        self.sat = self.count = 0

    def write(self, off: int, value: int) -> None:
        if off != CTRL:
            return
        was_running = self.run
        if value & ARM and not was_running:
            self.armed, self.done = True, False
        if value & RUN and not was_running:
            bits = delta_sigma(self.room(), ref.bits_needed(64) + 64)
            out, sat = ref.process(bits)
            self.sat, self.count = int(sat) << 2, len(out)
            if self.armed:
                self.cap, self.armed, self.done = out[:64], False, True
        self.run = value & RUN

    def read(self, off: int) -> int:
        regs = {CTRL: self.run, STATUS: int(self.done) | int(self.armed) << 1 | self.sat, COUNT: self.count}
        if off in regs:
            return regs[off]
        if off >= CAP0 and self.done:
            return self.cap[off - CAP0] & 0xFFFF_FFFF
        return 0


def capture(board: Board, timeout_s: float = 5.0) -> np.ndarray:
    """ARM and RUN in one write, wait for DONE, stop the run, read the 64 samples (full scale 1.0)."""
    board.write(CTRL, ARM | RUN)
    t0 = time.monotonic()
    while not board.read(STATUS) & DONE:
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError("the capture did not complete")
    board.write(CTRL, 0)
    raw = [board.read(CAP0 + i) for i in range(64)]
    return np.array([v - (1 << 32) if v & 0x8000_0000 else v for v in raw], dtype=float) / 32768.0


def tone_amplitude(rec: np.ndarray, f_hz: float) -> float:
    """Amplitude of the tone at ``f_hz`` in one record: a least-squares fit of cosine, sine and a constant (full scale 1.0). A fit rather than a
    DFT bin, because a record holds only a cycle or two of the lowest tone and a bin would depend on its phase."""
    n = np.arange(len(rec))
    basis = np.stack([np.cos(2 * np.pi * f_hz / FS_OUT * n), np.sin(2 * np.pi * f_hz / FS_OUT * n), np.ones(len(rec))], axis=1)
    a, b, _ = np.linalg.lstsq(basis, rec, rcond=None)[0]
    return float(math.hypot(a, b))


def noise_dbfs(records: list[np.ndarray]) -> float:
    """RMS of the records with each record's mean removed, in dBFS."""
    x = np.concatenate([r - r.mean() for r in records])
    return 20 * math.log10(max(float(np.sqrt(np.mean(x ** 2))), 1e-12))


def measure(board: Board, records: int, speaker: Callable[[float], Callable[[], None]] | None = None,
            conditions: Callable[[], dict] | None = None) -> dict:
    """The plan: quiet-room noise (M1), then each tone (M2, M3). ``speaker(f)`` starts a tone and returns its stopper."""
    res: dict = {"records_per_point": records, "fs_out_hz": FS_OUT, "conditions": {}}
    if conditions:
        res["conditions"]["start"] = conditions()
    quiet = [capture(board) for _ in range(records)]
    res["noise_floor_dbfs"] = round(noise_dbfs(quiet), 1)
    points = []
    for f in TONES_HZ:
        stop = speaker(f) if speaker else None
        amps = [tone_amplitude(capture(board), f) for _ in range(records)]
        if stop:
            stop()
        points.append({"f_hz": f, "amp_mean": float(np.mean(amps)), "amp_std": float(np.std(amps))})
    ref_amp = next(p["amp_mean"] for p in points if p["f_hz"] == 1000)
    floor_amp = 10 ** (res["noise_floor_dbfs"] / 20)
    for p in points:
        p["rel_db"] = round(20 * math.log10(p["amp_mean"] / ref_amp), 2)
        p["snr_db"] = round(20 * math.log10(p["amp_mean"] / floor_amp), 1)
    res["points"] = points
    res["sat_seen"] = bool(board.read(STATUS) & SAT)
    if conditions:
        res["conditions"]["end"] = conditions()
    return res


def loudspeaker(f_hz: float, level: float = 0.05, seconds: float = 120.0, device: str | None = None) -> Callable[[], None]:
    """A PC loudspeaker tone through ``aplay`` (a temporary 48 kHz mono WAV). Returns the function that stops it. ``level`` is a fraction of
    the PC output's full scale: start low and raise it by hand; a loud tone is not a better measurement."""
    n = int(48000 * seconds)
    x = (level * 32767 * np.sin(2 * np.pi * f_hz * np.arange(n) / 48000)).astype("<i2")
    path = Path(tempfile.mkdtemp()) / "tone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(x.tobytes())
    proc = subprocess.Popen(["aplay", "-q"] + (["-D", device] if device else []) + [str(path)])
    return proc.terminate


def simulated_room(rng: np.random.Generator, tone_hz: list[float | None], tone_amp: float = 0.05,
                   noise_dbfs_: float = -72.0) -> Callable[[], Callable[[int], float]]:
    """A room with an optional loudspeaker tone (``tone_hz[0]``, set by the speaker hook) and white acoustic noise."""
    sigma = 10 ** (noise_dbfs_ / 20)

    def room() -> Callable[[int], float]:
        phase = float(rng.uniform(0, 2 * np.pi))
        noise = rng.normal(0.0, sigma, 4096)
        f = tone_hz[0]
        return lambda k: (tone_amp * math.sin(2 * math.pi * f * k / FS_PDM + phase) if f else 0.0) + float(noise[k % 4096])
    return room


def dry_run(records: int = 24, seed: int = 5) -> dict:
    """The whole plan on the simulated board and room; no hardware, no audio device."""
    tone: list[float | None] = [None]
    board = SimBoard(simulated_room(np.random.default_rng(seed), tone))

    def speaker(f: float) -> Callable[[], None]:
        tone[0] = f
        return lambda: tone.__setitem__(0, None)

    res = measure(board, records, speaker)
    res["dry_run"] = True
    res["rig_settings"] = {"tone_amplitude_fs": 0.05, "room_noise_dbfs_per_pdm_sample": -72.0, "seed": seed,
                           "note": "every figure below is a property of these settings and of the model, not a measurement of hardware"}
    res["dry_run_pass"] = bool(all(abs(p["rel_db"]) <= RESPONSE_LIMIT_DB for p in res["points"])
                               and min(p["snr_db"] for p in res["points"]) >= SNR_FLOOR_DB)
    return res
