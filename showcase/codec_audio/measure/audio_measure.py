"""PC-side measurement of the codec audio path (brief 78, phase 1): tone generator, analysers, two rigs.

Two rigs give the same interface, so every analyser and the runner are tested without any hardware:

* `SimRig`: a numpy model of the path (the arithmetic of model/audio_ref.py, vectorised) behind a modelled codec and
  PC interface (converter noise, a little distortion, crosstalk, delay). A dry run uses it. Its numbers are properties of
  the model's settings, never measurements of the board, and every record it writes says `"dry_run": true`.
* `AlsaRig`: `aplay` and `arecord` on the owner's PC interface, plus a controller callback for gain and mute writes on the
  board. Written in phase 1, not yet run on any hardware (phase 3 does that).

Measurements: frequency response, THD+N at 1 kHz, noise floor, crosstalk, latency in samples (analogue in to analogue
out), and the click energy of a gain step against an unsmoothed control. A result that the codec or the PC interface
limits is reported as that limit: `classify` compares a result with a baseline taken with the interface alone (line out
cabled to line in, no board), and with the codec datasheet limit, and names the limiting item.
"""
from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FS = 48000
FULL_SCALE = float(1 << 23)

# ---- signals --------------------------------------------------------------------------------------------------------


def dbfs_to_amp(db: float) -> float:
    return 10.0 ** (db / 20.0)


def tone(f: float, secs: float, db: float = -30.0, fs: int = FS, fade_ms: float = 50.0, phase: float = 0.0) -> np.ndarray:
    """A sine at `db` dBFS peak, with a raised-cosine fade in and out so that starting it never clicks the headphones."""
    n = int(round(secs * fs))
    t = np.arange(n) / fs
    x = dbfs_to_amp(db) * np.sin(2 * math.pi * f * t + phase)
    k = min(int(fade_ms * 1e-3 * fs), n // 2)
    if k:
        w = 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k)
        x[:k] *= w
        x[-k:] *= w[::-1]
    return x


def noise_burst(secs: float, db: float = -30.0, fs: int = FS, seed: int = 1) -> np.ndarray:
    """Band-limited white noise (a fixed seed, so a run can be repeated): the signal for the latency measurement."""
    rng = np.random.default_rng(seed)
    n = int(round(secs * fs))
    x = rng.standard_normal(n)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / fs)
    spec[(f < 100) | (f > 18000)] = 0
    x = np.fft.irfft(spec, n)
    return dbfs_to_amp(db) * x / np.max(np.abs(x))


# ---- analysers (numpy only) ---------------------------------------------------------------------------------------


def _bh(n: int) -> np.ndarray:
    k = np.arange(n) * 2 * np.pi / n
    return 0.35875 - 0.48829 * np.cos(k) + 0.14128 * np.cos(2 * k) - 0.01168 * np.cos(3 * k)


