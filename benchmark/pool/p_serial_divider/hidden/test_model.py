from model import Model


def divide(m, a, b):
    m.write(0, a)
    m.write(1, b)
    m.write(2, 1)


def test_normal_division():
    m = Model()
    divide(m, 1000, 7)
    assert m.read(3) == 142 and m.read(4) == 6 and m.read(5) == 2 | 17 << 8


def test_divide_by_zero_and_larger_divisor():
    m = Model()
    divide(m, 1234, 0)
    assert m.read(3) == 0xFFFF and m.read(4) == 1234 and m.read(5) == 2 | 4 | 1 << 8 and m.leds() == 0x80FF
    divide(m, 5, 9)
    assert m.read(3) == 0 and m.read(4) == 5 and m.read(5) == 2 | 2 << 8 and m.leds() == 0


def test_edge_values():
    m = Model()
    divide(m, 0xFFFF, 1)
    assert m.read(3) == 0xFFFF and m.read(4) == 0 and m.read(5) >> 8 == 17
    divide(m, 0xFFFF, 0xFFFF)
    assert m.read(3) == 1 and m.read(4) == 0
    divide(m, 0, 5)
    assert m.read(3) == 0 and m.read(5) >> 8 == 2
