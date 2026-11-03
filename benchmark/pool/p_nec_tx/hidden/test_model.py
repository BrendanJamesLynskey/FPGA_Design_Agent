from model import Model, frame_bits, frame_wave, mark, repeat_wave, space


def test_bits_and_complements():
    b = frame_bits(0x04, 0x08)
    assert b[:8] == [0, 0, 1, 0, 0, 0, 0, 0] and b[8:16] == [1, 1, 0, 1, 1, 1, 1, 1]
    assert b[16:24] == [0, 0, 0, 1, 0, 0, 0, 0] and b[24:] == [1, 1, 1, 0, 1, 1, 1, 1]


def test_carrier_and_lengths():
    m = mark(2, 24, 6)
    assert len(m) == 48 and m[:6] == [1, 1, 1, 0, 0, 0] and sum(m) == 24
    assert len(space(3, 24)) == 72
    unit = 24
    ones = sum(frame_bits(0x12, 0x34))
    assert len(frame_wave(0x12, 0x34, unit, 6)) == (16 + 8 + 32 + 32 + 2 * ones + 1) * unit
    assert len(repeat_wave(unit, 6)) == (16 + 4 + 1) * unit


def test_frame_length_formula():
    unit = 8
    for addr, cmd in ((0, 0), (0xFF, 0xFF), (0x5A, 0xA5)):
        ones = sum(frame_bits(addr, cmd))
        assert len(frame_wave(addr, cmd, unit, 4)) == (16 + 8 + 32 + 32 + 2 * ones + 1) * unit


def test_send_busy_and_repeat_counts():
    m = Model()
    m.write(0, 0x1FF)
    m.write(1, 7)
    m.write(2, 1)
    m.write(2, 1)
    m.repeat()
    assert m.read(3) == 1 | 1 << 8 | 1 << 16 and m.sent == (0xFF, 7) and m.leds(True) == 0x0701
    m.finish()
    assert m.read(4) == 1
