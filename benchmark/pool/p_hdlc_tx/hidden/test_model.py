from model import FLAG, Model, crc16_x25, frame_bits, stuffed_bits


def test_crc_check_value():
    assert crc16_x25(b"123456789") == 0x906E
    assert crc16_x25(b"") == 0x0000


def test_stuffing_runs_and_flag_never_inside():
    s = stuffed_bits(bytes([0xFF, 0xFF]))
    # 0xFF = eight 1s LSB first: 11111 0 111 ... a zero follows each run of five
    assert s[:6] == [1, 1, 1, 1, 1, 0]
    for payload in (b"\x7e", b"\xfb\xf8", b"\x1f\x1f", bytes(range(8))):
        f = frame_bits(payload)
        body = f[8:-8]
        assert all(sum(body[i:i + 6]) < 6 for i in range(len(body) - 5)), "six 1s in a row inside the frame"
    assert frame_bits(b"A")[:8] == FLAG and frame_bits(b"A")[-8:] == FLAG


def test_trailing_stuff_zero():
    # a payload whose last five FCS bits are 1s gets a 0 inserted before the closing flag
    hits = [b for b in range(256) if stuffed_bits(bytes([b]))[-6:] == [1, 1, 1, 1, 1, 0]]
    assert hits


def test_buffer_rules():
    m = Model()
    for i in range(9):
        m.write(0, i)
    assert len(m.buf) == 8 and m.dropped == 1
    m.write(1, 1)
    assert m.busy and m.read(3) == crc16_x25(bytes(range(8)))
    m.write(0, 99)
    m.write(1, 2)
    assert len(m.buf) == 8 and m.dropped == 2
    m.finish()
    assert m.read(2) == 8 << 4 | 2 << 8
    m.write(1, 2)
    assert not m.buf
