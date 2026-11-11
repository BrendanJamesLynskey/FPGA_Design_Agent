"""The board lock (house rules): one board job at a time, through _handoff/board.lock, taken like the heavy slot.

    with BoardLock("FPGA b30: audio HIL run, 12:00, expected end 12:30"): ...

take() writes the text with noclobber (it never overwrites another session's lock); release() removes the lock only if
its text still starts with this session's prefix (the part before the first colon, plus the colon). Never a bare rm.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT = Path(os.environ.get("BOARD_LOCK", "/home/brendan/Claude_sandbox/_handoff/board.lock"))


class BoardBusy(RuntimeError):
    """Another session holds the board; the message carries its lock text."""


def prefix_of(text: str) -> str:
    head, sep, _ = text.partition(":")
    if not sep or not head.strip():
        raise ValueError("lock text must start with '<session prefix>: ...'")
    return head.strip() + ":"


class BoardLock:
    def __init__(self, text: str, path: Path | str = DEFAULT) -> None:
        self.text, self.path, self.prefix = text, Path(path), prefix_of(text)
        self.held = False

    def take(self) -> None:
        try:
            with open(self.path, "x") as f:           # exclusive create: fails if the file exists (noclobber)
                f.write(self.text + "\n")
        except FileExistsError:
            raise BoardBusy(f"board is locked: {self.path.read_text().strip()}") from None
        self.held = True

    def release(self) -> bool:
        """Remove the lock only if it is ours. Returns True if it was removed."""
        try:
            cur = self.path.read_text()
        except FileNotFoundError:
            self.held = False
            return False
        if cur.startswith(self.prefix):
            self.path.unlink()
            self.held = False
            return True
        return False

    def __enter__(self) -> "BoardLock":
        self.take()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
