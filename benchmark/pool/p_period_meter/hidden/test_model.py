from model import Model


def test_periods_min_max_count():
    m = Model(1000)
    m.edge(None)
    for d in (50, 20, 80):
        m.edge(d)
    assert [m.read(i) for i in range(5)] == [80, 20, 80, 3, 0]


def test_stall_restarts_measurement():
    m = Model(1000)
    m.edge(None)
    m.edge(100)
    m.timed_out()
    assert m.read(4) == 1
    m.edge(5000)                      # the first edge after the stall: nothing recorded
    assert m.read(4) == 0 and m.read(3) == 1 and m.read(0) == 100
    m.edge(60)
    assert m.read(3) == 2 and m.read(0) == 60


def test_clear_and_led_saturation():
    m = Model(10 ** 6)
    m.edge(None)
    m.edge(70000)
    assert m.leds() == 0xFFFF and m.read(0) == 70000
    m.write(5, 0)
    assert [m.read(i) for i in range(4)] == [0, 0xFFFFFFFF, 0, 0]
    m.edge(30)
    assert m.read(3) == 0                  # restarted by the clear
