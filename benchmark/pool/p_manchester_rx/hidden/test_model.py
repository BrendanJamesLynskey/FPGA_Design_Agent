from model import Model, classify, frame, wave


def test_good_frames_for_every_byte():
    for b in (0, 1, 0x80, 0xA5, 0xFF):
        assert classify(frame(b), 64) == ("good", b)


def test_error_classes():
    assert classify(frame(0x55, parity_flip=True), 64) == ("parity",)
    bad = frame(0x55)
    bad[2] = 0
    assert classify(bad, 64) == ("preamble",)
    assert classify(frame(0x55), 64, drop_transition=8) == ("coding",)
    assert classify(frame(0x55, parity_flip=True), 64, drop_transition=3) == ("coding",)


def test_counts_leds_and_clear():
    m = Model(64)
    m.receive(frame(0x3C))
    m.receive(frame(0x3C, True))
    m.receive(frame(0x3C), drop_transition=6)
    assert [m.read(i) for i in range(5)] == [0x3C, 1, 1, 0, 1] and m.leds() == 0x013C
    m.write(5, 0)
    assert [m.read(i) for i in range(5)] == [0x3C, 0, 0, 0, 0]
    assert len(wave(frame(1), 64)) == 14 * 64
