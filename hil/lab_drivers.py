"""Lab instruments behind the instrument contract (brief 221; brief 52's adapter step for the instruments a lab file can script).

``debug_core/instruments.py`` defines the contract: ``describe``, ``configure``, ``arm``, ``capture``, ``close``. The ILA drivers there return
``fda-capture/1`` (digital sample windows on a cycle time base). A bench instrument that answers a scalar question (a frequency, a level) returns
``fda-measurement/1`` instead: one reading with its unit, the channel, the instrument and its uncertainty when known. Brief 52 had not been run;
this module is its adapter step for the Red Pitaya and the M2K, and the mock and manual instruments the tests and dry runs use. No new driver:
the adapters call ``hil/instruments/redpitaya.py`` and ``m2k.py`` as they are.

Every ``configure`` that asks for a drive goes through :func:`hil.lab.check_drive` first, in the base class, so no driver can skip the lab file's
limits. Nothing opens a device at import or construction time; a real connection is made only by ``arm()``/``capture()`` of an adapter built
without a handle, and only an owner-run script does that.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from debug_core.instruments import Instrument
from hil import lab as L

MEASUREMENT = "fda-measurement/1"
_UNITS = {"hz": ("Hz", 1.0), "khz": ("Hz", 1e3), "mhz": ("Hz", 1e6), "ghz": ("Hz", 1e9), "v": ("V", 1.0), "mv": ("V", 1e-3), "uv": ("V", 1e-6)}
_QUANTITY_UNIT = {"frequency": "Hz", "voltage": "V"}


class ReadingError(ValueError):
    """A manual reading that cannot be used: no unit, a unit that does not fit the quantity, or not a number."""


def parse_reading(text: str, quantity: str) -> tuple[float, str]:
    """A typed reading as (value in the quantity's base unit, base unit). The unit is required ("25.0001 MHz", "3.29 V"): a bare number is
    refused, because a reading typed in the wrong unit (kHz for MHz) is the commonest manual error and the unit is what catches it. A unit of
    another quantity ("3.3 V" for a frequency) is refused."""
    m = re.fullmatch(r"\s*([-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)\s*([A-Za-zµ]+)?\s*", str(text))
    if not m:
        raise ReadingError(f"{text!r} is not a number with a unit (for example '25.0001 MHz')")
    num = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").replace("µ", "u")
    if not unit:
        raise ReadingError(f"{text!r} has no unit: type it with its unit (Hz, kHz, MHz, GHz for a frequency; mV, V for a voltage)")
    if unit.lower() not in _UNITS:
        raise ReadingError(f"unit {unit!r} is not one of Hz, kHz, MHz, GHz, mV, V")
    base, k = _UNITS[unit.lower()]
    want = _QUANTITY_UNIT.get(quantity)
    if want and base != want:
        raise ReadingError(f"{unit} is a unit of {'frequency' if base == 'Hz' else 'voltage'}, but this step asks for a {quantity}")
    return num * k, base


def freq_from_samples(samples: list[float | int], fs: float, threshold: float | None = None) -> float:
    """Frequency of a repetitive signal from evenly spaced samples: rising threshold crossings, linearly interpolated, first to last. A digital
    signal (0/1) uses 0.5. Needs at least three crossings; the resolution is about one sample over the window."""
    if threshold is None:
        lo, hi = min(samples), max(samples)
        threshold = (lo + hi) / 2.0
    cross: list[float] = []
    for i in range(1, len(samples)):
        a, b = samples[i - 1], samples[i]
        if a < threshold <= b:
            cross.append(i - 1 + (threshold - a) / (b - a))
    if len(cross) < 3:
        raise L.LabError(f"only {len(cross)} rising edges in the capture: not enough to measure a frequency (is the probe on the right pin?)")
    return (len(cross) - 1) * fs / (cross[-1] - cross[0])


class LabInstrument(Instrument):
    """Base for the lab adapters. ``entry`` is the lab file's instrument entry, ``lab`` the merged lab (for the safety limits)."""
    kind = "lab_instrument"
    mock = False

    def __init__(self, entry: dict[str, Any], lab: L.Lab) -> None:
        self.entry, self.lab, self.plan_, self.armed = entry, lab, None, False
        self.drives: list[dict[str, Any]] = []

    @property
    def id(self) -> str:
        return self.entry["id"]

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "model": self.entry.get("model"), "channels": [c.get("name") for c in self.entry.get("channels") or []],
                "limits": [c for c in self.entry.get("capabilities") or []], "safety": {"outputs": self.entry.get("outputs") or []},
                "mock": self.mock, "onboarded": bool(self.entry.get("onboarded"))}

    def configure(self, plan: dict[str, Any]) -> None:
        if "drive" in plan:                               # the lab file's limits first, whatever the driver is
            d = plan["drive"]
            L.check_drive(self.lab, self.id, d["output"], volts=d.get("volts"), amps=d.get("amps"), dbm=d.get("dbm"), hz=d.get("hz"),
                          attenuator_db=d.get("attenuator_db"), board_vcco_v=d.get("board_vcco_v"))
        elif plan.get("measure") not in L.MEASURES:
            raise L.LabError(f"{self.id}: plan needs 'drive' or a 'measure' of {', '.join(L.MEASURES)}")
        self.plan_, self.armed = plan, False

    def arm(self) -> None:
        if self.plan_ is None:
            raise RuntimeError("configure first")
        self.armed = True

    def capture(self) -> dict[str, Any]:
        if not self.armed or self.plan_ is None:
            raise RuntimeError("arm first")
        plan = self.plan_
        base = {"schema": MEASUREMENT, "instrument": self.describe(), "channel": plan.get("channel") or (plan.get("drive") or {}).get("output"),
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "mock": self.mock}
        if "drive" in plan:
            self._drive(plan["drive"])
            self.drives.append(dict(plan["drive"]))
            return {**base, "drive": plan["drive"], "value": None, "unit": None}
        value, unit, unc = self._measure(plan)
        return {**base, "measure": plan["measure"], "value": value, "unit": unit, "uncertainty": unc}

    def _measure(self, plan: dict[str, Any]) -> tuple[float, str, float | None]:
        raise NotImplementedError

    def _drive(self, d: dict[str, Any]) -> None:
        raise NotImplementedError

    def stop_outputs(self) -> None:
        """Called by the runner at the end of every run, whatever happened: every output off."""

    def close(self) -> None:
        self.stop_outputs()


