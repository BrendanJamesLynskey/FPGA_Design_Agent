from model import Model


def test_convert_and_clamp():
    m = Model()
    m.write(0, 12345)
    assert m.bcd() == 0x12345 and m.read(2) == 0
    m.write(0, 99999)
    assert m.read(2) == 0 and m.bcd() == 0x99999
    m.write(0, 100000)
    assert m.read(2) == 1 and m.bcd() == 0x99999
    m.write(0, 0x1FFFF | 1 << 31)
    assert m.read(2) == 3


def test_negative_zero_and_ignored_bits():
    m = Model()
    m.write(0, 1 << 31)
    assert m.neg is False and m.read(2) == 0
    m.write(0, 0x7FFE0000 | 5)
    assert m.read(0) == 5


def test_display_markers():
    m = Model()
    m.write(0, 1 << 31 | 42)
    d = m.display()
    assert set(d) == {0, 1, 2} and m.leds() == 0x42
    m.write(0, 1 << 31 | 123456)
    d = m.display()
    assert set(d) == {0, 1, 2, 3, 4, 5, 6} and m.leds() == 0x9999
    m.write(0, 0)
    assert set(m.display()) == {0}
