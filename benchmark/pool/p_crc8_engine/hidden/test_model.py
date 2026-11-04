from model import CRC, DATA, STATUS, Model, crc8


def test_check_value():
    assert crc8(b"123456789") == 0x4B
    assert crc8(b"") == 0x00


def test_busy_drop_and_finish():
    m = Model()
    m.write(DATA, 0x31)
    assert m.read(STATUS) == 1 and m.read(CRC) == 0          # CRC still from before the byte
    m.write(DATA, 0x32)
    assert m.read(STATUS) == 0x101 and m.read(DATA) == 0x31
    m.finish()
    assert m.read(CRC) == crc8(b"1") and m.read(STATUS) == 0x100 and m.read(2) == 1


def test_ctrl_rules():
    m = Model()
    m.write(DATA, 5)
    m.write(4, 3)                                              # busy: ignored
    m.finish()
    assert m.read(2) == 1
    m.write(DATA, 1)
    m.write(DATA, 1)
    m.finish()
    m.write(4, 2)
    assert m.read(STATUS) == 0 and m.read(2) == 2
    m.write(4, 1)
    assert m.read(2) == 0 and m.read(CRC) == 0 and m.read(DATA) == 0


def test_dropped_saturates():
    m = Model()
    m.write(DATA, 1)
    for _ in range(300):
        m.write(DATA, 2)
    assert m.read(STATUS) >> 8 == 255