class MockInstrument(LabInstrument):
    """Stands in for any instrument in a dry run or CI. ``truth`` maps a quantity (``"frequency"``) or ``(quantity, channel)`` to a value or a
    function of the plan. A reading it returns is marked ``mock`` and is never evidence in a requirements report."""
    kind = "mock_lab_instrument"
    mock = True

    def __init__(self, entry: dict[str, Any], lab: L.Lab, truth: dict[Any, Any] | None = None) -> None:
        super().__init__(entry, lab)
        self.truth = truth or {}
        self.output_on: set[str] = set()

    def _measure(self, plan: dict[str, Any]) -> tuple[float, str, float | None]:
        key = (plan["measure"], plan.get("channel"))
        v = self.truth.get(key, self.truth.get(plan["measure"]))
        if v is None:
            raise L.LabError(f"{self.id} (mock): no value set for {plan['measure']} on {plan.get('channel')}")
        v = v(plan) if callable(v) else v
        return float(v), _QUANTITY_UNIT.get(plan["measure"], ""), None

    def _drive(self, d: dict[str, Any]) -> None:
        self.output_on.add(d["output"])

    def stop_outputs(self) -> None:
        self.output_on.clear()


class ManualInstrument(LabInstrument):
    """The owner reads an instrument and types the value. ``ask(prompt) -> str``; the reading must carry its unit (:func:`parse_reading`)."""
    kind = "manual_lab_instrument"

    def __init__(self, entry: dict[str, Any], lab: L.Lab, ask: Callable[[str], str]) -> None:
        super().__init__(entry, lab)
        self.ask = ask

    def _measure(self, plan: dict[str, Any]) -> tuple[float, str, float | None]:
        prompt = plan.get("prompt") or f"Read the {plan['measure']} on {self.id} {plan.get('channel') or ''}".strip()
        typed = self.ask(prompt)
        value, unit = parse_reading(typed, plan["measure"])
        self.typed = typed
        return value, unit, None

    def _drive(self, d: dict[str, Any]) -> None:
        raise L.SafetyRefused(f"{self.id}: a manual instrument is set by the owner, not driven by a script")