def _power(x: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    """One-sided power spectrum scaled so that a sine of amplitude A has A**2 / 2 summed over its lobe."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    w = _bh(len(x))
    p = 2.0 * np.abs(np.fft.rfft(x * w)) ** 2 / (len(x) * np.sum(w ** 2))
    return np.fft.rfftfreq(len(x), 1 / fs), p


def _db(v: float) -> float:
    return 10.0 * math.log10(max(v, 1e-30))


SINE_RMS_DB = 10.0 * math.log10(2.0)        # a full-scale sine has power 1/2; levels are quoted against its rms (AES17), so it reads 0 dBFS


LOBE = 6      # bins either side of a tone that belong to it (Blackman-Harris main lobe)


def level_dbfs(x: np.ndarray, fs: int, f0: float) -> float:
    """RMS level of the tone at f0, in dBFS against a full-scale sine's rms (a full-scale sine reads 0 dBFS, a sine of peak -30 dBFS reads -30)."""
    f, p = _power(x, fs)
    k = int(round(f0 / f[1]))
    return _db(p[max(k - LOBE, 0):k + LOBE + 1].sum()) + SINE_RMS_DB


def thd_n(x: np.ndarray, fs: int, f0: float, band: tuple[float, float] = (20.0, 20000.0)) -> dict:
    """THD+N: everything in the band except the fundamental, against the fundamental. Level, ratio in dB and percent."""
    f, p = _power(x, fs)
    k = int(round(f0 / f[1]))
    sig = p[max(k - LOBE, 0):k + LOBE + 1].sum()
    inband = (f >= band[0]) & (f <= band[1])
    mask = inband.copy()
    mask[max(k - LOBE, 0):k + LOBE + 1] = False
    rest = p[mask].sum()
    return {"fundamental_dbfs": _db(sig) + SINE_RMS_DB, "thd_n_db": _db(rest / sig), "thd_n_percent": 100.0 * math.sqrt(rest / sig)}


def noise_floor_dbfs(x: np.ndarray, fs: int, band: tuple[float, float] = (20.0, 20000.0)) -> float:
    """RMS level of a capture of silence in the band, in dBFS (against a full-scale sine's rms, as AES17 does; no weighting)."""
    f, p = _power(x, fs)
    return _db(p[(f >= band[0]) & (f <= band[1])].sum()) + SINE_RMS_DB


def crosstalk_db(driven: np.ndarray, quiet: np.ndarray, fs: int, f0: float) -> float:
    """Level of the tone on the channel that was not driven, relative to the driven channel (negative; more negative is better)."""
    return level_dbfs(quiet, fs, f0) - level_dbfs(driven, fs, f0)


def latency_samples(ref: np.ndarray, rec: np.ndarray, max_lag: int = 2000) -> float:
    """Delay of rec behind ref in samples (a fraction through a parabola on the correlation peak)."""
    n = 1 << int(math.ceil(math.log2(len(ref) + len(rec))))
    c = np.fft.irfft(np.fft.rfft(rec, n) * np.conj(np.fft.rfft(ref, n)), n)
    c = np.concatenate([c[-max_lag:], c[:max_lag + 1]])
    k = int(np.argmax(c))
    frac = 0.0
    if 0 < k < len(c) - 1:
        a, b, d = c[k - 1], c[k], c[k + 1]
        if (a - 2 * b + d) != 0:
            frac = 0.5 * (a - d) / (a - 2 * b + d)
    return k - max_lag + frac


def step_index(x: np.ndarray, fs: int, win_ms: float = 2.0) -> int:
    """Where the level of a steady tone changes most (the gain step): the largest jump of the windowed rms."""
    w = max(int(win_ms * 1e-3 * fs), 8)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, mode="valid"))
    d = np.abs(e[w:] - e[:-w])
    return int(np.argmax(d)) + w


