#!/usr/bin/env python3
"""HW/SW partitioning cost model (brief 64A): time and energy per call of one kernel as pure software, as a custom
instruction in a soft CPU, and as an accelerator behind DMA, across problem sizes; the break-even sizes between them;
the whole-application speed-up by Amdahl's law; and the decision rules for custom instruction against accelerator.

    python3 -m hwsw.partition hwsw/examples/partition_crc32.yaml            # table, crossovers, decision
    python3 -m hwsw.partition hwsw/examples/partition_crc32.yaml --json out.json

The model is a set of formulas over stated inputs; it measures nothing. Every input carries a `source` (a measurement
file, a document, or "assumption"), every input may be a range [low, high], and every output is reported as a range
over all corners of the input ranges. The KB skill `hw-sw-partitioning-cost-model` explains the terms; docs/hwsw.md
the input format.

Time per call for N items (an item is the kernel's unit of work: a byte, a word, a sample):

    software            t_sw(N)  = (C_call + c_item * N) / f_cpu
    custom instruction  t_ci(N)  = (C_call_ci + c_item_ci * N) / f_core
    accelerator         t_acc(N) = t_setup + t_cache(N) + t_body(N) + t_done
        t_setup  = mmio_writes * t_mmio_write + mmio_reads * t_mmio_read      (programming the job)
        t_cache  = (bytes_in * N) / flush_rate + (bytes_out * N) / invalidate_rate   (0 on a coherent port)
        t_body   = t_in + t_compute + t_out             (overlap: false; a store-and-forward job)
                 = max(t_in, t_compute, t_out) + t_fill (overlap: true; a streaming pipeline)
            t_in = bytes_in * N / dma_rate, t_out = bytes_out * N / dma_rate,
            t_compute = (latency + ii * N) / f_fabric, t_fill = latency / f_fabric
        t_done   = irq_latency (completion: irq) or poll_read * polls (completion: poll)

Amdahl: a kernel that takes a fraction p of the application's time and runs s times faster gives an overall speed-up
1 / ((1 - p) + p / s), never above 1 / (1 - p).
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import yaml

FORMAT = 1
OPTIONS = ("sw", "ci", "accel")
INPUTS = {
    "sw": {"f_cpu_hz", "cycles_per_call", "cycles_per_item", "power_w"},
    "ci": {"f_core_hz", "cycles_per_call", "cycles_per_item", "power_w"},
    "accel": {"f_fabric_hz", "latency_clocks", "ii_clocks", "bytes_in_per_item", "bytes_out_per_item", "dma_bytes_per_s",
              "mmio_writes", "mmio_reads", "mmio_write_s", "mmio_read_s", "completion", "irq_latency_s", "polls",
              "coherent", "flush_bytes_per_s", "invalidate_bytes_per_s", "overlap", "power_w"},
}
NON_NUMERIC = {"completion", "coherent", "overlap"}


class ModelError(ValueError):
    pass


# ---- inputs ------------------------------------------------------------------------------------------------------------
def _val(spec):
    """An input is a number, a [low, high] range, or {value: <number or range>, source: <text>}."""
    if isinstance(spec, dict):
        return _val(spec.get("value"))
    if isinstance(spec, str):                       # YAML 1.1 reads 100e6 (no dot) as a string
        try:
            return float(spec)
        except ValueError:
            raise ModelError(f"{spec!r} is not a number or a [low, high] range") from None
    if isinstance(spec, (list, tuple)):
        spec = [_val(x) if isinstance(x, str) else x for x in spec]
        if len(spec) != 2 or not all(isinstance(x, (int, float)) for x in spec) or spec[0] > spec[1]:
            raise ModelError(f"a range must be [low, high] with low <= high, not {spec!r}")
        return (float(spec[0]), float(spec[1]))
    if isinstance(spec, bool) or not isinstance(spec, (int, float)):
        raise ModelError(f"{spec!r} is not a number or a [low, high] range")
    return float(spec)


def load(path: str | Path) -> dict:
    d = yaml.safe_load(Path(path).read_text())
    return check_inputs(d, str(path))


def check_inputs(d: dict, where: str = "<dict>") -> dict:
    errs = []
    if not isinstance(d, dict) or d.get("partition") != FORMAT:
        raise ModelError(f"{where}: needs `partition: {FORMAT}` at the top")
    opts = d.get("options") or {}
    if not opts or set(opts) - set(OPTIONS):
        errs.append(f"options: give some of {', '.join(OPTIONS)} (got {sorted(opts)})")
    for o, spec in opts.items():
        if o not in INPUTS:
            continue
        extra = set(spec) - INPUTS[o] - {"label", "notes"}
        if extra:
            errs.append(f"options.{o}: unknown inputs {sorted(extra)}")
        for k, v in spec.items():
            if k in INPUTS[o] and k not in NON_NUMERIC:
                if not (isinstance(v, dict) and "source" in v):
                    errs.append(f"options.{o}.{k}: give {{value: ..., source: ...}} (where the number comes from)")
                try:
                    _val(v)
                except ModelError as ex:
                    errs.append(f"options.{o}.{k}: {ex}")
        need = {"sw": {"f_cpu_hz", "cycles_per_item"}, "ci": {"f_core_hz", "cycles_per_item"},
                "accel": {"f_fabric_hz", "ii_clocks", "bytes_in_per_item", "dma_bytes_per_s", "completion"}}[o]
        for k in sorted(need - set(spec)):
            errs.append(f"options.{o}: missing {k}")
        if o == "accel":
            if spec.get("completion") not in ("irq", "poll"):
                errs.append("options.accel.completion: irq or poll")
            if spec.get("completion") == "irq" and "irq_latency_s" not in spec:
                errs.append("options.accel: completion irq needs irq_latency_s")
            if not spec.get("coherent", False) and ("flush_bytes_per_s" not in spec or "invalidate_bytes_per_s" not in spec):
                errs.append("options.accel: a non-coherent port needs flush_bytes_per_s and invalidate_bytes_per_s "
                            "(or coherent: true)")
    app = d.get("application") or {}
    if "kernel_fraction" in app:
        try:
            p = _val(app["kernel_fraction"])
            lo, hi = p if isinstance(p, tuple) else (p, p)
            if not 0 <= lo <= hi < 1:
                errs.append("application.kernel_fraction: must be in [0, 1)")
        except ModelError as ex:
            errs.append(f"application.kernel_fraction: {ex}")
    sizes = d.get("sizes")
    if not isinstance(sizes, list) or not sizes or not all(isinstance(n, int) and n > 0 for n in sizes):
        errs.append("sizes: a list of positive integers (items per call)")
    if errs:
        raise ModelError(f"{where}:\n  " + "\n  ".join(errs))
    return d


def _ranges(d: dict) -> list[tuple[str, str]]:
    """Every (option, input) whose value is a range: the corners are taken over these."""
    out = []
    for o, spec in d["options"].items():
        for k, v in spec.items():
            if k not in NON_NUMERIC and k in INPUTS[o] and isinstance(_val(v), tuple):
                out.append((o, k))
    app = d.get("application") or {}
    if "kernel_fraction" in app and isinstance(_val(app["kernel_fraction"]), tuple):
        out.append(("application", "kernel_fraction"))
    return out


def corners(d: dict):
    """Every assignment of the ranged inputs to their ends (at most 2**14 corners); yields {option: {input: float}}."""
    rs = _ranges(d)
    if len(rs) > 14:
        raise ModelError(f"{len(rs)} ranged inputs: at most 14 (2**14 corners)")
    base = {o: {k: (v if k in NON_NUMERIC else _val(v)) for k, v in spec.items() if k in INPUTS[o]}
            for o, spec in d["options"].items()}
    app = d.get("application") or {}
    base["application"] = {"kernel_fraction": _val(app["kernel_fraction"])} if "kernel_fraction" in app else {}
    for pick in itertools.product((0, 1), repeat=len(rs)):
        c = {o: dict(v) for o, v in base.items()}
        for (o, k), i in zip(rs, pick):
            c[o][k] = c[o][k][i]
        yield c


# ---- the formulas -------------------------------------------------------------------------------------------------------
def t_sw(p: dict, n: float) -> float:
    return (p.get("cycles_per_call", 0.0) + p["cycles_per_item"] * n) / p["f_cpu_hz"]


def t_ci(p: dict, n: float) -> float:
    return (p.get("cycles_per_call", 0.0) + p["cycles_per_item"] * n) / p["f_core_hz"]


def accel_parts(p: dict, n: float) -> dict:
    setup = p.get("mmio_writes", 0) * p.get("mmio_write_s", 0.0) + p.get("mmio_reads", 0) * p.get("mmio_read_s", 0.0)
    bi, bo = p["bytes_in_per_item"] * n, p.get("bytes_out_per_item", 0.0) * n
    cache = 0.0 if p.get("coherent", False) else bi / p["flush_bytes_per_s"] + bo / p["invalidate_bytes_per_s"]
    t_in, t_out = bi / p["dma_bytes_per_s"], bo / p["dma_bytes_per_s"]
    t_comp = (p.get("latency_clocks", 0.0) + p["ii_clocks"] * n) / p["f_fabric_hz"]
    if p.get("overlap", False):
        body = max(t_in, t_comp, t_out) + p.get("latency_clocks", 0.0) / p["f_fabric_hz"]
    else:
        body = t_in + t_comp + t_out
    done = p["irq_latency_s"] if p["completion"] == "irq" else p.get("polls", 1) * p.get("mmio_read_s", 0.0)
    return {"setup": setup, "cache": cache, "transfer_in": t_in, "compute": t_comp, "transfer_out": t_out,
            "body": body, "done": done, "total": setup + cache + body + done}


def t_accel(p: dict, n: float) -> float:
    return accel_parts(p, n)["total"]


TIME = {"sw": t_sw, "ci": t_ci, "accel": t_accel}


def amdahl(p: float, s: float) -> float:
    """Whole-application speed-up when a fraction p of the time is sped up s times."""
    return 1.0 / ((1.0 - p) + p / s)


def crossings(fa, fb, lo: float = 1.0, hi: float = 2.0 ** 40) -> dict:
    """Where option b is faster than option a over N in [lo, hi]: {'faster_at_lo': bool, 'points': [N, ...]}, the
    sizes at which the faster option changes (log-spaced scan, each change refined by bisection). Both times are
    affine in N or a maximum of affine pieces, so there are at most a few changes."""
    def faster(n):
        return fb(n) < fa(n)
    pts = []
    prev_n, prev = lo, faster(lo)
    n = lo
    while n < hi:
        n = min(hi, n * 1.25 + 1)
        cur = faster(n)
        if cur != prev:
            a, b = prev_n, n
            for _ in range(80):
                mid = (a + b) / 2
                if faster(mid) == prev:
                    a = mid
                else:
                    b = mid
            pts.append(b)
            prev = cur
        prev_n = n
    return {"faster_at_lo": faster(lo), "points": pts}


def break_even(fa, fb, lo: float = 1.0, hi: float = 2.0 ** 40) -> float | None:
    """The size from which b stays faster than a up to hi; lo if b is faster everywhere; None if b is not faster at hi."""
    c = crossings(fa, fb, lo, hi)
    if not fb(hi) < fa(hi):
        return None
    return c["points"][-1] if c["points"] else lo


# ---- evaluation ----------------------------------------------------------------------------------------------------------
def _span(xs):
    xs = [x for x in xs if x is not None]
    return [min(xs), max(xs)] if xs else None


def evaluate(d: dict) -> dict:
    """Times, energies and speed-ups per size, crossovers between options and the Amdahl bound, each as [low, high]
    over the corners of the input ranges."""
    opts = [o for o in OPTIONS if o in d["options"]]
    cs = list(corners(d))
    rows = []
    for n in d["sizes"]:
        row = {"n": n}
        for o in opts:
            ts = [TIME[o](c[o], n) for c in cs]
            row[f"t_{o}_s"] = _span(ts)
            if "power_w" in c_first(cs, o):
                row[f"e_{o}_j"] = _span([TIME[o](c[o], n) * c[o]["power_w"] for c in cs])
        for o in opts:
            if o != "sw" and "sw" in opts:
                row[f"speedup_{o}"] = _span([TIME["sw"](c["sw"], n) / TIME[o](c[o], n) for c in cs])
        if "accel" in opts:
            parts = [accel_parts(c["accel"], n) for c in cs]
            row["accel_parts_s"] = {k: _span([p[k] for p in parts]) for k in parts[0]}
        rows.append(row)
    cross = {}
    for a, b in itertools.combinations(opts, 2):
        for x, y in ((a, b), (b, a)):
            fx = [lambda n, c=c: TIME[x](c[x], n) for c in cs]
            fy = [lambda n, c=c: TIME[y](c[y], n) for c in cs]
            cr = [crossings(f1, f2) for f1, f2 in zip(fx, fy)]
            hi_fast = [f2(2.0 ** 40) < f1(2.0 ** 40) for f1, f2 in zip(fx, fy)]
            n_always = sum(c["faster_at_lo"] and not c["points"] for c in cr)
            n_never = sum(not h for h in hi_fast)
            pts = [c["points"][-1] for c, h in zip(cr, hi_fast) if h and c["points"]]
            if not pts and not n_always:
                continue                                    # y is never faster than x for large N in any corner
            cross[f"{y}_beats_{x}_from_n"] = {
                "range": _span(pts), "corners_crossing": len(pts), "corners_always_faster": n_always,
                "corners_never_faster_at_large_n": n_never, "corners": len(cs),
                "corners_with_several_changes": sum(len(c["points"]) > 1 for c in cr)}
    out = {"kernel": d.get("kernel", ""), "corners": len(cs), "rows": rows, "crossovers": cross}
    app = d.get("application") or {}
    if app.get("typical_n"):
        out["sensitivity_at_typical_n"] = sensitivity(d, app["typical_n"])
    if "kernel_fraction" in app:
        n0 = app.get("typical_n")
        out["amdahl_bound"] = _span([1.0 / (1.0 - c["application"]["kernel_fraction"]) for c in cs])
        if n0:
            out["typical_n"] = n0
            for o in opts:
                if o != "sw":
                    out[f"app_speedup_{o}_at_typical_n"] = _span(
                        [amdahl(c["application"]["kernel_fraction"], TIME["sw"](c["sw"], n0) / TIME[o](c[o], n0)) for c in cs])
    return out


def sensitivity(d: dict, n: float) -> list[dict]:
    """Which ranged input moves the answer most: for each option against software, the kernel speed-up at size n
    with one ranged input at its low and high end and every other at the middle of its range. Sorted by swing, largest
    first: the order in which to measure (brief 64B)."""
    rs = _ranges(d)
    mid = {o: {k: (v if k in NON_NUMERIC else (sum(_val(v)) / 2 if isinstance(_val(v), tuple) else _val(v)))
               for k, v in spec.items() if k in INPUTS[o]} for o, spec in d["options"].items()}
    out = []
    for o in [x for x in OPTIONS if x in d["options"] and x != "sw"]:
        if "sw" not in d["options"]:
            break
        for (oo, k) in rs:
            if oo not in (o, "sw"):
                continue
            vals = []
            for end in _val(d["options"][oo][k]):
                c = {x: dict(v) for x, v in mid.items()}
                c[oo][k] = end
                vals.append(TIME["sw"](c["sw"], n) / TIME[o](c[o], n))
            out.append({"option": o, "input": f"{oo}.{k}", "speedup_at_ends": vals,
                        "swing": abs(vals[1] - vals[0])})
    return sorted(out, key=lambda x: -x["swing"])


def c_first(cs, o):
    return cs[0][o]


# ---- the decision rules -------------------------------------------------------------------------------------------------
# The rule set of the KB skill `custom-instruction-or-accelerator` in executable form. Thresholds are defaults the
# owner may change (they are listed as questions in the brief 64A report), not laws.
DEFAULTS = {
    "max_src_regs": 2,           # read ports of a classic RV32 register file
    "max_dst_regs": 1,
    "max_state_bits": 64,        # small configuration state fits in one or two custom CSRs (like the core's gf.cfg)
    "max_stall_clocks": 4,       # a multi-cycle unit that stalls EX longer than this hurts every instruction behind it
    "min_app_speedup": 1.10,     # below this whole-application gain, keep the software
    "max_core_fmax_loss": 0.05,  # a unit that costs more than 5 % of the core's Fmax must be pipelined or moved out
}


def decide(t: dict, rules: dict | None = None) -> dict:
    """Recommend sw | ci | accel (or `measure` when the evidence straddles the threshold) for one kernel from its
    traits, with every reason stated.

    Traits (missing ones are reported as unknown, never assumed):
      src_regs, dst_regs           operands one call of the operation needs and produces (in registers)
      state_bits                   state kept between calls (accumulators, tables, configuration)
      streaming                    the kernel consumes a stream or a buffer with state across items (FFT, FIR, packets)
      unit_latency_clocks          latency of the function unit at the core's clock (from ip_lib's variant data)
      unit_fmax_hz, core_fmax_hz   the unit's and the core's Fmax estimates
      memory_access                the operation itself must load or store (not just the program around it)
      bytes_per_call, accel_break_even_bytes   data per call and the accelerator's break-even (from evaluate())
      app_speedup_ci, app_speedup_accel        whole-application speed-ups at the typical size, a number or
                                               [low, high] (from evaluate())
      toolchain                    'intrinsic' (compiler or .insn) | 'driver' | 'none'
      reuse_programs               how many programs would use the instruction
    """
    r = dict(DEFAULTS, **(rules or {}))
    why: list[str] = []
    unknown = []

    def get(k):
        if k not in t or t[k] is None:
            unknown.append(k)
            return None
        return t[k]

    ci_ok, acc_ok = True, True
    src, dst, st = get("src_regs"), get("dst_regs"), get("state_bits")
    if src is not None and src > r["max_src_regs"]:
        ci_ok = False
        why.append(f"CI no: needs {src} source registers, the register file reads {r['max_src_regs']}")
    if dst is not None and dst > r["max_dst_regs"]:
        ci_ok = False
        why.append(f"CI no: produces {dst} results, one write port")
    if st is not None and st > r["max_state_bits"]:
        ci_ok = False
        why.append(f"CI no: {st} bits of state between calls (more than {r['max_state_bits']}): an accelerator owns it")
    if get("streaming"):
        ci_ok = False
        why.append("CI no: a streaming kernel with state across items stays an accelerator")
    if get("memory_access"):
        ci_ok = False
        why.append("CI no: the operation itself accesses memory; that is a load/store unit or a DMA master")
    lat = get("unit_latency_clocks")
    if lat is not None and lat > r["max_stall_clocks"]:
        ci_ok = False
        why.append(f"CI no: {lat}-clock latency stalls the pipeline (limit {r['max_stall_clocks']}) unless the core "
                   "scoreboards the result")
    uf, cf = get("unit_fmax_hz"), get("core_fmax_hz")
    if uf is not None and cf is not None and uf < cf * (1 - r["max_core_fmax_loss"]):
        ci_ok = False
        why.append(f"CI no as is: unit Fmax {uf / 1e6:.0f} MHz below the core's {cf / 1e6:.0f} MHz: pipeline it "
                   "(a lower-latency variant may not help) or keep it out of the core")
    bpc, be = get("bytes_per_call"), get("accel_break_even_bytes")
    if bpc is not None and be is not None and bpc < be:
        acc_ok = False
        why.append(f"accelerator no: {bpc} bytes per call is below its break-even {be:.0f} bytes (transfer and "
                   "setup dominate)")
    def rng(v):
        return None if v is None else (tuple(v) if isinstance(v, (list, tuple)) else (v, v))
    sci, sacc = rng(t.get("app_speedup_ci")), rng(t.get("app_speedup_accel"))
    tool = t.get("toolchain")
    if ci_ok and tool == "none":
        why.append("CI cost: no compiler support; every call site needs inline assembly (.insn)")
    if (t.get("reuse_programs") or 0) <= 1 and ci_ok:
        why.append("CI cost: one program uses it; a core change is paid once for one user")
    cands = []
    if ci_ok:
        cands.append(("ci", sci))
    if acc_ok:
        cands.append(("accel", sacc))
    known = [(o, s) for o, s in cands if s is not None]
    th = r["min_app_speedup"]
    sure = [(o, s) for o, s in known if s[0] >= th]
    maybe = [(o, s) for o, s in known if s[0] < th <= s[1]]
    if sure:
        choice, s = max(sure, key=lambda x: x[1][0])
        why.append(f"choose {choice}: whole-application speed-up {s[0]:.2f} .. {s[1]:.2f} at the typical size, "
                   f"at least {th} at every corner")
    elif maybe:
        choice = "measure"
        why.append("undecided: " + "; ".join(f"{o} gives {s[0]:.2f} .. {s[1]:.2f}" for o, s in maybe)
                   + f", which straddles {th}: measure the uncertain inputs (the widest ranges) before choosing")
    else:
        choice = "sw"
        best = max(known, key=lambda x: x[1][1], default=None)
        why.append(f"choose software: no option passes its rules with a whole-application speed-up of {th} or more"
                   + (f" (best {best[0]}: at most {best[1][1]:.2f})" if best else ""))
    return {"choice": choice, "ci_eligible": ci_ok, "accel_eligible": acc_ok, "reasons": why, "unknown": unknown}


# ---- report --------------------------------------------------------------------------------------------------------------
def _fmt_t(x):
    lo, hi = x
    def one(v):
        for unit, s in (("s", 1), ("ms", 1e-3), ("us", 1e-6), ("ns", 1e-9)):
            if v >= s:
                return f"{v / s:.3g} {unit}"
        return f"{v / 1e-9:.3g} ns"
    return one(lo) if math.isclose(lo, hi, rel_tol=1e-9) else f"{one(lo)} .. {one(hi)}"


def _fmt_x(x):
    return "never" if x is None else (f"{x[0]:.3g}" if math.isclose(x[0], x[1], rel_tol=1e-9) else f"{x[0]:.3g} .. {x[1]:.3g}")


def report(d: dict, out: dict, dec: dict | None) -> str:
    opts = [o for o in OPTIONS if o in d["options"]]
    L = [f"Kernel: {out['kernel']} ({out['corners']} input corners)", ""]
    head = ["N"] + [f"t_{o}" for o in opts] + [f"speed-up {o}" for o in opts if o != "sw"]
    L.append(" | ".join(head))
    for r in out["rows"]:
        cells = [str(r["n"])] + [_fmt_t(r[f"t_{o}_s"]) for o in opts] + \
                [_fmt_x(r[f"speedup_{o}"]) for o in opts if o != "sw" and f"speedup_{o}" in r]
        L.append(" | ".join(cells))
    L.append("")
    for k, v in out["crossovers"].items():
        y, x = k.replace("_from_n", "").split("_beats_")
        parts = []
        if v["corners_crossing"]:
            parts.append(f"from N = {_fmt_x(v['range'])} in {v['corners_crossing']} of {v['corners']} corners")
        if v["corners_always_faster"]:
            parts.append(f"at every N in {v['corners_always_faster']} corners")
        if v["corners_never_faster_at_large_n"]:
            parts.append(f"not at large N in {v['corners_never_faster_at_large_n']} corners")
        L.append(f"{y} faster than {x}: " + "; ".join(parts))
    if "amdahl_bound" in out:
        L.append(f"Amdahl bound (kernel time to zero): {_fmt_x(out['amdahl_bound'])}")
        for k, v in out.items():
            if k.startswith("app_speedup_"):
                L.append(f"{k}: {_fmt_x(v)}")
    if out.get("sensitivity_at_typical_n"):
        L += ["", f"What moves the kernel speed-up at N = {out['typical_n'] if 'typical_n' in out else ''} most "
                  "(one input at each end, the others mid-range):"]
        for x in out["sensitivity_at_typical_n"][:5]:
            a, b = x["speedup_at_ends"]
            L.append(f"  {x['option']}: {x['input']}: {a:.3g} .. {b:.3g}")
    if dec:
        L += ["", f"Decision: {dec['choice']}"] + [f"  - {x}" for x in dec["reasons"]]
        if dec["unknown"]:
            L.append(f"  unknown traits (not assumed): {', '.join(dec['unknown'])}")
    return "\n".join(L)


def run(path: str | Path) -> tuple[dict, dict | None]:
    d = load(path)
    out = evaluate(d)
    dec = None
    if "traits" in d:
        t = dict(d["traits"])
        if "accel" in d["options"] and "sw" in d["options"] and "accel_break_even_bytes" not in t:
            v = out["crossovers"].get("accel_beats_sw_from_n", {}).get("range")
            if v:
                bpi = _val(d["options"]["accel"]["bytes_in_per_item"])
                bpi = bpi[1] if isinstance(bpi, tuple) else bpi
                t["accel_break_even_bytes"] = v[1] * bpi            # the pessimistic end
        for o in ("ci", "accel"):
            k = f"app_speedup_{o}_at_typical_n"
            if k in out and f"app_speedup_{o}" not in t:
                t[f"app_speedup_{o}"] = out[k]                      # [low, high] over the corners
        dec = decide(t, d.get("rules"))
    return out, dec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hwsw.partition", description=__doc__.split("\n\n")[0])
    ap.add_argument("yaml")
    ap.add_argument("--json", default=None, help="write the evaluation and the decision as JSON")
    a = ap.parse_args(argv)
    try:
        d = load(a.yaml)
        out, dec = run(a.yaml)
    except ModelError as ex:
        print(ex, file=sys.stderr)
        return 2
    print(report(d, out, dec))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"inputs": a.yaml, "evaluation": out, "decision": dec}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
