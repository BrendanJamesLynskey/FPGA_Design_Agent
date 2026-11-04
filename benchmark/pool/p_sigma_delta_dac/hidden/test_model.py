from model import Model


def test_density_exact_in_every_window():
    for v in (0, 1, 7, 64, 128, 200, 255):
        m = Model()
        m.write(0, v)
        p = m.pattern()
        assert sum(p) == v
        assert all(sum((p + p)[i:i + 256]) == v for i in range(0, 256, 17))


def test_even_spreading_and_inversion():
    m = Model()
    m.write(0, 128)
    assert m.pattern()[:6] == [0, 1, 0, 1, 0, 1]
    m.write(0, 64)
    p = m.pattern()
    assert [i for i, x in enumerate(p) if x][:3] == [3, 7, 11]
    m.write(0, 200)
    assert sum(m.pattern(inv=1)) == 56


def test_write_keeps_phase_and_masks():
    m = Model()
    m.write(0, 0x1FF)
    assert m.read(0) == 0xFF and m.leds() == 0x80FF
    m.write(0, 100)
    m.stream(10)
    acc = m.acc
    m.write(0, 33)
    assert m.acc == acc
