"""board_check for a design with no test shell (NO_SHELL = True in its selfcheck.py): identify and still_alive ask
the shell nothing; the self-check gets the open serial port. A design with a shell is unchanged."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from flow import board_check


def _run(check: Any) -> board_check.Run:
    r = object.__new__(board_check.Run)
    r.check = check
    r.res = {"build_stamp": "0badf00d", "steps": {}}
    r.board = {"uart": "/dev/null"}
    return r


class FakeShell:
    opened = 0

    def __init__(self) -> None:
        self.port = SimpleNamespace(timeout=0.5)

    @classmethod
    def open(cls, device: str) -> "FakeShell":
        cls.opened += 1
        return cls()

    def __enter__(self) -> "FakeShell":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def identify(self) -> dict[str, int]:
        raise AssertionError("a no-shell design must not be asked to identify")


def test_no_shell_identify_and_still_alive_skip_the_shell(monkeypatch) -> None:
    monkeypatch.setattr(board_check, "FpgaShell", FakeShell)
    run = _run(SimpleNamespace(NO_SHELL=True))
    assert run.no_shell
    i = run.identify()
    assert i["pass"] and i["shell"] is False and i["build_stamp"] == "0badf00d"
    assert run.still_alive()["pass"]
    assert FakeShell.opened == 0


def test_no_shell_selfcheck_gets_the_serial_port(monkeypatch) -> None:
    monkeypatch.setattr(board_check, "FpgaShell", FakeShell)
    seen: list[Any] = []

    def check(sh: Any) -> dict[str, Any]:
        seen.append(sh.port)
        return {"pass": True}

    run = _run(SimpleNamespace(NO_SHELL=True, check=check, __doc__="x\n\nPass rule: y"))
    assert run.selfcheck()["pass"] and len(seen) == 1


def test_a_shell_design_still_identifies_through_the_shell(monkeypatch) -> None:
    monkeypatch.setattr(board_check, "FpgaShell", FakeShell)
    run = _run(SimpleNamespace(DESIGN_ID=1))
    assert not run.no_shell
    try:
        run.identify()
    except AssertionError as e:
        assert "must not be asked" in str(e)
    else:
        raise AssertionError("identify should have gone to the shell")
