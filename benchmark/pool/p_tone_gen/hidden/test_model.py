from model import WEIGHT, Model, half_period


def test_scale_rises_and_octave_halves():
    h = [half_period(96, k, 0) for k in range(8)]
    assert h == sorted(h, reverse=True) and len(set(h)) == 8
    assert half_period(96, 0, 0) == 192 and half_period(96, 7, 0) == 96
    assert half_period(96, 7, 1) == 48 and half_period(96, 3, 1) == 72
    assert WEIGHT == (24, 22, 20, 18, 16, 15, 13, 12)


def test_registers_and_leds():
    m = Model(96)
    m.sw = 0x8000 | 8 | 5
    assert m.read(0) == 0b1101 and m.read(1) == 96 * 15 // 12 // 2 and m.leds() == 0x8000 | 8 | 5
    m.toggles = 9
    m.write(2, 1)
    assert m.read(2) == 0
