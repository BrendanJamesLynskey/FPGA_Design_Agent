from model import Model


def feed(m, *xs):
    for x in xs:
        m.write(0, x)


def test_filling_averages_over_present_samples():
    m = Model()
    feed(m, 10)
    assert m.avg == 10 and m.read(3) == 1
    feed(m, 21)
    assert m.avg == 15 and m.read(2) == 31


def test_full_window_and_drop_oldest():
    m = Model()
    feed(m, 100, 100, 100, 100, 100, 100)
    assert m.avg == 100 and m.read(3) == 6
    feed(m, 200)
    assert m.win == [100] * 5 + [200] and m.avg == 116


def test_clipping_to_limit_and_floor():
    m = Model()
    feed(m, 1000, 1000, 1000, 1000, 1000, 1000)
    feed(m, 4000)                       # clipped to 1500
    assert m.win[-1] == 1500
    m.write(4, 100)
    feed(m, 0)                          # avg is 1083, clipped to 983
    assert m.win[-1] == 983
    m.write(4, 4095)
    m.win = [10] * 6
    feed(m, 0)
    assert m.win[-1] == 0 and m.read(1) == 8
    m.write(5, 1)
    assert m.read(3) == 0 and m.read(1) == 0 and m.read(4) == 4095 and m.read(0) == 0
