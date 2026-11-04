from model import Model


def test_good_kick_and_early():
    m = Model(40, 120)
    m.enable(True)
    m.advance(60)
    m.kick(0x6B)
    assert m.c == 0 and m.read(1) == 0
    m.advance(10)
    m.kick(0x6B)
    assert m.read(2) == 1 and m.read(1) == 0b011 and m.c == 0


def test_late_repeats_every_window_close_plus_one():
    m = Model(40, 120)
    m.enable(True)
    m.advance(121)
    assert m.read(3) == 1 and m.c == 0
    m.advance(121 * 2 + 5)
    assert m.read(3) == 3 and m.c == 5 and m.read(1) == 0b101


def test_bad_key_disabled_and_clear():
    m = Model(40, 120)
    m.kick(0x11)
    m.kick(0x6B)                       # disabled: no effect
    m.advance(1000)
    assert m.read(4) == 1 and m.read(2) == 0 and m.read(3) == 0
    m.enable(True)
    m.advance(130)
    m.write(1, 0)
    assert [m.read(i) for i in (1, 2, 3, 4)] == [0, 0, 0, 0] and m.read(5) == 40 and m.read(6) == 120
