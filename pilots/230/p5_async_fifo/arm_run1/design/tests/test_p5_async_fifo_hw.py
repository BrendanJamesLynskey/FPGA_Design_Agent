import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.hw


def _bus(board):
    return board


def test_design_id(board):
    assert board.rd(0x000) == 0x20950001


def test_scratch(board):
    board.wr(0x008, 0xA5A55A5A)
    assert board.rd(0x008) == 0xA5A55A5A
    board.wr(0x008, 0)


def test_soak_and_inject(board):
    import hw_checks
    res = hw_checks.run(board)
    bad = [r for r in res if not r[1]]
    assert not bad, bad
