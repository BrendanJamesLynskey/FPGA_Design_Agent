"""Pick a board file from what a request says (brief 95).

``--board`` takes a board id (``nexys_a7_100t``) or the words of a request ("the Arty A7-100T", "a PYNQ-Z2"). A request that
names two boards, or a family that has several ("Arty A7"), is refused with the candidates; a board the agent cannot yet
write constraints for is refused with the reason. The catalogue and the trust labels are in ``boards/catalogue.yaml`` and
``docs/board_catalogue.md``.
"""

from __future__ import annotations

import argparse

from flow import board_catalogue as cat


def board_name(value: str) -> str:
    """argparse ``type=`` for commands that only read a finished design (``document``, ``resume``): the board id for an id or a
    free-text request, whether or not the agent can write that board's constraints."""
    if (cat.BOARDS / value).is_dir() and value not in cat.load():
        return value                    # a board directory the catalogue does not list: as before, a plain name
    return board_arg(value, require_targetable=False)


def board_arg(value: str, require_targetable: bool = True) -> str:
    """argparse ``type=`` for ``run``: the board id for an id or a free-text request; refuses a board the agent cannot target."""
    boards = cat.load()
    if value in boards:
        board = value
    else:
        board, cands = cat.resolve(value)
        if board is None:
            if cands:
                raise argparse.ArgumentTypeError(f"{value!r} names more than one board ({', '.join(cands)}); say which")
            raise argparse.ArgumentTypeError(f"no board named in {value!r}; the catalogue has: {', '.join(boards)}")
    e = boards[board]
    if require_targetable and not e.get("targetable"):
        raise argparse.ArgumentTypeError(
            f"{board} ({e['display']}) is in the catalogue but the agent cannot target it yet: {e.get('smoke_note') or 'no usable pin list'}. "
            f"See boards/{board}/board.yaml (facts and known gaps)")
    return board
