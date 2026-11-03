from model import Model, config_regs


def test_config_regs_from_shell_values():
    assert config_regs(250, 5) == {0x20: 0xFA, 0x21: 0, 0x22: 5, 0x27: 1, 0x2A: 0x10, 0x2D: 2}
    assert config_regs(0x2B7, 9)[0x21] == 2 and config_regs(0x2B7, 9)[0x20] == 0xB7
    assert config_regs(0x7FF, 0)[0x21] == 7


def test_events_and_sign_extension():
    m = Model()
    m.event(300)
    assert m.read(3) == 1 and m.read(4) == 0x10 and m.read(5) == 300 and m.leds() == 0x1200 | 2
    m.event(-50)
    assert m.read(5) == 0xFFCE and m.leds(True) == (0xFC << 8) | 3 and m.count == 2


def test_defaults_masks():
    m = Model()
    assert m.read(0) == 250 and m.read(1) == 5
    m.write(0, 0xFFFF)
    m.write(1, 0x1FF)
    assert m.read(0) == 0x7FF and m.read(1) == 0xFF
