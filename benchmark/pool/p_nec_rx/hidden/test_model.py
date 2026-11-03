from model import Model, classify, ideal, ideal_repeat


def test_ideal_frame_and_repeat():
    t = 40
    assert classify(ideal(0x04, 0x08, t), t) == ("frame", 0x04, 0x08)
    assert classify(ideal_repeat(t), t) == ("repeat",)
    assert classify(ideal(0x04, 0x08, t, comp_flip=True), t) == ("check",)


def test_tolerance_and_rejection():
    t = 40
    d = [round(x * 1.15) for x in ideal(0xA5, 0x3C, t)]
    assert classify(d, t) == ("frame", 0xA5, 0x3C)
    d = [round(x * 0.85) for x in ideal(0xA5, 0x3C, t)]
    assert classify(d, t) == ("frame", 0xA5, 0x3C)
    bad = ideal(0xA5, 0x3C, t)
    bad[10] = 3 * t                                # a bit mark three units long
    assert classify(bad, t) == ("format",)
    bad = ideal(0xA5, 0x3C, t)
    bad[1] = 5 * t + t // 2                        # a space between repeat and frame windows
    assert classify(bad, t) == ("format",)
    assert classify([4 * t] + ideal(0, 0, t)[1:], t) == ("ignored",)


def test_counts_leds_clear():
    m = Model(40)
    m.receive(ideal(0x20, 0xDF, 40))
    m.receive(ideal_repeat(40))
    m.receive(ideal(1, 2, 40, True))
    m.receive([16 * 40, 5 * 40 + 20])                  # a space between the repeat and frame windows
    assert m.leds() == 0x20DF and [m.read(i) for i in range(2, 6)] == [1, 1, 1, 1]
    m.write(6, 0)
    assert [m.read(i) for i in range(2, 6)] == [0, 0, 0, 0]
