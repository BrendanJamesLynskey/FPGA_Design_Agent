from model import Model


def test_lone_trigger():
    m = Model(50)
    m.trigger(100)
    assert m.run_lengths() == [50] and m.read(0) == 1 and m.read(1) == 0 and m.read(2) == 50


def test_retrigger_extends_from_latest():
    m = Model(50)
    m.trigger(100)
    m.trigger(120)
    assert m.run_lengths() == [70] and m.read(1) == 1 and m.read(2) == 70
    m.trigger(300)
    assert m.run_lengths() == [70, 50] and m.read(0) == 3 and m.read(2) == 70


def test_clear_and_hold():
    m = Model(50)
    m.trigger(0)
    m.write(0, 7)
    assert [m.read(i) for i in range(4)] == [0, 0, 0, 50] and m.run_lengths() == []
    m.write(3, 1)
    assert m.read(3) == 50 and m.read(9) == 0
