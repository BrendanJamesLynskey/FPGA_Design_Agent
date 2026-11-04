from model import Model


def rl(seq):
    out = []
    for v in seq:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def test_all_request_rotates_with_one_clock_gaps():
    m = Model(12)
    out = m.run([0xF] * 200)
    runs = rl(out)[1:-1]
    g = [v for v, _ in runs if v]
    assert g == ([1, 2, 4, 8] * 10)[: len(g)] and len(g) >= 8
    assert all(n == 12 for v, n in runs if v) and all(n == 1 for v, n in runs if not v)
    assert m.forced >= 4 and m.read(5) in range(4)


def test_single_requester_is_not_revoked_until_someone_waits():
    m = Model(12)
    out = m.run([0b0100] * 60 + [0b0101] * 8)
    assert out[10] == 4 and out[55] == 4 and 1 in out[-4:]
    assert m.forced == 1


def test_rotation_after_release():
    m = Model(50)
    m.run([0b0010] * 20)
    out = m.run([0b1101] * 20)
    assert m.last == 2 and 4 in out and m.grants[1] == 1 and m.grants[2] == 1


def test_clear():
    m = Model(12)
    m.run([0xF] * 100)
    m.write(0, 1)
    assert [m.read(i) for i in range(5)] == [0, 0, 0, 0, 0] and m.read(5) in range(4)
