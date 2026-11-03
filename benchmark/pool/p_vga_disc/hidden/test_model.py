from model import Geometry, Model

G = Geometry(64, 3, 6, 5, 48, 2, 2, 3, 4, 2)


def test_totals_and_offsets():
    assert G.h_total == 78 and G.v_total == 55 and G.frame_clocks == 78 * 55 * 4
    assert G.clock_of(0, 0) == ((2 + 3) * 78 + 6 + 5) * 4


def test_picture():
    c = 0xA5C
    assert G.pixel(0, 20, c) == 0xFFF and G.pixel(63, 20, c) == 0xFFF and G.pixel(30, 1, c) == 0xFFF and G.pixel(30, 46, c) == 0xFFF
    assert G.pixel(32, 24, c) == c and G.pixel(32 + 12, 24, c) == c and G.pixel(32 + 13, 24, c) == 0
    assert G.pixel(10, 24, c) == 0 and G.pixel(2, 24, c) == 0 and G.pixel(1, 24, c) == 0xFFF


def test_disc_area_close_to_pi_r_squared():
    n = sum(1 for y in range(48) for x in range(64) if G.pixel(x, y, 0x123) == 0x123)
    assert 3.14159 * 144 * 0.95 < n < 3.14159 * 144 * 1.1
    assert Model().read(1) == 0
