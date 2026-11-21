"""Brief 127 board driver: build rm_gp_itch on the KR260 optical loopback, the PRE-REGISTERED stages of docs/board_test_plan.md. NOT YET RUN ON A BOARD.

One session, in this order (the lock text must start '97I:'; SRAM only; the laser is on for the stages and off on every path out):
  0. the build is the right one: ID 0x96A00001 and FEATURES bit 7 (the ITCH path) are read back; anything else stops the run;
  1. polarity and pins with the laser off, then on (the stage-3 sequence of every earlier build: stops if RX_LOS does not behave);
  2. the link comes up on the fibre loop; operating conditions (SYSMON: die temperature, VCCINT, VCCAUX, VCCBRAM) are read at the start, at the end and between plans at least once a minute;
  3. the stages smoke, counters, latency (speculation off, then on), rate, risk (host/b127_stages.py), each judged on its own pre-registered criteria;
  4. `verdict`: every stage's result with the operating conditions and a statement "inside ROC" or "outside ROC" for each failure.
Nothing is tuned: a failed stage is reported with its numbers. Synthetic data only, no exchange, no NIC: the loopback returns our own frames (host/itch_host.py says what that does and does not test)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b96c_ppm as pp
from designs.b96_kr260_10g.rm_gp_itch.host import b127_stages as S


class BoardRunner(S.Runner):
    """Runs plans on a Transport; samples the operating conditions between plans at least every `cond_every_s`."""

    def __init__(self, t: bb.Transport, cond_every_s: float = 60.0) -> None:
        self.t, self.cond_every_s = t, cond_every_s
        self.conditions: list[dict] = []
        self._last = 0.0
        super().__init__(execute=self._execute, sim=False, link_ready=True)

    def sample(self, tag: str) -> dict:
        c = pp.safe_conditions(self.t)
        c["tag"] = tag
        self.conditions.append(c)
        self._last = time.time()
        return c

    def _execute(self, plan) -> dict:
        if time.time() - self._last > self.cond_every_s:
            self.sample("interval")
        return plan.run(self.t)


def run_stages(runner: BoardRunner, stages, sizes: dict | None, latency_passes: int) -> dict:
    """The stages in order; `latency` runs twice (speculation off, then on) as the two entries latency_at_verdict and latency_speculative."""
    out: dict = {}
    for name in stages:
        kw = (sizes or {}).get(name, {})
        if name == "latency":
            for spec in (False, True):
                out["latency_speculative" if spec else "latency_at_verdict"] = S.stage_latency(runner, passes=latency_passes, spec=spec, **kw)
        else:
            out[name] = S.STAGES[name](runner, **kw)
    out["all_pass"] = all(v["pass"] for v in out.values())
    return out


def run_session(t: bb.Transport, lock_text: str, out_dir: Path, *, loop_m: float, stages=("smoke", "counters", "latency", "rate", "risk"), sizes: dict | None = None, latency_passes: int = 125) -> dict:
    if not lock_text.startswith("97I:"):
        raise RuntimeError("take _handoff/board.lock with a text starting '97I:' first, and pass that text")
    b = bb.Board(t)
    res: dict = {"lock": lock_text, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "loop_m": loop_m}
    res["id"] = f"{b.id():08x}"
    feat = t.rd(0x008)
    res["features"] = f"{feat:08x}"
    if b.id() != 0x96A00001 or not (feat >> 7) & 1:
        res["stopped"] = "the loaded design is not rm_gp_itch (ID or FEATURES bit 7 wrong); nothing was run"
        (out_dir / "stage1.json").write_text(json.dumps(res, indent=1))
        return res
    runner = BoardRunner(t)
    try:
        b.laser(False)
        s0 = b.status()
        b.laser(True); time.sleep(0.1); s1 = b.status(); b.laser(False); time.sleep(0.1); s2 = b.status()
        res["polarity"] = {"off": s0, "on": s1, "off_again": s2}
        if not (s0["rx_los"] == 1 and s1["rx_los"] == 0 and s2["rx_los"] == 1 and s0["mod_abs"] == 0):
            res["stopped"] = "laser polarity or pin functions differ from the open-source example: read the schematic, do not continue"
            (out_dir / "stage1.json").write_text(json.dumps(res, indent=1))
            return res
        res["module"] = b.module_info()
        b.laser(True)
        b.reset(all_=True)
        res["link_up"] = b.wait(lambda s: s["tx_done"] and s["rx_done"] and s["pcs_lock"], 5.0)
        res["ddm_start"] = b.ddm()
        res["conditions_start"] = runner.sample("start")
        if not res["link_up"]:
            res["stopped"] = "link did not come up on the loop"
        else:
            t.wr(0x018, 1)                                   # clear the base counters
            res["stages"] = run_stages(runner, stages, sizes, latency_passes)
            res["ddm_end"] = b.ddm()
        res["conditions_end"] = runner.sample("end")
        res["conditions"] = runner.conditions
        roc_ok = all(c.get("inside_roc") for c in runner.conditions)
        res["roc_ok"] = roc_ok
        if "stages" in res:
            for k, v in res["stages"].items():
                if isinstance(v, dict) and not v.get("pass"):
                    v["conditions_at_failure"] = "inside ROC" if roc_ok else "OUTSIDE ROC: the run's results are void until repeated inside ROC"
    finally:
        try:
            b.laser(False)
        except Exception as e:  # noqa: BLE001 - recorded
            res["laser_off_error"] = f"{type(e).__name__}: {e}"
        (out_dir / "stage1.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main() -> None:
    import argparse

    from flow import version_pin
    ap = argparse.ArgumentParser(description="Brief 127 loopback stages for build rm_gp_itch. The laser is left off at the end.")
    ap.add_argument("--serial", required=True, help="the cable serial of the KR260's JTAG (from ~/.config/fpga_design_agent/boards.yaml, never 'the first target')")
    ap.add_argument("--lock-text", required=True, help="the text you wrote into _handoff/board.lock (must start '97I:')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--loop-m", type=float, required=True, help="measured length of the fibre loopback lead in metres")
    ap.add_argument("--stages", default="smoke,counters,latency,rate,risk")
    ap.add_argument("--latency-passes", type=int, default=125, help="passes of 8 orders each, per speculation setting (125 = 1000 orders)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[4]
    t = bb.VivadoTcl(repo, a.serial, version_pin.vivado_path())
    try:
        res = run_session(t, a.lock_text, a.out, loop_m=a.loop_m, stages=tuple(a.stages.split(",")), latency_passes=a.latency_passes)
    finally:
        t.close()
    out = {k: res.get(k) for k in ("id", "features", "link_up", "stopped", "roc_ok")}
    out["stages"] = {k: v.get("pass") if isinstance(v, dict) else v for k, v in res.get("stages", {}).items()}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
