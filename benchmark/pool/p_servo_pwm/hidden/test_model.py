from model import Model


def test_width_and_train():
    m = Model(100, 10, 2)
    m.new_frame(0x0003)
    assert m.width() == 16 and m.read(1) == 16 and m.read(0) == 3
    t = m.pulse_train(2)
    assert len(t) == 200 and sum(t) == 32 and t[:17] == [1] * 16 + [0]


def test_off_and_leds():
    m = Model(100, 10, 2)
    m.new_frame(0x80FF)
    assert m.width() == 0 and sum(m.pulse_train(1)) == 0 and m.leds() == 0x80FF
    assert m.read(2) == 100 and m.read(7) == 0
