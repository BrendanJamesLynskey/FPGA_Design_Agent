"""Board bring-up tests for p2_mem_test (run only with the board attached)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hw_checks  # noqa: E402

pytestmark = pytest.mark.hw


def _results(board):
    return hw_checks.run(board)


def test_id_register(board):
    assert board.rd(0) == hw_checks.DESIGN_ID


def test_bringup_checks(board):
    bad = [(n, d) for n, ok, d in _results(board) if not ok]
    assert not bad, bad