def click_energy_db(x: np.ndarray, fs: int, f0: float, at: int, win: int = 4096, guard_hz: float = 400.0) -> float:
    """Energy of a window around a gain step that is not near the carrier (|f - f0| > guard_hz), relative to the carrier's
    energy in the same window: the splatter that the ear hears as a click. A smooth ramp keeps it far below a step."""
    seg = np.asarray(x[max(at - win // 2, 0):at + win // 2], dtype=float)
    f, p = _power(seg, fs)
    near = np.abs(f - f0) <= guard_hz
    far = (f >= 20) & (f <= 20000) & ~near
    return _db(p[far].sum() / max(p[near].sum(), 1e-30))


def compare_click(smooth_rec: np.ndarray, control_rec: np.ndarray, fs: int, f0: float) -> dict:
    """The click energy of two captures of the same gain step, one with the ramp and one without (a separate unsmoothed build)."""
    a = click_energy_db(smooth_rec, fs, f0, step_index(smooth_rec, fs))
    c = click_energy_db(control_rec, fs, f0, step_index(control_rec, fs))
    return {"smoothed_db": a, "control_db": c, "improvement_db": c - a}


def classify(value_db: float, baseline_db: float | None, datasheet_db: float | None, margin_db: float = 6.0) -> dict:
    """Who limits a measurement where lower (more negative) is better: THD+N, noise, crosstalk. The result is reported as the
    interface's limit when it is within `margin_db` of the baseline taken with the PC interface alone, and as the codec's
    limit when within `margin_db` of the datasheet figure; only a result worse than both is the design's own."""
    if baseline_db is not None and value_db <= baseline_db + margin_db:
        return {"limited_by": "pc_interface", "value_db": value_db, "baseline_db": baseline_db}
    if datasheet_db is not None and value_db <= datasheet_db + margin_db:
        return {"limited_by": "codec", "value_db": value_db, "datasheet_db": datasheet_db}
    return {"limited_by": "design_or_unknown", "value_db": value_db, "baseline_db": baseline_db, "datasheet_db": datasheet_db}


# ---- rigs --------------------------------------------------------------------------------------------------------


@dataclass
class Event:
    """A control write at a time from the start of playback: ('gain', channel, q412 value) or ('mute', channel, 0 or 1)."""
    t: float
    op: str
    ch: int
    value: int


class SimRig:
    """A modelled path, codec and PC interface. All settings are explicit and recorded in the dry-run record."""

    def __init__(self, fs: int = FS, ramp_step: int = 16, smooth: bool = True, adc_noise_dbfs: float = -108.0,
                 h2_db: float = -100.0, h3_db: float = -105.0, crosstalk_db: float = -96.0, codec_delay: float = 41.0,
                 seed: int = 3) -> None:
        self.fs, self.ramp_step, self.smooth = fs, ramp_step, smooth
        self.noise, self.h2, self.h3, self.xt, self.delay = adc_noise_dbfs, h2_db, h3_db, crosstalk_db, codec_delay
        self.rng = np.random.default_rng(seed)
        self.gain = [0x1000, 0x1000]
        self.mute = [0, 0]
        self.cur = [0x1000, 0x1000]
        self.kind = "sim"

    def settings(self) -> dict:
        return {"ramp_step": self.ramp_step, "smooth": self.smooth, "adc_noise_dbfs": self.noise, "h2_db": self.h2,
                "h3_db": self.h3, "crosstalk_db": self.xt, "codec_delay_samples": self.delay}

    def reset_controls(self) -> None:
        self.gain, self.mute, self.cur = [0x1000, 0x1000], [0, 0], [0x1000, 0x1000]

    def _channel(self, x: np.ndarray, ch: int, events: list[Event]) -> np.ndarray:
        """The path's gain stage on one channel, 24-bit integers in and out, exactly the arithmetic of audio_ref.Path."""
        n = len(x)
        at = {int(round(e.t * self.fs)): e for e in events if e.ch == ch}
        out = np.empty(n, dtype=np.int64)
        start = 0
        marks = sorted(at) + [n]
        for m in marks:
            m = min(max(m, 0), n)
            if m > start:
                tgt = 0 if self.mute[ch] else self.gain[ch]
                cur = self.cur[ch]
                if self.smooth:
                    k = np.arange(1, m - start + 1)
                    d = tgt - cur
                    steps = np.minimum(k * self.ramp_step, abs(d))
                    g = cur + np.sign(d) * steps
                else:
                    g = np.full(m - start, tgt)
                self.cur[ch] = int(g[-1])
                out[start:m] = np.clip((x[start:m] * g.astype(np.int64)) >> 12, -(1 << 23), (1 << 23) - 1)
                start = m
            if m in at and m < n:
                e = at.pop(m)
                if e.op == "gain":
                    self.gain[ch] = e.value
                else:
                    self.mute[ch] = e.value
        return out

    def play_record(self, left: np.ndarray, right: np.ndarray, events: list[Event] | None = None) -> tuple[np.ndarray, np.ndarray]:
        events = events or []
        q = [np.clip(np.round(np.asarray(c) * FULL_SCALE), -(1 << 23), (1 << 23) - 1).astype(np.int64) for c in (left, right)]
        y = [self._channel(q[0], 0, events), self._channel(q[1], 1, events)]
        a = [np.roll(c.astype(float), 1) / FULL_SCALE for c in y]          # one frame of latency in the path
        for c in a:
            c[0] = 0.0
        out = []
        for i, c in enumerate(a):
            d = c + dbfs_to_amp(self.h2) * c ** 2 * 2 + dbfs_to_amp(self.h3) * c ** 3 * 4      # a little distortion, scaled to full scale
            d = d + (dbfs_to_amp(self.xt)) * a[1 - i]
            d = d + dbfs_to_amp(self.noise) / math.sqrt(2) * self.rng.standard_normal(len(d))
            out.append(self._delay(d))
        return out[0], out[1]

    def _delay(self, x: np.ndarray) -> np.ndarray:
        """The converters' delay, a whole number of samples plus a fraction by linear interpolation."""
        whole = int(math.floor(self.delay))
        frac = self.delay - whole
        y = np.concatenate([np.zeros(whole), x])[:len(x)]
        if frac:
            y = (1 - frac) * y + frac * np.concatenate([[0.0], y[:-1]])
        return y


def write_wav(path: Path, chans: list[np.ndarray], fs: int = FS) -> None:
    """24-bit stereo PCM WAV."""
    n = min(len(c) for c in chans)
    q = np.stack([np.clip(np.round(np.asarray(c[:n]) * FULL_SCALE), -(1 << 23), (1 << 23) - 1).astype(np.int64) for c in chans], axis=1)
    raw = bytearray()
    for v in q.reshape(-1):
        raw += int(v & 0xFFFFFF).to_bytes(3, "little")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(chans))
        w.setsampwidth(3)
        w.setframerate(fs)
        w.writeframes(bytes(raw))


def read_wav(path: Path) -> tuple[list[np.ndarray], int]:
    with wave.open(str(path)) as w:
        ch, width, fs = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
        v = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        v = np.where(v >> 23, v - (1 << 24), v) / FULL_SCALE
    else:
        v = np.frombuffer(raw, dtype={2: "<i2", 4: "<i4"}[width]).astype(float) / float(1 << (8 * width - 1))
    v = v.reshape(-1, ch)
    return [v[:, i] for i in range(ch)], fs


class AlsaRig:
    """The owner's PC interface through ALSA. `controller(op, ch, value)` writes the board's gain or mute register (the host
    driver of phase 3); events run on a timer thread, so their time is only approximate and the analysers find the step in
    the data. Written in phase 1 and not run on any hardware yet."""

    def __init__(self, play_dev: str, rec_dev: str, controller=None, fs: int = FS, pad_s: float = 0.6) -> None:
        self.play_dev, self.rec_dev, self.controller, self.fs, self.pad = play_dev, rec_dev, controller, fs, pad_s
        self.kind = "alsa"

    def settings(self) -> dict:
        return {"play_device": self.play_dev, "record_device": self.rec_dev, "pad_s": self.pad}

    def reset_controls(self) -> None:
        if self.controller:
            for ch in (0, 1):
                self.controller("gain", ch, 0x1000)
                self.controller("mute", ch, 0)

    def play_record(self, left: np.ndarray, right: np.ndarray, events: list[Event] | None = None) -> tuple[np.ndarray, np.ndarray]:
        import threading
        import time
        lead = np.zeros(int(self.pad * self.fs))
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "play.wav", Path(d) / "rec.wav"
            write_wav(src, [np.concatenate([lead, left, lead]), np.concatenate([lead, right, lead])], self.fs)
            secs = (len(left) + 2 * len(lead)) / self.fs + 1.0
            rec = subprocess.Popen(["arecord", "-q", "-D", self.rec_dev, "-f", "S24_3LE", "-r", str(self.fs), "-c", "2",
                                    "-d", str(int(math.ceil(secs))), str(dst)])
            time.sleep(0.3)
            t0 = time.time()
            timers = []
            for e in events or []:
                if not self.controller:
                    raise RuntimeError("events need a controller for the board's registers")
                timers.append(threading.Timer(self.pad + e.t, self.controller, args=(e.op, e.ch, e.value)))
                timers[-1].start()
            subprocess.run(["aplay", "-q", "-D", self.play_dev, str(src)], check=True, timeout=secs + 15)
            rec.wait(timeout=secs + 15)
            for t in timers:
                t.join()
            del t0
            (cl, cr), fs = read_wav(dst)
        k = int(self.pad * self.fs)
        return cl[k:k + len(left) + int(0.3 * self.fs)], cr[k:k + len(right) + int(0.3 * self.fs)]


# ---- the measurements ------------------------------------------------------------------------------------------------


@dataclass
class Plan:
    level_db: float = -30.0            # the first level to play: low, because the owner may be wearing headphones
    thd_level_db: float = -6.0
    tone_s: float = 1.0
    silence_s: float = 1.5
    freqs: tuple = (20, 50, 100, 250, 500, 1000, 2000, 5000, 10000, 15000, 20000)
    f_thd: float = 1000.0
    click_f: float = 1000.0
    click_at_s: float = 0.6
    click_gain: int = 0x0800           # a step from 1.0 to 0.5
    fs: int = FS
    notes: list = field(default_factory=list)


def _tail(x: np.ndarray, fs: int, skip_s: float = 0.15, trail_s: float = 0.12) -> np.ndarray:
    """The steady part of a capture of a faded tone: the fade in, the fade out and the converters' start-up are cut off."""
    x = np.asarray(x)
    return x[int(skip_s * fs):max(len(x) - int(trail_s * fs), int(skip_s * fs) + 1)] if len(x) > int((skip_s + trail_s) * fs) else x


def run_all(rig, plan: Plan, baseline: dict | None = None, datasheet: dict | None = None) -> dict:
    """Run every measurement on `rig`; returns the result dict that run_measure.py writes. `baseline` holds the same keys
    measured with the PC interface alone; `datasheet` the codec's figures (each in dB, lower is better)."""
    fs = plan.fs
    res: dict = {"plan": {k: v for k, v in plan.__dict__.items() if k != "notes"}}
    rig.reset_controls()
    # latency: noise burst, analogue in to analogue out
    ref = noise_burst(1.0, plan.level_db, fs)
    r_l, _ = rig.play_record(ref, np.zeros_like(ref))
    res["latency_samples"] = latency_samples(ref, r_l[:len(ref) + 400])
    res["latency_ms"] = 1000.0 * res["latency_samples"] / fs
    # frequency response, relative to 1 kHz
    levels = {}
    for f in plan.freqs:
        x = tone(f, plan.tone_s, plan.level_db, fs)
        a, _ = rig.play_record(x, np.zeros_like(x))
        levels[f] = level_dbfs(_tail(a, fs), fs, f)
    ref_l = levels.get(1000, levels[min(levels, key=lambda k: abs(k - 1000))])
    res["frequency_response_db"] = {str(f): round(v - ref_l, 3) for f, v in levels.items()}
    res["level_at_1khz_dbfs"] = ref_l
    # THD+N at 1 kHz
    x = tone(plan.f_thd, plan.tone_s, plan.thd_level_db, fs)
    a, _ = rig.play_record(x, np.zeros_like(x))
    res["thd_n"] = thd_n(_tail(a, fs), fs, plan.f_thd)
    # noise floor: silence in, capture
    z = np.zeros(int(plan.silence_s * fs))
    a, b = rig.play_record(z, z)
    res["noise_floor_dbfs"] = {"left": noise_floor_dbfs(_tail(a, fs), fs), "right": noise_floor_dbfs(_tail(b, fs), fs)}
    # crosstalk: left driven, right quiet, and the other way round
    x = tone(plan.f_thd, plan.tone_s, plan.thd_level_db, fs)
    a, b = rig.play_record(x, np.zeros_like(x))
    c, d = rig.play_record(np.zeros_like(x), x)
    res["crosstalk_db"] = {"left_to_right": crosstalk_db(_tail(a, fs), _tail(b, fs), fs, plan.f_thd),
                           "right_to_left": crosstalk_db(_tail(d, fs), _tail(c, fs), fs, plan.f_thd)}
    # click energy of a gain step, smoothed (the design) against an unsmoothed control
    secs = plan.click_at_s + 0.5
    x = tone(plan.click_f, secs, plan.level_db, fs, fade_ms=20)
    ev = [Event(plan.click_at_s, "gain", 0, plan.click_gain)]
    rig.reset_controls()
    a, _ = rig.play_record(x, x, ev)
    res["click"] = {"smoothed_db": click_energy_db(a, fs, plan.click_f, step_index(a, fs))}
    if hasattr(rig, "smooth"):                                  # the simulated control is the same rig without the ramp
        rig.smooth = False
        rig.reset_controls()
        c, _ = rig.play_record(x, x, ev)
        rig.smooth = True
        rig.reset_controls()
        res["click"]["control_db"] = click_energy_db(c, fs, plan.click_f, step_index(c, fs))
        res["click"]["control"] = "the same rig with the ramp removed"
        res["click"]["improvement_db"] = res["click"]["control_db"] - res["click"]["smoothed_db"]
    else:
        res["click"]["control"] = "not run: needs an unsmoothed build (RAMP_STEP = 0xFFFF) loaded separately; give its capture to compare_click"
    # who limits what
    base, ds = baseline or {}, datasheet or {}
    res["limits"] = {
        "thd_n": classify(res["thd_n"]["thd_n_db"], base.get("thd_n_db"), ds.get("thd_n_db")),
        "noise_floor": classify(max(res["noise_floor_dbfs"].values()), base.get("noise_floor_dbfs"), ds.get("noise_floor_dbfs")),
        "crosstalk": classify(max(res["crosstalk_db"].values()), base.get("crosstalk_db"), ds.get("crosstalk_db")),
    }
    return res
