from model import Model


def test_autoreload_period_and_b_lead():
    m = Model()
    m.write(3, 9)
    m.write(4, 4)
    m.write(0, 0b00111111 & ~0b01000000 | 0b11 | (3 << 2) | (3 << 4))
    ev = m.ticks(30)
    a = [i for i, (x, _) in enumerate(ev) if x]
    b = [i for i, (_, y) in enumerate(ev) if y]
    assert a == [8, 18, 28] and b == [3, 13, 23]


def test_set_clear_modes_flags_and_forced_outputs():
    m = Model()
    m.write(3, 3)
    m.write(4, 2)
    m.write(0, 1 | (1 << 2) | (2 << 4) | (1 << 7))       # A set on match, B clear on match, B starts high
    assert m.leds() == 0b10
    m.ticks(2)
    assert m.leds() == 0b00 and m.read(5) == 2
    m.ticks(1)
    assert m.leds() == 0b01 and m.read(5) == 3
    m.write(5, 0)
    assert m.read(5) == 0


def test_cnt_write_only_when_stopped_and_wrap():
    m = Model()
    m.write(2, 0xFFFFFFFE)
    m.write(3, 1)
    m.write(0, 1)
    m.write(2, 77)
    assert m.read(2) == 0xFFFFFFFE
    m.ticks(3)
    assert m.read(2) == 1 and m.read(5) & 1
