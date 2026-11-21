"""Brief 82P7: the Vivado job count (flow/hw.py via flow/vivado_count.py, flow/run_vivado.sh) counts only processes whose argv[0] is the
Vivado binary, not a shell that names its path in its command line (82P6: a 40-hour waiting shell was counted, and the synthesis
gate logged "limit FDA_VIVADO_MAX=1 reached" for most of two runs). Tested with real fake processes: a ``sleep`` started with argv[0] set to
``.../unwrapped/lnx64.o/vivado`` (a job) and a ``bash`` whose command line names that path (a waiting shell)."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest

from flow import hw, vivado_count

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fake_procs(tmp_path):
    exe_dir = tmp_path / "Vivado" / "bin" / "unwrapped" / "lnx64.o"
    exe_dir.mkdir(parents=True)
    exe = exe_dir / "vivado"
    # a waiting shell: its command line names the path (as `while pgrep -af unwrapped/lnx64.o/vivado ...; do sleep 60; done` did)
    shell = subprocess.Popen(["bash", "-c", f"sleep 30; true  # waiting for {exe}"])
    job = None
    procs = [shell]

    def start_job():
        nonlocal job
        job = subprocess.Popen(["bash", "-c", f"exec -a {exe} sleep 30"])      # argv[0] is the Vivado path, as for the real binary
        procs.append(job)
        time.sleep(0.3)
        return job
    time.sleep(0.3)
    yield shell, start_job
    for p in procs:
        p.terminate()
        p.wait(timeout=10)


def test_a_waiting_shell_is_not_counted_but_a_real_job_is(fake_procs):
    shell, start_job = fake_procs
    ps = subprocess.run(["ps", "-ww", "-eo", "pid=,args="], capture_output=True, text=True).stdout
    assert str(shell.pid) not in vivado_count.running_pids(ps)             # the shell names the path: not a job
    assert f"unwrapped/lnx64.o/vivado" in ps                                # and the decoy is really in the process table
    job = start_job()
    ps = subprocess.run(["ps", "-ww", "-eo", "pid=,args="], capture_output=True, text=True).stdout
    pids = vivado_count.running_pids(ps)
    assert str(job.pid) in pids and str(shell.pid) not in pids


@pytest.mark.parametrize("script", ["run_vivado.sh", "checks/run_vivado_checks.sh"])
def test_the_shell_scripts_count_the_same_way(fake_procs, script):
    """The awk line of flow/run_vivado.sh and flow/checks/run_vivado_checks.sh, run over the real process table, agrees with the Python count."""
    shell, start_job = fake_procs
    src = (ROOT / "flow" / script).read_text()
    m = re.search(r"""n="\$\(ps -ww -eo pid=,args= \| (awk '[^\n]*?') \| wc -l""", src)
    assert m, "the counting line of run_vivado.sh changed: update this test"
    assert "$2 ~" in m.group(1)                                             # argv[0] only, not the whole command line

    def count():
        return int(subprocess.run(f"ps -ww -eo pid=,args= | {m.group(1)} | wc -l", shell=True, capture_output=True, text=True).stdout)

    def count_py():
        return len(vivado_count.running_now())
    before = count()
    assert before == count_py()                                             # the decoy shell adds nothing to either
    start_job()
    assert count() == before + 1 == count_py()


def test_hw_preflight_ignores_the_waiting_shell(fake_procs, monkeypatch):
    shell, start_job = fake_procs
    monkeypatch.setenv("FDA_VIVADO_MAX", "1")
    others = len(vivado_count.running_now())                                # real jobs of other sessions on this PC, if any
    if others:
        pytest.skip("a real Vivado is running on this PC")
    assert hw.preflight(min_avail_gb=0) >= 0                                # only the decoy shell is there: no refusal
    start_job()
    with pytest.raises(hw.HwError, match="another Vivado is running"):
        hw.preflight(min_avail_gb=0)


def test_task_worker_helpers_are_not_jobs():
    ps = ("101 /o/Vivado/bin/unwrapped/lnx64.o/vivado -mode batch -source build.tcl\n"
          "102 /o/Vivado/bin/unwrapped/lnx64.o/vivado -mode tcl -source task_worker.tcl\n"
          "103 bash -c while pgrep -af /o/Vivado/bin/unwrapped/lnx64.o/vivado; do sleep 60; done\n"
          "104 /usr/bin/time -v /o/Vivado/bin/unwrapped/lnx64.o/vivado -mode batch\n")
    assert vivado_count.running_pids(ps) == ["101"]
