from model import Model, decode, encode


def test_known_codewords():
    assert encode(0) == 0
    # data 1 -> d0 at position 3: p1 = 1, p2 = 1, p4 = 0; word bits (pos1..7) = 1 1 1 0 0 0 0 = 0b0000111; parity 1 -> 0b10000111
    assert encode(1) == 0b10000111
    assert all(bin(encode(d)).count("1") % 2 == 0 for d in range(16))
    assert all(decode(encode(d)) == (d, 0, 0) for d in range(16))


def test_every_single_error_is_fixed():
    for d in range(16):
        w = encode(d)
        for b in range(8):
            data, s, code = decode(w ^ (1 << b))
            assert data == d and code == 1 and s == (b + 1 if b < 7 else 0)


def test_double_errors_flagged_data_as_received():
    w = encode(0b1010)
    data, s, code = decode(w ^ 0b00000110)          # positions 2 and 3
    assert code == 2 and s != 0 and data == 0b1010 ^ 0b0001
    data, s, code = decode(w ^ 0b10000001)          # position 1 and the overall bit
    assert code == 2


def test_stats_and_registers():
    m = Model()
    m.write(1, 5)
    m.write(2, encode(5) ^ 1)
    m.write(2, encode(5) ^ 0b11)
    m.write(2, encode(5))
    assert m.read(4) == 1 | 1 << 8 and m.read(0) == 0 and m.read(3) >> 8 == 0
    m.write(0, 0xF5)
    assert m.read(0) == 5 and m.read(1) == encode(5)
    m.write(4, 0)
    assert m.read(4) == 0
