"""Board bring-up tests (JTAG register bus); run only with the board attached."""
import pytest

pytestmark = pytest.mark.hw

import hw_checks  # noqa: E402


def _bus(board):
    return board


def test_design_id(board):
    assert board.rd(0x000) == hw_checks.DESIGN_ID


def test_scratch(board):
    board.wr(0x008, 0xA5A55A5A)
    assert board.rd(0x008) == 0xA5A55A5A
    board.wr(0x008, 0)


def test_hw_checks(board):
    res = hw_checks.run(board)
    bad = [r for r in res if not r[1]]
    assert not bad, bad
