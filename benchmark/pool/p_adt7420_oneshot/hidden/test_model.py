from model import Model, config_byte, signed16


def test_config_byte_and_signed():
    assert config_byte(False) == 0x20 and config_byte(True) == 0xA0
    assert signed16(0xF9C0) == -1600 and signed16(0x0D80) == 3456


def test_temperature_shift_both_resolutions():
    m = Model()
    m.start()
    m.complete(0x0D80 | 0b101)                 # 27.0 C in 13-bit mode with flag bits set: 432 sixteenths
    assert m.read(4) == 432 and m.read(3) == 0x0D85
    m.start()
    m.complete(0xF9C0)                         # -12.5 C in 16-bit mode: -200 sixteenths
    assert m.read(4) == (-200) & 0xFFFF and m.leds() == 0xFF38
    assert m.read(5) == 0xFF38 and m.read(6) == 432 and m.read(7) == 2


def test_busy_ignore_abandon_and_clear():
    m = Model()
    assert m.read(5) == 0x7FFF and m.read(6) == 0x8000
    assert m.start() and not m.start()
    assert m.read(2) == 1 | 1 << 8
    m.abandon()
    assert m.read(2) == 2 | 4 | 1 << 8 and m.errors == 1
    m.start()
    m.complete(0x0100)
    m.write(0, 2)
    assert m.read(7) == 0 and m.read(8) == 0 and m.read(5) == 0x7FFF
