from model import Model, frame_bits, waveform


def test_frame_bits_and_parity():
    assert frame_bits(0x00) == [1, 1, 1, 1, 0] + [0] * 8 + [0]
    assert frame_bits(0x01)[5:] == [1, 0, 0, 0, 0, 0, 0, 0, 1]
    assert frame_bits(0xA5)[5:] == [1, 0, 1, 0, 0, 1, 0, 1, 0]
    for b in range(256):
        f = frame_bits(b)
        assert sum(f[5:]) % 2 == 0 and len(f) == 14


def test_waveform_polarity_and_length():
    w = waveform(0x01, 8)
    assert len(w) == 14 * 8
    assert w[:8] == [0, 0, 0, 0, 1, 1, 1, 1]          # a 1 bit: low then high
    assert w[4 * 8: 5 * 8] == [1, 1, 1, 1, 0, 0, 0, 0]  # the 0 bit of the lead-in
    assert w[5 * 8: 6 * 8] == [0, 0, 0, 0, 1, 1, 1, 1]  # data bit 0 = 1


def test_busy_drop_and_counts():
    m = Model()
    m.write(0, 0x5A)
    m.write(0, 0x11)
    assert m.read(1) == 0x101 and m.read(0) == 0x5A
    m.finish()
    assert m.read(1) == 0x100 and m.read(2) == 1
