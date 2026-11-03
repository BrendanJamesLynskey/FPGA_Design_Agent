from model import Model, gaps, signed16, step_starts


def test_trapezoid_for_a_long_move():
    g = gaps(40, 40, 12, 4)
    assert g[:8] == [40, 36, 32, 28, 24, 20, 16, 12] and g[-8:] == [12, 16, 20, 24, 28, 32, 36, 40]
    assert len(g) == 39 and set(g[7:-7]) == {12}


def test_short_move_is_symmetric_and_never_fast():
    g = gaps(7, 40, 12, 4)
    assert g == [40, 36, 32, 32, 36, 40]
    assert g == g[::-1] and max(g) == 40 and min(g) > 12
    assert gaps(1, 40, 12, 4) == [] and gaps(2, 40, 12, 4) == [40]


def test_starts_and_position_rules():
    s = step_starts(3, 6, 40, 12, 4)
    assert s == [6, 46, 86]
    m = Model()
    m.write(0, 0)
    m.write(0, 0xFFFB)                 # -5
    assert m.busy and m.dir == 0 and m.read(1) == (1 << 32) - 5 and m.read(2) == 1 | 1 << 16
    m.write(0, 3)
    assert m.read(2) == 1 | 1 << 8 | 1 << 16 and m.pos == -5
    m.finish()
    m.write(0, 10)
    assert m.pos == 5 and signed16(0x8000) == -32768
