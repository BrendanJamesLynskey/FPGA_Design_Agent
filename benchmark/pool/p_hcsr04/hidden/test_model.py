from model import Model, median


def test_median_rules():
    assert median([7]) == 7 and median([9, 4]) == 4 and median([9, 4, 6]) == 6 and median([1, 2, 3]) == 2


def test_floor_division_and_window():
    m = Model(58, 5800)
    assert m.ping(58 * 30 + 57) == "good" and m.raw == 30 and m.dist == 30
    m.ping(58 * 31 - 1)
    assert m.raw == 30
    m.ping(58 * 10)
    assert m.window == [30, 30, 10] and m.dist == 30
    m.ping(58 * 12)
    assert m.window == [30, 10, 12] and m.dist == 12 and m.read(3) == 58 * 12


def test_timeouts_and_oor_leave_window_alone():
    m = Model(58, 5800)
    m.ping(58 * 20)
    assert m.ping(None) == "timeout" and m.ping(5801) == "oor" and m.ping(5800) == "good"
    assert m.window == [20, 100] and m.dist == 20 and m.timeouts == 1 and m.oor == 1
    m.write(8, 0)
    assert m.read(2) == 0 and m.good == 0 and m.window == []
    m.dist = 400
    assert m.leds() == 255
