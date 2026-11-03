from model import Model


def run_len(out, bit):
    return sum(1 for v in out if (v >> bit) & 1)


def test_normal_transfer():
    m = Model(6, 20)
    out = m.run([1] * 15 + [0] * 10)
    assert m.transfers == 1 and m.aborts == 0 and m.faults == 0
    assert run_len(out, 2) == 6 and run_len(out, 0) > 3


def test_abort():
    m = Model(6, 20)
    m.run([1] * 4 + [0] * 10)
    assert m.aborts == 1 and m.transfers == 0


def test_fault_until_req_falls():
    m = Model(6, 20)
    out = m.run([1] * 100)
    assert m.faults == 1 and run_len(out, 0) == 20 and run_len(out, 1) > 50
    m.run([0] * 5)
    assert m.state == 0


def test_one_clock_pulse_and_clear():
    m = Model(6, 20)
    m.run([1, 0, 0, 0, 0, 0, 0, 0])
    assert m.aborts == 1
    m.write(0, 1)
    assert [m.read(i) for i in range(5)] == [0, 0, 0, 6, 20]
