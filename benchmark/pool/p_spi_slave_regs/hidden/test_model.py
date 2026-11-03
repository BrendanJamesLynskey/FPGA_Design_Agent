from model import Model, bits_of


def run(m, data, cut=None):
    bits = bits_of(data)
    if cut is not None:
        bits = bits[:cut]
    return m.frame(bits)


def bytes_from(miso):
    return [sum(miso[8 * j + k] << (7 - k) for k in range(8)) for j in range(len(miso) // 8)]


def test_id_and_write_read_back():
    m = Model()
    assert bytes_from(run(m, [0x80, 0, 0]))[1:] == [0xA7, 0]
    run(m, [0x01, 0x11, 0x22, 0x44])
    assert bytes_from(run(m, [0x81, 0, 0, 0, 0]))[1:] == [0x11, 0x22, 0x44, 0]
    assert m.rd(8) == 0x11 ^ 0x22 ^ 0x44 and m.frames == 3 and m.last == 0x81


def test_ro_zero_and_out_of_range():
    m = Model()
    run(m, [0x00, 0x99, 0x55])                 # write to reg 0 ignored, then to reg 1
    assert m.reg[1] == 0x55 and m.rd(0) == 0xA7          # byte 1 -> reg 0 (ignored), byte 2 -> reg 1
    assert bytes_from(run(m, [0x8E, 0, 0, 0]))[1:] == [0, 0, 0xFF]
    run(m, [0x10, 0xAA])
    assert m.rd(16) == 0xFF
    assert bytes_from(run(m, [0xFF, 0, 0]))[1:] == [0xFF, 0xA7]   # 127, then the address wraps to 0: the ID


def test_partial_and_empty_frames():
    m = Model()
    run(m, [0x05, 0xEE], cut=12)
    assert m.reg[5] == 0 and m.bad == 1 and m.frames == 1 and m.last == 0x05
    run(m, [], cut=0)
    assert m.frames == 1
    run(m, [0x03], cut=3)
    assert m.bad == 2 and m.last == 0x05
