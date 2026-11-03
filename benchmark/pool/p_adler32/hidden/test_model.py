import zlib

from model import Model, adler32


def test_known_value():
    assert adler32(b"Wikipedia") == 0x11E60398
    assert adler32(b"") == 1


def test_matches_zlib_including_modulus():
    for data in (b"a", bytes(range(256)) * 3, b"\xff" * 300, b"\x00" * 70000):
        assert adler32(data) == zlib.adler32(data)


def test_word_is_little_endian_and_ctrl():
    m = Model()
    m.write(1, 0x696B6957)                  # "Wiki" little-endian
    m.write(0, ord("p"))
    m.write(0, ord("e") | 0x100)
    assert m.data == b"Wikipe" and m.read(3) == 6
    assert m.read(2) == adler32(b"Wikipe") and m.leds() == adler32(b"Wikipe") & 0xFFFF
    m.write(4, 1)
    assert m.read(2) == 1 and m.read(3) == 0 and m.leds() == 1
    m.write(4, 0)
    m.write(0, 1)
    m.write(4, 2)
    assert m.read(3) == 1
