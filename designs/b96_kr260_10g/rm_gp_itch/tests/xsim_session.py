"""Run a host plan on the whole core in xsim (brief 127): builds the script, runs sim/xsim_core.sh, parses the monitors. Shared by the pytest entry and the record-making scripts."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
ROOT = DESIGN.parents[2]
XSIM = Path("/opt/Xilinx/2026.1/Vivado/bin/xsim")
T_CLK = 6.2058


def have_xsim() -> bool:
    return XSIM.exists()


def run_plan(plan, work: Path, phase_ps: int = 0, rm_own: int = 1, timeout_s: int = 3600) -> str:
    work.mkdir(parents=True, exist_ok=True)
    script = work / "plan.txt"
    script.write_text(plan.script())
    r = subprocess.run(["systemd-run", "--user", "--scope", "-p", "MemoryMax=3G", "nice", "-n", "10", "bash", str(DESIGN / "sim" / "xsim_core.sh"), str(script), str(work / "x"), str(phase_ps), str(rm_own)],
                       capture_output=True, text=True, timeout=timeout_s)
    log = (work / "x" / "xsim.log")
    if not log.exists():
        raise RuntimeError(f"xsim did not run: {r.stdout[-800:]} {r.stderr[-800:]}")
    return log.read_text()


def monitors(log: str) -> dict:
    """XW per frame: {frame n: {idx: t}}, MW {idx: [t...]}, GO [t], OSOP [t], TXW [(d, c)]."""
    xw: dict[int, dict[int, float]] = {}
    mw: list[tuple[int, float]] = []
    go, osop, txw = [], [], []
    for l in log.splitlines():
        t = l.split()
        if not t:
            continue
        if t[0] == "XW":
            xw.setdefault(int(t[1]), {})[int(t[2])] = float(t[3])
        elif t[0] == "MW":
            mw.append((int(t[1]), float(t[2])))
        elif t[0] == "GO":
            go.append(float(t[1]))
        elif t[0] == "OSOP":
            osop.append(float(t[1]))
        elif t[0] == "TXW":
            txw.append((int(t[1], 16), int(t[2], 16)))
    return {"xw": xw, "mw": mw, "go": go, "osop": osop, "txw": txw}


class LazyResult(dict):
    """The result of the LAST plan executed so far; the simulation runs when it is first looked at (every plan of the stage then runs in ONE simulation, in order)."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def _load(self):
        if not self.owner.done:
            self.owner.run()
        super().update(self.owner.results)

    def __getitem__(self, k):
        if not self.owner.done:
            self._load()
        return super().__getitem__(k)

    def get(self, k, d=None):
        if not self.owner.done:
            self._load()
        return super().get(k, d)

    def __contains__(self, k):
        if not self.owner.done:
            self._load()
        return super().__contains__(k)

    def items(self):
        if not self.owner.done:
            self._load()
        return super().items()


class SimOwner:
    def __init__(self, work: Path, phase_ps: int = 0):
        self.work, self.phase = work, phase_ps
        self.plans = []
        self.done = False
        self.results = {}
        self.log = ""

    def execute(self, plan):
        from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
        assert not self.done, "this simulation already ran; make a new runner for the next stage"
        self.plans.append(plan)
        return LazyResult(self)

    def run(self):
        from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
        merged = B.Plan()
        seen_link = False
        for p in self.plans:
            for op in p.ops:
                if op[0] == "L":
                    if seen_link:
                        continue
                    seen_link = True
                merged.ops.append(op)
            merged.reads += p.reads
        self.log = run_plan(merged, self.work, self.phase)
        assert "DONE" in self.log, self.log[-600:]
        rd = [(int(l.split()[1], 16), int(l.split()[2], 16)) for l in self.log.splitlines() if l.startswith("RD ")]
        assert len(rd) == len(merged.reads), (len(rd), len(merged.reads))
        self.results = {tag: v for tag, (a, v) in zip(merged.reads, rd)}
        self.done = True
        return self.results


def sim_runner(work: Path, phase_ps: int = 0):
    from designs.b96_kr260_10g.rm_gp_itch.host import b127_stages as S
    o = SimOwner(work, phase_ps)
    return S.Runner(execute=o.execute, sim=True), o
