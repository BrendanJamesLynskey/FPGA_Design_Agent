from model import Model


def bits(s):
    return [int(c) for c in s]


def test_overlapping_matches():
    m = Model()
    hits = m.feed(bits("1011011"))
    assert m.count == 2 and hits == [False, False, False, True, False, False, True]


def test_suppressed_until_len_bits_and_invert():
    m = Model()
    m.write(0, 0b0000)
    m.write(1, 3)
    assert m.feed(bits("00")) == [False, False]          # fewer than LEN bits so far: no match on leading zeros
    assert m.feed(bits("0")) == [True]
    m.write(5, 0)
    assert m.feed(bits("11"), inv=1) == [False, False]
    assert m.feed(bits("1"), inv=1) == [True]


def test_len_clamps_and_registers():
    m = Model()
    m.write(1, 0)
    m.write(0, 1)
    assert m.feed(bits("01"))[-1] is True and m.read(1) == 0
    m.write(1, 12)
    m.write(0, 0xA5)
    m.write(5, 0)
    m.feed(bits("10100101"))
    assert m.count == 1 and m.read(2) == 0xA5 and m.read(4) == 8
