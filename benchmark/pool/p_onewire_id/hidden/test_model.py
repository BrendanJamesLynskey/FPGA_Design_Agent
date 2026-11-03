from model import Model, crc8_maxim


def test_crc_known_values():
    assert crc8_maxim(bytes([0x02, 0x1C, 0xB8, 0x1C, 0x00, 0x00, 0x00])) == crc8_maxim(bytes([0x02, 0x1C, 0xB8, 0x1C, 0x00, 0x00, 0x00]))
    assert crc8_maxim(b"") == 0
    assert crc8_maxim(bytes([0x01])) == 0x5E
    assert crc8_maxim(bytes([0x00])) == 0x00


def test_good_absent_and_bad_crc_results():
    m = Model()
    m.read_done(True, 0xBEEF)
    assert m.read(1) == 0b1110 and m.read(2) == 0xBEEF and m.read(4) == 0
    assert m.read(3) == crc8_maxim(bytes([0xEF, 0xBE]))
    m.read_done(False, 0)
    assert m.read(1) == 0b0010 and m.read(4) == 1 and m.read(2) == 0xBEEF
    m.read_done(True, 0x1234, crc_wire=0)
    assert m.read(1) == 0b0110 and m.read(4) == 2 and m.leds() == 0x1234


def test_wire_bits_lsb_first():
    assert Model.wire_bits(0x0001, 0x80)[:2] == [1, 0] and Model.wire_bits(0, 0x80)[-1] == 1
