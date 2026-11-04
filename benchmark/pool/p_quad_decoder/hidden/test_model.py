from model import Model


def test_forward_and_backward():
    m = Model()
    for ab in (0b01, 0b11, 0b10, 0b00):
        m.set_ab(ab)
    assert m.pos == 4 and m.fwd == 4 and m.dir == 1
    m.set_ab(0b10)
    assert m.pos == 3 and m.rev == 1 and m.dir == 2


def test_double_step_is_error_only():
    m = Model()
    m.set_ab(0b11)
    assert m.pos == 0 and m.errs == 1 and m.dir == 0
    m.set_ab(0b00)
    assert m.errs == 2


def test_wrap_and_index_and_clears():
    m = Model()
    m.write(0, 0)
    m.set_ab(0b10)
    assert m.pos == 0xFFFF and m.leds() == 0xFFFF
    m.index()
    assert m.pos == 0 and m.rev == 1
    m.write(2, 5)
    m.write(3, 5)
    assert m.rev == 0 and m.errs == 0
