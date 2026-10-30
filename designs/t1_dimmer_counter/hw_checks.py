"""T1's ILA captures on the board, and the rules each capture is checked against.

flow/bringup.py runs every capture in CAPTURES on the ILA build: ``setup`` over the
UART, arm the trigger, ``stimulus`` over the UART, upload, then ``check`` the samples
(``{probe name: [value per clock]}``, 1024 consecutive clocks at 100 MHz).

Comparison rules (from spec.yaml, with model.py giving the expected values):
- **count_write** (trigger: ``win_wr == 1 AND addr == 0x80``, a COUNT write sent over
  the UART). Exactly one ``win_wr`` in the window; ``count`` holds the old value up to
  and including that clock and the written value from the next clock on (the register
  takes the write at the clock edge that ends the ``win_wr`` cycle); the LED rule
  below holds on every clock.
- **pwm_<duty>** (trigger: ``phase == 0``). 1024 samples are exactly one PWM period
  (256 phases x PWM_PRESCALE). (1) ``phase`` steps by +1 (mod 256) and every whole run
  is PWM_PRESCALE clocks long. (2) The LED rule on every clock k >= 1:
  ``led[k] == (count[k-1] if phase[k-1] < duty else 0)`` (LED is a register of the
  compare; spec: "lit while phase < DUTY_EFF", outputs registered). (3) Each LED's
  lit samples over the window equal ``model.led_on_clocks()`` exactly: duty x 4 for
  a 1 bit of COUNT, 0 for a 0 bit.
Exact equality everywhere: no tolerance.

USB power (owner rule): the board runs from its USB cable, so the captures light at
most 5 LEDs, at duties up to 0xA0 (63 %), for well under a second each, and the
design is left at its reset values (COUNT 0: LEDs off) afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from designs.t1_dimmer_counter import model as m
from shell.host import protocol as p

PRESCALE = m.PARAMS["PWM_PRESCALE"]
PERIOD = 256 * PRESCALE
COUNT_BEFORE, COUNT_WRITTEN, WRITE_DUTY = 0x0003, 0x1234, 0x10
PWM_COUNT = 0x8421                     # 4 LEDs (0, 5, 10, 15), every nibble used
PWM_DUTIES = (0x08, 0x40, 0xA0)        # the three dimmer levels


def w(sh: Any, off: int, v: int) -> None:
    sh.write(p.WINDOW_BASE + off, v)


@dataclass
class Capture:
    name: str
    condition: str                               # AND / OR across the compares
    position: int                                # trigger position in the window
    compares: dict[str, int]                     # probe name -> the value it must equal (AND/OR)
    setup: Callable[[Any], None]
    stimulus: Callable[[Any], None]
    check: Callable[[dict[str, list[int]]], dict[str, Any]]
    expect: dict[str, Any] = field(default_factory=dict)


def led_rule(s: dict[str, list[int]], duty: int) -> list[int]:
    """Clocks k where led[k] differs from the registered compare of clock k-1."""
    bad = []
    for k in range(1, len(s["led"])):
        want = s["count"][k - 1] if s["phase"][k - 1] < duty else 0
        if s["led"][k] != want:
            bad.append(k)
    return bad


def phase_rule(phase: list[int]) -> list[str]:
    errs, runs, run = [], [], 1
    for k in range(1, len(phase)):
        if phase[k] == phase[k - 1]:
            run += 1
        elif phase[k] == (phase[k - 1] + 1) % 256:
            runs.append(run)
            run = 1
        else:
            errs.append(f"phase jumps {phase[k-1]} -> {phase[k]} at sample {k}")
    whole = runs[1:]                     # the first run is cut by where the window starts
    if any(r != PRESCALE for r in whole):
        errs.append(f"phase run lengths {sorted(set(whole))}, expected {PRESCALE}")
    return errs


def check_count_write(s: dict[str, list[int]]) -> dict[str, Any]:
    hits = [k for k in range(len(s["win_wr"])) if s["win_wr"][k] == 1 and s["addr"][k] == 0x80]
    errs: list[str] = []
    if len(hits) != 1:
        errs.append(f"expected one COUNT write in the window, saw {len(hits)}")
    else:
        t = hits[0]
        if any(c != COUNT_BEFORE for c in s["count"][: t + 1]):
            errs.append("count changed before the write took effect")
        if any(c != COUNT_WRITTEN for c in s["count"][t + 1:]):
            errs.append(f"count is not 0x{COUNT_WRITTEN:04X} from the clock after win_wr")
    bad_led = led_rule(s, WRITE_DUTY)
    if bad_led:
        errs.append(f"LED rule broken at {len(bad_led)} clocks (first {bad_led[:5]})")
    return {"pass": not errs, "errors": errs, "write_at_sample": hits[0] if hits else None,
            "samples": len(s["count"]), "led_rule_violations": len(bad_led)}


def make_pwm_check(duty: int) -> Callable[[dict[str, list[int]]], dict[str, Any]]:
    def check(s: dict[str, list[int]]) -> dict[str, Any]:
        model = m.DimmerCounterModel()
        model.window_write(m.COUNT, PWM_COUNT)
        model.window_write(m.DUTY, duty)
        want = model.led_on_clocks()
        n = len(s["led"])
        got = [sum((v >> i) & 1 for v in s["led"]) for i in range(16)]
        errs = []
        if n != PERIOD:
            errs.append(f"{n} samples, expected one PWM period of {PERIOD}")
        if set(s["count"]) != {PWM_COUNT}:
            errs.append(f"count not constant 0x{PWM_COUNT:04X}: {sorted(set(s['count']))[:4]}")
        errs += phase_rule(s["phase"])
        bad_led = led_rule(s, duty)
        if bad_led:
            errs.append(f"LED rule broken at {len(bad_led)} clocks (first {bad_led[:5]})")
        if got != want:
            errs.append(f"LED on-clocks {got}, model {want}")
        return {"pass": not errs, "errors": errs, "duty": duty, "samples": n,
                "led_on_clocks_measured": got, "led_on_clocks_model": want,
                "led_rule_violations": len(bad_led)}
    return check


def _setup_count_write(sh: Any) -> None:
    w(sh, m.CTRL, m.CTRL_DISPLAY_EN)
    w(sh, m.DUTY, WRITE_DUTY)
    w(sh, m.COUNT, COUNT_BEFORE)


def _setup_pwm(duty: int) -> Callable[[Any], None]:
    def setup(sh: Any) -> None:
        w(sh, m.CTRL, m.CTRL_DISPLAY_EN)
        w(sh, m.COUNT, PWM_COUNT)
        w(sh, m.DUTY, duty)
    return setup


def _nothing(sh: Any) -> None:
    pass


CAPTURES: list[Capture] = [
    Capture("count_write", "AND", 64, {"win_wr": 1, "addr": 0x80}, _setup_count_write,
            lambda sh: w(sh, m.COUNT, COUNT_WRITTEN), check_count_write),
] + [
    Capture(f"pwm_{d:02x}", "AND", 0, {"phase": 0x00}, _setup_pwm(d), _nothing, make_pwm_check(d))
    for d in PWM_DUTIES
]


def restore(sh: Any) -> None:
    """Back to the reset values: COUNT 0 (LEDs off), DUTY 0x40, display on."""
    w(sh, m.COUNT, 0)
    w(sh, m.DUTY, 0x40)
    w(sh, m.CTRL, m.CTRL_DISPLAY_EN)