class RedPitayaInstrument(LabInstrument):
    """The Red Pitaya over SCPI (hil/instruments/redpitaya.py). ``rp`` is a connected client (tests pass a fake); without one, ``arm`` connects to
    the lab file's address, which is the owner's script's job, not a test's."""
    kind = "redpitaya"

    def __init__(self, entry: dict[str, Any], lab: L.Lab, rp: Any | None = None) -> None:
        super().__init__(entry, lab)
        self.rp = rp

    def arm(self) -> None:
        super().arm()
        if self.rp is None:
            from hil.instruments.redpitaya import RedPitaya
            self.rp = RedPitaya(self.entry["connection"]["address"])

    def _measure(self, plan: dict[str, Any]) -> tuple[float, str, float | None]:
        ch = {"IN1": 1, "IN2": 2}[plan["channel"]]
        dec = int(plan.get("decimation", 1))
        data = self.rp.acquire(ch, dec)
        fs = 125e6 / dec
        if plan["measure"] == "frequency":
            return freq_from_samples(data, fs), "Hz", fs / len(data)         # resolution: one bin of the capture window
        if plan["measure"] == "voltage":
            return sum(data) / len(data), "V", None
        raise L.LabError(f"{self.id}: cannot measure {plan['measure']}")

    def _drive(self, d: dict[str, Any]) -> None:
        ch = {"OUT1": 1, "OUT2": 2}[d["output"]]
        self.rp.generate(ch, d.get("shape", "SINE"), float(d.get("hz", 1000.0)), float(d["volts"]), float(d.get("offset_v", 0.0)))

    def stop_outputs(self) -> None:
        if self.rp is not None:
            for ch in (1, 2):
                try:
                    self.rp.stop(ch)
                except Exception:                       # noqa: BLE001 - closing must not raise over a lost connection
                    pass
            try:
                self.rp.close()
            except Exception:                           # noqa: BLE001
                pass


class M2kInstrument(LabInstrument):
    """The ADALM2000 through libm2k (hil/instruments/m2k.py): frequency and logic level from the digital inputs, voltage from the scope. ``ctx`` is
    an open libm2k context (tests pass ``None`` and patch the capture functions); a real one is opened by ``arm`` through ``open_m2k``. Outputs
    (supplies, the AWG) are not driven by this adapter: the lab file lists them ``never_by_script`` until the owner confirms limits."""
    kind = "m2k"

    def __init__(self, entry: dict[str, Any], lab: L.Lab, ctx: Any | None = None) -> None:
        super().__init__(entry, lab)
        self.ctx = ctx

    def arm(self) -> None:
        super().arm()
        if self.ctx is None:
            from hil.instruments import m2k
            self.ctx = m2k.open_m2k()

    def _measure(self, plan: dict[str, Any]) -> tuple[float, str, float | None]:
        from hil.instruments import m2k
        ch = plan["channel"]
        if ch.startswith("DIO") and plan["measure"] in ("frequency", "logic"):
            fs = float(plan.get("fs", 100e6))
            n = int(plan.get("samples", 100_000))
            bits = m2k.logic_capture(self.ctx, fs, n)[int(ch[3:])]
            if plan["measure"] == "frequency":
                return freq_from_samples(bits, fs, 0.5), "Hz", fs / n
            return float(sum(bits)) / len(bits), "duty", None
        if ch in ("CH1", "CH2") and plan["measure"] == "voltage":
            a, b = m2k.scope_capture(self.ctx)
            s = a if ch == "CH1" else b
            return sum(s) / len(s), "V", None
        raise L.LabError(f"{self.id}: cannot measure {plan['measure']} on {ch}")

    def _drive(self, d: dict[str, Any]) -> None:
        raise L.SafetyRefused(f"{self.id}: this adapter does not drive outputs (the lab file keeps them never_by_script)")


def open_instrument(entry: dict[str, Any], lab: L.Lab, *, mock: bool = False, truth: dict[Any, Any] | None = None,
                    ask: Callable[[str], str] | None = None) -> LabInstrument:
    """The adapter for a lab entry. ``mock=True`` (dry runs, CI) returns a :class:`MockInstrument` for any entry. A manual entry needs ``ask``."""
    if mock or entry.get("mock"):
        return MockInstrument(entry, lab, truth)
    ctl = entry.get("control") or {}
    if ctl.get("mode") == "manual":
        if ask is None:
            raise L.LabError(f"{entry['id']}: a manual instrument needs a way to ask the owner (run the bring-up in a terminal)")
        return ManualInstrument(entry, lab, ask)
    cls = {"hil.instruments.redpitaya": RedPitayaInstrument, "hil.instruments.m2k": M2kInstrument}.get(ctl.get("driver"))
    if cls is None:
        _no_adapter(entry)
    return cls(entry, lab)


def _no_adapter(entry: dict[str, Any]) -> None:
    raise L.LabError(f"{entry['id']}: no adapter for driver {(entry.get('control') or {}).get('driver')!r} yet (adapters: redpitaya, m2k, manual, mock)")
