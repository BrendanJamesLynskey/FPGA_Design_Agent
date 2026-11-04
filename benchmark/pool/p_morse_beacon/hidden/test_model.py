from model import Model, key_units


def test_sos_timing():
    u = key_units("SOS")
    assert u[:5] == [(1, 1), (0, 1), (1, 1), (0, 1), (1, 1)] and u[5] == (0, 3) and u[6] == (1, 3)
    assert u[-1][0] == 1 and sum(n for _, n in u) == (1 + 1 + 1 + 1 + 1) + 3 + (3 + 1 + 3 + 1 + 3) + 3 + (1 + 1 + 1 + 1 + 1)


def test_word_gap_and_edge_spaces():
    u = key_units("E E")
    assert u == [(1, 1), (0, 7), (1, 1)]
    assert key_units(" E ") == [(1, 1)]
    assert key_units("E  T") == [(1, 1), (0, 7), (1, 3)]


def test_buffer_rules():
    m = Model()
    for ch in "sos 73 de k9":
        m.write(0, ord(ch))
    m.write(0, ord("!"))
    assert m.text == "SOS 73 DE K9" and m.dropped == 0 and m.read(0) == 12
    for ch in "ABCDEFG":
        m.write(0, ord(ch))
    assert len(m.text) == 16 and m.dropped == 3
    m.write(1, 1)
    assert m.busy
    m.write(0, ord("A"))
    m.write(1, 2)
    assert m.dropped == 4 and len(m.text) == 16
    m.finish()
    m.write(1, 2)
    assert m.read(2) == 4 << 16
