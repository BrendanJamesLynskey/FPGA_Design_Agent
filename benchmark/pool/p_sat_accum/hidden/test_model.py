from model import Model, signed


def test_signed():
    assert signed(0xFF, 8) == -1 and signed(0x80, 8) == -128 and signed(0x7F, 8) == 127


def test_saturate_high_flag_only_when_clamped():
    m = Model(1000)
    for _ in range(10):
        m.tick(100)
    assert m.acc == 1000 and m.read(1) == 0          # exactly on the limit: no flag
    m.tick(100)
    assert m.acc == 1000 and m.read(1) == 1 and m.read(2) == 11


def test_saturate_low_and_wrap_free():
    m = Model(1000)
    for _ in range(20):
        m.tick(0x80)                                  # -128 each
    assert m.acc == -1000 and m.read(1) == 2 and m.read(0) == 0xFFFFFC18 and m.leds() == 0xFC18


def test_write_clamps_and_clear():
    m = Model(1000)
    m.write(0, 5000)
    assert m.acc == 1000
    m.write(0, 0xFFFF)
    assert m.acc == -1
    m.write(1, 0)
    m.write(2, 9)
    assert m.read(1) == 0 and m.read(2) == 0 and m.read(3) == 1000
    m.clear_level()
    assert m.acc == 0
