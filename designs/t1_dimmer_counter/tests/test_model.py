"""Unit tests of model.py on its own (the spec's rules, independent of the RTL)."""

from __future__ import annotations

from designs.t1_dimmer_counter import model as m


def test_glyphs_round_trip_and_are_distinct() -> None:
    pins = [m.segments_to_pins(g) for g in m.GLYPHS]
    assert len(set(pins)) == 16
    assert [m.pins_to_digit(x) for x in pins] == list(range(16))
    assert m.segments_to_pins("abcdef") == 0b1000000      # "0": only g dark (active low)


def test_debounce_rule() -> None:
    assert m.presses_in([1] * 4 + [0] * 10, 5) == 0
    assert m.presses_in([1] * 5 + [0] * 10, 5) == 1
    assert m.presses_in([1] * 5 + [0, 1] * 10 + [0] * 5, 5) == 1   # chatter while held is ignored
    assert m.debounce([1, 1, 1], 2) == [0, 1, 1]


def test_counter_priority_and_wrap() -> None:
    t = m.DimmerCounterModel()
    t.press(down=True)
    assert t.count == 0xFFFF
    t.press(up=True, down=True)
    assert t.count == 0
    t.window_write(m.COUNT, 5)
    t.press(clear=True, up=True)
    assert t.count == 0 and t.presses == [2, 2, 1]
    t.press(up=True, reg_write=True)                       # a register write on the same clock wins
    assert t.count == 0 and t.presses[0] == 3


def test_pwm_and_display() -> None:
    t = m.DimmerCounterModel()
    t.window_write(m.COUNT, 0x8001)
    assert t.led_on_clocks()[0] == 0x40 * 4 and t.led_on_clocks()[1] == 0 and t.pwm_period_clocks == 1024
    t.set_switches(0x00FF)
    t.window_write(m.CTRL, m.CTRL_DUTY_SRC | m.CTRL_DISPLAY_EN)
    assert t.duty_eff == 0xFF
    d = t.display()
    assert d[4] is None and d[5] is None and m.pins_to_digit(d[3]) == 8 and m.pins_to_digit(d[7]) == 0xF
    t.window_write(m.CTRL, 0)
    assert t.display() == [None] * 8


def test_spec_parameters_are_the_board_values() -> None:
    assert m.PARAMS["CLKS_PER_BIT"] == round(100e6 / 115200)
    assert m.PARAMS["DEBOUNCE_CYCLES"] == 1_000_000 and m.DESIGN_ID == 0x5431_4443
