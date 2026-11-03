from model import Model, seg_pins


def test_rollover_and_days():
    m = Model()
    m.write(0, 23 << 12 | 59 << 6 | 58)
    m.seconds(3)
    assert m.read(0) == 1 and m.read(1) == 1 and m.read(2) == 3


def test_invalid_write_ignored_whole():
    m = Model()
    m.write(0, 5 << 12 | 5 << 6 | 5)
    m.write(0, 24 << 12)
    m.write(0, 60)
    m.write(0, 61 << 6)
    assert m.read(0) == 5 << 12 | 5 << 6 | 5


def test_12h_display_rules():
    m = Model()
    m.twelve = True
    m.write(0, 0)
    assert m.display()[4][0] == seg_pins("abdeg") and m.display()[5][0] == seg_pins("bc") and m.leds() == 0
    m.write(0, 15 << 12)
    assert m.shown_hours() == (0, 3) and 5 not in m.display() and m.leds() == 1
    m.write(0, 12 << 12)
    assert m.shown_hours() == (1, 2) and m.leds(True) == 0x8001


def test_24h_display_and_dp():
    m = Model()
    m.write(0, 7 << 12 | 8 << 6 | 9)
    d = m.display()
    assert d[5][0] == seg_pins("abcdef") and d[4][1] == 0 and d[2][1] == 0 and d[3][1] == 1 and 6 not in d
