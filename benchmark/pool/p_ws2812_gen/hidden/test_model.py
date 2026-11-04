from model import Model, bits_for, scale, waveform


def test_scale_is_not_full_at_255():
    assert scale(255, 255) == 254 and scale(255, 0) == 0 and scale(128, 128) == 64


def test_grb_order_msb_first():
    b = bits_for(0xFF0000, 1, 255)           # pure red: green byte, red byte, blue byte
    assert b[:8] == [0] * 8 and b[8:16] == [1, 1, 1, 1, 1, 1, 1, 0] and b[16:] == [0] * 8
    b = bits_for(0x010203, 2, 256 - 1)
    assert len(b) == 48


def test_waveform_widths():
    w = waveform([1, 0], 4, 8, 8, 4)
    assert w == [1] * 8 + [0] * 4 + [1] * 4 + [0] * 8


def test_clamp_ignore_and_frames():
    m = Model()
    m.write(1, 0)
    assert m.read(1) == 1
    m.write(1, 99)
    assert m.read(1) == 16
    m.write(3, 1)
    m.write(3, 1)
    assert m.read(4) == 0x101 and m.read(5) == 1
    m.finish()
    assert m.read(4) == 0x100
