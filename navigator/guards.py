"""The guards a start (a run, a board action) passes before anything is spawned: the owner's usage stop, and the lock files.

Usage: ``_handoff/usage_check.sh`` (headless ``/usage``, 0 tokens) is run first and the line it appended to ``usage_log.txt`` must be fresh; a reading
that cannot be made, or is stale, refuses the start (fail closed). The stop is the owner's current weekly stop, 90 % until the 23 Nov reset
(``FDA_USAGE_STOP_PCT`` overrides it for a later schedule): a reading at or above it refuses.

Locks: ``OwnedLock`` takes a lock file the house way (exclusive create, which is what ``set -o noclobber`` does) and releases it only if the file still
holds exactly the text this process wrote, so it can never remove another session's lock. ``HeavySlot`` takes a heavy-job slot through the owner's
``take_heavy_slot.sh`` (which holds the admission rules) and releases it the same owner-checked way. Neither ever uses a bare ``rm``.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import secrets
from pathlib import Path
from typing import Any, Callable

USAGE_STOP_PCT = int(os.environ.get("FDA_USAGE_STOP_PCT", "90") or 90)
USAGE_FRESH_MIN = 15                      # a reading older than this, taken right after running the check, is not a reading
PREFIX = "103S2:"                         # the session prefix of every lock text this module writes


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def end_text(hours: float) -> str:
    return (dt.datetime.now() + dt.timedelta(hours=hours)).strftime("%H:%M")


def lock_text(job: str, hours: float) -> str:
    """``103S2: <job>, <start>, expected end <hh:mm>``: the format every lock text of this PC has."""
    job = re.sub(r"[^A-Za-z0-9 _.,/()+=-]", "", job)[:120]
    return f"{PREFIX} {job} #{secrets.token_hex(3)}, {now_text()}, expected end {end_text(hours)}"      # the nonce makes two takes in one minute differ, so one can never release the other's lock


# --- usage ----------------------------------------------------------------------------------------------------------------------

def parse_usage_line(line: str) -> dict[str, Any] | None:
    m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d)\s+", line)
    w = re.search(r"Current week \(all models\):\s*(\d+)% used", line)
    if not (m and w):
        return None
    reset = re.search(r"resets ([^;]+)", line)
    return {"when": m.group(1), "percent": int(w.group(1)), "resets": reset.group(1).strip() if reset else None}


def usage_reading(handoff: Path) -> dict[str, Any] | None:
    try:
        lines = [ln for ln in (Path(handoff) / "usage_log.txt").read_text().splitlines() if ln.strip()]
    except OSError:
        return None
    r = parse_usage_line(lines[-1]) if lines else None
    if r is not None:
        r["age_min"] = (dt.datetime.now() - dt.datetime.strptime(r["when"], "%Y-%m-%d %H:%M")).total_seconds() / 60
    return r


def usage_guard(handoff: Path, runner: Any, stop_pct: int | None = None) -> tuple[bool, str, dict[str, Any] | None]:
    """Run the usage check, read the result. Returns (allowed, reason, reading). Refuses on a failed check, a stale or unreadable line, or a percentage at the stop."""
    stop = USAGE_STOP_PCT if stop_pct is None else stop_pct
    rc, out, err = runner.run(["bash", str(Path(handoff) / "usage_check.sh")], timeout=90)
    if rc != 0:
        return False, f"usage check failed (exit {rc}), so the weekly usage is unknown: refused", None
    r = usage_reading(handoff)
    if r is None:
        return False, "usage_log.txt has no readable line after the check: refused", None
    if r["age_min"] > USAGE_FRESH_MIN:
        return False, f"the usage reading is {r['age_min']:.0f} min old after running the check: refused", r
    if r["percent"] >= stop:
        return False, f"weekly usage is {r['percent']}%, at or above the owner's stop of {stop}% (resets {r['resets'] or 'unknown'}): refused", r
    return True, f"weekly usage {r['percent']}% is below the stop of {stop}%", r


# --- locks ----------------------------------------------------------------------------------------------------------------------

class LockBusy(RuntimeError):
    """The lock is held; the message carries its text."""


class OwnedLock:
    """One lock file, taken by exclusive create and released only if it still holds the exact text written."""

    def __init__(self, path: Path, text: str):
        if not text.startswith(PREFIX):
            raise ValueError(f"lock text must start with {PREFIX!r}")
        self.path, self.text, self.held = Path(path), text, False

    def take(self) -> None:
        try:
            with open(self.path, "x") as f:
                try:
                    f.write(self.text + "\n")
                except BaseException:                       # an empty lock file nobody can release must not be left behind
                    f.close()
                    self.path.unlink()
                    raise
        except FileExistsError:
            try:
                other = self.path.read_text().strip()[:200]
            except OSError:
                other = "(unreadable)"
            raise LockBusy(f"{self.path.name} is held: {other}") from None
        self.held = True

    def release(self) -> bool:
        """True if the file was removed. A lock another session holds (any other text) is left alone."""
        if not self.held:                                   # a take that was refused never owns the file, whatever its text says
            return False
        self.held = False
        return release_if_ours(self.path, self.text)


def release_if_ours(path: Path, text: str) -> bool:
    try:
        cur = Path(path).read_text().strip()
    except (OSError, ValueError):
        return False
    if cur != text.strip() or not cur.startswith(PREFIX):
        return False
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return False
    return True


class HeavySlot:
    """A heavy-job slot through ``take_heavy_slot.sh``. ``take`` returns the lock file path it printed (checked to be one of the two slot files)."""

    def __init__(self, handoff: Path, runner: Any, text: str):
        if not text.startswith(PREFIX):
            raise ValueError(f"lock text must start with {PREFIX!r}")
        self.handoff, self.runner, self.text = Path(handoff), runner, text
        self.lock: Path | None = None

    def _release_anywhere(self) -> None:
        for n in ("heavy_slot.lock", "heavy_slot2.lock"):
            release_if_ours(self.handoff / n, self.text)

    def take(self) -> Path:
        rc, out, err = self.runner.run(["bash", str(self.handoff / "take_heavy_slot.sh"), self.text], timeout=30)
        if rc == 1:
            raise LockBusy("no heavy slot is free (take_heavy_slot.sh refused: two jobs running, or less than 12 GB free for the second slot)")
        printed = out.strip().splitlines()[-1].strip() if out.strip() else ""
        cand = Path(printed)
        # the real script prints its own fixed directory; only the file name is checked here, and release re-reads the file and removes it only if it holds our exact text
        if rc != 0 or cand.name not in ("heavy_slot.lock", "heavy_slot2.lock"):
            self._release_anywhere()                         # the script may have written the lock before failing or timing out: free it if it is ours
            raise LockBusy(f"take_heavy_slot.sh did not give a usable answer (exit {rc}); any slot it took for this text was released")
        self.lock = cand
        return cand

    def release(self) -> bool:
        if self.lock is None:
            return False
        lock, self.lock = self.lock, None
        return release_if_ours(lock, self.text)


def release_all(*locks: Any) -> list[bool]:
    """Release in reverse order of the arguments; one failure never skips the rest."""
    out = []
    for lk in reversed(locks):
        try:
            out.append(bool(lk.release()))
        except Exception:                                  # a release problem must not hide the first error or skip another release
            out.append(False)
    return out
