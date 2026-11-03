from model import Model


def mk():
    return Model(100, 200, 80, 220)


def test_mapping_and_clamps():
    m = mk()
    assert [m.position(w) for w in (80, 100, 101, 150, 199, 200, 220)] == [0, 0, 2, 127, 252, 255, 255]


def test_bad_pulses_ignored_and_counted():
    m = mk()
    m.pulse(150)
    assert m.pos == 127 and m.good == 1 and m.lastgood
    assert m.pulse(79) is False and m.pulse(221) is False
    assert m.pos == 127 and m.bad == 2 and not m.lastgood and m.read(0) == 221


def test_failsafe_and_recovery():
    m = mk()
    assert m.pos == 128 and not m.fail
    m.pulse(100)
    m.timeout()
    assert m.pos == 128 and m.read(2) == 1 | 2 and m.leds() == 128 | 1 << 14 | 1 << 15
    m.pulse(70)                                   # bad: does not clear failsafe
    assert m.fail
    m.pulse(200)
    assert not m.fail and m.pos == 255
    m.write(5, 0)
    assert m.good == 0 and m.bad == 0
