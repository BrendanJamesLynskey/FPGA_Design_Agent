from model import Model, bar_len


def test_bar_len():
    assert [bar_len(r) for r in (0, 1, 16, 17, 240, 241, 255)] == [0, 1, 1, 2, 15, 16, 16]


def test_leds_peak_marker():
    m = Model()
    m.level(0x50)                    # N = 5
    assert m.leds() == 0b11111
    m.level(0x10)                    # N = 1, marker stays at 5
    assert m.peak == 5 and m.leds() == 0b10001


def test_decay_sequence_and_merge():
    m = Model()
    m.level(0x40)
    m.level(0x20)
    seq = m.decay_leds()
    assert seq == [0b111, 0b11] and m.peak == 4      # 4 -> 3 (marker above the 2-LED bar), then merges into the bar
    m.clear_peak()
    assert m.peak == 2 and m.leds() == 0b11


def test_maxraw():
    m = Model()
    m.level(200)
    m.level(30)
    assert m.read(2) == 200
    m.write(2, 0)
    assert m.read(2) == 30 and m.read(0) == 2
