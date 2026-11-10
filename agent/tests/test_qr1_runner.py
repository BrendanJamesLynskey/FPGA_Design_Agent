"""QR1: LocalRunner kills the whole process group on a timeout (a timed-out build left its Vivado running)."""
import os
import shutil
import time
from pathlib import Path

import pytest

from agent.core.runner import LocalRunner


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except FileNotFoundError:
        return False


def test_timeout_kills_grandchildren(tmp_path):
    pidfile = tmp_path / "pid"
    script = tmp_path / "run.sh"
    script.write_text(f"#!/bin/bash\nsleep 300 &\necho $! > {pidfile}\nwait\n")
    script.chmod(0o755)
    r = LocalRunner().run("t", [str(script)], tmp_path, timeout=2)
    assert r.returncode == 124 and "timed out" in r.stderr
    pid = int(pidfile.read_text())
    for _ in range(20):
        if not _alive(pid):
            break
        time.sleep(0.1)
    assert not _alive(pid), "the grandchild survived the timeout"


def test_normal_run_and_stdin_closed(tmp_path):
    r = LocalRunner().run("t", ["bash", "-c", "cat; echo out; echo err >&2; exit 3"], tmp_path)
    assert (r.returncode, r.stdout.strip(), r.stderr.strip()) == (3, "out", "err")      # cat saw EOF at once


@pytest.mark.skipif(not shutil.which("systemd-run"), reason="no systemd-run")
def test_timeout_kills_a_systemd_scope_child(tmp_path):
    r = LocalRunner().run("t", ["bash", "-c", "systemd-run --user --scope -q sleep 301"], tmp_path, timeout=3)
    time.sleep(0.5)
    assert r.returncode == 124
    left = os.popen("pgrep -f '^sleep 301$'").read().split()
    assert not left, f"scope child survived: {left}"
