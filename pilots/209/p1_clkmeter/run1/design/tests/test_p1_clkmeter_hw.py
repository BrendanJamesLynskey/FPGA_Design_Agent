import pytest

pytestmark = pytest.mark.hw

DESIGN_ID = 0x20910001


def test_id_register(board):
    assert board.rd(0x00) == DESIGN_ID


def test_scratch_readback(board):
    board.wr(0x08, 0xA5A5A5A5)
    assert board.rd(0x08) == 0xA5A5A5A5
    board.wr(0x08, 0)


def test_short_measurement(board):
    board.wr(0x10, 156250)
    board.wr(0x14, 1)
    for _ in range(1000):
        if board.rd(0x18) & 2:
            break
    assert board.rd(0x20) == 156250
    assert abs(board.rd(0x1C) - 25000) <= 3
    board.wr(0x10, 156250000)
