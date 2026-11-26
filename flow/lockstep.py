"""Brief 213: the harness's lock-step bench. One cocotb test that drives the RTL and the reference model with the same inputs, cycle by cycle, and
writes where and how they first differ.

It is not the Verifier's bench and shares nothing with it except the build (top level, sources, parameters), which ``flow/cocotb_run.run`` hands
over when ``$FDA_LOCKSTEP`` is set (see ``flow/divergence.py`` for the callers). Two modes (``$FDA_LOCKSTEP_MODE``):

* ``replay``: the stimulus the design's own bench applied, as ``flow/model_record.py`` recorded it (the model's ``step`` inputs, segment by
  segment). The first divergence of the failing run, per cycle, with the inputs in flight.
* ``fresh``: new sequences from ``$FDA_LOCKSTEP_SEED``: values drawn mostly from the pool the recorded bench used for each input (so addresses and
  opcodes are ones the spec defines), with random and neighbour values, bursts and holds, ready-like inputs toggled for back-pressure, and
  resets mid-stream (the model is reset at the same cycle).

Model API contract (the Modeller's and the Verifier's): ``Model(**params)``, ``reset()``, ``step(inputs)`` -> outputs sampled after the clock edge
for ONE cycle. Per cycle the bench drives the inputs on the falling edge, waits for the rising edge, reads the outputs when the simulator has
settled (ReadOnly), and compares every model output that exists on the DUT with its value masked to the DUT signal's width. A DUT bit that is X or
Z counts as different. Result: JSON at ``$FDA_LOCKSTEP_OUT`` (schema ``fda/lockstep/v1``).

Limits (the digest says so): inputs the model has but the DUT top does not are skipped and listed (``unmapped``); a model output that is not on
the DUT is not compared; a DUT without a reset port is replayed from power-up for the first segment only.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

SCHEMA = "fda/lockstep/v1"
CONTEXT = 6                       # cycles of inputs and outputs kept before the first divergence
RESET_CYCLES = 3
READY_LIKE = ("ready", "ack", "grant", "stall", "busy_n", "cts", "tready", "rready", "bready", "wready", "awready", "arready", "full_n")


def _load_spec(design: Path) -> dict[str, Any]:
    try:
        import yaml
        return yaml.safe_load((design / "spec.yaml").read_text()) or {}
    except Exception:
        return {}


def read_record(path: Path) -> list[list[dict[str, Any]]]:
    """The recording as segments: each starts at a ``new`` line; ``step`` and ``reset`` follow. A recording that starts without ``new`` gets one."""
    segs: list[list[dict[str, Any]]] = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return segs
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("op") == "new" or not segs:
            segs.append([r] if r.get("op") == "new" else [{"op": "new", "params": {}, "test": None}, r])
        elif r.get("op") == "reset" and not any(x.get("op") == "step" for x in segs[-1]):
            continue                                            # the constructor's own reset(): the replay resets at the start of every segment
        elif r.get("op") in ("step", "reset"):
            segs[-1].append(r)
    return segs


def harvest_pool(segs: list[list[dict[str, Any]]], cap: int = 64) -> dict[str, list[int]]:
    """Per input name, the distinct values the recorded bench applied (most frequent first, at most ``cap``)."""
    count: dict[str, dict[int, int]] = {}
    for seg in segs:
        for r in seg:
            if r.get("op") == "step":
                for k, v in (r.get("in") or {}).items():
                    if isinstance(v, int):
                        count.setdefault(k, {}).setdefault(v, 0)
                        count[k][v] += 1
    return {k: [v for v, _ in sorted(c.items(), key=lambda kv: -kv[1])[:cap]] for k, c in count.items()}


class Stim:
    """A seeded stimulus generator for ``fresh`` mode over the model's input names, bound to the DUT's widths."""

    def __init__(self, seed: int, widths: dict[str, int], pool: dict[str, list[int]], cycles: int) -> None:
        self.rng = random.Random(seed)
        self.w, self.pool, self.cycles = widths, pool, cycles
        self.last = {k: 0 for k in widths}
        self.hold = {k: 0 for k in widths}
        self.p_active = 0.25
        self.next_phase = 0

    def _draw(self, k: str) -> int:
        r, w = self.rng, self.w[k]
        mask = (1 << w) - 1
        pool = self.pool.get(k) or []
        x = r.random()
        if pool and x < 0.55:
            return r.choice(pool) & mask
        if x < 0.70:
            return (self.last[k] + r.choice((-1, 1))) & mask
        if x < 0.80:
            return r.choice((0, mask, 1 << (w - 1), mask >> 1)) & mask
        return r.getrandbits(w)

    def inputs(self, cycle: int) -> dict[str, int]:
        r = self.rng
        if cycle >= self.next_phase:                       # bursts and quiet stretches
            self.p_active = r.choice((0.02, 0.1, 0.3, 0.7))
            self.next_phase = cycle + r.randint(20, 200)
        out: dict[str, int] = {}
        for k in self.w:
            if self.hold[k] > 0:
                self.hold[k] -= 1
            elif any(t in k.lower() for t in READY_LIKE):   # back-pressure: long holds of either level
                if r.random() < 0.3:
                    self.last[k] = r.getrandbits(1) if self.w[k] == 1 else self._draw(k)
                    self.hold[k] = r.choice((0, 0, 1, 3, 8, 20))
            elif r.random() < self.p_active:
                self.last[k] = self._draw(k)
            out[k] = self.last[k]
        return out


def _sig(dut: Any, name: str) -> Any:
    try:
        return getattr(dut, name)
    except AttributeError:
        return None


def _val(h: Any) -> int | str:
    v = h.value
    try:
        return int(v)
    except ValueError:
        return "x:" + str(v)


@cocotb.test()
async def lockstep(dut: Any) -> None:
    design = Path(os.environ["FDA_LOCKSTEP_DESIGN"])
    out_path = Path(os.environ["FDA_LOCKSTEP_OUT"])
    mode = os.environ.get("FDA_LOCKSTEP_MODE", "replay")
    seed = int(os.environ.get("FDA_LOCKSTEP_SEED", "1"))
    max_cycles = int(os.environ.get("FDA_LOCKSTEP_CYCLES", "20000"))
    segs = read_record(Path(os.environ["FDA_MODEL_RECORD_IN"])) if os.environ.get("FDA_MODEL_RECORD_IN") else []
    res: dict[str, Any] = {"schema": SCHEMA, "mode": mode, "seed": seed if mode == "fresh" else None, "top": os.environ.get("FDA_LOCKSTEP_TOP"),
                           "ok": True, "segments": [], "divergence": None, "unmapped": {}, "cycles": 0, "resets": 0, "notes": []}

    def finish() -> None:
        out_path.write_text(json.dumps(res, indent=1, default=str))

    sys.path.insert(0, str(design))
    try:
        import model as model_mod
    except Exception as e:
        res.update(ok=False, error=f"model.py did not import: {e!r}")
        return finish()
    spec = _load_spec(design)
    clk_name = ((spec.get("clocks") or [{}])[0] or {}).get("name") or "clk"
    rst = spec.get("reset") or {}
    rst_name, rst_high = rst.get("name") or "rst", (rst.get("polarity") or "active-high") != "active-low"
    clk, rsth = _sig(dut, clk_name), _sig(dut, rst_name)
    if clk is None:
        res.update(ok=False, error=f"no clock port {clk_name!r} on {os.environ.get('FDA_LOCKSTEP_TOP')}")
        return finish()
    cocotb.start_soon(Clock(clk, 10, unit="ns").start())

    if not segs:                                            # no recording: one segment of fresh stimulus with the spec's default parameters
        segs = [[{"op": "new", "params": {}, "test": None}]]
    pool = harvest_pool(segs)
    if mode == "fresh":                                       # independent segments: the recorded Model parameters, new stimulus
        nseg = int(os.environ.get("FDA_LOCKSTEP_FRESH_SEGMENTS", "3"))
        base = [sg[0] for sg in segs]
        segs = [[{"op": "new", "params": (base[i % len(base)].get("params") or {}), "test": None}] for i in range(nseg)]
        in_all = sorted(pool)
    budget = max_cycles
    first = True
    for si, seg in enumerate(segs):
        if budget <= 0:
            res["notes"].append(f"cycle budget {max_cycles} reached after {si} of {len(segs)} segments")
            break
        params = seg[0].get("params") or {}
        try:
            m = model_mod.Model(**params)
        except Exception as e:
            res.update(ok=False, error=f"Model(**{params}) failed: {e!r}")
            return finish()
        ops = [r for r in seg[1:] if r.get("op") in ("step", "reset")]
        in_names = sorted({k for r in ops if r["op"] == "step" for k in (r.get("in") or {})} | set(pool)) if mode == "replay" else in_all
        dut_in = {k: _sig(dut, k) for k in in_names if k not in (clk_name, rst_name)}
        unmapped = sorted(k for k, h in dut_in.items() if h is None)
        res["unmapped"].update({"inputs": sorted(set(res["unmapped"].get("inputs", [])) | set(unmapped))})
        dut_in = {k: h for k, h in dut_in.items() if h is not None}
        widths = {k: max(1, len(h)) for k, h in dut_in.items()}
        if mode == "fresh":
            n = min(budget, int(os.environ.get("FDA_LOCKSTEP_FRESH_CYCLES", "4000")))
            if not in_names:
                res["notes"].append("no input values were recorded: nothing to drive")
            stim = Stim(seed * 1000 + si, widths, pool, n)
            ops = []
            cyc, nxt_rst = 0, stim.rng.randint(300, 1500)
            while cyc < n:
                if cyc == nxt_rst and cyc > 0:
                    ops.append({"op": "reset"})
                    nxt_rst = cyc + stim.rng.randint(300, 2500)
                else:
                    ops.append({"op": "step", "in": stim.inputs(cyc)})
                cyc += 1

        async def do_reset() -> None:
            for h in dut_in.values():
                h.value = 0
            if rsth is None:
                return
            await FallingEdge(clk)
            rsth.value = 1 if rst_high else 0
            for _ in range(RESET_CYCLES):
                await RisingEdge(clk)
                await FallingEdge(clk)
            rsth.value = 0 if rst_high else 1
            res["resets"] += 1
        # the first segment starts from the simulator's power-up state; every segment ends the previous one's state with a reset
        if rsth is None and not first:
            res["notes"].append("no reset port: segments after the first were not replayed")
            break
        if rsth is not None:
            await do_reset()
        else:
            await FallingEdge(clk)
        first = False
        m.reset()
        sdiv = None
        ring: list[dict[str, Any]] = []
        cycle = 0
        compared: set[str] = set()
        missing_out: set[str] = set()
        for r in ops:
            if budget <= 0:
                break
            if r["op"] == "reset":
                if rsth is None:
                    continue
                await do_reset()
                m.reset()
                ring.append({"cycle": cycle, "event": "reset"})
                continue
            vec = {k: v for k, v in (r.get("in") or {}).items()}
            for k, h in dut_in.items():
                if k in vec:
                    h.value = int(vec[k]) & ((1 << widths[k]) - 1)
            try:
                exp = m.step(vec)
            except Exception as e:
                res.update(ok=False, error=f"model.step raised at cycle {cycle}: {e!r}")
                return finish()
            await RisingEdge(clk)
            await ReadOnly()
            diffs, row = [], {}
            for name, ev in (exp or {}).items():
                h = _sig(dut, name)
                if h is None:
                    missing_out.add(name)
                if h is None or not isinstance(ev, int):
                    continue
                compared.add(name)
                w = max(1, len(h))
                actual = _val(h)
                want = ev & ((1 << w) - 1)
                row[name] = [want, actual]
                if actual != want:
                    diffs.append({"signal": name, "expected": want, "actual": actual, "width": w})
            ring.append({"cycle": cycle, "in": vec, "out": row})
            ring = ring[-(CONTEXT + 1):]
            cycle += 1
            budget -= 1
            res["cycles"] += 1
            if diffs:
                sdiv = {"segment": si, "test": seg[0].get("test"), "cycle": cycle - 1, "global_cycle": res["cycles"] - 1,
                        "signals": diffs, "context": ring[:-1], "at": ring[-1]}
                break
            await FallingEdge(clk)
        res["segments"].append({"segment": si, "test": seg[0].get("test"), "cycles": cycle, "compared": sorted(compared), "diverged": sdiv is not None})
        res["unmapped"]["outputs"] = sorted(set(res["unmapped"].get("outputs", [])) | missing_out)
        if sdiv:
            res["ok"], res["divergence"] = False, sdiv
            break
    finish()
