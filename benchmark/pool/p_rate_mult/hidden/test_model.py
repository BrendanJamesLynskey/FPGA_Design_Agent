from model import Model


def ticks(m, k):
    return [m.step() for _ in range(k)]


def test_n_in_m_and_pattern_repeats():
    m = Model()
    m.write(0, 3)
    m.write(1, 8)
    p = m.pattern()
    assert sum(p) == 3 and len(p) == 8 and p == [0, 0, 1, 0, 0, 1, 0, 1]
    assert ticks(m, 24) == p * 3


def test_clamps():
    m = Model()
    m.write(0, 9)
    m.write(1, 4)
    assert m.pattern() == [1, 1, 1, 1]
    m.write(1, 0)
    assert m.pattern() == [1]
    m.write(0, 0)
    assert m.pattern() == [0]


def test_disabled_holds_and_clear():
    m = Model()
    m.write(0, 1)
    m.write(1, 3)
    ticks(m, 2)
    assert [m.step(False) for _ in range(5)] == [0] * 5
    assert m.step() == 1 and m.read(2) == 1
    m.write(3, 0)
    assert m.read(2) == 0 and m.acc == 0
